/**
 * flows-flow-node-editor — редактор вложенного flow (FlowNode).
 *
 * Поля точно по `FlowNode` (apps/flows/src/runtime/nodes.py):
 *   - flow_id (combobox: список доступных flows + ручной ввод)
 *   - skill_id (default 'default')
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import './flows-base-node-editor.js';
import { asObject, asString } from '../../_helpers/flows-resolvers.js';

export class FlowsFlowNodeEditor extends PlatformElement {
    static properties = {
        nodeId: { type: String },
        flowId: { type: String },
        skillId: { type: String },
        nodeConfig: { type: Object },
        nodeType: { type: String },
        flowVariables: { type: Object },
        graphNodes: { type: Array },
        previewExecutionState: { type: Object },
        expanded: { type: Boolean, reflect: true },
        embedded: { type: Boolean, reflect: true },
        _showCustom: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; height: 100%; min-height: 0; }
            .field { display: flex; flex-direction: column; gap: var(--space-1); margin-bottom: var(--space-3); }
            label { font-size: var(--text-sm); color: var(--text-secondary); }
            input, select {
                padding: var(--space-2);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary); font: inherit;
                width: 100%; box-sizing: border-box;
            }
            .toggle button {
                padding: 4px 12px;
                background: var(--glass-solid-subtle);
                color: var(--text-secondary);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-full);
                font-size: var(--text-xs);
                cursor: pointer;
            }
            .toggle button[active] { background: var(--accent-subtle); color: var(--accent); border-color: var(--accent-subtle); }
            .row { display: flex; gap: var(--space-2); margin-bottom: var(--space-2); }
        `,
    ];

    constructor() {
        super();
        this.nodeId = '';
        this.flowId = '';
        this.skillId = '';
        this.nodeConfig = null;
        this.nodeType = 'flow';
        this.flowVariables = null;
        this.graphNodes = null;
        this.previewExecutionState = null;
        this.expanded = false;
        this.embedded = false;
        this._showCustom = false;
        this._flows = this.useResource('flows/flows', { autoload: true });
    }

    _emitPatch(patch) {
        this.emit('change', { nodeId: this.nodeId, patch });
    }

    _onFlowId(e) {
        this._emitPatch({ flow_id: e.target.value });
    }

    _onSkillId(e) {
        this._emitPatch({ skill_id: e.target.value });
    }

    render() {
        const cfg = asObject(this.nodeConfig);
        const flowId = typeof cfg.flow_id === 'string' ? cfg.flow_id : '';
        const skillId = typeof cfg.skill_id === 'string' ? cfg.skill_id : 'default';
        const flows = Array.isArray(this._flows.items) ? this._flows.items.filter((f) => f && f.flow_id !== this.flowId) : [];
        const isInList = flows.some((f) => f.flow_id === flowId);
        const useCustom = this._showCustom || (flowId && !isInList);
        return html`
            <flows-base-node-editor
                .nodeId=${this.nodeId}
                .flowId=${this.flowId}
                .skillId=${this.skillId}
                .nodeConfig=${this.nodeConfig}
                .nodeType=${typeof this.nodeType === 'string' && this.nodeType.length > 0 ? this.nodeType : 'flow'}
                .flowVariables=${this.flowVariables}
                .graphNodes=${this.graphNodes}
                .previewExecutionState=${this.previewExecutionState}
                ?expanded=${this.expanded}
                ?embedded=${this.embedded}
            >
                <div slot="settings">
                    <div class="field">
                        <label>${this.t('flow_node_editor.flow_id')}</label>
                        <div class="row toggle">
                            <button ?active=${!useCustom} @click=${() => { this._showCustom = false; }}>
                                ${this.t('flow_node_editor.from_list')}
                            </button>
                            <button ?active=${useCustom} @click=${() => { this._showCustom = true; }}>
                                ${this.t('flow_node_editor.custom_id')}
                            </button>
                        </div>
                        ${useCustom ? html`
                            <input type="text" placeholder=${this.t('flow_node_editor.custom_id_hint')}
                                .value=${flowId} @input=${this._onFlowId} />
                        ` : html`
                            <select .value=${flowId} @change=${this._onFlowId}>
                                <option value="">—</option>
                                ${flows.map((f) => html`<option value=${f.flow_id} ?selected=${f.flow_id === flowId}>${typeof f.name === 'string' && f.name.length > 0 ? f.name : f.flow_id}</option>`)}
                            </select>
                        `}
                    </div>
                    <div class="field">
                        <label>${this.t('flow_node_editor.skill_id')}</label>
                        <input type="text" placeholder="default" .value=${skillId} @input=${this._onSkillId} />
                    </div>
                </div>
            </flows-base-node-editor>
        `;
    }
}

customElements.define('flows-flow-node-editor', FlowsFlowNodeEditor);
