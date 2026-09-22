/**
 * Test case generation tool - frontend logic
 */

class CaseGenerationApp {
    constructor() {
        this.typeActionGroups = {};  // Two-level classification data
        this.selectedCases = new Set();
        this.currentType = null;  // Currently selected test type
        this.currentAction = null;  // Currently selected action
        this.currentCases = [];
        this.statistics = {};
        this.filterType = 'all';
        this.searchQuery = '';
        
        this.init();
    }
    
    async init() {
        console.log('Initializing case generation tool...');
        this.bindEvents();
        await this.loadActionGroups();
    }
    
    // Load cases grouped by test type and action
    async loadActionGroups() {
        try {
            const response = await fetch('/api/test-cases/by-action');
            const result = await response.json();
            
            if (result.success) {
                this.typeActionGroups = result.data;
                this.statistics = result.statistics;
                
                console.log('Load succeeded:', this.statistics);
                console.log('Test type count:', this.statistics.测试类型数);
                console.log('Action category count:', this.statistics.动作分类数);
                
                this.updateStatsDisplay();
                this.renderTypeList();
            } else {
                this.showError('Load failed: ' + result.error);
            }
        } catch (error) {
            console.error('Load failed:', error);
            this.showError('Network error; please refresh and retry');
        }
    }
    
    // Update statistics display
    updateStatsDisplay() {
        const statsText = document.getElementById('statsText');
        statsText.textContent = `Total ${this.statistics.总案例数} cases | ${this.statistics.测试类型数} test types | ${this.statistics.动作分类数} action categories | Selected ${this.selectedCases.size}`;
        
        const actionCount = document.getElementById('actionCount');
        actionCount.textContent = this.statistics.测试类型数;
    }
    
    // Render test type list (two-level; filtered by filterType)
    renderTypeList() {
        const container = document.getElementById('actionList');
        container.innerHTML = '';
        
        const entries = Object.entries(this.typeActionGroups);
        
        console.log('Rendering test type list, count', entries.length, 'types, filter mode:', this.filterType);
        
        if (entries.length === 0) {
            container.innerHTML = '<div class="loading">No data</div>';
            return;
        }
        
        let visibleTypeCount = 0;
        
        entries.forEach(([testType, typeData]) => {
            // Filter actions and cases by filterType
            const filteredActions = {};
            let filteredTotalCount = 0;
            
            Object.entries(typeData.actions).forEach(([action, cases]) => {
                // Filter cases by criteria
                let filteredCases = cases;
                if (this.filterType === 'single') {
                    filteredCases = cases.filter(c => c.是否单一预期);
                } else if (this.filterType === 'multiple') {
                    filteredCases = cases.filter(c => !c.是否单一预期);
                }
                
                // Show only when the action has matching cases
                if (filteredCases.length > 0) {
                    filteredActions[action] = filteredCases;
                    filteredTotalCount += filteredCases.length;
                }
            });
            
            // Skip types with no matching cases
            if (filteredTotalCount === 0) {
                console.log(`  Skip ${testType}: no cases matching filter`);
                return;
            }
            
            visibleTypeCount++;
            const actionCount = Object.keys(filteredActions).length;
            console.log(`  📁 ${testType}: ${filteredTotalCount} cases, ${actionCount} actions`);
            
            // Create test type group
            const typeGroup = document.createElement('div');
            typeGroup.className = 'type-group';
            
            // Test type header (collapsible)
            const typeHeader = document.createElement('div');
            typeHeader.className = 'type-header';
            typeHeader.innerHTML = `
                <input type="checkbox" class="type-checkbox" data-type="${this.escapeHtml(testType)}" title="Select/deselect all cases under this type">
                <span class="type-toggle">▶</span>
                <span class="type-name">${this.escapeHtml(testType)}</span>
                <span class="type-count">${filteredTotalCount}</span>
            `;
            
            // Action list (collapsed by default)
            const actionList = document.createElement('div');
            actionList.className = 'action-list-nested collapsed';
            
            Object.entries(filteredActions).forEach(([action, cases]) => {
                const actionItem = document.createElement('div');
                actionItem.className = 'action-item nested';
                actionItem.innerHTML = `
                    <span class="action-name">${this.escapeHtml(action)}</span>
                    <span class="case-count">${cases.length}</span>
                `;
                actionItem.onclick = (e) => {
                    e.stopPropagation();
                    this.selectAction(testType, action);
                };
                actionList.appendChild(actionItem);
            });
            
            console.log(`    Rendered ${actionList.children.length} action items`);
            
            // Select-all checkbox event
            const typeCheckbox = typeHeader.querySelector('.type-checkbox');
            typeCheckbox.onclick = (e) => {
                e.stopPropagation();
                this.toggleTypeSelection(testType, typeCheckbox.checked);
            };
            
            // Toggle collapse on type header click
            typeHeader.onclick = (e) => {
                // Do not collapse when clicking the checkbox
                if (e.target.classList.contains('type-checkbox')) return;
                
                actionList.classList.toggle('collapsed');
                const toggle = typeHeader.querySelector('.type-toggle');
                toggle.textContent = actionList.classList.contains('collapsed') ? '▶' : '▼';
            };
            
            typeGroup.appendChild(typeHeader);
            typeGroup.appendChild(actionList);
            container.appendChild(typeGroup);
        });
        
        // Show empty state when no types match
        if (visibleTypeCount === 0) {
            const filterName = this.filterType === 'single' ? 'Single expected result' : 
                              this.filterType === 'multiple' ? 'Multiple expected results' : 'All';
            container.innerHTML = `<div class="empty-state"><p>No test cases for ${filterName}</p></div>`;
            console.log('No test types match the filter');
            return;
        }
        
        console.log(`Showing ${visibleTypeCount} test types`);
        
        // Sticky header IntersectionObserver
        this.setupStickyHeaders();
    }
    
    // Set up sticky header observer
    setupStickyHeaders() {
        const container = document.getElementById('actionList').parentElement;
        
        // Detect sticky headers with IntersectionObserver
        const observer = new IntersectionObserver(
            (entries) => {
                entries.forEach(entry => {
                    const header = entry.target;
                    // Add sticky class when header reaches top
                    if (entry.intersectionRatio < 1) {
                        header.classList.add('sticky');
                    } else {
                        header.classList.remove('sticky');
                    }
                });
            },
            {
                root: container,
                threshold: [1],
                rootMargin: '-1px 0px 0px 0px'
            }
        );
        
        // Observe all type headers
        document.querySelectorAll('.type-header').forEach(header => {
            observer.observe(header);
        });
    }
    
    // Select an action
    selectAction(testType, action) {
        this.currentType = testType;
        this.currentAction = action;
        this.currentCases = this.typeActionGroups[testType]?.actions[action] || [];
        
        // Update UI
        document.querySelectorAll('.action-item').forEach(item => {
            item.classList.remove('active');
        });
        event.currentTarget.classList.add('active');
        
        document.getElementById('currentAction').textContent = `${testType} > ${action}`;
        document.getElementById('caseCount').textContent = `${this.currentCases.length} cases`;
        
        this.applyFilters();
    }
    
    // Select/deselect all cases under a test type
    toggleTypeSelection(testType, isChecked) {
        console.log(`${isChecked ? 'ON' : 'OFF'} select-all type: ${testType}, filter: ${this.filterType}`);
        
        const typeData = this.typeActionGroups[testType];
        if (!typeData) return;
        
        // Collect all cases under the type filtered by current criteria
        const allCasesInType = [];
        Object.values(typeData.actions).forEach(cases => {
            // Filter cases by criteria
            let filteredCases = cases;
            if (this.filterType === 'single') {
                filteredCases = cases.filter(c => c.是否单一预期);
            } else if (this.filterType === 'multiple') {
                filteredCases = cases.filter(c => !c.是否单一预期);
            }
            // No filter when filterType === 'all'
            
            allCasesInType.push(...filteredCases);
        });
        
        console.log(`  Matching cases under type: ${allCasesInType.length}`);
        
        if (isChecked) {
            // Select all: add matching unique_ids to selectedCases
            allCasesInType.forEach(caseItem => {
                const uniqueId = caseItem.unique_id;
                if (!this.selectedCases.has(uniqueId)) {
                    this.selectedCases.add(uniqueId);
                }
            });
            console.log(`Selected ${allCasesInType.length} cases`);
        } else {
            // Deselect all: remove matching unique_ids
            allCasesInType.forEach(caseItem => {
                const uniqueId = caseItem.unique_id;
                this.selectedCases.delete(uniqueId);
            });
            console.log(`Deselected ${allCasesInType.length} cases`);
        }
        
        // Update stats display
        this.updateStatsDisplay();
        
        // Update selection UI (Selected count on the right)
        this.updateSelectionUI();
        
        // Refresh checkboxes if viewing an action under this type
        if (this.currentType === testType && this.currentAction) {
            this.applyFilters();
        }
    }
    
    // Apply filter and search
    applyFilters() {
        let filteredCases = [...this.currentCases];
        
        // Apply type filter
        if (this.filterType === 'single') {
            // Single expected result only
            filteredCases = filteredCases.filter(c => c.是否单一预期);
        } else if (this.filterType === 'multiple') {
            // Multiple expected results only
            filteredCases = filteredCases.filter(c => !c.是否单一预期);
        }
        // Show all cases when filterType === 'all'
        
        // Apply search
        if (this.searchQuery) {
            const query = this.searchQuery.toLowerCase();
            filteredCases = filteredCases.filter(c => 
                c.测试用例名称.toLowerCase().includes(query) ||
                c.编号.toLowerCase().includes(query)
            );
        }
        
        this.renderCaseList(filteredCases);
    }
    
    // Render case list (single vs multiple expected)
    renderCaseList(cases) {
        const container = document.getElementById('caseList');
        container.innerHTML = '';
        
        if (cases.length === 0) {
            container.innerHTML = '<div class="empty-state"><p>No matching cases</p></div>';
            return;
        }
        
        // Group: single vs multiple expected
        const singleExpectedCases = cases.filter(c => c.是否单一预期);
        const multipleExpectedCases = cases.filter(c => !c.是否单一预期);
        
        // Render single-expected group
        if (singleExpectedCases.length > 0) {
            const singleSection = document.createElement('div');
            singleSection.className = 'case-section';
            singleSection.innerHTML = `
                <div class="section-header">
                    <h3 class="section-title">
                        <span class="section-icon">✓</span>
                        Single-expected-result cases
                        <span class="section-count">${singleExpectedCases.length}</span>
                    </h3>
                </div>
                <div class="section-content" id="singleCasesList"></div>
            `;
            container.appendChild(singleSection);
            
            const singleContainer = singleSection.querySelector('#singleCasesList');
            singleExpectedCases.forEach(testCase => {
                const card = this.createCaseCard(testCase);
                singleContainer.appendChild(card);
            });
        }
        
        // Render multiple-expected group
        if (multipleExpectedCases.length > 0) {
            const multipleSection = document.createElement('div');
            multipleSection.className = 'case-section';
            multipleSection.innerHTML = `
                <div class="section-header">
                    <h3 class="section-title">
                        <span class="section-icon">📋</span>
                        Multiple-expected-result cases
                        <span class="section-count">${multipleExpectedCases.length}</span>
                    </h3>
                </div>
                <div class="section-content" id="multipleCasesList"></div>
            `;
            container.appendChild(multipleSection);
            
            const multipleContainer = multipleSection.querySelector('#multipleCasesList');
            multipleExpectedCases.forEach(testCase => {
                const card = this.createCaseCard(testCase);
                multipleContainer.appendChild(card);
            });
        }
    }
    
    // Create case card
    createCaseCard(testCase) {
        const card = document.createElement('div');
        card.className = 'case-card';
        const caseId = testCase.unique_id || testCase.编号;  // Use unique_id
        
        if (this.selectedCases.has(caseId)) {
            card.classList.add('selected');
        }
        
        const singleBadge = testCase.是否单一预期 
            ? '<span class="single-expected-badge">✓ Single expected</span>' 
            : '';
        
        card.innerHTML = `
            <div class="case-header">
                <input type="checkbox" 
                       class="case-checkbox" 
                       data-id="${caseId}"
                       ${this.selectedCases.has(caseId) ? 'checked' : ''}>
                <span class="case-id">${this.escapeHtml(testCase.编号 || caseId)}</span>
                <span class="case-type">${this.escapeHtml(testCase.测试用例类型)}</span>
                ${singleBadge}
            </div>
            <div class="case-body">
                <h4>${this.escapeHtml(testCase.测试用例名称)}</h4>
                <div class="case-preconditions">
                    <strong>Preconditions:</strong>
                    <ul>
                        ${testCase.前提条件.map(c => `<li>${this.escapeHtml(c)}</li>`).join('')}
                    </ul>
                </div>
                <div class="case-expected">
                    <strong>Expected Behavior:</strong>
                    <span class="expected-text">${this.escapeHtml(testCase.预期行为)}</span>
                </div>
            </div>
        `;
        
        // Bind checkbox events
        const checkbox = card.querySelector('.case-checkbox');
        checkbox.addEventListener('change', (e) => {
            e.stopPropagation();
            this.toggleCaseSelection(caseId, e.target.checked);
        });
        
        // Clicking the card also toggles selection
        card.addEventListener('click', (e) => {
            if (e.target.type !== 'checkbox') {
                checkbox.checked = !checkbox.checked;
                this.toggleCaseSelection(caseId, checkbox.checked);
            }
        });
        
        return card;
    }
    
    // Toggle case selection
    toggleCaseSelection(caseId, selected) {
        if (selected) {
            this.selectedCases.add(caseId);
        } else {
            this.selectedCases.delete(caseId);
        }
        
        this.updateSelectionUI();
        
        // Update card style
        document.querySelectorAll('.case-card').forEach(card => {
            const checkbox = card.querySelector('.case-checkbox');
            if (checkbox && checkbox.dataset.id === caseId) {
                card.classList.toggle('selected', selected);
            }
        });
    }
    
    // Update selection UI
    updateSelectionUI() {
        const count = this.selectedCases.size;
        document.getElementById('selectedCount').textContent = `Selected: ${count}`;
        document.getElementById('generateCount').textContent = count;
        document.getElementById('generateBtn').disabled = count === 0;
    }
    
    // Select all currently displayed cases
    selectAllCases() {
        const checkboxes = document.querySelectorAll('.case-checkbox');
        checkboxes.forEach(cb => {
            cb.checked = true;
            this.selectedCases.add(cb.dataset.id);
        });
        this.updateSelectionUI();
        document.querySelectorAll('.case-card').forEach(card => {
            card.classList.add('selected');
        });
    }
    
    // Clear selection
    clearSelection() {
        this.selectedCases.clear();
        document.querySelectorAll('.case-checkbox').forEach(cb => {
            cb.checked = false;
        });
        document.querySelectorAll('.case-card').forEach(card => {
            card.classList.remove('selected');
        });
        this.updateSelectionUI();
    }
    
    // Generate reverse cases
    async generateReverseCases() {
        if (this.selectedCases.size === 0) {
            this.showError('Please select test cases to generate from first');
            return;
        }
        
        console.log('Generation mode: batch');
        console.log('Selected case count:', this.selectedCases.size);
        
        this.showProgressModal();
        
        try {
            // Call generation API (batch mode)
            const response = await fetch('/api/test-cases/generate-reverse', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    case_ids: Array.from(this.selectedCases),
                    generation_mode: 'batch',  // Always use batch mode
                    model_name: 'qwen2.5-3b-finetune-data-continued'
                })
            });
            
            const result = await response.json();
            
            if (result.success) {
                console.log('Task created:', result.task_id);
                // Poll progress
                this.pollGenerationStatus(result.task_id);
            } else {
                this.hideProgressModal();
                this.showError('Generation failed: ' + result.error);
            }
        } catch (error) {
            console.error('Generation failed:', error);
            this.hideProgressModal();
            this.showError('Network error; please retry');
        }
    }
    
    // Poll generation progress
    async pollGenerationStatus(taskId) {
        const pollInterval = setInterval(async () => {
            try {
                const response = await fetch(`/api/test-cases/generation-status/${taskId}`);
                const result = await response.json();
                
                if (result.success) {
                    const progress = result.progress;
                    this.updateProgressUI(progress);
                    
                    if (result.status === 'completed') {
                        clearInterval(pollInterval);
                        console.log('Generation complete');
                        setTimeout(() => {
                            this.showResults(taskId);
                        }, 500);
                    } else if (result.status === 'failed') {
                        clearInterval(pollInterval);
                        this.hideProgressModal();
                        this.showError('Generation failed; please retry');
                    }
                }
            } catch (error) {
                console.error('Progress query failed:', error);
                clearInterval(pollInterval);
                this.hideProgressModal();
                this.showError('Failed to query progress');
            }
        }, 1000); // Poll once per second
    }
    
    // Update progress UI
    updateProgressUI(progress) {
        const percentage = progress.percentage || 0;
        document.getElementById('progressFill').style.width = `${percentage}%`;
        document.getElementById('progressText').textContent = 
            `${progress.completed} / ${progress.total} (${percentage.toFixed(1)}%)`;
    }
    
    // Show generation results
    async showResults(taskId) {
        try {
            const response = await fetch(`/api/test-cases/reverse-results/${taskId}`);
            const result = await response.json();
            
            if (result.success) {
                this.hideProgressModal();
                this.displayResults(result.data, taskId);
            } else {
                this.showError('Failed to fetch results: ' + result.error);
            }
        } catch (error) {
            console.error('Failed to fetch results:', error);
            this.showError('Failed to fetch results');
        }
    }
    
    // Display results
    displayResults(data, taskId) {
        const modal = document.getElementById('resultModal');
        const content = document.getElementById('resultContent');
        
        content.innerHTML = `
            <div class="result-summary">
                <p>Succeeded: ${data.statistics.成功数}</p>
                <p>Failed: ${data.statistics.失败数}</p>
                <p>Success rate: ${data.statistics.成功率}</p>
            </div>
            <div class="result-list">
                ${this.renderResultList(data.reverse_cases)}
            </div>
        `;
        
        modal.classList.add('show');
        
        // Bind download buttons
        document.getElementById('downloadBtn').onclick = () => {
            this.downloadResults(data, taskId);
        };
    }
    
    // Render result list
    renderResultList(reverseCases) {
        if (reverseCases.length === 0) {
            return '<p style="text-align:center;color:#909399;">No results</p>';
        }
        
        // Batch-mode render only
        return reverseCases.map(rc => this.renderBatchCase(rc)).join('');
    }
    
    // Render batch-generated cases
    renderBatchCase(rc) {
        return `
            <div class="result-item batch-result-item">
                <h4 style="margin: 0 0 15px 0;">
                    🔄 ${this.escapeHtml(rc.案例名称 || 'Untitled')}
                </h4>
                
                <div style="margin: 15px 0;">
                    <h5 style="color: #606266; margin-bottom: 8px;">Preconditions</h5>
                    <ul style="margin: 0; padding-left: 20px;">
                        ${(rc.前提条件 || []).map(c => 
                            `<li style="margin: 4px 0;">${this.escapeHtml(c)}</li>`
                        ).join('')}
                    </ul>
                </div>
                
                <div style="margin: 15px 0;">
                    <h5 style="color: #606266; margin-bottom: 8px;">Expected Behavior</h5>
                    <p style="margin: 0; padding: 10px; background: rgba(255,255,255,0.7); border-radius: 6px;">
                        ${this.escapeHtml(rc.预期行为 || '')}
                    </p>
                </div>
                
                ${(() => {
                    // Ensure related original cases is an array
                    let relatedCases = rc.关联原始案例;
                    if (!relatedCases) return '';
                    
                    // If string, try to parse or convert to array
                    if (typeof relatedCases === 'string') {
                        try {
                            relatedCases = JSON.parse(relatedCases);
                        } catch (e) {
                            // On parse failure, split by comma
                            relatedCases = relatedCases.split(/[,，、]/).map(s => s.trim()).filter(s => s);
                        }
                    }
                    
                    // Ensure non-empty array
                    if (!Array.isArray(relatedCases) || relatedCases.length === 0) return '';
                    
                    return `
                    <div style="margin: 15px 0; padding: 12px; background: linear-gradient(135deg, #fff3e0 0%, #ffe0b2 100%); border-left: 4px solid #ff9800; border-radius: 6px;">
                        <strong style="color: #e65100; font-size: 14px;">Generated from these cases:</strong>
                        <div style="margin-top: 8px;">
                            ${relatedCases.map(name => 
                                `<div style="display: inline-block; padding: 6px 12px; background: white; border: 1px solid #ff9800; border-radius: 4px; margin: 4px; font-size: 13px; font-weight: 500; color: #e65100; max-width: 400px;">${this.escapeHtml(name)}</div>`
                            ).join('')}
                        </div>
                    </div>
                    `;
                })()}
                
                <div style="margin-top: 10px; padding-top: 10px; border-top: 1px solid #e0e0e0; font-size: 12px; color: #909399;">
                    <span>Type: ${this.escapeHtml(rc.测试用例类型 || '')}</span>
                    <span style="margin-left: 15px;">⏰ ${rc.生成时间 || ''}</span>
                </div>
            </div>
        `;
    }
    
    // Download results as Excel
    downloadResults(data, taskId) {
        // Call Excel export API directly
        const exportUrl = `/api/test-cases/export-excel/${taskId}`;
        
        console.log('Starting Excel download...');
        
        // Create hidden anchor for download
        const a = document.createElement('a');
        a.href = exportUrl;
        a.style.display = 'none';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        
        console.log('Excel download started');
    }
    
    // Export selected cases
    exportSelectedCases() {
        const selected = [];
        this.currentCases.forEach(c => {
            if (this.selectedCases.has(c.编号)) {
                selected.push(c);
            }
        });
        
        const jsonStr = JSON.stringify(selected, null, 2);
        const blob = new Blob([jsonStr], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `selected_cases_${new Date().getTime()}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        
        console.log('Exported', selected.length, 'cases');
    }
    
    // Show progress modal
    showProgressModal() {
        const modal = document.getElementById('progressModal');
        modal.classList.add('show');
        document.getElementById('progressFill').style.width = '0%';
        document.getElementById('progressText').textContent = '0 / 0 (0%)';
    }
    
    // Hide progress modal
    hideProgressModal() {
        const modal = document.getElementById('progressModal');
        modal.classList.remove('show');
    }
    
    // Show error message
    showError(message) {
        alert('❌ ' + message);
    }
    
    // HTML escape
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    // Bind events
    bindEvents() {
        // Generate button
        document.getElementById('generateBtn').addEventListener('click', () => {
            this.generateReverseCases();
        });
        
        // Select-all button
        document.getElementById('selectAll').addEventListener('click', () => {
            this.selectAllCases();
        });
        
        // Clear-selection button
        document.getElementById('clearSelection').addEventListener('click', () => {
            this.clearSelection();
        });
        
        // Export button
        document.getElementById('exportBtn').addEventListener('click', () => {
            this.exportSelectedCases();
        });
        
        // Search box
        document.getElementById('searchBox').addEventListener('input', (e) => {
            this.searchQuery = e.target.value;
            if (this.currentAction) {
                this.applyFilters();
            }
        });
        
        // Filter dropdown
        document.getElementById('filterType').addEventListener('change', (e) => {
            this.filterType = e.target.value;
            
            // Re-render left test type list by filter
            this.renderTypeList();
            
            // Re-apply filter if an action is selected
            if (this.currentAction) {
                this.applyFilters();
            }
        });
        
        // Close results modal
        document.getElementById('closeResultModal').addEventListener('click', () => {
            document.getElementById('resultModal').classList.remove('show');
        });
        
        document.getElementById('closeBtn').addEventListener('click', () => {
            document.getElementById('resultModal').classList.remove('show');
        });
        
        // Close when clicking outside modal
        document.getElementById('resultModal').addEventListener('click', (e) => {
            if (e.target.id === 'resultModal') {
                document.getElementById('resultModal').classList.remove('show');
            }
        });
    }
}

// Initialize app
document.addEventListener('DOMContentLoaded', () => {
    console.log('Case generation tool loaded');
    new CaseGenerationApp();
});
