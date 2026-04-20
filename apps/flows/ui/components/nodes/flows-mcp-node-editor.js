/**
 * flows-mcp-node-editor — редактор MCP-ноды.
 *
 * Поля точно по `MCPNode` (apps/flows/src/runtime/nodes.py):
 *   - server_id (select из useResource('flows/mcp_servers'))
 *   - tool_name (select из selectedServer.cached_tools)
 *   - headers (dict<str, str>)
 *   - state_mapping (dict<response_field, state_field>)
 *
 * Дополнительно: read-only превью args_schema выбранного tool через
 * <flows-args-schema-form readonly>; кнопка Sync для useOp('flows/mcp_server_sync').
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import './flows-base-node-editor.js';
import '../editors/flows-json-field-editor.js';
import '../editors/flows-state-mapping-editor.js';
import '../editors/flows-args-schema-form.js';
import '@platform/lib/components/glass-button.js';
import '@platform/lib/components/platform-icon.js';
import { asObject, asString, isPlainObject } from '../../_helpers/flows-resolvers.js';

export class FlowsMcpNodeEditor extends PlatformElement {
    static properties = {
        nodeId: { type: String },
        flowId: { type: String },
        skillId: { type: String },
        nodeConfig: { type: Object },
        nodeType: { type: String },
        flowVariables: { type: Object },
        graphNodes: { type: Array },
        previewExecutionState: { type: Object },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; }
            details {
                margin-bottom: var(--space-3);
                padding: var(--space-2) var(--space-3);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-solid-subtle);
            }
            summary { cursor: pointer; font-size: var(--text-sm); font-weight: var(--font-semibold); }
            .field { display: flex; flex-direction: column; gap: var(--space-1); margin-bottom: var(--space-2); }
            label { font-size: var(--text-sm); color: var(--text-secondary); }
            input, select {
                padding: var(--space-2);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary); font: inherit;
                width: 100%; box-sizing: border-box;
            }
            .row { display: flex; align-items: center; gap: var(--space-2); }
            .row > select, .row > input { flex: 1; }
        `,
    ];

    constructor() {
        super();
        this.nodeId = '';
        this.flowId = '';
        this.skillId = '';
        this.nodeConfig = null;
        this.nodeType = 'mcp';
        this.flowVariables = null;
        this.graphNodes = null;
        this.previewExecutionState = null;
        this._servers = this.useResource('flows/mcp_servers', { autoload: true });
        this._sync = this.useOp('flows/mcp_server_sync');
    }

    _emitPatch(patch) {
        this.emit('change', { nodeId: this.nodeId, patch });
    }

    _onServer(e) {
        this._emitPatch({ server_id: e.target.value, tool_name: '' });
    }

    _onTool(e) {
        this._emitPatch({ tool_name: e.target.value });
    }

    _onHeaders(parsed) {
        this._emitPatch({ headers: parsed && typeof parsed === 'object' ? parsed : {} });
    }

    _onStateMapping(e) {
        const mapping = e.detail?.mapping;
        this._emitPatch({ state_mapping: isPlainObject(mapping) ? mapping : {} });
    }

    async _onSync(serverId) {
        if (!serverId) return;
        await this._sync.run({ server_id: serverId });
    }

    _findServer(servers, id) {
        const found = servers.find((s) => s && s.server_id === id);
        return found ? found : null;
    }

    _findTool(server, name) {
        if (!server || !Array.isArray(server.cached_tools)) return null;
        const found = server.cached_tools.find((t) => {
            if (typeof t === 'string') return t === name;
            return t && t.name === name;
        });
        return found ? found : null;
    }

    _toolSchema(tool) {
        if (!tool || typeof tool !== 'object') return null;
        if (tool.args_schema && typeof tool.args_schema === 'object') return tool.args_schema;
        if (tool.parameters_schema && typeof tool.parameters_schema === 'object'
            && tool.parameters_schema.properties && typeof tool.parameters_schema.properties === 'object') {
            return tool.parameters_schema.properties;
        }
        return null;
    }

    render() {
        const cfg = asObject(this.nodeConfig);
        const serverId = typeof cfg.server_id === 'string' ? cfg.server_id : '';
        const toolName = typeof cfg.tool_name === 'string' ? cfg.tool_name : '';
        const servers = Array.isArray(this._servers.items) ? this._servers.items : [];
        const server = this._findServer(servers, serverId);
        const tools = server && Array.isArray(server.cached_tools) ? server.cached_tools : [];
        const selectedTool = this._findTool(server, toolName);
        const schema = this._toolSchema(selectedTool);
        const headersJson = cfg.headers && typeof cfg.headers === 'object'
            ? JSON.stringify(cfg.headers, null, 2) : '{}';
        const stateMapping = cfg.state_mapping && typeof cfg.state_mapping === 'object'
            ? cfg.state_mapping : {};
        return html`
            <flows-base-node-editor
                .nodeId=${this.nodeId}
                .flowId=${this.flowId}
                .skillId=${this.skillId}
                .nodeConfig=${this.nodeConfig}
                .nodeType=${typeof this.nodeType === 'string' && this.nodeType.length > 0 ? this.nodeType : 'mcp'}
                .flowVariables=${this.flowVariables}
                .graphNodes=${this.graphNodes}
                .previewExecutionState=${this.previewExecutionState}
                @change=${(e) => this.emit('change', e.detail)}
                @rename-node=${(e) => this.emit('rename-node', e.detail)}
                @delete-node=${(e) => this.emit('delete-node', e.detail)}
                @duplicate-node=${(e) => this.emit('duplicate-node', e.detail)}
            >
                <div slot="settings">
                    <div class="field">
                        <label>${this.t('mcp_node_editor.server_id')}</label>
                        <div class="row">
                            <select .value=${serverId} @change=${this._onServer}>
                                <option value="">—</option>
                                ${servers.map((s) => html`<option value=${s.server_id} ?selected=${s.server_id === serverId}>${s.name}</option>`)}
                            </select>
                            <glass-button size="sm" variant="ghost" ?disabled=${!serverId || this._sync.busy}
                                @click=${() => this._onSync(serverId)}>
                                <platform-icon name="refresh"></platform-icon>
                                ${this.t('mcp_node_editor.sync_server')}
                            </glass-button>
                        </div>
                    </div>
                    <div class="field">
                        <label>${this.t('mcp_node_editor.tool_name')}</label>
                        <select .value=${toolName} @change=${this._onTool}>
                            <option value="">—</option>
                            ${tools.map((t) => {
                                const value = typeof t === 'string' ? t : t.name;
                                const label = typeof t === 'string' ? t : (typeof t.title === 'string' && t.title.length > 0 ? t.title : t.name);
                                return html`<option value=${value} ?selected=${value === toolName}>${label}</option>`;
                            })}
                        </select>
                    </div>
                    ${schema ? html`
                        <details>
                            <summary>${this.t('mcp_node_editor.args_preview')}</summary>
                            <flows-args-schema-form
                                .schema=${schema}
                                .values=${{}}
                                ?readonly=${true}
                            ></flows-args-schema-form>
                        </details>
                    ` : ''}
                    <details>
                        <summary>${this.t('mcp_node_editor.headers')}</summary>
                        <flows-json-field-editor
                            .value=${headersJson}
                            @change=${(e) => { if (e.detail && 'parsed' in e.detail) this._onHeaders(e.detail.parsed); }}
                        ></flows-json-field-editor>
                    </details>
                    <details>
                        <summary>${this.t('external_api_editor.response_mapping')}</summary>
                        <flows-state-mapping-editor
                            .mapping=${stateMapping}
                            @change=${this._onStateMapping}
                        ></flows-state-mapping-editor>
                    </details>
                </div>
            </flows-base-node-editor>
        `;
    }
}

customElements.define('flows-mcp-node-editor', FlowsMcpNodeEditor);
