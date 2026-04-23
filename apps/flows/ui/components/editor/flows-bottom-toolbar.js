/**
 * flows-bottom-toolbar — плавающая «таблетка» в нижней части канваса.
 *
 * Группы:
 *   1. zoom: zoom_in / zoom_out / zoom_100 / fit_view
 *   2. tools: select / pan
 *   3. actions: undo / redo / variables / smart-guides toggle / help
 *
 * Источник state: useOp('flows/editor').state.{activeTool,canUndo,canRedo,
 * smartGuidesEnabled,viewBox,skillsData,flowConfig}.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';
import { asObject, isPlainObject, getSkillsNodes } from '../../_helpers/flows-resolvers.js';
import { computeFitViewBox, FLOWS_EDITOR_DEFAULT_VIEWBOX } from '../../_helpers/flows-viewbox.js';

const ZOOM_FACTOR = 1.2;

export class FlowsBottomToolbar extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                position: absolute;
                bottom: var(--space-4);
                left: 50%;
                transform: translateX(-50%);
                z-index: 6;
                display: flex; align-items: center; gap: var(--space-1);
                padding: var(--space-1) var(--space-2);
                border-radius: var(--radius-full);
                background: var(--glass-solid-strong);
                border: 1px solid var(--glass-border-medium);
                box-shadow: var(--glass-shadow-strong);
            }
            .btn {
                box-sizing: border-box;
                flex: 0 0 auto;
                width: 36px; height: 36px;
                padding: 0; gap: 0;
                font-size: 0; line-height: 1;
                display: inline-flex; align-items: center; justify-content: center;
                background: transparent; border: none;
                border-radius: var(--radius-full);
                color: var(--text-secondary);
                cursor: pointer;
                transition: background var(--duration-fast), color var(--duration-fast);
            }
            .btn:hover:not(:disabled) { background: var(--glass-solid-medium); color: var(--text-primary); }
            .btn[active] { background: var(--accent-subtle); color: var(--accent); }
            .btn:disabled { opacity: 0.35; cursor: not-allowed; pointer-events: none; }
            .btn platform-icon { display: inline-flex; pointer-events: none; }
            .divider {
                width: 1px;
                height: 22px;
                background: var(--border-subtle);
                margin: 0 var(--space-1);
            }
        `,
    ];

    constructor() {
        super();
        this._editor = this.useOp('flows/editor');
    }

    _viewBox() {
        const vb = isPlainObject(this._editor.state) ? this._editor.state.viewBox : null;
        return isPlainObject(vb) ? vb : { ...FLOWS_EDITOR_DEFAULT_VIEWBOX };
    }

    _setViewBox(vb) {
        this._editor.setViewBox({ viewBox: vb });
    }

    _zoom(factor) {
        const vb = this._viewBox();
        const cx = vb.x + vb.w / 2;
        const cy = vb.y + vb.h / 2;
        const w = vb.w * factor;
        const h = vb.h * factor;
        this._setViewBox({ x: cx - w / 2, y: cy - h / 2, w, h });
    }

    _zoomIn()    { this._zoom(1 / ZOOM_FACTOR); }
    _zoomOut()   { this._zoom(ZOOM_FACTOR); }
    _zoom100() {
        const vb = this._viewBox();
        const d = FLOWS_EDITOR_DEFAULT_VIEWBOX;
        this._setViewBox({ x: vb.x + vb.w / 2 - d.w / 2, y: vb.y + vb.h / 2 - d.h / 2, w: d.w, h: d.h });
    }

    _fitView() {
        const nodes = Object.values(getSkillsNodes(this._editor.state));
        const vb = computeFitViewBox(nodes);
        if (vb === null) {
            this._setViewBox({ ...FLOWS_EDITOR_DEFAULT_VIEWBOX });
            return;
        }
        this._setViewBox(vb);
    }

    _setTool(tool) { this._editor.setActiveTool({ tool }); }
    _undo() { this._editor.undo({}); }
    _redo() { this._editor.redo({}); }
    _openVariables() {
        const flowId = this._editor.state.flowConfig.flow_id;
        this.openModal('flows.variables', { scope: 'flow', flowId });
    }
    _toggleGuides() { this._editor.toggleSmartGuides({}); }
    _help() { this.openModal('flows.canvas_help', {}); }

    render() {
        const state = asObject(this._editor.state);
        const activeTool = typeof state.activeTool === 'string' && state.activeTool.length > 0 ? state.activeTool : 'select';
        const guidesOn = state.smartGuidesEnabled !== false;
        return html`
            <button class="btn" type="button" title=${this.t('canvas.toolbar.zoom_in')} @click=${this._zoomIn}>
                <platform-icon name="plus" size="16"></platform-icon>
            </button>
            <button class="btn" type="button" title=${this.t('canvas.toolbar.zoom_out')} @click=${this._zoomOut}>
                <platform-icon name="minus" size="16"></platform-icon>
            </button>
            <button class="btn" type="button" title=${this.t('canvas.toolbar.zoom_100')} @click=${this._zoom100}>
                <platform-icon name="search" size="16"></platform-icon>
            </button>
            <button class="btn" type="button" title=${this.t('canvas.toolbar.zoom_fit')} @click=${this._fitView}>
                <platform-icon name="fullscreen" size="16"></platform-icon>
            </button>

            <span class="divider"></span>

            <button class="btn" type="button" ?active=${activeTool === 'select'} title=${this.t('canvas.toolbar.tool_select')} @click=${() => this._setTool('select')}>
                <platform-icon name="target" size="16"></platform-icon>
            </button>
            <button class="btn" type="button" ?active=${activeTool === 'pan'} title=${this.t('canvas.toolbar.tool_pan')} @click=${() => this._setTool('pan')}>
                <platform-icon name="drag-handle" size="16"></platform-icon>
            </button>

            <span class="divider"></span>

            <button class="btn" type="button" ?disabled=${!state.canUndo} title=${this.t('canvas.toolbar.undo')} @click=${this._undo}>
                <platform-icon name="undo" size="16"></platform-icon>
            </button>
            <button class="btn" type="button" ?disabled=${!state.canRedo} title=${this.t('canvas.toolbar.redo')} @click=${this._redo}>
                <platform-icon name="redo" size="16"></platform-icon>
            </button>

            <span class="divider"></span>

            <button class="btn" type="button" title=${this.t('canvas.toolbar.open_variables')} @click=${this._openVariables}>
                <platform-icon name="code" size="16"></platform-icon>
            </button>
            <button class="btn" type="button" ?active=${guidesOn} title=${this.t('canvas.toolbar.toggle_guides')} @click=${this._toggleGuides}>
                <platform-icon name="schema" size="16"></platform-icon>
            </button>
            <button class="btn" type="button" title=${this.t('canvas.toolbar.help')} @click=${this._help}>
                <platform-icon name="help" size="16"></platform-icon>
            </button>
        `;
    }
}

customElements.define('flows-bottom-toolbar', FlowsBottomToolbar);
