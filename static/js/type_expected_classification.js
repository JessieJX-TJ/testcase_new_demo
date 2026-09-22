/**
 * Test type – expected behavior classification tool
 */

class TypeExpectedClassificationApp {
    constructor() {
        this.typeExpectedGroups = {};  // Data shape: {testType: {expectedBehavior: [cases]}}
        this.currentType = null;
        this.currentExpected = null;
        this.currentCases = [];
        this.statistics = {};
        this.filterType = 'all';
        this.searchQuery = '';
        this.actionColorMap = {};  // Map actions to colors
        this.selectedExpectedBehaviors = new Set();  // Selected expected behaviors
        
        this.init();
    }
    
    // Stable color for an action
    getActionColor(action) {
        if (this.actionColorMap[action]) {
            return this.actionColorMap[action];
        }
        
        // Hash string to color
        let hash = 0;
        for (let i = 0; i < action.length; i++) {
            hash = action.charCodeAt(i) + ((hash << 5) - hash);
        }
        
        // Soft color (high saturation, medium lightness)
        const hue = Math.abs(hash % 360);
        const saturation = 65 + (Math.abs(hash) % 20); // 65-85%
        const lightness = 75 + (Math.abs(hash >> 8) % 15); // 75-90%
        
        const color = `hsl(${hue}, ${saturation}%, ${lightness}%)`;
        this.actionColorMap[action] = color;
        
        return color;
    }
    
    async init() {
        console.log('Initializing type–expected classification tool...');
        this.bindEvents();
        await this.loadTypeExpectedGroups();
    }
    
    // Load cases grouped by test type and expected behavior
    async loadTypeExpectedGroups() {
        try {
            const response = await fetch('/api/test-cases/by-type-expected');
            const result = await response.json();
            
            if (result.success) {
                this.typeExpectedGroups = result.data;
                this.statistics = result.statistics;
                
                console.log('Load succeeded:', this.statistics);
                
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
        statsText.textContent = `Total ${this.statistics.总案例数} cases | ${this.statistics.测试类型数} test types | ${this.statistics.预期行为数} expected behaviors`;
        
        const typeCount = document.getElementById('typeCount');
        typeCount.textContent = this.statistics.测试类型数;
    }
    
    // Render test type list
    renderTypeList() {
        const container = document.getElementById('typeList');
        container.innerHTML = '';
        
        const entries = Object.entries(this.typeExpectedGroups);
        
        console.log('Rendering test type list, count', entries.length, 'types');
        
        if (entries.length === 0) {
            container.innerHTML = '<div class="loading">No data</div>';
            return;
        }
        
        entries.forEach(([testType, typeData]) => {
            // Filter total case count by filterType
            let totalCount = 0;
            Object.values(typeData.expected_behaviors).forEach(cases => {
                if (this.filterType === 'single') {
                    totalCount += cases.filter(c => c.是否单一预期).length;
                } else if (this.filterType === 'multiple') {
                    totalCount += cases.filter(c => !c.是否单一预期).length;
                } else {
                    totalCount += cases.length;
                }
            });
            
            // Skip types with no matching cases
            if (totalCount === 0) return;
            
            const typeItem = document.createElement('div');
            typeItem.className = 'type-item';
            typeItem.innerHTML = `
                <span class="type-name">${this.escapeHtml(testType)}</span>
                <span class="type-count">${totalCount}</span>
            `;
            
            typeItem.onclick = () => this.selectType(testType);
            container.appendChild(typeItem);
        });
    }
    
    // Select test type
    selectType(testType) {
        this.currentType = testType;
        this.currentExpected = null;
        this.currentCases = [];
        
        // Update UI
        document.querySelectorAll('.type-item').forEach(item => {
            item.classList.remove('active');
        });
        event.currentTarget.classList.add('active');
        
        // Show current type info
        const typeInfo = document.getElementById('currentTypeInfo');
        typeInfo.innerHTML = `<strong>Current type:</strong> ${this.escapeHtml(testType)}`;
        
        this.renderExpectedList(testType);
    }
    
    // Render expected behavior list
    renderExpectedList(testType) {
        const container = document.getElementById('expectedList');
        container.innerHTML = '';
        
        const typeData = this.typeExpectedGroups[testType];
        if (!typeData) return;
        
        const expectedBehaviors = typeData.expected_behaviors;
        const entries = Object.entries(expectedBehaviors);
        
        console.log(`Rendering expected behaviors, ${entries.length} items`);
        
        // Sort by case count
        entries.sort((a, b) => b[1].length - a[1].length);
        
        let visibleCount = 0;
        entries.forEach(([expected, cases]) => {
            // Filter cases by filterType
            let filteredCases = cases;
            if (this.filterType === 'single') {
                filteredCases = cases.filter(c => c.是否单一预期);
            } else if (this.filterType === 'multiple') {
                filteredCases = cases.filter(c => !c.是否单一预期);
            }
            
            if (filteredCases.length === 0) return;
            
            visibleCount++;
            
            const expectedItem = document.createElement('div');
            expectedItem.className = 'expected-item';
            
            // Truncate long expected behavior text
            const displayText = expected.length > 60 ? expected.substring(0, 60) + '...' : expected;
            
            // Check selection
            const isChecked = this.selectedExpectedBehaviors.has(expected);
            
            expectedItem.innerHTML = `
                <input type="checkbox" class="expected-checkbox" data-expected="${this.escapeHtml(expected)}" ${isChecked ? 'checked' : ''}>
                <div class="expected-item-content">
                    <span class="expected-text">${this.escapeHtml(displayText)}</span>
                    <span class="expected-count">${filteredCases.length} cases</span>
                </div>
            `;
            
            // Checkbox click
            const checkbox = expectedItem.querySelector('.expected-checkbox');
            checkbox.onclick = (e) => {
                e.stopPropagation();
                this.toggleExpectedSelection(expected, checkbox.checked);
            };
            
            // Clicking the item also selects
            expectedItem.querySelector('.expected-item-content').onclick = () => this.selectExpected(testType, expected);
            expectedItem.title = expected;  // Full text as tooltip
            container.appendChild(expectedItem);
        });
        
        document.getElementById('expectedCount').textContent = visibleCount;
        
        if (visibleCount === 0) {
            container.innerHTML = '<div class="empty-state"><p>No matching expected behaviors</p></div>';
        }
    }
    
    // Select expected behavior
    selectExpected(testType, expected) {
        this.currentType = testType;
        this.currentExpected = expected;
        
        // Get case list
        const typeData = this.typeExpectedGroups[testType];
        this.currentCases = typeData.expected_behaviors[expected] || [];
        
        // Update UI
        document.querySelectorAll('.expected-item').forEach(item => {
            item.classList.remove('active');
        });
        event.currentTarget.classList.add('active');
        
        // Update title
        const displayExpected = expected.length > 50 ? expected.substring(0, 50) + '...' : expected;
        document.getElementById('currentSelection').textContent = `${testType} > ${displayExpected}`;
        
        this.applyFilters();
    }
    
    // Apply filter and search
    applyFilters() {
        let filteredCases = [...this.currentCases];
        
        // Apply type filter
        if (this.filterType === 'single') {
            filteredCases = filteredCases.filter(c => c.是否单一预期);
        } else if (this.filterType === 'multiple') {
            filteredCases = filteredCases.filter(c => !c.是否单一预期);
        }
        
        // Apply search
        if (this.searchQuery) {
            const query = this.searchQuery.toLowerCase();
            filteredCases = filteredCases.filter(c => 
                c.测试用例名称.toLowerCase().includes(query) ||
                c.编号.toLowerCase().includes(query) ||
                c.预期行为.toLowerCase().includes(query)
            );
        }
        
        this.renderCaseList(filteredCases);
    }
    
    // Render case list
    renderCaseList(cases) {
        const container = document.getElementById('caseList');
        container.innerHTML = '';
        
        document.getElementById('caseCount').textContent = `${cases.length} cases`;
        
        if (cases.length === 0) {
            container.innerHTML = '<div class="empty-state"><p>No matching cases</p></div>';
            return;
        }
        
        // Group by action
        const actionGroups = {};
        cases.forEach(testCase => {
            const action = testCase.执行动作;
            if (!actionGroups[action]) {
                actionGroups[action] = [];
            }
            actionGroups[action].push(testCase);
        });
        
        // Sort groups by case count (largest first)
        const sortedActions = Object.keys(actionGroups).sort((a, b) => {
            return actionGroups[b].length - actionGroups[a].length;
        });
        
        // Render cases by group
        sortedActions.forEach((action, groupIndex) => {
            const groupCases = actionGroups[action];
            const actionColor = this.getActionColor(action);
            
            // Add group heading
            if (sortedActions.length > 1) {
                const groupHeader = document.createElement('div');
                groupHeader.className = 'action-group-header';
                groupHeader.style.background = actionColor;
                groupHeader.innerHTML = `
                    <span class="action-group-title">Actions:${this.escapeHtml(action)}</span>
                    <span class="action-group-count">${groupCases.length} cases</span>
                `;
                container.appendChild(groupHeader);
            }
            
            // Render all cases in the group
            groupCases.forEach(testCase => {
                const card = this.createCaseCard(testCase);
                container.appendChild(card);
            });
        });
    }
    
    // Create case card
    createCaseCard(testCase) {
        const card = document.createElement('div');
        card.className = 'case-card';
        
        // Color for action
        const actionColor = this.getActionColor(testCase.执行动作);
        
        card.innerHTML = `
            <div class="case-header">
                <span class="case-id">${this.escapeHtml(testCase.编号)}</span>
                <span class="case-type">${this.escapeHtml(testCase.测试用例类型)}</span>
            </div>
            <div class="case-body">
                <h4>${this.escapeHtml(testCase.测试用例名称)}</h4>
                <div class="case-preconditions">
                    <strong>Preconditions:</strong>
                    <ul>
                        ${testCase.前提条件.map(c => `<li>${this.escapeHtml(c)}</li>`).join('')}
                    </ul>
                </div>
                <div class="case-action" style="background: ${actionColor}; padding: 10px; border-radius: 6px; margin-top: 10px;">
                    <strong style="color: #2c3e50;">Actions:</strong>
                    <span class="action-text" style="color: #2c3e50;">${this.escapeHtml(testCase.执行动作)}</span>
                </div>
                <div class="case-expected">
                    <strong>Expected Behavior:</strong>
                    <span class="expected-text">${this.escapeHtml(testCase.预期行为)}</span>
                </div>
            </div>
        `;
        
        return card;
    }
    
    // Export cases
    exportCases() {
        if (this.currentCases.length === 0) {
            this.showError('No cases to export');
            return;
        }
        
        const jsonStr = JSON.stringify(this.currentCases, null, 2);
        const blob = new Blob([jsonStr], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${this.currentType}_${this.currentExpected.substring(0, 20)}_${new Date().getTime()}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        
        console.log('Exported', this.currentCases.length, 'cases');
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
        // Search box
        document.getElementById('searchBox').addEventListener('input', (e) => {
            this.searchQuery = e.target.value;
            if (this.currentExpected) {
                this.applyFilters();
            }
        });
        
        // Filter dropdown
        document.getElementById('filterType').addEventListener('change', (e) => {
            this.filterType = e.target.value;
            
            // Re-render list
            this.renderTypeList();
            
            if (this.currentType) {
                this.renderExpectedList(this.currentType);
            }
            
            if (this.currentExpected) {
                this.applyFilters();
            }
        });
        
        // Export button
        document.getElementById('exportBtn').addEventListener('click', () => {
            this.exportCases();
        });
        
        // Select-all checkbox
        document.getElementById('selectAllExpected').addEventListener('change', (e) => {
            this.toggleSelectAll(e.target.checked);
        });
        
        // Generate reverse cases button
        document.getElementById('generateReverseCases').addEventListener('click', () => {
            this.generateReverseCases();
        });
        
        // Clear-all checkbox button
        document.getElementById('clearAllExpected').addEventListener('click', () => {
            this.clearAllSelections();
        });
    }
    
    // Toggle expected behavior selection
    toggleExpectedSelection(expected, isChecked) {
        if (isChecked) {
            this.selectedExpectedBehaviors.add(expected);
        } else {
            this.selectedExpectedBehaviors.delete(expected);
        }
        this.updateSelectionUI();
    }
    
    // Select all / deselect all
    toggleSelectAll(isChecked) {
        if (!this.currentType) return;
        
        const typeData = this.typeExpectedGroups[this.currentType];
        if (!typeData) return;
        
        const expectedBehaviors = Object.keys(typeData.expected_behaviors);
        
        if (isChecked) {
            expectedBehaviors.forEach(expected => {
                this.selectedExpectedBehaviors.add(expected);
            });
        } else {
            expectedBehaviors.forEach(expected => {
                this.selectedExpectedBehaviors.delete(expected);
            });
        }
        
        // Re-render list to update checkbox state
        this.renderExpectedList(this.currentType);
        this.updateSelectionUI();
    }
    
    // Clear all selections
    clearAllSelections() {
        // Clear all selected items
        this.selectedExpectedBehaviors.clear();
        
        // Uncheck select-all checkbox
        const selectAllCheckbox = document.getElementById('selectAllExpected');
        if (selectAllCheckbox) {
            selectAllCheckbox.checked = false;
        }
        
        // Re-render list to update checkbox state
        if (this.currentType) {
            this.renderExpectedList(this.currentType);
        }
        
        // Update UI
        this.updateSelectionUI();
        
        console.log('Cleared all selections');
    }
    
    // Update selection UI
    updateSelectionUI() {
        const count = this.selectedExpectedBehaviors.size;
        document.getElementById('selectedExpectedCount').textContent = `Selected: ${count}`;
        
        // Enable/disable generate button
        const generateBtn = document.getElementById('generateReverseCases');
        generateBtn.disabled = count === 0;
    }
    
    // Generate reverse cases
    async generateReverseCases() {
        if (this.selectedExpectedBehaviors.size === 0) {
            alert('Please select expected behaviors first');
            return;
        }
        
        console.log('Starting reverse case generation...');
        console.log('Selected expected behaviors:', Array.from(this.selectedExpectedBehaviors));
        
        // Collect cases for selected expected behaviors
        const selectedCases = [];
        this.selectedExpectedBehaviors.forEach(expected => {
            const typeData = this.typeExpectedGroups[this.currentType];
            if (typeData && typeData.expected_behaviors[expected]) {
                const cases = typeData.expected_behaviors[expected];
                selectedCases.push(...cases);
            }
        });
        
        console.log(`Collected ${selectedCases.length} cases`);
        
        // Call backend API to generate reverse cases
        try {
            const generateBtn = document.getElementById('generateReverseCases');
            generateBtn.disabled = true;
            generateBtn.textContent = 'Generating...';
            
            const response = await fetch('/api/generate-reverse-from-expected', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    cases: selectedCases
                })
            });
            
            const result = await response.json();
            
            if (result.success) {
                console.log('Generation result:', result);
                // Show results modal
                this.showResultModal(result);
            } else {
                alert(`Generation failed: ${result.error}`);
            }
        } catch (error) {
            console.error('Generation failed:', error);
            alert(`Generation failed: ${error.message}`);
        } finally {
            const generateBtn = document.getElementById('generateReverseCases');
            generateBtn.disabled = false;
            generateBtn.textContent = 'Generate reverse cases';
        }
    }
    
    // Show results modal
    showResultModal(result) {
        this.generatedCases = result.generated_cases || [];
        
        // Update statistics
        document.getElementById('generatedCount').textContent = result.generated_count;
        document.getElementById('generatedTime').textContent = new Date().toLocaleString('zh-CN');
        
        // Render generated cases
        this.renderGeneratedCases();
        
        // Show modal
        document.getElementById('resultModal').style.display = 'flex';
        
        // Bind download buttons
        document.getElementById('downloadExcelBtn').onclick = () => this.downloadExcel();
        document.getElementById('downloadJsonBtn').onclick = () => this.downloadJson();
    }
    
    // Render generated cases
    renderGeneratedCases() {
        const container = document.getElementById('generatedCasesList');
        container.innerHTML = '';
        
        if (this.generatedCases.length === 0) {
            container.innerHTML = '<div class="empty-state"><p>No generated cases</p></div>';
            return;
        }
        
        this.generatedCases.forEach((testCase, index) => {
            const card = document.createElement('div');
            card.className = 'generated-case-card';
            
            const preconditions = Array.isArray(testCase.前提条件) ? testCase.前提条件 : [];
            
            card.innerHTML = `
                <div class="generated-case-header">
                    <span class="generated-badge badge-new">NEW</span>
                    <span class="generated-badge badge-type">${this.escapeHtml(testCase.测试用例类型 || '')}</span>
                </div>
                <div class="generated-case-body">
                    <h4>${this.escapeHtml(testCase.测试用例名称 || `Reverse case ${index + 1}`)}</h4>
                    <div>
                        <strong>Preconditions:</strong>
                        <ul>
                            ${preconditions.map(c => `<li>${this.escapeHtml(c)}</li>`).join('')}
                        </ul>
                    </div>
                    <div>
                        <strong>Actions:</strong>
                        <span>${this.escapeHtml(testCase.执行动作 || '')}</span>
                    </div>
                    <div>
                        <strong>Expected Behavior:</strong>
                        <span>${this.escapeHtml(testCase.预期行为 || '')}</span>
                    </div>
                    ${testCase.原始前提条件 ? `
                    <div style="margin-top: 15px; padding: 10px; background: #f0f4ff; border-radius: 6px;">
                        <strong>Negation details:</strong>
                        <div style="margin-top: 5px;">
                            <span style="color: #909399;">Original:</span>
                            <span>${this.escapeHtml(testCase.原始前提条件)}</span>
                        </div>
                        <div style="margin-top: 3px;">
                            <span style="color: #909399;">Negated:</span>
                            <span class="reverse-highlight">${this.escapeHtml(testCase.反向前提条件)}</span>
                        </div>
                    </div>
                    ` : ''}
                </div>
            `;
            
            container.appendChild(card);
        });
    }
    
    // Download Excel
    async downloadExcel() {
        try {
            const response = await fetch('/api/export-generated-cases-excel', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    cases: this.generatedCases
                })
            });
            
            if (response.ok) {
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `reverse_test_cases_${new Date().getTime()}.xlsx`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                window.URL.revokeObjectURL(url);
                
                console.log('Excel download succeeded');
            } else {
                alert('Download failed');
            }
        } catch (error) {
            console.error('Download failed:', error);
            alert(`Download failed: ${error.message}`);
        }
    }
    
    // Download JSON
    downloadJson() {
        const jsonStr = JSON.stringify(this.generatedCases, null, 2);
        const blob = new Blob([jsonStr], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `reverse_test_cases_${new Date().getTime()}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        
        console.log('JSON download succeeded');
    }
}

// Close results modal
function closeResultModal() {
    document.getElementById('resultModal').style.display = 'none';
}

// Initialize app
document.addEventListener('DOMContentLoaded', () => {
    console.log('Type–expected classification tool loaded');
    new TypeExpectedClassificationApp();
});
