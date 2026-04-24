/**
 * flows-sticky-note — заметка-стикер на канвасе.
 *
 * Layout: header (drag-grip + collapse/link/delete) + body (textarea) +
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

const COLOR_VAR = Object.freeze({
    warning_bg: 'var(--warning-bg)',
    info_bg: 'var(--info-bg)',
    success_bg: 'var(--success-bg)',
    accent_secondary_subtle: 'var(--accent-secondary-subtle)',
});

export class FlowsStickyNote extends PlatformElement {
    static properties = {
        noteId: { type: String, attribute: 'note-id' },
        text: { type: String },
        colorToken: { type: String, attribute: 'color-token' },
        width: { type: Number },
        height: { type: Number },
        collapsed: { type: Boolean, reflect: true },
        attachedNodeId: { type: String, attribute: 'attached-node-id' },
        linkPending: { type: Boolean, attribute: 'link-pending', reflect: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                width: 100%;
                height: 100%;
                box-sizing: border-box;
                border-radius: var(--radius-md);
                box-shadow: var(--glass-shadow-medium);
                border: 1px solid var(--border-subtle);
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
                border-bottom: 1px solid rgba(0, 0, 0, 0.08);
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
            .icon-btn {
                width: 22px; height: 22px;
                display: inline-flex;
                align-items: center; justify-content: center;
                background: transparent;
                border: none;
                color: var(--text-tertiary);
                cursor: pointer;
                border-radius: var(--radius-md);
                padding: 0;
            }
            .icon-btn:hover { color: var(--text-primary); background: rgba(0, 0, 0, 0.06); }
            .icon-btn[data-active] { color: var(--accent); }
            .icon-btn.danger:hover { color: var(--error); background: rgba(239, 68, 68, 0.12); }

            .body {
                flex: 1;
                min-height: 0;
                padding: var(--space-2);
                box-sizing: border-box;
                position: relative;
            }
            :host([collapsed]) .body { display: none; }
            textarea {
                width: 100%;
                height: 100%;
                background: transparent;
                border: none;
                outline: none;
                resize: none;
                font: inherit;
                font-size: var(--text-sm);
                color: var(--text-primary);
                box-sizing: border-box;
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

    updated(changed) {
        super.updated?.(changed);
        if (changed.has('colorToken')) {
            const cv = COLOR_VAR[this.colorToken];
            this.style.background = typeof cv === 'string' && cv.length > 0 ? cv : COLOR_VAR.warning_bg;
        }
    }

    _onDragStart(e) {
        if (e.button !== 0) return;
        e.stopPropagation();
        this.emit('drag-start', {
            noteId: this.noteId,
            x: e.clientX,
            y: e.clientY,
            pointerId: e.pointerId,
        });
    }

    _onInput(e) {
        this.emit('change', { noteId: this.noteId, text: e.target.value });
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

    _onResizeStart(e) {
        if (e.button !== 0) return;
        e.stopPropagation();
        this.emit('resize-start', {
            noteId: this.noteId,
            x: e.clientX,
            y: e.clientY,
            pointerId: e.pointerId,
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
                <div class="header-actions" @pointerdown=${(e) => e.stopPropagation()}>
                    <button
                        class="icon-btn"
                        type="button"
                        ?data-active=${linkActive}
                        title=${linkTitle}
                        @click=${this._onToggleLink}
                    >
                        <platform-icon name="link" size="14"></platform-icon>
                    </button>
                    <button
                        class="icon-btn"
                        type="button"
                        title=${this.collapsed ? this.t('canvas.sticky_note.expand') : this.t('canvas.sticky_note.collapse')}
                        @click=${this._onToggleCollapse}
                    >
                        <platform-icon name=${this.collapsed ? 'chevron-down' : 'chevron-up'} size="14"></platform-icon>
                    </button>
                    <button
                        class="icon-btn danger"
                        type="button"
                        title=${this.t('canvas.sticky_note.delete')}
                        @click=${this._onDelete}
                    >
                        <platform-icon name="close" size="14"></platform-icon>
                    </button>
                </div>
            </div>
        `;
    }

    render() {
        return html`
            ${this._renderHeader()}
            <div class="body">
                <textarea
                    .value=${this.text}
                    placeholder=${this.t('canvas.sticky_note.placeholder')}
                    @input=${this._onInput}
                    @pointerdown=${(e) => e.stopPropagation()}
                ></textarea>
            </div>
            <div class="resize-handle" @pointerdown=${this._onResizeStart}></div>
        `;
    }
}

customElements.define('flows-sticky-note', FlowsStickyNote);
