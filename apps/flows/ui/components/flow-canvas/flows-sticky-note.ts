/**
 * flows-sticky-note — заметка-стикер на канвасе.
 *
 * Раскладка: header (drag-grip + collapse/link/delete) + body (textarea) +
 * resize-handle. Body и handle скрываются при `collapsed`.
 *
 * События в родительский canvas:
 *   - `drag-start` { noteId, x, y, pointerId } — pointerdown на drag-grip;
 *   - `change`     { noteId, text } — input в textarea;
 *   - `collapse-toggle` { noteId, collapsed };
 *   - `link-toggle` { noteId, isLinked } — клик по link-кнопке: запросить
 *     включение режима выбора ноды (если не привязана) или отвязать;
 *   - `remove`     { noteId };
 *   - `resize-start` { noteId, x, y, pointerId } — pointerdown на resize-handle.
 *
 * Цвет — семантический токен: `warning_bg | info_bg | success_bg |
 * accent_secondary_subtle`.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/fields/platform-field.js';
import type {CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult} from 'lit';

const COLOR_ACCENT_VAR = Object.freeze({
    warning_bg: 'var(--warning)',
    info_bg: 'var(--info)',
    success_bg: 'var(--success)',
    accent_secondary_subtle: 'var(--accent-secondary)',
});

export class FlowsStickyNote extends PlatformElement {
    static override properties: PropertyDeclarations = {
        noteId: { type: String, attribute: 'note-id' },
        text: { type: String },
        colorToken: { type: String, attribute: 'color-token' },
        width: { type: Number },
        height: { type: Number },
        collapsed: { type: Boolean, reflect: true },
        attachedNodeId: { type: String, attribute: 'attached-node-id' },
        linkPending: { type: Boolean, attribute: 'link-pending', reflect: true },
    }
    declare noteId: string;
    declare text: string;
    declare colorToken: string;
    declare width: number;
    declare height: number;
    declare collapsed: boolean;
    declare attachedNodeId: string;
    declare linkPending: boolean;
;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        css`
            :host {
                --sticky-accent: var(--warning);
                display: flex;
                flex-direction: column;
                width: 100%;
                height: 100%;
                box-sizing: border-box;
                border-radius: var(--radius-md);
                box-shadow: var(--flows-canvas-sticky-inset);
                border: 1px solid color-mix(in oklab, var(--sticky-accent) 20%, var(--border-subtle));
                background:
                    linear-gradient(180deg, color-mix(in oklab, var(--sticky-accent) 7%, transparent), transparent 58%),
                    var(--flows-canvas-sticky-surface);
                position: relative;
                overflow: hidden;
            }
            :host([link-pending]) {
                outline: 2px dashed var(--accent);
                outline-offset: 2px;
            }
            .header {
                display: flex;
                align-items: center;
                gap: var(--space-1);
                padding: 4px 6px;
                min-height: 28px;
                box-sizing: border-box;
                border-bottom: 1px solid color-mix(in oklab, var(--sticky-accent) 14%, var(--border-subtle));
                background: color-mix(in oklab, var(--bg-elevated) 86%, var(--sticky-accent) 8%);
                cursor: move;
                touch-action: none;
                user-select: none;
            }
            :host([collapsed]) .header { border-bottom: none; }
            .grip {
                width: 14px;
                height: 14px;
                color: var(--text-tertiary);
                flex-shrink: 0;
                display: flex; align-items: center; justify-content: center;
            }
            .title {
                flex: 1;
                font-size: var(--text-xs);
                color: var(--text-secondary);
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
                pointer-events: none;
            }
            .header-actions {
                display: flex;
                align-items: center;
                gap: 2px;
                flex-shrink: 0;
            }
            .header-actions platform-button[data-active] {
                color: var(--accent);
            }
            .header-actions platform-button.sticky-delete:hover {
                color: var(--error);
                background: var(--error-bg);
            }

            .body {
                flex: 1;
                min-height: 0;
                padding: 14px 16px 18px 16px;
                box-sizing: border-box;
                position: relative;
                display: flex;
                flex-direction: column;
                background: transparent;
            }
            :host([collapsed]) .body { display: none; }
            platform-field {
                display: block;
                flex: 1;
                min-height: 0;
                --field-pill-textarea-min-height: var(--sticky-editor-min-height);
                --field-pill-textarea-resize: none;
                --field-pill-input-size: var(--text-base);
                --field-pill-input-weight: var(--font-normal);
            }

            .resize-handle {
                position: absolute;
                right: 2px;
                bottom: 2px;
                width: 12px;
                height: 12px;
                cursor: nwse-resize;
                touch-action: none;
                background: linear-gradient(
                    135deg,
                    transparent 0%,
                    transparent 50%,
                    var(--text-tertiary) 50%,
                    var(--text-tertiary) 60%,
                    transparent 60%,
                    transparent 70%,
                    var(--text-tertiary) 70%,
                    var(--text-tertiary) 80%,
                    transparent 80%
                );
            }
            :host([collapsed]) .resize-handle { display: none; }
        `,
    ];

    constructor() {
        super();
        this.noteId = '';
        this.text = '';
        this.colorToken = 'warning_bg';
        this.width = 200;
        this.height = 140;
        this.collapsed = false;
        this.attachedNodeId = '';
        this.linkPending = false;
    }

    override updated(changed: PropertyValues<this>): void {
        super.updated?.(changed);
        if (changed.has('colorToken')) {
            const cv = (COLOR_ACCENT_VAR as any)[this.colorToken];
            this.style.setProperty('--sticky-accent', typeof cv === 'string' && cv.length > 0 ? cv : COLOR_ACCENT_VAR.warning_bg);
        }
    }

    _onDragStart(e: CustomEvent) {
        if ((e as Record<string, any>).button !== 0) return;
        e.stopPropagation();
        this.emit('drag-start', {
            noteId: this.noteId,
            x: (e as Record<string, any>).clientX,
            y: (e as Record<string, any>).clientY,
            pointerId: (e as Record<string, any>).pointerId,
        });
    }

    _onInput(e: CustomEvent) {
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error('flows-sticky-note: change detail');
        }
        if (!('value' in d)) {
            throw new Error('flows-sticky-note: detail.value');
        }
        const v = d.value;
        if (typeof v !== 'string') {
            throw new Error('flows-sticky-note: detail.value must be string');
        }
        this.emit('change', { noteId: this.noteId, text: v });
    }

    _onToggleCollapse() {
        this.emit('collapse-toggle', { noteId: this.noteId, collapsed: !this.collapsed });
    }

    _onToggleLink() {
        this.emit('link-toggle', { noteId: this.noteId, isLinked: Boolean(this.attachedNodeId) });
    }

    _onDelete() {
        this.emit('remove', { noteId: this.noteId });
    }

    _onResizeStart(e: MouseEvent) {
        if (e.button !== 0) return;
        e.stopPropagation();
        this.emit('resize-start', {
            noteId: this.noteId,
            x: e.clientX,
            y: e.clientY,
            pointerId: (e as Record<string, any>).pointerId,
        });
    }

    _renderHeader() {
        const isLinked = Boolean(this.attachedNodeId);
        const linkActive = isLinked || this.linkPending;
        const linkTitle = this.linkPending
            ? this.t('canvas.sticky_note.link_cancel')
            : isLinked
                ? this.t('canvas.sticky_note.unlink')
                : this.t('canvas.sticky_note.link_start');
        return html`
            <div class="header" @pointerdown=${this._onDragStart} title=${this.t('canvas.sticky_note.drag_hint')}>
                <div class="grip">
                    <platform-icon name="drag-handle" size="14"></platform-icon>
                </div>
                <div class="title">${this.text ? this.text.split('\n')[0] : this.t('canvas.sticky_note.placeholder')}</div>
                <div class="header-actions" @pointerdown=${(e: Event) => e.stopPropagation()}>
                    <platform-button
                        variant="ghost"
                        icon-only
                        density="dense"
                        ?data-active=${linkActive}
                        aria-label=${linkTitle}
                        @click=${this._onToggleLink}
                    >
                        <platform-icon name="link" size="14"></platform-icon>
                    </platform-button>
                    <platform-button
                        variant="ghost"
                        icon-only
                        density="dense"
                        aria-label=${this.collapsed ? this.t('canvas.sticky_note.expand') : this.t('canvas.sticky_note.collapse')}
                        @click=${this._onToggleCollapse}
                    >
                        <platform-icon name=${this.collapsed ? 'chevron-down' : 'chevron-up'} size="14"></platform-icon>
                    </platform-button>
                    <platform-button
                        class="sticky-delete"
                        variant="ghost"
                        icon-only
                        density="dense"
                        aria-label=${this.t('canvas.sticky_note.delete')}
                        @click=${this._onDelete}
                    >
                        <platform-icon name="close" size="14"></platform-icon>
                    </platform-button>
                </div>
            </div>
        `;
    }

    override render(): TemplateResult {
        const rawHeight = Number(this.height);
        const noteHeight = Number.isFinite(rawHeight) && rawHeight > 0 ? rawHeight : 140;
        const editorMinHeight = Math.max(52, noteHeight - 62);
        return html`
            ${this._renderHeader()}
            <div class="body">
                <platform-field
                    mode="edit"
                    type="text"
                    pill-embed
                    style=${`--sticky-editor-min-height: ${editorMinHeight}px;`}
                    .value=${this.text}
                    .placeholder=${this.t('canvas.sticky_note.placeholder')}
                    @change=${this._onInput}
                    @pointerdown=${(e: Event) => e.stopPropagation()}
                ></platform-field>
            </div>
            <div class="resize-handle" @pointerdown=${this._onResizeStart}></div>
        `;
    }
}

customElements.define('flows-sticky-note', FlowsStickyNote);
