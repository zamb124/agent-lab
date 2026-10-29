/**
 * flows-flow-node-editor — редактор вложенного flow (FlowNode).
 *
 * Поля точно по `FlowNode` (apps/flows/src/runtime/nodes.py):
 *   - flow_id (combobox: список доступных flows + ручной ввод)
 *   - branch_id (по умолчанию 'default')
 *   - call_type ('call' | 'handoff')
 */

import type { ResourceController } from '@platform/lib/base/use-resource.js';
import { html, css, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-segmented-control.js';
import './flows-base-node-editor.js';
import { asObject, isPlainObject } from '../../_helpers/flows-resolvers.js';
import type {CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult} from 'lit';

export class FlowsFlowNodeEditor extends PlatformElement {
    static override properties: PropertyDeclarations = {
        nodeId: { type: String },
        flowId: { type: String },
        branchId: { type: String },
        nodeConfig: { type: Object },
        flowNodeType: { type: String },
        flowVariables: { type: Object },
        graphNodes: { type: Array },
        previewExecutionState: { type: Object },
        dataflowNode: { type: Object },
        embedded: { type: Boolean, reflect: true },
        _showCustom: { state: true },
    }
    declare nodeId: string;
    declare flowId: string;
    declare branchId: string;
    declare nodeConfig: Record<string, unknown> | null;
    declare flowNodeType: string;
    declare flowVariables: Record<string, unknown> | null;
    declare graphNodes: unknown[] | null;
    declare previewExecutionState: Record<string, unknown> | null;
    declare dataflowNode: Record<string, unknown> | null;
    declare embedded: boolean;
    declare _showCustom: boolean;
;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        css`
            :host { display: block; height: 100%; min-height: 0; }
            .field { display: flex; flex-direction: column; gap: var(--space-1); margin-bottom: var(--space-3); }
            label { font-size: var(--text-sm); color: var(--text-secondary); }
            .source-mode {
                margin-bottom: var(--space-2);
            }
            .branch-mode-row {
                display: grid;
                grid-template-columns: minmax(0, 1fr) minmax(210px, 0.62fr);
                gap: var(--space-3);
                align-items: end;
            }
            .branch-mode-row .field { margin-bottom: 0; }
            .call-type-control {
                width: 100%;
            }
            .call-type-hint {
                min-height: 16px;
                font-size: var(--text-xs);
                line-height: 1.35;
                color: var(--text-tertiary);
            }
            @media (max-width: 680px) {
                .branch-mode-row { grid-template-columns: 1fr; }
            }
        `,
    ];
    private _flows: ResourceController;

    constructor() {
        super();
        this.nodeId = '';
        this.flowId = '';
        this.branchId = '';
        this.nodeConfig = null;
        this.flowNodeType = 'flow';
        this.flowVariables = null;
        this.graphNodes = null;
        this.previewExecutionState = null;
        this.dataflowNode = null;
        this.embedded = false;
        this._showCustom = false;
        this._flows = this.useResource('flows/flows', { autoload: true });
    }

    override willUpdate(changed: PropertyValues<this>): void {
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
    _resolvedFlowId(cfg: Record<string, unknown>) {
        const root = typeof cfg.flow_id === 'string' && cfg.flow_id.length > 0 ? cfg.flow_id : '';
        if (root.length > 0) {
            return root;
        }
        const inner = asObject(cfg.config);
        return typeof inner.flow_id === 'string' && inner.flow_id.length > 0 ? inner.flow_id : '';
    }

    _resolvedBranchId(cfg: Record<string, unknown>) {
        const root = typeof cfg.branch_id === 'string' && cfg.branch_id.length > 0 ? cfg.branch_id : '';
        if (root.length > 0) {
            return root;
        }
        const inner = asObject(cfg.config);
        return typeof inner.branch_id === 'string' && inner.branch_id.length > 0 ? inner.branch_id : 'default';
    }

    _branchIdOptions(resolvedFlowId: string, branchId: string): string[] {
        const byId = this._flows.byId;
        const detail = resolvedFlowId.length > 0 && isPlainObject(byId) ? byId[resolvedFlowId] : null;
        const branches = isPlainObject(detail) ? detail.branches : null;
        const keys = isPlainObject(branches) ? Object.keys(branches) : [];
        if (keys.length === 0) {
            return branchId.length > 0 ? [branchId] : ['default'];
        }
        const set = new Set(keys);
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

    _emitPatch(patch: Record<string, unknown>) {
        this.emit('change', { nodeId: this.nodeId, patch });
    }

    _onFlowId(e: CustomEvent) {
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

    _onBranchId(e: CustomEvent) {
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

    _onCallType(e: CustomEvent) {
        const d = e.detail;
        if (d === null || typeof d !== 'object' || !('value' in d)) {
            throw new Error('flows-flow-node-editor: call_type change detail.value');
        }
        const v = d.value;
        if (v !== 'call' && v !== 'handoff') {
            throw new Error('flows-flow-node-editor: call_type must be call or handoff');
        }
        this._emitPatch({ call_type: v });
    }

    override render(): TemplateResult {
        const cfg = asObject(this.nodeConfig);
        const flowId = this._resolvedFlowId(cfg);
        const branchId = this._resolvedBranchId(cfg);
        const callType = cfg.call_type === 'handoff' ? 'handoff' : 'call';
        const branchOptions = this._branchIdOptions(flowId, branchId);
        const flows: Record<string, unknown>[] = [];
        if (!Array.isArray(this._flows.items)) {
            throw new Error('flows-flow-node-editor: flows.items must be an array');
        }
        for (const item of this._flows.items) {
            if (!isPlainObject(item) || typeof item.flow_id !== 'string' || item.flow_id.length === 0) {
                throw new Error('flows-flow-node-editor: flow row requires flow_id');
            }
            if (item.flow_id !== this.flowId) {
                flows.push(item);
            }
        }
        const isInList = flows.some((flow) => flow.flow_id === flowId);
        const useCustom = this._showCustom || (flowId.length > 0 && !isInList);
        const flowIdEnumValues = [
            { value: '', label: '—' },
            ...flows.map((flow) => {
                const id = flow.flow_id;
                if (typeof id !== 'string' || id.length === 0) {
                    throw new Error('flows-flow-node-editor: flow row requires flow_id');
                }
                const name = typeof flow.name === 'string' && flow.name.length > 0 ? flow.name : id;
                return { value: id, label: name };
            }),
        ];
        const branchEnumValues = branchOptions.map((sid) => ({ value: sid, label: sid }));
        return html`
            <flows-base-node-editor
                .nodeId=${this.nodeId}
                .flowId=${this.flowId}
                .branchId=${this.branchId}
                .nodeConfig=${this.nodeConfig}
                .flowNodeType=${this.flowNodeType}
                .flowVariables=${this.flowVariables}
                .graphNodes=${this.graphNodes}
                .previewExecutionState=${this.previewExecutionState}
                .dataflowNode=${this.dataflowNode}
                ?embedded=${this.embedded}
            >
                <div slot="settings">
                    <div class="field">
                        <platform-segmented-control
                            class="source-mode"
                            full-width
                            density="compact"
                            .value=${useCustom ? 'custom' : 'list'}
                            .items=${[
                                { value: 'list', label: this.t('flow_node_editor.from_list') },
                                { value: 'custom', label: this.t('flow_node_editor.custom_id') },
                            ]}
                            aria-label=${this.t('flow_node_editor.flow_id_mode_aria')}
                            @change=${(e: CustomEvent) => { this._showCustom = e.detail.value === 'custom'; }}
                        ></platform-segmented-control>
                        ${useCustom ? html`
                            <platform-field
                                mode="edit"
                                type="string"
                                .label=${this.t('flow_node_editor.flow_id')}
                                .placeholder=${this.t('flow_node_editor.custom_id_hint')}
                                .value=${flowId}
                                @change=${this._onFlowId}
                            ></platform-field>
                        ` : html`
                            <platform-field
                                mode="edit"
                                type="enum"
                                .label=${this.t('flow_node_editor.flow_id')}
                                .value=${flowId}
                                .config=${{ values: flowIdEnumValues }}
                                @change=${this._onFlowId}
                            ></platform-field>
                        `}
                    </div>
                    <div class="branch-mode-row">
                        <div class="field">
                            <platform-field
                                mode="edit"
                                type="enum"
                                .label=${this.t('flow_node_editor.branch_id')}
                                .value=${branchId}
                                .config=${{ values: branchEnumValues }}
                                ?disabled=${flowId.length === 0}
                                @change=${this._onBranchId}
                            ></platform-field>
                        </div>
                        <div class="field call-type-field">
                            <label>${this.t('flow_node_editor.call_type')}</label>
                            <platform-segmented-control
                                class="call-type-control"
                                full-width
                                density="compact"
                                .value=${callType}
                                .items=${[
                                    { value: 'call', label: this.t('flow_node_editor.call_type_call') },
                                    { value: 'handoff', label: this.t('flow_node_editor.call_type_handoff') },
                                ]}
                                aria-label=${this.t('flow_node_editor.call_type')}
                                ?disabled=${flowId.length === 0}
                                @change=${this._onCallType}
                            ></platform-segmented-control>
                            <div class="call-type-hint">${this.t('flow_node_editor.call_type_hint')}</div>
                        </div>
                    </div>
                </div>
            </flows-base-node-editor>
        `;
    }
}

customElements.define('flows-flow-node-editor', FlowsFlowNodeEditor);
