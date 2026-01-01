from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, Sequence

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    ChannelVersions,
    WRITES_IDX_MAP,
    get_checkpoint_id,
    get_checkpoint_metadata,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_sqlite_path(db_conn: str) -> str:
    if db_conn.startswith("sqlite:///"):
        path = db_conn[len("sqlite:///") :]
    elif db_conn.startswith("sqlite://"):
        path = db_conn[len("sqlite://") :]
    else:
        raise ValueError("Only sqlite connection strings are supported for SQLiteSaver.")

    if not path:
        raise ValueError("Invalid sqlite path.")

    if not os.path.isabs(path):
        path = os.path.abspath(path)
    return path


def _connect(db_conn: str) -> sqlite3.Connection:
    path = _parse_sqlite_path(db_conn)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return sqlite3.connect(path, check_same_thread=False)


def _ensure_columns(conn: sqlite3.Connection, table: str, columns: Dict[str, str]) -> None:
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    for name, ddl in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


class SQLiteSaver(BaseCheckpointSaver[str]):
    def __init__(self, db_conn: str) -> None:
        super().__init__()
        self.db_conn = db_conn
        self._legacy_checkpoint_columns: bool = False
        self._legacy_metadata_columns: bool = False
        self._legacy_write_value_column: bool = False
        self._init_db()

    def _init_db(self) -> None:
        conn = _connect(self.db_conn)
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS lg_checkpoints (
                    thread_id TEXT NOT NULL,
                    checkpoint_ns TEXT NOT NULL,
                    checkpoint_id TEXT NOT NULL,
                    parent_checkpoint_id TEXT,
                    checkpoint_type TEXT,
                    checkpoint_blob BLOB,
                    metadata_type TEXT,
                    metadata_blob BLOB,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS lg_writes (
                    thread_id TEXT NOT NULL,
                    checkpoint_ns TEXT NOT NULL,
                    checkpoint_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    write_idx INTEGER NOT NULL,
                    value_type TEXT,
                    value_blob BLOB,
                    task_path TEXT NOT NULL,
                    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, channel, write_idx)
                )
                """
            )
            _ensure_columns(
                conn,
                "lg_checkpoints",
                {
                    "checkpoint_type": "TEXT",
                    "checkpoint_blob": "BLOB",
                    "metadata_type": "TEXT",
                    "metadata_blob": "BLOB",
                },
            )
            _ensure_columns(
                conn,
                "lg_writes",
                {
                    "value_type": "TEXT",
                    "value_blob": "BLOB",
                },
            )
            checkpoint_cols = {row[1] for row in conn.execute("PRAGMA table_info(lg_checkpoints)")}
            write_cols = {row[1] for row in conn.execute("PRAGMA table_info(lg_writes)")}
            self._legacy_checkpoint_columns = "checkpoint" in checkpoint_cols
            self._legacy_metadata_columns = "metadata" in checkpoint_cols
            self._legacy_write_value_column = "value" in write_cols
        conn.close()

    def _load_writes(
        self, thread_id: str, checkpoint_ns: str, checkpoint_id: str
    ) -> list[tuple[str, str, Any]]:
        conn = _connect(self.db_conn)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT task_id, channel, value_type, value_blob
            FROM lg_writes
            WHERE thread_id = ? AND checkpoint_ns = ? AND checkpoint_id = ?
            ORDER BY write_idx ASC
            """,
            (thread_id, checkpoint_ns, checkpoint_id),
        ).fetchall()
        conn.close()
        return [
            (
                row["task_id"],
                row["channel"],
                self.serde.loads_typed(
                    (row["value_type"], row["value_blob"])
                    if row["value_type"] is not None
                    else ("bytes", row["value_blob"])
                ),
            )
            for row in rows
        ]

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        thread_id: str = config["configurable"]["thread_id"]
        checkpoint_ns: str = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = get_checkpoint_id(config)

        conn = _connect(self.db_conn)
        conn.row_factory = sqlite3.Row
        if checkpoint_id:
            row = conn.execute(
                """
                SELECT * FROM lg_checkpoints
                WHERE thread_id = ? AND checkpoint_ns = ? AND checkpoint_id = ?
                """,
                (thread_id, checkpoint_ns, checkpoint_id),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT * FROM lg_checkpoints
                WHERE thread_id = ? AND checkpoint_ns = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (thread_id, checkpoint_ns),
            ).fetchone()
        conn.close()

        if not row:
            return None

        checkpoint_type = row["checkpoint_type"] or "bytes"
        metadata_type = row["metadata_type"] or "bytes"
        checkpoint = self.serde.loads_typed((checkpoint_type, row["checkpoint_blob"]))
        metadata = self.serde.loads_typed((metadata_type, row["metadata_blob"]))
        parent_id = row["parent_checkpoint_id"]
        pending_writes = self._load_writes(thread_id, checkpoint_ns, row["checkpoint_id"])

        config_out = {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": row["checkpoint_id"],
            }
        }
        parent_config = (
            {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "checkpoint_id": parent_id,
                }
            }
            if parent_id
            else None
        )

        return CheckpointTuple(
            config=config_out,
            checkpoint=checkpoint,
            metadata=metadata,
            pending_writes=pending_writes,
            parent_config=parent_config,
        )

    def list(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        conn = _connect(self.db_conn)
        conn.row_factory = sqlite3.Row

        params: list[Any] = []
        where = []
        if config:
            where.append("thread_id = ?")
            params.append(config["configurable"]["thread_id"])
            where.append("checkpoint_ns = ?")
            params.append(config["configurable"].get("checkpoint_ns", ""))
        if before and get_checkpoint_id(before):
            where.append("checkpoint_id < ?")
            params.append(get_checkpoint_id(before))

        where_clause = f"WHERE {' AND '.join(where)}" if where else ""
        sql = f"SELECT * FROM lg_checkpoints {where_clause} ORDER BY created_at DESC"
        if limit is not None:
            sql += f" LIMIT {int(limit)}"

        rows = conn.execute(sql, params).fetchall()
        conn.close()

        for row in rows:
            metadata_type = row["metadata_type"] or "bytes"
            metadata = self.serde.loads_typed((metadata_type, row["metadata_blob"]))
            if filter and not all(metadata.get(k) == v for k, v in filter.items()):
                continue
            checkpoint_type = row["checkpoint_type"] or "bytes"
            checkpoint = self.serde.loads_typed((checkpoint_type, row["checkpoint_blob"]))
            pending_writes = self._load_writes(
                row["thread_id"], row["checkpoint_ns"], row["checkpoint_id"]
            )
            config_out = {
                "configurable": {
                    "thread_id": row["thread_id"],
                    "checkpoint_ns": row["checkpoint_ns"],
                    "checkpoint_id": row["checkpoint_id"],
                }
            }
            parent_config = (
                {
                    "configurable": {
                        "thread_id": row["thread_id"],
                        "checkpoint_ns": row["checkpoint_ns"],
                        "checkpoint_id": row["parent_checkpoint_id"],
                    }
                }
                if row["parent_checkpoint_id"]
                else None
            )
            yield CheckpointTuple(
                config=config_out,
                checkpoint=checkpoint,
                metadata=metadata,
                pending_writes=pending_writes,
                parent_config=parent_config,
            )

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        parent_checkpoint_id = config["configurable"].get("checkpoint_id")

        checkpoint_type, checkpoint_blob = self.serde.dumps_typed(checkpoint)
        metadata_type, metadata_blob = self.serde.dumps_typed(
            get_checkpoint_metadata(config, metadata)
        )
        checkpoint_id = checkpoint["id"]

        columns = [
            "thread_id",
            "checkpoint_ns",
            "checkpoint_id",
            "parent_checkpoint_id",
            "checkpoint_type",
            "checkpoint_blob",
            "metadata_type",
            "metadata_blob",
            "created_at",
        ]
        values = [
            thread_id,
            checkpoint_ns,
            checkpoint_id,
            parent_checkpoint_id,
            checkpoint_type,
            checkpoint_blob,
            metadata_type,
            metadata_blob,
            _utc_now(),
        ]
        if self._legacy_checkpoint_columns:
            columns.append("checkpoint")
            values.append(checkpoint_blob)
        if self._legacy_metadata_columns:
            columns.append("metadata")
            values.append(metadata_blob)

        sql = (
            f"INSERT OR REPLACE INTO lg_checkpoints ({', '.join(columns)}) "
            f"VALUES ({', '.join(['?'] * len(columns))})"
        )

        conn = _connect(self.db_conn)
        with conn:
            conn.execute(sql, values)
        conn.close()

        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint_id,
            }
        }

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = config["configurable"]["checkpoint_id"]

        conn = _connect(self.db_conn)
        with conn:
            for idx, (channel, value) in enumerate(writes):
                write_idx = WRITES_IDX_MAP.get(channel, idx)
                value_type, value_blob = self.serde.dumps_typed(value)
                columns = [
                    "thread_id",
                    "checkpoint_ns",
                    "checkpoint_id",
                    "task_id",
                    "channel",
                    "write_idx",
                    "value_type",
                    "value_blob",
                    "task_path",
                ]
                values = [
                    thread_id,
                    checkpoint_ns,
                    checkpoint_id,
                    task_id,
                    channel,
                    write_idx,
                    value_type,
                    value_blob,
                    task_path,
                ]
                if self._legacy_write_value_column:
                    columns.append("value")
                    values.append(value_blob)
                sql = (
                    f"INSERT OR REPLACE INTO lg_writes ({', '.join(columns)}) "
                    f"VALUES ({', '.join(['?'] * len(columns))})"
                )
                conn.execute(sql, values)
        conn.close()

    def delete_thread(self, thread_id: str) -> None:
        conn = _connect(self.db_conn)
        with conn:
            conn.execute("DELETE FROM lg_checkpoints WHERE thread_id = ?", (thread_id,))
            conn.execute("DELETE FROM lg_writes WHERE thread_id = ?", (thread_id,))
        conn.close()

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        return self.get_tuple(config)

    async def alist(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        for item in self.list(config, filter=filter, before=before, limit=limit):
            yield item

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        return self.put(config, checkpoint, metadata, new_versions)

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        return self.put_writes(config, writes, task_id, task_path)

    async def adelete_thread(self, thread_id: str) -> None:
        return self.delete_thread(thread_id)
