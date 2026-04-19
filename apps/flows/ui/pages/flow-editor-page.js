/**
 * FlowEditorPage — визуальный редактор flow.
 *
 * Layout:
 *   <flows-editor-header />          — back / save / theme
 *   <flows-skills-tabs />            — табы skills
 *   .editor-shell:
 *     <flows-node-types-sidebar />    — drag-source типов нод
 *     <flows-flow-canvas />           — native SVG canvas
 *     property-panel или resource-property-panel в floating overlay
 *   <flows-bottom-toolbar />         — undo/redo, активный tool
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
import '../components/flow-canvas/flows-flow-canvas.js';

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
            .floating-panel {
                position: absolute;
                top: var(--space-3); right: var(--space-3); bottom: var(--space-3);
                width: 380px;
                background: var(--glass-solid-medium);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-lg);
                overflow: auto; z-index: 5;
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

    _renderPanel() {
        const state = this._editor.state || {};
        if (state.selectedNodeId) {
            return html`
                <div class="floating-panel">
                    <flows-property-panel
                        .flowId=${this.flowId}
                        .skillId=${this.skillId}
                    ></flows-property-panel>
                </div>
            `;
        }
        if (state.selectedResourceId) {
            return html`
                <div class="floating-panel">
                    <flows-resource-property-panel .flowId=${this.flowId}></flows-resource-property-panel>
                </div>
            `;
        }
        return '';
    }

    render() {
        return html`
            <flows-editor-header .flowId=${this.flowId} .skillId=${this.skillId}></flows-editor-header>
            <flows-skills-tabs .flowId=${this.flowId} active-skill-id=${this.skillId}></flows-skills-tabs>
            <div class="editor-shell">
                <flows-node-types-sidebar flow-id=${this.flowId}></flows-node-types-sidebar>
                <flows-flow-canvas .flowId=${this.flowId} .skillId=${this.skillId}></flows-flow-canvas>
                ${this._renderPanel()}
            </div>
            <flows-bottom-toolbar></flows-bottom-toolbar>
            <flows-breakpoint-manager .flowId=${this.flowId}></flows-breakpoint-manager>
            <flows-execution-panel .flowId=${this.flowId} .skillId=${this.skillId}></flows-execution-panel>
            <flows-variables-panel .flowId=${this.flowId}></flows-variables-panel>
        `;
    }
}

customElements.define('flow-editor-page', FlowEditorPage);
