/**
 * flows-sticky-note — заметка-стикер на канвасе.
 *
 * Использует `<foreignObject>` родителя (SVG-канваса). Текст редактируется
 * прямо в textarea, при blur эмитит `change`. Resize-handle в правом нижнем
 * углу, drag-обработка — на родителе.
 *
 * Цвет — семантический токен: `warning_bg | info_bg | success_bg |
 * accent_secondary_subtle`. По умолчанию warning_bg.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

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
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                width: 100%;
                height: 100%;
                box-sizing: border-box;
                padding: var(--space-2);
                border-radius: var(--radius-md);
                box-shadow: var(--glass-shadow-medium);
                border: 1px solid var(--border-subtle);
                position: relative;
                overflow: hidden;
            }
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
            .delete-btn {
                position: absolute;
                top: 4px; right: 4px;
                width: 20px; height: 20px;
                display: none;
                align-items: center; justify-content: center;
                background: transparent;
                border: none;
                color: var(--text-tertiary);
                cursor: pointer;
                font-size: 14px;
                line-height: 1;
            }
            :host(:hover) .delete-btn { display: flex; }
            .delete-btn:hover { color: var(--error); }
        `,
    ];

    constructor() {
        super();
        this.noteId = '';
        this.text = '';
        this.colorToken = 'warning_bg';
        this.width = 200;
        this.height = 140;
    }

    _onInput(e) {
        this.emit('change', { noteId: this.noteId, text: e.target.value });
    }

    _onDelete() {
        this.emit('remove', { noteId: this.noteId });
    }

    _onResizeStart(e) {
        e.stopPropagation();
        this.emit('resize-start', { noteId: this.noteId, x: e.clientX, y: e.clientY });
    }

    updated(changed) {
        super.updated?.(changed);
        if (changed.has('colorToken')) {
            this.style.background = COLOR_VAR[this.colorToken] || COLOR_VAR.warning_bg;
        }
    }

    render() {
        return html`
            <textarea
                .value=${this.text}
                placeholder=${this.t('canvas.sticky_note.placeholder')}
                @input=${this._onInput}
            ></textarea>
            <button class="delete-btn" type="button" title=${this.t('canvas.sticky_note.delete')} @click=${this._onDelete}>×</button>
            <div class="resize-handle" @pointerdown=${this._onResizeStart}></div>
        `;
    }
}

customElements.define('flows-sticky-note', FlowsStickyNote);
