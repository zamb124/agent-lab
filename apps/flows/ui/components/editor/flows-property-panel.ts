/**
 * flows-property-panel — слот для активного редактора ноды.
 *
 * Читает selectedNodeId, skillsData, variables, previewExecutionState из
 * useOp('flows/editor'). Маршрутизирует по `node.type` (NodeType enum).
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
import { asNumber, asString, isPlainObject } from '../../_helpers/flows-resolvers.js';
import type {CSSResultGroup, PropertyDeclarations, TemplateResult} from 'lit';

function nodeMap(skillsData: unknown): Record<string, unknown> {
    if (!isPlainObject(skillsData)) {
        return {};
    }
    return isPlainObject(skillsData.nodes) ? skillsData.nodes : {};
}

function nodeLabel(id: string, node: unknown): { id: string; name: string; type: string } {
    if (!isPlainObject(node)) {
        return { id, name: id, type: asString(undefined) };
    }
    const nameValue = node.name;
    const name = typeof nameValue === 'string' && nameValue.length > 0 ? nameValue : id;
    return { id, name, type: asString(node.type) };
}

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
                background: var(--accent-subtle);
                border: 1px dashed var(--accent);
                border-radius: var(--radius-sm);
                color: var(--text-secondary);
                font-size: var(--text-sm);
                line-height: 1.4;
                display: flex;
                gap: var(--space-2);
                align-items: flex-start;
            }
            .inherited-banner .badge {
                color: var(--accent);
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
        const detail = isPlainObject(e.detail) ? e.detail : null;
        if (detail === null) return;
        const nodeId = detail.nodeId;
        const patch = isPlainObject(detail.patch) ? detail.patch : null;
        if (typeof nodeId !== 'string' || nodeId.length === 0 || patch === null) return;
        const skillsData = isPlainObject(this._editor.state.branchData) ? this._editor.state.branchData : null;
        if (skillsData === null) return;
        const nodes = nodeMap(skillsData);
        const node = nodes[nodeId];
        if (!isPlainObject(node)) return;
        const normalizedPatch: Record<string, unknown> = { ...patch };
        if (Object.prototype.hasOwnProperty.call(normalizedPatch, 'llm_override')) {
            if (!Object.prototype.hasOwnProperty.call(normalizedPatch, 'llm')) {
                normalizedPatch.llm = normalizedPatch.llm_override;
            }
            delete normalizedPatch.llm_override;
        }
        const nextNode: Record<string, unknown> = { ...node, ...normalizedPatch };
        const patchHasLlm = Object.prototype.hasOwnProperty.call(normalizedPatch, 'llm');
        if (
            !patchHasLlm
            && isPlainObject(nextNode.llm_override)
        ) {
            nextNode.llm = { ...nextNode.llm_override };
        }
        delete nextNode.llm_override;
        nodes[nodeId] = nextNode;
        const nextData = { ...skillsData, nodes };
        this._editor.updateBranchData({ data: nextData });
        this._editor.setDirty({ dirty: true });
        this._editor.pushHistory({ snapshot: nextData });
    }

    async _onDeleteNode(e: CustomEvent) {
        const { nodeId } = isPlainObject(e.detail) ? e.detail : {};
        if (typeof nodeId !== 'string' || !nodeId) return;
        if (!this.flowId) return;
        const skillsData = this._editor.state.branchData;
        const node = nodeMap(skillsData)[nodeId];
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
        this._editor.removeNode({ nodeId });
    }

    _onDuplicateNode(e: CustomEvent) {
        const { nodeId } = isPlainObject(e.detail) ? e.detail : {};
        if (typeof nodeId !== 'string' || !nodeId) return;
        const branchData = isPlainObject(this._editor.state.branchData) ? this._editor.state.branchData : null;
        if (branchData === null) return;
        const nodes = nodeMap(branchData);
        if (!nodes[nodeId]) return;
        const baseId = `${nodeId}_copy`;
        let newId = baseId;
        let suffix = 1;
        while (newId in nodes) {
            suffix += 1;
            newId = `${baseId}_${suffix}`;
        }
        const source = nodes[nodeId];
        if (!isPlainObject(source)) return;
        const parsed: unknown = JSON.parse(JSON.stringify(source));
        if (!isPlainObject(parsed)) {
            throw new Error('flows-property-panel: node copy required');
        }
        const copy = parsed;
        copy.node_id = newId;
        if (typeof copy.name === 'string') copy.name = `${copy.name} copy`;
        if (isPlainObject(copy.position)) {
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
                }).then((ensured) => {
                    if (!isPlainObject(ensured) || typeof ensured.catalog_id !== 'string' || ensured.catalog_id.length === 0) {
                        throw new Error('flows-property-panel: copy-tree must return catalog_id');
                    }
                    const latestData = isPlainObject(this._editor.state.branchData) ? this._editor.state.branchData : null;
                    if (latestData === null) {
                        throw new Error(`flows-property-panel: code_agent copy missing after copy-tree: ${newId}`);
                    }
                    const latestNodes = nodeMap(latestData);
                    const current = latestNodes[newId];
                    if (!isPlainObject(current)) {
                        throw new Error(`flows-property-panel: code_agent copy missing after copy-tree: ${newId}`);
                    }
                    const nextNodes = { ...latestNodes, [newId]: { ...current, catalog_id: ensured.catalog_id } };
                    const nextLatest = { ...latestData, nodes: nextNodes };
                    this._editor.updateBranchData({ data: nextLatest });
                    this._editor.setDirty({ dirty: true });
                });
            }
        }
        const nextNodes = { ...nodes, [newId]: copy };
        const nextData = { ...branchData, nodes: nextNodes };
        this._editor.updateBranchData({ data: nextData });
        this._editor.setDirty({ dirty: true });
        this._editor.pushHistory({ snapshot: nextData });
        this._editor.selectNode({ nodeId: newId });
    }

    _renderEditor(node: Record<string, unknown>, nodeId: string) {
        const branchData = isPlainObject(this._editor.state.branchData) ? this._editor.state.branchData : null;
        const skillsData: Record<string, unknown> = branchData === null ? {} : branchData;
        const variables = isPlainObject(skillsData.variables) ? skillsData.variables : null;
        const flowVariables = variables === null ? {} : variables;
        const nodes = isPlainObject(skillsData.nodes) ? skillsData.nodes : null;
        const graphNodes = nodes === null ? [] : Object.entries(nodes).map(([id, nodeRecord]) => nodeLabel(id, nodeRecord));
        const previewExecutionState = this._editor.state.previewExecutionState;
        const dataflow = this._editor.state.dataflow;
        const dataflowNodes = isPlainObject(dataflow) && isPlainObject(dataflow.nodes) ? dataflow.nodes : null;
        const dataflowNode = dataflowNodes !== null && isPlainObject(dataflowNodes[nodeId])
            ? dataflowNodes[nodeId]
            : null;
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
        const selectedNodeId = this._editor.state.selectedNodeId;
        const nodeId = typeof this.nodeId === 'string' && this.nodeId.length > 0
            ? this.nodeId
            : (typeof selectedNodeId === 'string' ? selectedNodeId : '');
        if (nodeId.length === 0) {
            return html`
                <div style="padding: var(--space-3); color: var(--text-tertiary)">${this.t('property_panel.select_node')}</div>
            `;
        }
        const branchData = this._editor.state.branchData;
        const skillsData = isPlainObject(branchData) ? branchData : null;
        const nodes = skillsData !== null && isPlainObject(skillsData.nodes) ? skillsData.nodes : null;
        const node = nodes !== null ? nodes[nodeId] : undefined;
        if (!isPlainObject(node)) return html`<div></div>`;
        const inheritedNodeIds = this._editor.state.inheritedNodeIds;
        const isInherited = Array.isArray(inheritedNodeIds) && inheritedNodeIds.includes(nodeId);
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
