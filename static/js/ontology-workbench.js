(function () {
  'use strict';
  const $ = function (id) { return document.getElementById(id); };
  const app = window.workbench;
  const esc = function (value) { return String(value == null ? '' : value).replace(/[&<>"']/g, function (char) { return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]; }); };
  const clone = function (value) { return JSON.parse(JSON.stringify(value)); };
  const state = { sources: [], build: null, buildStep: 'intro', buildPicked: '', buildPickerQuery: '', refineStep: 'intro', refinePicked: '', refinePickerQuery: '', source: '', kind: '', tab: 'sources', sourcesWork: 'build', ontologyListOpen: false, ontologyListTab: 'sources', skillsCreate: false, skillsListOpen: false, skillsListTab: 'library', skillItems: [], pendingSkills: [], trashedSkills: [], excel: new Map(), row: 0, graph: null, graphEdges: [], highlighted: new Set(), pdf: null, pdfPreviewTriples: null, pdfEvaluation: null, pdfDirty: false, pdfCasePreviewToken: 0, messages: [], chatBusy: false, routeToken: 0, skillsLoaded: false, ready: false, sessionId: '', sessions: [] };
  const SESSION_STORE_KEY = 'kg-ontology-sessions-v1';
  const SESSION_LIMIT = 30;
  const statuses = { ready: 'Parsed', parsed: 'Parsed', completed: 'Completed', imported: 'In Graph', published: 'In Graph', waiting_dependency: 'Waiting for parse service', processing: 'Processing', pending: 'Pending', pending_review: 'Pending Review', reviewed: 'Reviewed', skipped: 'Skipped', failed: 'Failed', enabled: 'Enabled', disabled: 'Disabled', uploaded: 'Uploaded' };
  function icon(name) { return '<i data-lucide="' + name + '"></i>'; }
  function formatDate(value) {
    if (!value) return '-';
    const timestamp = Date.parse(value);
    if (!Number.isFinite(timestamp)) return String(value);
    return new Date(timestamp).toLocaleString('en-US', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false });
  }
  function formatSessionTime(value) {
    const timestamp = Date.parse(value);
    if (!Number.isFinite(timestamp)) return '';
    const date = new Date(timestamp);
    const now = new Date();
    const sameDay = date.toDateString() === now.toDateString();
    if (sameDay) return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
    return date.toLocaleString('en-US', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false });
  }
  function readStoredSessions() {
    try {
      const raw = window.localStorage.getItem(SESSION_STORE_KEY);
      const list = raw ? JSON.parse(raw) : [];
      return Array.isArray(list) ? list : [];
    } catch (error) {
      return [];
    }
  }
  function writeStoredSessions(list) {
    try {
      window.localStorage.setItem(SESSION_STORE_KEY, JSON.stringify(list.slice(0, SESSION_LIMIT)));
    } catch (error) { /* ignore quota */ }
  }
  function newSessionId() {
    return 's-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 8);
  }
  function importModeLabel(value) {
    return value === 'replace' ? 'Replace this source' : 'Supplement data';
  }
  function sessionProgressLabel(item) {
    if (!item) return 'Select file';
    if (item.mode === 'refine') {
      if (item.refineStep === 'work') return 'Refining';
      if (item.refineStep === 'pick') return 'Select Data Source';
      return 'Not started';
    }
    if (item.buildStep === 'upload') return 'Upload & parse';
    if (item.buildStep === 'review') return 'Confirm submit';
    if (item.buildStep === 'done') return 'Pending Review';
    if (item.buildStep === 'params') return 'Configure parameters';
    if (item.buildStep === 'pick') return 'Select Data Source';
    return 'Select file';
  }
  function currentSessionTitle() {
    const mode = state.sourcesWork === 'refine' ? 'refine' : 'build';
    if (mode === 'refine') {
      const picked = state.refinePicked || state.source;
      const source = picked && state.sources.find(function (item) { return sourceId(item) === picked; });
      const name = source ? (source.name || source.file_name || picked) : '';
      return name || 'Source Refine';
    }
    const domain = ($('kgIncrDomain') && $('kgIncrDomain').value || '').trim();
    const file = selectedBuildFile();
    const fileName = (state.build && (state.build.file_name || state.build.name)) || (file && file.name) || '';
    if (domain) return domain;
    if (fileName) return fileName;
    if (state.buildPicked) {
      const source = state.sources.find(function (item) { return sourceId(item) === state.buildPicked; });
      if (source) return source.name || source.file_name || state.buildPicked;
    }
    return 'No file selected';
  }
  function currentSessionFileName() {
    if (state.sourcesWork === 'refine') {
      const picked = state.refinePicked || state.source;
      const source = picked && state.sources.find(function (item) { return sourceId(item) === picked; });
      return source ? (source.name || source.file_name || picked) : '';
    }
    const file = selectedBuildFile();
    if (file && file.name) return file.name;
    if (state.build && (state.build.file_name || state.build.name)) return state.build.file_name || state.build.name;
    if (state.buildPicked) {
      const source = state.sources.find(function (item) { return sourceId(item) === state.buildPicked; });
      if (source) return source.name || source.file_name || state.buildPicked;
    }
    return '';
  }
  function snapshotCurrentSession() {
    const mode = state.sourcesWork === 'refine' ? 'refine' : 'build';
    const domain = ($('kgIncrDomain') && $('kgIncrDomain').value || '').trim();
    const importMode = ($('kgImportMode') && $('kgImportMode').value) || 'supplement';
    return {
      id: state.sessionId || newSessionId(),
      title: currentSessionTitle(),
      mode: mode,
      buildStep: state.buildStep || 'intro',
      refineStep: state.refineStep || 'intro',
      domain: domain,
      importMode: importMode,
      fileName: currentSessionFileName(),
      sourceId: state.source || state.refinePicked || state.buildPicked || '',
      doneText: ($('kgBuildDoneText') && $('kgBuildDoneText').textContent) || '',
      updatedAt: new Date().toISOString()
    };
  }
  function isBlankOntologySession(item) {
    if (!item) return true;
    if ((item.domain || '').trim()) return false;
    if ((item.fileName || '').trim()) return false;
    if ((item.sourceId || '').trim()) return false;
    if (item.mode === 'refine') {
      if (item.refineStep && item.refineStep !== 'intro') return false;
      return true;
    }
    if (item.buildStep && item.buildStep !== 'intro' && item.buildStep !== 'pick') return false;
    return true;
  }
  function syncSessionNewEnabled() {
    const btn = $('kgSessionNew');
    if (!btn) return;
    const blank = isBlankOntologySession(snapshotCurrentSession());
    btn.disabled = blank;
    btn.setAttribute('aria-disabled', blank ? 'true' : 'false');
    btn.title = blank ? 'Finish the current session before adding a new one' : 'New conversation';
  }
  function persistCurrentSession() {
    if (!state.sessionId) state.sessionId = newSessionId();
    const snap = snapshotCurrentSession();
    state.sessionId = snap.id;
    const byId = new Map();
    (readStoredSessions() || []).concat(state.sessions || []).forEach(function (item) {
      if (item && item.id && item.id !== snap.id) byId.set(item.id, item);
    });
    state.sessions = [snap].concat(Array.from(byId.values())).slice(0, SESSION_LIMIT);
    writeStoredSessions(state.sessions);
    renderSessionList();
  }
  function deleteOntologySession(id) {
    if (!id) return;
    const list = (state.sessions.length ? state.sessions : readStoredSessions()).filter(function (item) { return item && item.id !== id; });
    state.sessions = list;
    writeStoredSessions(list);
    if (state.sessionId === id) {
      state.sessionId = '';
      startNewOntologySession(true);
      return;
    }
    renderSessionList();
  }
  function renderSessionList() {
    const host = $('kgSessionList');
    const count = $('kgSessionCount');
    if (!host) return;
    const list = state.sessions.length ? state.sessions : readStoredSessions();
    state.sessions = list;
    if (count) count.textContent = String(list.length);
    if (!list.length) {
      host.innerHTML = '<div class="rail-history-empty">No conversation history</div>';
      syncSessionNewEnabled();
      app.icons();
      return;
    }
    host.innerHTML = list.map(function (item) {
      const active = item.id === state.sessionId ? ' is-active' : '';
      const domain = (item.domain || '').trim() || (item.mode === 'refine' ? 'Source Refine' : 'Business Domain not set');
      const fileName = (item.fileName || '').trim() || (item.mode === 'refine' ? 'No Data Source selected' : 'No file selected');
      const updateLabel = item.mode === 'refine' ? 'Refine' : importModeLabel(item.importMode);
      const progress = sessionProgressLabel(item);
      const detail = [updateLabel, fileName, progress].join(' · ');
      const tip = [domain, updateLabel, fileName, progress].join(' · ');
      return '<button type="button" class="rail-history-item' + active + '" data-session-id="' + esc(item.id) + '" title="' + esc(tip) + '">'
        + '<span class="rail-history-main">' + icon('file-text') + '<span><strong>' + esc(domain) + '</strong><small>' + esc(detail) + '</small></span></span>'
        + '<span class="rail-history-tools">'
        + '<span class="rail-history-delete" data-session-delete="' + esc(item.id) + '" title="Delete" aria-label="Delete" role="button" tabindex="0">' + icon('trash-2') + '</span>'
        + '</span></button>';
    }).join('');
    host.querySelectorAll('[data-session-id]').forEach(function (button) {
      button.addEventListener('click', function () {
        restoreOntologySession(button.getAttribute('data-session-id'));
      });
    });
    host.querySelectorAll('[data-session-delete]').forEach(function (btn) {
      const remove = function (event) {
        event.preventDefault();
        event.stopPropagation();
        deleteOntologySession(btn.getAttribute('data-session-delete'));
      };
      btn.addEventListener('click', remove);
      btn.addEventListener('keydown', function (event) {
        if (event.key === 'Enter' || event.key === ' ') remove(event);
      });
    });
    syncSessionNewEnabled();
    app.icons();
  }
  function resetOntologyConversationUi() {
    state.build = null;
    state.buildStep = 'intro';
    state.buildPicked = '';
    state.buildPickerQuery = '';
    state.refineStep = 'intro';
    state.refinePicked = '';
    state.refinePickerQuery = '';
    state.source = '';
    state.kind = '';
    state.row = 0;
    state.pdf = null;
    state.pdfDirty = false;
    const fileInput = $('kgFileInput');
    if (fileInput) fileInput.value = '';
    const refineInput = $('kgRefineFileInput');
    if (refineInput) refineInput.value = '';
    if ($('kgIncrDomain')) $('kgIncrDomain').value = '';
    if ($('kgImportMode')) $('kgImportMode').value = 'supplement';
    if ($('kgBuildParamsAck')) $('kgBuildParamsAck').hidden = true;
    if ($('kgBuildDoneText')) $('kgBuildDoneText').textContent = '';
    if ($('kgResults')) $('kgResults').hidden = true;
    if ($('kgPreviewPane')) { $('kgPreviewPane').innerHTML = ''; $('kgPreviewPane').hidden = true; }
    if ($('kgMeta')) $('kgMeta').textContent = '';
    if ($('kgStatus')) { $('kgStatus').textContent = ''; $('kgStatus').hidden = true; }
    if ($('kgBuildParamsStatus')) { $('kgBuildParamsStatus').textContent = ''; $('kgBuildParamsStatus').hidden = true; }
    if ($('kgExcelPanel')) $('kgExcelPanel').hidden = true;
    if ($('kgPdfPanel')) $('kgPdfPanel').hidden = true;
    if ($('kgRefineWorkBubble')) $('kgRefineWorkBubble').hidden = true;
    if ($('kgRefinePickerBubble')) $('kgRefinePickerBubble').hidden = true;
    if ($('kgBuildPickerBubble')) $('kgBuildPickerBubble').hidden = true;
    const refineSection = $('kgRefineSection');
    if (refineSection) refineSection.setAttribute('data-refine-step', 'intro');
    setBuildStep('intro');
    syncParamsConfirmEnabled();
    syncBuildAttachStrip();
    syncRefineAttachStrip();
    syncRefineGuide();
  }
  function startNewOntologySession(force) {
    // Untouched draft: do not stack another blank session.
    if (!force && state.sessionId && isBlankOntologySession(snapshotCurrentSession())) {
      syncSessionNewEnabled();
      return;
    }
    // Persist current form onto the active session before clearing the UI.
    if (state.sessionId) persistCurrentSession();
    const previous = (state.sessions.length ? state.sessions.slice() : readStoredSessions()).filter(function (item) {
      return item && item.id;
    });

    resetOntologyConversationUi();
    state.sessionId = newSessionId();
    state.sourcesWork = 'build';

    const panel = $('kgSubviewSources');
    if (panel) {
      panel.classList.add('is-build-mode');
      panel.classList.remove('is-refine-mode');
    }
    const workTabs = $('ontologyRailSubnav');
    if (workTabs) workTabs.hidden = false;
    setOntologyTitleMode(false);
    ['build', 'refine'].forEach(function (name) {
      const el = $(name === 'build' ? 'kgTabBuild' : 'kgTabRefine');
      if (!el) return;
      const active = name === 'build';
      el.classList.toggle('is-selected', active);
      el.classList.toggle('is-active', active);
      el.setAttribute('aria-pressed', String(active));
      el.tabIndex = active ? 0 : -1;
    });
    setBuildStep('intro');
    syncOntologyListToggle();

    const snap = snapshotCurrentSession();
    const byId = new Map();
    previous.forEach(function (item) {
      if (item.id !== snap.id) byId.set(item.id, item);
    });
    state.sessions = [snap].concat(Array.from(byId.values())).slice(0, SESSION_LIMIT);
    writeStoredSessions(state.sessions);
    renderSessionList();

    if (app.setView) app.setView('ontology', false);
    syncOntologyTopbarCopy();
    syncBuildGuide();
    syncParamsConfirmEnabled();
    syncSessionNewEnabled();
    const stream = $('kgBuildSection') && $('kgBuildSection').querySelector('.ontology-message-stream');
    if (stream) {
      window.requestAnimationFrame(function () { stream.scrollTop = 0; });
    }
    app.icons();
  }
  async function restoreOntologySession(id) {
    const list = readStoredSessions();
    const item = list.find(function (entry) { return entry && entry.id === id; });
    if (!item) return;
    state.sessionId = item.id;
    state.sessions = list;
    resetOntologyConversationUi();
    state.sessionId = item.id;
    if (item.domain && $('kgIncrDomain')) $('kgIncrDomain').value = item.domain;
    if (item.importMode && $('kgImportMode')) $('kgImportMode').value = item.importMode;
    if (item.mode === 'refine') {
      state.refinePicked = item.sourceId || '';
      if ($('kgRefineSource')) $('kgRefineSource').value = item.sourceId || '';
      setSourcesWorkMode('refine', false);
      if (item.sourceId && state.sources.some(function (source) { return sourceId(source) === item.sourceId; })) {
        await openSource(item.sourceId);
      } else {
        state.refineStep = item.refineStep === 'work' ? 'pick' : (item.refineStep || 'intro');
        if (state.refineStep === 'pick') showRefineSourcePicker();
        else syncRefineGuide();
      }
    } else {
      setSourcesWorkMode('build', false);
      state.buildPicked = item.sourceId || '';
      if (item.fileName) {
        state.build = {
          file_name: item.fileName,
          domain: item.domain || '',
          mode: item.importMode || 'supplement',
          pending_review: item.buildStep === 'done'
        };
      }
      if (item.buildStep === 'done' && item.doneText && $('kgBuildDoneText')) {
        $('kgBuildDoneText').textContent = item.doneText;
      }
      const step = item.buildStep || 'intro';
      if (step === 'upload' || step === 'review' || step === 'done') {
        const ack = $('kgBuildParamsAckText');
        if (ack && item.domain) {
          const modeLabel = item.importMode === 'replace' ? 'Replace this source' : 'Supplement data';
          ack.textContent = 'Confirmed: Business Domain “' + item.domain + '” · ' + modeLabel;
        }
        setBuildStep(step === 'review' && !state.build ? 'upload' : step);
      } else if (step === 'params') {
        setBuildStep('params');
      } else if (step === 'pick') {
        showBuildSourcePicker();
      } else {
        setBuildStep('intro');
      }
    }
    persistCurrentSession();
    if (app.setView) app.setView('ontology', false);
    syncOntologyTopbarCopy();
    syncSessionNewEnabled();
  }
  function status(id, text, kind) {
    const el = $(id);
    if (!el) return;
    el.textContent = text || '';
    el.hidden = !text;
    el.dataset.state = kind || 'ok';
  }
  function dataOf(payload) { return payload.data || payload; }
  async function get(url) { return dataOf(await app.api(url)); }
  async function post(url, body) { return dataOf(await app.api(url, body instanceof FormData ? { method: 'POST', body: body } : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })); }
  async function busy(id, statusId, fn) {
    const button = $(id);
    if (!button || button.disabled) return;
    const operation = (button._busyOperation || 0) + 1;
    button._busyOperation = operation;
    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
    try {
      return await fn();
    } catch (error) {
      if (button._busyOperation === operation) status(statusId, (error && error.message) || 'Operation failed', 'error');
    } finally {
      if (button._busyOperation === operation) {
        button.disabled = false;
        button.removeAttribute('aria-busy');
      }
    }
  }
  function cancelBusy(id, disabled) {
    const button = $(id); if (!button) return;
    button._busyOperation = (button._busyOperation || 0) + 1;
    button.removeAttribute('aria-busy');
    button.disabled = disabled === true;
  }
  function sourceId(source) { return source.source_id || source.id || source.name; }
  function currentExcel() { return state.excel.get(state.source); }
  function currentCase() { const doc = currentExcel(); return doc && doc.cases[state.row]; }
  function normalizeTriple(value) {
    if (Array.isArray(value)) return { head: value[0] || '', relation: value[1] || '', tail: value[2] || '', keep: true };
    return Object.assign({}, value, { head: value.head || value.subject || '', relation: value.relation || value.predicate || '', tail: value.tail || value.object || '', keep: value.keep !== false });
  }
  function tripleKey(value) { const t = normalizeTriple(value); return JSON.stringify([t.head, t.relation, t.tail]); }
  function tripleText(value) { if (!value) return ''; const t = normalizeTriple(value); return [t.head, t.relation, t.tail].join(' / '); }
  function hasUnsaved() { return state.pdfDirty || Array.from(state.excel.values()).some(function (doc) { return doc.cases.some(function (row) { return row._dirty; }); }); }
  app.hasUnsaved = hasUnsaved;
  function updateDirty() { $('kgRefineDirty').hidden = !hasUnsaved(); }
  window.addEventListener('beforeunload', function (event) { if (hasUnsaved()) { event.preventDefault(); event.returnValue = ''; } });
  function setHash(fields) {
    const params = new URLSearchParams(window.location.hash.split('?')[1] || '');
    Object.keys(fields).forEach(function (key) { if (fields[key] === '' || fields[key] == null) params.delete(key); else params.set(key, fields[key]); });
    const suffix = params.toString();
    const value = '#ontology' + (suffix ? '?' + suffix : '');
    if (window.location.hash !== value) window.history.replaceState(null, '', value);
  }
  function normalizeTab(tab) {
    if (tab === 'refine' || tab === 'builder' || tab === 'sources' || tab === 'skills') return 'sources';
    return 'sources';
  }
  function bindTablistKeys(root, getNext) {
    if (!root) return;
    root.addEventListener('keydown', function (event) {
      if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return;
      event.preventDefault();
      const next = getNext(event.key === 'ArrowRight');
      if (!next) return;
      next.click();
      next.focus();
    });
  }
  bindTablistKeys($('ontologyRailSubnav'), function () {
    return $(state.sourcesWork === 'build' ? 'kgTabRefine' : 'kgTabBuild');
  });
  function isPendingReviewSource(source) {
    return String((source && source.status) || '') === 'pending_review';
  }
  function updatePendingBadge(count) {
    const badge = $('kgPendingBadge');
    if (!badge) return;
    const n = Number(count) || 0;
    badge.textContent = String(n);
    badge.hidden = n <= 0;
  }
  function sourceTable(sources, actions, emptyText) {
    if (!sources.length) return '<p class="empty-state">' + esc(emptyText || 'No Data Sources') + '</p>';
    return '<table class="source-table"><thead><tr><th>File name</th><th>Status</th><th>Results</th><th>Updated</th><th>Version</th>' + (actions ? '<th></th>' : '') + '</tr></thead><tbody>' + sources.map(function (source) {
      const kind = source.kind || source.file_type || (/\.pdf$/i.test(source.name) ? 'pdf' : 'excel');
      const name = source.name || source.file_name || sourceId(source);
      const id = sourceId(source);
      const statusName = source.status || 'ready';
      const time = formatDate(source.updated_at);
      const badgeClass = statusName === 'failed' ? 'error' : (['processing', 'pending', 'pending_review', 'uploaded', 'waiting_dependency'].includes(statusName) ? 'warning' : '');
      return '<tr data-source-id="' + esc(id) + '"><td><span class="source-name">' + icon(kind === 'pdf' ? 'file-text' : 'file-spreadsheet') + '<span class="source-name-text"><span class="source-name-title">' + esc(name) + '</span><span class="source-kind">' + esc(kind.toUpperCase()) + '</span></span></span></td><td><span class="status-badge ' + badgeClass + '">' + esc(statuses[statusName] || statusName) + '</span></td><td>' + esc(source.triple_count == null ? source.triples || 0 : source.triple_count) + ' relations' + (source.case_count ? '<br><span class="muted">' + source.case_count + ' cases</span>' : '') + '</td><td>' + esc(time) + '</td><td>' + (source.version == null ? '-' : 'v' + esc(source.version)) + '</td>' + (actions ? '<td><div class="inline-actions"><button class="icon-button" data-delete-source="' + esc(id) + '" title="Delete Data Source" aria-label="Delete ' + esc(name) + '">' + icon('trash-2') + '</button></div></td>' : '') + '</tr>';
    }).join('') + '</tbody></table>';
  }
  function flashPendingSourceRow(id) {
    if (!id) return;
    const pendingList = $('kgSourcesPendingList');
    if (!pendingList) return;
    const rows = pendingList.querySelectorAll('tr[data-source-id]');
    let row = null;
    for (let i = 0; i < rows.length; i += 1) {
      if (rows[i].getAttribute('data-source-id') === String(id)) {
        row = rows[i];
        break;
      }
    }
    if (!row) {
      const build = state.build;
      const fileName = build && (build.file_name || build.name);
      if (fileName) {
        for (let j = 0; j < rows.length; j += 1) {
          const title = rows[j].querySelector('.source-name-title');
          if (title && title.textContent === fileName) {
            row = rows[j];
            break;
          }
        }
      }
    }
    if (row) highlightPendingRow(row);
  }
  function highlightPendingRow(row) {
    if (!row) return;
    row.classList.remove('is-just-submitted');
    // Force reflow so animation can replay
    void row.offsetWidth;
    row.classList.add('is-just-submitted');
    try {
      row.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    } catch (error) {
      row.scrollIntoView(false);
    }
    window.setTimeout(function () {
      row.classList.remove('is-just-submitted');
    }, 1100);
  }
  function bindSourceDeleteActions(list) {
    if (!list) return;
    list.querySelectorAll('[data-delete-source]').forEach(function (button) {
      button.addEventListener('click', function () {
        const id = button.dataset.deleteSource;
        const source = state.sources.find(function (item) { return sourceId(item) === id; });
        const name = (source && (source.name || source.file_name)) || id;
        openSourceDeleteModal(id, name);
      });
    });
  }
  function renderSources() {
    const search = $('kgSourceSearch');
    const query = search ? search.value.trim().toLowerCase() : '';
    const matchesQuery = function (source) { return String(source.name || source.file_name || '').toLowerCase().includes(query); };
    const activeSources = state.sources.filter(function (source) { return !isPendingReviewSource(source); });
    const pendingSources = state.sources.filter(isPendingReviewSource);
    const filteredActive = activeSources.filter(matchesQuery);
    const filteredPending = pendingSources.filter(matchesQuery);
    const list = $('kgSourcesList');
    const pendingList = $('kgSourcesPendingList');
    if (list) {
      list.innerHTML = sourceTable(filteredActive, true, activeSources.length ? 'No matching Data Sources' : 'No Data Sources');
      bindSourceDeleteActions(list);
    }
    if (pendingList) {
      pendingList.innerHTML = sourceTable(filteredPending, true, pendingSources.length ? 'No matching Pending Review items' : 'No Pending Review Data Sources');
      bindSourceDeleteActions(pendingList);
    }
    updatePendingBadge(pendingSources.length);
    if ($('overviewSources')) $('overviewSources').innerHTML = sourceTable(activeSources.slice(0, 8), false);
    if ($('kgSourcesCount')) $('kgSourcesCount').textContent = activeSources.length;
    if ($('overviewSourceCount')) $('overviewSourceCount').textContent = activeSources.length;
    const previous = ($('kgRefineSource') && $('kgRefineSource').value) || state.refinePicked || state.source;
    if ($('kgRefineSource')) {
      $('kgRefineSource').innerHTML = '<option value="">Select Data Source</option>' + activeSources.map(function (source) { return '<option value="' + esc(sourceId(source)) + '">' + esc((source.kind || source.file_type || 'excel').toUpperCase() + ' · ' + (source.name || sourceId(source))) + '</option>'; }).join('');
      $('kgRefineSource').value = previous;
    }
    if (state.refineStep === 'pick' || ($('kgRefinePickerBubble') && !$('kgRefinePickerBubble').hidden)) renderRefinePickerTable();
    if (state.buildStep === 'pick' || ($('kgBuildPickerBubble') && !$('kgBuildPickerBubble').hidden)) renderBuildPickerTable();
    if (typeof syncRefineGuide === 'function') syncRefineGuide();
    app.icons();
  }
  let pendingDelete = { type: '', id: '', name: '' };
  function setDeleteConfirmLabel(label) {
    const confirmBtn = $('kgSourceDeleteConfirm');
    if (confirmBtn) confirmBtn.textContent = label || 'Move to trash';
  }
  function openSourceDeleteModal(id, name) {
    pendingDelete = { type: 'source', id: id, name: name || id };
    const modal = $('kgSourceDeleteModal');
    const title = $('kgSourceDeleteTitle');
    const message = $('kgSourceDeleteMessage');
    if (title) title.textContent = 'Move to trash';
    if (message) message.textContent = 'Move Data Source “' + pendingDelete.name + '” to trash? You can restore it from trash later.';
    setDeleteConfirmLabel('Move to trash');
    if (modal) modal.hidden = false;
  }
  function openSkillDeleteModal(id, name) {
    pendingDelete = { type: 'skill', id: id, name: name || id };
    const modal = $('kgSourceDeleteModal');
    const title = $('kgSourceDeleteTitle');
    const message = $('kgSourceDeleteMessage');
    if (title) title.textContent = 'Move to trash';
    if (message) message.textContent = 'Move Skill “' + pendingDelete.name + '” to trash? You can restore it from trash later.';
    setDeleteConfirmLabel('Move to trash');
    if (modal) modal.hidden = false;
  }
  function openPurgeModal(kind, id, name) {
    pendingDelete = { type: kind === 'skill' ? 'purge-skill' : 'purge-source', id: id, name: name || id };
    const modal = $('kgSourceDeleteModal');
    const title = $('kgSourceDeleteTitle');
    const message = $('kgSourceDeleteMessage');
    const label = kind === 'skill' ? 'Skill' : 'Data Source';
    if (title) title.textContent = 'Delete permanently';
    if (message) message.textContent = 'Permanently delete ' + label + ' “' + pendingDelete.name + '”? This cannot be undone.';
    setDeleteConfirmLabel('Delete permanently');
    if (modal) modal.hidden = false;
  }
  function closeSourceDeleteModal() {
    pendingDelete = { type: '', id: '', name: '' };
    const modal = $('kgSourceDeleteModal');
    if (modal) modal.hidden = true;
    const confirmBtn = $('kgSourceDeleteConfirm');
    if (confirmBtn) {
      confirmBtn.disabled = false;
      confirmBtn.removeAttribute('aria-busy');
      confirmBtn.textContent = 'Move to trash';
    }
  }
  async function confirmSourceDelete() {
    const type = pendingDelete.type;
    const id = pendingDelete.id;
    if (!type || !id) return;
    const confirmBtn = $('kgSourceDeleteConfirm');
    if (confirmBtn) {
      confirmBtn.disabled = true;
      confirmBtn.setAttribute('aria-busy', 'true');
    }
    try {
      if (type === 'purge-skill') {
        await post('/api/kg/skills/purge', { skill: id });
        closeSourceDeleteModal();
        await loadSkills();
        if (state.skillsListTab === 'trash') setSkillsListTab('trash');
        await loadTrashList();
        await refreshTrashBadge();
      } else if (type === 'purge-source') {
        await post('/api/kg/sources/purge', { source: id });
        closeSourceDeleteModal();
        await loadTrashList();
        await refreshTrashBadge();
      } else if (type === 'skill') {
        await app.api('/api/kg/skills?skill=' + encodeURIComponent(id), { method: 'DELETE' });
        closeSourceDeleteModal();
        await loadSkills();
        if (state.skillsListTab === 'trash') setSkillsListTab('trash');
        await refreshTrashBadge();
      } else {
        await app.api('/api/kg/sources?source=' + encodeURIComponent(id), { method: 'DELETE' });
        if (state.source === id) {
          state.source = '';
          state.excel.delete(id);
          showSourcesLibrary();
          $('kgExcelPanel').hidden = true;
          $('kgPdfPanel').hidden = true;
          $('kgRefineEmpty').hidden = false;
        }
        closeSourceDeleteModal();
        await loadSources();
        await refreshTrashBadge();
      }
    } catch (error) {
      const statusId = (type === 'skill' || type === 'purge-skill') ? 'kgSkillStatus' : 'kgStatus';
      status(statusId, error.message, 'error');
      if (confirmBtn) {
        confirmBtn.disabled = false;
        confirmBtn.removeAttribute('aria-busy');
      }
    }
  }
  const sourceDeleteModal = $('kgSourceDeleteModal');
  if (sourceDeleteModal) {
    $('kgSourceDeleteClose')?.addEventListener('click', closeSourceDeleteModal);
    $('kgSourceDeleteCancel')?.addEventListener('click', closeSourceDeleteModal);
    $('kgSourceDeleteConfirm')?.addEventListener('click', confirmSourceDelete);
    sourceDeleteModal.addEventListener('click', function (event) {
      if (event.target === sourceDeleteModal) closeSourceDeleteModal();
    });
  }
  async function loadSources() {
    try {
      const data = await get('/api/kg/sources');
      state.sources = data.sources || [].concat((data.excel || []).map(function (source) { return Object.assign({ kind: 'excel' }, source); }), (data.pdf || []).map(function (source) { return Object.assign({ kind: 'pdf' }, source); }));
      state.sources.forEach(function (source) { const cached = state.excel.get(sourceId(source)); if (cached && cached.source && cached.source.version !== source.version && !cached.cases.some(function (row) { return row._dirty; })) state.excel.delete(sourceId(source)); });
      renderSources();
      await refreshTrashBadge();
    } catch (error) { $('kgSourcesList').innerHTML = '<p class="notice" data-state="error">' + esc(error.message) + '</p>'; }
  }
  function updateTrashBadge(count) {
    const n = Number(count) || 0;
    ['kgTrashBadge'].forEach(function (id) {
      const badge = $(id);
      if (!badge) return;
      badge.textContent = String(n);
      badge.hidden = n <= 0;
    });
  }
  async function refreshTrashBadge() {
    try {
      const results = await Promise.allSettled([get('/api/kg/sources/trash'), get('/api/kg/skills/trash')]);
      let total = 0;
      results.forEach(function (result) {
        if (result.status !== 'fulfilled') return;
        const data = result.value || {};
        total += Number(data.count != null ? data.count : (data.trash || []).length) || 0;
      });
      updateTrashBadge(total);
    } catch (_error) { /* keep previous badge */ }
  }
  async function loadTrashList() {
    const list = $('kgSourceTrashList');
    if (!list) return;
    list.innerHTML = '<p class="empty-state">Loading…</p>';
    try {
      const results = await Promise.allSettled([get('/api/kg/sources/trash'), get('/api/kg/skills/trash')]);
      const sourceTrash = results[0].status === 'fulfilled' ? (results[0].value.trash || []) : [];
      const skillTrash = results[1].status === 'fulfilled' ? (results[1].value.trash || []) : [];
      updateTrashBadge(sourceTrash.length + skillTrash.length);
      if (!sourceTrash.length && !skillTrash.length) {
        list.innerHTML = '<div class="empty-state empty-state-illustration"><img src="static/img/trash.svg" alt="" width="141" height="136"><p>Trash is empty</p></div>';
        return;
      }
      const sourceRows = sourceTrash.map(function (source) {
        const kind = source.kind || source.file_type || 'excel';
        const name = source.name || source.file_name || sourceId(source);
        const time = formatDate(source.deleted_at || source.updated_at);
        const sid = sourceId(source);
        return '<div class="trash-item"><div class="trash-item-main">' + icon(kind === 'pdf' ? 'file-text' : 'file-spreadsheet') + '<div><strong>' + esc(name) + '</strong><small>Data Source · ' + esc(String(kind).toUpperCase()) + (time && time !== '-' ? ' · Deleted ' + esc(time) : '') + '</small></div></div><div class="trash-item-actions"><button type="button" class="ghost-button" data-restore-source="' + esc(sid) + '">Restore</button><button type="button" class="ghost-button danger-ghost" data-purge-source="' + esc(sid) + '" data-purge-name="' + esc(name) + '">Delete permanently</button></div></div>';
      });
      const skillRows = skillTrash.map(function (skill) {
        const sid = skill.skill_id || skill.id || '';
        const name = skill.name || sid;
        const time = formatDate(skill.deleted_at);
        const typeLabel = [skill.file_type, skill.template_kind].filter(Boolean).join(' · ') || 'skill';
        return '<div class="trash-item"><div class="trash-item-main">' + icon('sparkles') + '<div><strong>' + esc(name) + '</strong><small>Skill · ' + esc(typeLabel) + (time && time !== '-' ? ' · Deleted ' + esc(time) : '') + '</small></div></div><div class="trash-item-actions"><button type="button" class="ghost-button" data-restore-skill="' + esc(sid) + '">Restore</button><button type="button" class="ghost-button danger-ghost" data-purge-skill="' + esc(sid) + '" data-purge-name="' + esc(name) + '">Delete permanently</button></div></div>';
      });
      list.innerHTML = sourceRows.concat(skillRows).join('');
      list.querySelectorAll('[data-restore-source]').forEach(function (button) {
        button.addEventListener('click', async function () {
          button.disabled = true;
          try {
            await post('/api/kg/sources/restore', { source: button.dataset.restoreSource });
            await loadSources();
            await loadTrashList();
          } catch (error) {
            status('kgStatus', error.message, 'error');
            button.disabled = false;
          }
        });
      });
      list.querySelectorAll('[data-restore-skill]').forEach(function (button) {
        button.addEventListener('click', async function () {
          button.disabled = true;
          try {
            await post('/api/kg/skills/restore', { skill: button.dataset.restoreSkill });
            await loadSkills();
            await loadTrashList();
          } catch (error) {
            status('kgSkillStatus', error.message, 'error');
            button.disabled = false;
          }
        });
      });
      list.querySelectorAll('[data-purge-source]').forEach(function (button) {
        button.addEventListener('click', function () {
          openPurgeModal('source', button.dataset.purgeSource, button.dataset.purgeName || button.dataset.purgeSource);
        });
      });
      list.querySelectorAll('[data-purge-skill]').forEach(function (button) {
        button.addEventListener('click', function () {
          openPurgeModal('skill', button.dataset.purgeSkill, button.dataset.purgeName || button.dataset.purgeSkill);
        });
      });
      app.icons();
    } catch (error) {
      list.innerHTML = '<p class="notice" data-state="error">' + esc(error.message) + '</p>';
    }
  }
  function openTrashModal() {
    setOntologyListOpen(true);
    setOntologyListTab('trash');
  }
  function closeTrashModal() {}
  $('kgSourcesRefresh')?.addEventListener('click', function () { busy('kgSourcesRefresh', 'kgStatus', loadSources); });
  $('kgSourceSearch')?.addEventListener('input', renderSources);
  function triplesTable(triples, title) {
    return (title ? '<div class="section-heading"><h3>' + esc(title) + ' <span class="count">' + triples.length + '</span></h3></div>' : '') + '<table class="diff-table ontology-triple-table"><thead><tr><th>Head</th><th>Relation</th><th>Tail</th></tr></thead><tbody>' + triples.map(function (raw) { const t = normalizeTriple(raw); return '<tr><td>' + esc(t.head) + '</td><td>' + esc(t.relation) + '</td><td>' + esc(t.tail) + '</td></tr>'; }).join('') + '</tbody></table>';
  }
  function strictCaseValue(value) {
    if (Array.isArray(value)) return value.length ? value.join('; ') : '—';
    return value == null || value === '' ? '—' : String(value);
  }
  function strictRoleMarkup(item, field, fallback) {
    const values = item[field];
    if (!Array.isArray(values) || !values.length || typeof values[0] !== 'object') return esc(strictCaseValue(fallback));
    return values.map(function (value) {
      const relation = value.relation_id ? '<small class="relation-code">' + esc(value.relation_id) + '</small>' : '';
      return '<span class="scenario-role-value">' + esc(value.text || '') + relation + '</span>';
    }).join('');
  }
  function scenarioScope(item) {
    const labels = [];
    (item.source_scopes || []).forEach(function (scope) {
      const page = scope.page_number == null ? scope.page : scope.page_number;
      const position = page == null || page === '' ? (scope.image_id || '') : 'Page ' + page;
      const unit = scope.rule_unit_id || scope.row_id || scope.clause_id || '';
      const label = [position, unit].filter(Boolean).join(' · ');
      if (label && !labels.includes(label)) labels.push(label);
    });
    return labels.slice(0, 3).join('; ');
  }
  function strictCaseRows(cases, scenarios) {
    return cases.map(function (item) {
      const canonical = item.canonical || {};
      const statusName = item.status === 'ready' ? 'Fields complete' : 'Fields missing';
      const statusClass = item.status === 'ready' ? '' : ' warning';
      const missingRoles = (item.missing_roles || []).join('、');
      const evidence = (item.source_triple_ids || []).length + ' evidence items';
      const scope = scenarios ? scenarioScope(item) : '';
      const score = scenarios && Number.isFinite(Number(item.heuristic_score)) ? 'Rule score ' + Number(item.heuristic_score).toFixed(1) : '';
      const meta = [score, scope, evidence, missingRoles ? 'Missing ' + missingRoles : ''].filter(Boolean).join(' · ');
      return '<tr><td><strong>' + esc(canonical['测试用例'] || item.test_case_name || item.case_name || item.name || '') + '</strong><br><span class="muted">' + esc(meta) + '</span></td><td>' + strictRoleMarkup(item, 'preconditions', canonical['前置条件'] || item.precondition_texts) + '</td><td>' + strictRoleMarkup(item, 'actions', canonical['执行动作'] || item.action_texts) + '</td><td>' + strictRoleMarkup(item, 'expected_behaviors', canonical['预期行为'] || item.expected_behavior_texts) + '</td><td><span class="status-badge' + statusClass + '">' + esc(statusName) + '</span></td></tr>';
    }).join('');
  }
  function strictCaseTable(cases, scenarios) {
    return '<div class="table-scroll"><table class="diff-table scenario-table"><thead><tr><th>Test Case</th><th>Preconditions</th><th>Actions</th><th>Expected Behavior</th><th>Status</th></tr></thead><tbody>' + strictCaseRows(cases, scenarios) + '</tbody></table></div>';
  }
  function renderPdfCasePreview(data) {
    const target = $('kgPdfCasePreview');
    if (!target) return;
    const hasScenarios = Array.isArray(data.selected_scenarios);
    const summary = hasScenarios ? (data.scenario_summary || {}) : (data.summary || {});
    const cases = hasScenarios ? data.selected_scenarios : (data.cases || data.test_cases || []);
    const missing = summary.missing_roles || {};
    const missingText = Object.keys(missing).map(function (key) { return key + ' ' + missing[key]; }).join(' · ');
    const coverage = Number(summary.coverage);
    const businessAtoms = Number(summary.business_atom_count);
    const coverageMeta = Number.isFinite(businessAtoms) && businessAtoms === 0
      ? 'Business facts 0'
      : 'Business fact coverage ' + (Number.isFinite(coverage) ? (coverage * 100).toFixed(1) + '%' : '—');
    const scenarioMeta = hasScenarios ? 'Candidates ' + (summary.candidates || 0) + ' · ' + coverageMeta + ' · Uncovered ' + (summary.uncovered_atoms || 0) : '';
    let html = '<div class="section-heading"><h3>' + (hasScenarios ? 'Auto-split scenarios' : 'Strict test case candidates') + ' <span class="count">' + cases.length + '</span></h3><span class="muted">' + esc([scenarioMeta, 'Fields complete ' + (summary.ready || 0), 'Fields missing ' + (summary.needs_review || 0), missingText ? 'Missing ' + missingText : ''].filter(Boolean).join(' · ')) + '</span></div>';
    if (!cases.length) {
      html += '<p class="empty-state">No auto-selectable test case scenarios for this record</p>';
    } else html += strictCaseTable(cases, hasScenarios);
    if (hasScenarios && (data.scenario_alternative_ids || []).length) {
      const alternativeIds = new Set(data.scenario_alternative_ids || []);
      const alternatives = (data.scenario_candidates || []).filter(function (item) { return alternativeIds.has(item.scenario_id); }).slice(0, 30);
      html += '<details><summary>Other candidates ' + data.scenario_alternative_ids.length + '</summary>' + strictCaseTable(alternatives, true) + '</details>';
    }
    if (hasScenarios && (data.cases || []).length) {
      html += '<details><summary>Legacy subject-projection comparison ' + data.cases.length + '</summary>' + strictCaseTable(data.cases, false) + '</details>';
    }
    target.innerHTML = html;
    target.hidden = false;
  }
  function clearPdfCasePreview() {
    state.pdfCasePreviewToken += 1;
    const target = $('kgPdfCasePreview');
    if (!target) return;
    target.innerHTML = '';
    target.hidden = true;
  }
  function clearPdfRecord() {
    state.pdf = null; state.pdfPreviewTriples = null; state.pdfEvaluation = null; state.pdfDirty = false;
    clearPdfCasePreview(); updateDirty();
    $('kgPdfVersion').textContent = '';
    $('kgPdfTriples').innerHTML = '<p class="empty-state">No reviewable content records</p>';
    $('kgPdfOcr').textContent = '';
    $('kgPdfHistory').innerHTML = '';
    $('kgPdfEval').innerHTML = '';
    $('kgPdfCorrections').innerHTML = '';
    $('kgPdfPreview').innerHTML = ''; $('kgPdfPreview').hidden = true;
    $('kgPdfApplyBtn').disabled = true;
    cancelBusy('kgPdfEvalBtn', true);
    cancelBusy('kgPdfCasePreviewBtn', true);
  }
  function syncPdfActionButtons() {
    if (!state.pdf) {
      $('kgPdfEvalBtn').disabled = true;
      $('kgPdfCasePreviewBtn').disabled = true;
    }
  }
  function selectedBuildFile() {
    const input = $('kgFileInput');
    return input && input.files && input.files[0] ? input.files[0] : null;
  }
  function formatFileSize(bytes) {
    const n = Number(bytes) || 0;
    if (n < 1024) return n + ' B';
    if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB';
    return (n / (1024 * 1024)).toFixed(1) + ' MB';
  }
  function attachFileIconName(fileName) {
    const lower = String(fileName || '').toLowerCase();
    if (lower.endsWith('.pdf')) return 'file-text';
    if (lower.endsWith('.csv')) return 'sheet';
    return 'file-spreadsheet';
  }
  function clearBuildFile() {
    const input = $('kgFileInput');
    if (input) input.value = '';
    syncBuildAttachStrip();
    syncBuildGuide();
  }
  function syncBuildAttachStrip() {
    const strip = $('kgBuildAttachStrip');
    if (!strip) return;
    const file = selectedBuildFile();
    const picked = state.buildPicked || '';
    const source = picked && state.sources.find(function (item) { return sourceId(item) === picked; });
    const step = state.buildStep || 'intro';
    const showFile = !!file && ['intro', 'pick', 'params', 'upload'].includes(step);
    const showSource = !file && !!source && ['intro', 'pick', 'params', 'upload'].includes(step);
    const show = showFile || showSource;
    strip.hidden = !show;
    if (!show) {
      strip.innerHTML = '';
      return;
    }
    if (showFile) {
      strip.innerHTML = '<div class="ontology-attach-card">'
        + icon(attachFileIconName(file.name))
        + '<span class="ontology-attach-meta"><strong title="' + esc(file.name) + '">' + esc(file.name) + '</strong><small>' + esc(formatFileSize(file.size)) + '</small></span>'
        + '<button type="button" class="ontology-attach-remove" id="kgBuildAttachRemove" title="Remove file" aria-label="Remove file">' + icon('x') + '</button>'
        + '</div>';
    } else {
      const name = source.name || source.file_name || picked;
      const kind = source.kind || source.file_type || '';
      strip.innerHTML = '<div class="ontology-attach-card">'
        + icon(kind === 'pdf' ? 'file-text' : 'file-spreadsheet')
        + '<span class="ontology-attach-meta"><strong title="' + esc(name) + '">' + esc(name) + '</strong><small>' + esc(String(kind || 'Data Source').toUpperCase()) + '</small></span>'
        + '<button type="button" class="ontology-attach-remove" id="kgBuildAttachRemove" title="Clear selection" aria-label="Clear selection">' + icon('x') + '</button>'
        + '</div>';
    }
    const removeBtn = $('kgBuildAttachRemove');
    if (removeBtn) removeBtn.addEventListener('click', clearBuildSelection);
    app.icons();
  }
  function clearBuildSelection() {
    clearBuildFile();
    state.buildPicked = '';
    syncBuildAttachStrip();
    syncBuildGuide();
    if (state.buildStep === 'pick') renderBuildPickerTable();
    persistCurrentSession();
  }
  function syncParamsConfirmEnabled() {
    const btn = $('kgBuildParamsBtn');
    if (!btn) return;
    const domain = ($('kgIncrDomain') && $('kgIncrDomain').value || '').trim();
    const ready = state.buildStep === 'params' && !!domain;
    btn.disabled = !ready;
    if (state.buildStep === 'params') btn.textContent = ready ? 'Confirm' : 'Fill parameters';
  }
  function setBuildStep(step) {
    state.buildStep = step || 'intro';
    const section = $('kgBuildSection');
    if (section) section.setAttribute('data-build-step', state.buildStep);
    const introBubble = $('kgBuildIntroBubble');
    const pickerBubble = $('kgBuildPickerBubble');
    const paramsBubble = $('kgBuildParamsBubble');
    const uploadBubble = $('kgBuildUploadBubble');
    const resultBubble = $('kgBuildResultBubble');
    const doneBubble = $('kgBuildDoneBubble');
    const paramsAck = $('kgBuildParamsAck');
    const current = state.buildStep;
    if (introBubble) introBubble.hidden = false;
    if (pickerBubble) pickerBubble.hidden = current !== 'pick';
    if (paramsBubble) paramsBubble.hidden = !['params', 'upload', 'review', 'done'].includes(current);
    if (uploadBubble) uploadBubble.hidden = !['upload', 'review', 'done'].includes(current);
    if (resultBubble) resultBubble.hidden = !['review', 'done'].includes(current);
    if (doneBubble) doneBubble.hidden = current !== 'done';
    if (paramsAck) paramsAck.hidden = !['upload', 'review', 'done'].includes(current);
    syncBuildGuide();
    syncParamsConfirmEnabled();
    syncBuildAttachStrip();
    if (current !== 'intro') {
      const stream = section && section.querySelector('.ontology-message-stream');
      if (stream) {
        window.requestAnimationFrame(function () {
          stream.scrollTop = stream.scrollHeight;
        });
      }
    }
  }
  function syncBuildGuide() {
    const title = $('kgBuildGuideTitle');
    const desc = $('kgBuildGuideDesc');
    const selectBtn = $('kgBuildSelectBtn');
    const paramsBtn = $('kgBuildParamsBtn');
    const parseBtn = $('kgParseBtn');
    const importBtn = $('kgImportBtn');
    const attachBtn = $('kgBuildAttachBtn');
    const step = state.buildStep || 'intro';
    const file = selectedBuildFile();
    const picked = state.buildPicked || '';
    const domain = ($('kgIncrDomain') && $('kgIncrDomain').value || '').trim();
    if (attachBtn) {
      attachBtn.hidden = !['intro', 'pick', 'params', 'upload'].includes(step);
      if (!attachBtn.hidden) attachBtn.innerHTML = icon('paperclip');
    }
    if (selectBtn) selectBtn.hidden = !['intro', 'pick'].includes(step);
    if (paramsBtn) paramsBtn.hidden = step !== 'params';
    if (parseBtn) {
      parseBtn.hidden = step !== 'upload';
      if (step === 'upload') {
        parseBtn.disabled = !file;
        parseBtn.textContent = file ? 'Upload & parse' : 'Select file';
      }
    }
    if (importBtn) importBtn.hidden = step !== 'review' && step !== 'done';

    if (step === 'intro' || step === 'pick') {
      if (title) title.textContent = 'Choose entry';
      if (desc) desc.textContent = 'Either upload a file or select a Data Source to start the build';
      if (selectBtn) {
        selectBtn.disabled = false;
        selectBtn.textContent = 'Select Data Source';
      }
    } else if (step === 'params') {
      if (title) title.textContent = domain ? 'Confirm parameters' : 'Fill parameters';
      if (desc) desc.textContent = domain
        ? 'Parameters filled; click Confirm to start parsing'
        : 'Fill in Business Domain and update mode in the conversation card above';
    } else if (step === 'upload') {
      if (file) {
        if (title) title.textContent = 'Upload & parse';
        if (desc) desc.textContent = 'File ready; click to start parsing';
        if (parseBtn) {
          parseBtn.disabled = false;
          parseBtn.textContent = 'Upload & parse';
        }
      } else if (picked) {
        if (title) title.textContent = 'Parsing';
        if (desc) desc.textContent = 'Parsing from the selected Data Source; no need to upload again';
        if (parseBtn) {
          parseBtn.hidden = true;
          parseBtn.disabled = true;
        }
        if (attachBtn) attachBtn.hidden = true;
      } else {
        if (title) title.textContent = 'Select file';
        if (desc) desc.textContent = 'Click the paperclip to select Excel / CSV / PDF';
        if (parseBtn) {
          parseBtn.disabled = true;
          parseBtn.textContent = 'Select file';
        }
      }
    } else if (step === 'done') {
      if (title) title.textContent = 'Submitted for Pending Review';
      if (desc) desc.textContent = 'View it in the Pending Review tab on the right, or start another build';
      if (importBtn) {
        importBtn.hidden = false;
        importBtn.disabled = true;
        importBtn.textContent = 'Submitted';
      }
    } else {
      if (title) title.textContent = 'Confirm submit for Pending Review';
      if (desc) desc.textContent = 'Review parse results, then submit; the file will appear in Pending Review on the right';
      if (importBtn) {
        importBtn.disabled = false;
        importBtn.textContent = 'Confirm submit';
      }
    }
    app.icons();
  }
  function confirmBuildParams() {
    const domainInput = $('kgIncrDomain');
    const domain = (domainInput && domainInput.value || '').trim();
    if (!domain) {
      status('kgBuildParamsStatus', 'Please enter a Business Domain first', 'error');
      if (domainInput) domainInput.focus();
      throw new Error('Please enter a Business Domain first');
    }
    status('kgBuildParamsStatus', '');
    const mode = ($('kgImportMode') && $('kgImportMode').value) || 'supplement';
    const modeLabel = mode === 'replace' ? 'Replace this source' : 'Supplement data';
    const ack = $('kgBuildParamsAckText');
    if (ack) ack.textContent = 'Confirmed: Business Domain “' + domain + '” · ' + modeLabel;
    if ($('kgStatus')) { $('kgStatus').hidden = true; $('kgStatus').textContent = ''; }

    const file = selectedBuildFile();
    const picked = state.buildPicked || '';
    // Source path: skip re-upload, parse from selected source immediately.
    if (!file && picked) {
      setBuildStep('upload');
      persistCurrentSession();
      syncSessionNewEnabled();
      return buildFromSelectedSource();
    }

    // File path: go to parse step (file already attached).
    setBuildStep('upload');
    persistCurrentSession();
    syncSessionNewEnabled();
  }
  async function buildFromSelectedSource() {
    const picked = state.buildPicked || '';
    if (!picked) throw new Error('Please select a Data Source first');
    const domain = ($('kgIncrDomain') && $('kgIncrDomain').value || '').trim();
    if (!domain) throw new Error('Please enter a Business Domain first');
    const mode = ($('kgImportMode') && $('kgImportMode').value) || 'supplement';
    const source = state.sources.find(function (item) { return sourceId(item) === picked; });
    const name = source ? (source.name || source.file_name || picked) : picked;
    status('kgStatus', 'Parsing from “' + name + '”…', 'building');
    const uploadBubble = $('kgBuildUploadBubble');
    if (uploadBubble) {
      const strong = uploadBubble.querySelector('.ontology-bubble-intro strong');
      const p = uploadBubble.querySelector('.ontology-bubble-intro p') || $('kgBuildUploadHint');
      if (strong) strong.textContent = 'Parse selected Data Source';
      if (p) p.textContent = 'Generating parse results from the selected Data Source; no need to upload again.';
    }
    syncBuildGuide();
    const result = await get('/api/kg/preview?' + new URLSearchParams({
      source_id: picked,
      source: picked,
      mode: mode
    }));
    state.build = Object.assign({}, result, {
      source_id: picked,
      domain: domain,
      mode: mode,
      file_name: result.file_name || result.name || name,
      name: result.name || result.file_name || name,
      imported: false,
      pending_review: false
    });
    status('kgStatus', '');
    renderBuild();
    buildStatus();
    persistCurrentSession();
  }
  function confirmBuildSelection() {
    const file = selectedBuildFile();
    const picked = state.buildPicked || '';
    if (!file && !picked) {
      showBuildSourcePicker();
      return;
    }
    if (picked && !file) {
      const source = state.sources.find(function (item) { return sourceId(item) === picked; });
      if (source && $('kgIncrDomain') && !($('kgIncrDomain').value || '').trim()) {
        $('kgIncrDomain').value = (source.domain || source.name || source.file_name || '').trim();
      }
    }
    const picker = $('kgBuildPickerBubble');
    if (picker) picker.hidden = true;
    setBuildStep('params');
    syncParamsConfirmEnabled();
    syncBuildGuide();
    persistCurrentSession();
    syncSessionNewEnabled();
    loadIncremental();
  }
  function renderBuildPendingDone(data, result) {
    const doneText = $('kgBuildDoneText');
    if (!doneText || !data) return;
    const name = data.file_name || data.name || 'Untitled file';
    const domain = data.domain || ($('kgIncrDomain').value || '').trim() || 'Untitled Business Domain';
    const triplesTotal = data.triples_total == null
      ? ((data.triples || []).length)
      : data.triples_total;
    const caseTotal = data.case_count == null
      ? ((data.cases || []).length)
      : data.case_count;
    const modeLabel = (data.mode || $('kgImportMode').value) === 'replace' ? 'Replace this source' : 'Supplement data';
    const parts = [
      'Added “' + name + '” to Pending Review.',
      'Business Domain: ' + domain + ' · Update mode: ' + modeLabel + '.',
      'Parse result: ' + (Number(triplesTotal) || 0) + ' relations' + (caseTotal ? ' · ' + caseTotal + ' cases' : '') + '.',
      'Continue in the Pending Review tab on the right.'
    ];
    if (result && result.message) parts.push(String(result.message));
    doneText.textContent = parts.join(' ');
  }
  function renderBuild() {
    const data = state.build; if (!data) return;
    const cases = data.cases || [];
    const triples = data.triples || [];
    const triplesTotal = data.triples_total == null ? triples.length : data.triples_total;
    const caseTotal = data.case_count == null ? cases.length : data.case_count;
    setBuildStep(data.imported || data.pending_review ? 'done' : 'review');
    $('kgResults').hidden = false;
    $('kgMeta').textContent = (data.file_name || data.name || 'Parse result') + ' · ' + triplesTotal + ' relations' + (caseTotal ? ' · ' + caseTotal + ' cases' : '');
    $('kgPreviewPane').innerHTML = data.kind === 'pdf'
      ? (triples.length ? triplesTable(triples) : '<p class="empty-state">No triple preview; ' + triplesTotal + ' relations total</p>')
      : (cases.length
        ? '<table class="diff-table"><thead><tr><th>Case name</th><th>Type</th><th>Preconditions</th><th>Actions</th><th>Expected Behavior</th></tr></thead><tbody>' + cases.map(function (row) { return '<tr><td>' + esc(row.case_name) + '</td><td>' + esc(row.case_type) + '</td><td>' + esc((row.preconditions || []).join('; ')) + '</td><td>' + esc(row.step) + '</td><td>' + esc(row.expectation) + '</td></tr>'; }).join('') + '</tbody></table>'
        : '<p class="empty-state">No case preview</p>');
    const pending = data.pending || {};
    const groups = [['add', 'Added'], ['remove', 'Removed'], ['changed', 'Changed']];
    $('kgIncrResults').innerHTML = '<div class="diff-summary">' + groups.map(function (pair) { const bucket = pending[pair[0]] || {}; const records = Array.isArray(bucket) ? bucket : bucket.records || []; return '<span class="' + pair[0] + '">' + pair[1] + '<b>' + (bucket.count == null ? records.length : bucket.count) + '</b></span>'; }).join('') + '</div>' + groups.map(function (pair) {
      const bucket = pending[pair[0]] || {}; const records = Array.isArray(bucket) ? bucket : bucket.records || [];
      if (!records.length) return '';
      return '<details><summary>' + pair[1] + ' ' + records.length + '</summary><div class="table-scroll"><table class="diff-table"><thead><tr><th>Case</th><th>Before</th><th>After</th></tr></thead><tbody>' + records.map(function (record) { return '<tr><td>' + esc(record.case_name || record.case_key || '') + '</td><td class="removed">' + esc(pair[0] === 'add' ? '' : tripleText(record.old_triple || record)) + '</td><td class="added">' + esc(pair[0] === 'remove' ? '' : tripleText(record.new_triple || record)) + '</td></tr>'; }).join('') + '</tbody></table></div></details>';
    }).join('');
    const importBtn = $('kgImportBtn');
    if (importBtn) {
      importBtn.hidden = false;
      importBtn.disabled = !!(data.imported || data.pending_review) || ['processing', 'pending', 'failed', 'waiting_dependency'].includes(data.status);
      importBtn.textContent = data.imported || data.pending_review ? 'Submitted' : 'Confirm submit';
    }
    if ($('kgIncrApplyBtn')) $('kgIncrApplyBtn').hidden = true;
    if ($('kgResumeBuild')) $('kgResumeBuild').hidden = !data.job_id || !['waiting_dependency', 'failed', 'processing', 'interrupted'].includes(data.status);
    $('kgPreviewPane').hidden = false;
    $('kgPreviewToggle').setAttribute('aria-expanded', 'true');
    if (data.pending_review || data.imported) renderBuildPendingDone(data);
    syncBuildGuide();
    app.icons();
  }
  function buildStatus() {
    const data = state.build; if (!data) return;
    if (data.status === 'waiting_dependency') status('kgStatus', 'File saved; parsing not finished yet.' + (data.message || ' Parse service temporarily unavailable.'), 'error');
    else if (data.status === 'failed') status('kgStatus', data.error || data.message || 'Parse failed; original file was saved.', 'error');
    else if (['pending', 'processing', 'interrupted'].includes(data.status)) {
      const progress = data.progress && typeof data.progress === 'object' ? data.progress.percentage : data.progress;
      status('kgStatus', (data.message || 'File saved; parsing in progress.') + (progress == null ? '' : ' ' + Number(progress) + '%'), 'building');
    }
    else if (data.imported || data.pending_review) status('kgStatus', 'Submitted for Pending Review; view it in the Pending Review tab on the right.');
    else status('kgStatus', data.duplicate ? 'This file already exists. Parse results loaded.' : 'Parse complete; confirm submit for Pending Review.');
  }
  async function buildFile() {
    if (state.buildStep === 'intro' || state.buildStep === 'pick') throw new Error('Please select a file or Data Source first');
    if (state.buildStep === 'params') throw new Error('Please confirm build parameters first');
    const domain = ($('kgIncrDomain').value || '').trim();
    if (!domain) throw new Error('Please enter a Business Domain first');
    const file = selectedBuildFile(); if (!file) throw new Error('Please select an Excel, CSV, or PDF file via the paperclip');
    const form = new FormData(); form.append('file', file); form.append('domain', domain); form.append('mode', $('kgImportMode').value);
    if (state.buildPicked) form.append('source_id', state.buildPicked);
    status('kgStatus', 'Parsing ' + file.name, 'building');
    state.build = null; if ($('kgResults')) $('kgResults').hidden = true;
    const data = await post('/api/kg/build', form);
    state.build = Object.assign({ file_name: file.name, mode: $('kgImportMode').value, domain: domain }, data);
    if (data.domain) $('kgIncrDomain').value = data.domain;
    renderBuild();
    buildStatus();
    persistCurrentSession();
  }
  $('kgBuildParamsBtn')?.addEventListener('click', function (event) {
    event.preventDefault();
    event.stopPropagation();
    if (this.disabled) return;
    const btn = this;
    btn.disabled = true;
    Promise.resolve()
      .then(function () { return confirmBuildParams(); })
      .catch(function (error) {
        status('kgBuildParamsStatus', (error && error.message) || 'Confirmation failed', 'error');
      })
      .finally(function () {
        syncParamsConfirmEnabled();
        syncBuildGuide();
      });
  });
  $('kgBuildSelectBtn')?.addEventListener('click', function (event) {
    event.preventDefault();
    event.stopPropagation();
    showBuildSourcePicker();
  });
  $('kgIncrDomain')?.addEventListener('input', function () {
    syncParamsConfirmEnabled();
    syncBuildGuide();
    persistCurrentSession();
  });
  $('kgIncrDomain')?.addEventListener('change', function () {
    syncParamsConfirmEnabled();
    loadIncremental();
    persistCurrentSession();
  });
  $('kgImportMode')?.addEventListener('change', function () {
    syncParamsConfirmEnabled();
    persistCurrentSession();
  });
  $('kgBuildAttachBtn')?.addEventListener('click', function () {
    const input = $('kgFileInput');
    if (input) input.click();
  });
  $('kgFileInput')?.addEventListener('change', function () {
    if (!selectedBuildFile()) {
      syncBuildAttachStrip();
      syncBuildGuide();
      return;
    }
    // Path A — upload only: enter build immediately
    state.buildPicked = '';
    confirmBuildSelection();
  });
  $('kgParseBtn')?.addEventListener('click', function () {
    if (!selectedBuildFile()) {
      const input = $('kgFileInput');
      if (input) input.click();
      return;
    }
    const run = busy('kgParseBtn', 'kgStatus', buildFile);
    if (run && typeof run.finally === 'function') run.finally(syncBuildGuide);
    else syncBuildGuide();
  });
  const resumeBuild = document.createElement('button'); resumeBuild.id = 'kgResumeBuild'; resumeBuild.className = 'kg-workbench-button'; resumeBuild.innerHTML = icon('rotate-cw') + 'Resume parse'; resumeBuild.hidden = true;
  const resultActions = $('kgPreviewToggle') && $('kgPreviewToggle').parentElement;
  if (resultActions) resultActions.appendChild(resumeBuild);
  else if ($('kgImportBtn')) $('kgImportBtn').after(resumeBuild);
  resumeBuild.addEventListener('click', function () { busy('kgResumeBuild', 'kgStatus', async function () {
    const data = state.build; if (!data || !data.job_id) throw new Error('No resumable parse job found');
    status('kgStatus', 'Resuming file parse', 'building');
    const result = await post('/api/kg/jobs/' + encodeURIComponent(data.job_id) + '/retry', {});
    state.build = Object.assign({}, data, result); renderBuild(); buildStatus();
  }); });
  $('kgImportMode').addEventListener('change', async function () { if (!state.build || !state.build.source_id) return; try { const result = await get('/api/kg/preview?' + new URLSearchParams({ source_id: state.build.source_id, mode: this.value })); state.build = Object.assign({}, result, { mode: this.value }); renderBuild(); buildStatus(); } catch (error) { status('kgStatus', error.message, 'error'); } });
  $('kgPreviewToggle').addEventListener('click', function () { $('kgPreviewPane').hidden = !$('kgPreviewPane').hidden; this.setAttribute('aria-expanded', String(!$('kgPreviewPane').hidden)); });
  $('kgImportBtn').addEventListener('click', function () { busy('kgImportBtn', 'kgStatus', async function () {
    const data = state.build; if (!data) return;
    const body = {
      source_id: data.source_id,
      job_id: data.job_id,
      kind: data.kind,
      domain: data.domain || ($('kgIncrDomain').value || '').trim(),
      mode: data.mode || $('kgImportMode').value,
      version: data.version,
      file_name: data.file_name || data.name,
      bytes: data.bytes || 0,
      case_count: data.case_count,
      triples_total: data.triples_total,
      cases: data.cases,
      triples: data.triples,
    };
    const result = await post('/api/kg/import', body);
    data.imported = false;
    data.pending_review = true;
    data.status = 'pending_review';
    if (result && result.source_id) data.source_id = result.source_id;
    renderBuildPendingDone(data, result);
    renderBuild();
    status('kgStatus', result.message || ('Submitted for Pending Review. Current results: ' + (result.total || result.triples_total || result.triple_count || 0) + '.'));
    await loadSources();
    setOntologyListOpen(true);
    setOntologyListTab('pending');
    persistCurrentSession();
    const highlightId = (result && result.source_id) || data.source_id || state.buildPicked;
    window.requestAnimationFrame(function () {
      flashPendingSourceRow(highlightId);
    });
  }).then(function () { if (state.build && (state.build.imported || state.build.pending_review)) $('kgImportBtn').disabled = true; }); });
  async function loadIncremental() {
    const summary = $('kgIncrSummary');
    if (!summary) return;
    const domain = ($('kgIncrDomain').value || '').trim();
    if (!domain) { summary.textContent = ''; return; }
    try { const data = await get('/api/kg/incr/state?domain=' + encodeURIComponent(domain)); summary.textContent = data.has_baseline ? 'Baseline ' + (data.current.cases || 0) + ' cases / ' + (data.current.triples || 0) + ' relations' : 'No baseline yet'; }
    catch (error) { summary.textContent = error.message; }
  }
  function activeRefineSources() {
    return (state.sources || []).filter(function (source) { return !isPendingReviewSource(source); });
  }
  function filteredRefinePickerSources() {
    const query = String(state.refinePickerQuery || '').trim().toLowerCase();
    const sources = activeRefineSources();
    if (!query) return sources;
    return sources.filter(function (source) {
      const name = String(source.name || source.file_name || '').toLowerCase();
      const id = String(sourceId(source) || '').toLowerCase();
      const kind = String(source.kind || source.file_type || '').toLowerCase();
      return name.includes(query) || id.includes(query) || kind.includes(query);
    });
  }
  function syncRefineAttachStrip() {
    const strip = $('kgRefineAttachStrip');
    if (!strip) return;
    const selected = state.refinePicked || '';
    const source = selected && state.sources.find(function (item) { return sourceId(item) === selected; });
    const show = !!selected && !!source && state.refineStep === 'pick';
    strip.hidden = !show;
    if (!show) {
      strip.innerHTML = '';
      return;
    }
    const name = source.name || source.file_name || selected;
    const kind = source.kind || source.file_type || (/\.pdf$/i.test(name) ? 'pdf' : 'excel');
    const triples = source.triple_count == null ? (source.triples || 0) : source.triple_count;
    const meta = String(kind).toUpperCase()
      + ' · ' + triples + ' relations'
      + (source.case_count ? ' · ' + source.case_count + ' cases' : '');
    strip.innerHTML = '<div class="ontology-attach-card">'
      + icon(attachFileIconName(name))
      + '<span class="ontology-attach-meta"><strong title="' + esc(name) + '">' + esc(name) + '</strong><small>' + esc(meta) + '</small></span>'
      + '<button type="button" class="ontology-attach-remove" id="kgRefineAttachRemove" title="Remove" aria-label="Remove">' + icon('x') + '</button>'
      + '</div>';
    const removeBtn = $('kgRefineAttachRemove');
    if (removeBtn) removeBtn.addEventListener('click', clearRefinePick);
    app.icons();
  }
  function filteredBuildPickerSources() {
    const query = String(state.buildPickerQuery || '').trim().toLowerCase();
    const sources = activeRefineSources();
    if (!query) return sources;
    return sources.filter(function (source) {
      const name = String(source.name || source.file_name || '').toLowerCase();
      const id = String(sourceId(source) || '').toLowerCase();
      const kind = String(source.kind || source.file_type || '').toLowerCase();
      return name.includes(query) || id.includes(query) || kind.includes(query);
    });
  }
  function renderBuildPickerTable() {
    const host = $('kgBuildPickerTable');
    if (!host) return;
    syncBuildAttachStrip();
    const allSources = activeRefineSources();
    const sources = filteredBuildPickerSources();
    if (!allSources.length) {
      host.innerHTML = '<div class="ontology-sources-empty">No available Data Sources</div>';
      return;
    }
    if (!sources.length) {
      host.innerHTML = '<div class="ontology-sources-empty">No matching Data Sources found</div>';
      return;
    }
    const selected = state.buildPicked || '';
    host.innerHTML = sources.map(function (source) {
      const id = sourceId(source);
      const kind = source.kind || source.file_type || (/\.pdf$/i.test(source.name || '') ? 'pdf' : 'excel');
      const name = source.name || source.file_name || id;
      const triples = source.triple_count == null ? (source.triples || 0) : source.triple_count;
      const isSelected = id === selected;
      return '<button type="button" class="ontology-source-item' + (isSelected ? ' is-selected' : '') + '" data-build-pick-source="' + esc(id) + '" role="radio" aria-checked="' + (isSelected ? 'true' : 'false') + '" title="' + esc(name) + '">'
        + '<span class="ontology-source-radio" aria-hidden="true"></span>'
        + '<span class="src-name">' + esc(name) + '</span>'
        + '<span class="src-meta">' + esc(String(kind).toUpperCase()) + ' · ' + esc(triples) + ' relations</span>'
        + '</button>';
    }).join('');
    host.querySelectorAll('[data-build-pick-source]').forEach(function (row) {
      row.addEventListener('click', function () {
        const id = row.getAttribute('data-build-pick-source');
        if (id && id === state.buildPicked) clearBuildPick();
        else pickBuildSource(id);
      });
    });
  }
  function clearBuildPick() {
    state.buildPicked = '';
    renderBuildPickerTable();
    syncBuildAttachStrip();
    syncBuildGuide();
    persistCurrentSession();
  }
  function pickBuildSource(id) {
    if (!id) return;
    const input = $('kgFileInput');
    if (input) input.value = '';
    state.buildPicked = id;
    // Path B — select source only: enter build immediately
    confirmBuildSelection();
  }
  function applyBuildPickerSearch() {
    const input = $('kgBuildPickerSearch');
    state.buildPickerQuery = input ? input.value : '';
    renderBuildPickerTable();
  }
  function showBuildSourcePicker() {
    state.buildStep = 'pick';
    const section = $('kgBuildSection');
    if (section) section.setAttribute('data-build-step', 'pick');
    const picker = $('kgBuildPickerBubble');
    if (picker) picker.hidden = false;
    renderBuildPickerTable();
    syncBuildGuide();
    syncBuildAttachStrip();
    const stream = section && section.querySelector('.ontology-message-stream');
    if (stream) {
      window.requestAnimationFrame(function () { stream.scrollTop = stream.scrollHeight; });
    }
    window.setTimeout(function () {
      const search = $('kgBuildPickerSearch');
      if (search && typeof search.focus === 'function') search.focus();
    }, 80);
  }
  function renderRefinePickerTable() {
    const host = $('kgRefinePickerTable');
    if (!host) return;
    syncRefineAttachStrip();
    const allSources = activeRefineSources();
    const sources = filteredRefinePickerSources();
    if (!allSources.length) {
      host.innerHTML = '<div class="ontology-sources-empty">No available Data Sources</div>';
      return;
    }
    if (!sources.length) {
      host.innerHTML = '<div class="ontology-sources-empty">No matching Data Sources found</div>';
      return;
    }
    const selected = state.refinePicked || '';
    host.innerHTML = sources.map(function (source) {
      const id = sourceId(source);
      const kind = source.kind || source.file_type || (/\.pdf$/i.test(source.name || '') ? 'pdf' : 'excel');
      const name = source.name || source.file_name || id;
      const triples = source.triple_count == null ? (source.triples || 0) : source.triple_count;
      const isSelected = id === selected;
      return '<button type="button" class="ontology-source-item' + (isSelected ? ' is-selected' : '') + '" data-pick-source="' + esc(id) + '" role="radio" aria-checked="' + (isSelected ? 'true' : 'false') + '" title="' + esc(name) + '">'
        + '<span class="ontology-source-radio" aria-hidden="true"></span>'
        + '<span class="src-name">' + esc(name) + '</span>'
        + '<span class="src-meta">' + esc(String(kind).toUpperCase()) + ' · ' + esc(triples) + ' relations</span>'
        + '</button>';
    }).join('');
    host.querySelectorAll('[data-pick-source]').forEach(function (row) {
      row.addEventListener('click', function () {
        const id = row.getAttribute('data-pick-source');
        if (id && id === state.refinePicked) clearRefinePick();
        else pickRefineSource(id);
      });
    });
  }
  function clearRefinePick() {
    state.refinePicked = '';
    if ($('kgRefineSource')) $('kgRefineSource').value = '';
    renderRefinePickerTable();
    syncRefineAttachStrip();
    syncRefineGuide();
  }
  function pickRefineSource(id) {
    if (!id) return;
    state.refinePicked = id;
    if ($('kgRefineSource')) $('kgRefineSource').value = id;
    renderRefinePickerTable();
    syncRefineAttachStrip();
    syncRefineGuide();
    persistCurrentSession();
    const stream = $('kgRefineSection') && $('kgRefineSection').querySelector('.ontology-message-stream');
    if (stream) stream.scrollTop = stream.scrollHeight;
  }
  function applyRefinePickerSearch() {
    const input = $('kgRefinePickerSearch');
    state.refinePickerQuery = input ? input.value : '';
    renderRefinePickerTable();
  }
  function showRefineSourcePicker() {
    state.refineStep = 'pick';
    const section = $('kgRefineSection');
    if (section) section.setAttribute('data-refine-step', 'pick');
    const picker = $('kgRefinePickerBubble');
    if (picker) picker.hidden = false;
    renderRefinePickerTable();
    syncRefineGuide();
    const stream = section && section.querySelector('.ontology-message-stream');
    if (stream) {
      window.requestAnimationFrame(function () { stream.scrollTop = stream.scrollHeight; });
    }
    window.setTimeout(function () {
      const search = $('kgRefinePickerSearch');
      if (search && typeof search.focus === 'function') search.focus();
    }, 80);
  }
  function syncRefineGuide() {
    const title = $('kgRefineGuideTitle');
    const desc = $('kgRefineGuideDesc');
    const loadBtn = $('kgRefineLoad');
    const uploadBtn = $('kgRefineUploadBtn');
    const picked = state.refinePicked || ($('kgRefineSource') && $('kgRefineSource').value) || '';
    const opened = !!state.source;
    if (uploadBtn) uploadBtn.innerHTML = icon('paperclip');
    if (opened) {
      if (title) title.textContent = 'Refining';
      if (desc) desc.textContent = 'Reselect a Data Source, or upload a new file';
      if (loadBtn) {
        loadBtn.disabled = false;
        loadBtn.textContent = 'Reselect';
      }
    } else if (picked) {
      if (title) title.textContent = 'Confirm selection';
      if (desc) desc.textContent = 'Data Source selected; click Confirm to enter refine';
      if (loadBtn) {
        loadBtn.disabled = false;
        loadBtn.textContent = 'Confirm';
      }
    } else {
      if (title) title.textContent = 'Select Data Source';
      if (desc) desc.textContent = 'Select a Data Source, or upload a new file via the paperclip';
      if (loadBtn) {
        loadBtn.disabled = false;
        loadBtn.textContent = 'Select Data Source';
      }
    }
    syncRefineAttachStrip();
    app.icons();
  }
  $('kgRefineUploadBtn')?.addEventListener('click', function () {
    const input = $('kgRefineFileInput');
    if (input) input.click();
  });
  $('kgRefinePickerSearch')?.addEventListener('input', applyRefinePickerSearch);
  $('kgRefinePickerSearch')?.addEventListener('keydown', function (event) {
    if (event.key === 'Enter') {
      event.preventDefault();
      applyRefinePickerSearch();
    }
  });
  $('kgRefinePickerSearchBtn')?.addEventListener('click', applyRefinePickerSearch);
  $('kgRefinePickerClear')?.addEventListener('click', clearRefinePick);
  $('kgRefineFileInput')?.addEventListener('change', function () {
    const input = $('kgRefineFileInput');
    const file = input && input.files && input.files[0];
    if (!file) return;
    busy('kgRefineUploadBtn', 'kgRefineFile', async function () {
      setSkillsCreateMode(false, false);
      setSourcesWorkMode('refine', false);
      status('kgRefineFile', 'Uploading and parsing ' + file.name, 'building');
      const form = new FormData();
      form.append('file', file);
      form.append('domain', (($('kgIncrDomain') && $('kgIncrDomain').value) || '').trim() || 'Default Business Domain');
      form.append('mode', 'supplement');
      const built = await post('/api/kg/build', form);
      const body = {
        source_id: built.source_id,
        job_id: built.job_id,
        kind: built.kind,
        domain: built.domain || 'Default Business Domain',
        mode: 'supplement',
        version: built.version,
        file_name: built.file_name || file.name,
        bytes: built.bytes || file.size || 0,
        case_count: built.case_count,
        triples_total: built.triples_total,
        cases: built.cases,
        triples: built.triples,
      };
      const imported = await post('/api/kg/import', body);
      await loadSources();
      const newId = (imported && imported.source_id) || built.source_id;
      if (newId) {
        state.refinePicked = newId;
        if ($('kgRefineSource')) $('kgRefineSource').value = newId;
        await openSource(newId);
      }
      status('kgRefineFile', '');
      if (input) input.value = '';
    });
  });
  setBuildStep('intro');
  syncParamsConfirmEnabled();
  $('kgBuildPickerSearch')?.addEventListener('input', applyBuildPickerSearch);
  $('kgBuildPickerSearch')?.addEventListener('keydown', function (event) {
    if (event.key === 'Enter') {
      event.preventDefault();
      applyBuildPickerSearch();
    }
  });
  $('kgBuildPickerSearchBtn')?.addEventListener('click', applyBuildPickerSearch);
  $('kgBuildPickerClear')?.addEventListener('click', clearBuildPick);
  $('kgRefineLoad')?.addEventListener('click', function () {
    const picked = state.refinePicked || ($('kgRefineSource') && $('kgRefineSource').value) || '';
    const label = ($('kgRefineLoad') && $('kgRefineLoad').textContent) || '';
    if (label === 'Reselect' || (!picked && state.refineStep !== 'pick')) {
      state.refinePicked = '';
      if ($('kgRefineSource')) $('kgRefineSource').value = '';
      showRefineSourcePicker();
      return;
    }
    if (!picked) {
      showRefineSourcePicker();
      return;
    }
    openSource(picked);
  });
  syncRefineGuide();
  const crumbLibrary = $('kgCrumbLibrary');
  if (crumbLibrary) crumbLibrary.addEventListener('click', showOntologyHome);
  $('kgCrumbOntologyRoot')?.addEventListener('click', showOntologyHome);
  function syncOntologyTopbarCopy() {
    const onOntology = !!document.querySelector('.view-panel.is-visible[data-panel="ontology"]')
      || (window.location.hash || '').startsWith('#ontology');
    if (!onOntology) return;
    const title = $('viewTitle');
    const crumb = $('ontologyTitleBreadcrumb');
    const desc = $('viewDescription');
    if (crumb && !crumb.hidden) return;
    const mode = state.sourcesWork === 'refine' ? 'refine' : 'build';
    if (title) {
      title.hidden = false;
      const sub = mode === 'refine' ? 'Source Refine' : 'File Build';
      title.innerHTML = 'Ontology<span class="view-title-sep" aria-hidden="true"></span>' + sub;
    }
    if (desc) {
      desc.hidden = false;
      desc.textContent = mode === 'refine'
        ? 'Select an existing Data Source to refine, or upload a new file to continue.'
        : 'Configure build parameters, upload and parse files, then submit for Pending Review.';
    }
  }
  function setOntologyTitleMode(work, label) {
    const title = $('viewTitle');
    const crumb = $('ontologyTitleBreadcrumb');
    const current = $('ontologyCrumbCurrent');
    if (work) {
      if (title) title.hidden = true;
      if (crumb) crumb.hidden = false;
      if (current) current.textContent = label || 'Data Source';
    } else {
      if (crumb) crumb.hidden = true;
      syncOntologyTopbarCopy();
    }
  }
  function setSkillTitleMode(work, label) {
    const title = $('viewTitle');
    const crumb = $('skillTitleBreadcrumb');
    const current = $('skillCrumbCurrent');
    if (work) {
      if (title) title.hidden = true;
      if (crumb) crumb.hidden = false;
      if (current) current.textContent = label || 'New';
    } else {
      if (title) {
        title.hidden = false;
        if (document.body.querySelector('.view-panel.is-visible[data-panel="skill"]') || (window.location.hash.indexOf('skill') === 1)) {
          title.textContent = 'Skill';
        }
      }
      if (crumb) crumb.hidden = true;
    }
    syncSkillTrashVisibility();
  }
  function syncOntologyListToggle() {
    const listOpen = !!state.ontologyListOpen;
    const listBtn = $('kgOntologyListToggle');
    if (listBtn) {
      listBtn.classList.toggle('is-selected', listOpen);
      listBtn.setAttribute('aria-pressed', String(listOpen));
      listBtn.title = listOpen ? 'Collapse list' : 'Open list';
      listBtn.setAttribute('aria-label', listOpen ? 'Collapse list' : 'Open list');
    }
    const listPanel = $('kgOntologyListBlock');
    if (listPanel) listPanel.hidden = !listOpen;
    const sourcesPanel = $('kgSubviewSources');
    if (sourcesPanel) sourcesPanel.classList.toggle('is-list-dock', listOpen);
    const workspace = document.querySelector('.workspace');
    const onOntology = !!document.querySelector('.view-panel.is-visible[data-panel="ontology"]')
      || (window.location.hash || '').startsWith('#ontology');
    if (workspace) {
      workspace.classList.toggle('is-ontology-page', onOntology);
      if (onOntology) workspace.classList.toggle('is-list-dock', listOpen);
    }
  }
  function setOntologyListOpen(open) {
    state.ontologyListOpen = !!open;
    syncOntologyListToggle();
    if (state.ontologyListOpen && state.ontologyListTab === 'trash') loadTrashList();
  }
  function setOntologyListTab(tab) {
    if (tab === 'trash') state.ontologyListTab = 'trash';
    else if (tab === 'pending') state.ontologyListTab = 'pending';
    else state.ontologyListTab = 'sources';
    document.querySelectorAll('#kgOntologyListTabs [data-ontology-list-tab]').forEach(function (button) {
      const selected = button.getAttribute('data-ontology-list-tab') === state.ontologyListTab;
      button.classList.toggle('is-selected', selected);
      button.setAttribute('aria-selected', String(selected));
    });
    const sourcesPane = $('kgOntologySourcesPane');
    const pendingPane = $('kgOntologyPendingPane');
    const trashPane = $('kgOntologyTrashPane');
    const searchRow = $('kgOntologySourceSearchRow');
    if (sourcesPane) sourcesPane.hidden = state.ontologyListTab !== 'sources';
    if (pendingPane) pendingPane.hidden = state.ontologyListTab !== 'pending';
    if (trashPane) trashPane.hidden = state.ontologyListTab !== 'trash';
    if (searchRow) searchRow.hidden = state.ontologyListTab === 'trash';
    const search = $('kgSourceSearch');
    if (search) {
      search.placeholder = state.ontologyListTab === 'pending' ? 'Search Pending Review' : 'Search Data Sources';
    }
    if (state.ontologyListTab === 'trash') loadTrashList();
    else renderSources();
  }
  function toggleOntologyList() {
    setOntologyListOpen(!state.ontologyListOpen);
  }
  function syncOntologyTrashVisibility() {}
  function syncSkillTrashVisibility() {
    const actions = $('skillStageActions');
    if (!actions) return;
    const onSkill = !!document.querySelector('.view-panel.is-visible[data-panel="skill"]');
    actions.hidden = !onSkill;
    syncSkillViewTabs();
  }
  function syncSkillsListToggle() {
    const listOpen = !!state.skillsListOpen;
    const listBtn = $('kgSkillListToggle');
    if (listBtn) {
      listBtn.classList.toggle('is-selected', listOpen);
      listBtn.setAttribute('aria-pressed', String(listOpen));
      listBtn.title = listOpen ? 'Collapse list' : 'Open list';
      listBtn.setAttribute('aria-label', listOpen ? 'Collapse list' : 'Open list');
    }
    const listPanel = $('kgSkillsBlock');
    if (listPanel) listPanel.hidden = !listOpen;
    const panel = $('kgSkillWorkbench');
    if (panel) panel.classList.toggle('is-list-dock', listOpen);
    const workspace = document.querySelector('.workspace');
    const onSkill = !!document.querySelector('.view-panel.is-visible[data-panel="skill"]')
      || (window.location.hash || '').startsWith('#skill');
    if (workspace && onSkill) workspace.classList.toggle('is-list-dock', listOpen);
  }
  function setSkillsListOpen(open) {
    state.skillsListOpen = !!open;
    syncSkillsListToggle();
    if (state.skillsListOpen) ensureSkills();
  }
  function toggleSkillsList() {
    setSkillsListOpen(!state.skillsListOpen);
    if (app.setView) app.setView('skill', false);
  }
  function syncSkillViewTabs() {
    syncSkillsListToggle();
  }
  function setSourcesWorkMode(mode, writeRoute) {
    if (mode !== 'build' && mode !== 'refine') {
      state.sourcesWork = null;
      const panel = $('kgSubviewSources');
      if (panel) panel.classList.remove('is-build-mode', 'is-refine-mode');
      ['build', 'refine'].forEach(function (name) {
        const el = $(name === 'build' ? 'kgTabBuild' : 'kgTabRefine');
        if (!el) return;
        el.classList.remove('is-selected', 'is-active');
        el.setAttribute('aria-pressed', 'false');
        el.tabIndex = -1;
      });
      return;
    }
    const next = mode;
    setSkillsCreateMode(false, false);
    state.sourcesWork = next;
    const panel = $('kgSubviewSources');
    if (panel) {
      panel.classList.toggle('is-build-mode', next === 'build');
      panel.classList.toggle('is-refine-mode', next === 'refine');
    }
    const workTabs = $('ontologyRailSubnav');
    if (workTabs) workTabs.hidden = false;
    setOntologyTitleMode(false);
    ['build', 'refine'].forEach(function (name) {
      const el = $(name === 'build' ? 'kgTabBuild' : 'kgTabRefine');
      if (!el) return;
      const active = next === name;
      el.classList.toggle('is-selected', active);
      el.classList.toggle('is-active', active);
      el.setAttribute('aria-pressed', String(active));
      el.tabIndex = active ? 0 : -1;
    });
    syncOntologyListToggle();
    if (next === 'refine') syncRefineGuide();
    if (app.setView) app.setView('ontology', false);
    syncOntologyTopbarCopy();
    persistCurrentSession();
    if (writeRoute !== false) {
      if (next === 'build') setHash({ tab: 'builder', view: '', source: '', row: '', record: '' });
      else setHash({ tab: 'refine', view: '', source: state.source || '', row: state.source ? state.row : '', record: '' });
    }
  }
  function showOntologyHome() {
    setSkillsCreateMode(false, false);
    setOntologyListOpen(false);
    setOntologyListTab('sources');
    setSourcesWorkMode('build');
    const meta = $('kgSourceMeta');
    if (meta) { meta.textContent = ''; meta.hidden = true; }
  }
  function showSourcesLibrary() { showOntologyHome(); }
  function enterSourcesWork(mode, focusId) {
    setSkillsCreateMode(false, false);
    setSourcesWorkMode(mode);
    if (!focusId) return;
    window.setTimeout(function () {
      const focusEl = $(focusId);
      if (focusEl && typeof focusEl.focus === 'function') focusEl.focus();
    }, 80);
  }
  $('kgTabBuild')?.addEventListener('click', function () {
    setSourcesWorkMode('build');
    setOntologyListOpen(false);
  });
  $('kgTabRefine')?.addEventListener('click', function () {
    setSourcesWorkMode('refine');
    setOntologyListOpen(false);
  });
  $('kgOntologyListToggle')?.addEventListener('click', toggleOntologyList);
  $('kgOntologyListTabs')?.addEventListener('click', function (event) {
    const button = event.target.closest('[data-ontology-list-tab]');
    if (!button) return;
    setOntologyListOpen(true);
    setOntologyListTab(button.getAttribute('data-ontology-list-tab'));
  });
  async function openSource(id) {
    if (!id) return;
    if (state.pdfDirty && !window.confirm(id === state.source ? 'PDF has unsaved changes. Discard and reload?' : 'PDF has unsaved changes. Discard and switch Data Source?')) {
      if ($('kgRefineSource')) $('kgRefineSource').value = state.source;
      return;
    }
    const source = state.sources.find(function (item) { return sourceId(item) === id; });
    if (!source) { status('kgRefineFile', 'Data Source does not exist or is not in the current group', 'error'); return; }
    const token = ++state.routeToken;
    state.source = id;
    state.refinePicked = id;
    state.refineStep = 'work';
    state.kind = source.kind || source.file_type || 'excel';
    state.pdfDirty = false;
    state.pdfPreviewTriples = null;
    clearPdfCasePreview();
    cancelBusy('kgPdfEvalBtn', true); cancelBusy('kgPdfCasePreviewBtn', true);
    setSkillsCreateMode(false, false);
    setSourcesWorkMode('refine', false);
    const section = $('kgRefineSection');
    if (section) section.setAttribute('data-refine-step', 'work');
    const workBubble = $('kgRefineWorkBubble');
    if (workBubble) workBubble.hidden = false;
    if ($('kgRefineSource')) $('kgRefineSource').value = id;
    if ($('kgRefineEmpty')) $('kgRefineEmpty').hidden = true;
    $('kgExcelPanel').hidden = true;
    $('kgPdfPanel').hidden = true;
    status('kgRefineFile', 'Loading ' + (source.name || id), 'building');
    syncRefineGuide();
    setHash({ tab: 'refine', source: id, record: '' });
    try {
      if (state.kind === 'pdf') await openPdf(id, token);
      else await openExcel(id, token);
      if (token === state.routeToken) { status('kgRefineFile', ''); updateDirty(); persistCurrentSession(); }
    } catch (error) { if (token === state.routeToken) status('kgRefineFile', error.message, 'error'); }
    const stream = section && section.querySelector('.ontology-message-stream');
    if (stream) window.requestAnimationFrame(function () { stream.scrollTop = stream.scrollHeight; });
  }
  async function fetchRows(id) { return get('/api/kg/excel/rows?source=' + encodeURIComponent(id)); }
  async function openExcel(id, token) {
    let doc = state.excel.get(id);
    if (!doc) { doc = await fetchRows(id); doc.cases = (doc.cases || []).map(function (row) { row.triples = (row.triples || []).map(normalizeTriple); return row; }); state.excel.set(id, doc); }
    if (token !== state.routeToken) return;
    $('kgExcelPanel').hidden = false;
    const routeRow = new URLSearchParams(window.location.hash.split('?')[1] || '').get('row');
    const index = doc.cases.findIndex(function (row) { return String(row.row) === routeRow; });
    state.row = index < 0 ? 0 : index;
    const fileName = doc.file_name || (doc.source && doc.source.name) || 'Excel';
    const skill = doc.skill || doc.matched_skill;
    const skillText = skill ? 'Skill · ' + (skill.name || skill.skill_id || skill) : '';
    const meta = $('kgSourceMeta');
    if (meta) {
      meta.textContent = [fileName, skillText].filter(Boolean).join(' · ');
      meta.hidden = !meta.textContent;
    }
    state.highlighted.clear();
    renderCaseList(); renderRow(); await loadExcelGraph();
  }
  function caseStatusLabel(row) {
    if (row._dirty) return 'Unsaved';
    if (row.status === 'skipped') return 'Skipped';
    if (row.reviewed) return 'Reviewed';
    return 'Pending review';
  }
  function renderCaseList() {
    const doc = currentExcel();
    const select = $('kgCaseSelect');
    if (!doc || !select) return;
    select.innerHTML = doc.cases.map(function (row, index) {
      const label = (row.row != null ? row.row : (index + 1)) + '  ' + (row.case_name || 'Untitled case') + '  ·  ' + caseStatusLabel(row);
      return '<option value="' + index + '"' + (index === state.row ? ' selected' : '') + '>' + esc(label) + '</option>';
    }).join('') || '<option value="">No cases</option>';
    select.value = String(state.row);
  }
  function tripleEditor(triples, type) {
    return '<div class="table-scroll"><table class="triple-editor"><thead><tr><th>Keep</th><th>Head</th><th>Relation</th><th>Tail</th></tr></thead><tbody>' + triples.map(function (triple, index) {
      return '<tr class="' + (triple.keep === false ? 'is-skipped' : '') + '"><td><input type="checkbox" data-triple-index="' + index + '" data-field="keep" ' + (triple.keep !== false ? 'checked' : '') + ' aria-label="Keep relation ' + (index + 1) + '"></td>' + ['head', 'relation', 'tail'].map(function (field) { return '<td><input data-triple-index="' + index + '" data-field="' + field + '" value="' + esc(triple[field]) + '" aria-label="' + (field === 'head' ? 'Head' : field === 'relation' ? 'Relation' : 'Tail') + ' ' + (index + 1) + '"></td>'; }).join('') + '</tr>';
    }).join('') + '</tbody></table></div>';
  }
  function historyMarkup(history, restore) {
    if (!history || !history.length) return '<p class="empty-state">No change history</p>';
    return history.slice().reverse().map(function (item, reversedIndex) {
      const index = history.length - 1 - reversedIndex;
      const before = index > 0 ? history[index - 1].triples || [] : [];
      const after = item.triples || [];
      const previous = new Set(before.map(tripleKey)); const next = new Set(after.map(tripleKey));
      const added = item.diff && item.diff.add ? item.diff.add.records || [] : after.filter(function (triple) { return !previous.has(tripleKey(triple)); });
      const removed = item.diff && item.diff.remove ? item.diff.remove.records || [] : before.filter(function (triple) { return !next.has(tripleKey(triple)); });
      const changes = added.map(function (triple) { return '<div class="added">Added · ' + esc(tripleText(triple)) + '</div>'; }).concat(removed.map(function (triple) { return '<div class="removed">Removed · ' + esc(tripleText(triple)) + '</div>'; })).join('');
      return '<div class="history-item"><div class="inline-actions"><strong>v' + esc(item.review_version || item.version || '-') + '</strong> <small>' + esc(formatDate(item.updated_at || item.created_at)) + '</small>' + (restore ? '<button data-restore-version="' + esc(item.version) + '" class="icon-button" title="Restore this version" aria-label="Restore version ' + esc(item.version) + '">' + icon('history') + '</button>' : '') + '</div><p>' + esc(item.summary || statuses[item.status] || item.action || 'Review saved') + '</p><details><summary>Added ' + added.length + ' / Removed ' + removed.length + '</summary>' + (changes || '<span class="muted">Triples unchanged</span>') + '</details></div>';
    }).join('');
  }
  function renderRow() {
    const doc = currentExcel(); const row = currentCase();
    $('kgReextractPreview').hidden = true;
    if (!row) {
      $('kgRowEditor').innerHTML = '<p class="empty-state">No reviewable cases</p>';
      $('kgRowIndex').textContent = '0 / 0';
      renderCaseList();
      return;
    }
    $('kgRowIndex').textContent = (state.row + 1) + ' / ' + doc.cases.length + ' rows';
    $('kgRowPrev').disabled = state.row === 0; $('kgRowNext').disabled = state.row === doc.cases.length - 1;
    $('kgRowEditor').innerHTML = '<div class="case-original"><p><b>' + esc(row.case_type) + '</b></p><p>Preconditions: ' + esc((row.preconditions || []).join('; ')) + '</p><p>Actions: ' + esc(row.step) + '</p><p>Expected Behavior: ' + esc(row.expectation) + '</p></div>' + tripleEditor(row.triples, 'excel');
    renderCaseList();
    $('kgRowSummary').value = row.summary || '';
    $('kgRowHint').value = row._hint || '';
    $('kgRowHistoryList').innerHTML = historyMarkup(row.history || row.review_history);
    $('kgRowEditor').querySelectorAll('[data-triple-index]').forEach(function (input) { input.addEventListener('input', function () { const triple = row.triples[Number(input.dataset.tripleIndex)]; triple[input.dataset.field] = input.dataset.field === 'keep' ? input.checked : input.value; input.closest('tr').classList.toggle('is-skipped', triple.keep === false); markRowDirty(row); }); });
    setHash({ tab: 'refine', source: state.source, row: row.row, record: '' });
  }
  function markRowDirty(row) { row._dirty = true; row._editRevision = (row._editRevision || 0) + 1; updateDirty(); renderCaseList(); }
  $('kgRowSummary').addEventListener('input', function () { const row = currentCase(); if (row) { row.summary = this.value; markRowDirty(row); } });
  $('kgRowHint').addEventListener('input', function () { const row = currentCase(); if (row) row._hint = this.value; });
  $('kgExcelPanel')?.addEventListener('change', function (event) {
    if (!event.target || event.target.id !== 'kgCaseSelect') return;
    const next = Number(event.target.value);
    if (!Number.isFinite(next)) return;
    state.row = next;
    renderRow();
    renderExcelGraph();
  });
  $('kgRowPrev').addEventListener('click', function () { if (state.row > 0) { state.row--; renderRow(); renderExcelGraph(); } });
  $('kgRowNext').addEventListener('click', function () { const doc = currentExcel(); if (doc && state.row < doc.cases.length - 1) { state.row++; renderRow(); renderExcelGraph(); } });
  $('kgRowAdd').addEventListener('click', function () { const row = currentCase(); if (row) { row.triples.push({ head: '', relation: '', tail: '', keep: true }); markRowDirty(row); renderRow(); } });
  async function saveRow(row, source) {
    const doc = state.excel.get(source);
    const editRevision = row._editRevision || 0;
    const kept = row.triples.filter(function (triple) { return triple.keep !== false; });
    if (!kept.length && row.status !== 'skipped') throw new Error('No kept relations on this row. If the row is not needed, mark it as skipped.');
    if (row.status !== 'skipped' && kept.some(function (triple) { return !triple.head.trim() || !triple.relation.trim() || !triple.tail.trim(); })) throw new Error('Row ' + row.row + ' has empty entities or relations');
    await post('/api/kg/excel/row/save', { domain: doc.domain, source: source, source_version: doc.source ? doc.source.version : doc.version, row: row.row, triples: row.triples, summary: row.summary || '', status: row.status === 'skipped' ? 'skipped' : 'reviewed', allow_empty: row.status === 'skipped', review_version: row.review_version == null ? 0 : row.review_version });
    const fresh = await fetchRows(source);
    const saved = fresh.cases.find(function (candidate) { return candidate.row === row.row; });
    if (!saved) throw new Error('Row not found after save; please reload the Data Source');
    const index = doc.cases.findIndex(function (candidate) { return candidate.row === row.row; });
    saved.triples = (saved.triples || []).map(normalizeTriple); saved._dirty = false; saved._hint = row._hint;
    if ((row._editRevision || 0) === editRevision) doc.cases[index] = saved;
    else { row.review_version = saved.review_version; row.history = saved.history; row.reviewed = true; }
  }
  $('kgRowSave').addEventListener('click', function () { busy('kgRowSave', 'kgRefineFile', async function () { const row = currentCase(); const source = state.source; if (!row) return; status('kgRefineFile', 'Saving row ' + row.row, 'building'); await saveRow(row, source); updateDirty(); renderCaseList(); renderRow(); await loadExcelGraph(); await loadSources(); await app.refreshGraph(); status('kgRefineFile', 'Row ' + row.row + ' saved and reloaded.'); }); });
  $('kgRowsSave').addEventListener('click', function () { busy('kgRowsSave', 'kgRefineFile', async function () { const source = state.source; const doc = currentExcel(); if (!doc) return; const dirty = doc.cases.filter(function (row) { return row._dirty; }); for (const row of dirty) await saveRow(row, source); updateDirty(); renderCaseList(); renderRow(); await loadExcelGraph(); await loadSources(); await app.refreshGraph(); status('kgRefineFile', 'Saved ' + dirty.length + ' rows.'); }); });
  $('kgRowReextract').addEventListener('click', function () { busy('kgRowReextract', 'kgRefineFile', async function () {
    const row = currentCase(); const doc = currentExcel(); if (!row) return;
    const source = state.source; const rowNumber = row.row;
    status('kgRefineFile', 'AI is re-extracting the current row', 'building');
    const data = await post('/api/kg/excel/row/reextract', { source: source, source_version: doc.source ? doc.source.version : doc.version, row: row.row, domain: doc.domain, hint: $('kgRowHint').value.trim(), row_data: { name: row.case_name, type: row.case_type, preconditions: (row.preconditions || []).join('; '), step: row.step, expectation: row.expectation }, existing_triples: row.triples.filter(function (triple) { return triple.keep !== false; }).map(function (triple) { return [triple.head, triple.relation, triple.tail]; }) });
    if (state.source !== source || !currentCase() || currentCase().row !== rowNumber) { status('kgRefineFile', 'Re-extract finished. Case changed; return to the original row to retry.'); return; }
    const triples = (data.triples || []).map(normalizeTriple);
    if (!triples.length) throw new Error('AI returned no valid triples; current edits kept');
    $('kgReextractPreview').innerHTML = '<div class="table-scroll">' + triplesTable(triples, 'AI re-extract suggestion') + '</div><div class="inline-actions"><button id="kgReextractAccept" class="primary-button">Apply suggestion</button><button id="kgReextractDismiss" class="kg-workbench-button">Discard suggestion</button></div>';
    $('kgReextractPreview').hidden = false;
    $('kgReextractAccept').addEventListener('click', function () { row.triples = triples; markRowDirty(row); renderRow(); status('kgRefineFile', 'Re-extract suggestion loaded; not saved yet.'); });
    $('kgReextractDismiss').addEventListener('click', function () { $('kgReextractPreview').hidden = true; });
    status('kgRefineFile', 'Re-extract done; waiting to confirm suggestion.');
  }); });
  async function loadExcelGraph() {
    const doc = currentExcel(); if (!doc) return;
    try { const data = await get('/api/kg/excel/graph?' + new URLSearchParams({ domain: doc.domain, source: state.source })); state.graphEdges = (data.edges || []).map(normalizeTriple); renderExcelGraph(); }
    catch (error) { $('kgExcelGraph').innerHTML = '<p class="notice" data-state="error">' + esc(error.message) + '</p>'; }
  }
  function selectedRows() { const doc = currentExcel(); if (!doc) return []; const scope = $('kgGraphScope').value; return scope === 'all' ? doc.cases : scope === 'selected' ? doc.cases.filter(function (_, index) { return state.highlighted.has(index); }) : currentCase() ? [currentCase()] : []; }
  function renderExcelGraph() {
    const highlights = new Set(selectedRows().flatMap(function (row) { return row.triples.filter(function (triple) { return triple.keep !== false; }).map(tripleKey); }));
    const edges = state.graphEdges;
    if (state.graph) { state.graph.destroy(); state.graph = null; }
    if (!edges.length) { $('kgExcelGraph').innerHTML = '<p class="empty-state">No confirmed relations</p>'; $('kgExcelGraphDetails').textContent = ''; return; }
    $('kgExcelGraph').innerHTML = '';
    if (!window.vis) { $('kgExcelGraph').innerHTML = '<p class="notice" data-state="error">Graph component failed to load</p>'; return; }
    const nodes = new Map(); const active = new Set();
    edges.forEach(function (edge) { nodes.set(edge.head, edge.head); nodes.set(edge.tail, edge.tail); if (highlights.has(tripleKey(edge))) { active.add(edge.head); active.add(edge.tail); } });
    state.graph = new vis.Network($('kgExcelGraph'), { nodes: Array.from(nodes.keys()).map(function (name) { return { id: name, label: name.length > 22 ? name.slice(0, 22) + '…' : name, title: name, shape: 'dot', size: active.has(name) ? 12 : 6, color: active.has(name) ? '#168278' : '#cdd6d5', font: { size: 11, color: active.has(name) ? '#233d37' : '#7d8987' } }; }), edges: edges.map(function (edge, index) { const selected = highlights.has(tripleKey(edge)); return { id: index, from: edge.head, to: edge.tail, label: selected ? edge.relation : '', title: edge.relation, arrows: 'to', color: selected ? '#168278' : '#dfe6e4', width: selected ? 2 : 1, font: { size: 10, color: '#147d74', strokeWidth: 0 } }; }) }, { layout: { improvedLayout: true }, physics: { stabilization: { iterations: 120 }, barnesHut: { springLength: 130, gravitationalConstant: -1800 } }, interaction: { hover: true }, edges: { smooth: false } });
    state.graph.once('stabilizationIterationsDone', function () { if (state.graph) state.graph.setOptions({ physics: false }); });
    state.graph.on('click', function (event) { if (event.nodes.length) { const name = event.nodes[0]; const related = edges.filter(function (edge) { return edge.head === name || edge.tail === name; }); $('kgExcelGraphDetails').textContent = related.map(tripleText).join('; '); } else if (event.edges.length) { $('kgExcelGraphDetails').textContent = tripleText(edges[event.edges[0]]); } });
    $('kgExcelGraphDetails').textContent = 'Confirmed ' + edges.length + ' relations · Highlighted ' + edges.filter(function (edge) { return highlights.has(tripleKey(edge)); }).length
  }
  $('kgGraphScope').addEventListener('change', renderExcelGraph);
  async function exportExcel(highlight) {
    const doc = currentExcel(); if (!doc) return;
    if (doc.cases.some(function (row) { return row._dirty; })) throw new Error('Data Source has unsaved changes; save before export');
    const rows = selectedRows().map(function (row) { return row.row; });
    if (highlight && !rows.length) throw new Error('Select cases to highlight for export first');
    const body = { domain: doc.domain, source: state.source }; if (highlight) body.rows = rows;
    const data = await post('/api/kg/excel/export', body);
    if (!data.url) throw new Error('Export did not return a download URL');
    const link = document.createElement('a'); link.href = data.url; link.download = data.filename || 'refined.json'; document.body.appendChild(link); link.click(); link.remove(); status('kgRefineFile', 'Exported and archived ' + (data.total == null ? '' : data.total + ' relations') + '.');
  }
  $('kgExcelExport').addEventListener('click', function () { busy('kgExcelExport', 'kgRefineFile', function () { return exportExcel(false); }); });
  $('kgExcelExportSelected').addEventListener('click', function () { busy('kgExcelExportSelected', 'kgRefineFile', function () { return exportExcel(true); }); });
  async function openPdf(id, token) {
    const data = await get('/api/kg/pdf/images?doc=' + encodeURIComponent(id)); if (token !== state.routeToken) return;
    $('kgPdfPanel').hidden = false;
    const source = state.sources.find(function (item) { return sourceId(item) === id; });
    const meta = $('kgSourceMeta');
    if (meta) {
      meta.textContent = (source && source.name) || id || 'PDF';
      meta.hidden = !meta.textContent;
    }
    $('kgPdfImage').innerHTML = (data.images || []).map(function (record) { return '<option value="' + esc(record.image_id) + '">' + esc(record.image_id) + ' · ' + (record.triple_count || 0) + ' relations</option>'; }).join('');
    const routeImage = new URLSearchParams(window.location.hash.split('?')[1] || '').get('record');
    if (routeImage && (data.images || []).some(function (record) { return record.image_id === routeImage; })) $('kgPdfImage').value = routeImage;
    if ($('kgPdfImage').value) await loadPdfRecord();
    else clearPdfRecord();
  }
  async function loadPdfRecord() {
    const source = state.source; const image = $('kgPdfImage').value;
    clearPdfRecord();
    const data = await get('/api/kg/pdf/image?' + new URLSearchParams({ doc: source, img: image }));
    if (source !== state.source || image !== $('kgPdfImage').value) return;
    state.pdf = data; state.pdf.triples = (data.reviewed_triples == null ? data.triples || [] : data.reviewed_triples).map(function (triple, index) {
      const normalized = normalizeTriple(triple);
      const previewId = data.preview_triple_ids && data.preview_triple_ids[index];
      const sourceTripleId = (data.preview_source_triple_ids && data.preview_source_triple_ids[index]) || normalized.source_triple_id || normalized.id || normalized.triple_id;
      const sourceOccurrence = data.preview_source_triple_occurrences && data.preview_source_triple_occurrences[index];
      if (previewId) {
        if (sourceTripleId && sourceTripleId !== previewId) normalized.source_triple_id = sourceTripleId;
        if (Number.isInteger(sourceOccurrence) && sourceOccurrence >= 0) normalized.source_triple_occurrence = sourceOccurrence;
        normalized.pdf_record_id = previewId;
        normalized.triple_id = previewId;
      }
      return normalized;
    });
    state.pdf.img = image; state.pdfPreviewTriples = null; state.pdfDirty = false; state.pdfEvaluation = null; clearPdfCasePreview();
    cancelBusy('kgPdfEvalBtn', false); cancelBusy('kgPdfCasePreviewBtn', false);
    $('kgPdfEval').innerHTML = ''; $('kgPdfCorrections').innerHTML = ''; $('kgPdfPreview').hidden = true; $('kgPdfApplyBtn').disabled = true;
    $('kgPdfVersion').textContent = 'v' + (data.review_version || 0) + (data.reviewed ? ' · Reviewed' : ' · Pending review');
    $('kgPdfTriples').innerHTML = triplesTable(state.pdf.triples, 'Triples');
    $('kgPdfOcr').textContent = (data.ocr_terms || []).map(function (term) { return typeof term === 'string' ? term : JSON.stringify(term); }).join(' · ') + '\n\n' + (typeof data.description === 'string' ? data.description : JSON.stringify(data.description || {}, null, 2));
    $('kgPdfHistory').innerHTML = (data.review_version ? '<div class="inline-actions"><button data-restore-version="0">' + icon('rotate-ccw') + 'Restore original extraction</button><button data-restore-version="' + (data.review_version - 1) + '">' + icon('undo-2') + 'Undo latest change</button></div>' : '') + historyMarkup(data.history || data.review_history, true);
    $('kgPdfHistory').querySelectorAll('[data-restore-version]').forEach(function (button) { button.addEventListener('click', async function () {
      const version = Number(button.dataset.restoreVersion);
      if (!window.confirm('Restore to ' + (version ? 'review version ' + version : 'original extraction') + '? Current content will be saved as history.')) return;
      button.disabled = true;
      try { await post('/api/kg/pdf/restore', { doc: state.source, img: state.pdf.img, source_version: state.pdf.source ? state.pdf.source.version : state.pdf.version, review_version: state.pdf.review_version, restore_version: version }); await loadPdfRecord(); await loadSources(); await app.refreshGraph(); status('kgRefineFile', 'History version restored and reloaded.'); }
      catch (error) { status('kgRefineFile', error.message, 'error'); button.disabled = false; }
    }); });
    app.icons();
    updateDirty(); setHash({ record: image, row: '' });
  }
  $('kgPdfImage').addEventListener('change', async function () {
    if (state.pdfDirty && !window.confirm('There are unapplied corrections. Discard and switch records?')) { this.value = state.pdf.img; return; }
    const image = this.value;
    status('kgRefineFile', 'Loading ' + image, 'building');
    try {
      await loadPdfRecord();
      if (state.pdf && state.pdf.img === image && this.value === image) status('kgRefineFile', '');
    } catch (error) { if (this.value === image) status('kgRefineFile', error.message, 'error'); }
  });
  $('kgPdfCasePreviewBtn').addEventListener('click', function () { busy('kgPdfCasePreviewBtn', 'kgRefineFile', async function () {
    if (!state.pdf) throw new Error('Please select a content record first');
    const source = state.source; const image = state.pdf.img;
    const sourceVersion = state.pdf.source ? state.pdf.source.version : state.pdf.version;
    const reviewVersion = state.pdf.review_version || 0;
    clearPdfCasePreview(); const previewToken = state.pdfCasePreviewToken;
    // Quality corrections are editable before they are applied. Project the
    // in-memory triples in that state so the strict preview matches the table
    // the reviewer is actually looking at; otherwise use the persisted GET.
    const data = state.pdfDirty
      ? await post('/api/kg/pdf/test-cases/preview', {
        doc: source,
        img: image,
        source_version: sourceVersion,
        review_version: reviewVersion,
        triples: clone(state.pdfPreviewTriples || state.pdf.triples),
      })
      : await get('/api/kg/pdf/test-cases?' + new URLSearchParams({ doc: source, img: image, source_version: sourceVersion, review_version: reviewVersion }));
    if (previewToken !== state.pdfCasePreviewToken || source !== state.source || !state.pdf || state.pdf.img !== image || Number(sourceVersion) !== Number(state.pdf.source ? state.pdf.source.version : state.pdf.version) || Number(reviewVersion) !== Number(state.pdf.review_version || 0)) return;
    renderPdfCasePreview(data);
    status('kgRefineFile', state.pdfDirty ? 'Auto scenario split done from current unsaved relations; not published yet.' : 'Auto scenario split completed; not published yet.');
  }).then(syncPdfActionButtons); });
  function selectedCorrections() { return Array.from($('kgPdfCorrections').querySelectorAll('[data-correction]:checked')).map(function (input) { return Number(input.dataset.correction); }); }
  function correctionTriple(value) {
    const normalized = normalizeTriple(value || {});
    return { head: normalized.head, relation: normalized.relation, tail: normalized.tail, keep: normalized.keep };
  }
  function correctionMatch(triples, previous) {
    if (!previous) return -1;
    const recordId = previous.pdf_record_id || previous.triple_id;
    if (recordId) return triples.findIndex(function (triple) { return (triple.pdf_record_id || triple.triple_id) === recordId; });
    const matches = triples.map(function (triple, index) { return tripleKey(triple) === tripleKey(previous) ? index : -1; }).filter(function (index) { return index >= 0; });
    return matches.length === 1 ? matches[0] : -1;
  }
  function pdfPreview() {
    if (!state.pdf || !state.pdfEvaluation) return;
    const selected = selectedCorrections(); let triples = clone(state.pdf.triples);
    selected.forEach(function (index) {
      const correction = state.pdfEvaluation.corrections[index]; const action = correction.action;
      const previous = correction.old_triple || correction.original || correction.triple;
      const next = correction.new_triple || correction.corrected || correction.triple;
      const match = correctionMatch(triples, previous);
      if (['delete', 'remove'].includes(action)) { if (match >= 0) triples.splice(match, 1); }
      else if (['add', 'insert'].includes(action)) { if (next) triples.push(correctionTriple(next)); }
      else if (['modify', 'update', 'replace', 'correct'].includes(action) && match >= 0 && next) {
        const replacement = Object.assign({}, triples[match], correctionTriple(next));
        replacement.pdf_record_id = triples[match].pdf_record_id || triples[match].triple_id;
        replacement.triple_id = replacement.pdf_record_id;
        triples[match] = replacement;
      }
    });
    state.pdfPreviewTriples = triples;
    state.pdfDirty = selected.length > 0; updateDirty();
    clearPdfCasePreview();
    cancelBusy('kgPdfCasePreviewBtn', false);
    $('kgPdfApplyBtn').disabled = !selected.length || !triples.length;
    $('kgPdfPreview').hidden = !selected.length;
    $('kgPdfPreview').innerHTML = '<div class="section-heading"><h3>Change preview <span class="count">' + state.pdf.triples.length + ' → ' + triples.length + ' relations</span></h3></div><div class="table-scroll">' + triplesTable(triples) + '</div>' + (!triples.length ? '<p class="notice" data-state="error">This selection would clear all triples and cannot be applied.</p>' : '');
  }
  $('kgPdfEvalBtn').addEventListener('click', function () { busy('kgPdfEvalBtn', 'kgRefineFile', async function () {
    if (!state.pdf) throw new Error('Please select a content record first');
    const source = state.source; const image = state.pdf.img;
    status('kgRefineFile', 'Evaluating current record', 'building');
    const data = await post('/api/kg/pdf/eval', { doc: source, img: image, source_version: state.pdf.source ? state.pdf.source.version : state.pdf.version });
    if (source !== state.source || !state.pdf || state.pdf.img !== image) return;
    state.pdfEvaluation = data; data.corrections = data.corrections || [];
    const scores = [['overall_score', 'Overall'], ['ocr_completeness', 'OCR'], ['description_accuracy', 'Description'], ['triple_precision', 'Precision'], ['triple_recall', 'Recall']];
    $('kgPdfEval').innerHTML = '<div class="pdf-scores">' + scores.map(function (score) { return '<div><b>' + esc(data[score[0]] == null ? '-' : data[score[0]]) + '</b><span>' + score[1] + '</span></div>'; }).join('') + '</div>' + (data.issues || []).map(function (issue) { return '<div class="pdf-issue"><span class="status-badge ' + (issue.severity === 'critical' ? 'error' : 'warning') + '">' + esc(({ critical: 'Critical', major: 'Major', minor: 'Minor' })[issue.severity] || issue.severity) + '</span><span>' + esc(issue.description || issue.issue_type) + '</span></div>'; }).join('');
    $('kgPdfCorrections').innerHTML = '<div class="section-heading"><h3>Correction suggestions <span class="count">' + data.corrections.length + '</span></h3></div>' + (data.corrections.length ? data.corrections.map(function (correction, index) { return '<label class="correction-item"><input type="checkbox" data-correction="' + index + '"><span><p><strong>' + esc(({ add: 'Add', insert: 'Add', remove: 'Remove', delete: 'Remove', modify: 'Modify', update: 'Modify', replace: 'Replace' })[correction.action] || correction.action) + '</strong> · ' + esc(correction.reason || '') + '</p><span class="correction-values"><span class="removed">' + esc(tripleText(correction.old_triple || correction.original)) + '</span><span class="added">' + esc(tripleText(correction.new_triple || correction.corrected || correction.triple)) + '</span></span></span></label>'; }).join('') : '<p class="empty-state">No corrections to apply</p>');
    $('kgPdfCorrections').querySelectorAll('[data-correction]').forEach(function (input) { input.addEventListener('change', pdfPreview); });
    status('kgRefineFile', 'Quality evaluation completed.');
  }).then(syncPdfActionButtons); });
  $('kgPdfApplyBtn').addEventListener('click', function () { busy('kgPdfApplyBtn', 'kgRefineFile', async function () {
    const selected = selectedCorrections(); if (!state.pdf || !state.pdfEvaluation || !selected.length) throw new Error('Please select correction suggestions first');
    await post('/api/kg/pdf/apply', { doc: state.source, img: state.pdf.img, source_version: state.pdf.source ? state.pdf.source.version : state.pdf.version, triples: state.pdf.triples, review_version: state.pdf.review_version || 0, selected_corrections: selected, evaluation_id: state.pdfEvaluation.evaluation_id });
    await loadPdfRecord(); await loadSources(); await app.refreshGraph(); status('kgRefineFile', 'Selected corrections applied and reloaded.');
  }).then(function () { $('kgPdfApplyBtn').disabled = !state.pdfDirty; }); });
  function scrollSkillStream() {
    const stream = document.querySelector('.skill-message-stream');
    if (stream) stream.scrollTop = stream.scrollHeight;
  }
  function renderChat(role, text, options) {
    const opts = options || {};
    const row = document.createElement('article');
    const isUser = role === 'user';
    row.className = 'skill-msg skill-msg-' + (isUser ? 'user' : 'ai') + (opts.loading ? ' is-loading' : '');
    if (opts.id) row.id = opts.id;
    if (isUser) {
      const bubble = document.createElement('div');
      bubble.className = 'skill-msg-user-bubble';
      bubble.textContent = text;
      row.appendChild(bubble);
    } else {
      const block = document.createElement('div');
      block.className = 'skill-msg-ai-block';
      const label = document.createElement('div');
      label.className = 'skill-msg-label';
      label.innerHTML = '<span>Skill Assistant</span><small>' + (opts.loading ? 'Thinking' : 'Ready') + '</small>';
      const bubble = document.createElement('div');
      bubble.className = 'skill-msg-ai-bubble';
      bubble.textContent = text;
      block.append(label, bubble);
      row.appendChild(block);
    }
    $('kgSkillChatLog').appendChild(row);
    scrollSkillStream();
    return row;
  }
  function resetChat() {
    state.messages = [];
    state.conversationId = null;
    $('kgSkillChatLog').innerHTML = '';
    $('kgSkillChatDraft').hidden = true;
    $('kgSkillChatDraft').innerHTML = '';
    $('kgSkillChatInput').value = '';
    resizeSkillComposer();
    syncSkillSendEnabled();
    status('kgSkillStatus', '');
    renderChat('ai', 'What file types should this Skill handle, and which entities and relations should it extract?');
  }
  const draftLabels = {
    name: 'Name',
    function_desc: 'Description',
    audience: 'Audience',
    input_req: 'Input requirements',
    output_result: 'Output',
    scenario: 'Scenarios',
    steps: 'Steps',
    limits: 'Limits & exceptions',
    example: 'Example'
  };
  const draftFieldOrder = ['name', 'function_desc', 'audience', 'input_req', 'output_result', 'scenario', 'steps', 'limits', 'example'];
  function formatDraftValue(value) {
    if (value == null) return '';
    if (typeof value === 'string') return value;
    if (Array.isArray(value)) return value.map(function (item, index) { return (index + 1) + '.' + item; }).join('\n');
    return JSON.stringify(value, null, 2);
  }
  function collectDraftEdits(base) {
    const next = Object.assign({}, base || {});
    document.querySelectorAll('#kgSkillChatDraft [data-draft-field]').forEach(function (el) {
      const key = el.getAttribute('data-draft-field');
      if (!key) return;
      next[key] = (el.value || '').trim();
    });
    if (next.name) next.description = next.function_desc || next.description || next.name;
    return next;
  }
  function fitDraftEditCell(el) {
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = Math.max(36, el.scrollHeight) + 'px';
  }
  function bindDraftEditCells() {
    document.querySelectorAll('#kgSkillChatDraft .draft-edit-cell').forEach(function (el) {
      fitDraftEditCell(el);
      el.addEventListener('input', function () { fitDraftEditCell(el); });
    });
  }
  function renderDraft(draft) {
    $('kgSkillChatDraft').hidden = false;
    const fields = draftFieldOrder.filter(function (field) { return draft[field] != null && String(draft[field]).trim() !== ''; });
    const rows = fields.map(function (field) {
      const label = esc(draftLabels[field] || field);
      const value = esc(formatDraftValue(draft[field]));
      return '<tr><th scope="row">' + label + '</th><td><textarea class="draft-edit-cell" data-draft-field="' + esc(field) + '" rows="1" aria-label="' + label + '">' + value + '</textarea></td></tr>';
    }).join('');
    $('kgSkillChatDraft').innerHTML = '<div class="draft-preview"><h3>Draft pending confirmation</h3><div class="draft-table-wrap"><table class="draft-edit-table"><tbody>' + rows + '</tbody></table></div><div class="inline-actions draft-actions"><button id="kgDraftConfirm" class="primary-button" type="button">Submit Pending Review version</button></div></div>';
    bindDraftEditCells();
    $('kgDraftConfirm').addEventListener('click', function () {
      busy('kgDraftConfirm', 'kgSkillStatus', async function () {
        const payload = collectDraftEdits(draft);
        const data = await post('/api/kg/skills/draft', Object.assign({}, payload, { confirmed: true }));
        $('kgSkillChatDraft').hidden = true;
        renderChat('ai', 'Submitted Pending Review version “' + (data.name || payload.name) + '”. View it under Pending Review Skills on the right.');
        state.skillsLoaded = false;
        await loadSkills();
        setSkillsCreateMode(false, false);
        setSkillsListTab('pending');
      });
    });
    scrollSkillStream();
  }
  async function sendChat() {
    const text = $('kgSkillChatInput').value.trim(); if (!text || state.chatBusy) return;
    state.chatBusy = true; syncSkillSendEnabled();
    const messages = state.messages.concat([{ role: 'user', content: text }]);
    renderChat('user', text);
    $('kgSkillChatInput').value = '';
    resizeSkillComposer();
    status('kgSkillStatus', '');
    $('kgSkillChatDraft').hidden = true;
    const loading = renderChat('ai', 'Thinking…', { loading: true, id: 'kgSkillChatLoading' });
    try {
      const data = await post('/api/kg/skills/chat', state.conversationId ? { conversation_id: state.conversationId, message: text, messages: messages } : { messages: messages });
      state.conversationId = data.conversation_id || state.conversationId;
      const reply = data.reply || '';
      state.messages = messages.concat([{ role: 'assistant', content: reply }]);
      if (loading && loading.parentNode) loading.parentNode.removeChild(loading);
      renderChat('ai', reply || (data.draft ? 'Draft generated for confirmation' : 'Please continue with more requirements.'));
      if (data.draft) renderDraft(data.draft);
      if (data.stage === 'clarify') $('kgSkillChatInput').focus();
    } catch (error) {
      if (loading && loading.parentNode) loading.parentNode.removeChild(loading);
      status('kgSkillStatus', error.message + '. Message restored; you can resend.', 'error');
      $('kgSkillChatInput').value = text;
      resizeSkillComposer();
      renderChat('ai', 'Request failed: ' + error.message + '. Edit and retry.');
    } finally {
      state.chatBusy = false;
      syncSkillSendEnabled();
    }
  }
  function resizeSkillComposer() {
    const input = $('kgSkillChatInput');
    if (!input) return;
    input.style.height = '0px';
    const next = Math.min(150, Math.max(24, input.scrollHeight));
    input.style.height = next + 'px';
  }
  function syncSkillSendEnabled() {
    const send = $('kgSkillChatSend');
    const input = $('kgSkillChatInput');
    if (!send || !input) return;
    send.disabled = state.chatBusy || !input.value.trim();
  }
  $('kgSkillChatSend').addEventListener('click', sendChat);
  $('kgSkillChatInput').addEventListener('keydown', function (event) {
    if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      sendChat();
    }
  });
  $('kgSkillChatInput').addEventListener('input', function () {
    resizeSkillComposer();
    syncSkillSendEnabled();
  });
  resizeSkillComposer();
  syncSkillSendEnabled();
  function setSkillHash(fields) {
    const params = new URLSearchParams();
    Object.keys(fields || {}).forEach(function (key) {
      if (fields[key] === '' || fields[key] == null) return;
      params.set(key, fields[key]);
    });
    const suffix = params.toString();
    const value = '#skill' + (suffix ? '?' + suffix : '');
    if (window.location.hash !== value) window.history.replaceState(null, '', value);
  }
  function setSkillsCreateMode(active, writeRoute) {
    const next = !!active;
    if (next) setSourcesWorkMode(null, false);
    if (writeRoute !== false) {
      if (next) setSkillHash({ view: 'create' });
      else if ((window.location.hash || '').startsWith('#skill')) setSkillHash({});
    }
    state.skillsCreate = next;
    const sourcesPanel = $('kgSubviewSources');
    if (sourcesPanel) sourcesPanel.classList.remove('is-create-mode');
    const panel = $('kgSkillWorkbench');
    if (panel) panel.classList.remove('is-create-mode');
    const workspace = document.querySelector('.workspace');
    const onSkill = !!document.querySelector('.view-panel.is-visible[data-panel="skill"]')
      || (window.location.hash || '').startsWith('#skill');
    const onOntology = !!document.querySelector('.view-panel.is-visible[data-panel="ontology"]')
      || (window.location.hash || '').startsWith('#ontology');
    if (workspace) {
      workspace.classList.remove('is-skill-create');
      workspace.classList.toggle('is-skill-page', onSkill);
      if (!onSkill && !onOntology) workspace.classList.remove('is-list-dock');
    }
    if (next) {
      if (app.setView && !document.querySelector('.view-panel.is-visible[data-panel="skill"]')) {
        app.setView('skill', false);
      }
    } else {
      ensureSkills();
    }
    setSkillTitleMode(false);
    syncSkillsListToggle();
  }
  function showSkillsLibrary() {
    setSkillsCreateMode(false);
    if (app.setView) app.setView('skill', false);
  }
  function startNewSkill() {
    const hasUserTurns = (state.messages || []).some(function (item) { return item.role === 'user'; });
    if (!state.skillsCreate && hasUserTurns && !window.confirm('Start a new Skill? The current conversation will be cleared.')) {
      syncSkillViewTabs();
      return;
    }
    if (!state.skillsCreate || hasUserTurns) resetChat();
    setSkillsCreateMode(true);
    window.setTimeout(function () {
      const input = $('kgSkillChatInput');
      if (input) input.focus();
    }, 80);
  }
  $('kgSkillListToggle')?.addEventListener('click', toggleSkillsList);
  $('kgCrumbSkillRoot')?.addEventListener('click', showSkillsLibrary);
  let skillFastTipEl = null;
  function hideSkillFastTip() {
    if (!skillFastTipEl) return;
    skillFastTipEl.classList.remove('is-visible');
  }
  function showSkillFastTip(button) {
    const text = button && button.getAttribute('data-tip');
    if (!text) return;
    if (!skillFastTipEl) {
      skillFastTipEl = document.createElement('div');
      skillFastTipEl.className = 'skill-fast-tip';
      skillFastTipEl.setAttribute('role', 'tooltip');
      document.body.appendChild(skillFastTipEl);
    }
    skillFastTipEl.textContent = text;
    const rect = button.getBoundingClientRect();
    const tipWidth = skillFastTipEl.offsetWidth || 48;
    let left = rect.left + rect.width / 2;
    left = Math.max(tipWidth / 2 + 8, Math.min(left, window.innerWidth - tipWidth / 2 - 8));
    let top = rect.bottom + 6;
    skillFastTipEl.style.left = left + 'px';
    skillFastTipEl.style.top = top + 'px';
    // Prefer above when near bottom edge.
    if (top + 28 > window.innerHeight - 8) {
      skillFastTipEl.style.top = Math.max(8, rect.top - 28) + 'px';
    }
    skillFastTipEl.classList.add('is-visible');
  }
  function bindSkillFastTips(root) {
    if (!root) return;
    root.querySelectorAll('[data-tip]').forEach(function (button) {
      button.addEventListener('pointerenter', function () { showSkillFastTip(button); });
      button.addEventListener('pointerleave', hideSkillFastTip);
      button.addEventListener('focus', function () { showSkillFastTip(button); });
      button.addEventListener('blur', hideSkillFastTip);
      button.addEventListener('click', hideSkillFastTip);
    });
  }
  async function loadSkills() {
    try {
      const [skillsData, pendingData, trashData] = await Promise.all([
        get('/api/kg/skills'),
        get('/api/kg/skills/pending').catch(function () { return { drafts: [] }; }),
        get('/api/kg/skills/trash').catch(function () { return { trash: [] }; }),
      ]);
      state.skillItems = skillsData.skills || [];
      state.pendingSkills = pendingData.drafts || pendingData.pending || [];
      state.trashedSkills = trashData.trash || [];
      renderSkillList();
      await refreshTrashBadge();
    } catch (error) {
      $('kgSkillRegistry').innerHTML = '<p class="notice" data-state="error">' + esc(error.message) + '</p>';
    }
    app.icons();
  }
  function setSkillsListTab(tab, render) {
    if (tab === 'pending') state.skillsListTab = 'pending';
    else if (tab === 'trash') state.skillsListTab = 'trash';
    else state.skillsListTab = 'library';
    document.querySelectorAll('#kgSkillsTabs [data-skills-tab]').forEach(function (button) {
      const selected = button.getAttribute('data-skills-tab') === state.skillsListTab;
      button.classList.toggle('is-selected', selected);
      button.setAttribute('aria-selected', selected ? 'true' : 'false');
    });
    const search = $('kgSkillSearch');
    if (search) {
      search.placeholder = state.skillsListTab === 'pending'
        ? 'Name or description'
        : (state.skillsListTab === 'trash' ? 'Name or type' : 'Name, type, or description');
    }
    if (render !== false) renderSkillList();
  }
  function renderSkillList() {
    const tab = state.skillsListTab;
    const isPending = tab === 'pending';
    const isTrash = tab === 'trash';
    const skills = isTrash ? (state.trashedSkills || []) : (isPending ? (state.pendingSkills || []) : (state.skillItems || []));
    const query = (($('kgSkillSearch') && $('kgSkillSearch').value) || '').trim().toLowerCase();
    const filtered = skills.filter(function (skill) {
      if (!query) return true;
      const hay = [skill.name, skill.skill_id, skill.id, skill.file_type, skill.template_kind, skill.description, skill.function_desc, skill.status, skill.filename]
        .filter(Boolean).join(' ').toLowerCase();
      return hay.indexOf(query) !== -1;
    });
    if (!filtered.length) {
      if (isTrash && !skills.length) {
        $('kgSkillRegistry').innerHTML = '<div class="empty-state empty-state-illustration skill-trash-empty"><img src="static/img/trash.svg" alt="" width="141" height="136"><p>Trash is empty</p></div>';
        return;
      }
      $('kgSkillRegistry').innerHTML = '<p class="empty-state">' + (
        isTrash
          ? 'No matching trash Skills'
          : isPending
            ? (skills.length ? 'No matching Pending Review Skills' : 'No Pending Review Skills')
            : (skills.length ? 'No matching Skills' : 'No registered Skills')
      ) + '</p>';
      return;
    }
    if (isTrash) {
      $('kgSkillRegistry').innerHTML = filtered.map(function (skill) {
        const sid = skill.skill_id || skill.id || '';
        const name = skill.name || sid || 'Untitled';
        const typeLabel = [skill.file_type, skill.template_kind].filter(Boolean).join(' · ') || 'skill';
        const desc = skill.description || skill.function_desc || '—';
        const time = formatDate(skill.deleted_at);
        return '<div class="skill-list-row is-trashed">'
          + '<div class="skill-list-main">'
          + '<div class="skill-list-top"><span class="skill-list-name">' + esc(name) + '</span><span class="status-badge warning">Trash</span></div>'
          + '<div class="skill-list-type">' + esc(typeLabel) + (time && time !== '-' ? ' · Deleted ' + esc(time) : '') + '</div>'
          + '<p class="skill-list-desc">' + esc(desc) + '</p>'
          + '</div>'
          + '<div class="inline-actions skill-row-actions">'
          + '<button type="button" class="icon-button" data-restore-skill="' + esc(sid) + '" data-tip="Restore" aria-label="Restore ' + esc(name) + '">' + icon('rotate-ccw') + '</button>'
          + '<button type="button" class="icon-button" data-purge-skill="' + esc(sid) + '" data-purge-name="' + esc(name) + '" data-tip="Delete permanently" aria-label="Delete permanently ' + esc(name) + '">' + icon('trash-2') + '</button>'
          + '</div></div>';
      }).join('');
      $('kgSkillRegistry').querySelectorAll('[data-restore-skill]').forEach(function (button) {
        button.addEventListener('click', async function () {
          button.disabled = true;
          try {
            await post('/api/kg/skills/restore', { skill: button.dataset.restoreSkill });
            await loadSkills();
            setSkillsListTab('trash');
          } catch (error) {
            status('kgSkillStatus', error.message, 'error');
            button.disabled = false;
          }
        });
      });
      $('kgSkillRegistry').querySelectorAll('[data-purge-skill]').forEach(function (button) {
        button.addEventListener('click', function () {
          openPurgeModal('skill', button.dataset.purgeSkill, button.dataset.purgeName || button.dataset.purgeSkill);
        });
      });
      bindSkillFastTips($('kgSkillRegistry'));
      app.icons();
      return;
    }
    if (isPending) {
      $('kgSkillRegistry').innerHTML = filtered.map(function (skill) {
        const name = skill.name || skill.filename || 'Untitled';
        const typeLabel = [skill.file_type, skill.template_kind].filter(Boolean).join(' · ') || 'Pending Review';
        const desc = skill.function_desc || skill.description || '—';
        const statusLabel = statuses[skill.status] || skill.status || 'Pending Review';
        return '<div class="skill-list-row is-pending">'
          + '<div class="skill-list-main">'
          + '<div class="skill-list-top"><span class="skill-list-name">' + esc(name) + '</span><span class="status-badge warning">' + esc(statusLabel) + '</span></div>'
          + '<div class="skill-list-type">' + esc(typeLabel) + '</div>'
          + '<p class="skill-list-desc">' + esc(desc) + '</p>'
          + '</div>'
          + '<div class="inline-actions skill-row-actions">'
          + '<button type="button" class="icon-button" data-pending-delete="' + esc(skill.filename || '') + '" data-pending-name="' + esc(name) + '" data-tip="Delete Pending Review" aria-label="Delete ' + esc(name) + '">' + icon('trash-2') + '</button>'
          + '</div></div>';
      }).join('');
      $('kgSkillRegistry').querySelectorAll('[data-pending-delete]').forEach(function (button) {
        button.addEventListener('click', async function () {
          const filename = button.dataset.pendingDelete;
          if (!filename) return;
          button.disabled = true;
          try {
            await app.api('/api/kg/skills/draft?filename=' + encodeURIComponent(filename), { method: 'DELETE' });
            await loadSkills();
            setSkillsListTab('pending');
          } catch (error) {
            status('kgSkillStatus', error.message, 'error');
            button.disabled = false;
          }
        });
      });
      bindSkillFastTips($('kgSkillRegistry'));
      app.icons();
      return;
    }
    $('kgSkillRegistry').innerHTML = filtered.map(function (skill) {
      const sid = skill.skill_id || skill.id || '';
      const name = skill.name || sid;
      const enabled = String(skill.status || 'enabled').toLowerCase() !== 'disabled';
      const typeLabel = [skill.file_type, skill.template_kind].filter(Boolean).join(' · ') || '—';
      const toggleLabel = enabled ? 'Disable' : 'Enable';
      const nextStatus = enabled ? 'disabled' : 'enabled';
      const statusLabel = statuses[skill.status] || skill.status || 'Enabled';
      const desc = skill.description || '—';
      return '<div class="skill-list-row' + (enabled ? '' : ' is-disabled') + '">'
        + '<div class="skill-list-main">'
        + '<div class="skill-list-top"><span class="skill-list-name">' + esc(name) + '</span><span class="status-badge' + (enabled ? '' : ' error') + '">' + esc(statusLabel) + '</span></div>'
        + '<div class="skill-list-type">' + esc(typeLabel) + '</div>'
        + '<p class="skill-list-desc">' + esc(desc) + '</p>'
        + '</div>'
        + '<div class="inline-actions skill-row-actions">'
        + '<button type="button" class="icon-button skill-toggle-btn" data-skill-toggle="' + esc(sid) + '" data-next-status="' + nextStatus + '" data-tip="' + toggleLabel + '" aria-label="' + toggleLabel + ' ' + esc(name) + '">' + icon(enabled ? 'unplug' : 'circle-check') + '</button>'
        + '<button type="button" class="icon-button" data-skill-delete="' + esc(sid) + '" data-skill-name="' + esc(name) + '" data-tip="Move to trash" aria-label="Delete ' + esc(name) + '">' + icon('trash-2') + '</button>'
        + '</div></div>';
    }).join('');
    $('kgSkillRegistry').querySelectorAll('[data-skill-toggle]').forEach(function (button) {
      button.addEventListener('click', async function () {
        const sid = button.dataset.skillToggle;
        const next = button.dataset.nextStatus;
        button.disabled = true;
        try {
          await post('/api/kg/skills/status', { skill: sid, status: next });
          await loadSkills();
        } catch (error) {
          status('kgSkillStatus', error.message, 'error');
          button.disabled = false;
        }
      });
    });
    $('kgSkillRegistry').querySelectorAll('[data-skill-delete]').forEach(function (button) {
      button.addEventListener('click', function () {
        openSkillDeleteModal(button.dataset.skillDelete, button.dataset.skillName || button.dataset.skillDelete);
      });
    });
    bindSkillFastTips($('kgSkillRegistry'));
    app.icons();
  }
  async function ensureSkills() {
    if (!state.ready || state.skillsLoaded) return;
    state.skillsLoaded = true;
    await loadSkills();
  }
  $('kgSkillsTabs')?.addEventListener('click', function (event) {
    const button = event.target.closest('[data-skills-tab]');
    if (!button) return;
    setSkillsListTab(button.getAttribute('data-skills-tab'));
  });
  $('kgSkillSearch')?.addEventListener('input', renderSkillList);
  async function routeOntology() {
    if (!state.sources.length) await Promise.allSettled([loadSources(), loadSkills()]);
    const params = new URLSearchParams(window.location.hash.split('?')[1] || '');
    const tab = params.get('tab') || state.tab;
    const source = params.get('source');
    const view = params.get('view');
    if (view === 'create' || tab === 'skills') {
      const next = view === 'create' ? '#skill?view=create' : '#skill';
      window.history.replaceState(null, '', next);
      if (app.setView) app.setView('skill', false);
      await routeSkill();
      return;
    }
    if (tab === 'builder') {
      setSkillsCreateMode(false, false);
      setSourcesWorkMode('build', false);
      setOntologyListOpen(false);
    } else if (tab === 'refine' || source) {
      setSkillsCreateMode(false, false);
      setSourcesWorkMode('refine', false);
      setOntologyListOpen(false);
      if (source && state.sources.length) {
        if (source !== state.source) await openSource(source);
        else setSourcesWorkMode('refine', false);
      }
    } else {
      setSkillsCreateMode(false, false);
      setOntologyListOpen(false);
      setOntologyListTab('sources');
      setSourcesWorkMode('build', false);
    }
  }
  async function routeSkill() {
    await ensureSkills();
    const params = new URLSearchParams(window.location.hash.split('?')[1] || '');
    if (params.get('view') === 'create') setSkillsCreateMode(true, false);
    else setSkillsCreateMode(false, false);
  }
  async function route() {
    const hash = window.location.hash || '';
    if (hash.startsWith('#skill')) await routeSkill();
    else if (hash.startsWith('#ontology')) await routeOntology();
  }
  window.addEventListener('hashchange', route);
  window.addEventListener('workbench:view', function (event) {
    if (event.detail === 'skill') {
      ensureSkills();
      if (!/[#&?]view=create\b/.test(window.location.hash || '')) setSkillsCreateMode(false, false);
    } else if (event.detail === 'ontology') {
      setSkillsCreateMode(false, false);
      if (!state.sourcesWork) setSourcesWorkMode('build', false);
      else {
        syncOntologyListToggle();
        syncOntologyTopbarCopy();
      }
    } else {
      setSkillsCreateMode(false, false);
    }
  });
  setOntologyListTab(state.ontologyListTab);
  syncOntologyListToggle();
  syncSkillsListToggle();
  state.sessions = readStoredSessions();
  if (!state.sessionId) state.sessionId = newSessionId();
  renderSessionList();
  $('kgSessionNew')?.addEventListener('click', function (event) {
    event.preventDefault();
    event.stopPropagation();
    if (this.disabled) return;
    startNewOntologySession();
  });
  resetChat();
  app.ready.then(async function (authenticated) {
    if (!authenticated) return;
    state.ready = true;
    await loadSources();
    await route();
    persistCurrentSession();
    if ((window.location.hash || '').startsWith('#skill')) await ensureSkills();
  });
})();
