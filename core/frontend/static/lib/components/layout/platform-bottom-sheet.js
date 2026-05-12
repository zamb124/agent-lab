/**
 * platform-bottom-sheet — базовый компонент нижнего экрана (mobile shell 2026).
 *
 * Принцип:
 *   - Конкретные листы (kind = '<scope>.<name>') наследуются от PlatformBottomSheet,
 *     перекрывают renderBody() (+ опц. heading, snap, dismissible).
 *   - При импорте файла лист сам регистрирует свой kind в bottom-sheet-registry.
 *   - PlatformBottomSheetStack рендерит лист в DOM по state.bottomSheets.stack,
 *     проставляет `_sheetId`, `_sheetKind`, `props`, `open=true`. На закрытие
 *     dispatch'ит UI_BOTTOM_SHEET_CLOSED, чтобы reducer убрал элемент из стека.
 *
 * Поведение:
 *   - Появляется снизу, плавный slide-up + scrim. Drag-handle сверху + swipe-down закрывает.
 *   - Snap-points через property `snap`:  'half' (50dvh) | 'full' (90dvh). По умолчанию 'half'.
 *   - Размещается в `document.body` через _attachPortalToBody(), чтобы предки с backdrop-filter
 *     не ломали position:fixed (как у glass-modal).
 *   - Z-index: --platform-bottom-sheet-z-index.
 *
 * Запрет: ни fetch, ни прямого dispatch с обходом контракта. Только helpers.
 */

import { html, css } from 'lit';
import { PlatformElement } from '../../platform-element/index.js';
import { CoreEvents } from '../../events/contract.js';
import '../platform-icon.js';

const SNAP_HALF = 'half';
const SNAP_FULL = 'full';
const SWIPE_CLOSE_THRESHOLD_PX = 80;

export class PlatformBottomSheet extends PlatformElement {
    static properties = {
        ...PlatformElement.properties,
        open: { type: Boolean, reflect: true },
        snap: { type: String, reflect: true },
        heading: { type: String },
        dismissible: { type: Boolean },
        _sheetId: { state: true },
        _sheetKind: { state: true },
        _dragOffset: { state: true },
        _dragging: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            @keyframes platformBottomSheetIn {
                from { transform: translateY(100%); }
                to { transform: translateY(0); }
            }

            @keyframes platformBottomSheetScrimIn {
                from { opacity: 0; }
                to { opacity: 1; }
            }

            :host {
                display: none;
            }

            :host([open]) {
                display: block;
                position: fixed;
                inset: 0;
                z-index: var(--platform-bottom-sheet-z-index);
            }

            .scrim {
                position: absolute;
                inset: 0;
                background: var(--platform-bottom-sheet-scrim);
                animation: platformBottomSheetScrimIn var(--duration-normal) var(--easing-smooth) both;
            }

            .panel {
                position: absolute;
                left: 0;
                right: 0;
                bottom: 0;
                max-height: 90dvh;
                display: flex;
                flex-direction: column;
                background: var(--glass-solid-strong);
                backdrop-filter: blur(var(--glass-blur-medium)) saturate(180%);
                -webkit-backdrop-filter: blur(var(--glass-blur-medium)) saturate(180%);
                border-top: 1px solid var(--glass-border-medium);
                border-radius: var(--platform-bottom-sheet-radius) var(--platform-bottom-sheet-radius) 0 0;
                box-shadow: var(--glass-shadow-strong), var(--glass-inner-glow-medium);
                padding-bottom: max(var(--space-4), env(safe-area-inset-bottom, 0px));
                animation: platformBottomSheetIn var(--duration-normal) var(--easing-smooth) both;
                will-change: transform;
            }

            :host([snap='half']) .panel {
                max-height: 60dvh;
            }

            :host([snap='full']) .panel {
                max-height: 92dvh;
                min-height: 50dvh;
            }

            .drag-handle {
                position: relative;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: var(--space-2) 0 var(--space-1);
                cursor: grab;
                touch-action: none;
                flex-shrink: 0;
            }

            .drag-handle:active {
                cursor: grabbing;
            }

            .drag-handle-bar {
                width: 44px;
                height: 5px;
                border-radius: var(--radius-full);
                background: var(--glass-border-strong);
            }

            .header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-3);
                padding: var(--space-1) var(--space-5) var(--space-3);
                flex-shrink: 0;
            }

            .heading {
                flex: 1;
                font-size: var(--text-xl);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                margin: 0;
                letter-spacing: var(--tracking-tight);
            }

            .close-btn {
                width: 32px;
                height: 32px;
                display: flex;
                align-items: center;
                justify-content: center;
                background: var(--glass-tint-medium);
                border: none;
                border-radius: var(--radius-full);
                color: var(--text-secondary);
                cursor: pointer;
                transition: all var(--duration-fast) var(--easing-default);
                flex-shrink: 0;
            }

            .close-btn:hover {
                background: var(--glass-tint-strong);
                color: var(--text-primary);
            }

            .body {
                flex: 1 1 auto;
                min-height: 0;
                overflow-y: auto;
                -webkit-overflow-scrolling: touch;
                padding: 0 var(--space-5) var(--space-4);
            }
        `,
    ];

    constructor() {
        super();
        this.open = false;
        this.snap = SNAP_HALF;
        this.heading = '';
        this.dismissible = true;
        this._sheetId = null;
        this._sheetKind = null;
        this._dragOffset = 0;
        this._dragging = false;
        this._dragStartY = 0;
        this._panelEl = null;
        this._boundEscape = (e) => this._handleEscape(e);
        this._portalAttached = false;
        this._origParent = null;
        this._origNextSibling = null;
    }

    connectedCallback() {
        super.connectedCallback();
        document.addEventListener('keydown', this._boundEscape);
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        document.removeEventListener('keydown', this._boundEscape);
        // Лист удаляется из DOM (через el.remove() в PlatformBottomSheetStack либо
        // переезжает на портал) — оба случая допустимы. Восстанавливать предка не нужно:
        // когда PlatformBottomSheetStack снимает лист, обратное вкорневление в стек
        // оживило бы только что закрытый лист обратно (классическая «шторка не закрывается»).
        // Просто чистим внутренние ссылки.
        this._portalAttached = false;
        this._origParent = null;
        this._origNextSibling = null;
    }

    updated(changed) {
        super.updated && super.updated(changed);
        if (changed.has('open') && this.open) {
            this._attachPortalToBody();
        }
        if (this.shadowRoot) {
            this._panelEl = this.shadowRoot.querySelector('.panel');
        }
    }

    _attachPortalToBody() {
        if (this._portalAttached) return;
        if (this.parentNode === document.body) {
            this._portalAttached = true;
            return;
        }
        this._origParent = this.parentNode;
        this._origNextSibling = this.nextSibling;
        document.body.appendChild(this);
        this._portalAttached = true;
    }

    _handleEscape(e) {
        if (!this.open) return;
        if (e.key !== 'Escape') return;
        if (!this.dismissible) return;
        e.preventDefault();
        this._requestClose();
    }

    _onScrimClick() {
        if (!this.dismissible) return;
        this._requestClose();
    }

    _onCloseClick() {
        this._requestClose();
    }

    _requestClose() {
        const payload = {};
        if (this._sheetId) payload.id = this._sheetId;
        else if (this._sheetKind) payload.kind = this._sheetKind;
        this.dispatch(CoreEvents.UI_BOTTOM_SHEET_CLOSED, payload);
    }

    _onHandlePointerDown(e) {
        if (!this.dismissible) return;
        if (e.pointerType === 'mouse' && e.button !== 0) return;
        this._dragging = true;
        this._dragStartY = e.clientY;
        this._dragOffset = 0;
        const target = e.currentTarget;
        try { target.setPointerCapture(e.pointerId); } catch { /* ignore */ }
    }

    _onHandlePointerMove(e) {
        if (!this._dragging) return;
        const dy = e.clientY - this._dragStartY;
        this._dragOffset = Math.max(0, dy);
        if (this._panelEl) {
            this._panelEl.style.transform = `translateY(${this._dragOffset}px)`;
        }
    }

    _onHandlePointerUp(e) {
        if (!this._dragging) return;
        this._dragging = false;
        const target = e.currentTarget;
        try { target.releasePointerCapture(e.pointerId); } catch { /* ignore */ }
        if (this._dragOffset >= SWIPE_CLOSE_THRESHOLD_PX) {
            this._requestClose();
        } else if (this._panelEl) {
            this._panelEl.style.transition = 'transform var(--duration-fast) var(--easing-smooth)';
            this._panelEl.style.transform = 'translateY(0)';
            setTimeout(() => {
                if (this._panelEl) this._panelEl.style.transition = '';
            }, 200);
        }
        this._dragOffset = 0;
    }

    /**
     * Подклассы перекрывают: возвращают вёрстку тела листа.
     * По умолчанию — слот для отладки/композиции.
     */
    renderBody() {
        return html`<slot></slot>`;
    }

    /**
     * Подклассы перекрывают: вёрстка кастомного заголовка. По умолчанию — heading + close.
     */
    renderHeader() {
        const ariaClose = this.t('bottom_sheet.close_aria', null, 'platform');
        return html`
            <div class="header">
                <h2 class="heading">${this.heading}</h2>
                ${this.dismissible
                    ? html`
                        <button
                            type="button"
                            class="close-btn"
                            aria-label=${ariaClose}
                            @click=${this._onCloseClick}
                        >
                            <platform-icon name="close" size="18"></platform-icon>
                        </button>
                    `
                    : ''}
            </div>
        `;
    }

    render() {
        const ariaDrag = this.t('bottom_sheet.drag_handle_aria', null, 'platform');
        return html`
            <div class="scrim" @click=${this._onScrimClick}></div>
            <div
                class="panel"
                role="dialog"
                aria-modal="true"
                aria-label=${this.heading || this._sheetKind || 'bottom-sheet'}
            >
                <div
                    class="drag-handle"
                    role="button"
                    aria-label=${ariaDrag}
                    @pointerdown=${this._onHandlePointerDown}
                    @pointermove=${this._onHandlePointerMove}
                    @pointerup=${this._onHandlePointerUp}
                    @pointercancel=${this._onHandlePointerUp}
                >
                    <span class="drag-handle-bar"></span>
                </div>
                ${this.renderHeader()}
                <div class="body">${this.renderBody()}</div>
            </div>
        `;
    }
}

customElements.define('platform-bottom-sheet', PlatformBottomSheet);
