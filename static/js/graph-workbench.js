(function () {
  const container = document.getElementById('graphCanvas');
  const list = document.getElementById('graphList');
  const loading = document.getElementById('graphLoading');
  const select = document.getElementById('kgSelect');
  if (!container || !loading || !select) return;

  const state = {
    layout: 'radial',
    listMode: 'dock',
    motion: 'static',
    graphLoaded: false,
    graphRequest: null,
    graphController: null,
    graph: { nodes: [], edges: [], stats: {} },
    list: { types: [], cases: [], stats: {}, typeOptions: [] },
    network: null,
    nodesData: null,
    edgesData: null,
    selectedNodeId: null,
    selectedEdgeId: null,
    selectedCaseId: null,
    pendingFocusId: null,
    savedView: null,
    graphFocus: null,
  };
  const nodeCard = document.getElementById('graphNodeCard');
  const listPanel = document.getElementById('listPanel');
  const canvasWrap = document.querySelector('.graph-canvas-wrap');
  const graphControls = document.querySelector('.graph-controls');
  const listExpandToggle = document.getElementById('listExpandToggle');

  const kindLabels = {
    type: 'Test Type',
    case: 'Test Case',
    condition: 'Preconditions',
    action: 'Actions',
    expectation: 'Expected Behavior',
    category: 'Test Type',
  };

  function esc(value) {
    return String(value || '').replace(/[&<>"']/g, (char) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[char]));
  }

  async function api(url, options) {
    if (window.workbench && typeof window.workbench.api === 'function') {
      return window.workbench.api(url, options);
    }
    const response = await fetch(url, Object.assign({ credentials: 'same-origin' }, options || {}));
    let payload;
    try { payload = await response.json(); } catch (_) { throw new Error('Service returned an invalid response. Please retry.'); }
    if (!response.ok || payload.success === false || payload.ok === false) {
      throw new Error(payload.error || payload.message || 'Request failed');
    }
    return payload;
  }

  function resolveStaticAsset(relPath) {
    const scripts = document.getElementsByTagName('script');
    for (let i = 0; i < scripts.length; i += 1) {
      const src = scripts[i].src || '';
      if (src.includes('graph-workbench')) {
        return src.replace(/js\/graph-workbench\.js(\?[^/]*)?$/, relPath);
      }
    }
    // Prefer absolute-from-origin when page is served under a subpath-unfriendly host,
    // but keep relative form for GitHub Pages project sites.
    const base = document.querySelector('base[href]');
    if (base && base.href) {
      try {
        return new URL(`static/${relPath}`, base.href).href;
      } catch (_error) { /* fall through */ }
    }
    return `static/${relPath}`;
  }

  async function apiWithStaticFallback(url, fallbackRelPath, options) {
    try {
      return await api(url, options);
    } catch (error) {
      if (options && options.signal && options.signal.aborted) throw error;
      const candidates = [
        resolveStaticAsset(fallbackRelPath),
        `static/${fallbackRelPath}`,
        `./static/${fallbackRelPath}`,
      ];
      let lastError = error;
      for (let i = 0; i < candidates.length; i += 1) {
        try {
          const response = await fetch(candidates[i], Object.assign({
            cache: 'no-cache',
          }, options && options.signal ? { signal: options.signal } : {}));
          let payload;
          try { payload = await response.json(); } catch (_) { continue; }
          if (!response.ok || payload.success === false || payload.ok === false) continue;
          return payload;
        } catch (fallbackError) {
          lastError = fallbackError;
        }
      }
      throw lastError;
    }
  }

  function renderList() {
    const grouped = {};
    (state.list.cases || []).forEach((record) => {
      (grouped[record.type] || (grouped[record.type] = [])).push(record);
    });
    const relationCount = (record) => 1 + (record.condition_count || 0) + (record.has_action ? 1 : 0) + (record.has_expectation ? 1 : 0);
    const row = (record) => {
      const label = record.label || record.name || record.id || 'Untitled test case';
      const typeName = record.type || record.case_type || 'Uncategorized';
      return `<button type="button" class="list-row${state.selectedCaseId === record.id ? ' is-selected' : ''}" data-case-id="${esc(record.id)}"><span class="list-case-name">${esc(label)}</span><span class="list-case-id">${esc(record.case_number || record.id)}</span><span class="list-case-type">${esc(typeName)}</span><span class="list-case-relations">${relationCount(record)} relations</span></button>`;
    };
    const groups = Object.keys(grouped).map((typeName, index) => {
      const records = grouped[typeName];
      const groupId = `list-group-${index}`;
      return `<section class="list-group" data-list-group="${esc(groupId)}"><div class="list-group-title"><button type="button" class="group-toggle" data-collapse-type="${esc(groupId)}" aria-expanded="true">−</button><span class="list-group-name">${esc(typeName)}</span><small>${records.length} test cases</small></div><div class="list-group-body" id="${esc(groupId)}">${records.map(row).join('')}</div></section>`;
    }).join('');
    list.innerHTML = `<div class="list-column-head"><span>Test Case Name</span><span>ID</span><span>Test Type</span><span>Relations</span></div>${groups || '<div class="list-empty">No matching test cases</div>'}`;
    list.querySelectorAll('[data-collapse-type]').forEach((toggle) => {
      toggle.addEventListener('click', () => {
        const body = document.getElementById(toggle.dataset.collapseType);
        const expanded = toggle.getAttribute('aria-expanded') === 'true';
        body.hidden = expanded;
        toggle.setAttribute('aria-expanded', String(!expanded));
        toggle.textContent = expanded ? '+' : '−';
      });
    });
    list.querySelectorAll('[data-case-id]').forEach((item) => {
      item.addEventListener('click', () => focusCase(item.dataset.caseId));
    });
    const stats = state.list.stats || {};
    const statsBox = document.getElementById('listStats');
    if (statsBox) {
      const metrics = [
        ['Test Type', stats.types || 0, 'Number of types in the current filter scope'],
        ['Test Case', stats.total_cases || 0, 'Total cases matching the filter'],
        ['Type–Case Relations', stats.relations || 0, 'Each test case belongs to one test type'],
        ['Avg Cases per Type', stats.average_cases_per_type || 0, 'Total cases ÷ test types'],
      ];
      statsBox.innerHTML = metrics.map(([label, value, tip], index) => (
        `<span class="list-metric">`
        + `<span class="list-metric-label">`
        + `<small>${label}</small>`
        + `<button class="list-metric-help" type="button" aria-label="${label} help" aria-describedby="listMetricTip${index}">`
        + `<i data-lucide="circle-help"></i>`
        + `<span class="list-metric-tip" id="listMetricTip${index}" role="tooltip">${tip}</span>`
        + `</button>`
        + `</span>`
        + `<b>${Number(value).toLocaleString()}</b>`
        + `</span>`
      )).join('');
      if (window.lucide && typeof window.lucide.createIcons === 'function') {
        window.lucide.createIcons({ root: statsBox });
      }
    }
  }

  function populateListTypes(types) {
    const filter = document.getElementById('listTypeFilter');
    if (!filter) return;
    const current = filter.value;
    if (!state.list.typeOptions.length) state.list.typeOptions = types.slice();
    filter.innerHTML = `<option value="">All test types</option>${state.list.typeOptions.map((item) => `<option value="${esc(item.name)}">${esc(item.name)} (${item.count})</option>`).join('')}`;
    filter.value = current;
  }

  async function loadList() {
    const filter = document.getElementById('listTypeFilter');
    const search = document.getElementById('listSearch');
    const limit = document.getElementById('listLimit');
    const params = new URLSearchParams({
      kg_id: select.value,
      type: filter ? filter.value : '',
      q: search ? search.value.trim() : '',
      limit: limit ? limit.value : '180',
    });
    loading.textContent = 'Loading list…';
    loading.classList.remove('is-hidden');
    try {
      const payload = await apiWithStaticFallback(
        `/api/graph/list?${params.toString()}`,
        'data/graph-list-preview.json',
      );
      state.list = Object.assign(state.list, payload.data);
      populateListTypes(payload.data.available_types || payload.data.types || []);
      renderList();
      loading.classList.add('is-hidden');
    } catch (error) {
      loading.textContent = error.message || 'Failed to load list';
    }
  }

  function focusNetworkNode(nodeId, scale, onFocused) {
    const network = state.network;
    if (!network) return;
    let done = false;
    const applyFocus = () => {
      if (done || state.network !== network) return;
      const point = network.getPositions([nodeId])[nodeId];
      if (!point) return;
      done = true;
      const nextScale = scale || 1.65;
      const shift = listDockShiftX();
      // Keep focused nodes in the visible canvas area (left of the docked list).
      network.moveTo({
        position: point,
        scale: nextScale,
        offset: { x: -shift, y: 0 },
        animation: { duration: 500, easingFunction: 'easeInOutQuad' },
      });
      if (shift) {
        state.savedView = { position: { x: point.x, y: point.y }, scale: nextScale };
      }
      network.selectNodes([nodeId]);
      state.pendingFocusId = null;
      if (onFocused) onFocused();
    };
    network.once('afterDrawing', applyFocus);
    window.setTimeout(applyFocus, 1000);
  }

  function markSelectedCase(caseId) {
    state.selectedCaseId = caseId || null;
    if (!list) return;
    list.querySelectorAll('.list-row[data-case-id]').forEach((item) => {
      item.classList.toggle('is-selected', item.dataset.caseId === state.selectedCaseId);
    });
  }

  async function focusCase(caseId) {
    if (!caseId) return;
    markSelectedCase(caseId);
    try {
      loading.textContent = 'Loading case relations…';
      loading.classList.remove('is-hidden');
      const payload = await apiWithStaticFallback(
        `/api/graph/data?kg_id=${encodeURIComponent(select.value)}&case_id=${encodeURIComponent(caseId)}&limit=40`,
        'data/graph-preview.json',
      );
      if (!payload.data.nodes.length) throw new Error('Test case not found');
      // Static preview is an overview dump; when falling back, keep only the focused case neighborhood if present.
      const caseNodeId = `case:${caseId}`;
      const hasCase = (payload.data.nodes || []).some((node) => node.id === caseNodeId || node.case_number === caseId || node.id === caseId);
      if (hasCase && (payload.data.stats || {}).source === 'static-preview') {
        const keepNodes = new Set([caseNodeId]);
        (payload.data.nodes || []).forEach((node) => {
          if (node.id === caseId || node.case_number === caseId) keepNodes.add(node.id);
        });
        (payload.data.edges || []).forEach((edge) => {
          if (keepNodes.has(edge.source) || keepNodes.has(edge.target) || edge.source === caseNodeId || edge.target === caseNodeId) {
            keepNodes.add(edge.source);
            keepNodes.add(edge.target);
          }
        });
        // Include parent type edges into the case.
        (payload.data.edges || []).forEach((edge) => {
          if (edge.target === caseNodeId) keepNodes.add(edge.source);
        });
        payload.data = {
          ...payload.data,
          nodes: (payload.data.nodes || []).filter((node) => keepNodes.has(node.id)),
          edges: (payload.data.edges || []).filter((edge) => keepNodes.has(edge.source) && keepNodes.has(edge.target)),
        };
      }
      state.graph = payload.data;
      updateStats();
      if (state.network) {
        stopMotionWatch();
        state.network.destroy();
        state.network = null;
        state.nodesData = null;
        state.edgesData = null;
      }
      // Always show the extracted local neighborhood (never zoom the overview mesh).
      state.pendingFocusId = `case:${caseId}`;
      if (state.layout === 'list') {
        if (state.listMode === 'expanded') state.listMode = 'dock';
        setLayout('list', { keepListMode: true, skipFit: true });
      } else {
        setLayout(state.layout || 'radial', { skipFit: true });
      }
      if (!state.network) createNetwork();
      const targetId = state.pendingFocusId;
      focusNetworkNode(targetId, 1.35, () => {
        state.pendingFocusId = null;
        const node = state.graph.nodes.find((candidate) => (
          candidate.id === targetId || candidate.case_number === caseId || candidate.id === caseId
        ));
        if (node) selectNode(node);
      });
    } catch (error) {
      state.pendingFocusId = null;
      loading.classList.add('is-hidden');
      window.alert(error.message || 'Unable to locate test case');
    }
  }

  function kindOf(node) {
    return node.kind === 'category' ? 'type' : node.kind;
  }

  function wreathPositions(graphNodes, graphEdges) {
    const byId = Object.fromEntries(graphNodes.map((node) => [node.id, node]));
    const casesByType = {};
    const detailsByCase = {};
    (graphEdges || []).forEach((edge) => {
      const source = byId[edge.source];
      const target = byId[edge.target];
      if (!source || !target) return;
      if (kindOf(source) === 'type' && kindOf(target) === 'case') {
        (casesByType[source.id] || (casesByType[source.id] = [])).push(target.id);
      } else if (kindOf(source) === 'case') {
        (detailsByCase[source.id] || (detailsByCase[source.id] = [])).push(target.id);
      }
    });

    const typeNodes = graphNodes.filter((node) => kindOf(node) === 'type');
    const placed = {};
    const typeCount = Math.max(typeNodes.length, 1);
    const ringRadius = 520;

    typeNodes.forEach((typeNode, typeIndex) => {
      const angle = (typeIndex / typeCount) * Math.PI * 2 - Math.PI / 2;
      const tx = Math.cos(angle) * ringRadius;
      const ty = Math.sin(angle) * ringRadius;
      placed[typeNode.id] = { x: tx, y: ty };

      const caseIds = casesByType[typeNode.id] || graphNodes
        .filter((node) => kindOf(node) === 'case' && (node.case_type === typeNode.label || node.case_type === typeNode.id))
        .map((node) => node.id);
      const uniqueCases = [...new Set(caseIds)];
      uniqueCases.forEach((caseId, caseIndex) => {
        const caseCount = Math.max(uniqueCases.length, 1);
        const petal = ((caseIndex - (caseCount - 1) / 2) / caseCount) * 0.55;
        const caseAngle = angle + petal;
        const caseRadius = ringRadius - 78;
        const cx = Math.cos(caseAngle) * caseRadius;
        const cy = Math.sin(caseAngle) * caseRadius;
        placed[caseId] = { x: cx, y: cy };

        const detailIds = detailsByCase[caseId] || [];
        detailIds.forEach((detailId, detailIndex) => {
          const spread = ((detailIndex - (detailIds.length - 1) / 2) / Math.max(detailIds.length, 1)) * 0.35;
          const detailAngle = caseAngle + spread;
          const detailRadius = caseRadius - 52 - (detailIndex % 3) * 10;
          placed[detailId] = {
            x: Math.cos(detailAngle) * detailRadius,
            y: Math.sin(detailAngle) * detailRadius,
          };
        });
      });
    });

    // Place any leftover nodes on the outer ring so nothing stacks at origin.
    let orphan = 0;
    graphNodes.forEach((node) => {
      if (placed[node.id]) return;
      const angle = (orphan / Math.max(graphNodes.length, 1)) * Math.PI * 2;
      placed[node.id] = {
        x: Math.cos(angle) * (ringRadius + 40),
        y: Math.sin(angle) * (ringRadius + 40),
      };
      orphan += 1;
    });
    return placed;
  }

  function nodeStyle(node, positions) {
    const kind = kindOf(node);
    const size = kind === 'type' ? 22 : (kind === 'case' ? 14 : 9);
    const accent = kind === 'type' ? '#14C9C9' : (kind === 'case' ? '#F7BA1E' : '#8D4EDA');
    const label = String(node.label || node.id || '');
    const point = (positions && positions[node.id]) || { x: 0, y: 0 };
    return {
      id: node.id,
      x: point.x,
      y: point.y,
      label: label.length > 26 ? `${label.slice(0, 26)}…` : label,
      shape: 'dot',
      size,
      value: size,
      color: {
        background: accent,
        border: accent,
        highlight: { background: accent, border: '#0066FF' },
        hover: { background: accent, border: '#0066FF' },
      },
      font: {
        color: '#22303c',
        size: kind === 'type' || kind === 'case' ? 10 : 9,
        face: 'Microsoft YaHei, sans-serif',
        strokeWidth: 0,
      },
      borderWidth: 1,
      borderWidthSelected: 3,
    };
  }

  function edgeStyle(edge) {
    return {
      id: edge.id,
      from: edge.source,
      to: edge.target,
      label: edge.relation || edge.label || 'Relation',
      arrows: { to: { enabled: true, scaleFactor: 0.42 } },
      color: { color: 'rgba(76, 96, 116, .40)', highlight: '#14C9C9', hover: '#14C9C9' },
      font: { color: '#54697a', size: 9, face: 'Microsoft YaHei, sans-serif', strokeWidth: 0, align: 'middle' },
      smooth: false,
      width: 1,
    };
  }

  function nodeAccent(kind) {
    return kind === 'type' ? '#14C9C9' : (kind === 'case' ? '#F7BA1E' : '#8D4EDA');
  }

  function setCanvasFocusClass(active) {
    if (!canvasWrap) return;
    canvasWrap.classList.toggle('is-graph-focus', !!active);
  }

  function collectFocusSets(type, id) {
    const focusNodes = new Set();
    const focusEdges = new Set();
    if (!id) return { focusNodes, focusEdges };
    if (type === 'node') {
      focusNodes.add(id);
      nodeEdges(id).forEach((edge) => {
        if (edge.id) focusEdges.add(edge.id);
        if (edge.source) focusNodes.add(edge.source);
        if (edge.target) focusNodes.add(edge.target);
      });
    } else if (type === 'edge') {
      const edge = (state.graph.edges || []).find((candidate) => candidate.id === id);
      if (edge) {
        if (edge.id) focusEdges.add(edge.id);
        if (edge.source) focusNodes.add(edge.source);
        if (edge.target) focusNodes.add(edge.target);
      }
    }
    return { focusNodes, focusEdges };
  }

  function applyGraphFocus(type, id) {
    if (!state.nodesData || !state.edgesData) return;
    if (!type || !id) {
      clearGraphFocus();
      return;
    }
    state.graphFocus = { type, id };
    setCanvasFocusClass(true);
    const { focusNodes, focusEdges } = collectFocusSets(type, id);
    const byId = Object.fromEntries((state.graph.nodes || []).map((node) => [node.id, node]));

    const nodeUpdates = state.nodesData.getIds().map((nodeId) => {
      const focused = focusNodes.has(nodeId);
      const node = byId[nodeId];
      const kind = kindOf(node || { kind: 'detail' });
      const accent = nodeAccent(kind);
      return {
        id: nodeId,
        opacity: focused ? 1 : 0.45,
        color: focused
          ? {
            background: accent,
            border: type === 'node' && nodeId === id ? '#0066FF' : accent,
            highlight: { background: accent, border: '#0066FF' },
            hover: { background: accent, border: '#0066FF' },
          }
          : {
            background: '#B8BFC9',
            border: '#B8BFC9',
            highlight: { background: accent, border: '#0066FF' },
            hover: { background: accent, border: '#0066FF' },
          },
        font: {
          color: focused ? '#22303c' : 'rgba(34, 48, 60, .48)',
          size: kind === 'type' || kind === 'case' ? 10 : 9,
          face: 'Microsoft YaHei, sans-serif',
          strokeWidth: 0,
        },
        borderWidth: focused && type === 'node' && nodeId === id ? 3 : 1,
      };
    });

    const edgeUpdates = state.edgesData.getIds().map((edgeId) => {
      const focused = focusEdges.has(edgeId);
      return {
        id: edgeId,
        color: {
          color: focused ? (type === 'edge' && edgeId === id ? '#14C9C9' : 'rgba(76, 96, 116, .72)') : 'rgba(120, 136, 152, .38)',
          highlight: '#14C9C9',
          hover: '#14C9C9',
          opacity: focused ? 1 : 0.42,
        },
        font: {
          color: focused ? '#54697a' : 'rgba(84, 105, 122, .42)',
          size: 9,
          face: 'Microsoft YaHei, sans-serif',
          strokeWidth: 0,
          align: 'middle',
        },
        width: focused && type === 'edge' && edgeId === id ? 2.4 : 1,
      };
    });

    try {
      if (nodeUpdates.length) state.nodesData.update(nodeUpdates);
      if (edgeUpdates.length) state.edgesData.update(edgeUpdates);
    } catch (_error) { /* ignore */ }
    if (state.network) {
      try { state.network.redraw(); } catch (_error) { /* ignore */ }
    }
  }

  function clearGraphFocus() {
    state.graphFocus = null;
    setCanvasFocusClass(false);
    if (!state.nodesData || !state.edgesData) return;
    const byId = Object.fromEntries((state.graph.nodes || []).map((node) => [node.id, node]));
    const nodeUpdates = state.nodesData.getIds().map((nodeId) => {
      const node = byId[nodeId] || { id: nodeId, kind: 'detail', label: nodeId };
      const kind = kindOf(node);
      const accent = nodeAccent(kind);
      return {
        id: nodeId,
        opacity: 1,
        color: {
          background: accent,
          border: accent,
          highlight: { background: accent, border: '#0066FF' },
          hover: { background: accent, border: '#0066FF' },
        },
        font: {
          color: '#22303c',
          size: kind === 'type' || kind === 'case' ? 10 : 9,
          face: 'Microsoft YaHei, sans-serif',
          strokeWidth: 0,
        },
        borderWidth: 1,
      };
    });
    const edgeUpdates = state.edgesData.getIds().map((edgeId) => ({
      id: edgeId,
      color: { color: 'rgba(76, 96, 116, .40)', highlight: '#14C9C9', hover: '#14C9C9', opacity: 1 },
      font: { color: '#54697a', size: 9, face: 'Microsoft YaHei, sans-serif', strokeWidth: 0, align: 'middle' },
      width: 1,
    }));
    try {
      if (nodeUpdates.length) state.nodesData.update(nodeUpdates);
      if (edgeUpdates.length) state.edgesData.update(edgeUpdates);
    } catch (_error) { /* ignore */ }
    if (state.network) {
      try { state.network.redraw(); } catch (_error) { /* ignore */ }
    }
  }

  function refreshGraphFocus() {
    if (state.graphFocus && state.graphFocus.id) {
      applyGraphFocus(state.graphFocus.type, state.graphFocus.id);
    } else {
      clearGraphFocus();
    }
  }

  function createNetwork() {
    if (!window.vis) {
      loading.textContent = 'Graph component failed to load. Please refresh the page.';
      return;
    }
    const positions = wreathPositions(state.graph.nodes || [], state.graph.edges || []);
    const nodes = new vis.DataSet((state.graph.nodes || []).map((node) => nodeStyle(node, positions)));
    const edges = new vis.DataSet((state.graph.edges || []).map(edgeStyle));
    state.nodesData = nodes;
    state.edgesData = edges;
    state.network = new vis.Network(container, { nodes, edges }, {
      autoResize: true,
      layout: { improvedLayout: false, randomSeed: 7 },
      physics: {
        enabled: true,
        minVelocity: 0.65,
        maxVelocity: 3.5,
        stabilization: { iterations: 55, updateInterval: 25, fit: true },
        barnesHut: {
          gravitationalConstant: -3600,
          centralGravity: 0.35,
          springLength: 150,
          springConstant: 0.02,
          damping: 0.48,
          avoidOverlap: 1.05,
        },
      },
      interaction: {
        hover: true,
        tooltipDelay: 80,
        zoomView: true,
        dragView: true,
        dragNodes: true,
        hideEdgesOnDrag: true,
        keyboard: { enabled: true },
      },
      nodes: { chosen: true },
      edges: { selectionWidth: 2, hoverWidth: 1.5 },
    });
    state.network.once('stabilizationIterationsDone', () => {
      state.network.setOptions({ physics: state.motion === 'micro' ? motionPhysics('micro') : { enabled: false } });
      if (state.motion === 'micro') keepMicroMotionInView();
      else if (!state.pendingFocusId && state.layout === 'list' && state.listMode === 'dock') {
        window.requestAnimationFrame(() => fitGraphInView(false));
      }
    });
    state.network.on('click', (event) => {
      if (event.nodes && event.nodes.length) {
        const node = state.graph.nodes.find((candidate) => candidate.id === event.nodes[0]);
        if (node) selectNode(node);
        return;
      }
      if (event.edges && event.edges.length) {
        const edge = state.graph.edges.find((candidate) => candidate.id === event.edges[0]);
        if (edge) selectEdge(edge);
        return;
      }
      clearSelection();
    });
    state.network.on('dragEnd', () => {
      if (state.selectedNodeId) positionNodeCard(state.selectedNodeId);
    });
    state.network.on('zoom', () => {
      if (state.selectedNodeId) positionNodeCard(state.selectedNodeId);
    });
    state.network.on('dragging', () => {
      if (state.selectedNodeId) positionNodeCard(state.selectedNodeId);
    });
    hideNodeCard();
    loading.classList.add('is-hidden');
    // Ensure canvas has real pixel size (embedded/preview panes often start at 0),
    // then fit the wreath into view so nodes are not off-screen.
    window.requestAnimationFrame(() => {
      if (!state.network) return;
      try {
        state.network.setSize('100%', '100%');
        state.network.redraw();
      } catch (_error) { /* ignore */ }
      fitGraphInView(false);
    });
  }

  function hideNodeCard() {
    state.selectedNodeId = null;
    state.selectedEdgeId = null;
    cleanupFilterMenus();
    clearGraphFocus();
    if (nodeCard) {
      nodeCard.classList.remove('is-editing');
      nodeCard.hidden = true;
      nodeCard.innerHTML = '';
    }
  }

  function clearSelection() {
    hideNodeCard();
    if (state.network) state.network.unselectAll();
  }

  function positionNodeCard() {
    if (!nodeCard) return;
    nodeCard.hidden = false;
    nodeCard.style.left = '';
    nodeCard.style.right = '';
    const docked = state.layout === 'list' && state.listMode === 'dock' && listPanel && !listPanel.hidden;
    if (docked) {
      const rect = listPanel.getBoundingClientRect();
      nodeCard.style.top = '4px';
      nodeCard.style.maxHeight = Math.max(160, Math.round(rect.height)) + 'px';
    } else {
      nodeCard.style.top = '12px';
      nodeCard.style.maxHeight = '';
    }
  }

  if (nodeCard && !nodeCard.dataset.filterScrollBound) {
    nodeCard.dataset.filterScrollBound = '1';
    const repositionOpenMenus = () => {
      document.querySelectorAll('.node-filter-menu.is-fixed:not([hidden])').forEach((menu) => {
        const ownerId = menu.dataset.filterOwner;
        const wrap = ownerId ? document.getElementById(ownerId) : null;
        const field = wrap && wrap.querySelector('.node-filter-input');
        if (!field) return;
        const rect = field.getBoundingClientRect();
        const spaceBelow = window.innerHeight - rect.bottom - 8;
        const spaceAbove = rect.top - 8;
        const preferUp = spaceBelow < 140 && spaceAbove > spaceBelow;
        menu.style.left = Math.round(rect.left) + 'px';
        menu.style.width = Math.round(rect.width) + 'px';
        menu.style.maxHeight = Math.min(168, Math.max(96, preferUp ? spaceAbove : spaceBelow)) + 'px';
        if (preferUp) {
          menu.style.top = 'auto';
          menu.style.bottom = Math.round(window.innerHeight - rect.top + 4) + 'px';
        } else {
          menu.style.bottom = 'auto';
          menu.style.top = Math.round(rect.bottom + 4) + 'px';
        }
      });
    };
    nodeCard.addEventListener('scroll', repositionOpenMenus, { passive: true });
    window.addEventListener('resize', repositionOpenMenus);
  }

  function cleanupFilterMenus() {
    document.querySelectorAll('.node-filter-menu.is-fixed, .node-filter-menu').forEach((menu) => {
      menu.hidden = true;
      menu.classList.remove('is-fixed');
      if (menu.parentElement === document.body) menu.remove();
    });
    if (nodeCard) {
      nodeCard.querySelectorAll('.node-filter-combo.is-open').forEach((wrap) => {
        wrap.classList.remove('is-open');
      });
    }
  }

  function formatVisNodeLabel(label) {
    const text = String(label || '');
    return text.length > 26 ? `${text.slice(0, 26)}…` : text;
  }

  function ensureEdgeId(edge) {
    if (!edge) return '';
    if (!edge.id) {
      edge.id = 'local-edge:' + Date.now() + ':' + Math.random().toString(36).slice(2, 8);
    }
    return edge.id;
  }

  function syncNodeNeighborhood(nodeId) {
    if (!nodeId) return;
    const node = state.graph.nodes.find((candidate) => candidate.id === nodeId);
    if (node && state.nodesData) {
      try {
        state.nodesData.update({
          id: node.id,
          label: formatVisNodeLabel(node.label || node.id),
        });
      } catch (_error) { /* ignore */ }
    }

    if (!state.edgesData) return;
    const liveEdges = nodeEdges(nodeId);
    const liveIds = new Set();
    liveEdges.forEach((edge) => {
      const id = ensureEdgeId(edge);
      liveIds.add(id);
      const styled = edgeStyle(edge);
      try {
        if (state.edgesData.get(id)) state.edgesData.update(styled);
        else state.edgesData.add(styled);
      } catch (_error) {
        try { state.edgesData.update(styled); } catch (__error) { /* ignore */ }
      }

      const otherId = edge.source === nodeId ? edge.target : edge.source;
      const other = state.graph.nodes.find((candidate) => candidate.id === otherId);
      if (other && state.nodesData) {
        try {
          if (state.nodesData.get(otherId)) {
            state.nodesData.update({
              id: otherId,
              label: formatVisNodeLabel(other.label || otherId),
            });
          } else {
            let point = { x: 0, y: 0 };
            if (state.network) {
              const anchor = state.network.getPositions([nodeId])[nodeId];
              if (anchor) point = { x: anchor.x + 70, y: anchor.y + 36 };
            }
            state.nodesData.add(nodeStyle(other, { [otherId]: point }));
          }
        } catch (_error) { /* ignore */ }
      }
    });

    (state.edgesData.get() || []).forEach((visEdge) => {
      if (!visEdge || !visEdge.id) return;
      const touches = visEdge.from === nodeId || visEdge.to === nodeId;
      if (touches && !liveIds.has(visEdge.id)) {
        try { state.edgesData.remove(visEdge.id); } catch (_error) { /* ignore */ }
      }
    });

    if (state.network) {
      try { state.network.redraw(); } catch (_error) { /* ignore */ }
    }
    refreshGraphFocus();
  }

  function applyNodeLabel(nodeId, label) {
    if (!nodeId || label == null) return;
    const text = String(label).replace(/\s+/g, ' ').trim();
    if (!text) return;
    const node = state.graph.nodes.find((candidate) => candidate.id === nodeId);
    if (node) node.label = text;
    if (state.nodesData) {
      try {
        state.nodesData.update({ id: nodeId, label: formatVisNodeLabel(text) });
      } catch (_error) { /* ignore missing node */ }
    }
    if (list) {
      try {
        const listRow = list.querySelector(`.list-row[data-case-id="${CSS.escape(nodeId)}"]`);
        if (listRow) {
          const name = listRow.querySelector('.list-case-name');
          if (name) name.textContent = text;
        }
      } catch (_error) { /* ignore invalid selectors */ }
    }
  }

  function nodeEdges(nodeId) {
    return (state.graph.edges || []).filter((edge) => edge.source === nodeId || edge.target === nodeId);
  }

  function refreshNodeIcons(root) {
    if (window.workbench && typeof window.workbench.icons === 'function') window.workbench.icons(root);
    else if (window.lucide && typeof window.lucide.createIcons === 'function') window.lucide.createIcons({ root: root || undefined });
  }

  function fitEditField(field) {
    if (!field) return;
    if (field.tagName === 'TEXTAREA') {
      field.style.height = '0px';
      const next = Math.min(96, Math.max(30, field.scrollHeight));
      field.style.height = next + 'px';
    }
  }

  function relationOptions() {
    // Canonical relations used by /api/graph/data, plus any extras already on the loaded graph.
    const values = new Set(['包含用例', '前提条件', '执行动作', '预期行为']);
    (state.graph.edges || []).forEach((edge) => {
      const relation = String(edge.relation || edge.label || '').replace(/\s+/g, ' ').trim();
      if (relation) values.add(relation);
    });
    const preferred = ['包含用例', '前提条件', '执行动作', '预期行为'];
    const rest = Array.from(values)
      .filter((item) => !preferred.includes(item))
      .sort((a, b) => a.localeCompare(b, 'zh-CN'));
    return preferred.filter((item) => values.has(item)).concat(rest);
  }

  function nodeOptions(excludeId) {
    return (state.graph.nodes || [])
      .filter((node) => node && node.id && node.id !== excludeId)
      .map((node) => ({
        id: node.id,
        label: String(node.label || node.case_number || node.id).replace(/\s+/g, ' ').trim() || node.id,
        kind: node.kind || '',
      }))
      .sort((a, b) => a.label.localeCompare(b.label, 'zh-CN'));
  }

  function confirmConnectionDelete(message) {
    const modal = document.getElementById('graphConnectionDeleteModal');
    const messageEl = document.getElementById('graphConnectionDeleteMessage');
    const confirmBtn = document.getElementById('graphConnectionDeleteConfirm');
    const cancelBtn = document.getElementById('graphConnectionDeleteCancel');
    const closeBtn = document.getElementById('graphConnectionDeleteClose');
    if (!modal || !confirmBtn || !cancelBtn) {
      return Promise.resolve(window.confirm(message || 'Delete this connection?'));
    }
    if (messageEl) messageEl.textContent = message || 'Delete this connection? Changes apply to the graph after you save.';
    modal.hidden = false;
    return new Promise((resolve) => {
      const finish = (ok) => {
        modal.hidden = true;
        confirmBtn.removeEventListener('click', onConfirm);
        cancelBtn.removeEventListener('click', onCancel);
        if (closeBtn) closeBtn.removeEventListener('click', onCancel);
        modal.removeEventListener('click', onBackdrop);
        document.removeEventListener('keydown', onKey);
        resolve(ok);
      };
      const onConfirm = (event) => {
        event.preventDefault();
        finish(true);
      };
      const onCancel = (event) => {
        event.preventDefault();
        finish(false);
      };
      const onBackdrop = (event) => {
        if (event.target === modal) finish(false);
      };
      const onKey = (event) => {
        if (event.key === 'Escape') finish(false);
      };
      confirmBtn.addEventListener('click', onConfirm);
      cancelBtn.addEventListener('click', onCancel);
      if (closeBtn) closeBtn.addEventListener('click', onCancel);
      modal.addEventListener('click', onBackdrop);
      document.addEventListener('keydown', onKey);
      window.setTimeout(() => confirmBtn.focus(), 0);
    });
  }

  function bindDetailActions(root) {
    if (!root) return;

    root.querySelectorAll('.connection-row[data-connected-id]').forEach((item) => {
      item.addEventListener('click', (event) => {
        if (root.classList.contains('is-editing')) return;
        if (event.target.closest('[data-delete-connection], [data-add-connection], .node-filter-combo')) return;
        event.stopPropagation();
        const connected = state.graph.nodes.find((candidate) => candidate.id === item.dataset.connectedId);
        if (connected) selectNode(connected);
      });
    });

    const editBtn = root.querySelector('[data-node-edit], [data-edge-edit]');
    const saveBtn = root.querySelector('[data-node-save], [data-edge-save]');
    const cancelBtn = root.querySelector('[data-node-cancel], [data-edge-cancel]');
    const addBtn = root.querySelector('[data-add-connection]');
    const isEdgeCard = !!root.querySelector('[data-edge-edit]');
    if (!editBtn || !saveBtn || !cancelBtn) return;

    let snapshot = null;

    function mountField(sourceEl, options) {
      if (!sourceEl) return null;
      const initial = (options.value != null ? String(options.value) : (sourceEl.textContent || '')).replace(/\s+/g, ' ').trim();
      sourceEl.setAttribute('data-display-text', initial);
      sourceEl.hidden = true;
      sourceEl.removeAttribute('contenteditable');
      const multiline = !!options.multiline || initial.length > 36;
      const field = document.createElement(multiline ? 'textarea' : 'input');
      field.className = 'node-edit-field' + (multiline ? ' is-multiline' : '');
      if (!multiline) field.type = 'text';
      field.value = initial;
      field.dataset.editKind = options.kind || '';
      if (options.field) field.dataset.editField = options.field;
      if (options.edgeIndex != null) field.dataset.edgeIndex = String(options.edgeIndex);
      if (options.connectedId) field.dataset.connectedId = options.connectedId;
      if (multiline) field.rows = 1;
      const connectionField = sourceEl.closest('.connection-field');
      if (connectionField) connectionField.appendChild(field);
      else sourceEl.insertAdjacentElement('afterend', field);
      field.addEventListener('input', () => fitEditField(field));
      fitEditField(field);
      return field;
    }

    function mountFilterField(sourceEl, options) {
      if (!sourceEl) return null;
      const initial = (options.value != null ? String(options.value) : (sourceEl.textContent || '')).replace(/\s+/g, ' ').trim();
      sourceEl.setAttribute('data-display-text', initial);
      sourceEl.hidden = true;
      const wrap = document.createElement('div');
      wrap.className = 'node-filter-combo';
      wrap.dataset.editKind = options.kind || '';
      if (options.edgeIndex != null) wrap.dataset.edgeIndex = String(options.edgeIndex);
      if (options.connectedId) wrap.dataset.connectedId = options.connectedId;
      if (options.selectedId) wrap.dataset.selectedId = options.selectedId;

      const field = document.createElement('input');
      field.type = 'text';
      field.className = 'node-edit-field node-filter-input';
      field.autocomplete = 'off';
      field.spellcheck = false;
      field.placeholder = options.placeholder || 'Filter';
      field.value = initial;
      field.dataset.editKind = options.kind || '';
      if (options.edgeIndex != null) field.dataset.edgeIndex = String(options.edgeIndex);
      if (options.connectedId) field.dataset.connectedId = options.connectedId;
      if (options.selectedId) field.dataset.selectedId = options.selectedId;

      const caret = document.createElement('button');
      caret.type = 'button';
      caret.className = 'node-filter-caret';
      caret.setAttribute('aria-label', 'Open dropdown');
      caret.tabIndex = -1;

      const menu = document.createElement('div');
      menu.className = 'node-filter-menu';
      menu.hidden = true;
      menu.setAttribute('role', 'listbox');

      const choices = options.choices || [];
      const maxVisible = options.maxVisible || (options.kind === 'relation' ? 50 : 250);

      function closeMenu() {
        menu.hidden = true;
        wrap.classList.remove('is-open');
        const row = wrap.closest('.connection-row');
        if (row) row.style.zIndex = '';
        if (menu.parentElement !== wrap) wrap.appendChild(menu);
        menu.classList.remove('is-fixed');
        menu.style.left = '';
        menu.style.top = '';
        menu.style.width = '';
        menu.style.bottom = '';
        menu.style.maxHeight = '';
        delete menu.dataset.filterOwner;
      }

      function placeMenu() {
        const rect = field.getBoundingClientRect();
        const spaceBelow = window.innerHeight - rect.bottom - 8;
        const spaceAbove = rect.top - 8;
        const preferUp = spaceBelow < 160 && spaceAbove > spaceBelow;
        const maxH = Math.min(220, Math.max(120, preferUp ? spaceAbove : spaceBelow));
        if (!wrap.id) wrap.id = 'nfc-' + Math.random().toString(36).slice(2, 9);
        menu.dataset.filterOwner = wrap.id;
        document.body.appendChild(menu);
        menu.classList.add('is-fixed');
        menu.style.width = Math.round(rect.width) + 'px';
        menu.style.left = Math.round(rect.left) + 'px';
        menu.style.maxHeight = maxH + 'px';
        if (preferUp) {
          menu.style.top = 'auto';
          menu.style.bottom = Math.round(window.innerHeight - rect.top + 4) + 'px';
        } else {
          menu.style.bottom = 'auto';
          menu.style.top = Math.round(rect.bottom + 4) + 'px';
        }
      }

      function pickOption(btn) {
        if (!btn) return;
        field.value = btn.getAttribute('data-value') || '';
        const id = btn.getAttribute('data-id') || '';
        if (id) {
          field.dataset.selectedId = id;
          wrap.dataset.selectedId = id;
          wrap.dataset.connectedId = id;
          field.dataset.connectedId = id;
          const row = wrap.closest('.connection-row');
          if (row) row.setAttribute('data-connected-id', id);
        } else {
          delete field.dataset.selectedId;
          delete wrap.dataset.selectedId;
        }
        closeMenu();
        field.focus();
      }

      function renderMenu(query) {
        const q = String(query || '').trim().toLowerCase();
        const matched = choices.filter((item) => {
          if (!q) return true;
          if (typeof item === 'string') return String(item).toLowerCase().includes(q);
          const label = String(item.label || '').toLowerCase();
          const id = String(item.id || '').toLowerCase();
          return label.includes(q) || id.includes(q);
        });
        const visible = matched.slice(0, maxVisible);
        if (!matched.length) {
          menu.innerHTML = '<div class="node-filter-empty">No matches</div>';
        } else {
          const rows = visible.map((item) => {
            if (typeof item === 'string') {
              return `<button type="button" class="node-filter-option" role="option" data-value="${esc(item)}">${esc(item)}</button>`;
            }
            const meta = item.kind ? `<small>${esc(item.kind)} · ${esc(item.id)}</small>` : `<small>${esc(item.id)}</small>`;
            return `<button type="button" class="node-filter-option" role="option" data-id="${esc(item.id)}" data-value="${esc(item.label)}"><span>${esc(item.label)}</span>${meta}</button>`;
          });
          if (matched.length > visible.length) {
            rows.push(`<div class="node-filter-empty">Showing first ${visible.length} / ${matched.length} items; type to filter further</div>`);
          }
          menu.innerHTML = rows.join('');
          menu.querySelectorAll('.node-filter-option').forEach((btn) => {
            btn.addEventListener('mousedown', (event) => {
              event.preventDefault();
              event.stopPropagation();
              pickOption(btn);
            });
          });
        }
        wrap.classList.add('is-open');
        const row = wrap.closest('.connection-row');
        if (row) row.style.zIndex = '20';
        placeMenu();
        menu.hidden = false;
      }

      field.addEventListener('focus', () => renderMenu(field.value));
      field.addEventListener('click', () => {
        if (menu.hidden) renderMenu(field.value);
      });
      caret.addEventListener('mousedown', (event) => {
        event.preventDefault();
        event.stopPropagation();
        if (menu.hidden) {
          field.focus();
          renderMenu(field.value);
        } else {
          closeMenu();
        }
      });
      field.addEventListener('input', () => {
        delete field.dataset.selectedId;
        delete wrap.dataset.selectedId;
        renderMenu(field.value);
      });
      field.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') {
          closeMenu();
          return;
        }
        if (event.key === 'ArrowDown' || event.key === 'Enter') {
          const first = menu.querySelector('.node-filter-option');
          if (event.key === 'Enter' && first && !menu.hidden) {
            event.preventDefault();
            pickOption(first);
          } else if (event.key === 'ArrowDown' && menu.hidden) {
            event.preventDefault();
            renderMenu(field.value);
          }
        }
      });
      field.addEventListener('blur', () => {
        window.setTimeout(() => {
          if (!wrap.contains(document.activeElement) && !menu.contains(document.activeElement)) {
            closeMenu();
          }
        }, 120);
      });

      wrap.appendChild(field);
      wrap.appendChild(caret);
      wrap.appendChild(menu);
      const connectionField = sourceEl.closest('.connection-field');
      if (connectionField) connectionField.appendChild(wrap);
      else sourceEl.insertAdjacentElement('afterend', wrap);
      return field;
    }

    function bindRowDelete(btn) {
      if (!btn || btn.dataset.boundDelete === '1') return;
      btn.dataset.boundDelete = '1';
      btn.addEventListener('click', async (event) => {
        event.preventDefault();
        event.stopPropagation();
        if (!root.classList.contains('is-editing')) return;
        const row = btn.closest('.connection-row');
        if (!row) return;
        cleanupFilterMenus();

        const relationText = (
          (row.querySelector('.node-edit-field[data-edit-kind="relation"]') || {}).value
          || (row.querySelector('[data-edit-relation]') || {}).textContent
          || 'Relation'
        ).replace(/\s+/g, ' ').trim();
        const nodeText = (
          (row.querySelector('.node-edit-field[data-edit-kind="connected"]') || {}).value
          || (row.querySelector('[data-conn-label]') || {}).textContent
          || row.getAttribute('data-connected-id')
          || 'Untitled node'
        ).replace(/\s+/g, ' ').trim();
        const isDraft = row.classList.contains('is-draft');
        const ok = await confirmConnectionDelete(
          isDraft
            ? `Delete unsaved connection “${relationText} → ${nodeText}”?`
            : `Delete connection “${relationText} → ${nodeText}”? It will be removed from the graph after you save.`
        );
        if (!ok || !row.isConnected) return;

        const index = Number(row.getAttribute('data-edge-index'));
        if (isDraft) {
          row.remove();
        } else if (Number.isFinite(index)) {
          const edges = nodeEdges(state.selectedNodeId);
          const target = edges[index];
          if (target) {
            state.graph.edges = state.graph.edges.filter((edge) => edge !== target);
          }
          row.remove();
          root.querySelectorAll('.connection-row:not(.is-draft)').forEach((item, idx) => {
            item.setAttribute('data-edge-index', String(idx));
            item.querySelectorAll('[data-edge-index]').forEach((field) => {
              field.dataset.edgeIndex = String(idx);
            });
          });
        }
        const degreeEl = root.querySelector('[data-degree-value]');
        const node = state.graph.nodes.find((candidate) => candidate.id === state.selectedNodeId);
        if (degreeEl && node) {
          node.degree = nodeEdges(node.id).length || 0;
          degreeEl.textContent = String(node.degree || 0);
        }
      });
    }

    function resolveConnected(field, row) {
      const text = field ? field.value.replace(/\s+/g, ' ').trim() : '';
      const selectedId = (field && field.dataset.selectedId) || (row && row.getAttribute('data-connected-id')) || '';
      if (selectedId) {
        const exists = state.graph.nodes.find((item) => item.id === selectedId);
        if (exists) return { id: exists.id, label: exists.label || text || exists.id };
      }
      if (!text) return { id: '', label: '' };
      const byLabel = state.graph.nodes.find((item) => String(item.label || '').trim() === text);
      if (byLabel) return { id: byLabel.id, label: byLabel.label || text };
      return { id: '', label: text };
    }

    function mountRowFields(row) {
      const edgeIndex = row.getAttribute('data-edge-index');
      const connectedId = row.getAttribute('data-connected-id') || '';
      const relationEl = row.querySelector('[data-edit-relation]');
      const labelEl = row.querySelector('[data-conn-label]');
      mountFilterField(relationEl, {
        kind: 'relation',
        edgeIndex,
        placeholder: 'Filter existing relations',
        choices: relationOptions(),
        value: relationEl ? relationEl.getAttribute('data-display-text') || relationEl.textContent : '',
      });
      mountFilterField(labelEl, {
        kind: 'connected',
        connectedId,
        selectedId: connectedId,
        placeholder: 'Filter existing nodes',
        choices: nodeOptions(state.selectedNodeId),
        value: labelEl ? labelEl.getAttribute('data-display-text') || labelEl.textContent : '',
      });
      const del = row.querySelector('[data-delete-connection]');
      if (del) {
        del.hidden = false;
        bindRowDelete(del);
        refreshNodeIcons(del);
      }
    }

    if (isEdgeCard) {
      function exitToEdgeCard(edgeId) {
        cleanupFilterMenus();
        const id = edgeId || state.selectedEdgeId;
        const edge = (state.graph.edges || []).find((candidate) => candidate.id === id);
        if (edge) {
          try {
            selectEdge(edge);
            return;
          } catch (error) {
            console.error(error);
          }
        }
        root.classList.remove('is-editing');
        editBtn.hidden = false;
        saveBtn.hidden = true;
        cancelBtn.hidden = true;
      }

      function resolveEdgeEndpoint(field, fallbackId) {
        const text = field ? field.value.replace(/\s+/g, ' ').trim() : '';
        const selectedId = (field && field.dataset.selectedId) || fallbackId || '';
        if (selectedId) {
          const exists = state.graph.nodes.find((item) => item.id === selectedId);
          if (exists) return exists.id;
        }
        if (!text) return fallbackId || '';
        const byLabel = state.graph.nodes.find((item) => String(item.label || '').trim() === text);
        if (byLabel) return byLabel.id;
        const byId = state.graph.nodes.find((item) => item.id === text);
        return byId ? byId.id : (fallbackId || text);
      }

      editBtn.addEventListener('click', (event) => {
        event.stopPropagation();
        if (root.classList.contains('is-editing')) return;
        const edge = (state.graph.edges || []).find((candidate) => candidate.id === state.selectedEdgeId);
        if (!edge) return;
        snapshot = {
          edgeId: edge.id,
          relation: edge.relation || edge.label || '',
          source: edge.source,
          target: edge.target,
          label: edge.label || edge.relation || '',
        };
        root.classList.add('is-editing');
        editBtn.hidden = true;
        saveBtn.hidden = false;
        cancelBtn.hidden = false;
        positionNodeCard();

        const relationEl = root.querySelector('[data-edge-relation]');
        const sourceEl = root.querySelector('[data-edge-source]');
        const targetEl = root.querySelector('[data-edge-target]');
        mountFilterField(relationEl, {
          kind: 'relation',
          placeholder: 'Filter existing relations',
          choices: relationOptions(),
          value: edge.relation || edge.label || '',
        });
        mountFilterField(sourceEl, {
          kind: 'connected',
          selectedId: edge.source,
          connectedId: edge.source,
          placeholder: 'Filter source node',
          choices: nodeOptions(),
          value: sourceEl ? sourceEl.getAttribute('data-display-text') || sourceEl.textContent : '',
        });
        mountFilterField(targetEl, {
          kind: 'connected',
          selectedId: edge.target,
          connectedId: edge.target,
          placeholder: 'Filter target node',
          choices: nodeOptions(),
          value: targetEl ? targetEl.getAttribute('data-display-text') || targetEl.textContent : '',
        });
        const focusField = root.querySelector('.node-edit-field[data-edit-kind="relation"]');
        if (focusField) {
          focusField.focus();
          focusField.select();
        }
      });

      cancelBtn.addEventListener('click', (event) => {
        event.preventDefault();
        event.stopPropagation();
        cleanupFilterMenus();
        if (snapshot) {
          const edge = (state.graph.edges || []).find((candidate) => candidate.id === snapshot.edgeId);
          if (edge) {
            edge.relation = snapshot.relation;
            edge.label = snapshot.label || snapshot.relation;
            edge.source = snapshot.source;
            edge.target = snapshot.target;
            syncNodeNeighborhood(edge.source);
            syncNodeNeighborhood(edge.target);
          }
          exitToEdgeCard(snapshot.edgeId);
          snapshot = null;
          return;
        }
        exitToEdgeCard();
      });

      saveBtn.addEventListener('click', (event) => {
        event.preventDefault();
        event.stopPropagation();
        cleanupFilterMenus();
        try {
          const edgeId = state.selectedEdgeId;
          const edge = (state.graph.edges || []).find((candidate) => candidate.id === edgeId);
          if (!edge) {
            exitToEdgeCard(edgeId);
            return;
          }
          const prevSource = edge.source;
          const prevTarget = edge.target;
          const relationField = root.querySelector('.node-edit-field[data-edit-kind="relation"]');
          const sourceField = root.querySelectorAll('.node-edit-field[data-edit-kind="connected"]')[0];
          const targetField = root.querySelectorAll('.node-edit-field[data-edit-kind="connected"]')[1];
          const nextRelation = relationField
            ? relationField.value.replace(/\s+/g, ' ').trim()
            : (edge.relation || edge.label || 'Relation');
          if (nextRelation) {
            edge.relation = nextRelation;
            edge.label = nextRelation;
          }
          edge.source = resolveEdgeEndpoint(sourceField, edge.source) || edge.source;
          edge.target = resolveEdgeEndpoint(targetField, edge.target) || edge.target;
          syncNodeNeighborhood(prevSource);
          if (prevTarget !== prevSource) syncNodeNeighborhood(prevTarget);
          syncNodeNeighborhood(edge.source);
          if (edge.target !== edge.source) syncNodeNeighborhood(edge.target);
          snapshot = null;
          exitToEdgeCard(edgeId);
        } catch (error) {
          console.error(error);
          exitToEdgeCard(state.selectedEdgeId);
        }
      });

      root.addEventListener('keydown', (event) => {
        if (!root.classList.contains('is-editing')) return;
        if (event.key === 'Escape') {
          event.preventDefault();
          cancelBtn.click();
        }
      });
      return;
    }

    function enterEditMode() {
      if (root.classList.contains('is-editing')) return;
      const nodeId = state.selectedNodeId;
      const node = state.graph.nodes.find((candidate) => candidate.id === nodeId);
      // Only snapshot what edit mode can change: current node fields + edge list.
      // Never clone the full node catalog (can be thousands of items).
      snapshot = {
        nodeId,
        label: node ? node.label : '',
        case_number: node ? node.case_number : '',
        case_type: node ? node.case_type : '',
        degree: node ? node.degree : 0,
        edges: (state.graph.edges || []).map((edge) => Object.assign({}, edge)),
      };
      root.classList.add('is-editing');
      editBtn.hidden = true;
      saveBtn.hidden = false;
      cancelBtn.hidden = false;
      if (addBtn) addBtn.hidden = false;
      positionNodeCard();

      const titleEl = root.querySelector('[data-node-label]');
      const titleField = mountField(titleEl, {
        kind: 'label',
        multiline: true,
        value: node ? node.label : (titleEl && titleEl.textContent),
      });
      root.querySelectorAll('[data-edit-value]').forEach((el) => {
        const fieldName = el.getAttribute('data-edit-value') || '';
        const value = fieldName === 'case_number'
          ? (node && (node.case_number || node.id)) || el.textContent
          : fieldName === 'case_type'
            ? (node && node.case_type) || el.textContent
            : el.textContent;
        mountField(el, { kind: 'value', field: fieldName, value });
      });
      root.querySelectorAll('.connection-row').forEach(mountRowFields);
      if (titleField) {
        titleField.focus();
        titleField.select();
      }
    }

    function exitToCard(nodeId) {
      cleanupFilterMenus();
      const id = nodeId || state.selectedNodeId;
      const node = state.graph.nodes.find((candidate) => candidate.id === id);
      if (node) {
        try {
          selectNode(node);
          return;
        } catch (error) {
          console.error(error);
        }
      }
      root.classList.remove('is-editing');
      editBtn.hidden = false;
      saveBtn.hidden = true;
      cancelBtn.hidden = true;
      if (addBtn) addBtn.hidden = true;
    }

    editBtn.addEventListener('click', (event) => {
      event.stopPropagation();
      enterEditMode();
    });

    cancelBtn.addEventListener('click', (event) => {
      event.preventDefault();
      event.stopPropagation();
      cleanupFilterMenus();
      if (snapshot) {
        state.graph.edges = snapshot.edges.map((edge) => Object.assign({}, edge));
        const node = state.graph.nodes.find((candidate) => candidate.id === snapshot.nodeId);
        if (node) {
          node.label = snapshot.label;
          node.case_number = snapshot.case_number;
          node.case_type = snapshot.case_type;
          node.degree = snapshot.degree;
          if (snapshot.label) applyNodeLabel(node.id, snapshot.label);
        }
        syncNodeNeighborhood(snapshot.nodeId);
        exitToCard(snapshot.nodeId);
        snapshot = null;
        return;
      }
      exitToCard();
    });

    saveBtn.addEventListener('click', (event) => {
      event.preventDefault();
      event.stopPropagation();
      cleanupFilterMenus();
      try {
        const nodeId = state.selectedNodeId;
        const node = state.graph.nodes.find((candidate) => candidate.id === nodeId);
        const labelField = root.querySelector('.node-edit-field[data-edit-kind="label"]');
        const nextLabel = labelField
          ? labelField.value.replace(/\s+/g, ' ').trim()
          : (node && node.label) || '';
        applyNodeLabel(nodeId, nextLabel || (snapshot && snapshot.label) || (node && node.label) || '');

        root.querySelectorAll('.node-edit-field[data-edit-kind="value"]').forEach((field) => {
          if (!node) return;
          const value = field.value.replace(/\s+/g, ' ').trim();
          if (field.dataset.editField === 'case_number' && value) node.case_number = value;
          if (field.dataset.editField === 'case_type' && value) node.case_type = value;
        });

        const edges = nodeEdges(nodeId);
        root.querySelectorAll('.connection-row:not(.is-draft)').forEach((row) => {
          const index = Number(row.getAttribute('data-edge-index'));
          const edge = edges[index];
          if (!edge) return;
          const relationField = row.querySelector('.node-edit-field[data-edit-kind="relation"]');
          const connectedField = row.querySelector('.node-edit-field[data-edit-kind="connected"]');
          const nextRelation = relationField
            ? relationField.value.replace(/\s+/g, ' ').trim()
            : (edge.relation || edge.label || 'Relation');
          if (nextRelation) {
            edge.relation = nextRelation;
            edge.label = nextRelation;
          }
          const resolved = resolveConnected(connectedField, row);
          if (resolved.id) {
            if (edge.source === nodeId) edge.target = resolved.id;
            else edge.source = resolved.id;
            row.setAttribute('data-connected-id', resolved.id);
          } else if (resolved.label) {
            const currentId = row.getAttribute('data-connected-id') || '';
            if (currentId) applyNodeLabel(currentId, resolved.label);
          }
        });

        root.querySelectorAll('.connection-row.is-draft').forEach((row) => {
          const relationField = row.querySelector('.node-edit-field[data-edit-kind="relation"]');
          const connectedField = row.querySelector('.node-edit-field[data-edit-kind="connected"]');
          const relation = (relationField && relationField.value.replace(/\s+/g, ' ').trim()) || 'Relation';
          const resolved = resolveConnected(connectedField, row);
          if (!resolved.id && !resolved.label) return;
          let targetId = resolved.id;
          if (!targetId) {
            targetId = 'local:' + Date.now() + ':' + Math.random().toString(36).slice(2, 7);
            const newNode = { id: targetId, label: resolved.label, kind: 'detail', degree: 1 };
            state.graph.nodes.push(newNode);
          }
          const edge = {
            id: 'local-edge:' + Date.now() + ':' + Math.random().toString(36).slice(2, 8),
            source: nodeId,
            target: targetId,
            relation,
            label: relation,
          };
          state.graph.edges.push(edge);
        });

        if (node) node.degree = nodeEdges(node.id).length || 1;
        syncNodeNeighborhood(nodeId);
        snapshot = null;
        exitToCard(nodeId);
      } catch (error) {
        console.error(error);
        exitToCard(state.selectedNodeId);
      }
    });

    if (addBtn) {
      addBtn.addEventListener('click', (event) => {
        event.preventDefault();
        event.stopPropagation();
        if (!root.classList.contains('is-editing')) return;
        const listEl = root.querySelector('.node-connections-list');
        if (!listEl) return;
        const empty = listEl.querySelector('.inspector-empty');
        if (empty) empty.remove();
        const row = document.createElement('div');
        row.className = 'connection-row is-draft';
        row.setAttribute('data-connected-id', '');
        row.innerHTML = '<span class="connection-direction">→</span><span class="connection-main"><span class="connection-field"><span class="connection-field-label">Relation:</span><span data-edit-relation>Relation</span></span><span class="connection-field"><span class="connection-field-label">Node:</span><span data-conn-label></span></span></span><button type="button" class="connection-delete" data-delete-connection title="Delete connection" aria-label="Delete connection"><i data-lucide="trash-2"></i></button>';
        listEl.appendChild(row);
        refreshNodeIcons(row);
        mountRowFields(row);
        const focusField = row.querySelector('.node-edit-field[data-edit-kind="connected"]');
        if (focusField) focusField.focus();
      });
    }

    root.addEventListener('keydown', (event) => {
      if (!root.classList.contains('is-editing')) return;
      if (event.key === 'Escape') {
        event.preventDefault();
        cancelBtn.click();
      }
    });
  }

  function renderDetails(markup) {
    if (nodeCard) {
      nodeCard.classList.remove('is-editing');
      cleanupFilterMenus();
      nodeCard.innerHTML = markup;
      refreshNodeIcons(nodeCard);
      bindDetailActions(nodeCard);
    }
  }

  function selectNode(node) {
    const kind = node.kind === 'category' ? 'type' : node.kind;
    const kindLabel = kindLabels[kind] || 'Business Entity';
    const typeProperty = kind === 'case' && node.case_type
      ? `<div class="node-property"><span>Test Type</span><b data-edit-value="case_type">${esc(node.case_type)}</b></div>`
      : '';
    const byId = Object.fromEntries((state.graph.nodes || []).map((candidate) => [candidate.id, candidate]));
    const connections = nodeEdges(node.id);
    const connectionRows = connections.map((edge, index) => {
      const outgoing = edge.source === node.id;
      const otherId = outgoing ? edge.target : edge.source;
      const other = byId[otherId];
      const relation = edge.relation || edge.label || 'Relation';
      const otherLabel = other ? other.label : otherId;
      return `<div class="connection-row" data-connected-id="${esc(otherId || '')}" data-edge-index="${index}" role="button" tabindex="0"><span class="connection-direction">${outgoing ? '→' : '←'}</span><span class="connection-main"><span class="connection-field"><span class="connection-field-label">Relation:</span><span data-edit-relation>${esc(relation)}</span></span><span class="connection-field"><span class="connection-field-label">Node:</span><span data-conn-label>${esc(otherLabel)}</span></span></span><button type="button" class="connection-delete" data-delete-connection title="Delete connection" aria-label="Delete connection" hidden><i data-lucide="trash-2"></i></button></div>`;
    }).join('');
    const connectionMarkup = `<div class="node-connections"><div class="node-connections-head"><h4>Connected Nodes & Relations</h4><button type="button" class="node-add-connection" data-add-connection title="Add node" aria-label="Add node" hidden><i data-lucide="plus"></i></button></div><div class="node-connections-list">${connectionRows || '<p class="inspector-empty">No connections yet.</p>'}</div></div>`;
    const markup = `<div class="node-card-head"><p class="node-type">${kindLabel}</p><div class="node-card-actions"><button type="button" class="node-card-action" data-node-edit>Edit</button><button type="button" class="node-card-action is-primary" data-node-save hidden>Save</button><button type="button" class="node-card-action" data-node-cancel hidden>Discard</button></div></div><h3 class="node-title" data-node-label>${esc(node.label || '')}</h3><div class="node-property"><span>Node ID</span><b data-edit-value="case_number">${esc(node.case_number || node.id)}</b></div>${typeProperty}<div class="node-property"><span>Connection Count</span><b data-degree-value>${node.degree || connections.length || 1}</b></div>${connectionMarkup}`;
    state.selectedNodeId = node.id;
    state.selectedEdgeId = null;
    renderDetails(markup);
    positionNodeCard();
    applyGraphFocus('node', node.id);
    const selectedId = node.id;
    window.setTimeout(() => {
      if (!state.network || state.selectedNodeId !== selectedId) return;
      try { state.network.selectNodes([selectedId]); } catch (_error) { /* ignore */ }
    }, 0);
  }

  function selectEdge(edge) {
    state.selectedNodeId = null;
    state.selectedEdgeId = edge.id;
    const sourceNode = (state.graph.nodes || []).find((candidate) => candidate.id === edge.source);
    const targetNode = (state.graph.nodes || []).find((candidate) => candidate.id === edge.target);
    const sourceLabel = sourceNode ? (sourceNode.label || edge.source) : edge.source;
    const targetLabel = targetNode ? (targetNode.label || edge.target) : edge.target;
    const relationName = edge.relation || edge.label || 'Relation';
    const markup = `<div class="node-card-head"><p class="node-type">Triple Relation</p><div class="node-card-actions"><button type="button" class="node-card-action" data-edge-edit>Edit</button><button type="button" class="node-card-action is-primary" data-edge-save hidden>Save</button><button type="button" class="node-card-action" data-edge-cancel hidden>Discard</button></div></div><h3 class="node-title">${esc(relationName)}</h3><div class="node-property"><span>Relation Name</span><b data-edge-relation>${esc(relationName)}</b></div><div class="node-property"><span>Source</span><b data-edge-source data-node-id="${esc(edge.source || '')}">${esc(sourceLabel)}</b></div><div class="node-property"><span>Target</span><b data-edge-target data-node-id="${esc(edge.target || '')}">${esc(targetLabel)}</b></div>`;
    renderDetails(markup);
    if (nodeCard) {
      nodeCard.hidden = false;
      positionNodeCard();
    }
    applyGraphFocus('edge', edge.id);
    const selectedId = edge.id;
    window.setTimeout(() => {
      if (!state.network || state.selectedEdgeId !== selectedId) return;
      try { state.network.selectEdges([selectedId]); } catch (_error) { /* ignore */ }
    }, 0);
  }

  function motionPhysics(mode) {
    if (mode !== 'micro') return { enabled: false };
    return {
      enabled: true,
      minVelocity: 0.015,
      maxVelocity: 0.18,
      timestep: 0.18,
      stabilization: { enabled: false },
      barnesHut: {
        gravitationalConstant: -480,
        centralGravity: 0.85,
        springLength: 150,
        springConstant: 0.01,
        damping: 0.98,
        avoidOverlap: 1.1,
      },
    };
  }

  let motionWatchRaf = 0;
  let motionWatchTicks = 0;
  function stopMotionWatch() {
    if (motionWatchRaf) {
      window.cancelAnimationFrame(motionWatchRaf);
      motionWatchRaf = 0;
    }
    motionWatchTicks = 0;
  }

  function listDockShiftX() {
    const docked = state.layout === 'list' && state.listMode === 'dock';
    if (!docked || !listPanel || listPanel.hidden) return 0;
    return listPanel.getBoundingClientRect().width / 2;
  }

  function fitGraphInView(animate) {
    if (!state.network) return;
    const shift = listDockShiftX();
    const motion = animate
      ? { duration: 350, easingFunction: 'easeInOutCubic' }
      : false;
    if (!shift) {
      state.network.fit({ animation: motion });
      return;
    }
    // Fit to full canvas first, then shift into the uncovered left region.
    state.network.fit({ animation: false });
    const scale = state.network.getScale();
    const position = Object.assign({}, state.network.getViewPosition());
    state.network.moveTo({
      position,
      scale,
      offset: { x: -shift, y: 0 },
      animation: motion,
    });
    state.savedView = { position, scale };
  }

  function rebalanceGraphCenter() {
    if (!state.network) return;
    const positions = state.network.getPositions();
    const ids = Object.keys(positions);
    if (ids.length < 2) return;
    let cx = 0;
    let cy = 0;
    ids.forEach((id) => {
      cx += positions[id].x;
      cy += positions[id].y;
    });
    cx /= ids.length;
    cy /= ids.length;
    if (Math.hypot(cx, cy) < 6) return;
    const bodyNodes = state.network.body && state.network.body.nodes;
    if (bodyNodes) {
      ids.forEach((id) => {
        const node = bodyNodes[id];
        if (!node) return;
        node.x -= cx;
        node.y -= cy;
        if (typeof node.vx === 'number') node.vx *= 0.7;
        if (typeof node.vy === 'number') node.vy *= 0.7;
      });
      return;
    }
    if (state.nodesData) {
      state.nodesData.update(ids.map((id) => ({
        id,
        x: positions[id].x - cx,
        y: positions[id].y - cy,
      })));
    }
  }

  function centerGraphView(animate) {
    if (!state.network) return;
    const scale = state.network.getScale();
    const shift = listDockShiftX();
    state.network.moveTo({
      position: { x: 0, y: 0 },
      scale,
      offset: { x: -shift, y: 0 },
      animation: animate
        ? { duration: 280, easingFunction: 'easeInOutCubic' }
        : false,
    });
    if (state.layout === 'list' && state.listMode === 'dock') {
      state.savedView = { position: { x: 0, y: 0 }, scale };
    }
  }

  function keepMicroMotionInView() {
    stopMotionWatch();
    const tick = () => {
      if (!state.network || state.motion !== 'micro') {
        motionWatchRaf = 0;
        return;
      }
      motionWatchTicks += 1;
      // Keep COM at origin and camera locked so micro physics cannot drift off-canvas.
      if (motionWatchTicks % 10 === 0) {
        rebalanceGraphCenter();
        centerGraphView(false);
      }
      motionWatchRaf = window.requestAnimationFrame(tick);
    };
    motionWatchRaf = window.requestAnimationFrame(tick);
  }

  function setMotion(mode) {
    state.motion = mode === 'micro' ? 'micro' : 'static';
    const toggle = document.getElementById('motionToggle');
    if (toggle) {
      const isMicro = state.motion === 'micro';
      toggle.dataset.motion = state.motion;
      toggle.classList.toggle('is-micro', isMicro);
      toggle.classList.toggle('is-static', !isMicro);
      const current = isMicro ? 'Micro-motion' : 'Still';
      const next = isMicro ? 'Still' : 'Micro-motion';
      const label = `${current} (click to switch to ${next})`;
      toggle.title = label;
      toggle.setAttribute('aria-label', label);
      toggle.innerHTML = `<i data-lucide="${isMicro ? 'pause' : 'play'}"></i>`;
      if (window.lucide && typeof window.lucide.createIcons === 'function') {
        window.lucide.createIcons({ root: toggle });
      }
    }
    if (!state.network) return;
    state.network.setOptions({ physics: motionPhysics(state.motion) });
    if (state.motion === 'micro') {
      // Do not restore savedView here — it fights COM rebalance and pushes the graph off-screen.
      rebalanceGraphCenter();
      centerGraphView(true);
      keepMicroMotionInView();
    } else {
      stopMotionWatch();
      rebalanceGraphCenter();
      centerGraphView(true);
    }
  }

  function syncGraphViewport(animate) {
    if (!state.network) return;
    const docked = state.layout === 'list' && state.listMode === 'dock';
    if (docked && !state.savedView) {
      state.savedView = {
        position: { x: 0, y: 0 },
        scale: state.network.getScale(),
      };
    }
    const base = state.savedView || {
      position: { x: 0, y: 0 },
      scale: state.network.getScale(),
    };
    const motion = animate
      ? { duration: 280, easingFunction: 'easeInOutCubic' }
      : false;
    window.requestAnimationFrame(() => {
      if (!state.network) return;
      state.network.moveTo({
        position: base.position,
        scale: base.scale,
        offset: { x: -listDockShiftX(), y: 0 },
        animation: motion,
      });
      if (!docked) state.savedView = null;
    });
  }

  function applyListPresentation() {
    const graphLayout = document.querySelector('.graph-layout');
    const expanded = state.layout === 'list' && state.listMode === 'expanded';
    const docked = state.layout === 'list' && state.listMode === 'dock';
    if (graphLayout) {
      graphLayout.classList.toggle('is-list-dock', docked);
      graphLayout.classList.toggle('is-list-expanded', expanded);
      graphLayout.classList.toggle('is-list-mode', expanded);
    }
    if (listPanel) listPanel.hidden = state.layout !== 'list';
    container.hidden = expanded;
    if (graphControls) graphControls.hidden = expanded;
    if (expanded) hideNodeCard();
    else if (docked && nodeCard && nodeCard.innerHTML.trim()) {
      nodeCard.hidden = false;
      positionNodeCard();
    }
    if (listExpandToggle) {
      const expand = !expanded;
      listExpandToggle.title = expand ? 'Expand list' : 'Collapse to sidebar';
      listExpandToggle.setAttribute('aria-label', listExpandToggle.title);
      listExpandToggle.innerHTML = `<i data-lucide="${expand ? 'maximize-2' : 'minimize-2'}"></i>`;
      if (window.lucide && typeof window.lucide.createIcons === 'function') {
        window.lucide.createIcons({ root: listExpandToggle });
      }
    }
  }

  function syncGraphListToggle() {
    const listOpen = state.layout === 'list';
    const toggle = document.getElementById('graphListToggle');
    if (!toggle) return;
    toggle.classList.toggle('is-selected', listOpen);
    toggle.setAttribute('aria-pressed', String(listOpen));
    toggle.title = listOpen ? 'Collapse list' : 'Open list';
    toggle.setAttribute('aria-label', listOpen ? 'Collapse list' : 'Open list');
  }

  function setLayout(layout, options) {
    options = options || {};
    const previous = state.layout;
    state.layout = layout;
    if (layout === 'list' && !options.keepListMode) state.listMode = 'dock';
    syncGraphListToggle();
    applyListPresentation();
    if (layout === 'list') {
      if (state.listMode === 'expanded') {
        hideNodeCard();
      } else if (nodeCard && nodeCard.innerHTML.trim()) {
        nodeCard.hidden = false;
        positionNodeCard();
      }
      loadList();
      if (state.listMode === 'dock') {
        if (!state.network) createNetwork();
        else syncGraphViewport(previous !== 'list' || options.keepListMode);
      }
      return;
    }
    if (nodeCard && nodeCard.innerHTML.trim()) {
      nodeCard.hidden = false;
      positionNodeCard();
    }
    if (!state.network) createNetwork();
    else syncGraphViewport(previous === 'list');
  }

  function toggleGraphList() {
    setLayout(state.layout === 'list' ? 'radial' : 'list');
  }

  function toggleListExpand() {
    if (state.layout !== 'list') return;
    state.listMode = state.listMode === 'expanded' ? 'dock' : 'expanded';
    setLayout('list', { keepListMode: true });
  }

  function updateStats() {
    const stats = state.graph.stats || {};
    const nodes = Number(stats.nodes || 0);
    const edges = Number(stats.edges || stats.triples || 0);
    const types = Number(stats.types || stats.categories || 0);
    const cases = Number(stats.cases || 0);
    const overviewNodes = document.getElementById('overviewNodeCount');
    const overviewEdges = document.getElementById('overviewEdgeCount');
    if (overviewNodes) overviewNodes.textContent = nodes.toLocaleString();
    if (overviewEdges) overviewEdges.textContent = edges.toLocaleString();
    const graphSource = document.getElementById('graphSource');
    if (graphSource) {
      graphSource.textContent = `${nodes.toLocaleString()} nodes · ${edges.toLocaleString()} relations · ${types.toLocaleString()} types · ${cases.toLocaleString()} cases`;
    }
    window.dispatchEvent(new CustomEvent('graph:stats', {
      detail: {
        edges,
        cases: Number(stats.total_cases || cases || 0),
      },
    }));
  }

  async function loadGraph(options) {
    options = options || {};
    if (!select.value) return null;
    if (state.graphLoaded && !options.force) return state.graph;
    if (state.graphRequest && !options.force) return state.graphRequest;
    if (state.graphController) state.graphController.abort();
    const controller = new AbortController();
    state.graphController = controller;
    loading.textContent = 'Loading graph';
    loading.classList.remove('is-hidden');
    const request = (async () => {
      const payload = await apiWithStaticFallback(
        `/api/graph/data?kg_id=${encodeURIComponent(select.value)}&limit=60`,
        'data/graph-preview.json',
        { signal: controller.signal, cache: 'no-cache' },
      );
      if (controller.signal.aborted) return null;
      state.graph = payload.data;
      state.graphLoaded = true;
      updateStats();
      if (state.network) { stopMotionWatch(); state.network.destroy(); state.network = null; state.nodesData = null; state.edgesData = null; }
      state.savedView = null;
      hideNodeCard();
      if (state.layout === 'list') setLayout('list', { keepListMode: true });
      else createNetwork();
      return state.graph;
    })();
    state.graphRequest = request;
    try {
      return await request;
    } catch (error) {
      if (error.name === 'AbortError') return null;
      loading.textContent = error.message || 'Failed to load graph';
      return null;
    } finally {
      if (state.graphRequest === request) state.graphRequest = null;
      if (state.graphController === controller) state.graphController = null;
    }
  }

  document.getElementById('refreshGraph')?.addEventListener('click', () => loadGraph({ force: true }));
  document.getElementById('zoomIn').addEventListener('click', () => {
    if (state.network) state.network.moveTo({ scale: Math.min(2.8, state.network.getScale() * 1.25), animation: { duration: 250 } });
  });
  document.getElementById('zoomOut').addEventListener('click', () => {
    if (state.network) state.network.moveTo({ scale: Math.max(0.2, state.network.getScale() / 1.25), animation: { duration: 250 } });
  });
  document.getElementById('resetZoom').addEventListener('click', () => {
    fitGraphInView(true);
  });
  document.getElementById('graphListToggle')?.addEventListener('click', toggleGraphList);
  listExpandToggle?.addEventListener('click', toggleListExpand);
  document.getElementById('motionToggle')?.addEventListener('click', () => {
    setMotion(state.motion === 'micro' ? 'static' : 'micro');
  });
  select.addEventListener('change', () => {
    state.graphLoaded = false;
    state.list.typeOptions = [];
    loadGraph({ force: true });
  });
  document.getElementById('listTypeFilter').addEventListener('change', loadList);
  document.getElementById('listLimit').addEventListener('change', loadList);
  document.getElementById('listReset').addEventListener('click', () => {
    document.getElementById('listTypeFilter').value = '';
    document.getElementById('listSearch').value = '';
    document.getElementById('listLimit').value = '180';
    loadList();
  });
  let listSearchTimer;
  document.getElementById('listSearch').addEventListener('input', () => {
    window.clearTimeout(listSearchTimer);
    listSearchTimer = window.setTimeout(loadList, 220);
  });
  document.getElementById('refreshKg')?.addEventListener('click', () => loadGraph({ force: true }));

  function refreshGraphViewport() {
    if (!state.network) return;
    // Panel was display:none while on Skill/Ontology; vis canvas size goes stale and
    // redraw alone leaves a zoomed corner. Force resize + fit to init framing.
    try {
      state.network.setSize('100%', '100%');
    } catch (_error) { /* ignore */ }
    try {
      state.network.redraw();
    } catch (_error) { /* ignore */ }
    state.savedView = null;
    fitGraphInView(false);
    if (state.motion === 'micro') keepMicroMotionInView();
  }

  window.graphWorkbench = {
    load: (options) => loadGraph(options || { force: false }),
    reload: () => loadGraph({ force: true }),
    onView(view) {
      if (view !== 'graph') return;
      const restore = () => {
        window.requestAnimationFrame(() => {
          window.requestAnimationFrame(() => {
            if (!state.network) {
              if (state.graph) createNetwork();
              return;
            }
            refreshGraphViewport();
          });
        });
      };
      loadGraph().then(restore).catch(restore);
    },
    focusCase,
    getGraph: () => state.graph,
  };

  syncGraphListToggle();
  loadGraph();
})();
