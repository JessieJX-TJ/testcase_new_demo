(function () {
  const root = document.getElementById('tcWorkbench');
  if (!root) return;

  const UI_VERSION = 'testcase-native-20260911';
  const RECORD_KEY = 'testcase_native_records_v1';
  const REVIEW_KEY = 'testcase_native_reviewed_v1';
  const $ = (id) => document.getElementById(id);

  const state = {
    activeTab: 'requirement',
    cases: [],
    selected: 0,
    traces: [],
    evidence: null,
    meta: null,
    evalIssues: [],
    sts: { doc: null, sections: [], clusters: [], artifacts: null },
    records: readJson(RECORD_KEY, []),
    reviewed: new Set(readJson(REVIEW_KEY, [])),
    busy: false
  };

  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (char) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char];
    });
  }

  function readJson(key, fallback) {
    try {
      const value = localStorage.getItem(key);
      return value ? JSON.parse(value) : fallback;
    } catch (_) {
      return fallback;
    }
  }

  function writeJson(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch (_) {}
  }

  function icons() {
    if (window.lucide) window.lucide.createIcons();
  }

  function setStatus(message, error) {
    const el = $('tcStatusLine');
    el.textContent = message || '';
    el.classList.toggle('error', Boolean(error));
  }

  function setBusy(value) {
    state.busy = value;
    [
      'tcGenerateBtn', 'tcRefineBtn', 'tcAutoImproveBtn', 'tcEvaluateBtn',
      'tcAcceptBtn', 'tcRejectBtn', 'tcStsUploadBtn', 'tcStsUseUrlBtn',
      'tcStsParseBtn', 'tcStsGenerateBtn', 'tcExportTxtBtn', 'tcExportJsonBtn',
      'tcExportExcelBtn'
    ].forEach(function (id) {
      const el = $(id);
      if (el) el.disabled = value || (id === 'tcStsParseBtn' && !state.sts.doc) || (id === 'tcStsGenerateBtn' && !state.sts.doc);
    });
  }

  function selectedModel() {
    return ($('tcModel').value || 'Qwen3-4B').trim();
  }

  function selectedCount() {
    const value = Number($('tcCaseCount').value || 1);
    return Math.max(1, Math.min(10, Number.isFinite(value) ? value : 1));
  }

  function hashText(value) {
    let hash = 0;
    const text = String(value || '');
    for (let i = 0; i < text.length; i += 1) {
      hash = ((hash << 5) - hash) + text.charCodeAt(i);
      hash |= 0;
    }
    return Math.abs(hash).toString(36);
  }

  function ensureArray(value) {
    if (Array.isArray(value)) return value.map((item) => String(item || '').trim()).filter(Boolean);
    if (!value) return [];
    return String(value).split(/\n+/).map((item) => item.replace(/^\s*[-•\d一二三四五六七八九十]+[.、)]?\s*/, '').trim()).filter(Boolean);
  }

  function splitThinkAndAnswer(rawText) {
    const text = String(rawText || '');
    const thinkRegex = /<think>([\s\S]*?)<\/think>/gi;
    const thoughts = [];
    let match;
    while ((match = thinkRegex.exec(text)) !== null) {
      if ((match[1] || '').trim()) thoughts.push(match[1].trim());
    }
    return { thinkText: thoughts.join('\n\n'), answerText: text.replace(thinkRegex, '').trim() };
  }

  function parseGeneratedCase(genText) {
    const text = String(genText || '').replace(/\r\n?/g, '\n').replace(/[：]/g, ':').trim();
    const headerUnion = '(?:前提条件|前置条件|前提|先决条件|Prerequisite|Preconditions|执行动作|操作步骤|测试步骤|执行步骤|步骤|Actions|预期行为|预期结果|期望结果|期望|Expected)';
    const lines = text.split('\n');
    const indices = [];
    for (let i = 0; i < lines.length; i += 1) {
      const match = lines[i].match(new RegExp('^\\s*(' + headerUnion + ')\\s*:\\s*', 'i'));
      if (!match) continue;
      const label = match[1];
      let type = '';
      if (/(前提条件|前置条件|前提|先决条件|Prerequisite|Preconditions)/i.test(label)) type = 'pre';
      if (/(执行动作|操作步骤|测试步骤|执行步骤|步骤|Actions)/i.test(label)) type = 'act';
      if (/(预期行为|预期结果|期望结果|期望|Expected)/i.test(label)) type = 'exp';
      indices.push({ idx: i, type, offset: lines[i].indexOf(match[0]) + match[0].length });
    }
    const result = { pre: [], act: [], exp: [] };
    function collect(fromLine, toLine, offset) {
      const segment = lines.slice(fromLine, toLine);
      if (segment.length) segment[0] = segment[0].slice(offset);
      return ensureArray(segment.join('\n'));
    }
    indices.forEach(function (current, index) {
      const next = indices[index + 1];
      result[current.type] = collect(current.idx, next ? next.idx : lines.length, current.offset);
    });
    if ((!result.act.length || !result.exp.length) && text) {
      if (!result.act.length) result.act = ensureArray(lines.filter((line) => /执行|操作|步骤/.test(line)).join('\n'));
      if (!result.exp.length) result.exp = ensureArray(lines.filter((line) => /预期|期望|Expected/i.test(line)).join('\n'));
    }
    return result;
  }

  function caseTitle(text, fallback) {
    return (String(text || '').match(/(?:测试项|测试用例名称|标题)\s*[：:]\s*([^\n]+)/) || [])[1] || fallback || 'Generated test case';
  }

  function splitGeneratedCases(text) {
    const parts = String(text || '').split(/\n\s*---+\s*\n/g).map((item) => item.trim()).filter(Boolean);
    return parts.length ? parts : (text ? [String(text).trim()] : []);
  }

  function normalizeCase(item, index, source) {
    const raw = item || {};
    const text = raw.testcase || raw.rawText || '';
    const parsed = parseGeneratedCase(text);
    return {
      id: raw.case_id || raw.id || 'generated_' + hashText([text, index, Date.now()].join(':')),
      title: raw.title || raw.topic || raw.section_title || caseTitle(text, 'Test Case ' + (index + 1)),
      testcase: text,
      original_testcase: raw.original_testcase || text,
      preconditions: ensureArray(raw.preconditions || parsed.pre),
      actions: ensureArray(raw.actions || parsed.act),
      expected_behaviors: ensureArray(raw.expected_behaviors || parsed.exp),
      source: source || raw.source || state.meta?.source || 'natural_language',
      status: raw.status || '',
      case_id: raw.case_id || '',
      model: raw.model || state.meta?.model || selectedModel(),
      document_id: raw.document_id || state.meta?.document_id || '',
      trace: raw.trace || state.meta?.trace || [],
      raw
    };
  }

  function startMeta(source, extra) {
    state.traces = [];
    state.meta = Object.assign({
      job_id: 'job_' + Date.now() + '_' + Math.random().toString(16).slice(2, 8),
      source,
      model: selectedModel(),
      ui_version: UI_VERSION,
      prompt_version: 'server-default',
      testcase_count: selectedCount(),
      document_id: state.sts.doc?.document_id || '',
      started_at: new Date().toISOString(),
      trace: []
    }, extra || {});
    renderTrace();
    renderMeta();
  }

  function finishMeta(extra) {
    if (!state.meta) startMeta('manual');
    Object.assign(state.meta, extra || {}, { finished_at: new Date().toISOString() });
    renderMeta();
  }

  function addTrace(message, type) {
    const text = String(message || '').trim();
    if (!text) return;
    const event = { at: new Date().toISOString(), type: type || 'info', message: text };
    state.traces.push(event);
    if (state.traces.length > 120) state.traces.shift();
    if (state.meta) state.meta.trace = state.traces.slice();
    renderTrace();
  }

  function renderTrace() {
    const log = $('tcTraceLog');
    log.textContent = state.traces.length
      ? state.traces.map((item) => '[' + item.type + '] ' + item.message).join('\n')
      : 'Waiting for task to start';
    log.scrollTop = log.scrollHeight;
  }

  function renderMeta() {
    const el = $('tcMetaLine');
    if (!state.meta) {
      el.textContent = 'Not generated yet';
      return;
    }
    const count = state.cases.length || state.meta.result_count || 0;
    el.textContent = 'Source: ' + state.meta.source + ' · Model: ' + state.meta.model + ' · Results: ' + count + ' · job: ' + state.meta.job_id;
  }

  function renderTabs() {
    const tabs = $('tcCaseTabs');
    if (!state.cases.length) {
      tabs.innerHTML = '';
      return;
    }
    tabs.innerHTML = state.cases.map(function (item, index) {
      return '<button type="button" class="tc-case-tab ' + (index === state.selected ? 'is-active' : '') + '" data-tc-case="' + index + '">' + esc(index + 1 + '. ' + item.title) + '</button>';
    }).join('');
    tabs.querySelectorAll('[data-tc-case]').forEach(function (button) {
      button.addEventListener('click', function () {
        saveEditorToCase();
        state.selected = Number(button.dataset.tcCase);
        renderSelectedCase();
      });
    });
  }

  function renderSelectedCase() {
    renderTabs();
    const item = state.cases[state.selected];
    $('tcCaseEditor').value = item ? item.testcase : '';
    renderCaseFields();
    renderMeta();
    renderEvidence();
  }

  function renderCaseFields() {
    const item = state.cases[state.selected];
    const fields = $('tcCaseFields');
    if (!item) {
      fields.innerHTML = '';
      return;
    }
    const blocks = [
      ['Preconditions', item.preconditions],
      ['Actions', item.actions],
      ['Expected Behavior', item.expected_behaviors]
    ];
    fields.innerHTML = blocks.map(function (block) {
      const items = block[1] || [];
      return '<div class="tc-field"><b>' + esc(block[0]) + '</b>' + (items.length ? '<ul>' + items.map((x) => '<li>' + esc(x) + '</li>').join('') + '</ul>' : '<span class="muted">Not identified</span>') + '</div>';
    }).join('');
  }

  function saveEditorToCase() {
    const item = state.cases[state.selected];
    if (!item) return;
    item.testcase = $('tcCaseEditor').value.trim();
    const parsed = parseGeneratedCase(item.testcase);
    item.title = caseTitle(item.testcase, item.title);
    item.preconditions = parsed.pre;
    item.actions = parsed.act;
    item.expected_behaviors = parsed.exp;
  }

  function setCases(cases, source, persist) {
    state.cases = (cases || []).map((item, index) => normalizeCase(item, index, source)).filter((item) => item.testcase);
    state.selected = 0;
    state.evalIssues = [];
    $('tcEvalBox').hidden = true;
    renderSelectedCase();
    if (persist !== false) saveRecord();
  }

  function renderEvidence() {
    const box = $('tcEvidenceList');
    const data = state.evidence || {};
    const items = [];
    (data.retrieved_testcases || []).slice(0, 5).forEach(function (item) {
      items.push({ title: item.case_name || item.title || 'Similar test case', detail: [item.test_type, ensureArray(item.actions).join('; '), ensureArray(item.expected_behaviors).join('; ')].filter(Boolean).join(' / ') });
    });
    (data.pdf_kg_evidence || []).slice(0, 5).forEach(function (item) {
      items.push({ title: item.title || item.source || 'PDF evidence', detail: item.text || item.content || JSON.stringify(item).slice(0, 220) });
    });
    const current = state.cases[state.selected];
    if (current && (current.raw.llm_error || current.raw.rag_error || current.raw.source_quality)) {
      items.unshift({
        title: 'Generation status',
        detail: [current.raw.source_quality ? 'Quality: ' + current.raw.source_quality : '', current.raw.rag_error ? 'RAG: ' + current.raw.rag_error : '', current.raw.llm_error ? 'Model: ' + current.raw.llm_error : ''].filter(Boolean).join(' / ')
      });
    }
    box.innerHTML = items.length
      ? '<h3>Evidence & Status</h3>' + items.map((item) => '<div class="tc-evidence-item"><strong>' + esc(item.title) + '</strong><small>' + esc(item.detail || '') + '</small></div>').join('')
      : '<h3>Evidence & Status</h3><p class="empty-state">No evidence</p>';
  }

  function saveRecord() {
    if (!state.meta || !state.cases.length) return;
    const record = {
      id: state.meta.job_id,
      created_at: new Date().toISOString(),
      source: state.meta.source,
      model: state.meta.model,
      ui_version: UI_VERSION,
      query: $('tcRequirementInput').value.trim(),
      meta: state.meta,
      cases: state.cases
    };
    state.records = [record].concat(state.records.filter((item) => item.id !== record.id)).slice(0, 60);
    writeJson(RECORD_KEY, state.records);
    renderRecords();
  }

  function renderRecords() {
    const list = $('tcRecordList');
    if (!state.records.length) {
      list.innerHTML = '<p class="empty-state">No records</p>';
      return;
    }
    list.innerHTML = state.records.map(function (record, index) {
      const first = (record.cases || [])[0] || {};
      return '<button type="button" class="tc-record" data-record-index="' + index + '"><strong>' + esc(first.title || record.query || record.source || 'Generation task') + '</strong><small>' + esc(record.source || '') + ' / ' + esc(record.model || '') + ' / ' + esc(record.created_at || '') + '</small></button>';
    }).join('');
    list.querySelectorAll('[data-record-index]').forEach(function (button) {
      button.addEventListener('click', function () {
        const record = state.records[Number(button.dataset.recordIndex)];
        state.meta = record.meta || record;
        state.traces = state.meta.trace || record.trace || [];
        state.evidence = null;
        setCases(record.cases || [], record.source || 'history', false);
        switchTab('records');
        setStatus('History restored');
      });
    });
  }

  async function readNdjson(response, onEvent) {
    if (!response.ok || !response.body) {
      let message = 'Request failed: ' + response.status;
      try {
        const payload = await response.json();
        message = payload.error || payload.message || message;
      } catch (_) {}
      throw new Error(message);
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
      const chunk = await reader.read();
      if (chunk.done) break;
      buffer += decoder.decode(chunk.value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';
      lines.forEach(function (line) {
        const trimmed = line.trim();
        if (!trimmed) return;
        onEvent(JSON.parse(trimmed));
      });
    }
    if (buffer.trim()) onEvent(JSON.parse(buffer.trim()));
  }

  function casesFromText(text, source, data) {
    const clean = splitThinkAndAnswer(text).answerText;
    return splitGeneratedCases(clean).map(function (part, index) {
      return {
        testcase: part,
        source,
        model: data?.model || selectedModel(),
        document_id: data?.document_id || state.sts.doc?.document_id || '',
        trace: state.traces.slice()
      };
    });
  }

  async function generateFromRequirement() {
    const requirement = $('tcRequirementInput').value.trim();
    if (!requirement) {
      setStatus('Please enter a test requirement', true);
      return;
    }
    startMeta('natural_language', { model: selectedModel(), testcase_count: selectedCount() });
    setStatus('Generating test cases...');
    addTrace('Submitted requirement: ' + requirement, 'start');
    setBusy(true);
    try {
      await readNdjson(await fetch('/generate-stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_input: requirement, testcase_count: selectedCount(), model: selectedModel() })
      }), function (event) {
        if (event.type === 'thought') addTrace(event.message, 'thought');
        if (event.type === 'result' && event.data) {
          const split = splitThinkAndAnswer(event.data.testcase || '');
          if (split.thinkText) addTrace(split.thinkText, 'model');
          state.evidence = event.data;
          finishMeta({ elapsed_time: event.data.elapsed_time, model: event.data.model || selectedModel(), testcase_count: event.data.testcase_count || selectedCount() });
          setCases(casesFromText(event.data.testcase || '', 'natural_language', event.data), 'natural_language');
          setStatus('Generation complete');
        }
        if (event.type === 'error') throw new Error(event.message || 'Generation failed');
      });
    } catch (error) {
      setStatus(error.message || 'Generation failed', true);
      addTrace(error.message || 'Generation failed', 'error');
    } finally {
      setBusy(false);
    }
  }

  async function evaluateCurrentCase() {
    saveEditorToCase();
    const item = state.cases[state.selected];
    if (!item || !item.testcase) return setStatus('No test case available to evaluate', true);
    setBusy(true);
    setStatus('Evaluating...');
    try {
      const response = await fetch('/api/evaluate-testcase', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ testcase: item.testcase })
      });
      const result = await response.json();
      if (!result.success) throw new Error(result.error || 'Evaluation failed');
      state.evalIssues = result.issues || [];
      const box = $('tcEvalBox');
      box.hidden = false;
      box.innerHTML = '<strong>Score: ' + esc(result.score) + '</strong>' + (state.evalIssues.length ? '<ul>' + state.evalIssues.map((issue) => '<li>' + esc(issue) + '</li>').join('') + '</ul>' : '<p>No obvious issues found</p>');
      setStatus('Evaluation complete: ' + result.score);
    } catch (error) {
      setStatus(error.message || 'Evaluation failed', true);
    } finally {
      setBusy(false);
    }
  }

  async function refineCurrentCase(instruction) {
    saveEditorToCase();
    const item = state.cases[state.selected];
    const text = item?.testcase || '';
    const inst = (instruction || $('tcRefineInput').value || '').trim();
    if (!text) return setStatus('No test case available to refine', true);
    if (!inst) return setStatus('Please enter refine instructions', true);
    startMeta((item.source || 'natural_language') + '_refine', { model: selectedModel(), testcase_count: 1, document_id: item.document_id || '' });
    addTrace('Refine instructions: ' + inst, 'refine');
    setBusy(true);
    setStatus('Refining...');
    try {
      await readNdjson(await fetch('/refine-stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ current_testcase: text, instruction: inst, eval_issues: state.evalIssues, model: selectedModel() })
      }), function (event) {
        if (event.type === 'thought') addTrace(event.message, 'thought');
        if (event.type === 'result' && event.data) {
          const refined = splitThinkAndAnswer(event.data.testcase || '').answerText;
          state.cases[state.selected] = normalizeCase(Object.assign({}, item, {
            testcase: refined,
            original_testcase: item.original_testcase || text,
            model: event.data.model || selectedModel(),
            trace: state.traces.slice()
          }), state.selected, item.source);
          finishMeta({ elapsed_time: event.data.elapsed_time, model: event.data.model || selectedModel(), result_count: 1 });
          renderSelectedCase();
          saveRecord();
          setStatus('Refine complete');
        }
        if (event.type === 'error') throw new Error(event.message || 'Refine failed');
      });
    } catch (error) {
      setStatus(error.message || 'Refine failed', true);
      addTrace(error.message || 'Refine failed', 'error');
    } finally {
      setBusy(false);
    }
  }

  async function autoImproveCurrentCase() {
    saveEditorToCase();
    const item = state.cases[state.selected];
    if (!item || !item.testcase) return setStatus('No test case available for auto-improve', true);
    const threshold = Math.max(50, Math.min(95, Number($('tcAutoThreshold').value || 95)));
    const maxIterations = Math.max(1, Math.min(5, Number($('tcAutoIterations').value || 3)));
    startMeta((item.source || 'natural_language') + '_auto_improve', { model: selectedModel(), testcase_count: 1, document_id: item.document_id || '' });
    setBusy(true);
    setStatus('Auto-improving...');
    try {
      await readNdjson(await fetch('/auto-improve-stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ current_testcase: item.testcase, threshold, max_iterations: maxIterations, model: selectedModel() })
      }), function (event) {
        if (event.type === 'auto_start') addTrace('Auto-improve started, target ' + event.threshold + ', max ' + event.max_iterations + ' rounds', 'auto');
        if (event.type === 'auto_phase') addTrace(event.message, 'auto');
        if (event.type === 'auto_eval') {
          state.evalIssues = event.issues || [];
          addTrace('Round ' + event.iteration + ' score: ' + event.score + (event.reached ? ', target reached' : ''), 'auto');
        }
        if (event.type === 'result' && event.data) {
          const refined = splitThinkAndAnswer(event.data.testcase || '').answerText;
          state.cases[state.selected] = normalizeCase(Object.assign({}, item, {
            testcase: refined,
            original_testcase: item.original_testcase || item.testcase,
            model: event.data.model || selectedModel(),
            trace: state.traces.slice()
          }), state.selected, item.source);
          finishMeta({ final_score: event.data.final_score, model: event.data.model || selectedModel(), result_count: 1 });
          renderSelectedCase();
          saveRecord();
          setStatus('Auto-improve complete, final score: ' + (event.data.final_score || 0));
        }
        if (event.type === 'error') throw new Error(event.message || 'Auto-improve failed');
      });
    } catch (error) {
      setStatus(error.message || 'Auto-improve failed', true);
      addTrace(error.message || 'Auto-improve failed', 'error');
    } finally {
      setBusy(false);
    }
  }

  function reviewPayload(item) {
    return {
      source: item.source,
      case_id: item.case_id || item.id,
      title: item.title,
      testcase: item.testcase,
      preconditions: item.preconditions,
      actions: item.actions,
      expected_behaviors: item.expected_behaviors,
      model: item.model || selectedModel(),
      ui_version: UI_VERSION,
      prompt_version: state.meta?.prompt_version || 'server-default',
      job_id: state.meta?.job_id || '',
      document_id: item.document_id || '',
      trace: state.traces.slice(),
      generated_at: new Date().toISOString()
    };
  }

  async function reviewCurrentCase(decision) {
    saveEditorToCase();
    const item = state.cases[state.selected];
    if (!item || !item.testcase) return setStatus('No test case available to review', true);
    const comment = $('tcReviewComment').value.trim();
    const fingerprint = hashText([item.source, item.testcase].join('\n'));
    if (state.reviewed.has(fingerprint)) return setStatus('This result was already submitted for review; refine before submitting again.', true);
    setBusy(true);
    setStatus('Submitting review...');
    try {
      let response;
      if (item.case_id && item.status === 'pending_review') {
        response = await fetch('/api/review/test-cases/' + encodeURIComponent(item.case_id), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ decision, comment })
        });
      } else {
        response = await fetch('/api/review/generated-case', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ decision, comment, case: reviewPayload(item) })
        });
      }
      const result = await response.json();
      if (!result.success) throw new Error(result.error || 'Review submit failed');
      item.status = decision;
      state.reviewed.add(fingerprint);
      writeJson(REVIEW_KEY, Array.from(state.reviewed).slice(-300));
      setStatus(decision === 'accepted' ? 'Accepted and stored' : 'Rejected and stored');
      saveRecord();
    } catch (error) {
      setStatus(error.message || 'Review submit failed', true);
    } finally {
      setBusy(false);
    }
  }

  function exportCases(type) {
    saveEditorToCase();
    if (!state.cases.length) return setStatus('No test cases available to export', true);
    if (type === 'txt') {
      downloadBlob('test_cases_' + Date.now() + '.txt', 'text/plain;charset=utf-8', state.cases.map((item, index) => '# ' + (index + 1) + '. ' + item.title + '\n\n' + item.testcase).join('\n\n---\n\n'));
    }
    if (type === 'json') {
      downloadBlob('test_cases_' + Date.now() + '.json', 'application/json;charset=utf-8', JSON.stringify({ meta: state.meta, cases: state.cases }, null, 2));
    }
    if (type === 'excel') exportExcel();
  }

  async function exportExcel() {
    const rows = state.cases.map(function (item) {
      return {
        '测试用例名称': item.title,
        '前提条件': item.preconditions.join('\n'),
        '执行动作': item.actions.join('\n'),
        '预期行为': item.expected_behaviors.join('\n'),
        '生成方式': [item.source, item.model || selectedModel(), UI_VERSION].filter(Boolean).join(' / ')
      };
    });
    setBusy(true);
    try {
      const response = await fetch('/api/export-generated-cases-excel', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cases: rows })
      });
      if (!response.ok) throw new Error('Excel export failed');
      downloadBlob('test_cases_' + Date.now() + '.xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', await response.blob());
      setStatus('Excel exported');
    } catch (error) {
      setStatus(error.message || 'Excel export failed', true);
    } finally {
      setBusy(false);
    }
  }

  function downloadBlob(filename, type, content) {
    const blob = content instanceof Blob ? content : new Blob([content], { type });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  function renderStsDoc() {
    const card = $('tcStsDocCard');
    const doc = state.sts.doc;
    if (!doc) {
      card.hidden = true;
      $('tcStsParseBtn').disabled = true;
      $('tcStsGenerateBtn').disabled = true;
      $('tcStsArtifactsBtn').disabled = true;
      return;
    }
    card.hidden = false;
    card.innerHTML = '<strong>' + esc(doc.filename || doc.document_id) + '</strong><div class="tc-badges"><span class="tc-badge">' + esc(doc.status || 'registered') + '</span><span class="tc-badge">' + esc(doc.document_id) + '</span></div>';
    $('tcStsParseBtn').disabled = state.busy;
    $('tcStsGenerateBtn').disabled = state.busy || !(state.sts.sections.length || state.sts.clusters.length);
    $('tcStsArtifactsBtn').disabled = state.busy;
  }

  function renderStsSelections() {
    const list = $('tcStsSectionList');
    const clusters = state.sts.clusters || [];
    const sections = state.sts.sections || [];
    const rows = [];
    clusters.forEach(function (cluster) {
      rows.push('<label class="tc-choice"><input type="checkbox" data-sts-cluster="' + esc(cluster.cluster_id || '') + '"><span><strong>' + esc(cluster.topic || 'STS topic') + '</strong><small>' + esc([cluster.cluster_id, (cluster.requirement_units || []).length + ' requirement units'].join(' · ')) + '</small></span></label>');
    });
    sections.forEach(function (section) {
      rows.push('<label class="tc-choice"><input type="checkbox" data-sts-section="' + esc(section.section_id || '') + '"><span><strong>' + esc(section.title || section.section_title || 'Section') + '</strong><small>' + esc([section.section_id, section.page_start ? 'P' + section.page_start : ''].filter(Boolean).join(' · ')) + '</small></span></label>');
    });
    list.innerHTML = rows.length ? rows.join('') : '<p class="empty-state">Sections and topics appear after parsing</p>';
    renderStsDoc();
  }

  async function uploadStsFile() {
    const file = $('tcStsFile').files[0];
    if (!file) return setStatus('Please select an STS PDF file', true);
    const form = new FormData();
    form.append('file', file);
    await loadStsDocument('/api/sts/upload', { method: 'POST', body: form }, 'STS PDF uploaded');
  }

  async function registerStsUrl() {
    const url = $('tcStsUrl').value.trim();
    if (!url) return setStatus('Please enter a PDF URL', true);
    await loadStsDocument('/api/sts/register-url', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url })
    }, 'STS URL registered');
  }

  async function loadStsDocument(url, options, successMessage) {
    setBusy(true);
    try {
      const result = await fetchJson(url, options);
      state.sts.doc = result.data;
      state.sts.sections = result.data.sections || [];
      state.sts.clusters = result.data.topic_clusters || [];
      renderStsSelections();
      setStatus(successMessage);
    } catch (error) {
      setStatus(error.message, true);
    } finally {
      setBusy(false);
    }
  }

  async function parseSts() {
    if (!state.sts.doc) return setStatus('Please upload or register an STS document first', true);
    setBusy(true);
    setStatus('Parsing STS document...');
    try {
      const result = await fetchJson('/api/sts/parse/' + encodeURIComponent(state.sts.doc.document_id), { method: 'POST' });
      state.sts.doc = result.data;
      state.sts.sections = result.data.sections || [];
      state.sts.clusters = result.data.topic_clusters || [];
      renderStsSelections();
      setStatus('Parse complete: ' + state.sts.sections.length + ' sections, ' + state.sts.clusters.length + ' topics');
    } catch (error) {
      setStatus(error.message || 'STS parse failed', true);
    } finally {
      setBusy(false);
    }
  }

  async function generateFromSts() {
    if (!state.sts.doc) return setStatus('Please prepare an STS document first', true);
    const clusterIds = Array.from(root.querySelectorAll('[data-sts-cluster]:checked')).map((input) => input.dataset.stsCluster);
    const sectionIds = Array.from(root.querySelectorAll('[data-sts-section]:checked')).map((input) => input.dataset.stsSection);
    if (!clusterIds.length && !sectionIds.length) return setStatus('Please select a topic or section', true);
    startMeta('sts_document', { model: selectedModel(), testcase_count: selectedCount(), document_id: state.sts.doc.document_id });
    addTrace('STS generation started: ' + (clusterIds.length ? clusterIds.length + ' topics' : sectionIds.length + ' sections'), 'sts');
    setBusy(true);
    setStatus('Generating test cases from STS...');
    try {
      const result = await fetchJson('/api/sts/generate-cases/' + encodeURIComponent(state.sts.doc.document_id), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          cluster_ids: clusterIds,
          section_ids: clusterIds.length ? [] : sectionIds,
          max_units: 3,
          max_sections: 3,
          use_rag: true,
          testcase_count: selectedCount(),
          model: selectedModel()
        })
      });
      const cases = result.data.generated_cases || [];
      finishMeta({ result_count: cases.length, document_id: state.sts.doc.document_id });
      addTrace('STS generation complete: ' + cases.length + ' cases', 'sts');
      state.evidence = { retrieved_testcases: cases.flatMap((item) => item.retrieved_testcases || []), pdf_kg_evidence: [] };
      setCases(cases, 'sts_document');
      setStatus('STS generation complete: ' + cases.length + ' cases');
    } catch (error) {
      setStatus(error.message || 'STS generation failed', true);
      addTrace(error.message || 'STS generation failed', 'error');
    } finally {
      setBusy(false);
    }
  }

  async function showStsArtifacts() {
    if (!state.sts.doc) return;
    setBusy(true);
    try {
      const result = await fetchJson('/api/sts/artifacts/' + encodeURIComponent(state.sts.doc.document_id));
      state.sts.artifacts = result.data;
      const box = $('tcStsArtifacts');
      const counts = result.data.counts || {};
      box.hidden = false;
      box.innerHTML = '<strong>Artifacts</strong><div class="tc-badges"><span class="tc-badge">Sections ' + esc(counts.sections || 0) + '</span><span class="tc-badge">Requirement units ' + esc(counts.requirement_units || 0) + '</span><span class="tc-badge">Signals ' + esc(counts.signals || 0) + '</span><span class="tc-badge">Topics ' + esc(counts.topic_clusters || 0) + '</span></div>';
      setStatus('STS artifacts loaded');
    } catch (error) {
      setStatus(error.message || 'Failed to load artifacts', true);
    } finally {
      setBusy(false);
    }
  }

  async function fetchJson(url, options) {
    const response = await fetch(url, options || {});
    const payload = await response.json();
    if (!response.ok || payload.success === false) throw new Error(payload.error || payload.message || 'Request failed');
    return payload;
  }

  function switchTab(tab) {
    state.activeTab = tab;
    root.querySelectorAll('[data-tc-tab]').forEach((button) => button.classList.toggle('is-active', button.dataset.tcTab === tab));
    root.querySelectorAll('[data-tc-panel]').forEach((panel) => panel.classList.toggle('is-active', panel.dataset.tcPanel === tab));
  }

  function bind() {
    root.querySelectorAll('[data-tc-tab]').forEach((button) => button.addEventListener('click', () => switchTab(button.dataset.tcTab)));
    root.querySelectorAll('[data-chip]').forEach(function (button) {
      button.addEventListener('click', function () {
        const input = $('tcRequirementInput');
        input.value = (input.value.trim() ? input.value.trim() + '，' : '') + button.dataset.chip;
        input.focus();
      });
    });
    $('tcClearRequirement').addEventListener('click', () => { $('tcRequirementInput').value = ''; });
    $('tcGenerateBtn').addEventListener('click', generateFromRequirement);
    $('tcCaseEditor').addEventListener('input', function () {
      saveEditorToCase();
      renderCaseFields();
      renderTabs();
    });
    $('tcClearTrace').addEventListener('click', function () { state.traces = []; if (state.meta) state.meta.trace = []; renderTrace(); renderMeta(); });
    $('tcEvaluateBtn').addEventListener('click', evaluateCurrentCase);
    $('tcRefineBtn').addEventListener('click', () => refineCurrentCase());
    $('tcAutoImproveBtn').addEventListener('click', autoImproveCurrentCase);
    $('tcAcceptBtn').addEventListener('click', () => reviewCurrentCase('accepted'));
    $('tcRejectBtn').addEventListener('click', () => reviewCurrentCase('rejected'));
    $('tcExportTxtBtn').addEventListener('click', () => exportCases('txt'));
    $('tcExportJsonBtn').addEventListener('click', () => exportCases('json'));
    $('tcExportExcelBtn').addEventListener('click', () => exportCases('excel'));
    $('tcStsUploadBtn').addEventListener('click', uploadStsFile);
    $('tcStsUseUrlBtn').addEventListener('click', registerStsUrl);
    $('tcStsParseBtn').addEventListener('click', parseSts);
    $('tcStsGenerateBtn').addEventListener('click', generateFromSts);
    $('tcStsArtifactsBtn').addEventListener('click', showStsArtifacts);
    $('tcRefreshRecords').addEventListener('click', renderRecords);
  }

  bind();
  renderRecords();
  renderSelectedCase();
  icons();
})();
