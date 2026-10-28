/**
 * flows-property-panel — слот для активного редактора ноды.
 *
 * Читает selectedNodeId, skillsData, variables, previewExecutionState из
 * useOp('flows/editor') as unknown as ControllerFor<'flows/editor'>. Маршрутизирует по `node.type` (NodeType enum).
 *
 * Действия от base-node-editor:
 *   - 'change' { nodeId, patch } → updateBranchData(смёржить node)
 *   - 'delete-node' { nodeId } → bulk_delete + локальный removeNode
 *   - 'duplicate-node' { nodeId } → клонирует node под новым id
 */

import type { OpController, ControllerFor } from '@platform/lib/base/use-resource.js';
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { renderFlowsNodeEditorSurface } from './flows-node-editor-surface.js';
import { asArray, asNumber, asObject, asString, isPlainObject } from '../../_helpers/flows-resolvers.js';
import type {CSSResultGroup, PropertyDeclarations, TemplateResult} from 'lit';

export class FlowsPropertyPanel extends PlatformElement {
    static i18nNamespace = 'flows';

    static override properties: PropertyDeclarations = {
        flowId: { type: String },
        branchId: { type: String },
        nodeId: { type: String },
        focusMode: { type: Boolean },
        focusSection: { type: String },
    }
    declare flowId: string;
    declare branchId: string;
    declare nodeId: string;
    declare focusMode: boolean;
    declare focusSection: string;
;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        css`
            :host { display: block; height: 100%; min-height: 0; }
            .inherited-banner {
                margin: var(--space-3);
                padding: var(--space-2) var(--space-3);
                background: var(--accent-subtle, var(--info-bg));
                border: 1px dashed var(--accent, var(--info));
                border-radius: var(--radius-sm);
                color: var(--text-secondary);
                font-size: var(--text-sm);
                line-height: 1.4;
                display: flex;
                gap: var(--space-2);
                align-items: flex-start;
            }
            .inherited-banner .badge {
                color: var(--accent, var(--info));
                font-weight: var(--font-semibold);
            }
        `,
    ];
    private _editor: ControllerFor<'flows/editor'>;
    private _bulkDelete: OpController;
    private _codeAgentCopyTree: OpController;
    private _codeAgentDelete: OpController;

    constructor() {
        super();
        this.flowId = '';
        this.branchId = 'base';
        this.nodeId = '';
        this.focusMode = false;
        this.focusSection = 'prompt';
        this._editor = this.useOp('flows/editor');
        this._bulkDelete = this.useOp('flows/editor_bulk_delete');
        this._codeAgentCopyTree = this.useOp('flows/code_agent_copy_tree');
        this._codeAgentDelete = this.useOp('flows/code_agent_delete');
    }

    _onChange(e: CustomEvent) {
        const { nodeId, patch } = (isPlainObject(e.detail) ? e.detail : {}) as Record<string, any>;
        if (!nodeId || !patch || typeof patch !== 'object') return;
        const state = this._editor.state;
        if (!state) return;
        const skillsData = state.branchData;
        if (!skillsData || typeof skillsData !== 'object') return;
        const nodes: Record<string, any> = (skillsData as Record<string, any>).nodes && typeof (skillsData as Record<string, any>).nodes === 'object' ? { ...(skillsData as Record<string, any>).nodes } : {};
        const node = nodes[nodeId];
        if (!node) return;
        const normalizedPatch: any = { ...patch };
        if (Object.prototype.hasOwnProperty.call(normalizedPatch, 'llm_override')) {
            if (!Object.prototype.hasOwnProperty.call(normalizedPatch, 'llm')) {
                normalizedPatch.llm = normalizedPatch.llm_override;
            }
            delete normalizedPatch.llm_override;
        }
        const nextNode: any = { ...node, ...normalizedPatch };
        const patchHasLlm = Object.prototype.hasOwnProperty.call(normalizedPatch, 'llm');
        if (
            !patchHasLlm
            && isPlainObject(nextNode.llm_override)
        ) {
            nextNode.llm = { ...nextNode.llm_override };
        }
        delete nextNode.llm_override;
        nodes[nodeId] = nextNode;
        (this._editor.updateBranchData({ data: { ...skillsData, nodes } }) as any);
        (this._editor.setDirty({ dirty: true }) as any);
        (this._editor.pushHistory({ snapshot: { ...skillsData, nodes } }) as any);
    }

    async _onDeleteNode(e: CustomEvent) {
        const { nodeId } = isPlainObject(e.detail) ? e.detail : {};
        if (typeof nodeId !== 'string' || !nodeId) return;
        if (!this.flowId) return;
        const state = this._editor.state;
        const skillsData = state?.branchData;
        const node = (skillsData as Record<string, any>)?.nodes?.[nodeId];
        if (isPlainObject(node) && node.type === 'code_agent') {
            const catalogId = typeof node.catalog_id === 'string' ? node.catalog_id : '';
            await this._codeAgentDelete.run({
                flow_id: this.flowId,
                node_id: nodeId,
                branch_id: this.branchId,
                catalog_id: catalogId,
            });
        }
        await this._bulkDelete.run({ flow_id: this.flowId, node_ids: [nodeId] });
        (this._editor.removeNode({ nodeId }) as any);
    }

    _onDuplicateNode(e: CustomEvent) {
        const { nodeId } = isPlainObject(e.detail) ? e.detail : {};
        if (typeof nodeId !== 'string' || !nodeId) return;
        const state = this._editor.state;
        const skillsData = state?.branchData;
        const nodes = (skillsData as Record<string, any>)?.nodes;
        if (!nodes || !nodes[nodeId]) return;
        const baseId = `${nodeId}_copy`;
        let newId = baseId;
        let suffix = 1;
        while (newId in nodes) {
            suffix += 1;
            newId = `${baseId}_${suffix}`;
        }
        const source = nodes[nodeId];
        const copy = JSON.parse(JSON.stringify(source));
        copy.node_id = newId;
        if (typeof copy.name === 'string') copy.name = `${copy.name} copy`;
        if (copy.position && typeof copy.position === 'object') {
            copy.position = {
                x: asNumber(copy.position.x) + 40,
                y: asNumber(copy.position.y) + 40,
            };
        }
        if (copy.type === 'code_agent') {
            const fromCatalogId = typeof copy.catalog_id === 'string' ? copy.catalog_id : '';
            delete copy.catalog_id;
            if (fromCatalogId.length > 0 && this.flowId) {
                void this._codeAgentCopyTree.run({
                    flow_id: this.flowId,
                    node_id: newId,
                    branch_id: this.branchId,
                    from_catalog_id: fromCatalogId,
                }).then((ensured: any) => {
                    if (!ensured || typeof ensured.catalog_id !== 'string' || ensured.catalog_id.length === 0) {
                        throw new Error('flows-property-panel: copy-tree must return catalog_id');
                    }
                    const latestState = this._editor.state;
                    const latestData = latestState?.branchData;
                    const latestNodes = (latestData as Record<string, any>)?.nodes;
                    if (!latestNodes || !latestNodes[newId]) {
                        throw new Error(`flows-property-panel: code_agent copy missing after copy-tree: ${newId}`);
                    }
                    const nextNodes = { ...latestNodes, [newId]: { ...latestNodes[newId], catalog_id: ensured.catalog_id } };
                    const nextLatest = { ...latestData, nodes: nextNodes };
                    (this._editor.updateBranchData({ data: nextLatest }) as any);
                    (this._editor.setDirty({ dirty: true }) as any);
                });
            }
        }
        const nextNodes = { ...nodes, [newId]: copy };
        const nextData = { ...skillsData, nodes: nextNodes };
        (this._editor.updateBranchData({ data: nextData }) as any);
        (this._editor.setDirty({ dirty: true }) as any);
        (this._editor.pushHistory({ snapshot: nextData }) as any);
        (this._editor.selectNode({ nodeId: newId }) as any);
    }

    _renderEditor(node: any, nodeId: string) {
        const state = asObject(this._editor.state);
        const skillsData = isPlainObject((state as any).branchData) ? (state as any).branchData : {};
        const flowVariables = skillsData.variables && typeof skillsData.variables === 'object' ? skillsData.variables : {};
        const graphNodes = skillsData.nodes && typeof skillsData.nodes === 'object'
            ? Object.entries(skillsData.nodes).map(([id, n]) => ({ id, name: typeof (n as Record<string, any>)?.name === 'string' && (n as Record<string, any>).name.length > 0 ? (n as Record<string, any>).name : id, type: asString((n as Record<string, any>)?.type) }))
            : [];
        const previewExecutionState = (state as any).previewExecutionState;
        const dataflowNode = isPlainObject((state as any).dataflow?.nodes?.[nodeId]) ? (state as any).dataflow.nodes[nodeId] : null;
        return renderFlowsNodeEditorSurface({
            node,
            nodeId,
            flowId: this.flowId,
            branchId: this.branchId,
            flowVariables,
            graphNodes,
            previewExecutionState,
            dataflowNode,
            embedded: false,
            focusMode: this.focusMode === true,
            focusSection: typeof this.focusSection === 'string' && this.focusSection.length > 0
                ? this.focusSection
                : 'prompt',
            onChange: (e: CustomEvent) => this._onChange(e),
            onDelete: (e: CustomEvent) => this._onDeleteNode(e),
            onDuplicate: (e: CustomEvent) => this._onDuplicateNode(e),
        });
    }

    override render(): TemplateResult {
        const state = asObject(this._editor.state);
        const nodeId = typeof this.nodeId === 'string' && this.nodeId.length > 0
            ? this.nodeId
            : (state as any).selectedNodeId;
        if (!nodeId) {
            return html`
                <div style="padding: var(--space-3); color: var(--text-tertiary)">${this.t('property_panel.select_node')}</div>
            `;
        }
        const skillsData = isPlainObject((state as any).branchData) ? (state as any).branchData : { nodes: {} };
        const node = skillsData.nodes?.[nodeId];
        if (!node) return html`<div></div>`;
        const isInherited = asArray((state as any).inheritedNodeIds).includes(nodeId);
        return html`
            ${isInherited ? html`
                <div class="inherited-banner">
                    <span class="badge">↑</span>
                    <span>${this.t('property_panel.inherited_hint')}</span>
                </div>
            ` : ''}
            ${this._renderEditor(node, nodeId)}
        `;
    }
}

customElements.define('flows-property-panel', FlowsPropertyPanel);
