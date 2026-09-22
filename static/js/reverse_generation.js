class ReverseGenerationApp {
  constructor() {
    this.mode = 'action';
    this.groups = {};
    this.expectedGroups = {};
    this.type = null;
    this.facet = null;
    this.selectedFacets = new Map();
    this.pinnedFacets = new Map();
    this.previewFacet = null;
    this.activeFacetKey = null;
    this.expandedTypes = new Set();
    this.cases = [];
    this.selected = new Set();
    this.search = '';
    this.filter = 'all';
    this.renderToken = 0;
    this.virtualRows = [];
    this.virtualOffsets = [];
    this.virtualTotalHeight = 0;
    this.virtualRenderQueued = false;
    this.taskId = null;
    this.pollTimer = null;
    this.bind();
    this.load();
  }

  async load() {
    try {
      const [actionResponse, expectedResponse] = await Promise.all([
        fetch('/api/test-cases/by-action'),
        fetch('/api/test-cases/by-type-expected')
      ]);
      const action = await actionResponse.json();
      const expected = await expectedResponse.json();
      if (!action.success) throw new Error(action.error || 'Load failed');
      this.groups = action.data || {};
      this.expectedGroups = expected.success ? expected.data || {} : {};
      const stats = action.statistics || {};
      document.getElementById('statsText').textContent =
        `Total ${stats.总案例数 || 0} cases | ${stats.测试类型数 || 0} test types | Selected 0`;
      this.renderTypes();
    } catch (error) {
      this.error(error.message);
    }
  }

  bind() {
    document.querySelectorAll('[data-mode]').forEach(button => {
      button.onclick = () => this.setMode(button.dataset.mode);
    });
    document.getElementById('filterType').onchange = event => {
      this.filter = event.target.value;
      this.renderTypes();
      this.renderCases();
    };
    document.getElementById('searchBox').oninput = event => {
      this.search = event.target.value.trim().toLowerCase();
      this.renderCases();
    };
    const caseList = document.getElementById('caseList');
    caseList.onclick = event => {
      if (event.target.closest('.case-checkbox')) return;
      const card = event.target.closest('.case-card');
      if (!card) return;
      const checkbox = card.querySelector('.case-checkbox');
      checkbox.checked = !checkbox.checked;
      this.toggle(card.dataset.id, checkbox.checked, card.dataset.facetKey);
    };
    caseList.onchange = event => {
      if (!event.target.classList.contains('case-checkbox')) return;
      const card = event.target.closest('.case-card');
      this.toggle(event.target.dataset.id, event.target.checked, card.dataset.facetKey);
    };
    caseList.onscroll = () => {
      this.queueVirtualWindow();
    };
    document.getElementById('selectAll').onclick = () => this.selectAll();
    document.getElementById('clearSelection').onclick = () => { this.clear(); this.renderTypes(); this.renderCases(); };
    document.getElementById('generateBtn').onclick = () => this.generate();
    document.getElementById('exportBtn').onclick = () => this.exportSelected();
    document.getElementById('closeProgressBtn').onclick = () => this.close('progressModal');
    document.getElementById('closeBtn').onclick = () => this.close('resultModal');
    document.getElementById('closeResultModal').onclick = () => this.close('resultModal');
    document.getElementById('downloadBtn').onclick = () => this.downloadTask();
    document.getElementById('retryTaskBtn').onclick = () => this.retryTask();
    document.getElementById('refreshTaskBtn').onclick = () => this.poll();
  }

  setMode(mode) {
    this.mode = mode;
    this.type = null;
    this.facet = null;
    this.selectedFacets.clear();
    this.pinnedFacets.clear();
    this.previewFacet = null;
    this.activeFacetKey = null;
    this.expandedTypes.clear();
    this.cases = [];
    this.clear();
    document.querySelectorAll('[data-mode]').forEach(button => {
      button.classList.toggle('active', button.dataset.mode === mode);
    });
    this.renderTypes();
    this.renderCases();
  }

  sourceGroups() {
    return this.mode === 'action' ? this.groups : this.expectedGroups;
  }

  facetMap(data) {
    return this.mode === 'action' ? data.actions || {} : data.expected_behaviors || {};
  }

  visible(list) {
    return (list || []).filter(item =>
      this.filter === 'all' ||
      (this.filter === 'single' ? item.是否单一预期 : !item.是否单一预期)
    );
  }

  matchesSearch(item) {
    if (!this.search) return true;
    const text = `${item.测试用例名称 || ''} ${item.编号 || ''} ${item.预期行为 || ''}`.toLowerCase();
    return text.includes(this.search);
  }

  allCases() {
    const seen = new Map();
    Object.values(this.groups).forEach(group => {
      Object.values(group.actions || {}).forEach(list => {
        list.forEach(item => seen.set(item.unique_id || item.编号, item));
      });
    });
    return [...seen.values()];
  }

  isListSelected(list) {
    return list.length > 0 && list.every(item => this.selected.has(item.unique_id || item.编号));
  }

  toggleFacetSelection(type, facet, list, checked) {
    const key = this.facetKey(type, facet);
    if (checked) {
      this.selectedFacets.set(key, {type, facet});
      this.pinnedFacets.delete(key);
      this.previewFacet = null;
      this.activeFacetKey = key;
    } else {
      this.selectedFacets.delete(key);
      this.pinnedFacets.delete(key);
      if (this.activeFacetKey === key) this.activeFacetKey = null;
      if (this.previewFacet && this.facetKey(this.previewFacet.type, this.previewFacet.facet) === key) {
        this.previewFacet = null;
      }
    }
    list.forEach(item => {
      const id = item.unique_id || item.编号;
      if (checked) this.selected.add(id);
      else this.selected.delete(id);
    });
    this.renderTypes();
    this.renderCases();
  }
  renderTypes() {
    const container = document.getElementById('actionList');
    const source = this.sourceGroups();
    const entries = Object.entries(source || {});
    container.innerHTML = '';
    let visibleTypeCount = 0;

    entries.forEach(([type, data]) => {
      const facets = Object.entries(this.facetMap(data))
        .map(([name, list]) => [name, this.visible(list)])
        .filter(([, list]) => list.length > 0);
      const total = facets.reduce((sum, [, list]) => sum + list.length, 0);
      if (!total) return;
      visibleTypeCount += 1;

      const group = document.createElement('div');
      group.className = 'type-group';

      const header = document.createElement('div');
      const expanded = this.expandedTypes.has(type);
      header.className = `type-header${expanded ? ' expanded' : ''}`;
      header.innerHTML = `
        <input type="checkbox" class="type-checkbox" title="Select/deselect all cases under this type">
        <span class="type-toggle" aria-hidden="true"></span>
        <span class="type-name">${this.esc(type)}</span>
        <span class="type-count">${total}</span>
      `;

      const nested = document.createElement('div');
      nested.className = `action-list-nested${expanded ? '' : ' collapsed'}`;
      facets.forEach(([name, list]) => {
        const item = document.createElement('div');
        const facetKey = this.facetKey(type, name);
        item.className = `action-item nested${this.activeFacetKey === facetKey ? ' active' : ''}`;
        item.style.setProperty('--facet-color', this.facetColor(facetKey));
        item.innerHTML = `<input class="action-checkbox" type="checkbox" title="Select/deselect all cases under this action" ${this.isListSelected(list) ? 'checked' : ''}><span class="action-name">${this.esc(name)}</span><span class="case-count">${list.length}</span>`;
        item.onclick = event => {
          if (event.target.classList.contains('action-checkbox')) return;
          event.stopPropagation();
          this.focusFacet(type, name);
        };
        const actionCheckbox = item.querySelector('.action-checkbox');
        const selectedCount = list.filter(caseItem => this.selected.has(caseItem.unique_id || caseItem.编号)).length;
        actionCheckbox.indeterminate = selectedCount > 0 && selectedCount < list.length;
        actionCheckbox.onclick = event => {
          event.stopPropagation();
          this.toggleFacetSelection(type, name, list, actionCheckbox.checked);
        };
        nested.appendChild(item);
      });

      const checkbox = header.querySelector('.type-checkbox');
      const typeCases = facets.flatMap(([, list]) => list);
      const selectedTypeCount = typeCases.filter(caseItem => this.selected.has(caseItem.unique_id || caseItem.编号)).length;
      checkbox.checked = this.isListSelected(typeCases);
      checkbox.indeterminate = selectedTypeCount > 0 && selectedTypeCount < typeCases.length;
      checkbox.onclick = event => {
        event.stopPropagation();
        this.toggleTypeSelection(type, checkbox.checked);
      };
      header.onclick = event => {
        if (event.target === checkbox) return;
        if (this.expandedTypes.has(type)) this.expandedTypes.delete(type);
        else this.expandedTypes.add(type);
        this.facet = null;
        this.renderTypes();
        this.renderCases();
      };

      group.appendChild(header);
      group.appendChild(nested);
      container.appendChild(group);
    });

    document.getElementById('actionCount').textContent = visibleTypeCount;
    this.updateStats();
    if (!visibleTypeCount) {
      container.innerHTML = '<div class="empty-state"><p>No matching test cases</p></div>';
    }
  }

  facetKey(type, facet) {
    return `${type}::${facet}`;
  }

  facetColor() {
    return '#0f8f88';
  }

  focusFacet(type, facet) {
    const key = this.facetKey(type, facet);
    this.activeFacetKey = key;
    this.previewFacet = this.selectedFacets.has(key) ? null : {type, facet};
    this.renderTypes();
    this.renderCases();
    requestAnimationFrame(() => this.scrollToFacet(key));
  }

  scrollToFacet(key) {
    const rowIndex = this.virtualRows.findIndex(row => row.kind === 'heading' && row.facetKey === key);
    if (rowIndex >= 0) {
      const container = document.getElementById('caseList');
      const targetTop = Math.max(0, this.virtualOffsets[rowIndex] - 12);
      container.scrollTo({top: targetTop, behavior: 'smooth'});
      return;
    }
    const section = [...document.querySelectorAll('.case-action-section')]
      .find(element => element.dataset.facetKey === key);
    section?.scrollIntoView({behavior: 'smooth', block: 'start'});
  }

  currentFacetGroups() {
    const source = this.sourceGroups();
    const matchesCurrentFilters = item => {
      if (!this.visible([item]).length) return false;
      return this.matchesSearch(item);
    };
    if (this.search) {
      const groups = [];
      Object.entries(source).forEach(([type, data]) => {
        Object.entries(this.facetMap(data)).forEach(([facet, list]) => {
          const cases = list.filter(matchesCurrentFilters);
          if (!cases.length) return;
          const key = this.facetKey(type, facet);
          groups.push({key, type, facet, cases, color: this.facetColor(key), searchResult: true});
        });
      });
      return groups;
    }
    // Keep full-action groups before manually pinned cases so a preview does not move on selection.
    const persistedFacets = new Map([...this.selectedFacets, ...this.pinnedFacets]);
    const groups = [...persistedFacets.entries()].map(([key, selection]) => {
      const data = source[selection.type] || {};
      // Any persisted action (partial or full) and the current preview show every case.
      const keepWholeGroup = true;
      const list = (this.facetMap(data)[selection.facet] || []).filter(item => {
        if (!keepWholeGroup && !this.selected.has(item.unique_id || item.编号)) return false;
        return matchesCurrentFilters(item);
      });
      return {key, type: selection.type, facet: selection.facet, cases: list, color: this.facetColor(key)};
    }).filter(group => group.cases.length > 0);

    if (this.previewFacet) {
      const {type, facet} = this.previewFacet;
      const key = this.facetKey(type, facet);
      if (!persistedFacets.has(key)) {
        const data = source[type] || {};
        const list = (this.facetMap(data)[facet] || []).filter(matchesCurrentFilters);
        if (list.length) groups.push({key, type, facet, cases: list, color: this.facetColor(key), temporary: true});
      }
    }
    return groups;
  }

  renderCases() {
    this.renderToken += 1;
    const groups = this.currentFacetGroups();
    this.cases = groups.flatMap(group => group.cases);
    document.getElementById('caseCount').textContent = `${this.cases.length} cases`;
    const container = document.getElementById('caseList');
    const previousScrollTop = container.scrollTop;
    if (!groups.length) {
      this.virtualRows = [];
      this.virtualOffsets = [];
      const message = this.search ? 'No matching cases found' : 'Check the boxes next to actions on the left to show cases';
      container.innerHTML = `<div class="empty-state"><p>${message}</p></div>`;
      this.update();
      return;
    }

    this.virtualRows = [];
    groups.forEach(group => {
      this.virtualRows.push({kind: 'heading', facetKey: group.key, group, height: this.estimateHeadingHeight(group.facet)});
      group.cases.forEach(item => {
        this.virtualRows.push({kind: 'card', facetKey: group.key, item, height: this.estimateCardHeight(item)});
      });
    });
    this.rebuildVirtualOffsets();
    container.classList.add('virtualized');
    container.innerHTML = '<div class="case-virtual-content"></div>';
    const content = container.querySelector('.case-virtual-content');
    content.style.height = `${this.virtualTotalHeight}px`;
    container.scrollTop = Math.min(previousScrollTop, Math.max(0, this.virtualTotalHeight - container.clientHeight));
    this.renderVirtualWindow();
    this.update();
  }

  estimateCardHeight(item) {
    const preconditions = item.前提条件 || [];
    const textLength = `${item.测试用例名称 || ''}${item.执行动作 || ''}${item.预期行为 || ''}${preconditions.join('')}`.length;
    return Math.max(300, 232 + preconditions.length * 36 + Math.ceil(textLength / 52) * 24);
  }

  estimateHeadingHeight(facet) {
    return Math.max(54, 30 + Math.ceil(String(facet || '').length / 70) * 24);
  }

  rebuildVirtualOffsets() {
    let offset = 0;
    this.virtualOffsets = this.virtualRows.map(row => {
      const current = offset;
      offset += row.height;
      return current;
    });
    this.virtualTotalHeight = offset;
  }

  virtualRowIndexAt(position) {
    let low = 0;
    let high = this.virtualOffsets.length - 1;
    while (low <= high) {
      const middle = Math.floor((low + high) / 2);
      if (this.virtualOffsets[middle] <= position) low = middle + 1;
      else high = middle - 1;
    }
    return Math.max(0, high);
  }

  renderVirtualWindow() {
    const container = document.getElementById('caseList');
    const content = container.querySelector('.case-virtual-content');
    if (!content || !this.virtualRows.length) return;

    const buffer = 900;
    const scrollTop = container.scrollTop;
    const viewportBottom = scrollTop + (container.clientHeight || 600);
    const start = this.virtualRowIndexAt(Math.max(0, scrollTop - buffer));
    const end = Math.min(this.virtualRows.length, this.virtualRowIndexAt(viewportBottom + buffer) + 2);
    content.style.height = `${this.virtualTotalHeight}px`;

    const markup = [];
    for (let index = start; index < end; index += 1) {
      const row = this.virtualRows[index];
      const top = this.virtualOffsets[index];
      if (row.kind === 'heading') {
        markup.push(`<section class="case-action-section case-virtual-heading" data-row-index="${index}" data-facet-key="${this.esc(row.facetKey)}" style="--facet-color:${row.group.color};top:${top}px;height:${row.height}px"><div class="case-action-heading"><span class="case-action-marker"></span><h3>${this.esc(row.group.facet)}</h3><span>${row.group.cases.length} cases</span></div></section>`);
      } else {
        markup.push(`<div class="case-virtual-row" data-row-index="${index}" data-facet-key="${this.esc(row.facetKey)}" style="top:${top}px;min-height:${row.height}px;--virtual-row-height:${row.height}px">${this.card(row.item, row.facetKey)}</div>`);
      }
    }
    content.innerHTML = markup.join('');

  }

  queueVirtualWindow() {
    if (this.virtualRenderQueued) return;
    this.virtualRenderQueued = true;
    requestAnimationFrame(() => {
      this.virtualRenderQueued = false;
      this.renderVirtualWindow();
    });
  }

  card(item, facetKey) {
    const id = item.unique_id || item.编号;
    const preconditions = (item.前提条件 || [])
      .map(condition => `<li>${this.esc(condition)}</li>`).join('');
    return `<div class="case-card ${this.selected.has(id) ? 'selected' : ''}" data-id="${this.esc(id)}" data-facet-key="${this.esc(facetKey)}">
      <div class="case-header">
        <input class="case-checkbox" type="checkbox" data-id="${this.esc(id)}" ${this.selected.has(id) ? 'checked' : ''}>
        <span class="case-id">${this.highlight(item.编号 || id)}</span>
        <span class="case-type">${this.esc(item.测试用例类型 || '')}</span>
      </div>
      <div class="case-body">
        <h4>${this.highlight(item.测试用例名称 || 'Untitled')}</h4>
        <div class="case-preconditions"><strong class="field-label">Preconditions:</strong><ul>${preconditions}</ul></div>
        <div class="case-action"><strong class="field-label">Actions:</strong><div class="field-content">${this.esc(item.执行动作 || '')}</div></div>
        <div class="case-expected"><strong class="field-label">Expected Behavior:</strong><div class="field-content">${this.highlight(item.预期行为 || '')}</div></div>
      </div>
    </div>`;
  }

  toggleTypeSelection(type, checked) {
    const data = this.sourceGroups()[type] || {};
    Object.entries(this.facetMap(data)).forEach(([facet, list]) => {
      const visibleCases = this.visible(list);
      const key = this.facetKey(type, facet);
      if (checked) {
        this.selectedFacets.set(key, {type, facet});
        this.pinnedFacets.delete(key);
      } else {
        this.selectedFacets.delete(key);
        this.pinnedFacets.delete(key);
      }
      visibleCases.forEach(item => {
        const id = item.unique_id || item.编号;
        if (checked) this.selected.add(id);
        else this.selected.delete(id);
      });
    });
    this.renderTypes();
    this.renderCases();
  }

  findFacetSelection(key) {
    for (const [type, data] of Object.entries(this.sourceGroups())) {
      for (const facet of Object.keys(this.facetMap(data))) {
        if (this.facetKey(type, facet) === key) return {type, facet};
      }
    }
    return null;
  }

  toggle(id, checked, facetKey) {
    if (checked) this.selected.add(id);
    else this.selected.delete(id);
    const selection = facetKey ? this.findFacetSelection(facetKey) : null;
    if (selection) {
      const data = this.sourceGroups()[selection.type] || {};
      const cases = this.facetMap(data)[selection.facet] || [];
      const hasSelectedCase = cases.some(item => this.selected.has(item.unique_id || item.编号));
      if (this.selectedFacets.has(facetKey)) {
        if (!hasSelectedCase) this.selectedFacets.delete(facetKey);
      } else if (hasSelectedCase) {
        this.pinnedFacets.set(facetKey, selection);
      } else {
        this.pinnedFacets.delete(facetKey);
      }
    }
    this.renderTypes();
    this.renderCases();
  }

  selectAll() {
    Object.entries(this.sourceGroups()).forEach(([type, data]) => {
      Object.entries(this.facetMap(data)).forEach(([facet, list]) => {
        const visibleCases = this.visible(list);
        if (!visibleCases.length) return;
        this.selectedFacets.set(this.facetKey(type, facet), {type, facet});
        this.pinnedFacets.delete(this.facetKey(type, facet));
        visibleCases.forEach(item => this.selected.add(item.unique_id || item.编号));
      });
    });
    requestAnimationFrame(() => {
      this.renderTypes();
      this.renderCases();
    });
  }

  clear() {
    this.selected.clear();
    this.selectedFacets.clear();
    this.pinnedFacets.clear();
    this.previewFacet = null;
    this.activeFacetKey = null;
    this.update();
  }

  update() {
    document.getElementById('selectedCount').textContent = `Selected: ${this.selected.size}`;
    document.getElementById('generateCount').textContent = this.selected.size;
    document.getElementById('generateBtn').disabled = !this.selected.size;
    this.updateStats();
  }

  updateStats() {
    const seen = new Map();
    let typeCount = 0;
    Object.values(this.sourceGroups()).forEach(data => {
      const cases = Object.values(this.facetMap(data)).flatMap(list => this.visible(list));
      if (!cases.length) return;
      typeCount += 1;
      cases.forEach(item => seen.set(item.unique_id || item.编号, item));
    });
    const selectedCount = [...seen.keys()].filter(id => this.selected.has(id)).length;
    document.getElementById('statsText').textContent =
      `Total ${seen.size} cases | ${typeCount} test types | Selected ${selectedCount}`;
  }

  async generate() {
    if (!this.selected.size) return;
    this.showProgress();
    try {
      const response = await fetch('/api/test-cases/generate-reverse', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({case_ids: [...this.selected], generation_mode: 'batch', model_name: 'Qwen3-4B'})
      });
      const data = await this.readJson(response);
      this.taskId = data.task_id;
      this.poll();
    } catch (error) {
      this.showTaskFailure(error.message, false);
    }
  }

  showExpectedLoading() {
    this.showProgress();
    document.getElementById('taskStatusTitle').textContent = 'Generating reverse cases';
    document.getElementById('progressText').textContent = 'Calling model...';
  }

  showProgress() {
    clearTimeout(this.pollTimer);
    document.getElementById('taskStatusTitle').textContent = 'Generating reverse cases';
    document.getElementById('progressFill').style.width = '0%';
    document.getElementById('progressFill').classList.remove('is-indeterminate');
    document.getElementById('progressText').textContent = 'Creating task...';
    document.getElementById('taskStatusMessage').textContent = '';
    document.getElementById('retryTaskBtn').hidden = true;
    document.getElementById('refreshTaskBtn').hidden = true;
    document.getElementById('progressModal').classList.add('show');
  }

  async readJson(response) {
    const text = await response.text();
    let data;
    try {
      data = text ? JSON.parse(text) : {};
    } catch (_) {
      throw new Error(`Unexpected service response (HTTP ${response.status})`);
    }
    if (!response.ok || data.success === false) {
      throw new Error(data.error || `Request failed (HTTP ${response.status})`);
    }
    return data;
  }

  taskFailureMessage(data, fallback) {
    const reasons = (data?.failed_cases || [])
      .slice(0, 3)
      .map(item => `${item.执行动作 || 'Case'}: ${item.原因 || 'No result generated'}`);
    const message = data?.error || fallback || 'Generation failed. Check the model service and retry.';
    return reasons.length ? `${message} ${reasons.join('；')}` : message;
  }

  showTaskFailure(message, retryable = Boolean(this.taskId)) {
    clearTimeout(this.pollTimer);
    document.getElementById('taskStatusTitle').textContent = 'Reverse case generation failed';
    document.getElementById('progressFill').style.width = '100%';
    document.getElementById('progressFill').classList.remove('is-indeterminate');
    document.getElementById('progressText').textContent = 'No usable results generated';
    document.getElementById('taskStatusMessage').textContent = message;
    document.getElementById('retryTaskBtn').hidden = !retryable;
    document.getElementById('refreshTaskBtn').hidden = true;
    document.getElementById('progressModal').classList.add('show');
  }

  async retryTask() {
    if (!this.taskId) return;
    try {
      const response = await fetch(`/api/test-cases/retry/${encodeURIComponent(this.taskId)}`, {method: 'POST'});
      const data = await this.readJson(response);
      this.taskId = data.task_id;
      this.showProgress();
      this.poll();
    } catch (error) {
      this.showTaskFailure(error.message, false);
    }
  }

  async poll() {
    try {
      const response = await fetch(`/api/test-cases/generation-status/${encodeURIComponent(this.taskId)}`);
      const data = await this.readJson(response);
      const progress = data.progress || {};
      const progressFill = document.getElementById('progressFill');
      const workTotal = progress.work_total || progress.total || 0;
      const workCompleted = progress.work_completed ?? progress.completed ?? 0;
      const workStarted = progress.work_started || workCompleted;
      const generated = progress.completed || 0;
      progressFill.style.width = `${progress.percentage || 0}%`;
      progressFill.classList.toggle('is-indeterminate', data.status === 'processing' && Boolean(progress.current_action));
      document.getElementById('progressText').textContent = workTotal
        ? `Completed ${workCompleted} / ${workTotal} actions | Generated ${generated} cases`
        : `Generated ${generated} cases`;
      document.getElementById('taskStatusMessage').textContent = progress.current_action
        ? `Processing action ${workStarted} / ${workTotal}: ${progress.current_action}`
        : '';
      if (data.status === 'completed' || (data.status === 'partial' && (progress.completed || 0) > 0)) {
        const resultResponse = await fetch(`/api/test-cases/reverse-results/${this.taskId}`);
        const result = await this.readJson(resultResponse);
        this.showResults(result.data, this.taskId);
      } else if (['partial', 'failed', 'interrupted'].includes(data.status)) {
        this.showTaskFailure(this.taskFailureMessage(data), data.retryable);
      } else {
        this.pollTimer = setTimeout(() => this.poll(), 1000);
      }
    } catch (error) {
      this.showTaskFailure(error.message, Boolean(this.taskId));
    }
  }

  showResults(data, task) {
    this.close('progressModal');
    document.getElementById('progressFill').classList.remove('is-indeterminate');
    this.lastData = data;
    this.taskId = task;
    document.getElementById('resultContent').innerHTML = (data.reverse_cases || []).map(item => {
      const generated = item.生成案例 || item;
      return `<div class="result-item"><h4>${this.esc(generated.测试用例名称 || 'Reverse case')}</h4><p><b>Original case ID:</b>${this.esc(item.原始案例ID || '')}</p><p><b>Reverse type:</b>${this.esc(item.反转类型 || '')}</p><p><b>Preconditions:</b>${this.esc((generated.前提条件 || []).join('; '))}</p><p><b>Actions:</b>${this.esc(generated.执行动作 || '')}</p><p><b>Expected Behavior:</b>${this.esc(generated.预期行为 || '')}</p></div>`;
    }).join('') || '<p>No results</p>';
    document.getElementById('resultModal').classList.add('show');
  }

  async downloadTask() {
    if (this.taskId) {
      const link = document.createElement('a');
      link.href = `/api/test-cases/export-excel/${encodeURIComponent(this.taskId)}`;
      link.click();
      return;
    }
    if (!this.lastData) return;
    const response = await fetch('/api/export-generated-cases-excel', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({cases: this.lastData.reverse_cases || []})
    });
    const blob = await response.blob();
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = 'reverse_test_cases.xlsx';
    link.click();
  }

  exportSelected() {
    const blob = new Blob([JSON.stringify(this.cases.filter(item => this.selected.has(item.unique_id || item.编号)), null, 2)], {type: 'application/json'});
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = 'selected_cases.json';
    link.click();
  }

  close(id) { document.getElementById(id).classList.remove('show'); }
  error(message) { alert(`❌ ${message}`); }
  highlight(value) {
    const text = String(value ?? '');
    if (!this.search) return this.esc(text);
    const matcher = new RegExp(this.search.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi');
    let result = '';
    let lastIndex = 0;
    let match;
    while ((match = matcher.exec(text)) !== null) {
      result += this.esc(text.slice(lastIndex, match.index));
      result += `<mark class="search-highlight">${this.esc(match[0])}</mark>`;
      lastIndex = match.index + match[0].length;
    }
    return result + this.esc(text.slice(lastIndex));
  }
  esc(value) { const node = document.createElement('div'); node.textContent = value ?? ''; return node.innerHTML; }
}

document.addEventListener('DOMContentLoaded', () => new ReverseGenerationApp());
