/**
 * Variables Module - Управление переменными
 */

export default class VariablesModule {
    constructor(app) {
        this.app = app;
        this.name = 'variables';
        this.version = '1.0.0';
        
        this.editingKey = null;
        this.currentGroups = [];
    }
    
    async init() {
        console.log('🔑 Инициализация Variables модуля');
        
        this.setupGlobalFunctions();
        this.setupEventListeners();
        
        return this;
    }
    
    setupGlobalFunctions() {
        window.toggleGrouping = () => this.toggleGrouping();
        window.openAddVariableModal = () => this.openAddModal();
        window.editVariable = (key, value, isSecret) => this.edit(key, value, isSecret);
        window.closeVariableModal = () => this.closeModal();
        window.saveVariable = () => this.save();
        window.deleteVariable = (key) => this.delete(key);
        window.addGroup = () => this.addGroup();
        window.removeGroup = (group) => this.removeGroup(group);
        window.toggleSecret = (key, btnElement) => this.toggleSecret(key, btnElement);
    }
    
    setupEventListeners() {
        document.addEventListener('click', (e) => {
            if (e.target.id === 'variable-modal') {
                this.closeModal();
            }
        });

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && document.getElementById('variable-modal')?.style.display === 'flex') {
                this.closeModal();
            }
        });
    }
    
    toggleGrouping() {
        const btn = document.getElementById('group-by-tags-btn');
        const contentDiv = document.getElementById('variables-content');
        const variablesDataElement = document.getElementById('variables-data');
        
        if (!variablesDataElement) return;
        
        const variables = JSON.parse(variablesDataElement.textContent);
        const isGrouped = btn.classList.contains('active');
        
        if (!isGrouped) {
            btn.classList.add('active', 'btn-primary');
            btn.classList.remove('btn-outline-secondary');
            btn.innerHTML = '<i class="bi bi-grid-fill"></i> Группировано';
            this.renderGroupedView(variables, contentDiv);
        } else {
            btn.classList.remove('active', 'btn-primary');
            btn.classList.add('btn-outline-secondary');
            btn.innerHTML = '<i class="bi bi-grid"></i> Группировать по тегам';
            this.renderGridView(variables, contentDiv);
        }
    }
    
    renderGridView(variables, container) {
        htmx.ajax('GET', '/frontend/variables/list', {
            target: '#variables-container',
            swap: 'outerHTML'
        });
    }
    
    renderGroupedView(variables, container) {
        const allGroups = new Set();
        const ungrouped = [];
        
        Object.entries(variables).forEach(([key, data]) => {
            if (data.groups && data.groups.length > 0) {
                data.groups.forEach(g => allGroups.add(g));
            } else {
                ungrouped.push([key, data]);
            }
        });
        
        let html = ``;
        
        allGroups.forEach(group => {
            const groupVars = Object.entries(variables).filter(([key, data]) => 
                data.groups && data.groups.includes(group)
            );
            
            if (groupVars.length > 0) {
                html += `
                    <div class="variable-group-header">
                        <h5 class="variable-group-title">
                            <span class="variable-group-badge">${group}</span>
                            <span class="variable-group-count">(${groupVars.length})</span>
                        </h5>
                        <div class="variables-grid">
                `;
                
                groupVars.forEach(([key, data]) => {
                    html += this.renderVariableCard(key, data);
                });
                
                html += `
                        </div>
                    </div>
                `;
            }
        });
        
        if (ungrouped.length > 0) {
            html += `
                <div class="empty-group-header">
                    <h5 class="empty-group-title">
                        <span>Без группы</span>
                        <span class="variable-group-count">(${ungrouped.length})</span>
                    </h5>
                    <div class="variables-grid">
            `;
            
            ungrouped.forEach(([key, data]) => {
                html += this.renderVariableCard(key, data);
            });
            
            html += `
                    </div>
                </div>
            `;
        }
        
        container.innerHTML = html;
    }
    
    renderVariableCard(key, data) {
        const isSecret = data.secret;
        const icon = isSecret ? 
            '<i class="bi bi-shield-lock"></i>' :
            '<i class="bi bi-tag"></i>';
        
        const groups = data.groups && data.groups.length > 0 ? 
            data.groups.map(g => `<span class="variable-group-badge">${g}</span>`).join('') :
            '';
        
        const valueDisplay = isSecret ?
            `<div class="variable-secret-group">
                <input type="password" readonly value="••••••••••••" class="form-control form-control-sm" id="var-${key}" data-secret-key="${key}">
                <button class="btn-icon" type="button" onclick="toggleSecret('${key}', this)" title="Показать/скрыть">
                    <i class="bi bi-eye"></i>
                </button>
            </div>` :
            `<div class="variable-value-display">
                <code title="${data.value}">${data.value}</code>
            </div>`;
        
        return `
            <div class="variable-grid-item">
                <div class="card variable-card">
                    <div class="variable-card-header">
                        <div class="card-icon">
                            ${icon}
                        </div>
                        <div class="variable-card-info">
                            ${groups ? `<div class="variable-groups">${groups}</div>` : ''}
                        </div>
                        <div class="variable-card-actions">
                            <button class="btn-icon" onclick="event.stopPropagation();editVariable('${key}', '${data.value}', ${isSecret})" title="Изменить">
                                <i class="bi bi-pencil"></i>
                            </button>
                            <button class="btn-icon btn-icon-danger" onclick="event.stopPropagation();deleteVariable('${key}')" title="Удалить">
                                <i class="bi bi-trash"></i>
                            </button>
                        </div>
                    </div>
                    <div class="variable-card-body">
                        <div class="variable-key">
                            <code title="${key}">${key}</code>
                        </div>
                        <div class="variable-value">
                            ${valueDisplay}
                        </div>
                    </div>
                </div>
            </div>
        `;
    }
    
    openAddModal() {
        this.editingKey = null;
        this.currentGroups = [];
        document.getElementById('variable-modal-title').textContent = 'Добавить переменную';
        document.getElementById('variable-key').value = '';
        document.getElementById('variable-key').disabled = false;
        document.getElementById('variable-description').value = '';
        document.getElementById('variable-value').value = '';
        document.getElementById('variable-secret').checked = false;
        this.renderGroups();
        
        const modal = document.getElementById('variable-modal');
        if (modal.parentElement !== document.body) {
            document.body.appendChild(modal);
        }
        modal.style.display = 'flex';
    }
    
    async edit(key, value, isSecret) {
        this.editingKey = key;
        
        try {
            const response = await fetch(`/api/v1/admin/variables/${key}`, {
                headers: {'Authorization': `Bearer ${this.app.authToken}`}
            });
            if (response.ok) {
                const data = await response.json();
                this.currentGroups = data.groups || [];
                value = data.value;
                document.getElementById('variable-description').value = data.description || '';
            } else {
                this.currentGroups = [];
                document.getElementById('variable-description').value = '';
            }
        } catch {
            this.currentGroups = [];
            document.getElementById('variable-description').value = '';
        }
        
        document.getElementById('variable-modal-title').textContent = 'Изменить переменную';
        document.getElementById('variable-key').value = key;
        document.getElementById('variable-key').disabled = true;
        document.getElementById('variable-value').value = value === '***' ? '' : value;
        document.getElementById('variable-secret').checked = isSecret;
        this.renderGroups();
        
        const modal = document.getElementById('variable-modal');
        if (modal.parentElement !== document.body) {
            document.body.appendChild(modal);
        }
        modal.style.display = 'flex';
    }
    
    closeModal() {
        const modal = document.getElementById('variable-modal');
        if (modal) {
            modal.style.display = 'none';
        }
        this.editingKey = null;
    }
    
    async save() {
        const editingKey = this.editingKey;
        const key = document.getElementById('variable-key').value.trim();
        const description = document.getElementById('variable-description').value.trim();
        const value = document.getElementById('variable-value').value;
        const secret = document.getElementById('variable-secret').checked;
        const groups = this.currentGroups || [];
        
        if (!key) {
            this.app.showNotification('Введите ключ переменной', 'warning');
            return;
        }
        
        if (!value && !editingKey) {
            this.app.showNotification('Введите значение', 'warning');
            return;
        }
        
        try {
            const response = await fetch('/api/v1/admin/variables', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.app.authToken}`
                },
                body: JSON.stringify({ key, value, secret, groups, description })
            });
            
            if (response.ok) {
                this.closeModal();
                this.app.showNotification('Переменная сохранена', 'success');
                htmx.ajax('GET', '/frontend/variables/list', {
                    target: '#variables-container',
                    swap: 'outerHTML'
                });
            } else {
                const error = await response.json();
                this.app.showNotification('Ошибка: ' + (error.detail || 'Не удалось сохранить'), 'danger');
            }
        } catch (err) {
            console.error('Ошибка сохранения:', err);
            this.app.showNotification('Ошибка сохранения', 'danger');
        }
    }
    
    async delete(key) {
        if (!confirm(`Удалить переменную "${key}"?`)) {
            return;
        }
        
        try {
            const response = await fetch(`/api/v1/admin/variables/${key}`, {
                method: 'DELETE',
                headers: {
                    'Authorization': `Bearer ${this.app.authToken}`
                }
            });
            
            if (response.ok) {
                this.app.showNotification('Переменная удалена', 'success');
                htmx.ajax('GET', '/frontend/variables/list', {
                    target: '#variables-container',
                    swap: 'outerHTML'
                });
            } else {
                this.app.showNotification('Ошибка удаления', 'danger');
            }
        } catch (err) {
            console.error('Ошибка удаления:', err);
        }
    }
    
    addGroup() {
        const input = document.getElementById('variable-group-input');
        const group = input.value.trim().toLowerCase();
        
        if (!group) return;
        
        if (!/^[a-z_][a-z0-9_]*$/.test(group)) {
            this.app.showNotification('Группа должна быть snake_case', 'warning');
            return;
        }
        
        if (!this.currentGroups.includes(group)) {
            this.currentGroups.push(group);
            this.renderGroups();
        }
        
        input.value = '';
    }
    
    removeGroup(group) {
        this.currentGroups = this.currentGroups.filter(g => g !== group);
        this.renderGroups();
    }
    
    renderGroups() {
        const container = document.getElementById('variable-groups-container');
        if (!container) return;
        
        if (this.currentGroups.length === 0) {
            container.innerHTML = '<small class="text-muted">Нет групп</small>';
            return;
        }
        
        container.innerHTML = this.currentGroups.map(group => `
            <span class="badge bg-primary me-1 mb-1 variable-badge-group">
                ${group}
                <i class="bi bi-x variable-badge-remove" onclick="removeGroup('${group}')"></i>
            </span>
        `).join('');
    }
    
    async toggleSecret(key, btnElement) {
        const input = document.getElementById(`var-${key}`);
        const icon = btnElement.querySelector('i');
        
        if (input.type === 'password') {
            try {
                const response = await fetch(`/api/v1/admin/variables/${key}`, {
                    headers: {
                        'Authorization': `Bearer ${this.app.authToken}`
                    }
                });
                
                if (response.ok) {
                    const data = await response.json();
                    input.value = data.value;
                    input.type = 'text';
                    icon.className = 'bi bi-eye-slash';
                }
            } catch (err) {
                console.error('Ошибка загрузки значения:', err);
            }
        } else {
            input.value = '••••••••••••';
            input.type = 'password';
            icon.className = 'bi bi-eye';
        }
    }
    
    destroy() {
        console.log('🧹 Variables модуль выгружен');
    }
}

