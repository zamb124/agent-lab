/**
 * MCPNodeModal - модалка редактирования MCP Node
 * Вызов MCP tool с внешнего сервера
 */
import { html, css } from 'lit';
import { BaseNodeModal } from './base-node-modal.js';

export class MCPNodeModal extends BaseNodeModal {
    static styles = [
        BaseNodeModal.styles,
        css`
            .mcp-section {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                padding: var(--space-3);
                background: var(--glass-tint-subtle);
                border-radius: var(--radius-md);
            }
            
            .mcp-section-title {
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-secondary);
                margin-bottom: var(--space-2);
            }
            
            .server-info {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-top: var(--space-1);
            }
        `
    ];

    static properties = {
        ...BaseNodeModal.properties,
        mcpServers: { type: Array },
        selectedServerId: { type: String },
        serverTools: { type: Array },
    };

    constructor() {
        super();
        this.mcpServers = [];
        this.selectedServerId = '';
        this.serverTools = [];
    }

    getNodeType() {
        return 'mcp';
    }

    getModalTitle() {
        return 'MCP Tool Node';
    }

    showModal(nodeId = '', config = {}) {
        super.showModal(nodeId, config);
        this.selectedServerId = config.server_id || '';
        this._loadMCPServers();
    }

    async _loadMCPServers() {
        try {
            const servers = await this.a2a.get('/api/v1/mcp/servers');
            this.mcpServers = servers || [];
            
            if (this.selectedServerId) {
                this._loadServerTools(this.selectedServerId);
            }
        } catch (error) {
            this.error(`Ошибка загрузки MCP серверов: ${error.message}`);
            this.mcpServers = [];
        }
    }

    _loadServerTools(serverId) {
        const server = this.mcpServers.find(s => s.server_id === serverId);
        if (server?.cached_tools) {
            this.serverTools = server.cached_tools.map(toolId => {
                const parts = toolId.split(':');
                return {
                    tool_id: toolId,
                    name: parts[2] || toolId,
                };
            });
        } else {
            this.serverTools = [];
        }
    }

    _onServerChange(e) {
        this.selectedServerId = e.target.value;
        this._loadServerTools(e.target.value);
    }

    _buildDefaultState() {
        return {
            content: 'Текст запроса',
            messages: [],
            variables: this.flowVariables || {},
        };
    }

    _buildConfig() {
        const name = this.shadowRoot.querySelector('[name="name"]')?.value?.trim() || '';
        const serverId = this.shadowRoot.querySelector('[name="server_id"]')?.value?.trim() || '';
        const toolName = this.shadowRoot.querySelector('[name="tool_name"]')?.value?.trim() || '';
        
        if (!serverId) {
            throw new Error('MCP сервер обязателен');
        }
        
        if (!toolName) {
            throw new Error('Tool обязателен');
        }
        
        const config = {
            type: 'mcp',
            server_id: serverId,
            tool_name: toolName,
        };
        
        if (name) config.name = name;
        
        const headersEditor = this.shadowRoot.querySelector('json-field-editor[name="headers"]');
        if (headersEditor?.getValue()?.trim()) {
            if (!headersEditor.isValid()) {
                throw new Error('Неверный формат Headers JSON');
            }
            const headers = headersEditor.getParsedValue();
            if (Object.keys(headers).length > 0) {
                config.headers = headers;
            }
        }
        
        const stateMappingEditor = this.shadowRoot.querySelector('json-field-editor[name="state_mapping"]');
        if (stateMappingEditor?.getValue()?.trim()) {
            if (!stateMappingEditor.isValid()) {
                throw new Error('Неверный формат State Mapping JSON');
            }
            const stateMapping = stateMappingEditor.getParsedValue();
            if (Object.keys(stateMapping).length > 0) {
                config.state_mapping = stateMapping;
            }
        }
        
        const inputMappingEditor = this.shadowRoot.querySelector('state-mapping-editor');
        const inputMapping = inputMappingEditor?.getValue() || {};
        if (Object.keys(inputMapping).length > 0) {
            config.input_mapping = inputMapping;
        }
        
        return this._applyStateSettings(config);
    }

    renderBody() {
        const config = this.nodeConfig;
        const selectedServer = this.mcpServers.find(s => s.server_id === this.selectedServerId);
        
        return html`
            <div class="form-layout">
                <div class="form-sidebar">
                    <div class="form-group">
                        <label class="form-label">Node ID *</label>
                        <input 
                            type="text" 
                            name="node_id"
                            class="form-input ${this.isEdit ? 'readonly' : ''}"
                            .value=${this.nodeId || ''}
                            ?readonly=${this.isEdit}
                            placeholder="my_mcp_node"
                            required
                        />
                    </div>
                    
                    <div class="form-group">
                        <label class="form-label">Имя</label>
                        <input 
                            type="text" 
                            name="name"
                            class="form-input"
                            .value=${config.name || ''}
                            placeholder="MCP Tool Call"
                        />
                    </div>
                    
                    <div class="mcp-section">
                        <div class="mcp-section-title">MCP Сервер и Tool</div>
                        
                        <div class="form-group">
                            <label class="form-label">MCP Сервер *</label>
                            <select 
                                name="server_id" 
                                class="form-select"
                                .value=${this.selectedServerId}
                                @change=${this._onServerChange}
                                required
                            >
                                <option value="">Выберите сервер...</option>
                                ${this.mcpServers.map(server => html`
                                    <option 
                                        value=${server.server_id}
                                        ?selected=${server.server_id === this.selectedServerId}
                                    >
                                        ${server.name} (${server.server_id})
                                    </option>
                                `)}
                            </select>
                            ${selectedServer ? html`
                                <div class="server-info">URL: ${selectedServer.url}</div>
                            ` : ''}
                        </div>
                        
                        <div class="form-group">
                            <label class="form-label">Tool *</label>
                            <select 
                                name="tool_name" 
                                class="form-select"
                                .value=${config.tool_name || ''}
                                ?disabled=${!this.selectedServerId}
                                required
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
                            ${this.serverTools.length === 0 && this.selectedServerId ? html`
                                <span class="form-hint">Синхронизируйте tools на странице MCP серверов</span>
                            ` : ''}
                        </div>
                    </div>
                    
                    <div class="form-group">
                        <label class="form-label">Headers (JSON)</label>
                        <json-field-editor
                            name="headers"
                            .value=${config.headers ? JSON.stringify(config.headers, null, 2) : '{}'}
                            min-height="80"
                            placeholder='{"X-Custom-Header": "value"}'
                            hint="Дополнительные headers (переопределяют серверные)"
                        ></json-field-editor>
                    </div>
                    
                    ${this.renderStateSettings()}
                </div>
                
                <div class="form-main">
                    <div class="form-group">
                        <state-mapping-editor
                            mode="input"
                            .mappings=${config.input_mapping || {}}
                            .stateVariables=${Object.keys(this._buildDefaultState())}
                        ></state-mapping-editor>
                    </div>
                    
                    <div class="form-group">
                        <label class="form-label">State Mapping (JSON)</label>
                        <json-field-editor
                            name="state_mapping"
                            .value=${config.state_mapping ? JSON.stringify(config.state_mapping, null, 2) : '{}'}
                            min-height="80"
                            placeholder='{"result": "mcp_result"}'
                            hint="Маппинг результата MCP tool в state"
                        ></json-field-editor>
                    </div>
                    
                    <test-panel
                        .inputState=${this._buildDefaultState()}
                        @validate=${this._onValidate}
                        @execute=${this._onExecute}
                    ></test-panel>
                </div>
            </div>
        `;
    }

    _parseMappings(mapping) {
        if (!mapping) return [];
        return Object.entries(mapping).map(([param, source]) => ({
            param,
            source,
            id: crypto.randomUUID(),
        }));
    }
}

customElements.define('mcp-node-modal', MCPNodeModal);
