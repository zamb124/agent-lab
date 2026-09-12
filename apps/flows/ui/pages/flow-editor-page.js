/**
 * FlowEditorPage — визуальный редактор flow.
 *
 * Макет (canvas, workspace logic и run):
 *   <flows-editor-header />          — chrome: actions + branch tabs
 *   .editor-shell:
 *     <flows-node-types-sidebar />    — drag-source типов нод
 *     .canvas-host:
 *       <flows-flow-canvas />
 *       <flows-bottom-toolbar />
 *       <flows-execution-panel />     — Test Run; workspace=run открывает панель
 *       <flows-floating-panel /> — chrome property/resource panel (drag, resize, collapse)
 *     .editor-right-rail:
 *       <flows-flow-property-panel /> — лимиты и речь (по кнопке в сайдбаре)
 *
 * Макет (agent focus, ровно 1 llm_node):
 *   header + <flows-agent-focus-studio /> вместо сайдбара/канвы
 *
 * Workspace interface — редактор Flow UI. Полноэкранный platform-flow-ui вместо
 * канвы в run запрещён: визуализация графа живёт на канве + панели.
 */

import { html, css, nothing } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { CoreEvents } from '@platform/lib/events/index.js';
import '@platform/lib/components/platform-breadcrumbs.js';
import '../components/editor/flows-editor-header.js';
import '../components/editor/flows-node-types-sidebar.js';
import '../components/editor/flows-flow-property-panel.js';
import '../components/editor/flows-property-panel.js';
import '../components/editor/flows-resource-property-panel.js';
import '../components/editor/flows-bottom-toolbar.js';
import '../components/editor/flows-execution-panel.js';
import '../components/editor/flows-floating-panel.js';
import '../components/editor/flows-node-ai-helper.js';
import '../components/flow-canvas/flows-flow-canvas.js';
import '../modals/flows-edge-condition-modal.js';
import '../modals/flows-incoming-policy-modal.js';
import '../modals/flows-variable-mapping-modal.js';
import '../modals/flows-library-picker-modal.js';
import '../modals/flows-tool-create-modal.js';
import '../modals/flows-agent-skill-picker-modal.js';
import '../modals/flows-embedded-tool-config-modal.js';
import '../modals/flows-code-node-drop-modal.js';
import '../modals/flows-code-modal.js';
import '../modals/flows-code-docs-modal.js';
import '../modals/flows-canvas-help-modal.js';
import '../modals/flows-api-console-modal.js';
import '../modals/flows-raw-json-modal.js';
import '../modals/flows-state-modal.js';
import '../modals/flows-node-run-result-modal.js';
import { getNodeTypeMeta, getCategoryToken } from '../constants/node-icons.js';
import { asArray, asObject, isPlainObject } from '../_helpers/flows-resolvers.js';
import {
    EDITOR_LAYOUT_AGENT,
    isAgentFocusEligible,
    writeEditorLayoutPreference,
} from '../_helpers/flow-editor-layout.js';
import '../components/editor/flows-agent-focus-studio.js';
import '../components/interface-editor/flows-interface-editor.js';
import '../modals/flows-interface-template-modal.js';
import '../modals/flows-interface-html-editor-modal.js';
import { saveEditorFlow } from '../_helpers/flow-editor-save.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';

function stableStringify(value) {
    if (value === null || typeof value !== 'object') return JSON.stringify(value);
    if (Array.isArray(value)) return `[${value.map(stableStringify).join(',')}]`;
    const keys = Object.keys(value).sort();
    return `{${keys.map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`).join(',')}}`;
}

export class FlowEditorPage extends PlatformPage {
    static properties = {
        flowId: { type: String, attribute: 'flow-id' },
        branchId: { type: String, attribute: 'branch-id' },
        _flowSettingsOpen: { state: true, type: Boolean },
        _nodeAiHelperOpen: { state: true, type: Boolean },
    };

    static styles = [
        PlatformPage.styles,
        css`
            :host {
                flex: 1; min-width: 0; min-height: 0;
                display: flex; flex-direction: column;
                background: var(--bg-elevated); overflow: hidden;
            }
            .editor-chrome {
                flex-shrink: 0;
                background: var(--glass-solid-medium);
                border-bottom: 1px solid var(--border-subtle);
                box-shadow: var(--glass-shadow-subtle);
            }
            .editor-breadcrumbs {
                padding: var(--space-2) var(--space-4) 0;
            }
            .editor-shell {
                flex: 1; min-height: 0;
                display: flex; position: relative;
            }
            .canvas-host {
                flex: 1;
                min-width: 0;
                position: relative;
                display: flex;
                flex-direction: column;
                /* Содержит z-index детей (тулбар 6, execution 5, property panel 20): иначе они бьются с rail (5)
                   на уровне .editor-shell и перекрывают модалку/развёрнутую панель справа. */
                isolation: isolate;
                z-index: 0;
            }
            .canvas-host > flows-floating-panel {
                z-index: 20;
            }
            .editor-right-rail {
                position: absolute;
                top: var(--space-3);
                right: var(--space-3);
                bottom: var(--space-3);
                width: 420px;
                z-index: 5;
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                pointer-events: none;
            }
            :host(.flow-settings-panel-open) .editor-right-rail {
                z-index: 92;
            }
            .editor-right-rail > * {
                pointer-events: auto;
            }
            .layout-toggle-float {
                position: absolute;
                top: var(--space-3);
                right: var(--space-3);
                z-index: 8;
                transition: transform 120ms ease;
            }
            .layout-toggle-float:active {
                transform: scale(0.94);
            }
            .agent-studio-host {
                flex: 1;
                min-width: 0;
                min-height: 0;
                display: flex;
                flex-direction: column;
                position: relative;
                isolation: isolate;
                z-index: 0;
            }
            .flow-settings-dismiss-layer {
                position: fixed;
                inset: 0;
                z-index: 90;
                background: transparent;
                cursor: default;
            }
            .flow-settings-dismiss-safe {
                position: relative;
                z-index: 91;
            }
            .interface-host { flex: 1; min-width: 0; min-height: 0; }
        `,
    ];

    constructor() {
        super();
        this.flowId = '';
        this.branchId = 'base';
        this._flowSettingsOpen = false;
        this._nodeAiHelperOpen = false;
        this._editor = this.useOp('flows/editor');
        this._flowUpdate = this.useOp('flows/flow_update');
        this._flows = this.useResource('flows/flows');
        this._editorStateOp = this.useOp('flows/code_editor_state');
        this._dataflowInspectOp = this.useOp('flows/dataflow_inspect');
        this._dataflowTimer = null;
        this._lastDataflowKey = '';
        this._pendingDataflowKey = '';
        this._dataflowSeq = 0;
        this.useEvent(CoreEvents.ROUTER_ROUTE_CHANGED, () => this._loadFlowIfNeeded());
        this.useEvent('flows/flows/item_loaded', (e) => {
            const item = e && e.payload && e.payload.item;
            if (item && item.flow_id === this.flowId) {
                this._applyFlow(item);
            }
        });
    }

    connectedCallback() {
        super.connectedCallback();
        this.classList.toggle('flow-settings-panel-open', Boolean(this._flowSettingsOpen));
        this._loadFlowIfNeeded();
    }

    disconnectedCallback() {
        if (this._dataflowTimer) {
            clearTimeout(this._dataflowTimer);
            this._dataflowTimer = null;
        }
        super.disconnectedCallback?.();
    }

    updated(changed) {
        super.updated?.(changed);
        if (changed.has('flowId')) {
            this._flowSettingsOpen = false;
        }
        if (changed.has('_flowSettingsOpen') || changed.has('flowId')) {
            this.classList.toggle('flow-settings-panel-open', Boolean(this._flowSettingsOpen));
        }
        if (changed.has('flowId') || changed.has('branchId')) {
            this._loadFlowIfNeeded();
        }
    }

    _onDismissFlowSettingsBackdrop() {
        this._flowSettingsOpen = false;
    }

    _loadFlowIfNeeded() {
        if (!this.flowId) return;
        const editorState = this._editor.state;
        if (editorState && editorState.flowId === this.flowId && editorState.currentBranchId === this.branchId) return;
        const cached = this._flows.byId && this._flows.byId[this.flowId];
        if (cached) {
            this._applyFlow(cached);
            return;
        }
        this._flows.get(this.flowId);
    }

    async _applyFlow(flow) {
        this._editor.setFlow({
            flow,
            branchId: this.branchId,
            previewExecutionState: null,
        });
        const apiBranch = (typeof this.branchId !== 'string' || this.branchId.length === 0 || this.branchId === 'base') ? 'default' : this.branchId;
        const previewExecutionState = await this._editorStateOp.run({
            flow_id: this.flowId,
            branch_id: apiBranch,
        });
        if (previewExecutionState !== null) {
            this._editor.setPreviewExecutionState({ snapshot: previewExecutionState });
        }
        this._scheduleDataflowRefresh(asObject(this._editor.state));
    }

    _buildDataflowPayload(state) {
        const branchData = isPlainObject(state.branchData) ? state.branchData : null;
        if (!branchData || !isPlainObject(branchData.nodes)) return null;
        const apiBranch = (typeof this.branchId !== 'string' || this.branchId.length === 0 || this.branchId === 'base')
            ? 'default'
            : this.branchId;
        const interfaceConfig = this._resolvedInterfaceConfig(state);
        return {
            flow_id: this.flowId || state.flowId || null,
            branch_id: apiBranch,
            entry: typeof branchData.entry === 'string' && branchData.entry.length > 0 ? branchData.entry : null,
            nodes: branchData.nodes,
            edges: Array.isArray(branchData.edges) ? branchData.edges : [],
            variables: isPlainObject(branchData.variables) ? branchData.variables : {},
            triggers: isPlainObject(state.flowConfig?.triggers) ? state.flowConfig.triggers : {},
            interface: isPlainObject(interfaceConfig) ? interfaceConfig : null,
            sample_state: isPlainObject(state.previewExecutionState) ? state.previewExecutionState : null,
            observed_runs: isPlainObject(state.dataflowObservations) ? state.dataflowObservations : {},
        };
    }

    _scheduleDataflowRefresh(state) {
        const payload = this._buildDataflowPayload(state);
        if (!payload) {
            if (state.dataflow) this._editor.setDataflow({ dataflow: null });
            return;
        }
        const key = stableStringify(payload);
        if (key === this._lastDataflowKey || key === this._pendingDataflowKey) return;
        this._pendingDataflowKey = key;
        if (this._dataflowTimer) clearTimeout(this._dataflowTimer);
        this._dataflowTimer = setTimeout(() => {
            this._dataflowTimer = null;
            void this._refreshDataflow(key, payload);
        }, 220);
    }

    async _refreshDataflow(key, payload) {
        const seq = ++this._dataflowSeq;
        try {
            const dataflow = await this._dataflowInspectOp.run(payload);
            if (seq !== this._dataflowSeq || key !== this._pendingDataflowKey) return;
            this._lastDataflowKey = key;
            this._pendingDataflowKey = '';
            this._editor.setDataflow({ dataflow });
        } catch {
            if (seq === this._dataflowSeq) {
                this._pendingDataflowKey = '';
            }
        }
    }

    _panelHeaderForNode(nodeId, state) {
        const branchData = isPlainObject(state.branchData) ? state.branchData : null;
        const nodes = branchData && isPlainObject(branchData.nodes) ? branchData.nodes : null;
        const node = nodes ? nodes[nodeId] : null;
        if (!node) {
            return null;
        }
        const meta = getNodeTypeMeta(node.type);
        const title = typeof node.name === 'string' && node.name.length > 0 ? node.name : nodeId;
        return {
            icon: meta.icon,
            title,
            colorToken: getCategoryToken(meta.category),
        };
    }

    _panelHeader() {
        const state = asObject(this._editor.state);
        if (state.selectedNodeId) {
            return this._panelHeaderForNode(state.selectedNodeId, state);
        }
        if (state.selectedResourceId) {
            const branchData = isPlainObject(state.branchData) ? state.branchData : null;
            const resources = branchData && isPlainObject(branchData.resources) ? branchData.resources : null;
            const resource = resources ? resources[state.selectedResourceId] : null;
            const title = resource && typeof resource.name === 'string' && resource.name.length > 0
                ? resource.name
                : state.selectedResourceId;
            return {
                icon: 'box',
                title,
                colorToken: getCategoryToken('flow'),
            };
        }
        return null;
    }

    _onToggleFlowSettings() {
        this._flowSettingsOpen = !this._flowSettingsOpen;
    }

    _onToggleNodeAiHelper() {
        const state = asObject(this._editor.state);
        if (!state.selectedNodeId) {
            return;
        }
        this._nodeAiHelperOpen = !this._nodeAiHelperOpen;
    }

    _onCloseFloatingPanel(nodeId) {
        if (typeof nodeId === 'string' && nodeId.length > 0) {
            if (this._nodeAiHelperOpen && asObject(this._editor.state).selectedNodeId === nodeId) {
                this._nodeAiHelperOpen = false;
            }
            this._editor.closePanel({ nodeId });
            return;
        }
        this._nodeAiHelperOpen = false;
        this._editor.closePanel({});
    }

    _onPanelLayoutChange(nodeId, e) {
        const layout = e.detail;
        if (!layout || typeof layout !== 'object') {
            return;
        }
        this._editor.setPropertyPanelLayout({ nodeId, layout });
    }

    _onPanelActivate(nodeId) {
        this._editor.selectNode({ nodeId });
    }

    _renderNodeFloatingPanels(state) {
        const openIds = Array.isArray(state.openNodePanelIds) ? state.openNodePanelIds : [];
        if (openIds.length === 0) {
            return '';
        }
        const layouts = isPlainObject(state.propertyPanelLayouts) ? state.propertyPanelLayouts : {};
        const selectedNodeId = typeof state.selectedNodeId === 'string' ? state.selectedNodeId : '';
        return openIds.map((nodeId) => {
            const header = this._panelHeaderForNode(nodeId, state);
            if (!header) {
                return '';
            }
            const layout = isPlainObject(layouts[nodeId]) ? layouts[nodeId] : {};
            const collapsed = layout.collapsed === true;
            const isActive = nodeId === selectedNodeId && !collapsed;
            const nodeAiOpen = Boolean(isActive && this._nodeAiHelperOpen);
            return html`
                <flows-floating-panel
                    panel-id=${nodeId}
                    header-icon=${header.icon}
                    header-title=${header.title}
                    color-token=${header.colorToken}
                    .layout=${layout}
                    ?show-backdrop=${isActive}
                    ?ai-enabled=${isActive}
                    ?ai-active=${nodeAiOpen}
                    @layout-change=${(e) => this._onPanelLayoutChange(nodeId, e)}
                    @activate=${() => this._onPanelActivate(nodeId)}
                    @node-ai-helper-toggle=${this._onToggleNodeAiHelper}
                    @close=${() => this._onCloseFloatingPanel(nodeId)}
                >
                    ${isActive
                        ? html`
                            <flows-property-panel
                                slot="editor"
                                .flowId=${this.flowId}
                                .branchId=${this.branchId}
                                .nodeId=${nodeId}
                            ></flows-property-panel>
                            ${nodeAiOpen
                                ? html`
                                    <flows-node-ai-helper
                                        slot="assistant"
                                        .flowId=${this.flowId}
                                        .branchId=${this.branchId}
                                        .nodeId=${nodeId}
                                    ></flows-node-ai-helper>
                                `
                                : nothing}
                        `
                        : nothing}
                </flows-floating-panel>
            `;
        });
    }

    _renderResourceFloatingPanel(state) {
        const header = this._panelHeader();
        if (!header || !state.selectedResourceId) {
            return '';
        }
        return html`
            <flows-floating-panel
                panel-id=${`resource:${state.selectedResourceId}`}
                header-icon=${header.icon}
                header-title=${header.title}
                color-token=${header.colorToken}
                ?show-backdrop=${true}
                @close=${() => this._onCloseFloatingPanel()}
            >
                <flows-resource-property-panel .flowId=${this.flowId}></flows-resource-property-panel>
            </flows-floating-panel>
        `;
    }

    _renderPropertyPanel() {
        const state = asObject(this._editor.state);
        return html`
            ${this._renderNodeFloatingPanels(state)}
            ${this._renderResourceFloatingPanel(state)}
        `;
    }

    _renderRightRail() {
        if (!this.flowId || !this._flowSettingsOpen) return '';
        return html`
            <div class="editor-right-rail">
                <flows-flow-property-panel .flowId=${this.flowId} .branchId=${this.branchId}></flows-flow-property-panel>
            </div>
        `;
    }

    _branchDisplayLabel() {
        if (this.branchId === 'base') {
            return this.t('branches_tabs.base');
        }
        const flow = this._flows.byId && this._flows.byId[this.flowId]
            ? this._flows.byId[this.flowId]
            : asArray(this._flows.items).find((f) => f && f.flow_id === this.flowId);
        const branch = flow && flow.branches && flow.branches[this.branchId] ? flow.branches[this.branchId] : null;
        if (branch && typeof branch.name === 'string' && branch.name.length > 0) {
            return branch.name;
        }
        if (typeof this.branchId === 'string' && this.branchId.length > 0) {
            return this.branchId;
        }
        return '';
    }

    _isAgentLayoutActive(state) {
        const branchData = isPlainObject(state.branchData) ? state.branchData : null;
        if (branchData === null || !isAgentFocusEligible(branchData)) {
            return false;
        }
        return state.editorLayout === EDITOR_LAYOUT_AGENT;
    }

    _switchToAgentLayout() {
        if (typeof this.flowId !== 'string' || this.flowId.length === 0) {
            throw new Error('FlowEditorPage: flowId is required to switch to agent layout');
        }
        writeEditorLayoutPreference(this.flowId, EDITOR_LAYOUT_AGENT);
        this._editor.setEditorLayout({ layout: EDITOR_LAYOUT_AGENT });
    }

    _renderCanvasLayoutToggle(state) {
        const branchData = isPlainObject(state.branchData) ? state.branchData : null;
        if (branchData === null || !isAgentFocusEligible(branchData)) {
            return '';
        }
        if (state.editorLayout === EDITOR_LAYOUT_AGENT) {
            return '';
        }
        return html`
            <platform-button
                class="layout-toggle-float"
                variant="secondary"
                density="compact"
                icon-only
                title=${this.t('agent_focus.to_agent')}
                aria-label=${this.t('agent_focus.to_agent_aria')}
                @click=${() => this._switchToAgentLayout()}
            >
                <platform-icon name="llm_node" size="18"></platform-icon>
            </platform-button>
        `;
    }

    _resolvedInterfaceConfig(state) {
        const flow = isPlainObject(state.flowConfig) ? state.flowConfig : null;
        if (!flow || !isPlainObject(flow.interface)) return null;
        if (!this.branchId || this.branchId === 'base') return flow.interface;
        const branch = isPlainObject(flow.branches?.[this.branchId]) ? flow.branches[this.branchId] : null;
        return branch !== null && isPlainObject(branch.interface) ? branch.interface : flow.interface;
    }

    /** «Опубликовать» в редакторе интерфейса: документ ветки в flowConfig и сразу сохранение flow. */
    async _onInterfaceChange(event) {
        const config = event.detail?.config;
        const state = asObject(this._editor.state);
        if (!isPlainObject(config)) {
            throw new Error('flow-editor-page: interface-change config must be a plain object');
        }
        if (!isPlainObject(state.flowConfig)) {
            throw new Error('flow-editor-page: interface-change requires loaded flowConfig');
        }
        if (!this.branchId || this.branchId === 'base') {
            this._editor.patchFlowConfig({ patch: { interface: config } });
        } else {
            const branches = isPlainObject(state.flowConfig.branches) ? state.flowConfig.branches : {};
            const branch = isPlainObject(branches[this.branchId]) ? branches[this.branchId] : { name: this.branchId };
            this._editor.patchFlowConfig({ patch: { branches: { ...branches, [this.branchId]: { ...branch, interface: config } } } });
        }
        this._scheduleDataflowRefresh(asObject(this._editor.state));
        const saved = await saveEditorFlow(this._editor, this._flowUpdate, this.flowId);
        if (saved) this.toast('interface_editor.published');
    }

    _renderWorkspaceShell(state) {
        const workspace = state.workspace;
        if (workspace !== 'logic' && workspace !== 'interface' && workspace !== 'run') {
            throw new Error(`flow-editor-page: unsupported workspace ${String(workspace)}`);
        }
        if (workspace === 'interface') {
            return html`
                    <div class="interface-host"><flows-interface-editor
                        .interfaceConfig=${this._resolvedInterfaceConfig(state)}
                        .flowId=${this.flowId}
                        .branchId=${this.branchId === 'base' ? 'default' : this.branchId}
                        @interface-change=${this._onInterfaceChange}
                    ></flows-interface-editor></div>
                `;
        }
        const agentLayout = this._isAgentLayoutActive(state);
        const dismissSafe = this._flowSettingsOpen ? 'flow-settings-dismiss-safe' : '';
        return html`
                ${agentLayout
                    ? ''
                    : html`
                        <flows-node-types-sidebar
                            class=${dismissSafe}
                            flow-id=${this.flowId}
                            ?flow-settings-active=${this._flowSettingsOpen}
                            @toggle-flow-settings=${() => this._onToggleFlowSettings()}
                        ></flows-node-types-sidebar>
                    `}
                ${agentLayout
                    ? html`
                        <div class="agent-studio-host">
                            <flows-agent-focus-studio
                                .flowId=${this.flowId}
                                .branchId=${this.branchId}
                                @toggle-flow-settings=${() => this._onToggleFlowSettings()}
                            ></flows-agent-focus-studio>
                            <flows-execution-panel .flowId=${this.flowId} .branchId=${this.branchId}></flows-execution-panel>
                        </div>
                    `
                    : html`
                        <div class="canvas-host">
                            <flows-flow-canvas .flowId=${this.flowId} .branchId=${this.branchId}></flows-flow-canvas>
                            <flows-bottom-toolbar></flows-bottom-toolbar>
                            <flows-execution-panel .flowId=${this.flowId} .branchId=${this.branchId}></flows-execution-panel>
                            ${this._renderCanvasLayoutToggle(state)}
                            ${this._renderPropertyPanel()}
                        </div>
                    `}
                ${this._renderRightRail()}
                `;
    }

    render() {
        this._scheduleDataflowRefresh(asObject(this._editor.state));
        const dismissSafe = this._flowSettingsOpen ? 'flow-settings-dismiss-safe' : '';
        const state = asObject(this._editor.state);
        return html`
            ${this._flowSettingsOpen
                ? html`<div class="flow-settings-dismiss-layer" @click=${() => this._onDismissFlowSettingsBackdrop()}></div>`
                : ''}
            <div class="editor-chrome">
                <div class="editor-breadcrumbs">
                    <platform-breadcrumbs compact current-label=${this._branchDisplayLabel()}></platform-breadcrumbs>
                </div>
                <flows-editor-header
                    class="editor-chrome-panel ${dismissSafe}"
                    .flowId=${this.flowId}
                    .branchId=${this.branchId}
                ></flows-editor-header>
            </div>
            <div class="editor-shell">
                ${this._renderWorkspaceShell(state)}
            </div>
        `;
    }
}

customElements.define('flow-editor-page', FlowEditorPage);
