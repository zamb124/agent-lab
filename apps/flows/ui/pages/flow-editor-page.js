/**
 * FlowEditorPage — визуальный редактор flow.
 *
 * Layout:
 *   <flows-editor-header />          — back / save / theme
 *   <flows-branches-tabs />            — табы веток
 *   .editor-shell:
 *     <flows-node-types-sidebar />    — drag-source типов нод
 *     .canvas-host:
 *       <flows-flow-canvas />         — native SVG canvas
 *       <flows-bottom-toolbar />      — floating pill снизу
 *     <flows-floating-panel>          — chrome для property/resource panel
 *       <flows-property-panel />      — выбранная нода
 *       <flows-resource-property-panel /> — выбранный ресурс
 *   <flows-execution-panel />        — тестовый запуск (виден по флагу)
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { CoreEvents } from '@platform/lib/events/index.js';
import '../components/editor/flows-editor-header.js';
import '../components/editor/flows-branches-tabs.js';
import '../components/editor/flows-node-types-sidebar.js';
import '../components/editor/flows-property-panel.js';
import '../components/editor/flows-resource-property-panel.js';
import '../components/editor/flows-bottom-toolbar.js';
import '../components/editor/flows-execution-panel.js';
import '../components/editor/flows-floating-panel.js';
import '../components/flow-canvas/flows-flow-canvas.js';
import '../modals/flows-canvas-help-modal.js';
import { getNodeTypeMeta, getCategoryToken } from '../constants/node-icons.js';
import { asObject, isPlainObject } from '../_helpers/flows-resolvers.js';

export class FlowEditorPage extends PlatformPage {
    static properties = {
        flowId: { type: String, attribute: 'flow-id' },
        branchId: { type: String, attribute: 'branch-id' },
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
            }
        `,
    ];

    constructor() {
        super();
        this.flowId = '';
        this.branchId = 'base';
        this._editor = this.useOp('flows/editor');
        this._flows = this.useResource('flows/flows');
        this._editorStateOp = this.useOp('flows/code_editor_state');
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
        this._loadFlowIfNeeded();
    }

    updated(changed) {
        super.updated?.(changed);
        if (changed.has('flowId') || changed.has('branchId')) {
            this._loadFlowIfNeeded();
        }
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

    _renderPanel() {
        const header = this._panelHeader();
        if (!header) return '';
        const state = asObject(this._editor.state);
        return html`
            <flows-floating-panel
                header-icon=${header.icon}
                header-title=${header.title}
                color-token=${header.colorToken}
                ?expanded=${state.panelExpanded}
                @expand-change=${(e) => {
                    const d = e.detail;
                    if (d && typeof d.expanded === 'boolean') {
                        this._editor.togglePanelExpanded({ expanded: d.expanded });
                    } else {
                        this._editor.togglePanelExpanded({});
                    }
                }}
                @close=${() => this._editor.closePanel({})}
            >
                ${state.selectedNodeId
                    ? html`<flows-property-panel .flowId=${this.flowId} .branchId=${this.branchId}></flows-property-panel>`
                    : html`<flows-resource-property-panel .flowId=${this.flowId}></flows-resource-property-panel>`}
            </flows-floating-panel>
        `;
    }

    render() {
        return html`
            <flows-editor-header .flowId=${this.flowId} .branchId=${this.branchId}></flows-editor-header>
            <flows-branches-tabs .flowId=${this.flowId} active-branch-id=${this.branchId}></flows-branches-tabs>
            <div class="editor-shell">
                <flows-node-types-sidebar flow-id=${this.flowId}></flows-node-types-sidebar>
                <div class="canvas-host">
                    <flows-flow-canvas .flowId=${this.flowId} .branchId=${this.branchId}></flows-flow-canvas>
                    <flows-bottom-toolbar></flows-bottom-toolbar>
                    <flows-execution-panel .flowId=${this.flowId} .branchId=${this.branchId}></flows-execution-panel>
                </div>
                ${this._renderPanel()}
            </div>
        `;
    }
}

customElements.define('flow-editor-page', FlowEditorPage);
