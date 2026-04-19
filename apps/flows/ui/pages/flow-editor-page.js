/**
 * FlowEditorPage — визуальный редактор flow.
 *
 * Layout:
 *   <flows-editor-header />          — back / save / theme
 *   <flows-skills-tabs />            — табы skills
 *   .editor-shell:
 *     <flows-node-types-sidebar />    — drag-source типов нод
 *     .canvas-host:
 *       <flows-flow-canvas />         — native SVG canvas
 *       <flows-bottom-toolbar />      — floating pill снизу
 *       <flows-canvas-minimap />      — мини-карта снизу-справа
 *     <flows-floating-panel>          — chrome для property/resource panel
 *       <flows-property-panel />      — выбранная нода
 *       <flows-resource-property-panel /> — выбранный ресурс
 *   <flows-breakpoint-manager />     — индикатор брейкпоинтов
 *   <flows-execution-panel />        — тестовый запуск (виден по флагу)
 *   <flows-variables-panel />        — variables panel (виден по флагу)
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { CoreEvents } from '@platform/lib/events/index.js';
import '../components/editor/flows-editor-header.js';
import '../components/editor/flows-skills-tabs.js';
import '../components/editor/flows-node-types-sidebar.js';
import '../components/editor/flows-property-panel.js';
import '../components/editor/flows-resource-property-panel.js';
import '../components/editor/flows-bottom-toolbar.js';
import '../components/editor/flows-breakpoint-manager.js';
import '../components/editor/flows-execution-panel.js';
import '../components/editor/flows-variables-panel.js';
import '../components/editor/flows-floating-panel.js';
import '../components/flow-canvas/flows-flow-canvas.js';
import '../components/flow-canvas/flows-canvas-minimap.js';
import '../modals/flows-canvas-help-modal.js';
import { getNodeTypeMeta, getCategoryToken } from '../constants/node-icons.js';

export class FlowEditorPage extends PlatformPage {
    static properties = {
        flowId: { type: String, attribute: 'flow-id' },
        skillId: { type: String, attribute: 'skill-id' },
    };

    static styles = [
        PlatformPage.styles,
        css`
            :host {
                flex: 1; min-width: 0; min-height: 0;
                display: flex; flex-direction: column;
                background: var(--bg-gradient); overflow: hidden;
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
        this.skillId = 'base';
        this._editor = this.useOp('flows/editor');
        this._flows = this.useResource('flows/flows');
        this._editorStateOp = this.useOp('flows/code_editor_state');
        this.useEvent(CoreEvents.ROUTER_ROUTE_CHANGED, () => this._loadFlowIfNeeded());
        this.useEvent('flows/flow/updated', () => this._reloadFlow());
    }

    connectedCallback() {
        super.connectedCallback();
        this._loadFlowIfNeeded();
    }

    updated(changed) {
        super.updated?.(changed);
        if (changed.has('flowId') || changed.has('skillId')) {
            this._loadFlowIfNeeded();
        }
    }

    async _loadFlowIfNeeded() {
        if (!this.flowId) return;
        const editorState = this._editor.state;
        if (editorState && editorState.flowId === this.flowId && editorState.currentSkillId === this.skillId) return;
        await this._flows.get(this.flowId);
        const flow = (this._flows.items || []).find((f) => f && f.flow_id === this.flowId);
        if (!flow) return;
        const apiSkill = !this.skillId || this.skillId === 'base' ? 'default' : this.skillId;
        const previewExecutionState = await this._editorStateOp.run({
            flow_id: this.flowId,
            skill_id: apiSkill,
        });
        this._editor.setFlow({
            flow,
            skillId: this.skillId,
            previewExecutionState,
        });
    }

    async _reloadFlow() {
        if (!this.flowId) return;
        await this._flows.get(this.flowId);
    }

    _panelHeader() {
        const state = this._editor.state || {};
        if (state.selectedNodeId) {
            const node = state.skillsData?.nodes?.[state.selectedNodeId];
            const meta = getNodeTypeMeta(node?.type);
            return {
                icon: meta.icon,
                title: node?.name || state.selectedNodeId,
                colorToken: getCategoryToken(meta.category),
            };
        }
        if (state.selectedResourceId) {
            const resource = state.skillsData?.resources?.[state.selectedResourceId];
            return {
                icon: 'box',
                title: resource?.name || state.selectedResourceId,
                colorToken: getCategoryToken('flow'),
            };
        }
        return null;
    }

    _renderPanel() {
        const header = this._panelHeader();
        if (!header) return '';
        const state = this._editor.state || {};
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
                    ? html`<flows-property-panel .flowId=${this.flowId} .skillId=${this.skillId}></flows-property-panel>`
                    : html`<flows-resource-property-panel .flowId=${this.flowId}></flows-resource-property-panel>`}
            </flows-floating-panel>
        `;
    }

    render() {
        return html`
            <flows-editor-header .flowId=${this.flowId} .skillId=${this.skillId}></flows-editor-header>
            <flows-skills-tabs .flowId=${this.flowId} active-skill-id=${this.skillId}></flows-skills-tabs>
            <div class="editor-shell">
                <flows-node-types-sidebar flow-id=${this.flowId}></flows-node-types-sidebar>
                <div class="canvas-host">
                    <flows-flow-canvas .flowId=${this.flowId} .skillId=${this.skillId}></flows-flow-canvas>
                    <flows-bottom-toolbar></flows-bottom-toolbar>
                    <flows-canvas-minimap></flows-canvas-minimap>
                </div>
                ${this._renderPanel()}
            </div>
            <flows-breakpoint-manager .flowId=${this.flowId}></flows-breakpoint-manager>
            <flows-execution-panel .flowId=${this.flowId} .skillId=${this.skillId}></flows-execution-panel>
            <flows-variables-panel .flowId=${this.flowId}></flows-variables-panel>
        `;
    }
}

customElements.define('flow-editor-page', FlowEditorPage);
