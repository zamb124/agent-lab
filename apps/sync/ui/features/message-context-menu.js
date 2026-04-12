/**
 * Контекстное меню сообщения (ПКМ) + полоска быстрых реакций
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { glassStyles } from '@platform/lib/styles/shared/glass.styles.js';
import { modalShellStyles } from '@platform/lib/platform-element/styles.js';

const QUICK_REACTIONS = ['😀', '👍', '🤝', '❤️', '😢', '🔥', '🤔'];

export class MessageContextMenu extends PlatformElement {
    static properties = {
        open: { type: Boolean, reflect: true },
        anchorX: { type: Number },
        anchorY: { type: Number },
        isOwn: { type: Boolean },
        selectionMode: { type: Boolean },
    };

    static styles = [
        PlatformElement.styles,
        glassStyles,
        modalShellStyles,
        css`
            :host {
                display: block;
                position: fixed;
                z-index: 200;
                left: 0;
                top: 0;
                right: 0;
                bottom: 0;
                width: auto;
                height: auto;
                pointer-events: auto;
            }

            .backdrop {
                position: absolute;
                inset: 0;
                z-index: 199;
                background: transparent;
                cursor: default;
            }

            .panel {
                position: absolute;
                z-index: 201;
                pointer-events: auto;
                min-width: 220px;
                border-radius: var(--radius-xl);
                border: 1px solid var(--glass-border-medium);
                background: var(--glass-solid-strong);
                backdrop-filter: blur(var(--glass-blur-strong));
                box-shadow: var(--glass-shadow-strong);
                padding: var(--space-2);
            }

            .reactions {
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                gap: var(--space-1);
                margin-bottom: var(--space-2);
                padding-bottom: var(--space-2);
                border-bottom: 1px solid var(--glass-border-subtle);
            }

            .reaction-btn {
                font-size: 20px;
                line-height: 1;
                padding: 4px 6px;
                border: none;
                border-radius: var(--radius-md);
                background: var(--glass-solid-subtle);
                cursor: pointer;
            }

            .reaction-btn:hover {
                background: var(--glass-solid-medium);
            }

            .item {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                width: 100%;
                text-align: left;
                padding: var(--space-2) var(--space-3);
                border: none;
                border-radius: var(--radius-md);
                background: transparent;
                color: var(--text-primary);
                font-size: var(--text-sm);
                cursor: pointer;
            }

            .item:hover {
                background: var(--glass-solid-subtle);
            }

            .item.danger {
                color: var(--error);
            }

            .item-label {
                flex: 1;
            }
        `,
    ];

    constructor() {
        super();
        this.open = false;
        this.anchorX = 0;
        this.anchorY = 0;
        this.isOwn = false;
        this.selectionMode = false;
        /** @type {(() => void) | null} */
        this._i18nUnsub = null;
    }

    connectedCallback() {
        super.connectedCallback();
        this._i18nUnsub = this.i18n.subscribe(() => this.requestUpdate());
    }

    disconnectedCallback() {
        super.disconnectedCallback?.();
        this._i18nUnsub?.();
        this._i18nUnsub = null;
    }

    _tp(key, params) {
        return this.i18n.t(key, params ?? {});
    }

    _emit(kind, detail = {}) {
        this.emit('menu-action', { kind, ...detail });
    }

    _close() {
        this.emit('close');
    }

    /**
     * Координаты клика (clientX/Y) в системе отсчёта этого хоста.
     * Хост — fixed inset:0 в том же containing block, что и раньше был «сдвинутый» fixed;
     * панель — position:absolute внутри хоста, без второго вложенного fixed у viewport.
     */
    _position() {
        const margin = 8;
        const panelW = 260;
        const panelH = 320;
        const r = this.getBoundingClientRect();
        let x = this.anchorX - r.left;
        let y = this.anchorY - r.top;
        x = Math.min(x, r.width - panelW - margin);
        y = Math.min(y, r.height - panelH - margin);
        x = Math.max(margin, x);
        y = Math.max(margin, y);
        return { x, y };
    }

    render() {
        if (!this.open) return html``;
        const { x, y } = this._position();
        return html`
            <div class="backdrop modal-backdrop-no-animate" @click=${this._close}></div>
            <div class="panel" style=${`left:${x}px;top:${y}px`}>
                <div class="reactions" @click=${(e) => e.stopPropagation()}>
                    ${QUICK_REACTIONS.map(em => html`
                        <button type="button" class="reaction-btn" @click=${() => this._emit('react', { emoji: em })}>${em}</button>
                    `)}
                </div>
                <button type="button" class="item" @click=${() => this._emit('reply')}>
                    <span class="item-label">${this._tp('context_menu.reply')}</span>
                </button>
                <button type="button" class="item" @click=${() => this._emit('copy')}>
                    <span class="item-label">${this._tp('context_menu.copy_text')}</span>
                </button>
                <button type="button" class="item" @click=${() => this._emit('translate')}>
                    <span class="item-label">${this._tp('context_menu.translate')}</span>
                </button>
                ${this.isOwn ? html`
                    <button type="button" class="item" @click=${() => this._emit('edit')}>
                        <span class="item-label">${this._tp('context_menu.edit')}</span>
                    </button>
                ` : ''}
                <button type="button" class="item" @click=${() => this._emit('pin')}>
                    <span class="item-label">${this._tp('context_menu.pin')}</span>
                </button>
                <button type="button" class="item" @click=${() => this._emit('forward')}>
                    <span class="item-label">${this._tp('context_menu.forward')}</span>
                </button>
                <button type="button" class="item" @click=${() => this._emit('select')}>
                    <span class="item-label">${this._tp('context_menu.select')}</span>
                </button>
                <button type="button" class="item danger" @click=${() => this._emit('delete')}>
                    <span class="item-label">${this._tp('context_menu.delete')}</span>
                </button>
            </div>
        `;
    }
}

customElements.define('message-context-menu', MessageContextMenu);
