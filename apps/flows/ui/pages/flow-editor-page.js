/**
 * FlowEditorPage — визуальный редактор flow.
 *
 * Макет:
 *   <flows-editor-header />          — назад / сохранить / тема
 *   <flows-branches-tabs />            — табы веток
 *   .editor-shell:
 *     <flows-node-types-sidebar />    — drag-source типов нод
 *     .canvas-host:
 *       <flows-flow-canvas />         — native SVG canvas
 *       <flows-bottom-toolbar />      — floating pill снизу
 *     .editor-right-rail:
 *       <flows-flow-property-panel /> — лимиты и речь (по кнопке в сайдбаре над триггерами)
 *       <flows-floating-panel dock-stack> — chrome для ноды или ресурса
 *         <flows-property-panel /> / <flows-resource-property-panel />
 *   <flows-execution-panel />        — тестовый запуск (виден по флагу)
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { CoreEvents } from '@platform/lib/events/index.js';
import '../components/editor/flows-editor-header.js';
import '../components/editor/flows-branches-tabs.js';
import '../components/editor/flows-node-types-sidebar.js';
import '../components/editor/flows-flow-property-panel.js';
import '../components/editor/flows-property-panel.js';
import '../components/editor/flows-resource-property-panel.js';
import '../components/editor/flows-bottom-toolbar.js';
import '../components/editor/flows-execution-panel.js';
import '../components/editor/flows-floating-panel.js';
import '../components/editor/flows-node-ai-helper.js';
import '../components/flow-canvas/flows-flow-canvas.js';
import '../modals/flows-canvas-help-modal.js';
import '../modals/flows-preview-share-modal.js';
import '../modals/flows-api-console-modal.js';
import { getNodeTypeMeta, getCategoryToken } from '../constants/node-icons.js';
import { asObject, isPlainObject } from '../_helpers/flows-resolvers.js';

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
                /* Содержит z-index детей (тулбар 6, execution 5): иначе они бьются с rail (5)
                   на уровне .editor-shell и перекрывают модалку/развёрнутую панель справа. */
                isolation: isolate;
                z-index: 0;
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
        `,
    ];

    constructor() {
        super();
        this.flowId = '';
        this.branchId = 'base';
        this._flowSettingsOpen = false;
        this._nodeAiHelperOpen = false;
        this._editor = this.useOp('flows/editor');
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
        return {
            flow_id: this.flowId || state.flowId || null,
            branch_id: apiBranch,
            entry: typeof branchData.entry === 'string' && branchData.entry.length > 0 ? branchData.entry : null,
            nodes: branchData.nodes,
            edges: Array.isArray(branchData.edges) ? branchData.edges : [],
            variables: isPlainObject(branchData.variables) ? branchData.variables : {},
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

    _panelHeader() {
        const state = asObject(this._editor.state);
        const branchData = isPlainObject(state.branchData) ? state.branchData : null;
        if (state.selectedNodeId) {
            const nodes = branchData && isPlainObject(branchData.nodes) ? branchData.nodes : null;
            const node = nodes ? nodes[state.selectedNodeId] : null;
            const meta = getNodeTypeMeta(node?.type);
            const title = node && typeof node.name === 'string' && node.name.length > 0
                ? node.name
                : state.selectedNodeId;
            return {
                icon: meta.icon,
                title,
                colorToken: getCategoryToken(meta.category),
            };
        }
        if (state.selectedResourceId) {
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

    _onCloseFloatingPanel() {
        this._nodeAiHelperOpen = false;
        this._editor.closePanel({});
    }

    _renderFloatingPanelDocked() {
        const header = this._panelHeader();
        if (!header) return '';
        const state = asObject(this._editor.state);
        const nodeId = typeof state.selectedNodeId === 'string' ? state.selectedNodeId : '';
        const nodeAiOpen = Boolean(nodeId && this._nodeAiHelperOpen);
        return html`
            <flows-floating-panel
                dock-stack
                header-icon=${header.icon}
                header-title=${header.title}
                color-token=${header.colorToken}
                ?ai-enabled=${Boolean(nodeId)}
                ?ai-active=${nodeAiOpen}
                ?expanded=${state.panelExpanded}
                @node-ai-helper-toggle=${this._onToggleNodeAiHelper}
                @expand-change=${(e) => {
                    const d = e.detail;
                    if (d && typeof d.expanded === 'boolean') {
                        this._editor.togglePanelExpanded({ expanded: d.expanded });
                    } else {
                        this._editor.togglePanelExpanded({});
                    }
                }}
                @close=${this._onCloseFloatingPanel}
            >
                ${nodeAiOpen
                    ? html`
                        <flows-node-ai-helper
                            .flowId=${this.flowId}
                            .branchId=${this.branchId}
                            .nodeId=${nodeId}
                        ></flows-node-ai-helper>
                    `
                    : nodeId
                        ? html`<flows-property-panel .flowId=${this.flowId} .branchId=${this.branchId}></flows-property-panel>`
                    : html`<flows-resource-property-panel .flowId=${this.flowId}></flows-resource-property-panel>`}
            </flows-floating-panel>
        `;
    }

    _renderRightRail() {
        if (!this.flowId) return '';
        return html`
            <div class="editor-right-rail">
                ${this._flowSettingsOpen
                    ? html`<flows-flow-property-panel .flowId=${this.flowId} .branchId=${this.branchId}></flows-flow-property-panel>`
                    : ''}
                ${this._renderFloatingPanelDocked()}
            </div>
        `;
    }

    render() {
        this._scheduleDataflowRefresh(asObject(this._editor.state));
        const dismissSafe = this._flowSettingsOpen ? 'flow-settings-dismiss-safe' : '';
        return html`
            ${this._flowSettingsOpen
                ? html`<div class="flow-settings-dismiss-layer" @click=${() => this._onDismissFlowSettingsBackdrop()}></div>`
                : ''}
            <flows-editor-header
                class=${dismissSafe}
                .flowId=${this.flowId}
                .branchId=${this.branchId}
            ></flows-editor-header>
            <flows-branches-tabs class=${dismissSafe} .flowId=${this.flowId} active-branch-id=${this.branchId}></flows-branches-tabs>
            <div class="editor-shell">
                <flows-node-types-sidebar
                    class=${dismissSafe}
                    flow-id=${this.flowId}
                    ?flow-settings-active=${this._flowSettingsOpen}
                    @toggle-flow-settings=${() => this._onToggleFlowSettings()}
                ></flows-node-types-sidebar>
                <div class="canvas-host">
                    <flows-flow-canvas .flowId=${this.flowId} .branchId=${this.branchId}></flows-flow-canvas>
                    <flows-bottom-toolbar></flows-bottom-toolbar>
                    <flows-execution-panel .flowId=${this.flowId} .branchId=${this.branchId}></flows-execution-panel>
                </div>
                ${this._renderRightRail()}
            </div>
        `;
    }
}

customElements.define('flow-editor-page', FlowEditorPage);
