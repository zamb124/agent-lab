/**
 * Модалка редактора ноды (`renderFlowsNodeEditorSurface` / llm_node и др.):
 * - toolRef → inline/registry tool в LLM (callback onSave(toolRef));
 * - nodeId → llm_node (и др.) в FlowConfig через flows/flow_update.
 */

import type { OpController, ResourceController, ControllerFor } from '@platform/lib/base/use-resource.js';
import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-spinner.js';
import { renderFlowsNodeEditorSurface } from '../components/editor/flows-node-editor-surface.js';
import {
    effectiveFlowNodesMap,
    flowBodyWithNode,
} from '../_helpers/evaluation-flow-nodes.js';
import { isPlainObject, asString } from '../_helpers/flows-resolvers.js';
import type {CSSResultGroup, PropertyDeclarations, PropertyValues} from 'lit';
import {
    normalizeToolRef,
    toolRefNeedsRegistryFetch,
    toolRefToInitialNode,
    registryToolItemToNode,
    nodeConfigToToolRef,
    replaceToolRefInToolsList,
} from '../_helpers/flows-tool-ref.js';

export class FlowsEmbeddedToolConfigModal extends PlatformFormModal {
    static modalKind = 'flows.embedded_tool_config';
    static i18nNamespace = 'flows';

    static override properties: PropertyDeclarations = {
        ...PlatformFormModal.properties,
        onSave: { type: Object, attribute: false },
        onSaved: { attribute: false },
        toolRef: { type: Object, attribute: false },
        nodeId: { type: String, attribute: false },
        /** llm_node id — Save toolRef пишет прямо в editor.branchData.nodes[hostNodeId].tools */
        hostNodeId: { type: String, attribute: false },
        flowId: { type: String, attribute: false },
        branchId: { type: String, attribute: false },
        focusMode: { type: Boolean, attribute: false },
        _node: { state: true },
        _loadPhase: { state: true },
        _registryToolId: { state: true },
        _flowSnapshot: { state: true },
        _editorNodeId: { state: true },
    }
    declare onSave: ((toolRef: Record<string, unknown>) => void) | null;
    declare onSaved: ((saved: { flow_id: string; node_id: string }) => void) | null;
    declare toolRef: Record<string, unknown> | null;
    declare nodeId: string;
    declare hostNodeId: string;
    declare flowId: string;
    declare branchId: string;
    declare focusMode: boolean;
    declare _node: Record<string, unknown> | null;
    declare _loadPhase: string;
    declare _registryToolId: string | null;
    declare _flowSnapshot: Record<string, unknown> | null;
    declare _editorNodeId: string;
;

    static override styles: CSSResultGroup = [
        ...(PlatformFormModal.styles ? [PlatformFormModal.styles] : []),
        css`
            .body-wrap {
                box-sizing: border-box;
                width: 100%;
                min-width: 0;
                flex: 1 1 auto;
                min-height: 0;
                height: 100%;
                display: flex;
                flex-direction: column;
                overflow: hidden;
                padding: var(--space-3);
            }
            .body-wrap > * {
                flex: 1 1 auto;
                min-width: 0;
                min-height: 0;
                height: 100%;
                width: 100%;
            }
            .embedded-tool-run-host {
                display: inline-flex;
                align-items: center;
            }
            /* Как у flows-floating-panel: без лишней высоты от text-xl + вложенного h3. */
            .modal-header {
                padding: var(--space-3) var(--space-4) var(--space-2) var(--space-4);
                gap: var(--space-2);
            }
            .modal-title {
                font-size: var(--text-base);
                font-weight: var(--font-semibold);
                line-height: 1.3;
            }
        `,
    ];
    private _editor: ControllerFor<'flows/editor'>;
    private _tools: ResourceController;
    private _flows: ResourceController;
    private _flowUpdate: OpController;

    constructor() {
        super();
        this.size = 'full';
        this.headerSavePrimary = true;
        this.onSave = null;
        this.onSaved = null;
        this.toolRef = null;
        this.nodeId = '';
        this.hostNodeId = '';
        this.flowId = '';
        this.branchId = 'base';
        this.focusMode = false;
        this._node = null;
        this._loadPhase = 'idle';
        this._registryToolId = null;
        this._flowSnapshot = null;
        this._editorNodeId = '';
        this._editor = this.useOp('flows/editor');
        this._tools = this.useResource('flows/tools');
        this._flows = this.useResource('flows/flows');
        this._flowUpdate = this.useOp('flows/flow_update');
        this.useEvent('flows/tools/item_failed', (ev) => {
            const p = ev.payload;
            if (!isPlainObject(p)) {
                return;
            }
            const id = p.tool_id;
            if (typeof id !== 'string' || id.length === 0) {
                return;
            }
            if (this._registryToolId === id) {
                this._loadPhase = 'error';
                this._registryToolId = null;
                this.requestUpdate();
            }
        });
    }

    _isFlowNodeMode() {
        if (this.toolRef !== null && this.toolRef !== undefined) {
            return false;
        }
        return asString(this.nodeId).trim().length > 0;
    }

    _graphNodeRow(id: string, node: unknown): { id: string; name: string; type: string } {
        if (!isPlainObject(node)) {
            throw new Error(`flows-embedded-tool-config-modal: graph node required: ${id}`);
        }
        const name = node.name;
        return {
            id,
            name: typeof name === 'string' && name.length > 0 ? name : id,
            type: asString(node.type),
        };
    }

    _editorBranchData(): Record<string, unknown> | null {
        const branchData = this._editor.state.branchData;
        return isPlainObject(branchData) ? branchData : null;
    }

    _graphNodesList() {
        if (this._isFlowNodeMode()) {
            const flow = isPlainObject(this._flowSnapshot) ? this._flowSnapshot : null;
            if (flow === null) {
                return [];
            }
            const nodes = effectiveFlowNodesMap(flow, asString(this.branchId));
            return Object.entries(nodes).map(([id, node]) => this._graphNodeRow(id, node));
        }
        const branchData = this._editorBranchData();
        if (branchData === null) {
            return [];
        }
        const raw = isPlainObject(branchData.nodes) ? branchData.nodes : {};
        return Object.entries(raw).map(([id, node]) => this._graphNodeRow(id, node));
    }

    _flowVariables() {
        if (this._isFlowNodeMode()) {
            const flow = isPlainObject(this._flowSnapshot) ? this._flowSnapshot : null;
            if (flow === null) {
                return {};
            }
            const variables = flow.variables;
            return isPlainObject(variables) ? variables : {};
        }
        const branchData = this._editorBranchData();
        if (branchData === null) {
            return {};
        }
        return isPlainObject(branchData.variables) ? branchData.variables : {};
    }

    override willUpdate(c: PropertyValues<this>): void {
        if (
            (c.has('open') && this.open)
            || (c.has('toolRef') && this.open)
            || (c.has('nodeId') && this.open)
            || (c.has('flowId') && this.open)
            || (c.has('branchId') && this.open)
        ) {
            void this._syncFromProps();
        }
        super.willUpdate(c);
    }

    async _syncFromProps() {
        if (this.open !== true) {
            return;
        }
        this._loadPhase = 'idle';
        this._registryToolId = null;
        this._node = null;
        this._flowSnapshot = null;
        this._editorNodeId = '';
        this.isDirty = false;

        if (this._isFlowNodeMode()) {
            await this._syncFlowNode();
            return;
        }

        if (this.toolRef === null || this.toolRef === undefined) {
            this._loadPhase = 'error';
            return;
        }
        const { tool_id: toolId, raw } = normalizeToolRef(this.toolRef);
        const branchData = this._editorBranchData();
        const graphNodes = branchData !== null && isPlainObject(branchData.nodes) ? branchData.nodes : {};
        if (graphNodes[toolId] !== undefined) {
            this._loadPhase = 'error';
            return;
        }
        if (toolRefNeedsRegistryFetch(raw)) {
            this._registryToolId = toolId;
            this._loadPhase = 'loading';
            this._tools.get(toolId);
            return;
        }
        this._node = toolRefToInitialNode(raw, toolId);
        this._editorNodeId = toolId;
        this._loadPhase = 'ready';
    }

    async _syncFlowNode() {
        const flowId = asString(this.flowId).trim();
        const nodeId = asString(this.nodeId).trim();
        if (flowId.length === 0 || nodeId.length === 0) {
            this._loadPhase = 'error';
            return;
        }
        this._loadPhase = 'loading';
        let flow = this._flows.byId[flowId];
        if (!isPlainObject(flow)) {
            flow = await this._flows.fetchItem(flowId);
        }
        if (!isPlainObject(flow)) {
            this._loadPhase = 'error';
            return;
        }
        const nodes = effectiveFlowNodesMap(flow, asString(this.branchId));
        const raw = nodes[nodeId];
        if (!isPlainObject(raw)) {
            this._loadPhase = 'error';
            return;
        }
        this._flowSnapshot = flow;
        this._editorNodeId = nodeId;
        this._node = { ...raw, node_id: nodeId };
        this._loadPhase = 'ready';
    }

    override updated(changed: PropertyValues<this>): void {
        super.updated(changed);
        if (this._loadPhase === 'loading' && this._registryToolId) {
            const byId = this._tools.byId;
            const item = byId && isPlainObject(byId) ? byId[this._registryToolId] : null;
            if (item) {
                const base = registryToolItemToNode(item);
                if (!isPlainObject(base)) {
                    throw new Error('flows-embedded-tool-config-modal: registry tool node required');
                }
                const merged: Record<string, unknown> = { ...base };
                const raw = isPlainObject(this.toolRef) ? this.toolRef : null;
                if (raw !== null) {
                    if (isPlainObject(raw.input_mapping)) {
                        merged.input_mapping = raw.input_mapping;
                    }
                    if (isPlainObject(raw.output_mapping)) {
                        merged.output_mapping = raw.output_mapping;
                    }
                    if (isPlainObject(raw.state_mapping)) {
                        merged.state_mapping = raw.state_mapping;
                    }
                }
                this._node = merged;
                this._editorNodeId = this._registryToolId;
                this._loadPhase = 'ready';
                this._registryToolId = null;
            }
        }
    }

    _onNodeChange(e: CustomEvent) {
        if (!e.detail) return;
        const patch = e.detail.patch;
        if (!isPlainObject(patch)) return;
        const node = this._node;
        if (!isPlainObject(node)) {
            return;
        }
        const normalizedPatch: Record<string, unknown> = { ...patch };
        if (Object.prototype.hasOwnProperty.call(normalizedPatch, 'llm_override')) {
            if (!Object.prototype.hasOwnProperty.call(normalizedPatch, 'llm')) {
                normalizedPatch.llm = normalizedPatch.llm_override;
            }
            delete normalizedPatch.llm_override;
        }
        const nextNode: Record<string, unknown> = { ...node, ...normalizedPatch };
        if (
            !Object.prototype.hasOwnProperty.call(normalizedPatch, 'llm')
            && isPlainObject(nextNode.llm_override)
        ) {
            nextNode.llm = { ...nextNode.llm_override };
        }
        delete nextNode.llm_override;
        this._node = nextNode;
        this.isDirty = true;
    }

    _noopNode() {
        this.toast('flows:embedded_tool_config.toast_cannot_delete', { type: 'info' });
    }

    _persistableFlowNodeConfig() {
        const node = this._node;
        if (!isPlainObject(node)) {
            throw new Error('flows-embedded-tool-config-modal: node draft required');
        }
        const persist = { ...node };
        delete persist.node_id;
        delete persist.llm_override;
        return persist;
    }

    async _saveFlowNode() {
        if (this._loadPhase !== 'ready' || this._node === null) {
            return;
        }
        this._flushMappingEditorsIntoNode();
        const flowId = asString(this.flowId).trim();
        const nodeId = asString(this.nodeId).trim();
        let flow = isPlainObject(this._flowSnapshot) ? this._flowSnapshot : this._flows.byId[flowId];
        if (!isPlainObject(flow)) {
            flow = await this._flows.fetchItem(flowId);
        }
        if (!isPlainObject(flow)) {
            this.toast('evaluation.toast.flow_required', { type: 'error' });
            return;
        }
        const body = flowBodyWithNode(
            flow,
            asString(this.branchId),
            nodeId,
            this._persistableFlowNodeConfig(),
        );
        await this._flowUpdate.run({ ...body, flow_id: flowId });
        await this._flows.fetchItem(flowId);
        if (typeof this.onSaved === 'function') {
            this.onSaved({ flow_id: flowId, node_id: nodeId });
        }
        this.closeAfterSave();
    }

    _commitToolRefToHostNode(ref: Record<string, unknown>) {
        const hostNodeId = asString(this.hostNodeId).trim();
        if (hostNodeId.length === 0) {
            throw new Error('flows-embedded-tool-config-modal: hostNodeId required');
        }
        const branchData = this._editorBranchData();
        if (branchData === null || !isPlainObject(branchData.nodes)) {
            throw new Error('flows-embedded-tool-config-modal: editor branchData.nodes required');
        }
        const hostNode = branchData.nodes[hostNodeId];
        if (!isPlainObject(hostNode)) {
            throw new Error(`flows-embedded-tool-config-modal: host node not found: ${hostNodeId}`);
        }
        const nextTools = replaceToolRefInToolsList(hostNode.tools, ref);
        const nodes = {
            ...branchData.nodes,
            [hostNodeId]: { ...hostNode, tools: nextTools },
        };
        const nextData = { ...branchData, nodes };
        this._editor.updateBranchData({ data: nextData });
        this._editor.setDirty({ dirty: true });
        this._editor.pushHistory({ snapshot: nextData });
    }

    /**
     * Mapping editor держит строки локально; если DOM-change не дошёл до _node —
     * перед Save забираем mapping напрямую из редактора.
     */
    _flushMappingEditorsIntoNode() {
        const root = this.renderRoot;
        const editors: Element[] = [];
        const collect = (node: ParentNode) => {
            node.querySelectorAll('flows-state-mapping-editor').forEach((el) => {
                editors.push(el);
            });
            node.querySelectorAll('*').forEach((el) => {
                if (el.shadowRoot !== null) {
                    collect(el.shadowRoot);
                }
            });
        };
        collect(root);
        if (editors.length === 0) {
            return;
        }
        const node = this._node;
        if (!isPlainObject(node)) {
            return;
        }
        let next: Record<string, unknown> = { ...node };
        let changed = false;
        for (const editor of editors) {
            if (!('getMapping' in editor) || typeof editor.getMapping !== 'function') {
                continue;
            }
            const mapping = editor.getMapping();
            if (!isPlainObject(mapping)) {
                continue;
            }
            const kind = 'kind' in editor && typeof editor.kind === 'string' ? editor.kind : '';
            if (kind === 'output') {
                const nodeType = asString(next.type);
                const field = nodeType === 'mcp' || nodeType === 'external_api'
                    ? 'state_mapping'
                    : 'output_mapping';
                next = { ...next, [field]: mapping };
                changed = true;
            } else {
                next = { ...next, input_mapping: mapping };
                changed = true;
            }
        }
        if (changed) {
            this._node = next;
            this.isDirty = true;
        }
    }

    _saveToolRef() {
        if (this._node === null) return;
        this._flushMappingEditorsIntoNode();
        const ref = nodeConfigToToolRef(this._node);
        if (!isPlainObject(ref)) {
            throw new Error('flows-embedded-tool-config-modal: tool ref required');
        }
        const hostNodeId = asString(this.hostNodeId).trim();
        if (hostNodeId.length > 0) {
            this._commitToolRefToHostNode(ref);
        } else if (typeof this.onSave === 'function') {
            this.onSave(ref);
        }
        this.closeAfterSave();
    }

    async _save() {
        if (this._isFlowNodeMode()) {
            await this._saveFlowNode();
            return;
        }
        this._saveToolRef();
    }

    override renderHeaderActions() {
        return html`<span class="embedded-tool-run-host" aria-hidden="true"></span>`;
    }

    override renderSaveHeaderButton() {
        const canSave = this._loadPhase === 'ready' && this._node !== null;
        const busy = this.loading || this._flowUpdate.busy;
        return this._renderHeaderSaveIcon({
            onClick: () => { void this._save(); },
            disabled: busy || !canSave,
            title: busy
                ? this.t('modal.saving')
                : this.t('modal.save'),
        });
    }

    override async handleSubmit() {
        await this._save();
    }

    override renderHeader() {
        if (this._isFlowNodeMode()) {
            const node = this._node;
            const name = node !== null && typeof node.name === 'string' && node.name.length > 0
                ? node.name
                : '';
            if (typeof name === 'string' && name.length > 0) {
                return name;
            }
            return this.t('embedded_tool_config.title_flow_node');
        }
        return this.t('embedded_tool_config.title');
    }

    override renderBody() {
        if (this._loadPhase === 'loading' || this._loadPhase === 'idle') {
            return html`<div class="body-wrap graph-modal-body"><platform-spinner></platform-spinner></div>`;
        }
        const node = this._node;
        if (this._loadPhase === 'error' || node === null) {
            return html`<div class="body-wrap graph-modal-body">${this.t('embedded_tool_config.error')}</div>`;
        }
        const id = asString(this._editorNodeId);
        const ed = renderFlowsNodeEditorSurface({
            node,
            nodeId: id,
            flowId: this.flowId,
            branchId: this.branchId,
            flowVariables: this._flowVariables(),
            graphNodes: this._graphNodesList(),
            previewExecutionState: this._isFlowNodeMode() ? null : this._editor.state.previewExecutionState,
            embedded: true,
            focusMode: this.focusMode === true,
            focusSection: 'prompt',
            onChange: (e: CustomEvent) => this._onNodeChange(e),
            onDelete: () => this._noopNode(),
            onDuplicate: () => this._noopNode(),
        });
        return html`<div class="body-wrap graph-modal-body">${ed}</div>`;
    }

    override renderFooter() {
        return html``;
    }
}

customElements.define('flows-embedded-tool-config-modal', FlowsEmbeddedToolConfigModal);
registerModalKind(FlowsEmbeddedToolConfigModal.modalKind, 'flows-embedded-tool-config-modal');
