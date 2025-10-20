/**
 * MCP Module - MCP servers management
 */

export default class MCPModule {
    constructor(app) {
        this.app = app;
        this.name = 'mcp';
        this.version = '1.0.0';
        
        this.editingServerId = null;
    }
    
    async init() {
        console.log('🔌 MCP модуль инициализирован');
        
        this.setupGlobalFunctions();
        this.setupEventListeners();
        
        return this;
    }
    
    setupGlobalFunctions() {
        window.openAddServerModal = () => this.openAddModal();
        window.editServer = (serverId) => this.edit(serverId);
        window.closeServerModal = () => this.closeModal();
        window.saveServer = () => this.save();
        window.deleteServer = (serverId) => this.delete(serverId);
        window.syncServer = (serverId) => this.sync(serverId);
        window.testServer = (serverId) => this.test(serverId);
        window.toggleServerDetails = (serverId) => this.toggleDetails(serverId);
        window.insertSampleHeaders = () => this.insertSampleHeaders();
    }
    
    setupEventListeners() {
        document.addEventListener('click', (e) => {
            if (e.target.id === 'mcp-server-modal') {
                this.closeModal();
            }
        });

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && document.getElementById('mcp-server-modal')?.style.display === 'flex') {
                this.closeModal();
            }
        });
    }
    
    openAddModal() {
        this.editingServerId = null;
        document.getElementById('mcp-server-modal-title').textContent = 'Добавить MCP сервер';
        document.getElementById('server-id').value = '';
        document.getElementById('server-id').disabled = false;
        document.getElementById('server-name').value = '';
        document.getElementById('server-description').value = '';
        document.getElementById('server-url').value = '';
        document.getElementById('server-transport-type').value = 'http';
        document.getElementById('server-timeout').value = '30';
        document.getElementById('server-headers').value = '{}';
        document.getElementById('server-use-proxy').checked = true;
        document.getElementById('server-is-active').checked = true;
        document.getElementById('server-auto-sync').checked = true;
        
        const modal = document.getElementById('mcp-server-modal');
        if (modal.parentElement !== document.body) {
            document.body.appendChild(modal);
        }
        modal.style.display = 'flex';
    }
    
    async edit(serverId) {
        this.editingServerId = serverId;
        
        try {
            const response = await fetch(`/api/v1/mcp/servers/${serverId}`, {
                headers: {'Authorization': `Bearer ${this.app.authToken}`}
            });
            
            if (!response.ok) {
                this.app.showNotification('Не удалось загрузить данные сервера', 'danger');
                return;
            }
            
            const server = await response.json();
            
            document.getElementById('mcp-server-modal-title').textContent = 'Редактировать MCP сервер';
            document.getElementById('server-id').value = server.server_id;
            document.getElementById('server-id').disabled = true;
            document.getElementById('server-name').value = server.name;
            document.getElementById('server-description').value = server.description || '';
            document.getElementById('server-url').value = server.url;
            document.getElementById('server-transport-type').value = server.transport_type;
            document.getElementById('server-timeout').value = server.timeout;
            document.getElementById('server-headers').value = JSON.stringify(server.headers || {}, null, 2);
            document.getElementById('server-use-proxy').checked = server.use_proxy !== false;
            document.getElementById('server-is-active').checked = server.is_active;
            document.getElementById('server-auto-sync').checked = server.auto_sync_tools;
            
            const modal = document.getElementById('mcp-server-modal');
            if (modal.parentElement !== document.body) {
                document.body.appendChild(modal);
            }
            modal.style.display = 'flex';
        } catch (err) {
            console.error('Ошибка загрузки сервера:', err);
            this.app.showNotification('Ошибка загрузки данных', 'danger');
        }
    }
    
    closeModal() {
        const modal = document.getElementById('mcp-server-modal');
        if (modal) {
            modal.style.display = 'none';
        }
        this.editingServerId = null;
    }
    
    async save() {
        const serverId = document.getElementById('server-id').value.trim();
        const name = document.getElementById('server-name').value.trim();
        const description = document.getElementById('server-description').value.trim();
        const url = document.getElementById('server-url').value.trim();
        const transportType = document.getElementById('server-transport-type').value;
        const timeout = parseInt(document.getElementById('server-timeout').value);
        const headersText = document.getElementById('server-headers').value.trim();
        const useProxy = document.getElementById('server-use-proxy').checked;
        const isActive = document.getElementById('server-is-active').checked;
        const autoSync = document.getElementById('server-auto-sync').checked;
        
        if (!serverId) {
            this.app.showNotification('Укажите ID сервера', 'warning');
            return;
        }
        
        if (!name) {
            this.app.showNotification('Укажите название сервера', 'warning');
            return;
        }
        
        if (!url) {
            this.app.showNotification('Укажите URL сервера', 'warning');
            return;
        }
        
        let headers = {};
        if (headersText) {
            try {
                headers = JSON.parse(headersText);
            } catch (e) {
                this.app.showNotification('Некорректный JSON в заголовках', 'danger');
                return;
            }
        }
        
        const serverData = {
            server_id: serverId,
            name: name,
            description: description || null,
            url: url,
            transport_type: transportType,
            timeout: timeout,
            headers: headers,
            use_proxy: useProxy,
            is_active: isActive,
            auto_sync_tools: autoSync
        };
        
        try {
            const isEdit = this.editingServerId !== null;
            const method = isEdit ? 'PUT' : 'POST';
            const endpoint = isEdit ? `/api/v1/mcp/servers/${serverId}` : '/api/v1/mcp/servers';
            
            const response = await fetch(endpoint, {
                method: method,
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.app.authToken}`
                },
                body: JSON.stringify(serverData)
            });
            
            if (response.ok) {
                this.closeModal();
                this.app.showNotification(isEdit ? 'MCP сервер обновлен' : 'MCP сервер создан', 'success');
                
                htmx.ajax('GET', '/frontend/mcp/list', {
                    target: '#mcp-servers-container',
                    swap: 'outerHTML'
                });
            } else {
                const error = await response.json();
                this.app.showNotification('Ошибка сохранения: ' + (error.detail || 'Неизвестная ошибка'), 'danger');
            }
        } catch (err) {
            console.error('Ошибка сохранения сервера:', err);
            this.app.showNotification('Ошибка сохранения', 'danger');
        }
    }
    
    async delete(serverId) {
        if (!confirm(`Удалить MCP сервер "${serverId}"? Все его тулы также будут удалены.`)) {
            return;
        }
        
        try {
            const response = await fetch(`/api/v1/mcp/servers/${serverId}`, {
                method: 'DELETE',
                headers: {
                    'Authorization': `Bearer ${this.app.authToken}`
                }
            });
            
            if (response.ok) {
                this.app.showNotification('MCP сервер удален', 'success');
                
                htmx.ajax('GET', '/frontend/mcp/list', {
                    target: '#mcp-servers-container',
                    swap: 'outerHTML'
                });
            } else {
                this.app.showNotification('Не удалось удалить сервер', 'danger');
            }
        } catch (err) {
            console.error('Ошибка удаления сервера:', err);
            this.app.showNotification('Ошибка удаления', 'danger');
        }
    }
    
    async sync(serverId) {
        const btn = document.getElementById(`sync-btn-${serverId}`);
        const icon = btn.querySelector('i');
        
        icon.classList.add('spinning');
        btn.disabled = true;
        
        try {
            this.app.showNotification('Синхронизация тулов...', 'info');
            
            const response = await fetch(`/api/v1/mcp/servers/${serverId}/sync`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${this.app.authToken}`
                }
            });
            
            if (response.ok) {
                const result = await response.json();
                this.app.showNotification(
                    `Синхронизировано ${result.tools_count} инструментов`, 
                    'success'
                );
                
                htmx.ajax('GET', '/frontend/mcp/list', {
                    target: '#mcp-servers-container',
                    swap: 'outerHTML'
                });
            } else {
                const error = await response.json();
                this.app.showNotification('Ошибка синхронизации: ' + (error.detail || 'Неизвестная ошибка'), 'danger');
            }
        } catch (err) {
            console.error('Ошибка синхронизации:', err);
            this.app.showNotification('Ошибка синхронизации', 'danger');
        } finally {
            icon.classList.remove('spinning');
            btn.disabled = false;
        }
    }
    
    async test(serverId) {
        try {
            this.app.showNotification('Тестирование подключения...', 'info');
            
            const response = await fetch(`/api/v1/mcp/servers/${serverId}/test`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${this.app.authToken}`
                }
            });
            
            const result = await response.json();
            
            if (result.success) {
                this.app.showNotification(
                    `✅ Подключение успешно! Найдено ${result.tools_count} инструментов`, 
                    'success'
                );
            } else {
                this.app.showNotification(
                    `❌ Ошибка подключения: ${result.message}`, 
                    'danger'
                );
            }
        } catch (err) {
            console.error('Ошибка тестирования:', err);
            this.app.showNotification('Ошибка тестирования подключения', 'danger');
        }
    }
    
    toggleDetails(serverId) {
        const detailsDiv = document.getElementById(`details-${serverId}`);
        if (detailsDiv) {
            if (detailsDiv.style.display === 'none') {
                detailsDiv.style.display = 'block';
            } else {
                detailsDiv.style.display = 'none';
            }
        }
    }
    
    insertSampleHeaders() {
        const sampleHeaders = {
            "Authorization": "@var:mcp_api_key"
        };
        document.getElementById('server-headers').value = JSON.stringify(sampleHeaders, null, 2);
    }
    
    destroy() {
        console.log('🧹 MCP модуль выгружен');
    }
}

