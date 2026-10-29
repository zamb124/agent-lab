/**
 * flows-bottom-toolbar — плавающая «таблетка» в нижней части канваса.
 *
 * Группы:
 *   1. zoom: zoom_in / zoom_out / zoom_100 / fit_view
 *   2. tools: select / pan
 *   3. history: undo / redo
 *   4. actions: execution panel / variables / smart-guides / data-wires / help
 *
 * Источник state: useOp('flows/editor').state — activeTool, canUndo, canRedo,
 * smartGuidesEnabled, showDataWires, executionPanelOpen, viewBox, flowConfig.
 */

import type { OpController, ControllerFor } from '@platform/lib/base/use-resource.js';
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-button.js';
import { isPlainObject, getBranchNodes } from '../../_helpers/flows-resolvers.js';
import { computeFitViewBox, FLOWS_EDITOR_DEFAULT_VIEWBOX } from '../../_helpers/flows-viewbox.js';
import type {CSSResultGroup, TemplateResult} from 'lit';

const ZOOM_FACTOR = 1.2;

interface EditorViewBox {
    x: number;
    y: number;
    w: number;
    h: number;
}

interface ToolbarButton {
    icon: string;
    title: string;
    onClick: () => void;
    active?: boolean;
    disabled?: boolean;
}

function editorViewBox(value: unknown): EditorViewBox {
    if (!isPlainObject(value)) {
        return { ...FLOWS_EDITOR_DEFAULT_VIEWBOX };
    }
    const x = value.x;
    const y = value.y;
    const w = value.w;
    const h = value.h;
    if (typeof x !== 'number' || typeof y !== 'number' || typeof w !== 'number' || typeof h !== 'number') {
        throw new Error('flows-bottom-toolbar: viewBox numbers required');
    }
    return { x, y, w, h };
}

export class FlowsBottomToolbar extends PlatformElement {
    static override styles: CSSResultGroup = [
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
    private _editor: ControllerFor<'flows/editor'>;

    constructor() {
        super();
        this._editor = this.useOp('flows/editor');
    }

    _viewBox(): EditorViewBox {
        return editorViewBox(this._editor.state.viewBox);
    }

    _setViewBox(viewBox: EditorViewBox) {
        this._editor.setViewBox({ viewBox });
    }

    _zoom(factor: number) {
        const viewBox = this._viewBox();
        const centerX = viewBox.x + viewBox.w / 2;
        const centerY = viewBox.y + viewBox.h / 2;
        const width = viewBox.w * factor;
        const height = viewBox.h * factor;
        this._setViewBox({ x: centerX - width / 2, y: centerY - height / 2, w: width, h: height });
    }

    _zoomIn() { this._zoom(1 / ZOOM_FACTOR); }
    _zoomOut() { this._zoom(ZOOM_FACTOR); }
    _zoom100() {
        const viewBox = this._viewBox();
        const next = FLOWS_EDITOR_DEFAULT_VIEWBOX;
        this._setViewBox({
            x: viewBox.x + viewBox.w / 2 - next.w / 2,
            y: viewBox.y + viewBox.h / 2 - next.h / 2,
            w: next.w,
            h: next.h,
        });
    }

    _fitView() {
        const nodes = getBranchNodes(this._editor.state);
        const viewBox = computeFitViewBox(Object.values(nodes));
        if (viewBox === null) {
            this._setViewBox({ ...FLOWS_EDITOR_DEFAULT_VIEWBOX });
            return;
        }
        this._setViewBox(viewBox);
    }

    _setTool(tool: string) { this._editor.setActiveTool({ tool }); }
    _undo() { this._editor.undo({}); }
    _redo() { this._editor.redo({}); }
    _openVariables() {
        const flowConfig = this._editor.state.flowConfig;
        if (!isPlainObject(flowConfig) || typeof flowConfig.flow_id !== 'string' || flowConfig.flow_id.length === 0) {
            throw new Error('flows-bottom-toolbar: flow_id required');
        }
        this.openModal('flows.variables', { scope: 'flow', flowId: flowConfig.flow_id });
    }
    _toggleGuides() { this._editor.toggleSmartGuides({}); }
    _toggleDataWires() { this._editor.toggleDataWires({}); }
    _toggleExecutionPanel() {
        this._editor.setExecutionPanelOpen({ open: this._editor.state.executionPanelOpen !== true });
    }
    _help() { this.openModal('flows.canvas_help', {}); }

    _renderIconButton({ icon, title, onClick, active = false, disabled = false }: ToolbarButton) {
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

    override render(): TemplateResult {
        const activeTool = this._editor.state.activeTool;
        const tool = typeof activeTool === 'string' && activeTool.length > 0 ? activeTool : 'select';
        const guidesOn = this._editor.state.smartGuidesEnabled !== false;
        const wiresOn = this._editor.state.showDataWires === true;
        const executionOpen = this._editor.state.executionPanelOpen === true;
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
                active: tool === 'select',
            })}
            ${this._renderIconButton({
                icon: 'drag-handle',
                title: this.t('canvas.toolbar.tool_pan'),
                onClick: () => this._setTool('pan'),
                active: tool === 'pan',
            })}

            <span class="divider"></span>

            ${this._renderIconButton({
                icon: 'undo',
                title: this.t('canvas.toolbar.undo'),
                onClick: () => this._undo(),
                disabled: this._editor.state.canUndo !== true,
            })}
            ${this._renderIconButton({
                icon: 'redo',
                title: this.t('canvas.toolbar.redo'),
                onClick: () => this._redo(),
                disabled: this._editor.state.canRedo !== true,
            })}

            <span class="divider"></span>

            ${this._renderIconButton({
                icon: 'chat',
                title: executionOpen
                    ? this.t('canvas.toolbar.close_execution_panel')
                    : this.t('canvas.toolbar.open_execution_panel'),
                onClick: () => this._toggleExecutionPanel(),
                active: executionOpen,
            })}
            ${this._renderIconButton({ icon: 'code', title: this.t('canvas.toolbar.open_variables'), onClick: () => this._openVariables() })}
            ${this._renderIconButton({
                icon: 'schema',
                title: this.t('canvas.toolbar.toggle_guides'),
                onClick: () => this._toggleGuides(),
                active: guidesOn,
            })}
            ${this._renderIconButton({
                icon: 'link',
                title: wiresOn ? this.t('canvas.dataflow.hide_wires') : this.t('canvas.dataflow.show_wires'),
                onClick: () => this._toggleDataWires(),
                active: wiresOn,
            })}
            ${this._renderIconButton({ icon: 'help', title: this.t('canvas.toolbar.help'), onClick: () => this._help() })}
        `;
    }
}

customElements.define('flows-bottom-toolbar', FlowsBottomToolbar);
