/**
 * flows-flow-node-editor — редактор вложенного flow (FlowNode).
 *
 * Поля точно по `FlowNode` (apps/flows/src/runtime/nodes.py):
 *   - flow_id (combobox: список доступных flows + ручной ввод)
 *   - branch_id (по умолчанию 'default')
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/fields/platform-field.js';
import './flows-base-node-editor.js';
import { asObject } from '../../_helpers/flows-resolvers.js';

export class FlowsFlowNodeEditor extends PlatformElement {
    static properties = {
        nodeId: { type: String },
        flowId: { type: String },
        branchId: { type: String },
        nodeConfig: { type: Object },
        nodeType: { type: String },
        flowVariables: { type: Object },
        graphNodes: { type: Array },
        previewExecutionState: { type: Object },
        dataflowNode: { type: Object },
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
        this.branchId = '';
        this.nodeConfig = null;
        this.nodeType = 'flow';
        this.flowVariables = null;
        this.graphNodes = null;
        this.previewExecutionState = null;
        this.dataflowNode = null;
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

    _resolvedBranchId(cfg) {
        if (cfg === null) {
            return 'default';
        }
        const root = typeof cfg.branch_id === 'string' && cfg.branch_id.length > 0 ? cfg.branch_id : '';
        if (root.length > 0) {
            return root;
        }
        const inner = asObject(cfg.config);
        return typeof inner.branch_id === 'string' && inner.branch_id.length > 0 ? inner.branch_id : 'default';
    }

    _branchIdOptions(resolvedFlowId, branchId) {
        const detail = this._flows.byId && typeof this._flows.byId === 'object' && resolvedFlowId.length > 0
            ? this._flows.byId[resolvedFlowId]
            : null;
        const sk = detail !== null && detail !== undefined && typeof detail === 'object'
            && detail.branches !== null && detail.branches !== undefined && typeof detail.branches === 'object'
            ? Object.keys(detail.branches)
            : [];
        if (sk.length === 0) {
            return branchId.length > 0 ? [branchId] : ['default'];
        }
        const set = new Set(sk);
        if (branchId.length > 0) {
            set.add(branchId);
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
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error('flows-flow-node-editor: flow_id change detail');
        }
        if (!('value' in d)) {
            throw new Error('flows-flow-node-editor: flow_id detail.value');
        }
        const v = d.value;
        if (typeof v !== 'string') {
            throw new Error('flows-flow-node-editor: flow_id string required');
        }
        this._emitPatch({ flow_id: v });
    }

    _onBranchId(e) {
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error('flows-flow-node-editor: branch_id change detail');
        }
        if (!('value' in d)) {
            throw new Error('flows-flow-node-editor: branch_id detail.value');
        }
        const v = d.value;
        if (typeof v !== 'string') {
            throw new Error('flows-flow-node-editor: branch_id string required');
        }
        this._emitPatch({ branch_id: v });
    }

    render() {
        const cfg = asObject(this.nodeConfig);
        const flowId = this._resolvedFlowId(cfg);
        const branchId = this._resolvedBranchId(cfg);
        const branchOptions = this._branchIdOptions(flowId, branchId);
        const flows = Array.isArray(this._flows.items) ? this._flows.items.filter((f) => f && f.flow_id !== this.flowId) : [];
        const isInList = flows.some((f) => f.flow_id === flowId);
        const useCustom = this._showCustom || (flowId.length > 0 && !isInList);
        const flowIdEnumValues = [
            { value: '', label: '—' },
            ...flows.map((f) => ({
                value: f.flow_id,
                label: typeof f.name === 'string' && f.name.length > 0 ? f.name : f.flow_id,
            })),
        ];
        const branchEnumValues = branchOptions.map((sid) => ({ value: sid, label: sid }));
        return html`
            <flows-base-node-editor
                .nodeId=${this.nodeId}
                .flowId=${this.flowId}
                .branchId=${this.branchId}
                .nodeConfig=${this.nodeConfig}
                .nodeType=${typeof this.nodeType === 'string' && this.nodeType.length > 0 ? this.nodeType : 'flow'}
                .flowVariables=${this.flowVariables}
                .graphNodes=${this.graphNodes}
                .previewExecutionState=${this.previewExecutionState}
                .dataflowNode=${this.dataflowNode}
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
                            <platform-field
                                mode="edit"
                                type="string"
                                .placeholder=${this.t('flow_node_editor.custom_id_hint')}
                                .value=${flowId}
                                @change=${this._onFlowId}
                            ></platform-field>
                        ` : html`
                            <platform-field
                                mode="edit"
                                type="enum"
                                .value=${flowId}
                                .config=${{ values: flowIdEnumValues }}
                                @change=${this._onFlowId}
                            ></platform-field>
                        `}
                    </div>
                    <div class="field">
                        <label>${this.t('flow_node_editor.branch_id')}</label>
                        <platform-field
                            mode="edit"
                            type="enum"
                            .value=${branchId}
                            .config=${{ values: branchEnumValues }}
                            ?disabled=${flowId.length === 0}
                            @change=${this._onBranchId}
                        ></platform-field>
                    </div>
                </div>
            </flows-base-node-editor>
        `;
    }
}

customElements.define('flows-flow-node-editor', FlowsFlowNodeEditor);
