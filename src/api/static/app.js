const pendingList = document.getElementById('pending-list');
const pendingStatus = document.getElementById('pending-status');
const decisionStatus = document.getElementById('decision-status');
const decisionResult = document.getElementById('decision-result');
const refreshBtn = document.getElementById('refresh-btn');
const decisionForm = document.getElementById('decision-form');
const checkpointInput = document.getElementById('checkpoint-id');
const reviewerInput = document.getElementById('reviewer-id');
const notesInput = document.getElementById('notes');
const clearBtn = document.getElementById('clear-btn');
const baseUrlInput = document.getElementById('base-url');
const applyUrlBtn = document.getElementById('apply-url');
const serverUrlLabel = document.getElementById('server-url');
const pendingCount = document.getElementById('pending-count');
const lastRefresh = document.getElementById('last-refresh');

let baseUrl = window.location.origin;
let selectedCheckpoint = '';

function setStatus(el, message, type = 'info') {
  if (!el) return;
  el.textContent = message;
  el.style.color = type === 'error' ? '#f4725b' : '#a8c0c7';
}

function setDecisionResult(payload) {
  decisionResult.textContent = payload ? JSON.stringify(payload, null, 2) : '';
  decisionResult.classList.remove('success', 'error');
  if (!payload) return;
  if (payload.workflow_status === 'COMPLETED') {
    decisionResult.classList.add('success');
  }
  if (payload.workflow_status === 'REQUIRES_MANUAL_HANDLING') {
    decisionResult.classList.add('error');
  }
}

function formatAmount(value) {
  if (value === undefined || value === null) return '-';
  try {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(value);
  } catch (err) {
    return String(value);
  }
}

function formatDate(value) {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function highlightSelected() {
  const cards = pendingList.querySelectorAll('.card');
  cards.forEach((card) => {
    const checkpoint = card.dataset.checkpoint;
    card.classList.toggle('selected', checkpoint && checkpoint === selectedCheckpoint);
  });
}

function fillDecision(item) {
  checkpointInput.value = item.checkpoint_id;
  selectedCheckpoint = item.checkpoint_id;
  highlightSelected();
  setStatus(decisionStatus, 'Checkpoint loaded. Submit a decision.');
}

function renderList(items) {
  pendingList.innerHTML = '';
  if (!items.length) {
    pendingList.innerHTML = '<div class="card">No pending reviews.</div>';
    return;
  }

  items.forEach((item, index) => {
    const card = document.createElement('div');
    card.className = 'card';
    card.dataset.checkpoint = item.checkpoint_id;
    card.style.animationDelay = `${index * 0.04}s`;

    const top = document.createElement('div');
    top.className = 'card-top';

    const heading = document.createElement('div');
    const title = document.createElement('h4');
    title.textContent = item.vendor_name || 'Unknown vendor';
    const tiny = document.createElement('p');
    tiny.className = 'tiny';
    tiny.textContent = `Invoice: ${item.invoice_id || '-'}`;
    heading.appendChild(title);
    heading.appendChild(tiny);

    const badge = document.createElement('div');
    badge.className = 'badge';
    badge.textContent = item.checkpoint_id;

    top.appendChild(heading);
    top.appendChild(badge);

    const meta = document.createElement('div');
    meta.className = 'card-meta';
    meta.innerHTML = `
      <div>Amount: ${formatAmount(item.amount)}</div>
      <div>Reason: ${item.reason_for_hold || '-'}</div>
      <div>Created: ${formatDate(item.created_at)}</div>
    `;

    const actions = document.createElement('div');
    actions.className = 'card-actions';

    const useBtn = document.createElement('button');
    useBtn.className = 'ghost';
    useBtn.textContent = 'Use ID';
    useBtn.addEventListener('click', (event) => {
      event.stopPropagation();
      fillDecision(item);
    });

    const copyBtn = document.createElement('button');
    copyBtn.className = 'ghost';
    copyBtn.textContent = 'Copy';
    copyBtn.addEventListener('click', async (event) => {
      event.stopPropagation();
      try {
        await navigator.clipboard.writeText(item.checkpoint_id);
        setStatus(pendingStatus, 'Checkpoint ID copied.');
      } catch (err) {
        setStatus(pendingStatus, 'Copy failed.', 'error');
      }
    });

    actions.appendChild(useBtn);
    actions.appendChild(copyBtn);

    if (item.review_url) {
      const link = document.createElement('a');
      link.className = 'link';
      link.textContent = 'Open';
      link.href = item.review_url;
      link.target = '_blank';
      link.rel = 'noreferrer';
      actions.appendChild(link);
    }

    card.appendChild(top);
    card.appendChild(meta);
    card.appendChild(actions);

    card.addEventListener('click', () => fillDecision(item));

    pendingList.appendChild(card);
  });

  highlightSelected();
}

async function fetchPending() {
  setStatus(pendingStatus, 'Loading pending reviews...');
  try {
    const response = await fetch(`${baseUrl}/human-review/pending`);
    if (!response.ok) {
      throw new Error(`Request failed with ${response.status}`);
    }
    const payload = await response.json();
    const items = payload.items || [];
    setStatus(pendingStatus, `Found ${items.length} pending review(s).`);
    if (pendingCount) {
      pendingCount.textContent = items.length;
    }
    if (lastRefresh) {
      lastRefresh.textContent = `Last refresh: ${new Date().toLocaleTimeString()}`;
    }
    renderList(items);
  } catch (err) {
    setStatus(pendingStatus, `Error: ${err.message}`, 'error');
  }
}

async function submitDecision(event) {
  event.preventDefault();
  setDecisionResult('');
  setStatus(decisionStatus, 'Submitting decision...');

  const decision = decisionForm.querySelector('input[name="decision"]:checked')?.value || 'ACCEPT';
  const payload = {
    checkpoint_id: checkpointInput.value.trim(),
    decision,
    notes: notesInput.value.trim(),
    reviewer_id: reviewerInput.value.trim(),
  };

  if (!payload.checkpoint_id || !payload.reviewer_id) {
    setStatus(decisionStatus, 'Checkpoint ID and Reviewer ID are required.', 'error');
    return;
  }

  try {
    const response = await fetch(`${baseUrl}/human-review/decision`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Decision failed');
    }

    const result = await response.json();
    setStatus(decisionStatus, 'Decision recorded.');
    setDecisionResult(result);
    fetchPending();
  } catch (err) {
    setStatus(decisionStatus, `Error: ${err.message}`, 'error');
  }
}

function applyBaseUrl() {
  const value = baseUrlInput.value.trim();
  baseUrl = value || window.location.origin;
  serverUrlLabel.textContent = baseUrl;
  fetchPending();
}

refreshBtn.addEventListener('click', fetchPending);
decisionForm.addEventListener('submit', submitDecision);
clearBtn.addEventListener('click', () => {
  checkpointInput.value = '';
  reviewerInput.value = '';
  notesInput.value = '';
  selectedCheckpoint = '';
  setDecisionResult('');
  highlightSelected();
  setStatus(decisionStatus, 'Form cleared.');
});
applyUrlBtn.addEventListener('click', applyBaseUrl);

baseUrlInput.value = baseUrl;
serverUrlLabel.textContent = baseUrl;
fetchPending();
