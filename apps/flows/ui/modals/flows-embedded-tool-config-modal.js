/**
 * Редактирование inline/реестр tool в LLM: тот же набор полей, что у standalone-ноды.
 * Редактор внутри модалки всегда с expanded: master-detail как у развёрнутой панели свойств,
 * а не от глобального panelExpanded (иначе при узкой панели вложенная нода оставалась в compact).
 */

import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';
import { renderFlowsNodeEditorSurface } from '../components/editor/flows-node-editor-surface.js';
import { asObject, isPlainObject, asString } from '../_helpers/flows-resolvers.js';
import {
    normalizeToolRef,
    toolRefNeedsRegistryFetch,
    toolRefToInitialNode,
    registryToolItemToNode,
    nodeConfigToToolRef,
} from '../_helpers/flows-tool-ref.js';

export class FlowsEmbeddedToolConfigModal extends PlatformFormModal {
    static modalKind = 'flows.embedded_tool_config';
    static i18nNamespace = 'flows';

    static properties = {
        ...PlatformFormModal.properties,
        onSave: { type: Object, attribute: false },
        toolRef: { type: Object, attribute: false },
        flowId: { type: String, attribute: false },
        branchId: { type: String, attribute: false },
        _node: { state: true },
        _loadPhase: { state: true },
        _registryToolId: { state: true },
    };

    static styles = [
        ...(PlatformFormModal.styles ? [PlatformFormModal.styles] : []),
        css`
            .body-wrap {
                box-sizing: border-box;
                width: 100%;
                min-width: 0;
                min-height: 240px;
                max-height: min(90vh, 1400px);
                overflow: auto;
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

    constructor() {
        super();
        this.size = 'full';
        this.headerSavePrimary = true;
        this.onSave = null;
        this.toolRef = null;
        this.flowId = '';
        this.branchId = 'base';
        this._node = null;
        this._loadPhase = 'idle';
        this._registryToolId = null;
        this._editor = this.useOp('flows/editor');
        this._tools = this.useResource('flows/tools');
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

    _graphNodesList() {
        const st = asObject(this._editor.state);
        const skillsData = isPlainObject(st.branchData) ? st.branchData : {};
        const raw = isPlainObject(skillsData.nodes) ? skillsData.nodes : {};
        return Object.entries(raw).map(([id, n]) => ({
            id,
            name: typeof n.name === 'string' && n.name.length > 0 ? n.name : id,
            type: asString(n.type),
        }));
    }

    willUpdate(c) {
        if ((c.has('open') && this.open) || (c.has('toolRef') && this.open)) {
            this._syncFromProps();
        }
        super.willUpdate(c);
    }

    _syncFromProps() {
        if (this.open !== true) {
            return;
        }
        this._loadPhase = 'idle';
        this._registryToolId = null;
        this._node = null;
        if (this.toolRef === null || this.toolRef === undefined) {
            this._loadPhase = 'error';
            return;
        }
        const { tool_id: toolId, raw } = normalizeToolRef(this.toolRef);
        const st = asObject(this._editor.state);
        const skillsData = isPlainObject(st.branchData) ? st.branchData : {};
        const graphNodes = isPlainObject(skillsData.nodes) ? skillsData.nodes : {};
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
        this._loadPhase = 'ready';
    }

    updated(changed) {
        super.updated(changed);
        if (this._loadPhase === 'loading' && this._registryToolId) {
            const byId = this._tools.byId;
            const item = byId && isPlainObject(byId) ? byId[this._registryToolId] : null;
            if (item) {
                this._node = registryToolItemToNode(item);
                this._loadPhase = 'ready';
                this._registryToolId = null;
            }
        }
    }

    _onNodeChange(e) {
        if (!e.detail) return;
        const nodeId = e.detail.nodeId;
        const patch = e.detail.patch;
        if (typeof nodeId !== 'string' || !isPlainObject(patch)) return;
        const n = asObject(this._node);
        if (n === null) return;
        this._node = { ...n, ...patch };
        this.isDirty = true;
    }

    _noopNode() {
        this.toast('flows:embedded_tool_config.toast_cannot_delete', { type: 'info' });
    }

    _save() {
        if (this._node === null) return;
        const ref = nodeConfigToToolRef(this._node);
        if (typeof this.onSave === 'function') {
            this.onSave(ref);
        }
        this.closeAfterSave();
    }

    renderHeaderActions() {
        return html`<span class="embedded-tool-run-host" aria-hidden="true"></span>`;
    }

    renderSaveHeaderButton() {
        const canSave = this._loadPhase === 'ready' && this._node !== null;
        return this._renderHeaderSaveIcon({
            onClick: () => this._save(),
            disabled: this.loading || !canSave,
            title: this.loading
                ? (this.t('modal.saving') || 'modal.saving')
                : (this.t('modal.save') || 'modal.save'),
        });
    }

    async handleSubmit() {
        this._save();
    }

    renderHeader() {
        return this.t('embedded_tool_config.title');
    }

    renderBody() {
        if (this._loadPhase === 'loading' || this._loadPhase === 'idle') {
            return html`<div class="body-wrap">${this.t('embedded_tool_config.loading')}</div>`;
        }
        if (this._loadPhase === 'error' || this._node === null) {
            return html`<div class="body-wrap">${this.t('embedded_tool_config.error')}</div>`;
        }
        const st = asObject(this._editor.state);
        const skillsData = isPlainObject(st.branchData) ? st.branchData : {};
        const flowVariables = isPlainObject(skillsData.variables) ? skillsData.variables : {};
        const node = asObject(this._node);
        const id = asString(node.node_id);
        const ed = renderFlowsNodeEditorSurface({
            node,
            nodeId: id,
            flowId: this.flowId,
            branchId: this.branchId,
            flowVariables,
            graphNodes: this._graphNodesList(),
            previewExecutionState: st.previewExecutionState,
            expanded: true,
            embedded: true,
            onChange: (e) => this._onNodeChange(e),
            onDelete: (e) => this._noopNode(e),
            onDuplicate: (e) => this._noopNode(e),
        });
        return html`<div class="body-wrap">${ed}</div>`;
    }

    renderFooter() {
        return html``;
    }
}

customElements.define('flows-embedded-tool-config-modal', FlowsEmbeddedToolConfigModal);
registerModalKind(FlowsEmbeddedToolConfigModal.modalKind, 'flows-embedded-tool-config-modal');
