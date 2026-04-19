/**
 * flows-mcp-node-editor — mcp_node (вызов MCP-tool).
 */

import { html } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import './flows-base-node-editor.js';

export class FlowsMcpNodeEditor extends PlatformElement {
    static properties = {
        nodeId: { type: String },
        flowId: { type: String },
        skillId: { type: String },
        nodeConfig: { type: Object },
    };

    constructor() {
        super();
        this.nodeId = '';
        this.flowId = '';
        this.skillId = '';
        this.nodeConfig = null;
        this._servers = this.useResource('flows/mcp_servers', { autoload: true });
    }

    _onConfigChange(field, value) {
        const cfg = { ...(this.nodeConfig?.config || {}), [field]: value };
        this.emit('change', { nodeId: this.nodeId, patch: { config: cfg } });
    }

    render() {
        const cfg = this.nodeConfig?.config || {};
        const servers = this._servers.items || [];
        const currentServer = servers.find((s) => s.server_id === cfg.server_id);
        const tools = currentServer?.cached_tools || [];
        return html`
            <flows-base-node-editor
                .nodeId=${this.nodeId}
                .flowId=${this.flowId}
                .skillId=${this.skillId}
                .nodeConfig=${this.nodeConfig}
                .nodeType=${'mcp_node'}
                @change=${(e) => this.emit('change', e.detail)}
            >
                <div slot="settings">
                    <label>${this.t('mcp_node_editor.field_server')}</label>
                    <select
                        style="display:block;width:100%;padding:var(--space-2);margin-bottom:var(--space-3);"
                        .value=${cfg.server_id || ''}
                        @change=${(e) => this._onConfigChange('server_id', e.target.value)}
                    >
                        <option value="">— ${this.t('mcp_node_editor.field_server_pick')} —</option>
                        ${servers.map((s) => html`<option value=${s.server_id}>${s.name}</option>`)}
                    </select>
                    <label>${this.t('mcp_node_editor.field_tool')}</label>
                    <select
                        style="display:block;width:100%;padding:var(--space-2);"
                        .value=${cfg.tool_name || ''}
                        @change=${(e) => this._onConfigChange('tool_name', e.target.value)}
                    >
                        <option value="">—</option>
                        ${tools.map((t) => html`<option value=${t}>${t}</option>`)}
                    </select>
                </div>
            </flows-base-node-editor>
        `;
    }
}

customElements.define('flows-mcp-node-editor', FlowsMcpNodeEditor);
