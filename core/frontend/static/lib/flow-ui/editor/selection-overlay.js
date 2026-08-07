import { LitElement, css, html, nothing } from '../../lit-shim.js';
import { flowUIEditorChromeTokens } from './editor-chrome.styles.js';

const HANDLE_CURSORS = Object.freeze({
    move: 'move',
    n: 'ns-resize',
    s: 'ns-resize',
    e: 'ew-resize',
    w: 'ew-resize',
    ne: 'nesw-resize',
    nw: 'nwse-resize',
    se: 'nwse-resize',
    sw: 'nesw-resize',
});

/**
 * Selection / resize handles outside the production iframe.
 * Emits layout-space gesture events; does not mutate the document.
 */
export class FlowUISelectionOverlay extends LitElement {
    static properties = {
        rect: { attribute: false },
        label: { type: String },
        handles: { attribute: false },
        ghostRect: { attribute: false },
        targetCell: { attribute: false },
        targetCellValid: { type: Boolean },
        previewRects: { attribute: false },
        structureRects: { attribute: false },
        hoveredComponentId: { type: String },
        interactive: { type: Boolean },
        menuEnabled: { type: Boolean },
        menuLabel: { type: String },
    };

    static styles = [
        flowUIEditorChromeTokens,
        css`
        :host {
            position: absolute;
            inset: 0;
            pointer-events: none;
            z-index: 20;
        }
        .structure {
            position: absolute;
            border: 1px solid var(--flow-ui-editor-hover);
            box-sizing: border-box;
            pointer-events: none;
        }
        .structure[data-selected='true'] {
            border-color: transparent;
        }
        .box {
            position: absolute;
            border: 1.5px solid var(--flow-ui-editor-select);
            box-shadow: none;
            pointer-events: auto;
            cursor: move;
            box-sizing: border-box;
        }
        .box[data-locked='true'] {
            pointer-events: none;
            cursor: default;
        }
        .label {
            position: absolute;
            left: -1.5px;
            bottom: 100%;
            padding: 2px 6px;
            border-radius: 4px 4px 0 0;
            background: var(--flow-ui-editor-select-label);
            color: var(--flow-ui-editor-label-fg);
            font: 600 10px/1.3 var(--font-sans);
            pointer-events: none;
            white-space: nowrap;
        }
        .handle {
            position: absolute;
            width: 8px;
            height: 8px;
            margin: -4px 0 0 -4px;
            border-radius: 1px;
            background: var(--flow-ui-editor-handle-bg);
            border: 1.5px solid var(--flow-ui-editor-select);
            box-sizing: border-box;
            pointer-events: auto;
            z-index: 2;
        }
        .kebab {
            position: absolute;
            z-index: 4;
            width: 22px;
            height: 22px;
            margin: 0;
            padding: 0;
            border: 1px solid color-mix(in srgb, var(--flow-ui-editor-select) 55%, transparent);
            border-radius: 6px;
            background: var(--flow-ui-editor-handle-bg);
            color: var(--flow-ui-editor-select);
            font: 700 14px/1 var(--font-sans);
            letter-spacing: 0;
            cursor: pointer;
            pointer-events: auto;
            display: grid;
            place-items: center;
            box-shadow: 0 1px 4px color-mix(in srgb, var(--text-primary, #000) 12%, transparent);
        }
        .kebab:hover {
            background: var(--flow-ui-editor-select);
            color: var(--flow-ui-editor-label-fg);
        }
        .kebab:focus-visible {
            outline: 2px solid var(--flow-ui-editor-select);
            outline-offset: 1px;
        }
        .ghost {
            position: absolute;
            border: 1.5px dashed var(--flow-ui-editor-select);
            background: var(--flow-ui-editor-select-fill);
            pointer-events: none;
            box-sizing: border-box;
        }
        .target-cell {
            position: absolute;
            border: 1.5px solid var(--flow-ui-editor-insert);
            background: var(--flow-ui-editor-insert-fill);
            border-radius: 4px;
            pointer-events: none;
            box-sizing: border-box;
            z-index: 2;
        }
        /* Where each sibling ends up once the dragged element is inserted. */
        .preview-cell {
            position: absolute;
            border: 1px dashed var(--flow-ui-editor-hover);
            border-radius: 4px;
            pointer-events: none;
            box-sizing: border-box;
            z-index: 1;
        }
        /* Taken cells: the gesture will not commit, so the aim reads as refused. */
        .target-cell[data-valid='false'] {
            border-color: var(--flow-ui-editor-reject);
            border-style: dashed;
            background: var(--flow-ui-editor-reject-fill);
        }
    `];

    constructor() {
        super();
        this.rect = null;
        this.label = '';
        this.handles = Object.freeze([]);
        this.ghostRect = null;
        this.targetCell = null;
        this.targetCellValid = true;
        this.previewRects = Object.freeze([]);
        this.structureRects = Object.freeze([]);
        this.hoveredComponentId = '';
        this.interactive = true;
        this.menuEnabled = true;
        this.menuLabel = 'Menu';
        this._activePointerId = null;
        this._gestureKind = null;
    }

    _emit(type, detail) {
        this.dispatchEvent(new CustomEvent(type, {
            bubbles: true,
            composed: true,
            detail,
        }));
    }

    _onPointerDown(event, kind) {
        if (!this.interactive || !this.rect) return;
        if (event.button !== 0) return;
        event.preventDefault();
        event.stopPropagation();
        this._activePointerId = event.pointerId;
        this._gestureKind = kind;
        event.currentTarget.setPointerCapture(event.pointerId);
        this._emit('selection-gesture-start', {
            kind,
            clientX: event.clientX,
            clientY: event.clientY,
            pointerId: event.pointerId,
        });
    }

    _onPointerMove(event) {
        if (this._activePointerId !== event.pointerId || !this._gestureKind) return;
        event.preventDefault();
        this._emit('selection-gesture-move', {
            kind: this._gestureKind,
            clientX: event.clientX,
            clientY: event.clientY,
            pointerId: event.pointerId,
        });
    }

    _onPointerUp(event) {
        if (this._activePointerId !== event.pointerId) return;
        event.preventDefault();
        const kind = this._gestureKind;
        this._activePointerId = null;
        this._gestureKind = null;
        if (event.currentTarget.hasPointerCapture(event.pointerId)) {
            event.currentTarget.releasePointerCapture(event.pointerId);
        }
        this._emit('selection-gesture-end', {
            kind,
            clientX: event.clientX,
            clientY: event.clientY,
            pointerId: event.pointerId,
            cancelled: false,
        });
    }

    _handleStyle(kind, rect) {
        const midX = rect.x + rect.width / 2;
        const midY = rect.y + rect.height / 2;
        const right = rect.x + rect.width;
        const bottom = rect.y + rect.height;
        const positions = {
            n: { left: midX, top: rect.y },
            s: { left: midX, top: bottom },
            e: { left: right, top: midY },
            w: { left: rect.x, top: midY },
            ne: { left: right, top: rect.y },
            nw: { left: rect.x, top: rect.y },
            se: { left: right, top: bottom },
            sw: { left: rect.x, top: bottom },
        };
        const pos = positions[kind];
        if (!pos) return '';
        return `left:${pos.left}px;top:${pos.top}px;cursor:${HANDLE_CURSORS[kind] || 'default'}`;
    }

    _kebabStyle(rect) {
        const left = Math.max(rect.x + 4, rect.x + rect.width - 26);
        const top = Math.max(4, rect.y + 4);
        return `left:${left}px;top:${top}px`;
    }

    _openMenu(event, componentId, rect) {
        event.preventDefault();
        event.stopPropagation();
        if (!this.menuEnabled || !this.interactive) return;
        if (typeof componentId !== 'string' || componentId === '') return;
        if (!rect) return;
        this._emit('component-menu-open', {
            componentId,
            clientX: event.clientX,
            clientY: event.clientY,
            anchorRect: {
                x: rect.x,
                y: rect.y,
                width: rect.width,
                height: rect.height,
            },
        });
    }

    _renderKebab(componentId, rect) {
        if (!this.menuEnabled || !this.interactive) return nothing;
        if (!rect || typeof componentId !== 'string' || componentId === '') return nothing;
        return html`<button
            type="button"
            class="kebab"
            style=${this._kebabStyle(rect)}
            title=${this.menuLabel}
            aria-label=${this.menuLabel}
            @pointerdown=${(event) => {
                event.preventDefault();
                event.stopPropagation();
            }}
            @click=${(event) => this._openMenu(event, componentId, rect)}
        >⋮</button>`;
    }

    render() {
        const structure = Array.isArray(this.structureRects) ? this.structureRects : [];
        const selectedId = this.label;
        const hoveredId = this.hoveredComponentId || '';
        const handleSet = new Set(Array.isArray(this.handles) ? this.handles : []);
        const canMove = handleSet.has('move');
        const resizeHandles = [...handleSet].filter((h) => h !== 'move');
        const locked = !this.interactive || (!canMove && resizeHandles.length === 0);
        const rect = this.rect;
        const hoverItem = hoveredId && hoveredId !== selectedId
            ? structure.find((item) => item?.componentId === hoveredId)
            : null;

        return html`
            ${structure.map((item) => {
                if (!item?.rect) return nothing;
                const r = item.rect;
                return html`<div
                    class="structure"
                    data-selected=${item.componentId === selectedId ? 'true' : 'false'}
                    style=${`left:${r.x}px;top:${r.y}px;width:${r.width}px;height:${r.height}px`}
                ></div>`;
            })}
            ${(this.previewRects || []).map((item) => {
                if (!item?.rect) return nothing;
                const preview = item.rect;
                return html`<div
                    class="preview-cell"
                    style=${`left:${preview.x}px;top:${preview.y}px;width:${preview.width}px;height:${preview.height}px`}
                ></div>`;
            })}
            ${this.targetCell
                ? html`<div
                    class="target-cell"
                    data-valid=${this.targetCellValid === false ? 'false' : 'true'}
                    style=${`left:${this.targetCell.x}px;top:${this.targetCell.y}px;width:${this.targetCell.width}px;height:${this.targetCell.height}px`}
                ></div>`
                : nothing}
            ${this.ghostRect
                ? html`<div
                    class="ghost"
                    style=${`left:${this.ghostRect.x}px;top:${this.ghostRect.y}px;width:${this.ghostRect.width}px;height:${this.ghostRect.height}px`}
                ></div>`
                : nothing}
            ${rect
                ? html`
                    <div
                        class="box"
                        data-locked=${locked ? 'true' : 'false'}
                        style=${`left:${rect.x}px;top:${rect.y}px;width:${rect.width}px;height:${rect.height}px;cursor:${canMove ? 'move' : 'default'}`}
                        @pointerdown=${canMove ? (event) => this._onPointerDown(event, 'move') : undefined}
                        @pointermove=${this._onPointerMove}
                        @pointerup=${this._onPointerUp}
                        @pointercancel=${this._onPointerUp}
                    >
                        <span class="label">${this.label}</span>
                    </div>
                    ${resizeHandles.map((kind) => html`<div
                        class="handle"
                        data-kind=${kind}
                        style=${this._handleStyle(kind, rect)}
                        @pointerdown=${(event) => this._onPointerDown(event, kind)}
                        @pointermove=${this._onPointerMove}
                        @pointerup=${this._onPointerUp}
                        @pointercancel=${this._onPointerUp}
                    ></div>`)}
                    ${this._renderKebab(selectedId, rect)}
                `
                : nothing}
            ${hoverItem?.rect
                ? this._renderKebab(hoverItem.componentId, hoverItem.rect)
                : nothing}
        `;
    }
}

if (!customElements.get('flow-ui-selection-overlay')) {
    customElements.define('flow-ui-selection-overlay', FlowUISelectionOverlay);
}
