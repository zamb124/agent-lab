/**
 * flows-bottom-toolbar — плавающая «таблетка» в нижней части канваса.
 *
 * Группы:
 *   1. zoom: zoom_in / zoom_out / zoom_100 / fit_view
 *   2. tools: select / pan
 *   3. actions: undo / redo / variables / переключатель smart-guides / help
 *
 * Источник state: useOp('flows/editor').state.{activeTool,canUndo,canRedo,
 * smartGuidesEnabled,viewBox,skillsData,flowConfig}.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-help-hint.js';
import { asObject, isPlainObject, getBranchNodes } from '../../_helpers/flows-resolvers.js';
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
                display: flex;
                align-items: center;
                gap: var(--space-1);
                padding: var(--space-1) var(--space-2);
                border-radius: var(--radius-full);
                background: var(--glass-solid-strong);
                border: 1px solid var(--glass-border-medium);
                box-shadow: var(--glass-shadow-strong);
            }
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

    _zoomIn() { this._zoom(1 / ZOOM_FACTOR); }
    _zoomOut() { this._zoom(ZOOM_FACTOR); }
    _zoom100() {
        const vb = this._viewBox();
        const d = FLOWS_EDITOR_DEFAULT_VIEWBOX;
        this._setViewBox({ x: vb.x + vb.w / 2 - d.w / 2, y: vb.y + vb.h / 2 - d.h / 2, w: d.w, h: d.h });
    }

    _fitView() {
        const state = asObject(this._editor.state);
        const nodes = getBranchNodes(state);
        const vb = computeFitViewBox(Object.values(nodes));
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

    _renderIconButton({ icon, title, onClick, active = false, disabled = false }) {
        const variant = active ? 'secondary' : 'ghost';
        return html`
            <platform-button
                variant=${variant}
                icon-only
                density="dense"
                aria-label=${title}
                ?disabled=${disabled}
                @click=${onClick}
            >
                <platform-icon name=${icon} size="16"></platform-icon>
            </platform-button>
        `;
    }

    render() {
        const state = asObject(this._editor.state);
        const activeTool = typeof state.activeTool === 'string' && state.activeTool.length > 0 ? state.activeTool : 'select';
        const guidesOn = state.smartGuidesEnabled !== false;
        return html`
            ${this._renderIconButton({ icon: 'plus', title: this.t('canvas.toolbar.zoom_in'), onClick: () => this._zoomIn() })}
            ${this._renderIconButton({ icon: 'minus', title: this.t('canvas.toolbar.zoom_out'), onClick: () => this._zoomOut() })}
            ${this._renderIconButton({ icon: 'search', title: this.t('canvas.toolbar.zoom_100'), onClick: () => this._zoom100() })}
            ${this._renderIconButton({ icon: 'fullscreen', title: this.t('canvas.toolbar.zoom_fit'), onClick: () => this._fitView() })}

            <span class="divider"></span>

            ${this._renderIconButton({
                icon: 'target',
                title: this.t('canvas.toolbar.tool_select'),
                onClick: () => this._setTool('select'),
                active: activeTool === 'select',
            })}
            ${this._renderIconButton({
                icon: 'drag-handle',
                title: this.t('canvas.toolbar.tool_pan'),
                onClick: () => this._setTool('pan'),
                active: activeTool === 'pan',
            })}

            <span class="divider"></span>

            ${this._renderIconButton({
                icon: 'undo',
                title: this.t('canvas.toolbar.undo'),
                onClick: () => this._undo(),
                disabled: !state.canUndo,
            })}
            ${this._renderIconButton({
                icon: 'redo',
                title: this.t('canvas.toolbar.redo'),
                onClick: () => this._redo(),
                disabled: !state.canRedo,
            })}

            <span class="divider"></span>

            ${this._renderIconButton({ icon: 'code', title: this.t('canvas.toolbar.open_variables'), onClick: () => this._openVariables() })}
            ${this._renderIconButton({
                icon: 'schema',
                title: this.t('canvas.toolbar.toggle_guides'),
                onClick: () => this._toggleGuides(),
                active: guidesOn,
            })}
            <platform-help-hint
                .label=${this.t('canvas.toolbar.canvas_hint_label')}
                .summary=${this.t('canvas.toolbar.canvas_hint_summary')}
                .details=${this.t('canvas.toolbar.canvas_hint_details')}
                .docHref=${'/documentation/scenarios/flows/add-llm-node/'}
                .docLabel=${this.t('help_hints.open_scenario')}
            ></platform-help-hint>
            ${this._renderIconButton({ icon: 'help', title: this.t('canvas.toolbar.help'), onClick: () => this._help() })}
        `;
    }
}

customElements.define('flows-bottom-toolbar', FlowsBottomToolbar);
