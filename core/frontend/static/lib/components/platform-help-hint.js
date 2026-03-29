/**
 * Кнопка «?» со всплывающей подсказкой (hover / focus).
 * Текст подсказки — свойство text (обязательно при использовании).
 * Стратегии позиционирования:
 * - fixed (по умолчанию): тултип поверх модалок и скролл-контейнеров;
 * - local: тултип жестко привязан к кнопке внутри текущего блока.
 */
import { html, css } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import { nextModalLayerZIndex } from '../utils/modal-z-stack.js';

export class PlatformHelpHint extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: inline-flex;
                vertical-align: middle;
            }

            .hint-root {
                position: relative;
                display: inline-flex;
                align-items: center;
            }

            .hint-btn {
                width: 20px;
                height: 20px;
                padding: 0;
                margin: 0;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                font-size: 11px;
                font-weight: 600;
                line-height: 1;
                color: var(--text-tertiary, rgba(255, 255, 255, 0.45));
                background: rgba(255, 255, 255, 0.06);
                border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.1));
                border-radius: var(--radius-full, 999px);
                cursor: help;
                transition:
                    color var(--duration-fast, 0.2s) ease,
                    background var(--duration-fast, 0.2s) ease,
                    border-color var(--duration-fast, 0.2s) ease;
            }

            .hint-btn:hover,
            .hint-root:focus-within .hint-btn {
                color: var(--text-primary, rgba(255, 255, 255, 0.92));
                background: rgba(255, 255, 255, 0.1);
                border-color: var(--border-default, rgba(255, 255, 255, 0.14));
            }

            .hint-bubble {
                min-width: 200px;
                max-width: min(280px, 70vw);
                padding: 10px 12px;
                font-size: 12px;
                font-weight: 400;
                line-height: 1.45;
                color: var(--text-primary, rgba(255, 255, 255, 0.95));
                text-align: left;
                white-space: normal;
                background: var(--glass-solid-strong, rgba(40, 40, 64, 0.98));
                border: 1px solid var(--border-default, rgba(255, 255, 255, 0.12));
                border-radius: var(--radius-md, 10px);
                box-shadow: var(--glass-shadow-strong, 0 8px 28px rgba(0, 0, 0, 0.35));
                opacity: 0;
                visibility: hidden;
                pointer-events: none;
                transition:
                    opacity var(--duration-fast, 0.2s) ease,
                    visibility var(--duration-fast, 0.2s) ease;
            }

            .hint-bubble.fixed {
                position: fixed;
                transform: translate(-50%, -100%);
            }

            .hint-bubble.local {
                position: absolute;
                left: 50%;
                bottom: calc(100% + 8px);
                transform: translateX(-50%);
                z-index: var(--z-popover, 1200);
            }

            .hint-bubble.is-open {
                opacity: 1;
                visibility: visible;
                pointer-events: auto;
            }
        `,
    ];

    static properties = {
        text: { type: String },
        label: { type: String },
        strategy: { type: String },
        _open: { state: true },
        _bubbleLeft: { state: true },
        _bubbleTop: { state: true },
        _bubbleZ: { state: true },
    };

    constructor() {
        super();
        this.text = '';
        this.label = 'Справка';
        this.strategy = 'fixed';
        this._open = false;
        this._bubbleLeft = 0;
        this._bubbleTop = 0;
        this._bubbleZ = 0;
        this._bubbleId = `platform-help-hint-${Math.random().toString(36).slice(2, 10)}`;
        this._closeTimer = null;
        this._onGlobalScroll = this._onGlobalScroll.bind(this);
        this._onGlobalKeydown = this._onGlobalKeydown.bind(this);
    }

    disconnectedCallback() {
        this._clearCloseTimer();
        this._detachGlobalListeners();
        super.disconnectedCallback();
    }

    updated(changed) {
        super.updated(changed);
        if (changed.has('_open') || changed.has('strategy')) {
            if (this._open) {
                if (!this._isLocalStrategy()) {
                    window.addEventListener('scroll', this._onGlobalScroll, true);
                    window.addEventListener('resize', this._onGlobalScroll, true);
                }
                window.addEventListener('keydown', this._onGlobalKeydown, true);
            } else {
                this._detachGlobalListeners();
            }
        }
    }

    _detachGlobalListeners() {
        window.removeEventListener('scroll', this._onGlobalScroll, true);
        window.removeEventListener('resize', this._onGlobalScroll, true);
        window.removeEventListener('keydown', this._onGlobalKeydown, true);
    }

    _onGlobalScroll() {
        if (!this._open || this._isLocalStrategy()) {
            return;
        }
        this._syncBubblePosition(false);
    }

    _onGlobalKeydown(e) {
        if (e.key === 'Escape' && this._open) {
            this._closeNow();
        }
    }

    _clearCloseTimer() {
        if (this._closeTimer !== null) {
            clearTimeout(this._closeTimer);
            this._closeTimer = null;
        }
    }

    _scheduleClose() {
        this._clearCloseTimer();
        this._closeTimer = window.setTimeout(() => {
            this._closeTimer = null;
            this._open = false;
        }, 200);
    }

    _cancelClose() {
        this._clearCloseTimer();
    }

    _closeNow() {
        this._clearCloseTimer();
        this._open = false;
    }

    /**
     * @param {boolean} allocateZ — взять новый слой из стека (первое открытие)
     */
    _syncBubblePosition(allocateZ) {
        if (this._isLocalStrategy()) {
            return;
        }
        const btn = this.renderRoot?.querySelector('.hint-btn');
        if (!btn) {
            return;
        }
        const r = btn.getBoundingClientRect();
        if (allocateZ || !this._bubbleZ) {
            this._bubbleZ = nextModalLayerZIndex();
        }
        this._bubbleLeft = r.left + r.width / 2;
        this._bubbleTop = r.top - 8;
    }

    _openBubble() {
        this._cancelClose();
        if (!this._isLocalStrategy()) {
            this._syncBubblePosition(true);
        }
        this._open = true;
    }

    _isLocalStrategy() {
        return this.strategy === 'local';
    }

    _onBtnEnter() {
        this._cancelClose();
        this._openBubble();
    }

    _onBtnLeave() {
        this._scheduleClose();
    }

    _onBubbleEnter() {
        this._cancelClose();
    }

    _onBubbleLeave() {
        this._scheduleClose();
    }

    _onBtnFocusIn() {
        this._cancelClose();
        this._openBubble();
    }

    _onBtnFocusOut(e) {
        const related = e.relatedTarget;
        if (related && this.renderRoot?.contains(related)) {
            return;
        }
        this._closeNow();
    }

    render() {
        const bubbleStyleAttr = this._open && !this._isLocalStrategy()
            ? `left:${this._bubbleLeft}px;top:${this._bubbleTop}px;z-index:${this._bubbleZ}`
            : '';
        const bubbleStrategyClass = this._isLocalStrategy() ? 'local' : 'fixed';

        return html`
            <span class="hint-root">
                <button
                    type="button"
                    class="hint-btn"
                    aria-label=${this.label}
                    aria-expanded=${this._open ? 'true' : 'false'}
                    aria-describedby=${this._bubbleId}
                    @mouseenter=${this._onBtnEnter}
                    @mouseleave=${this._onBtnLeave}
                    @focusin=${this._onBtnFocusIn}
                    @focusout=${this._onBtnFocusOut}
                >
                    ?
                </button>
                <div
                    id=${this._bubbleId}
                    class="hint-bubble ${bubbleStrategyClass} ${this._open ? 'is-open' : ''}"
                    style=${bubbleStyleAttr}
                    role="tooltip"
                    @mouseenter=${this._onBubbleEnter}
                    @mouseleave=${this._onBubbleLeave}
                >
                    ${this.text}
                </div>
            </span>
        `;
    }
}

customElements.define('platform-help-hint', PlatformHelpHint);
