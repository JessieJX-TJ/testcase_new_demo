(function () {
  const state = { view: 'graph' };
  const select = document.getElementById('kgSelect');

  const viewCopy = {
    graph: ['Graph Browse', 'Browse nodes, relations, and domain structure in the current knowledge graph.', 'Graph / Browse'],
    ontology: ['Ontology', 'Configure build parameters, upload files, parse, then submit for Pending Review.', 'Ontology / Structure'],
    skill: ['Skill', 'Manage extraction Skills; configure file types and entity-relation extraction targets.', 'Skill / Config'],
    search: ['Knowledge Search', 'Search test types, cases, and evidence in the current knowledge graph.', 'Search / Evidence'],
    qa: ['Knowledge Q&A', 'Ask questions against the current knowledge graph.', 'Knowledge Q&A'],
    'test-case-generation': ['Test Case Generation', 'Create, improve, and refine test cases.', 'Test Case Generation'],
    account: ['Groups & Accounts', 'Manage the current account, group permissions, and knowledge graph visibility.', 'Groups & Accounts'],
    audit: ['Operation Log', 'View database changes for the knowledge graph, ontology, and Skills.', 'Admin / Operation Log'],
  };

  function icons(root) {
    if (window.lucide && typeof window.lucide.createIcons === 'function') {
      window.lucide.createIcons(root ? { root } : undefined);
    }
  }

  function escapeHtml(value) {
    return String(value || '').replace(/[&<>"']/g, (char) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[char]));
  }

  const LIVE_API_ORIGINS = [
    'http://127.0.0.1:4000',
    'http://localhost:4000',
  ];

  function resolveApiUrl(url) {
    if (/^https?:\/\//i.test(url)) return url;
    return url;
  }

  async function parseApiResponse(response) {
    let payload;
    try {
      payload = await response.json();
    } catch (_) {
      throw new Error('Service returned an invalid response. Please retry.');
    }
    if (!response.ok || payload.success === false || payload.ok === false) {
      throw new Error(payload.error || payload.message || 'Request failed');
    }
    return payload;
  }

  async function api(url, options) {
    const opts = Object.assign({ credentials: 'same-origin' }, options || {});
    const method = String(opts.method || 'GET').toUpperCase();
    const path = String(url || '');
    const candidates = [resolveApiUrl(path)];

    // When index.html is opened via Live Preview / static server (not :4000),
    // still talk to the local Flask backend for the full live effect.
    if (path.startsWith('/api/')) {
      const origin = window.location.origin || '';
      LIVE_API_ORIGINS.forEach((live) => {
        if (!origin.startsWith(live)) candidates.push(live + path);
      });
    }

    let lastError = null;
    for (let i = 0; i < candidates.length; i += 1) {
      try {
        const response = await fetch(candidates[i], Object.assign({}, opts, {
          // Cross-origin call to Flask needs CORS (already enabled) without cookies.
          credentials: candidates[i].startsWith('http') && !candidates[i].startsWith(window.location.origin)
            ? 'omit'
            : opts.credentials,
        }));
        return await parseApiResponse(response);
      } catch (error) {
        if (opts.signal && opts.signal.aborted) throw error;
        lastError = error;
      }
    }

    if (method !== 'GET') throw lastError || new Error('Request failed');
    const fallback = staticFallbackFor(path);
    if (!fallback) throw lastError || new Error('Request failed');
    try {
      const response = await fetch(fallback, { cache: 'no-cache', signal: opts.signal });
      return await parseApiResponse(response);
    } catch (error) {
      throw lastError || error;
    }
  }

  function staticFallbackFor(url) {
    const path = String(url || '').split('?')[0];
    const map = {
      '/api/graph/data': 'static/data/graph-preview.json',
      '/api/graph/list': 'static/data/graph-list-preview.json',
      '/api/kg/sources': 'static/data/kg-sources-preview.json',
      '/api/kg/skills': 'static/data/kg-skills-preview.json',
      '/api/kg/sources/trash': 'static/data/kg-sources-trash-preview.json',
      '/api/kg/skills/trash': 'static/data/kg-skills-trash-preview.json',
      '/api/auth/session': 'static/data/auth-session-preview.json',
      '/api/knowledge-graphs': 'static/data/knowledge-graphs-preview.json',
    };
    const rel = map[path];
    if (!rel) return null;
    const scripts = document.getElementsByTagName('script');
    for (let i = 0; i < scripts.length; i += 1) {
      const src = scripts[i].src || '';
      if (src.includes('/static/js/') || src.includes('static/js/')) {
        return src.replace(/js\/[^/?#]+(\?[^#]*)?(#.*)?$/, rel.replace(/^static\//, ''));
      }
    }
    return rel;
  }

  function setView(view, syncHash) {
    if (!viewCopy[view]) view = 'graph';
    state.view = view;
    document.querySelectorAll('.rail-link[data-view]').forEach((item) => {
      item.classList.toggle('is-active', item.dataset.view === view);
    });
    document.querySelectorAll('.view-panel').forEach((panel) => {
      panel.classList.toggle('is-visible', panel.dataset.panel === view);
    });
    const title = document.getElementById('viewTitle');
    const ontologyCrumb = document.getElementById('ontologyTitleBreadcrumb');
    const skillCrumb = document.getElementById('skillTitleBreadcrumb');
    const heading = document.getElementById('viewHeading');
    const description = document.getElementById('viewDescription');
    const overline = document.querySelector('.workspace-toolbar .overline');
    const graphActions = document.getElementById('graphStageActions');
    const ontologyActions = document.getElementById('ontologyStageActions');
    const skillActions = document.getElementById('skillStageActions');
    const graphSource = document.getElementById('graphSource');
    const graphLegend = document.getElementById('graphLegend');
    if (title) {
      title.hidden = false;
      if (view === 'graph') title.textContent = 'Relation Graph';
      else if (view === 'ontology') {
        title.innerHTML = 'Ontology<span class="view-title-sep" aria-hidden="true"></span>File Build';
      } else {
        title.textContent = viewCopy[view][0];
      }
    }
    if (ontologyCrumb && view !== 'ontology') ontologyCrumb.hidden = true;
    if (skillCrumb && view !== 'skill') skillCrumb.hidden = true;
    if (heading) heading.textContent = viewCopy[view][0];
    if (description) {
      description.textContent = viewCopy[view][1];
      description.hidden = view === 'graph';
    }
    if (overline) overline.textContent = viewCopy[view][2];
    if (graphActions) graphActions.hidden = view !== 'graph';
    if (ontologyActions) ontologyActions.hidden = view !== 'ontology';
    if (skillActions) skillActions.hidden = view !== 'skill';
    const ontologySubnav = document.getElementById('ontologyRailSubnav');
    if (ontologySubnav) ontologySubnav.hidden = view !== 'ontology';
    document.querySelectorAll('.rail-group[data-rail-group]').forEach((group) => {
      group.classList.toggle('is-open', group.getAttribute('data-rail-group') === view);
    });
    if (graphSource) graphSource.hidden = view !== 'graph';
    if (graphLegend) graphLegend.hidden = view !== 'graph';
    const workspace = document.querySelector('.workspace');
    if (workspace) {
      if (view === 'skill') {
        workspace.classList.add('is-skill-page');
        workspace.classList.remove('is-ontology-page', 'is-skill-create');
        // Collapsed by default; workbench skillsListOpen re-adds dock if the user opened the list
        workspace.classList.remove('is-list-dock');
      } else if (view === 'ontology') {
        workspace.classList.add('is-ontology-page');
        workspace.classList.remove('is-skill-page', 'is-skill-create');
      } else {
        workspace.classList.remove('is-skill-page', 'is-list-dock', 'is-skill-create', 'is-ontology-page');
      }
    }
    if (syncHash !== false) {
      const current = (location.hash || '').replace(/^#/, '').split('?')[0];
      if (current !== view) history.replaceState(null, '', `#${view}`);
    }
    if (window.graphWorkbench && typeof window.graphWorkbench.onView === 'function') {
      window.graphWorkbench.onView(view);
    }
    window.dispatchEvent(new CustomEvent('workbench:view', { detail: view }));
    icons();
  }

  function viewFromHash() {
    const hash = (location.hash || '#graph').replace(/^#/, '').split('?')[0] || 'graph';
    return viewCopy[hash] ? hash : 'graph';
  }

  document.querySelectorAll('.rail-link[data-view]').forEach((item) => {
    item.addEventListener('click', (event) => {
      event.preventDefault();
      setView(item.dataset.view);
    });
  });
  document.querySelectorAll('[data-open-view]').forEach((item) => {
    item.addEventListener('click', (event) => {
      event.preventDefault();
      setView(item.dataset.openView);
    });
  });
  document.querySelector('.brand')?.addEventListener('click', (event) => {
    event.preventDefault();
    setView('graph');
  });
  window.addEventListener('hashchange', () => setView(viewFromHash(), false));

  function refreshGraph() {
    if (window.graphWorkbench && typeof window.graphWorkbench.reload === 'function') {
      return window.graphWorkbench.reload();
    }
    return Promise.resolve(null);
  }

  window.workbench = {
    api,
    icons,
    setView,
    refreshGraph,
    authenticated: true,
    user: { username: 'local', display_name: 'Local User', role: 'admin', status: 'active' },
    hasUnsaved: () => false,
    ready: Promise.resolve(true),
  };

  const modal = document.getElementById('loginModal');
  const toggleModal = (open) => {
    if (!modal) return;
    modal.hidden = !open;
    if (open) document.getElementById('loginDone')?.focus();
  };
  document.getElementById('loginOpen')?.addEventListener('click', () => toggleModal(true));
  document.getElementById('loginClose')?.addEventListener('click', () => toggleModal(false));
  document.getElementById('loginDone')?.addEventListener('click', () => toggleModal(false));

  const searchEmpty = (title, detail) => (
    `<div class="empty-workspace compact"><div class="empty-glyph">⌕</div><h3>${escapeHtml(title)}</h3><p>${escapeHtml(detail)}</p></div>`
  );
  const joinSearchField = (value) => {
    if (Array.isArray(value)) return value.filter(Boolean).join('; ');
    return value ? String(value) : '';
  };
  let searchToken = 0;
  document.getElementById('searchForm')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const query = document.getElementById('searchInput').value.trim();
    if (!query) return;
    const result = document.getElementById('searchResults');
    const token = ++searchToken;
    result.innerHTML = '<p class="empty-state">Searching…</p>';
    try {
      const payload = await api(`/api/graph/search?kg_id=${encodeURIComponent(select.value)}&q=${encodeURIComponent(query)}&limit=50`);
      if (token !== searchToken) return;
      const rows = payload.data?.results || [];
      if (!rows.length) {
        result.innerHTML = searchEmpty('No matching results', 'No related content was found in the current knowledge graph.');
        return;
      }
      result.innerHTML = rows.map((record, index) => {
        const title = record.case_name || record.label || record.case_id || record.id || '';
        const type = record.test_type || record.case_type || record.kind || '';
        const score = record.score != null ? ` · ${Number(record.score).toFixed(3)}` : '';
        const detail = [record.preconditions, record.actions, record.expected_behaviors]
          .map(joinSearchField)
          .filter(Boolean)
          .join(' / ');
        return `<button class="result-row" type="button" data-search-index="${index}" data-case-id="${escapeHtml(record.case_id || record.id || '')}"><strong>${escapeHtml(title)}</strong><small>${escapeHtml(type)}${escapeHtml(score)}</small>${detail ? `<small>${escapeHtml(detail)}</small>` : ''}</button>`;
      }).join('');
      result.querySelectorAll('[data-search-index]').forEach((button) => {
        button.addEventListener('click', () => {
          const record = rows[Number(button.dataset.searchIndex)];
          if (!record) return;
          const caseId = record.case_id || record.id || button.dataset.caseId;
          setView('graph');
          if (window.graphWorkbench && typeof window.graphWorkbench.focusCase === 'function') {
            window.graphWorkbench.focusCase(caseId);
          }
        });
      });
    } catch (error) {
      if (token !== searchToken) return;
      result.innerHTML = searchEmpty('Search failed', error.message || 'Search service is temporarily unavailable. Please try again later.');
    }
  });

  setView(viewFromHash(), false);
  icons();
})();
