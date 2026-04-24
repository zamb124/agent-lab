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

    willUpdate(changed) {
        super.willUpdate(changed);
        if (changed.has('nodeConfig')) {
            const cfg = asObject(this.nodeConfig);
            const fid = this._resolvedFlowId(cfg);
            if (typeof fid === 'string' && fid.length > 0) {
                void this._flows.get(fid);
            }
        }
    }

    /**
     * Канвас и вложенный tool могут хранить поля в `config`; runtime читает с корня или из `config`.
     */
    _resolvedFlowId(cfg) {
        if (cfg === null) {
            return '';
        }
        const root = typeof cfg.flow_id === 'string' && cfg.flow_id.length > 0 ? cfg.flow_id : '';
        if (root.length > 0) {
            return root;
        }
        const inner = asObject(cfg.config);
        return typeof inner.flow_id === 'string' && inner.flow_id.length > 0 ? inner.flow_id : '';
    }

    _resolvedSkillId(cfg) {
        if (cfg === null) {
            return 'default';
        }
        const root = typeof cfg.skill_id === 'string' && cfg.skill_id.length > 0 ? cfg.skill_id : '';
        if (root.length > 0) {
            return root;
        }
        const inner = asObject(cfg.config);
        return typeof inner.skill_id === 'string' && inner.skill_id.length > 0 ? inner.skill_id : 'default';
    }

    _skillIdOptions(resolvedFlowId, skillId) {
        const detail = this._flows.byId && typeof this._flows.byId === 'object' && resolvedFlowId.length > 0
            ? this._flows.byId[resolvedFlowId]
            : null;
        const sk = detail !== null && detail !== undefined && typeof detail === 'object'
            && detail.skills !== null && detail.skills !== undefined && typeof detail.skills === 'object'
            ? Object.keys(detail.skills)
            : [];
        if (sk.length === 0) {
            return skillId.length > 0 ? [skillId] : ['default'];
        }
        const set = new Set(sk);
        if (skillId.length > 0) {
            set.add(skillId);
        }
        const arr = Array.from(set);
        arr.sort((a, b) => {
            if (a === 'default') {
                return -1;
            }
            if (b === 'default') {
                return 1;
            }
            return a.localeCompare(b, undefined, { sensitivity: 'base' });
        });
        return arr;
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
        const flowId = this._resolvedFlowId(cfg);
        const skillId = this._resolvedSkillId(cfg);
        const skillOptions = this._skillIdOptions(flowId, skillId);
        const flows = Array.isArray(this._flows.items) ? this._flows.items.filter((f) => f && f.flow_id !== this.flowId) : [];
        const isInList = flows.some((f) => f.flow_id === flowId);
        const useCustom = this._showCustom || (flowId.length > 0 && !isInList);
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
                        <select
                            .value=${skillId}
                            ?disabled=${flowId.length === 0}
                            @change=${this._onSkillId}
                        >
                            ${skillOptions.map(
                                (sid) => html`<option value=${sid}>${sid}</option>`,
                            )}
                        </select>
                    </div>
                </div>
            </flows-base-node-editor>
        `;
    }
}

customElements.define('flows-flow-node-editor', FlowsFlowNodeEditor);
