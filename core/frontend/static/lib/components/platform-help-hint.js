/**
 * Подсказка по hover / focus. По умолчанию — кнопка «?»; опционально слот-контент
 * (кастомный триггер). Пузырёк в document.body (z-index из nextModalLayerZIndex).
 * Свойство strategy для совместимости; `wide` — широкий моноширинный режим (JSON).
 * `placement`: `auto` — не вылезать за верх вьюпорта (снизу от якоря), `top` / `bottom` — жёстко.
 */
import { html, css } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import { nextModalLayerZIndex } from '../utils/modal-z-stack.js';

const PORTAL_STYLE_ID = 'platform-help-hint-portal-styles-v2';
const PORTAL_GAP_PX = 8;
const VIEWPORT_TOP_INSET_PX = 4;

function ensurePortalBubbleStyles() {
    if (typeof document === 'undefined' || document.getElementById(PORTAL_STYLE_ID)) {
        return;
    }
    const style = document.createElement('style');
    style.id = PORTAL_STYLE_ID;
    style.textContent = `
        .platform-help-hint-portal-bubble {
            position: fixed;
            min-width: 200px;
            max-width: min(280px, 70vw);
            padding: 10px 12px;
            font-size: 12px;
            font-weight: 400;
            line-height: 1.45;
            text-align: left;
            white-space: normal;
            color: var(--text-primary, rgba(255, 255, 255, 0.95));
            background: var(--glass-solid-strong, rgba(40, 40, 64, 0.98));
            border: 1px solid var(--border-default, rgba(255, 255, 255, 0.12));
            border-radius: var(--radius-md, 10px);
            box-shadow: var(--glass-shadow-strong, 0 8px 28px rgba(0, 0, 0, 0.35));
            pointer-events: auto;
            box-sizing: border-box;
        }
        .platform-help-hint-portal-bubble--above {
            transform: translate(-50%, calc(-100% - ${PORTAL_GAP_PX}px));
        }
        .platform-help-hint-portal-bubble--below {
            transform: translate(-50%, 0);
        }
        .platform-help-hint-portal-bubble--wide {
            min-width: 200px;
            max-width: min(560px, 92vw);
            max-height: 50vh;
            overflow: auto;
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 11px;
            line-height: 1.4;
            white-space: pre-wrap;
            word-break: break-word;
        }
    `;
    document.head.appendChild(style);
}

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
                cursor: help;
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

        `,
    ];

    static properties = {
        text: { type: String },
        label: { type: String },
        strategy: { type: String },
        /** @type {'auto'|'top'|'bottom'} */
        placement: { type: String, reflect: true },
        wide: { type: Boolean, reflect: true },
        _open: { state: true },
    };

    constructor() {
        super();
        this.text = '';
        this.label = 'Справка';
        this.strategy = 'portal';
        this.placement = 'auto';
        this.wide = false;
        this._open = false;
        this._bubbleId = `platform-help-hint-${Math.random().toString(36).slice(2, 10)}`;
        this._closeTimer = null;
        this._portalBubble = null;
        this._bubbleZ = 0;
        this._onGlobalScroll = this._onGlobalScroll.bind(this);
        this._onGlobalKeydown = this._onGlobalKeydown.bind(this);
        this._onPortalBubbleEnter = () => this._cancelClose();
        this._onPortalBubbleLeave = () => this._scheduleClose();
    }

    disconnectedCallback() {
        this._clearCloseTimer();
        this._detachGlobalListeners();
        this._teardownPortal();
        super.disconnectedCallback();
    }

    updated(changed) {
        super.updated(changed);
        if (changed.has('_open')) {
            if (this._open) {
                queueMicrotask(() => this._mountPortal());
                window.addEventListener('scroll', this._onGlobalScroll, true);
                window.addEventListener('resize', this._onGlobalScroll, true);
                window.addEventListener('keydown', this._onGlobalKeydown, true);
            } else {
                this._teardownPortal();
                this._detachGlobalListeners();
            }
        } else if (this._open && changed.has('text') && this._portalBubble) {
            this._portalBubble.textContent = this.text;
            requestAnimationFrame(() => {
                requestAnimationFrame(() => this._syncPortalPosition());
            });
        }
        if (this._open && this._portalBubble && changed.has('wide')) {
            this._applyWideClass();
            requestAnimationFrame(() => {
                requestAnimationFrame(() => this._syncPortalPosition());
            });
        }
        if (this._open && this._portalBubble && changed.has('placement')) {
            this._syncPortalPosition();
        }
    }

    _detachGlobalListeners() {
        window.removeEventListener('scroll', this._onGlobalScroll, true);
        window.removeEventListener('resize', this._onGlobalScroll, true);
        window.removeEventListener('keydown', this._onGlobalKeydown, true);
    }

    _onGlobalScroll() {
        if (!this._open) {
            return;
        }
        this._syncPortalPosition();
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

    _applyWideClass() {
        if (!this._portalBubble) {
            return;
        }
        if (this.wide) {
            this._portalBubble.classList.add('platform-help-hint-portal-bubble--wide');
        } else {
            this._portalBubble.classList.remove('platform-help-hint-portal-bubble--wide');
        }
    }

    /**
     * @param {DOMRect} anchor
     * @param {number} bubbleH
     * @returns {boolean}
     */
    _shouldPlaceAbove(anchor, bubbleH) {
        if (this.placement === 'top') {
            return true;
        }
        if (this.placement === 'bottom') {
            return false;
        }
        if (bubbleH <= 0) {
            return anchor.top >= 100;
        }
        const topEdgeIfAbove = anchor.top - PORTAL_GAP_PX - bubbleH;
        return topEdgeIfAbove >= VIEWPORT_TOP_INSET;
    }

    _syncPortalPosition() {
        if (!this._portalBubble) {
            return;
        }
        const root = this.renderRoot?.querySelector('.hint-root');
        if (!root) {
            return;
        }
        const r = root.getBoundingClientRect();
        const bubbleH = this._portalBubble.getBoundingClientRect().height;
        const above = this._shouldPlaceAbove(r, bubbleH);
        this._portalBubble.classList.remove('platform-help-hint-portal-bubble--above', 'platform-help-hint-portal-bubble--below');
        if (above) {
            this._portalBubble.classList.add('platform-help-hint-portal-bubble--above');
            this._portalBubble.style.top = `${r.top}px`;
        } else {
            this._portalBubble.classList.add('platform-help-hint-portal-bubble--below');
            this._portalBubble.style.top = `${r.bottom + PORTAL_GAP_PX}px`;
        }
        this._portalBubble.style.left = `${r.left + r.width / 2}px`;
    }

    _mountPortal() {
        if (!this._open) {
            return;
        }
        this._teardownPortal();
        const root = this.renderRoot?.querySelector('.hint-root');
        if (!root) {
            return;
        }
        ensurePortalBubbleStyles();
        this._bubbleZ = nextModalLayerZIndex();
        const bubble = document.createElement('div');
        bubble.id = this._bubbleId;
        bubble.className = 'platform-help-hint-portal-bubble';
        bubble.setAttribute('role', 'tooltip');
        bubble.textContent = this.text;
        bubble.style.zIndex = String(this._bubbleZ);
        bubble.addEventListener('mouseenter', this._onPortalBubbleEnter);
        bubble.addEventListener('mouseleave', this._onPortalBubbleLeave);
        document.body.appendChild(bubble);
        this._portalBubble = bubble;
        this._applyWideClass();
        this._syncPortalPosition();
        requestAnimationFrame(() => {
            requestAnimationFrame(() => this._syncPortalPosition());
        });
    }

    _teardownPortal() {
        if (this._portalBubble) {
            this._portalBubble.removeEventListener('mouseenter', this._onPortalBubbleEnter);
            this._portalBubble.removeEventListener('mouseleave', this._onPortalBubbleLeave);
            this._portalBubble.remove();
            this._portalBubble = null;
        }
    }

    _openBubble() {
        this._cancelClose();
        this._open = true;
    }

    _onRootEnter() {
        this._cancelClose();
        this._openBubble();
    }

    _onRootLeave() {
        this._scheduleClose();
    }

    _onRootFocusIn() {
        this._cancelClose();
        this._openBubble();
    }

    _onRootFocusOut(e) {
        const related = e.relatedTarget;
        if (related && this._portalBubble?.contains(related)) {
            return;
        }
        this._closeNow();
    }

    render() {
        return html`
            <span
                class="hint-root"
                aria-expanded=${this._open ? 'true' : 'false'}
                aria-describedby=${this._open ? this._bubbleId : ''}
                @mouseenter=${this._onRootEnter}
                @mouseleave=${this._onRootLeave}
                @focusin=${this._onRootFocusIn}
                @focusout=${this._onRootFocusOut}
            >
                <slot>
                    <button type="button" class="hint-btn" aria-label=${this.label}>?</button>
                </slot>
            </span>
        `;
    }
}

customElements.define('platform-help-hint', PlatformHelpHint);
