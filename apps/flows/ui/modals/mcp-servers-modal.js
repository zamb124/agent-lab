/**
 * MCPServersModal - модалка управления MCP серверами
 * CRUD операции с MCP серверами и синхронизация tools
 */
import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import '@platform/lib/components/platform-icon.js';

export class MCPServersModal extends PlatformModal {
    static styles = [
        PlatformModal.styles,
        css`
            .modal-container {
                width: 900px;
                max-width: 95vw;
            }
            
            .servers-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                max-height: 450px;
                overflow-y: auto;
                padding: var(--space-2);
            }
            
            .server-card {
                background: var(--glass-solid-subtle);
                border-radius: var(--radius-lg);
                padding: var(--space-4);
                border: 1px solid var(--border-subtle);
            }
            
            .server-header {
                display: flex;
                justify-content: space-between;
                align-items: flex-start;
                margin-bottom: var(--space-3);
            }
            
            .server-name {
                font-size: var(--text-base);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }
            
            .server-id {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                font-family: var(--font-mono);
            }
            
            .server-url {
                font-size: var(--text-sm);
                color: var(--text-secondary);
                word-break: break-all;
                margin-bottom: var(--space-2);
            }
            
            .server-description {
                font-size: var(--text-sm);
                color: var(--text-tertiary);
                margin-bottom: var(--space-2);
                font-style: italic;
            }
            
            .server-meta {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-3);
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
            
            .transport-badge {
                display: inline-flex;
                padding: var(--space-1) var(--space-2);
                background: var(--accent-bg);
                color: var(--accent);
                border-radius: var(--radius-sm);
                font-size: var(--text-xs);
                text-transform: uppercase;
            }
            
            .tools-count {
                color: var(--text-secondary);
            }
            
            .server-actions {
                display: flex;
                gap: var(--space-2);
            }
            
            .action-btn {
                display: flex;
                align-items: center;
                justify-content: center;
                width: 32px;
                height: 32px;
                border-radius: var(--radius-md);
                border: none;
                background: var(--glass-solid-subtle);
                color: var(--text-secondary);
                cursor: pointer;
                transition: all var(--duration-fast);
            }
            
            .action-btn:hover {
                background: var(--glass-solid-medium);
                color: var(--text-primary);
            }
            
            .action-btn.sync:hover { color: var(--accent); }
            .action-btn.edit:hover { color: var(--info); }
            .action-btn.test:hover { color: var(--warning); }
            .action-btn.delete:hover { color: var(--danger); }
            
            .action-btn.syncing {
                animation: spin 1s linear infinite;
            }
            
            @keyframes spin {
                from { transform: rotate(0deg); }
                to { transform: rotate(360deg); }
            }
            
            .empty-state {
                text-align: center;
                padding: var(--space-8);
                color: var(--text-tertiary);
            }
            
            .empty-state platform-icon {
                margin-bottom: var(--space-3);
                opacity: 0.5;
            }
            
            .add-btn {
                display: flex;
                align-items: center;
                justify-content: center;
                width: 32px;
                height: 32px;
                border-radius: var(--radius-full);
                border: 1px dashed var(--border-medium);
                background: transparent;
                color: var(--text-tertiary);
                cursor: pointer;
                transition: all var(--duration-fast);
                margin-bottom: var(--space-4);
            }
            
            .add-btn:hover {
                border-color: var(--accent);
                color: var(--accent);
                background: var(--accent-bg);
            }
            
            .add-form {
                background: var(--glass-solid-subtle);
                border-radius: var(--radius-lg);
                padding: var(--space-4);
                margin-bottom: var(--space-4);
                border: 1px solid var(--border-subtle);
            }
            
            .form-title {
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-secondary);
                margin-bottom: var(--space-3);
            }
            
            .form-row {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: var(--space-3);
                margin-bottom: var(--space-3);
            }
            
            .form-row.full {
                grid-template-columns: 1fr;
            }
            
            .form-row.triple {
                grid-template-columns: 1fr 1fr 1fr;
            }
            
            .form-label {
                font-size: var(--text-sm);
                color: var(--text-secondary);
                margin-bottom: var(--space-1);
                display: block;
            }
            
            .form-input, .form-select {
                width: 100%;
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-md);
                border: 1px solid var(--border-subtle);
                background: var(--glass-tint-subtle);
                color: var(--text-primary);
                font-size: var(--text-sm);
                box-sizing: border-box;
            }
            
            .form-input:focus, .form-select:focus {
                outline: none;
                border-color: var(--accent);
            }
            
            .form-hint {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-top: var(--space-1);
            }
            
            .form-actions {
                display: flex;
                justify-content: space-between;
                gap: var(--space-2);
                margin-top: var(--space-4);
            }
            
            .form-actions-left {
                display: flex;
                gap: var(--space-2);
            }
            
            .form-actions-right {
                display: flex;
                gap: var(--space-2);
            }
            
            .btn {
                padding: var(--space-2) var(--space-4);
                border-radius: var(--radius-md);
                border: none;
                font-size: var(--text-sm);
                cursor: pointer;
                transition: all var(--duration-fast);
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
            }
            
            .btn-primary {
                background: var(--accent);
                color: white;
            }
            
            .btn-primary:hover {
                background: var(--accent-hover);
            }
            
            .btn-secondary {
                background: var(--glass-solid-subtle);
                color: var(--text-secondary);
            }
            
            .btn-secondary:hover {
                background: var(--glass-solid-medium);
            }
            
            .btn-warning {
                background: var(--warning-bg);
                color: var(--warning);
            }
            
            .btn-warning:hover {
                background: var(--warning);
                color: white;
            }
            
            .btn:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }
            
            .headers-editor {
                font-family: var(--font-mono);
                font-size: var(--text-xs);
                min-height: 80px;
                resize: vertical;
            }
            
            .auth-presets {
                display: flex;
                gap: var(--space-2);
                margin-bottom: var(--space-2);
            }
            
            .auth-preset {
                padding: var(--space-1) var(--space-2);
                border-radius: var(--radius-sm);
                border: 1px solid var(--border-subtle);
                background: var(--glass-tint-subtle);
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                cursor: pointer;
                transition: all var(--duration-fast);
            }
            
            .auth-preset:hover {
                background: var(--accent-bg);
                color: var(--accent);
                border-color: var(--accent);
            }
            
            .test-result {
                margin-top: var(--space-2);
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-md);
                font-size: var(--text-sm);
            }
            
            .test-result.success {
                background: var(--success-bg);
                color: var(--success);
            }
            
            .test-result.error {
                background: var(--danger-bg);
                color: var(--danger);
            }
            
            .server-headers {
                margin-top: var(--space-2);
                padding: var(--space-2);
                background: var(--glass-tint-subtle);
                border-radius: var(--radius-sm);
                font-family: var(--font-mono);
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
        `
    ];

    static properties = {
        ...PlatformModal.properties,
        servers: { type: Array },
        loading: { type: Boolean },
        showAddForm: { type: Boolean },
        editingServer: { type: Object },
        syncingId: { type: String },
        testingForm: { type: Boolean },
        testResult: { type: Object },
    };

    constructor() {
        super();
        this.title = '';
        this.servers = [];
        this.loading = true;
        this.showAddForm = false;
        this.editingServer = null;
        this.syncingId = null;
        this.testingForm = false;
        this.testResult = null;
    }

    async showModal() {
        this.title = this.i18n.t('mcp_servers.modal_title');
        super.showModal();
        await this._loadServers();
    }

    async _loadServers() {
        this.loading = true;
        try {
            this.servers = await this.a2a.get('/api/v1/mcp/servers');
        } catch (error) {
            this.error(this.i18n.t('mcp_servers.err_load', { message: error.message }));
            this.servers = [];
        }
        this.loading = false;
    }

    _applyAuthPreset(preset) {
        const textarea = this.shadowRoot.querySelector('textarea[name="headers"]');
        if (!textarea) return;
        
        const presets = {
            bearer: '{\n  "Authorization": "Bearer @var:mcp_token"\n}',
            apikey: '{\n  "X-API-Key": "@var:mcp_api_key"\n}',
            basic: '{\n  "Authorization": "Basic @var:mcp_basic_auth"\n}',
        };
        
        textarea.value = presets[preset] || '{}';
    }

    async _testConnection(e) {
        e.preventDefault();
        const form = this.shadowRoot.querySelector('form');
        const formData = new FormData(form);
        
        const url = formData.get('url').trim();
        const transportType = formData.get('transport_type');
        const headersRaw = formData.get('headers').trim();
        
        if (!url) {
            this.error(this.i18n.t('mcp_servers.err_url_required'));
            return;
        }
        
        let headers = {};
        if (headersRaw) {
            try {
                headers = JSON.parse(headersRaw);
            } catch {
                this.error(this.i18n.t('mcp_servers.err_headers_json'));
                return;
            }
        }
        
        this.testingForm = true;
        this.testResult = null;
        
        try {
            // Создаём временный сервер для теста
            const tempId = `temp-test-${Date.now()}`;
            await this.a2a.post('/api/v1/mcp/servers', {
                server_id: tempId,
                name: 'Test',
                url,
                transport_type: transportType,
                headers,
            });
            
            try {
                const result = await this.a2a.post(`/api/v1/mcp/servers/${tempId}/test`);
                this.testResult = {
                    success: true,
                    message: this.i18n.t('mcp_servers.test_ok_tools', { count: result.tools_count }),
                };
            } catch (testError) {
                this.testResult = {
                    success: false,
                    message: this.i18n.t('mcp_servers.test_fail_connection', { message: testError.message }),
                };
            }
            
            // Удаляем временный сервер
            await this.a2a.delete(`/api/v1/mcp/servers/${tempId}`);
        } catch (error) {
            this.testResult = {
                success: false,
                message: this.i18n.t('mcp_servers.err_with_message', { message: error.message }),
            };
        }
        
        this.testingForm = false;
    }

    async _addServer(e) {
        e.preventDefault();
        const form = e.target;
        const formData = new FormData(form);
        
        // При редактировании берём server_id из editingServer
        const serverId = this.editingServer 
            ? this.editingServer.server_id 
            : formData.get('server_id').trim();
        const name = formData.get('name').trim();
        const url = formData.get('url').trim();
        const transportType = formData.get('transport_type');
        const headersRaw = formData.get('headers').trim();
        const description = formData.get('description')?.trim() || '';
        
        if (!serverId || !name || !url) {
            this.error(this.i18n.t('mcp_servers.err_required_fields'));
            return;
        }
        
        let headers = {};
        if (headersRaw) {
            try {
                headers = JSON.parse(headersRaw);
            } catch {
                this.error(this.i18n.t('mcp_servers.err_headers_json'));
                return;
            }
        }
        
        try {
            if (this.editingServer) {
                await this.a2a.put(`/api/v1/mcp/servers/${serverId}`, {
                    name,
                    url,
                    transport_type: transportType,
                    headers,
                    description,
                });
                this.success(this.i18n.t('mcp_servers.server_updated', { name }));
            } else {
                await this.a2a.post('/api/v1/mcp/servers', {
                    server_id: serverId,
                    name,
                    url,
                    transport_type: transportType,
                    headers,
                    description,
                });
                this.success(this.i18n.t('mcp_servers.server_added', { name }));
            }
            
            this.showAddForm = false;
            this.editingServer = null;
            this.testResult = null;
            form.reset();
            await this._loadServers();
        } catch (error) {
            this.error(this.i18n.t('mcp_servers.err_with_message', { message: error.message }));
        }
    }

    _editServer(server) {
        this.editingServer = server;
        this.showAddForm = true;
        this.testResult = null;
    }

    async _syncServer(serverId) {
        this.syncingId = serverId;
        try {
            const result = await this.a2a.post(`/api/v1/mcp/servers/${serverId}/sync`);
            this.success(this.i18n.t('mcp_servers.synced_tools', { count: result.tools_count }));
            await this._loadServers();
        } catch (error) {
            this.error(this.i18n.t('mcp_servers.err_sync', { message: error.message }));
        }
        this.syncingId = null;
    }

    async _testServer(serverId) {
        try {
            const result = await this.a2a.post(`/api/v1/mcp/servers/${serverId}/test`);
            this.success(this.i18n.t('mcp_servers.test_ok_short', { count: result.tools_count }));
        } catch (error) {
            this.error(this.i18n.t('mcp_servers.err_test_connection', { message: error.message }));
        }
    }

    async _deleteServer(serverId, serverName) {
        const modal = document.createElement('confirm-modal');
        modal.title = this.i18n.t('mcp_servers.delete_confirm_title');
        modal.message = this.i18n.t('mcp_servers.delete_confirm_message', { name: serverName });
        modal.confirmText = this.i18n.t('mcp_servers.delete_confirm_ok');
        modal.confirmVariant = 'danger';
        document.body.appendChild(modal);
        
        const confirmed = await modal.confirm();
        modal.remove();
        
        if (!confirmed) return;
        
        try {
            await this.a2a.delete(`/api/v1/mcp/servers/${serverId}`);
            this.success(this.i18n.t('mcp_servers.server_deleted'));
            await this._loadServers();
        } catch (error) {
            this.error(this.i18n.t('mcp_servers.err_with_message', { message: error.message }));
        }
    }

    _toggleAddForm() {
        this.showAddForm = !this.showAddForm;
        this.editingServer = null;
        this.testResult = null;
    }

    renderBody() {
        if (this.loading) {
            return html`
                <div class="empty-state">
                    <div class="loading-spinner"></div>
                    <div>${this.i18n.t('mcp_servers.loading')}</div>
                </div>
            `;
        }

        return html`
            ${this.showAddForm ? this._renderAddForm() : html`
                <button class="add-btn" @click=${this._toggleAddForm}>
                    <platform-icon name="plus" size="16"></platform-icon>
                </button>
            `}
            
            ${this.servers.length === 0 && !this.showAddForm ? html`
                <div class="empty-state">
                    <platform-icon name="server" size="48"></platform-icon>
                    <div>${this.i18n.t('mcp_servers.empty_title')}</div>
                    <div style="font-size: var(--text-sm); margin-top: var(--space-2);">
                        ${this.i18n.t('mcp_servers.empty_hint')}
                    </div>
                </div>
            ` : !this.showAddForm ? html`
                <div class="servers-list">
                    ${this.servers.map(server => this._renderServerCard(server))}
                </div>
            ` : ''}
        `;
    }

    _renderAddForm() {
        const server = this.editingServer;
        const isEdit = !!server;
        
        return html`
            <form class="add-form" @submit=${this._addServer}>
                <div class="form-title">${isEdit ? this.i18n.t('mcp_servers.form_title_edit') : this.i18n.t('mcp_servers.form_title_new')}</div>
                
                <div class="form-row">
                    <div>
                        <label class="form-label">${this.i18n.t('mcp_servers.field_server_id')}</label>
                        <input 
                            type="text" 
                            name="server_id" 
                            class="form-input" 
                            placeholder="context7" 
                            pattern="^[a-zA-Z][a-zA-Z0-9_-]*$"
                            .value=${server?.server_id || ''}
                            ?readonly=${isEdit}
                            required 
                        />
                        <div class="form-hint">${this.i18n.t('mcp_servers.hint_server_id')}</div>
                    </div>
                    <div>
                        <label class="form-label">${this.i18n.t('mcp_servers.field_name')}</label>
                        <input 
                            type="text" 
                            name="name" 
                            class="form-input" 
                            placeholder="My MCP Server" 
                            .value=${server?.name || ''}
                            required 
                        />
                    </div>
                </div>
                
                <div class="form-row full">
                    <div>
                        <label class="form-label">${this.i18n.t('mcp_servers.field_url')}</label>
                        <input 
                            type="url" 
                            name="url" 
                            class="form-input" 
                            placeholder="https://example.com/mcp" 
                            .value=${server?.url || ''}
                            required 
                        />
                        <div class="form-hint">${this.i18n.t('mcp_servers.hint_mcp_endpoint')}</div>
                    </div>
                </div>
                
                <div class="form-row">
                    <div>
                        <label class="form-label">${this.i18n.t('mcp_servers.field_transport')}</label>
                        <select name="transport_type" class="form-select">
                            <option value="http" ?selected=${server?.transport_type === 'http'}>HTTP (POST)</option>
                            <option value="sse" ?selected=${server?.transport_type === 'sse'}>SSE (Server-Sent Events)</option>
                        </select>
                        <div class="form-hint">${this.i18n.t('mcp_servers.hint_transport')}</div>
                    </div>
                    <div>
                        <label class="form-label">${this.i18n.t('mcp_servers.field_description')}</label>
                        <input 
                            type="text" 
                            name="description" 
                            class="form-input" 
                            placeholder=${this.i18n.t('mcp_servers.placeholder_server_description')}
                            .value=${server?.description || ''}
                        />
                    </div>
                </div>
                
                <div class="form-row full">
                    <div>
                        <label class="form-label">${this.i18n.t('mcp_servers.field_headers_json')}</label>
                        <div class="auth-presets">
                            <span style="font-size: var(--text-xs); color: var(--text-tertiary);">${this.i18n.t('mcp_servers.presets_label')}</span>
                            <button type="button" class="auth-preset" @click=${() => this._applyAuthPreset('bearer')}>Bearer Token</button>
                            <button type="button" class="auth-preset" @click=${() => this._applyAuthPreset('apikey')}>API Key</button>
                            <button type="button" class="auth-preset" @click=${() => this._applyAuthPreset('basic')}>Basic Auth</button>
                        </div>
                        <textarea 
                            name="headers" 
                            class="form-input headers-editor" 
                            placeholder='{"Authorization": "Bearer @var:api_key"}'
                        >${server?.headers ? JSON.stringify(server.headers, null, 2) : ''}</textarea>
                        <div class="form-hint">
                            ${this.i18n.t('mcp_servers.hint_agent_variables')}
                        </div>
                    </div>
                </div>
                
                ${this.testResult ? html`
                    <div class="test-result ${this.testResult.success ? 'success' : 'error'}">
                        ${this.testResult.message}
                    </div>
                ` : ''}
                
                <div class="form-actions">
                    <div class="form-actions-left">
                        <button 
                            type="button" 
                            class="btn btn-warning" 
                            @click=${this._testConnection}
                            ?disabled=${this.testingForm}
                        >
                            <platform-icon name="check" size="14"></platform-icon>
                            ${this.testingForm ? this.i18n.t('mcp_servers.test_checking') : this.i18n.t('mcp_servers.test_connection')}
                        </button>
                    </div>
                    <div class="form-actions-right">
                        <button type="button" class="btn btn-secondary" @click=${this._toggleAddForm}>${this.i18n.t('mcp_servers.cancel')}</button>
                        <button type="submit" class="btn btn-primary">
                            ${isEdit ? this.i18n.t('mcp_servers.save') : this.i18n.t('mcp_servers.add')}
                        </button>
                    </div>
                </div>
            </form>
        `;
    }

    _renderServerCard(server) {
        const isSyncing = this.syncingId === server.server_id;
        const hasHeaders = server.headers && Object.keys(server.headers).length > 0;
        
        return html`
            <div class="server-card">
                <div class="server-header">
                    <div>
                        <div class="server-name">${server.name}</div>
                        <div class="server-id">${server.server_id}</div>
                    </div>
                    <div class="server-actions">
                        <button 
                            class="action-btn test" 
                            title=${this.i18n.t('mcp_servers.title_test')}
                            @click=${() => this._testServer(server.server_id)}
                        >
                            <platform-icon name="check" size="16"></platform-icon>
                        </button>
                        <button 
                            class="action-btn sync ${isSyncing ? 'syncing' : ''}" 
                            title=${this.i18n.t('mcp_servers.title_sync')}
                            @click=${() => this._syncServer(server.server_id)}
                            ?disabled=${isSyncing}
                        >
                            <platform-icon name="refresh" size="16"></platform-icon>
                        </button>
                        <button 
                            class="action-btn edit" 
                            title=${this.i18n.t('mcp_servers.title_edit')}
                            @click=${() => this._editServer(server)}
                        >
                            <platform-icon name="edit" size="16"></platform-icon>
                        </button>
                        <button 
                            class="action-btn delete" 
                            title=${this.i18n.t('mcp_servers.title_delete')}
                            @click=${() => this._deleteServer(server.server_id, server.name)}
                        >
                            <platform-icon name="trash" size="16"></platform-icon>
                        </button>
                    </div>
                </div>
                ${server.description ? html`
                    <div class="server-description">${server.description}</div>
                ` : ''}
                <div class="server-url">${server.url}</div>
                <div class="server-meta">
                    <span class="transport-badge">${server.transport_type}</span>
                    <span class="tools-count">${this.i18n.t('mcp_servers.tools_count', { count: server.cached_tools.length })}</span>
                    ${server.last_sync_at ? html`
                        <span>${this.i18n.t('mcp_servers.last_sync')} ${new Date(server.last_sync_at).toLocaleString()}</span>
                    ` : ''}
                </div>
                ${hasHeaders ? html`
                    <div class="server-headers">
                        ${this.i18n.t('mcp_servers.headers_label')} ${Object.keys(server.headers).join(', ')}
                    </div>
                ` : ''}
            </div>
        `;
    }
}

customElements.define('mcp-servers-modal', MCPServersModal);
