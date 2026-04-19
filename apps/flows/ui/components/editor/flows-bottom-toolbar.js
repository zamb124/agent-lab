/**
 * flows-bottom-toolbar — плавающая «таблетка» в нижней части канваса.
 *
 * Группы:
 *   1. zoom: zoom_in / zoom_out / zoom_100 / fit_view
 *   2. tools: select / pan / add_node
 *   3. actions: undo / redo / variables / breakpoints / smart-guides toggle / help
 *
 * Источник state: useOp('flows/editor').state.{activeTool,canUndo,canRedo,
 * variablesPanelOpen,smartGuidesEnabled,viewBox,skillsData}.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';

const ZOOM_FACTOR = 1.2;
const DEFAULT_VIEWBOX = Object.freeze({ x: 0, y: 0, w: 1600, h: 1000 });

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
                width: 36px; height: 36px;
                display: flex; align-items: center; justify-content: center;
                background: transparent; border: none;
                border-radius: var(--radius-full);
                color: var(--text-secondary);
                cursor: pointer;
                transition: background var(--duration-fast), color var(--duration-fast);
            }
            .btn:hover { background: var(--glass-solid-medium); color: var(--text-primary); }
            .btn[active] { background: var(--accent-subtle); color: var(--accent); }
            .btn:disabled { opacity: 0.35; cursor: not-allowed; }
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
        return this._editor.state?.viewBox || { ...DEFAULT_VIEWBOX };
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
        this._setViewBox({ x: vb.x + vb.w / 2 - 800, y: vb.y + vb.h / 2 - 500, w: 1600, h: 1000 });
    }

    _fitView() {
        const nodes = Object.values(this._editor.state?.skillsData?.nodes || {});
        if (nodes.length === 0) return;
        let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
        for (const n of nodes) {
            const x = Number(n.pos_x) || 0;
            const y = Number(n.pos_y) || 0;
            if (x < minX) minX = x;
            if (y < minY) minY = y;
            if (x + 200 > maxX) maxX = x + 200;
            if (y + 72 > maxY)  maxY = y + 72;
        }
        const pad = 80;
        this._setViewBox({ x: minX - pad, y: minY - pad, w: (maxX - minX) + pad * 2, h: (maxY - minY) + pad * 2 });
    }

    _setTool(tool) { this._editor.setActiveTool({ tool }); }
    _undo() { this._editor.undo({}); }
    _redo() { this._editor.redo({}); }
    _toggleVariables() { this._editor.toggleVariablesPanel({}); }
    _toggleGuides() { this._editor.toggleSmartGuides({}); }
    _help() { this.openModal('flows.canvas_help', {}); }

    render() {
        const state = this._editor.state || {};
        const activeTool = state.activeTool || 'select';
        const guidesOn = state.smartGuidesEnabled !== false;
        return html`
            <button class="btn" type="button" title=${this.t('canvas.toolbar.zoom_in')} @click=${this._zoomIn}>
                <platform-icon name="plus" size="16"></platform-icon>
            </button>
            <button class="btn" type="button" title=${this.t('canvas.toolbar.zoom_out')} @click=${this._zoomOut}>
                <platform-icon name="minimize" size="16"></platform-icon>
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

            <button class="btn" type="button" ?active=${state.variablesPanelOpen} title=${this.t('canvas.toolbar.toggle_variables')} @click=${this._toggleVariables}>
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
