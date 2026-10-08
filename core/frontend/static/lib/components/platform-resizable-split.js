/**
 * Две панели с перетаскиваемой границей.
 *
 * Ширина боковой панели запоминается по `storage-key`, поэтому раскладка
 * переживает перезагрузку. Границу можно двигать и с клавиатуры — иначе
 * панель недоступна тем, кто не пользуется мышью.
 *
 * `collapsed` сжимает боковую панель до `collapsed-size` и убирает ручку,
 * не затирая настроенную ширину: при развороте возвращается прежний размер.
 *
 * @example
 * <platform-resizable-split storage-key="tree" min-size="220" max-size="480">
 *     <nav slot="side">...</nav>
 *     <main>...</main>
 * </platform-resizable-split>
 */

import { css, html } from '../lit-shim.js';

import { PlatformElement } from '../platform-element/index.js';
import { platformStorageKey } from '../utils/storage-keys.js';
import { storageGet, storageSet } from '../utils/platform-storage.js';

const KEYBOARD_STEP_PX = 16;

export class PlatformResizableSplit extends PlatformElement {
    static i18nNamespace = 'platform';

    static properties = {
        size: { type: Number },
        minSize: { type: Number, attribute: 'min-size' },
        maxSize: { type: Number, attribute: 'max-size' },
        side: { type: String },
        /** Ключ внутри scope сервиса; без него раскладка не сохраняется. */
        storageKey: { type: String, attribute: 'storage-key' },
        storageScope: { type: String, attribute: 'storage-scope' },
        disabled: { type: Boolean, reflect: true },
        collapsed: { type: Boolean, reflect: true },
        collapsedSize: { type: Number, attribute: 'collapsed-size' },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: flex;
                min-width: 0;
                min-height: 0;
                width: 100%;
                height: 100%;
            }

            :host([side='right']) {
                flex-direction: row-reverse;
            }

            .side {
                flex: 0 0 auto;
                min-width: 0;
                overflow: hidden;
            }

            .main {
                flex: 1;
                min-width: 0;
                overflow: hidden;
            }

            .handle {
                flex: 0 0 auto;
                width: 5px;
                margin: 0 -2px;
                border: none;
                padding: 0;
                background: transparent;
                cursor: col-resize;
                position: relative;
                z-index: 1;
                touch-action: none;
            }

            .handle::after {
                content: '';
                position: absolute;
                inset: 0 2px;
                background: transparent;
                transition: background-color 120ms ease;
            }

            .handle:hover::after,
            .handle.is-active::after {
                background: var(--accent);
            }

            .handle:focus-visible {
                outline: 2px solid var(--accent);
                outline-offset: 1px;
            }

            :host([disabled]) .handle,
            :host([collapsed]) .handle {
                display: none;
            }
        `,
    ];

    constructor() {
        super();
        this.size = 260;
        this.minSize = 180;
        this.maxSize = 520;
        this.side = 'left';
        this.storageKey = '';
        this.storageScope = 'core';
        this.disabled = false;
        this.collapsed = false;
        this.collapsedSize = 72;
        this._dragging = false;
        this._onPointerMove = this._onPointerMove.bind(this);
        this._onPointerUp = this._onPointerUp.bind(this);
    }

    connectedCallback() {
        super.connectedCallback();
        this._restoreSize();
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._detachDragListeners();
    }

    _fullStorageKey() {
        if (this.storageKey === '') {
            return null;
        }
        return platformStorageKey(this.storageScope, `split.${this.storageKey}`);
    }

    _restoreSize() {
        const key = this._fullStorageKey();
        if (key === null) {
            return;
        }
        const stored = storageGet(key);
        if (stored === null) {
            return;
        }
        const parsed = Number.parseInt(stored, 10);
        if (Number.isFinite(parsed)) {
            this.size = this._clamp(parsed);
        }
    }

    _persistSize() {
        const key = this._fullStorageKey();
        if (key === null) {
            return;
        }
        storageSet(key, String(this.size));
    }

    _clamp(value) {
        return Math.min(Math.max(value, this.minSize), this.maxSize);
    }

    _setSize(value) {
        const next = this._clamp(value);
        if (next === this.size) {
            return;
        }
        this.size = next;
        this.emit('split-resize', { size: next });
    }

    _sideWidth() {
        return this.collapsed ? this.collapsedSize : this.size;
    }

    _onPointerDown(event) {
        if (this.disabled || this.collapsed) {
            return;
        }
        event.preventDefault();
        this._dragging = true;
        this._dragOrigin = event.clientX;
        this._dragStartSize = this.size;
        window.addEventListener('pointermove', this._onPointerMove);
        window.addEventListener('pointerup', this._onPointerUp);
        this.requestUpdate();
    }

    _onPointerMove(event) {
        if (!this._dragging) {
            return;
        }
        const delta = event.clientX - this._dragOrigin;
        this._setSize(this.side === 'right' ? this._dragStartSize - delta : this._dragStartSize + delta);
    }

    _onPointerUp() {
        if (!this._dragging) {
            return;
        }
        this._dragging = false;
        this._detachDragListeners();
        this._persistSize();
        this.requestUpdate();
    }

    _detachDragListeners() {
        window.removeEventListener('pointermove', this._onPointerMove);
        window.removeEventListener('pointerup', this._onPointerUp);
    }

    _onHandleKeyDown(event) {
        if (this.collapsed) {
            return;
        }
        const towardsMain = this.side === 'right' ? 'ArrowLeft' : 'ArrowRight';
        const towardsSide = this.side === 'right' ? 'ArrowRight' : 'ArrowLeft';
        if (event.key === towardsMain) {
            event.preventDefault();
            this._setSize(this.size + KEYBOARD_STEP_PX);
            this._persistSize();
            return;
        }
        if (event.key === towardsSide) {
            event.preventDefault();
            this._setSize(this.size - KEYBOARD_STEP_PX);
            this._persistSize();
        }
    }

    render() {
        return html`
            <div class="side" style=${`width:${this._sideWidth()}px`} part="side">
                <slot name="side"></slot>
            </div>
            <div
                class=${this._dragging ? 'handle is-active' : 'handle'}
                role="separator"
                tabindex="0"
                aria-orientation="vertical"
                aria-valuenow=${this.size}
                aria-valuemin=${this.minSize}
                aria-valuemax=${this.maxSize}
                aria-label=${this.t('resizable_split.handle_aria')}
                @pointerdown=${this._onPointerDown}
                @keydown=${this._onHandleKeyDown}
            ></div>
            <div class="main" part="main">
                <slot></slot>
            </div>
        `;
    }
}

customElements.define('platform-resizable-split', PlatformResizableSplit);
