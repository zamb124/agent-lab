/**
 * MCPNodeEditor - редактор для MCP типа ноды
 * Вызов MCP tool с выбранного сервера
 */
import { html, css } from 'lit';
import { BaseNodeEditor } from './base-node-editor.js';
import '../editors/json-field-editor.js';
import '../editors/test-panel.js';

export class MCPNodeEditor extends BaseNodeEditor {
    static properties = {
        ...BaseNodeEditor.properties,
        mcpServers: { type: Array },
        selectedServer: { type: String },
        serverTools: { type: Array },
        selectedToolSchema: { type: Object },
    };

    static styles = [
        BaseNodeEditor.styles,
        css`
            .tool-params {
                background: var(--glass-tint-subtle);
                border-radius: var(--radius-md);
                padding: var(--space-2);
                font-size: var(--text-sm);
            }
            
            .tool-param {
                display: flex;
                align-items: baseline;
                gap: var(--space-2);
                padding: var(--space-1) 0;
                border-bottom: 1px solid var(--border-subtle);
            }
            
            .tool-param:last-child {
                border-bottom: none;
            }
            
            .param-name {
                font-family: var(--font-mono);
                font-weight: var(--font-medium);
                color: var(--text-primary);
            }
            
            .param-type {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                background: var(--glass-solid-subtle);
                padding: 1px 6px;
                border-radius: var(--radius-sm);
            }
            
            .param-required {
                color: var(--error);
                font-weight: bold;
            }
            
            .param-desc {
                color: var(--text-secondary);
                font-size: var(--text-xs);
                flex: 1;
            }
        `
    ];

    constructor() {
        super();
        this._nodeType = 'mcp';
        this.mcpServers = [];
        this.selectedServer = '';
        this.serverTools = [];
        this.selectedToolSchema = null;
    }

    connectedCallback() {
        super.connectedCallback();
        this._loadMCPServers();
    }

    async _loadMCPServers() {
        try {
            const servers = await this.a2a.get('/api/v1/mcp/servers');
            this.mcpServers = servers || [];
            
            if (this.nodeConfig?.server_id) {
                this.selectedServer = this.nodeConfig.server_id;
                this._loadServerTools(this.selectedServer);
            }
        } catch (error) {
            console.error('Failed to load MCP servers:', error);
            this.mcpServers = [];
        }
    }

    async _loadServerTools(serverId) {
        if (!serverId) {
            this.serverTools = [];
            return;
        }
        
        try {
            const server = this.mcpServers.find(s => s.server_id === serverId);
            if (server?.cached_tools) {
                this.serverTools = server.cached_tools.map(toolId => {
                    const parts = toolId.split(':');
                    return {
                        tool_id: toolId,
                        name: parts[2] || toolId,
                    };
                });
                
                // Если tool уже выбран - загружаем его схему
                if (this.nodeConfig?.tool_name) {
                    await this._loadToolSchema(serverId, this.nodeConfig.tool_name);
                }
            } else {
                this.serverTools = [];
            }
        } catch (error) {
            console.error('Failed to load server tools:', error);
            this.serverTools = [];
        }
    }

    async _loadToolSchema(serverId, toolName) {
        if (!serverId || !toolName) {
            this.selectedToolSchema = null;
            return;
        }
        
        const toolId = `mcp:${serverId}:${toolName}`;
        try {
            const tool = await this.a2a.get(`/api/v1/tools/${encodeURIComponent(toolId)}`);
            this.selectedToolSchema = tool.args_schema || {};
        } catch (error) {
            console.error('Failed to load tool schema:', error);
            this.selectedToolSchema = {};
        }
    }

    _onServerChange(e) {
        this.selectedServer = e.target.value;
        this._onInputChange('server_id', e.target.value);
        this._loadServerTools(e.target.value);
        this.selectedToolSchema = null;
    }

    async _onToolChange(e) {
        const toolName = e.target.value;
        this._onInputChange('tool_name', toolName);
        
        if (!toolName || !this.selectedServer) {
            this.selectedToolSchema = null;
            return;
        }
        
        // Загружаем схему tool
        const toolId = `mcp:${this.selectedServer}:${toolName}`;
        try {
            const tool = await this.a2a.get(`/api/v1/tools/${encodeURIComponent(toolId)}`);
            this.selectedToolSchema = tool.args_schema || {};
        } catch (error) {
            console.error('Failed to load tool schema:', error);
            this.selectedToolSchema = {};
        }
    }

    renderFields() {
        const config = this.nodeConfig;
        const selectedServerId = config.server_id || this.selectedServer;
        const selectedServer = this.mcpServers.find(s => s.server_id === selectedServerId);
        const showCommonFields = !this.expanded;
        
        return html`
            ${showCommonFields ? html`
                ${this.renderNodeIdField()}
                
                <div class="form-group">
                    <div class="form-label">
                        <span class="form-label-text">Имя</span>
                    </div>
                    <input 
                        type="text" 
                        class="form-input"
                        .value=${config.name || ''}
                        @change=${(e) => this._onInputChange('name', e.target.value)}
                    />
                </div>
            ` : ''}
            
            <div class="form-group">
                <div class="form-label">
                    <span class="form-label-text">MCP Сервер</span>
                </div>
                <select 
                    class="form-input form-select"
                    .value=${selectedServerId || ''}
                    @change=${this._onServerChange}
                >
                    <option value="">Выберите сервер...</option>
                    ${this.mcpServers.map(server => html`
                        <option 
                            value=${server.server_id}
                            ?selected=${server.server_id === selectedServerId}
                        >
                            ${server.name} (${server.server_id})
                        </option>
                    `)}
                </select>
                ${selectedServer ? html`
                    <span class="form-hint">${selectedServer.url}</span>
                ` : ''}
            </div>
            
            <div class="form-group">
                <div class="form-label">
                    <span class="form-label-text">Tool</span>
                </div>
                <select 
                    class="form-input form-select"
                    .value=${config.tool_name || ''}
                    @change=${this._onToolChange}
                    ?disabled=${!selectedServerId}
                >
                    <option value="">Выберите tool...</option>
                    ${this.serverTools.map(tool => html`
                        <option 
                            value=${tool.name}
                            ?selected=${tool.name === config.tool_name}
                        >
                            ${tool.name}
                        </option>
                    `)}
                </select>
                ${this.serverTools.length === 0 && selectedServerId ? html`
                    <span class="form-hint">Синхронизируйте тулы на странице MCP серверов</span>
                ` : ''}
            </div>
            
            ${this.selectedToolSchema && Object.keys(this.selectedToolSchema).length > 0 ? html`
                <div class="form-group">
                    <div class="form-label">
                        <span class="form-label-text">Параметры tool</span>
                    </div>
                    <div class="tool-params">
                        ${Object.entries(this.selectedToolSchema).map(([name, param]) => html`
                            <div class="tool-param">
                                <span class="param-name">${name}</span>
                                <span class="param-type">${param.type || 'string'}</span>
                                ${param.required ? html`<span class="param-required">*</span>` : ''}
                                ${param.description ? html`
                                    <span class="param-desc">${param.description}</span>
                                ` : ''}
                            </div>
                        `)}
                    </div>
                </div>
            ` : ''}
            
            <div class="form-group">
                <div class="form-label">
                    <span class="form-label-text">Headers (JSON)</span>
                </div>
                <json-field-editor
                    .value=${config.headers ? JSON.stringify(config.headers, null, 2) : '{}'}
                    @change=${(e) => {
                        const editor = e.target;
                        if (editor.isValid()) {
                            this._onInputChange('headers', editor.getParsedValue());
                        }
                    }}
                    min-height="60"
                    hint="Дополнительные headers (переопределяют серверные)"
                ></json-field-editor>
            </div>
            
            ${this.renderMappingSection()}
            
            <test-panel
                .inputState=${this._buildDefaultState()}
                ?expanded=${this.expanded}
                ?hide-input-state=${this.expanded}
                @validate=${this._onValidate}
                @execute=${this._onExecute}
            ></test-panel>
        `;
    }
}

customElements.define('mcp-node-editor', MCPNodeEditor);
