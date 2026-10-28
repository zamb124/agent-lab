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
import { asObject } from '../../_helpers/flows-resolvers.js';
import type {CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult} from 'lit';

export class FlowsFlowNodeEditor extends PlatformElement {
    static override properties: PropertyDeclarations = {
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
    }
    declare nodeId: string;
    declare flowId: string;
    declare branchId: string;
    declare nodeConfig: Record<string, any> | null;
    declare nodeType: any;
    declare flowVariables: Record<string, any> | null;
    declare graphNodes: any[] | null;
    declare previewExecutionState: Record<string, any> | null;
    declare dataflowNode: Record<string, any> | null;
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
        this.nodeType = 'flow';
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
    _resolvedFlowId(cfg: any) {
        if (cfg === null) {
            return '';
        }
        const root = typeof cfg.flow_id === 'string' && cfg.flow_id.length > 0 ? cfg.flow_id : '';
        if (root.length > 0) {
            return root;
        }
        const inner = asObject(cfg.config);
        return typeof (inner as any).flow_id === 'string' && (inner as any).flow_id.length > 0 ? (inner as any).flow_id : '';
    }

    _resolvedBranchId(cfg: any) {
        if (cfg === null) {
            return 'default';
        }
        const root = typeof cfg.branch_id === 'string' && cfg.branch_id.length > 0 ? cfg.branch_id : '';
        if (root.length > 0) {
            return root;
        }
        const inner = asObject(cfg.config);
        return typeof (inner as any).branch_id === 'string' && (inner as any).branch_id.length > 0 ? (inner as any).branch_id : 'default';
    }

    _branchIdOptions(resolvedFlowId: any, branchId: any) {
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

    _emitPatch(patch: any) {
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
        const callType = (cfg as Record<string, any>)?.call_type === 'handoff' ? 'handoff' : 'call';
        const branchOptions = this._branchIdOptions(flowId, branchId);
        const flows = Array.isArray(this._flows.items) ? this._flows.items.filter((f: any) => f && f.flow_id !== this.flowId) : [];
        const isInList = flows.some((f: any) => f.flow_id === flowId);
        const useCustom = this._showCustom || (flowId.length > 0 && !isInList);
        const flowIdEnumValues = [
            { value: '', label: '—' },
            ...flows.map((f: any) => ({
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
