(function () {
  const state = {
    messages: [],
    busy: false,
    sources: [],
    evidenceItems: [],
    selectedEvidenceIndex: -1,
    mentionState: { open: false, query: '', items: [], activeIndex: 0, start: 0, end: 0 },
  };

  const messagesEl = document.getElementById('qaMessages');
  const form = document.getElementById('qaForm');
  const input = document.getElementById('qaInput');
  const evidenceEl = document.getElementById('qaEvidence');
  const evidenceCountEl = document.getElementById('qaEvidenceCount');
  const evidenceDetailEl = document.getElementById('qaEvidenceDetail');
  const mentionsEl = document.getElementById('qaMentions');

  if (!messagesEl || !form || !input || !evidenceEl) return;

  function esc(value) {
    return String(value || '').replace(/[&<>"']/g, (char) => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;',
    }[char]));
  }

  function formatMessageContent(text, role) {
    const escaped = esc(text || '');
    if (role !== 'assistant') return escaped.replace(/\n/g, '<br>');
    return escaped
      .replace(/\*\*([\s\S]+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\[(\d+)\]/g, '<button type="button" class="qa-citation" data-citation-index="$1">[$1]</button>')
      .replace(/\n/g, '<br>');
  }

  function renderMessages() {
    if (!state.messages.length) {
      messagesEl.innerHTML = '<div class="qa-evidence-empty" style="padding:24px 0">Ask the knowledge graph, e.g. “What test types are there?” or “Seat heating related cases”.</div>';
      return;
    }
    messagesEl.innerHTML = state.messages.map((message) => {
      const isUser = message.role === 'user';
      const avatar = isUser ? 'You' : 'AI';
      const meta = message.meta ? `<div class="qa-meta">${esc(message.meta)}</div>` : '';
      return `<div class="qa-message ${isUser ? 'user' : 'assistant'}"><div class="qa-avatar">${avatar}</div><div class="qa-bubble">${formatMessageContent(message.content, message.role)}${meta}</div></div>`;
    }).join('');
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function normalizeSources(payload) {
    const pools = [payload && payload.excel ? payload.excel : [], payload && payload.pdf ? payload.pdf : []];
    const seen = new Set();
    const out = [];
    pools.flat().forEach((item) => {
      if (!item) return;
      const key = item.source_id || item.id || item.name;
      if (!key || seen.has(key)) return;
      seen.add(key);
      out.push({
        id: item.source_id || item.id || item.name,
        name: item.name || item.file_name || item.source_id || 'Untitled file',
        kind: item.kind || 'source',
        domain: item.domain || '',
        version: item.version || 0,
        triple_count: item.triple_count || item.triples || 0,
        case_count: item.case_count || 0,
      });
    });
    return out;
  }

  function sourceLabel(source) {
    const bits = [];
    if (source.version) bits.push(`v${source.version}`);
    if (source.case_count) bits.push(`${source.case_count} cases`);
    if (source.triple_count) bits.push(`${source.triple_count} relations`);
    return bits.join(' · ');
  }

  function buildEvidenceItems(data) {
    const items = [];
    (data.cases || []).forEach((item) => {
      items.push({
        kind: 'Test Case',
        title: item.case_name || 'Untitled',
        meta: [item.case_type || item.test_type || 'Uncategorized', item.source || ''].filter(Boolean).join(' · '),
        summary: [
          item.case_id ? `ID: ${item.case_id}` : '',
          item.score ? `Similarity: ${Number(item.score).toFixed(3)}` : '',
        ].filter(Boolean).join(' | '),
        details: [
          { label: 'Source', value: item.source || 'Unknown' },
          { label: 'Type', value: item.case_type || item.test_type || 'Uncategorized' },
          { label: 'ID', value: item.case_id || item.case_number || 'Not provided' },
          { label: 'Preconditions', value: Array.isArray(item.preconditions) ? item.preconditions.join('; ') : (item.preconditions || 'Not provided') },
          { label: 'Actions', value: Array.isArray(item.actions) ? item.actions.join('; ') : (item.actions || 'Not provided') },
          { label: 'Expected Behavior', value: Array.isArray(item.expected_behaviors) ? item.expected_behaviors.join('; ') : (item.expected_behaviors || 'Not provided') },
        ],
        copyText: [item.case_name, item.case_type || item.test_type, item.source].filter(Boolean).join(' | '),
        raw: item,
      });
    });
    (data.triples || []).forEach((item) => {
      const kind = item.source === 'PDF_KG' || item.doc_name ? 'PDF Spec Triple' : 'Test Case Triple';
      items.push({
        kind,
        title: [item.head, item.relation, item.tail].filter(Boolean).join(' — '),
        meta: item.doc_name || item.source || 'Knowledge Graph',
        summary: item.score ? `Score: ${Number(item.score).toFixed(2)}` : '',
        details: [
          { label: 'Head', value: item.head || 'Not provided' },
          { label: 'Relation', value: item.relation || 'Not provided' },
          { label: 'Tail', value: item.tail || 'Not provided' },
          { label: 'Source', value: item.doc_name || item.source || 'Knowledge Graph' },
        ],
        copyText: [item.head, item.relation, item.tail, item.doc_name || item.source].filter(Boolean).join(' | '),
        raw: item,
      });
    });
    (data.pdf || []).forEach((item) => {
      items.push({
        kind: 'PDF Spec',
        title: [item.head, item.relation, item.tail].filter(Boolean).join(' — '),
        meta: item.doc_name || 'PDF Spec',
        summary: item.score ? `Score: ${Number(item.score).toFixed(2)}` : '',
        details: [
          { label: 'Document', value: item.doc_name || 'Not provided' },
          { label: 'Source snippet', value: (item.sources || []).join('; ') || 'Not provided' },
          { label: 'Triple', value: [item.head, item.relation, item.tail].filter(Boolean).join(' — ') },
        ],
        copyText: [item.head, item.relation, item.tail, item.doc_name].filter(Boolean).join(' | '),
        raw: item,
      });
    });
    return items;
  }

  function renderEvidenceDetail(item, index) {
    if (!item) {
      evidenceDetailEl.hidden = true;
      evidenceDetailEl.innerHTML = '';
      return;
    }
    evidenceDetailEl.hidden = false;
    evidenceDetailEl.innerHTML = [
      '<div class="qa-evidence-detail-head">',
      `<div class="qa-evidence-detail-title"><strong>${esc(item.kind || 'Evidence')} #${index + 1}</strong><small>${esc(item.meta || '')}</small></div>`,
      `<button type="button" class="qa-evidence-copy" data-copy-evidence="${index}">Copy</button>`,
      '</div>',
      '<div class="qa-evidence-detail-body">',
      `<strong>${esc(item.title || '')}</strong>`,
      item.summary ? `<div><span class="label">Summary</span><div>${esc(item.summary)}</div></div>` : '',
      item.details.map((field) => `<div><span class="label">${esc(field.label)}</span><div>${esc(field.value)}</div></div>`).join(''),
      '</div>',
    ].join('');
  }

  function selectEvidence(index, options) {
    const item = state.evidenceItems[index];
    if (!item) return;
    state.selectedEvidenceIndex = index;
    evidenceEl.querySelectorAll('[data-evidence-index]').forEach((node) => {
      node.classList.toggle('is-active', Number(node.dataset.evidenceIndex) === index);
    });
    renderEvidenceDetail(item, index);
    if (!options || !options.silent) {
      const node = evidenceEl.querySelector(`[data-evidence-index="${index}"]`);
      if (node && typeof node.scrollIntoView === 'function') node.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }

  function currentMentionRange(value, cursor) {
    const before = value.slice(0, cursor);
    const match = before.match(/(^|\s)@([^\s@]*)$/);
    if (!match) return null;
    const start = cursor - match[2].length - 1;
    return { start, end: cursor, query: match[2] || '' };
  }

  function openMentionPanel(range) {
    const query = (range && range.query ? range.query : '').toLowerCase();
    const items = state.sources.filter((source) => (
      !query
      || String(source.name || '').toLowerCase().includes(query)
      || String(source.kind || '').toLowerCase().includes(query)
      || String(source.domain || '').toLowerCase().includes(query)
    )).slice(0, 12);
    state.mentionState = { open: true, query, items, activeIndex: 0, start: range.start, end: range.end };
    if (!items.length) {
      mentionsEl.innerHTML = '<div class="qa-mention-empty">No matching PDF / Excel files</div>';
    } else {
      mentionsEl.innerHTML = items.map((source, index) => (
        `<button type="button" class="qa-mention-item${index === 0 ? ' is-active' : ''}" data-mention-index="${index}"><span class="qa-mention-main"><strong>${esc(source.name)}</strong><small>${esc(source.domain || sourceLabel(source) || 'Data source')}</small></span><span class="qa-mention-kind">${esc(String(source.kind || '').toUpperCase())}</span></button>`
      )).join('');
    }
    mentionsEl.hidden = false;
  }

  function closeMentionPanel() {
    state.mentionState = { open: false, query: '', items: [], activeIndex: 0, start: 0, end: 0 };
    mentionsEl.hidden = true;
    mentionsEl.innerHTML = '';
  }

  function updateMentionHighlight() {
    mentionsEl.querySelectorAll('.qa-mention-item').forEach((item, index) => {
      item.classList.toggle('is-active', index === state.mentionState.activeIndex);
    });
  }

  function insertMention(source) {
    const token = `@${source.name} `;
    const before = input.value.slice(0, state.mentionState.start);
    const after = input.value.slice(state.mentionState.end);
    input.value = before + token + after;
    const pos = before.length + token.length;
    input.focus();
    input.setSelectionRange(pos, pos);
    closeMentionPanel();
  }

  function refreshMentions() {
    const range = currentMentionRange(input.value, input.selectionStart || 0);
    if (!range) {
      closeMentionPanel();
      return;
    }
    openMentionPanel(range);
  }

  function renderEvidence(data) {
    state.evidenceItems = buildEvidenceItems(data || {});
    state.selectedEvidenceIndex = -1;
    const items = state.evidenceItems.map((item, index) => (
      `<button type="button" class="qa-evidence-item" data-evidence-index="${index}"><div class="qa-evidence-tag">${esc(item.kind || 'Evidence')} #${index + 1}</div><strong>${esc(item.title || '')}</strong>${item.meta ? `<small>${esc(item.meta)}</small>` : ''}${item.summary ? `<small>${esc(item.summary)}</small>` : ''}</button>`
    ));
    evidenceCountEl.textContent = String(items.length);
    evidenceEl.innerHTML = items.length ? `<div class="qa-evidence-list">${items.join('')}</div>` : '<div class="qa-evidence-empty">No evidence found</div>';
    renderEvidenceDetail(null);
  }

  async function loadSources() {
    try {
      const payload = await fetch('/api/kg/sources', { credentials: 'same-origin' }).then((response) => response.json());
      if (payload && payload.success && payload.data) state.sources = normalizeSources(payload.data);
    } catch (error) {
      state.sources = [];
    }
  }

  async function ask(question) {
    if (!question || state.busy) return;
    state.busy = true;
    state.messages.push({ role: 'user', content: question });
    state.messages.push({ role: 'assistant', content: 'Thinking...', meta: 'loading' });
    renderMessages();
    input.value = '';
    closeMentionPanel();
    try {
      const kgSelect = document.getElementById('kgSelect');
      const payload = await fetch('/api/qa/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          kg_id: kgSelect ? kgSelect.value : undefined,
          messages: state.messages.filter((message) => message.meta !== 'loading'),
        }),
      }).then((response) => response.json());
      if (!payload.success) throw new Error(payload.error || 'Q&A failed');
      state.messages.pop();
      const metaParts = [];
      if (payload.data.generation_degraded) {
        metaParts.push(payload.data.generation_error_kind === 'quota' ? 'Model quota is zero or account status is abnormal; degraded' : 'Model generation degraded');
      }
      if (payload.data.elapsed_time) metaParts.push(`${Number(payload.data.elapsed_time).toFixed(2)}s`);
      state.messages.push({
        role: 'assistant',
        content: payload.data.answer || 'No answer returned.',
        meta: metaParts.join(' · '),
      });
      renderMessages();
      renderEvidence(payload.data.evidence || {});
      if (window.lucide) window.lucide.createIcons();
    } catch (error) {
      state.messages.pop();
      state.messages.push({ role: 'assistant', content: error.message || 'Q&A failed. Please try again later.' });
      renderMessages();
    } finally {
      state.busy = false;
    }
  }

  form.addEventListener('submit', (event) => {
    event.preventDefault();
    ask(input.value.trim());
  });

  document.querySelectorAll('[data-prompt]').forEach((button) => {
    button.addEventListener('click', () => ask(button.dataset.prompt || ''));
  });

  messagesEl.addEventListener('click', (event) => {
    const citation = event.target.closest('[data-citation-index]');
    if (!citation) return;
    const index = Number(citation.dataset.citationIndex) - 1;
    if (index >= 0) selectEvidence(index);
  });

  mentionsEl.addEventListener('click', (event) => {
    const button = event.target.closest('[data-mention-index]');
    if (!button) return;
    const source = state.mentionState.items[Number(button.dataset.mentionIndex)];
    if (source) insertMention(source);
  });

  evidenceEl.addEventListener('click', (event) => {
    const item = event.target.closest('[data-evidence-index]');
    if (!item) return;
    selectEvidence(Number(item.dataset.evidenceIndex));
  });

  evidenceDetailEl.addEventListener('click', (event) => {
    const copyBtn = event.target.closest('[data-copy-evidence]');
    if (!copyBtn) return;
    const item = state.evidenceItems[Number(copyBtn.dataset.copyEvidence)];
    if (!item) return;
    const text = item.copyText || item.title || '';
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(() => {
        copyBtn.textContent = 'Copied';
        window.setTimeout(() => { copyBtn.textContent = 'Copy'; }, 1000);
      });
    }
  });

  input.addEventListener('input', refreshMentions);
  input.addEventListener('click', refreshMentions);
  input.addEventListener('keydown', (event) => {
    if (state.mentionState.open && state.mentionState.items.length) {
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault();
        const delta = event.key === 'ArrowDown' ? 1 : -1;
        state.mentionState.activeIndex = (state.mentionState.activeIndex + delta + state.mentionState.items.length) % state.mentionState.items.length;
        updateMentionHighlight();
        return;
      }
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        const source = state.mentionState.items[state.mentionState.activeIndex];
        if (source) insertMention(source);
        return;
      }
      if (event.key === 'Escape') {
        closeMentionPanel();
        return;
      }
    }
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      ask(input.value.trim());
    }
  });

  loadSources();
  renderMessages();
  if (window.lucide) window.lucide.createIcons();
})();
