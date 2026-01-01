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
const stepPending = document.getElementById('step-pending');
const finalRefreshBtn = document.getElementById('final-refresh');
const finalStatus = document.getElementById('final-status');
const finalList = document.getElementById('final-list');
const invoiceForm = document.getElementById('invoice-form');
const invoiceInput = document.getElementById('invoice-json');
const invoiceStatus = document.getElementById('invoice-status');
const invoiceResult = document.getElementById('invoice-result');
const loadSampleBtn = document.getElementById('load-sample');
const loadMismatchBtn = document.getElementById('load-mismatch');
const clearInvoiceBtn = document.getElementById('clear-invoice');

let baseUrl = window.location.origin;
let selectedCheckpoint = '';

const SAMPLE_INVOICE = {
  invoice_id: 'INV-1001',
  vendor_name: 'acme supplies',
  vendor_tax_id: 'GST-112233',
  invoice_date: '2024-05-01',
  due_date: '2024-05-31',
  amount: 12500.5,
  currency: 'USD',
  line_items: [
    { desc: 'Paper', qty: 10, unit_price: 50, total: 500 },
    { desc: 'Ink', qty: 5, unit_price: 200, total: 1000 },
  ],
  attachments: ['invoice_1001.pdf'],
};

const SAMPLE_MISMATCH = {
  invoice_id: 'INV-1002',
  vendor_name: 'acme supplies',
  vendor_tax_id: 'GST-112233',
  invoice_date: '2024-05-15',
  due_date: '2024-06-15',
  amount: 12500.5,
  currency: 'USD',
  po_amount: 9000,
  line_items: [
    { desc: 'Paper', qty: 10, unit_price: 50, total: 500 },
    { desc: 'Ink', qty: 5, unit_price: 200, total: 1000 },
  ],
  attachments: ['invoice_1002.pdf'],
};

function setStatus(el, message, type = 'info') {
  if (!el) return;
  el.textContent = message;
  el.style.color = type === 'error' ? '#e11d48' : '#5f6b7a';
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

function setInvoiceResult(payload, type) {
  if (!invoiceResult) return;
  invoiceResult.textContent = payload ? JSON.stringify(payload, null, 2) : '';
  invoiceResult.classList.remove('success', 'warning', 'error');
  if (!payload) return;
  if (type) {
    invoiceResult.classList.add(type);
    return;
  }
  if (payload.status === 'COMPLETED') {
    invoiceResult.classList.add('success');
  } else if (payload.status === 'PAUSED') {
    invoiceResult.classList.add('warning');
  } else if (payload.status === 'REQUIRES_MANUAL_HANDLING') {
    invoiceResult.classList.add('error');
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

function renderFinalResults(items) {
  if (!finalList) return;
  finalList.innerHTML = '';
  if (!items.length) {
    finalList.innerHTML = '<div class="card">No final results yet.</div>';
    return;
  }

  items.forEach((item) => {
    const card = document.createElement('div');
    card.className = 'card';
    if (item.status === 'COMPLETED') {
      card.classList.add('success');
    }
    if (item.status === 'REQUIRES_MANUAL_HANDLING') {
      card.classList.add('danger');
    }

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
    badge.textContent = item.status || 'UNKNOWN';

    top.appendChild(heading);
    top.appendChild(badge);

    const meta = document.createElement('div');
    meta.className = 'card-meta';
    meta.innerHTML = `
      <div>Amount: ${formatAmount(item.amount)}</div>
      <div>Currency: ${item.currency || '-'}</div>
      <div>Created: ${formatDate(item.created_at)}</div>
    `;

    card.appendChild(top);
    card.appendChild(meta);
    finalList.appendChild(card);
  });
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

async function fetchFinalResults() {
  if (!finalList) return;
  setStatus(finalStatus, 'Loading final results...');
  try {
    const response = await fetch(`${baseUrl}/final-results`);
    if (!response.ok) {
      throw new Error(`Request failed with ${response.status}`);
    }
    const payload = await response.json();
    const items = payload.items || [];
    setStatus(finalStatus, `Found ${items.length} result(s).`);
    renderFinalResults(items);
  } catch (err) {
    setStatus(finalStatus, `Error: ${err.message}`, 'error');
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

async function submitInvoice(event) {
  event.preventDefault();
  setInvoiceResult('');
  setStatus(invoiceStatus, 'Submitting invoice...');

  let payload;
  try {
    payload = JSON.parse(invoiceInput.value);
  } catch (err) {
    setStatus(invoiceStatus, 'Invalid JSON payload.', 'error');
    setInvoiceResult({ error: err.message }, 'error');
    return;
  }

  try {
    const response = await fetch(`${baseUrl}/invoice/submit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Submission failed');
    }

    const result = await response.json();
    setStatus(invoiceStatus, `Workflow status: ${result.status}`);
    setInvoiceResult(result);
    if (result.status === 'PAUSED') {
      fetchPending();
      if (stepPending) {
        stepPending.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    }
  } catch (err) {
    setStatus(invoiceStatus, `Error: ${err.message}`, 'error');
    setInvoiceResult({ error: err.message }, 'error');
  }
}

function applyBaseUrl() {
  const value = baseUrlInput.value.trim();
  baseUrl = value || window.location.origin;
  serverUrlLabel.textContent = baseUrl;
  fetchPending();
}

function loadInvoiceSample(sample, label) {
  if (!invoiceInput) return;
  invoiceInput.value = JSON.stringify(sample, null, 2);
  setStatus(invoiceStatus, `${label} loaded.`);
  setInvoiceResult('');
}

refreshBtn.addEventListener('click', fetchPending);
decisionForm.addEventListener('submit', submitDecision);
if (finalRefreshBtn) {
  finalRefreshBtn.addEventListener('click', fetchFinalResults);
}
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

if (invoiceForm) {
  invoiceForm.addEventListener('submit', submitInvoice);
}
if (loadSampleBtn) {
  loadSampleBtn.addEventListener('click', () => loadInvoiceSample(SAMPLE_INVOICE, 'Sample invoice'));
}
if (loadMismatchBtn) {
  loadMismatchBtn.addEventListener('click', () => loadInvoiceSample(SAMPLE_MISMATCH, 'Mismatch sample'));
}
if (clearInvoiceBtn) {
  clearInvoiceBtn.addEventListener('click', () => {
    if (invoiceInput) {
      invoiceInput.value = '';
    }
    setInvoiceResult('');
    setStatus(invoiceStatus, 'Invoice cleared.');
  });
}

baseUrlInput.value = baseUrl;
serverUrlLabel.textContent = baseUrl;
fetchPending();
fetchFinalResults();

if (invoiceInput) {
  invoiceInput.value = JSON.stringify(SAMPLE_INVOICE, null, 2);
}
