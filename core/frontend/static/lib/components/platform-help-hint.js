/**
 * Подсказка по hover / focus. По умолчанию — кнопка «?»; опционально слот-контент
 * (кастомный триггер). Пузырёк в document.body (z-index из nextModalLayerZIndex).
 * Свойство strategy для совместимости; `wide` — широкий моноширинный режим (JSON).
 * Для сложных подсказок доступны `summary`, `details`, `docHref`, `docLabel`.
 * `fill` растягивает кастомный slotted trigger на всю область хоста.
 * `placement`: `auto` — не вылезать за верх вьюпорта (снизу от якоря), `top` / `bottom` — жёстко.
 * `size`: `md` — кнопка 32×32 (как `flows-node-run-control`).
 */
import { html, css } from '../../assets/js/lit/lit.min.js';
import { PlatformElement } from '../platform-element/index.js';
import { nextModalLayerZIndex } from '../utils/modal-z-stack.js';

const PORTAL_STYLE_ID = 'platform-help-hint-portal-styles-v2';
const PORTAL_GAP_PX = 8;
const VIEWPORT_TOP_INSET_PX = 4;
const VIEWPORT_SIDE_INSET_PX = 8;

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
        .platform-help-hint-portal-summary {
            margin: 0 0 4px;
            color: var(--text-primary, rgba(255, 255, 255, 0.95));
            font-size: 12px;
            font-weight: 650;
            line-height: 1.3;
        }
        .platform-help-hint-portal-body {
            color: var(--text-secondary, rgba(255, 255, 255, 0.74));
        }
        .platform-help-hint-portal-link {
            display: inline-flex;
            align-items: center;
            margin-top: 8px;
            color: var(--accent, #60a5fa);
            font-weight: 600;
            text-decoration: none;
        }
        .platform-help-hint-portal-link:hover,
        .platform-help-hint-portal-link:focus {
            text-decoration: underline;
            outline: none;
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

            :host([fill]) {
                width: 100%;
                height: 100%;
            }

            .hint-root {
                position: relative;
                display: inline-flex;
                align-items: center;
                cursor: help;
            }

            :host([fill]) .hint-root {
                width: 100%;
                height: 100%;
            }

            :host([fill]) .hint-root ::slotted(*) {
                width: 100%;
                height: 100%;
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

            :host([size='md']) .hint-btn {
                width: 32px;
                height: 32px;
                font-size: 14px;
                border-radius: var(--radius-md, 8px);
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
        summary: { type: String },
        details: { type: String },
        docHref: { type: String, attribute: 'doc-href' },
        docLabel: { type: String, attribute: 'doc-label' },
        label: { type: String },
        strategy: { type: String },
        /** @type {'auto'|'top'|'bottom'} */
        placement: { type: String, reflect: true },
        /** Площадь кнопки как у flows-node-run-control (32×32). */
        size: { type: String, reflect: true },
        wide: { type: Boolean, reflect: true },
        fill: { type: Boolean, reflect: true },
        _open: { state: true },
    };

    constructor() {
        super();
        this.text = '';
        this.summary = '';
        this.details = '';
        this.docHref = '';
        this.docLabel = '';
        this.label = 'Справка';
        this.strategy = 'portal';
        this.placement = 'auto';
        this.size = '';
        this.wide = false;
        this.fill = false;
        this._open = false;
        this._bubbleId = `platform-help-hint-${Math.random().toString(36).slice(2, 10)}`;
        this._closeTimer = null;
        this._portalBubble = null;
        this._bubbleZ = 0;
        this._onGlobalScroll = this._onGlobalScroll.bind(this);
        this._onGlobalKeydown = this._onGlobalKeydown.bind(this);
        this._onGlobalPointerDown = this._onGlobalPointerDown.bind(this);
        this._onPortalBubbleEnter = () => this._cancelClose();
        this._onPortalBubbleLeave = () => this._scheduleClose();
        this._onPortalBubbleFocusIn = () => this._cancelClose();
        this._onPortalBubbleFocusOut = (e) => this._onPortalFocusOut(e);
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
                window.addEventListener('pointerdown', this._onGlobalPointerDown, true);
            } else {
                this._teardownPortal();
                this._detachGlobalListeners();
            }
        } else if (
            this._open
            && this._portalBubble
            && (
                changed.has('text')
                || changed.has('summary')
                || changed.has('details')
                || changed.has('docHref')
                || changed.has('docLabel')
                || changed.has('label')
            )
        ) {
            this._updatePortalContent();
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
        window.removeEventListener('pointerdown', this._onGlobalPointerDown, true);
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

    _onGlobalPointerDown(e) {
        if (!this._open) {
            return;
        }
        const target = e.target;
        const root = this.renderRoot?.querySelector('.hint-root');
        if ((root && root.contains(target)) || (this._portalBubble && this._portalBubble.contains(target))) {
            return;
        }
        this._closeNow();
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

    _hasDocLink() {
        return typeof this.docHref === 'string' && this.docHref.trim() !== '';
    }

    _textValue(value) {
        return typeof value === 'string' ? value.trim() : '';
    }

    _appendPortalText(className, text) {
        const value = this._textValue(text);
        if (value === '' || !this._portalBubble) {
            return;
        }
        const node = document.createElement('div');
        node.className = className;
        node.textContent = value;
        this._portalBubble.appendChild(node);
    }

    _updatePortalContent() {
        if (!this._portalBubble) {
            return;
        }
        const summary = this._textValue(this.summary);
        const details = this._textValue(this.details);
        const text = this._textValue(this.text);
        this._portalBubble.textContent = '';
        this._portalBubble.setAttribute('role', this._hasDocLink() ? 'dialog' : 'tooltip');
        if (this._hasDocLink()) {
            this._portalBubble.setAttribute('aria-label', summary || this.label);
            this._portalBubble.setAttribute('aria-modal', 'false');
        } else {
            this._portalBubble.removeAttribute('aria-label');
            this._portalBubble.removeAttribute('aria-modal');
        }
        if (this.wide && summary === '' && details === '' && !this._hasDocLink()) {
            this._portalBubble.textContent = text;
            return;
        }
        this._appendPortalText('platform-help-hint-portal-summary', summary);
        this._appendPortalText('platform-help-hint-portal-body', details || text);
        if (this._hasDocLink()) {
            const link = document.createElement('a');
            link.className = 'platform-help-hint-portal-link';
            link.href = this.docHref.trim();
            link.target = '_blank';
            link.rel = 'noopener noreferrer';
            link.textContent = this._textValue(this.docLabel) || 'Open documentation';
            this._portalBubble.appendChild(link);
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
        return topEdgeIfAbove >= VIEWPORT_TOP_INSET_PX;
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
        const anchorCenterX = r.left + r.width / 2;
        this._portalBubble.style.left = `${anchorCenterX}px`;

        const br = this._portalBubble.getBoundingClientRect();
        const vw = window.innerWidth;
        const bubbleW = br.width;
        const idealLeft = anchorCenterX - bubbleW / 2;
        const maxLeft = vw - VIEWPORT_SIDE_INSET_PX - bubbleW;
        const clampedLeft = Math.max(
            VIEWPORT_SIDE_INSET_PX,
            Math.min(idealLeft, Math.max(VIEWPORT_SIDE_INSET_PX, maxLeft)),
        );
        const clampedCenterX = clampedLeft + bubbleW / 2;
        if (Math.abs(clampedCenterX - anchorCenterX) > 0.5) {
            this._portalBubble.style.left = `${clampedCenterX}px`;
        }
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
        bubble.tabIndex = -1;
        bubble.style.zIndex = String(this._bubbleZ);
        bubble.addEventListener('mouseenter', this._onPortalBubbleEnter);
        bubble.addEventListener('mouseleave', this._onPortalBubbleLeave);
        bubble.addEventListener('focusin', this._onPortalBubbleFocusIn);
        bubble.addEventListener('focusout', this._onPortalBubbleFocusOut);
        document.body.appendChild(bubble);
        this._portalBubble = bubble;
        this._updatePortalContent();
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
            this._portalBubble.removeEventListener('focusin', this._onPortalBubbleFocusIn);
            this._portalBubble.removeEventListener('focusout', this._onPortalBubbleFocusOut);
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

    _onPortalFocusOut(e) {
        const related = e.relatedTarget;
        const root = this.renderRoot?.querySelector('.hint-root');
        if ((related && this._portalBubble?.contains(related)) || (root && related && root.contains(related))) {
            return;
        }
        this._scheduleClose();
    }

    _onRootClick(e) {
        e.stopPropagation();
        this._cancelClose();
        this._openBubble();
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
                @click=${this._onRootClick}
            >
                <slot>
                    <button type="button" class="hint-btn" aria-label=${this.label}>?</button>
                </slot>
            </span>
        `;
    }
}

customElements.define('platform-help-hint', PlatformHelpHint);
