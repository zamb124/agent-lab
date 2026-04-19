/**
 * flows-flow-node-editor — flow_node (вложенный flow).
 */

import { html } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import './flows-base-node-editor.js';

export class FlowsFlowNodeEditor extends PlatformElement {
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
        this._flows = this.useResource('flows/flows', { autoload: true });
    }

    _onConfigChange(field, value) {
        const cfg = { ...(this.nodeConfig?.config || {}), [field]: value };
        this.emit('change', { nodeId: this.nodeId, patch: { config: cfg } });
    }

    render() {
        const cfg = this.nodeConfig?.config || {};
        const flows = (this._flows.items || []).filter((f) => f && f.flow_id !== this.flowId);
        return html`
            <flows-base-node-editor
                .nodeId=${this.nodeId}
                .flowId=${this.flowId}
                .skillId=${this.skillId}
                .nodeConfig=${this.nodeConfig}
                .nodeType=${'flow_node'}
                @change=${(e) => this.emit('change', e.detail)}
            >
                <div slot="settings">
                    <label>${this.t('flow_node_editor.field_flow_id')}</label>
                    <select
                        style="display:block;width:100%;padding:var(--space-2);margin-bottom:var(--space-3);"
                        .value=${cfg.flow_id || ''}
                        @change=${(e) => this._onConfigChange('flow_id', e.target.value)}
                    >
                        <option value="">— ${this.t('flow_node_editor.field_flow_pick')} —</option>
                        ${flows.map((f) => html`<option value=${f.flow_id}>${f.name || f.flow_id}</option>`)}
                    </select>
                    <label>${this.t('flow_node_editor.field_skill_id')}</label>
                    <input
                        type="text"
                        style="display:block;width:100%;padding:var(--space-2);"
                        .value=${cfg.skill_id || ''}
                        placeholder="base"
                        @input=${(e) => this._onConfigChange('skill_id', e.target.value)}
                    />
                </div>
            </flows-base-node-editor>
        `;
    }
}

customElements.define('flows-flow-node-editor', FlowsFlowNodeEditor);
