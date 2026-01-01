from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_sqlite_path(db_conn: str) -> str:
    if db_conn.startswith("sqlite:///"):
        path = db_conn[len("sqlite:///") :]
    elif db_conn.startswith("sqlite://"):
        path = db_conn[len("sqlite://") :]
    else:
        raise ValueError("Only sqlite connection strings are supported in demo mode.")

    if not path:
        raise ValueError("Invalid sqlite path.")

    if not os.path.isabs(path):
        path = os.path.abspath(path)
    return path


def _ensure_db_dir(path: str) -> None:
    directory = os.path.dirname(path)
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)


def _connect(db_conn: str) -> sqlite3.Connection:
    path = _parse_sqlite_path(db_conn)
    _ensure_db_dir(path)
    return sqlite3.connect(path, check_same_thread=False)


def init_db(db_conn: str) -> None:
    conn = _connect(db_conn)
    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS checkpoints (
                checkpoint_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                state_blob TEXT NOT NULL,
                status TEXT NOT NULL,
                invoice_id TEXT,
                vendor_name TEXT,
                amount REAL,
                reason TEXT,
                review_url TEXT,
                decision TEXT,
                reviewer_id TEXT,
                notes TEXT,
                decided_at TEXT,
                resume_token TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS raw_invoices (
                raw_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                invoice_id TEXT,
                vendor_name TEXT,
                amount REAL,
                currency TEXT,
                attachments TEXT,
                payload TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS human_review_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                checkpoint_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                status TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS final_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                invoice_id TEXT,
                vendor_name TEXT,
                amount REAL,
                currency TEXT,
                status TEXT,
                final_payload TEXT NOT NULL
            )
            """
        )
    conn.close()


def save_raw_invoice(
    db_conn: str,
    raw_id: str,
    payload: Dict[str, Any],
) -> None:
    init_db(db_conn)
    invoice_id = payload.get("invoice_id")
    vendor_name = payload.get("vendor_name")
    amount = payload.get("amount")
    currency = payload.get("currency")
    attachments = json.dumps(payload.get("attachments", []))
    payload_blob = json.dumps(payload)
    conn = _connect(db_conn)
    with conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO raw_invoices (
                raw_id, created_at, invoice_id, vendor_name,
                amount, currency, attachments, payload
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                raw_id,
                _utc_now(),
                invoice_id,
                vendor_name,
                amount,
                currency,
                attachments,
                payload_blob,
            ),
        )
    conn.close()


def save_final_result(
    db_conn: str,
    run_id: str,
    payload: Dict[str, Any],
    status: str,
    final_payload: Dict[str, Any],
) -> None:
    init_db(db_conn)
    invoice_id = payload.get("invoice_id")
    vendor_name = payload.get("vendor_name")
    amount = payload.get("amount")
    currency = payload.get("currency")
    payload_blob = json.dumps(final_payload)
    conn = _connect(db_conn)
    with conn:
        conn.execute(
            """
            INSERT INTO final_results (
                run_id, created_at, invoice_id, vendor_name,
                amount, currency, status, final_payload
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                _utc_now(),
                invoice_id,
                vendor_name,
                amount,
                currency,
                status,
                payload_blob,
            ),
        )
    conn.close()


def save_checkpoint(
    db_conn: str,
    state: Dict[str, Any],
    reason: str,
    review_url: str,
    invoice_id: Optional[str] = None,
    vendor_name: Optional[str] = None,
    amount: Optional[float] = None,
    checkpoint_id: Optional[str] = None,
) -> str:
    init_db(db_conn)
    checkpoint_id = checkpoint_id or f"chk_{uuid.uuid4().hex[:12]}"
    payload = json.dumps(state)
    now = _utc_now()

    conn = _connect(db_conn)
    with conn:
        conn.execute(
            """
            INSERT INTO checkpoints (
                checkpoint_id, created_at, state_blob, status, invoice_id,
                vendor_name, amount, reason, review_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                checkpoint_id,
                now,
                payload,
                "PENDING",
                invoice_id,
                vendor_name,
                amount,
                reason,
                review_url,
            ),
        )
        conn.execute(
            """
            INSERT INTO human_review_queue (checkpoint_id, created_at, status)
            VALUES (?, ?, ?)
            """,
            (checkpoint_id, now, "PENDING"),
        )
    conn.close()
    return checkpoint_id


def list_pending_reviews(db_conn: str) -> List[Dict[str, Any]]:
    init_db(db_conn)
    conn = _connect(db_conn)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT c.checkpoint_id, c.invoice_id, c.vendor_name, c.amount, c.created_at,
               c.reason AS reason_for_hold, c.review_url
        FROM checkpoints c
        WHERE c.status = 'PENDING'
        ORDER BY c.created_at ASC
        """
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def load_checkpoint(db_conn: str, checkpoint_id: str) -> Dict[str, Any]:
    init_db(db_conn)
    conn = _connect(db_conn)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        """
        SELECT state_blob FROM checkpoints WHERE checkpoint_id = ?
        """,
        (checkpoint_id,),
    ).fetchone()
    conn.close()
    if not row:
        raise KeyError(f"Checkpoint '{checkpoint_id}' not found.")
    return json.loads(row["state_blob"])


def save_human_decision(
    db_conn: str,
    checkpoint_id: str,
    decision: str,
    notes: str,
    reviewer_id: str,
) -> Tuple[str, str]:
    init_db(db_conn)
    resume_token = f"resume_{uuid.uuid4().hex[:10]}"
    decision = decision.upper()
    next_stage = "RECONCILE" if decision == "ACCEPT" else "MANUAL_HANDOFF"

    conn = _connect(db_conn)
    with conn:
        conn.execute(
            """
            UPDATE checkpoints
            SET status = ?, decision = ?, notes = ?, reviewer_id = ?, decided_at = ?, resume_token = ?
            WHERE checkpoint_id = ?
            """,
            (
                "RESOLVED",
                decision,
                notes,
                reviewer_id,
                _utc_now(),
                resume_token,
                checkpoint_id,
            ),
        )
        conn.execute(
            """
            UPDATE human_review_queue
            SET status = ?
            WHERE checkpoint_id = ?
            """,
            ("RESOLVED", checkpoint_id),
        )
    conn.close()
    return resume_token, next_stage


def get_checkpoint_status(db_conn: str, checkpoint_id: str) -> Dict[str, Any]:
    init_db(db_conn)
    conn = _connect(db_conn)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        """
        SELECT checkpoint_id, status, decision, reviewer_id, resume_token
        FROM checkpoints WHERE checkpoint_id = ?
        """,
        (checkpoint_id,),
    ).fetchone()
    conn.close()
    if not row:
        raise KeyError(f"Checkpoint '{checkpoint_id}' not found.")
    return dict(row)
