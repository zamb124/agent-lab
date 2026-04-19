/**
 * GlassModal - Базовый компонент модального окна
 * Apple Liquid Glass Design
 * Поддержка темной и светлой темы
 *
 * При открытии хост переносится в document.body: иначе предки с backdrop-filter
 * ломают position:fixed, модалка встаёт в поток и двигает вёрстку.
 * Общий modal.styles.js сюда не подмешиваем — там :host ломает разметку (flex + svg + оверлей).
 */
import { html, css } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import { nextModalLayerZIndex } from '../utils/modal-z-stack.js';
import { CoreEvents } from '../events/contract.js';
import './platform-icon.js';
import './platform-button.js';

export class GlassModal extends PlatformElement {
    static properties = {
        ...PlatformElement.properties,
        open: { type: Boolean, reflect: true },
        size: { type: String },
        heading: { type: String },
        title: { type: String },
        _modalId: { state: true },
        _modalKind: { state: true },
        _isFullscreen: { type: Boolean, state: true },
        _isDragging: { type: Boolean, state: true },
        _position: { type: Object, state: true },
        _panelEnterActive: { type: Boolean, state: true },
        hideHeaderClose: { type: Boolean },
        headerSavePrimary: { type: Boolean },
    };

    static styles = [
        PlatformElement.styles,
        css`
            /*
             * Вход через @keyframes + both (как modalShellStyles у thread-drawer): transition
             * с open + порталом в body часто не рисует «до», панель появляется мгновенно.
             */
            @keyframes glassModalBackdropIn {
                from {
                    opacity: 0;
                }
                to {
                    opacity: 1;
                }
            }

            @keyframes glassModalPanelIn {
                from {
                    opacity: 0;
                    transform: translate(-50%, calc(-50% + 12px)) scale(0.97);
                }
                to {
                    opacity: 1;
                    transform: translate(-50%, -50%) scale(1);
                }
            }

            :host {
                display: none;
                box-sizing: border-box;
            }

            :host([open]) {
                display: block;
                position: fixed;
                inset: 0;
                width: 100%;
                max-width: none;
                height: 100%;
                max-height: none;
                margin: 0;
                padding: 0;
                border: none;
                z-index: var(--platform-modal-layer-z, var(--z-modal, 1000));
            }

            :host([data-portal]) {
                left: 0;
                top: 0;
                right: 0;
                bottom: 0;
            }

            .modal-overlay {
                position: absolute;
                inset: 0;
                padding: max(var(--space-3), env(safe-area-inset-top, 0px))
                    max(var(--space-3), env(safe-area-inset-right, 0px))
                    max(var(--space-3), env(safe-area-inset-bottom, 0px))
                    max(var(--space-3), env(safe-area-inset-left, 0px));
                box-sizing: border-box;
                opacity: 0;
                visibility: hidden;
            }

            :host([open]) .modal-overlay {
                visibility: visible;
                animation: glassModalBackdropIn var(--modal-overlay-duration, var(--duration-normal)) var(--modal-enter-easing, var(--easing-smooth)) both;
            }

            .modal-scrim {
                position: absolute;
                inset: 0;
                z-index: 0;
                background: rgba(0, 0, 0, 0.3);
                backdrop-filter: blur(var(--glass-blur-subtle, 20px)) saturate(180%);
                -webkit-backdrop-filter: blur(var(--glass-blur-subtle, 20px)) saturate(180%);
            }

            /*
             * Центр панели: left/top 50% + translate(-50%,-50%). Тогда анимация width/height
             * идёт симметрично от центра (не из левого верхнего угла как у flex-центровки).
             */
            .modal {
                position: absolute;
                left: 50%;
                top: 50%;
                z-index: 1;
                width: 90%;
                max-width: min(500px, 100%);
                max-height: min(90vh, 100dvh);
                display: flex;
                flex-direction: column;
                overflow: hidden;
                min-height: 0;
                border-radius: var(--radius-3xl, 28px);
                padding: 0;
                box-sizing: border-box;

                --modal-content-inset: var(--space-2, 8px);
                --modal-content-radius: var(--radius-xl, 16px);

                background: var(--glass-solid-strong, rgba(40, 40, 40, 0.92));
                border: 1px solid var(--glass-border-medium, rgba(255, 255, 255, 0.12));

                backdrop-filter: blur(var(--glass-blur-medium, 40px)) saturate(180%);
                -webkit-backdrop-filter: blur(var(--glass-blur-medium, 40px)) saturate(180%);

                box-shadow: var(--glass-shadow-strong,
                    0 16px 48px rgba(0, 0, 0, 0.4),
                    0 4px 16px rgba(0, 0, 0, 0.25));

                transform: translate(-50%, calc(-50% + 12px)) scale(0.97);
                opacity: 0;
                transition: width var(--duration-normal, 0.3s) var(--modal-enter-easing, var(--easing-smooth)),
                    max-width var(--duration-normal, 0.3s) var(--modal-enter-easing, var(--easing-smooth)),
                    height var(--duration-normal, 0.3s) var(--modal-enter-easing, var(--easing-smooth)),
                    max-height var(--duration-normal, 0.3s) var(--modal-enter-easing, var(--easing-smooth)),
                    border-radius var(--duration-normal, 0.3s) var(--modal-enter-easing, var(--easing-smooth));
            }

            /*
             * Вход только пока висит .panel-enter-active; после animationend класс снимаем,
             * иначе при снятии .dragging анимация снова запускается с начала.
             */
            :host([open]) .modal.panel-enter-active {
                animation: glassModalPanelIn var(--modal-panel-duration, var(--duration-slow)) var(--modal-enter-easing, var(--modal-panel-easing, var(--easing-smooth))) both;
            }

            :host([open]) .modal:not(.panel-enter-active) {
                opacity: 1;
                transform: translate(-50%, -50%) scale(1);
            }

            :host([open]) .modal.dragging {
                animation: none !important;
                opacity: 1;
            }

            .modal.dragging {
                transition: width var(--duration-normal, 0.3s) var(--modal-enter-easing, var(--easing-smooth)),
                    max-width var(--duration-normal, 0.3s) var(--modal-enter-easing, var(--easing-smooth)),
                    height var(--duration-normal, 0.3s) var(--modal-enter-easing, var(--easing-smooth)),
                    max-height var(--duration-normal, 0.3s) var(--modal-enter-easing, var(--easing-smooth)),
                    border-radius var(--duration-normal, 0.3s) var(--modal-enter-easing, var(--easing-smooth));
                user-select: none;
            }

            .modal::before {
                content: '';
                position: absolute;
                top: 0;
                left: var(--space-4, 16px);
                right: var(--space-4, 16px);
                height: 1px;
                background: linear-gradient(
                    90deg,
                    transparent 0%,
                    rgba(255, 255, 255, 0.15) 20%,
                    rgba(255, 255, 255, 0.15) 80%,
                    transparent 100%
                );
                z-index: 1;
            }

            .modal::after {
                content: '';
                position: absolute;
                inset: 0;
                border-radius: var(--radius-3xl, 28px);
                background: linear-gradient(
                    135deg,
                    rgba(255, 255, 255, 0.04) 0%,
                    rgba(255, 255, 255, 0.01) 40%,
                    transparent 100%
                );
                pointer-events: none;
                z-index: 0;
            }

            .modal.sm { max-width: min(400px, 100%); }
            .modal.md { max-width: min(500px, 100%); }
            .modal.lg { max-width: min(640px, 100%); }
            .modal.xl { max-width: min(900px, 100%); }
            .modal.full {
                width: min(95vw, 100% - 2rem);
                max-width: min(95vw, 100% - 2rem);
                height: min(90vh, 100dvh - 2rem);
                max-height: min(95vh, 100dvh - 2rem);
            }

            .modal.fullscreen {
                width: min(96vw, 100vw - 1.5rem) !important;
                max-width: min(96vw, 100vw - 1.5rem) !important;
                height: min(94vh, 100dvh - 1.5rem) !important;
                max-height: min(94vh, 100dvh - 1.5rem) !important;
                border-radius: var(--radius-lg, 16px);
                --modal-content-radius: var(--radius-lg, 16px);
            }

            .modal-header {
                position: relative;
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-3, 12px);
                padding: var(--space-4, 16px) var(--space-4, 16px) 0 var(--space-4, 16px);
                z-index: 2;
                cursor: grab;
                user-select: none;
                flex-shrink: 0;
                align-self: stretch;
            }

            .modal-header:active {
                cursor: grabbing;
            }

            .modal-title {
                flex: 1;
                font-size: var(--text-xl, 20px);
                font-weight: var(--font-semibold, 600);
                color: var(--text-primary, rgba(255, 255, 255, 0.95));
                margin: 0;
                letter-spacing: var(--tracking-tight, -0.02em);
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }

            .header-buttons {
                display: flex;
                align-items: center;
                gap: var(--space-2, 8px);
                flex-shrink: 0;
            }

            .header-btn {
                width: 28px;
                height: 28px;
                display: flex;
                align-items: center;
                justify-content: center;
                background: var(--glass-tint-medium, rgba(255, 255, 255, 0.05));
                border: none;
                border-radius: var(--radius-full, 50%);
                color: var(--text-secondary, rgba(255, 255, 255, 0.65));
                font-size: var(--text-sm, 14px);
                cursor: pointer;
                transition: all var(--duration-fast, 0.2s) ease;
                flex-shrink: 0;
            }

            .header-btn:hover {
                background: var(--glass-tint-strong, rgba(255, 255, 255, 0.08));
                color: var(--text-primary, rgba(255, 255, 255, 0.95));
                transform: scale(1.08);
            }

            .header-btn platform-icon {
                display: flex;
            }

            .header-btn.header-save-btn--primary {
                background: var(--accent);
                color: var(--platform-btn-primary-text);
            }

            .header-btn.header-save-btn--primary:hover:not(:disabled) {
                background: var(--platform-btn-primary-hover);
                color: var(--platform-btn-primary-text);
                transform: scale(1.08);
            }

            .header-btn.header-save-btn--primary:disabled {
                opacity: 0.55;
                cursor: not-allowed;
                transform: none;
            }

            .modal-content {
                position: relative;
                color: var(--text-primary, rgba(255, 255, 255, 0.95));
                z-index: 2;
                flex: 1 1 auto;
                min-height: 0;
                min-width: 0;
                overflow-y: auto;
                overflow-x: hidden;
                -webkit-overflow-scrolling: touch;
                padding: var(--space-4, 16px);
                margin: 0 var(--modal-content-inset) var(--modal-content-inset);
                border-radius: var(--modal-content-radius);
                contain: paint style;
                isolation: isolate;
            }

            .modal.fullscreen .modal-content,
            .modal.full .modal-content {
                flex: 1;
                min-height: 0;
                height: auto;
                max-height: none;
            }

            .modal.fullscreen .modal-content:has(.graph-modal-body),
            .modal.full .modal-content:has(.graph-modal-body) {
                display: flex;
                flex-direction: column;
                overflow: hidden;
                margin: 0;
                border-radius: 0;
            }

            .modal-actions {
                position: relative;
                display: flex;
                gap: var(--space-3, 12px);
                padding: var(--space-4, 16px);
                padding-top: 0;
                z-index: 2;
                flex-shrink: 0;
                align-self: stretch;
                margin-left: var(--modal-content-inset);
                margin-right: var(--modal-content-inset);
            }

            .modal-actions:empty {
                display: none;
            }

            ::slotted([slot="actions"]) {
                display: flex;
                gap: var(--space-3, 12px);
                width: 100%;
            }

            @media (max-width: 768px) {
                .modal-overlay:has(.modal.fullscreen) {
                    padding: 0;
                }

                .modal {
                    width: 95%;
                    border-radius: var(--radius-2xl, 24px);
                }

                .modal.full {
                    width: min(95vw, 100% - 1rem);
                    max-width: min(95vw, 100% - 1rem);
                    height: min(92vh, 100dvh - 1rem);
                    max-height: min(92vh, 100dvh - 1rem);
                }

                .modal.fullscreen {
                    width: 100%;
                    max-width: 100%;
                    height: 100dvh;
                    max-height: 100dvh;
                    border-radius: 0;
                    margin: 0;
                }

                .modal.fullscreen .modal-header {
                    padding: max(var(--space-3, 12px), var(--platform-safe-top))
                        max(var(--space-3, 12px), var(--platform-safe-right)) 0
                        max(var(--space-3, 12px), var(--platform-safe-left));
                }

                .modal.fullscreen .modal-content {
                    padding: var(--space-3, 12px)
                        max(var(--space-3, 12px), var(--platform-safe-right))
                        var(--space-3, 12px)
                        max(var(--space-3, 12px), var(--platform-safe-left));
                }

                .modal.fullscreen .modal-actions {
                    padding: 0 max(var(--space-3, 12px), var(--platform-safe-right))
                        max(var(--space-3, 12px), var(--platform-safe-bottom))
                        max(var(--space-3, 12px), var(--platform-safe-left));
                }

                .modal::before {
                    left: var(--space-3, 12px);
                    right: var(--space-3, 12px);
                }

                .modal.fullscreen::before {
                    left: max(var(--space-3, 12px), var(--platform-safe-left));
                    right: max(var(--space-3, 12px), var(--platform-safe-right));
                }

                .modal-header {
                    padding: var(--space-3, 12px) var(--space-3, 12px) 0 var(--space-3, 12px);
                }

                .modal-content {
                    padding: var(--space-3, 12px);
                }

                .modal-actions {
                    padding: var(--space-3, 12px);
                    padding-top: 0;
                }
            }

            @media (max-width: 480px) {
                .modal {
                    border-radius: var(--radius-xl, 20px);
                }

                .modal.fullscreen {
                    border-radius: 0;
                }

                .modal-header {
                    padding: var(--space-2, 8px) var(--space-2, 8px) 0 var(--space-2, 8px);
                }

                .modal.fullscreen .modal-header {
                    padding: max(var(--space-2, 8px), var(--platform-safe-top))
                        max(var(--space-2, 8px), var(--platform-safe-right)) 0
                        max(var(--space-2, 8px), var(--platform-safe-left));
                }

                .modal-content {
                    padding: var(--space-2, 8px);
                }

                .modal.fullscreen .modal-content {
                    padding: var(--space-2, 8px) max(var(--space-2, 8px), var(--platform-safe-right)) var(--space-2, 8px)
                        max(var(--space-2, 8px), var(--platform-safe-left));
                }

                .modal-actions {
                    padding: var(--space-2, 8px);
                    padding-top: 0;
                    padding-bottom: max(var(--space-2, 8px), env(safe-area-inset-bottom, 0px));
                    flex-direction: column;
                }

                .modal.fullscreen .modal-actions {
                    padding: 0 max(var(--space-2, 8px), var(--platform-safe-right))
                        max(var(--space-2, 8px), var(--platform-safe-bottom))
                        max(var(--space-2, 8px), var(--platform-safe-left));
                    flex-direction: column;
                }

                .modal-title {
                    font-size: var(--text-lg, 18px);
                }
            }

            :host-context([data-theme="light"]) .modal-scrim {
                background: rgba(100, 100, 120, 0.25);
                backdrop-filter: blur(20px) saturate(120%);
                -webkit-backdrop-filter: blur(20px) saturate(120%);
            }

            :host-context([data-theme="light"]) .modal {
                background: linear-gradient(
                    145deg,
                    rgba(255, 255, 255, 0.95) 0%,
                    rgba(248, 250, 252, 0.98) 100%
                );
                border: 1px solid rgba(0, 0, 0, 0.06);
                box-shadow:
                    0 25px 60px rgba(0, 0, 0, 0.15),
                    0 10px 25px rgba(0, 0, 0, 0.08),
                    inset 0 1px 0 rgba(255, 255, 255, 1),
                    inset 0 -1px 0 rgba(0, 0, 0, 0.03);
            }

            :host-context([data-theme="light"]) .modal::before {
                background: linear-gradient(
                    90deg,
                    transparent 0%,
                    rgba(255, 255, 255, 1) 20%,
                    rgba(255, 255, 255, 1) 80%,
                    transparent 100%
                );
            }

            :host-context([data-theme="light"]) .modal::after {
                background: linear-gradient(
                    135deg,
                    rgba(255, 255, 255, 0.8) 0%,
                    rgba(255, 255, 255, 0.2) 50%,
                    transparent 100%
                );
            }

            :host-context([data-theme="light"]) .header-btn {
                background: rgba(15, 23, 42, 0.06);
                color: rgba(15, 23, 42, 0.5);
            }

            :host-context([data-theme="light"]) .header-btn:hover {
                background: rgba(15, 23, 42, 0.12);
                color: rgba(15, 23, 42, 0.9);
            }

            /*
             * Портал в body: при светлой теме документа :host-context(light) красит панель в белый.
             * data-theme="dark" на хосте принудительно возвращает тёмный glass (лендинг и т.п.).
             */
            :host([data-theme="dark"]) .modal-scrim {
                background: rgba(0, 0, 0, 0.3);
                backdrop-filter: blur(var(--glass-blur-subtle, 20px)) saturate(180%);
                -webkit-backdrop-filter: blur(var(--glass-blur-subtle, 20px)) saturate(180%);
            }

            :host([data-theme="dark"]) .modal {
                background: var(--glass-solid-strong, rgba(40, 40, 40, 0.92));
                border: 1px solid var(--glass-border-medium, rgba(255, 255, 255, 0.12));
                box-shadow: var(--glass-shadow-strong,
                    0 16px 48px rgba(0, 0, 0, 0.4),
                    0 4px 16px rgba(0, 0, 0, 0.25));
            }

            :host([data-theme="dark"]) .modal::before {
                background: linear-gradient(
                    90deg,
                    transparent 0%,
                    rgba(255, 255, 255, 0.15) 20%,
                    rgba(255, 255, 255, 0.15) 80%,
                    transparent 100%
                );
            }

            :host([data-theme="dark"]) .modal::after {
                background: linear-gradient(
                    135deg,
                    rgba(255, 255, 255, 0.04) 0%,
                    rgba(255, 255, 255, 0.01) 40%,
                    transparent 100%
                );
            }

            :host([data-theme="dark"]) .header-btn {
                background: var(--glass-tint-medium, rgba(255, 255, 255, 0.05));
                color: var(--text-secondary, rgba(255, 255, 255, 0.65));
            }

            :host([data-theme="dark"]) .header-btn:hover {
                background: var(--glass-tint-strong, rgba(255, 255, 255, 0.08));
                color: var(--text-primary, rgba(255, 255, 255, 0.95));
            }

            :host([data-theme="dark"]) .modal-content {
                color: var(--text-primary, rgba(255, 255, 255, 0.95));
            }

            :host([data-theme="dark"]) .modal-content ::slotted(*) {
                --text-primary: rgba(255, 255, 255, 0.95);
                --text-secondary: rgba(255, 255, 255, 0.65);
                --text-tertiary: rgba(255, 255, 255, 0.45);
                --glass-solid-subtle: rgba(28, 28, 46, 0.75);
                --glass-solid-medium: rgba(35, 35, 55, 0.85);
                --border-default: rgba(255, 255, 255, 0.1);
                --border-subtle: rgba(255, 255, 255, 0.06);
            }

            @media (prefers-reduced-motion: reduce) {
                :host([open]) .modal-overlay {
                    animation-duration: 1ms !important;
                }

                :host([open]) .modal.panel-enter-active {
                    animation-duration: 1ms !important;
                }

                .modal {
                    transition-duration: 1ms !important;
                }
            }

            .modal-svg-hidden {
                position: absolute;
                width: 0;
                height: 0;
                overflow: hidden;
                pointer-events: none;
                visibility: hidden;
            }
        `,
    ];

    constructor() {
        super();
        this.open = false;
        this.size = 'md';
        this.heading = '';
        this.title = '';
        this._modalId = null;
        this._modalKind = null;
        this._isFullscreen = false;
        this._isDragging = false;
        this._panelEnterActive = false;
        this._position = { x: null, y: null };
        this._dragStart = { x: 0, y: 0 };
        this._boundMouseMove = this._handleMouseMove.bind(this);
        this._boundMouseUp = this._handleMouseUp.bind(this);
        this._boundEscape = this._handleEscape.bind(this);
        /** @type {ParentNode | null} */
        this._portalRestoreParent = null;
        /** @type {ChildNode | null} */
        this._portalRestoreNext = null;
        /** @type {(() => void) | null} */
        this._portalTransitionCleanup = null;
        /** @type {ReturnType<typeof setTimeout> | null} */
        this._portalRestoreFallbackTimer = null;
    }

    /**
     * Закрытие = dispatch UI_MODAL_CLOSE с _modalId. Reducer снимет элемент со стека,
     * platform-modal-stack удалит DOM-узел. Любая прямая мутация this.open=false
     * запрещена: source of truth — state.modals.stack.
     */
    close() {
        if (!this._modalId) {
            throw new Error(
                'GlassModal.close: _modalId is empty. Modals must be opened via dispatch(UI_MODAL_OPEN, { kind, props }) — direct mounting запрещён.',
            );
        }
        this.dispatch(CoreEvents.UI_MODAL_CLOSE, { id: this._modalId });
    }

    toggleFullscreen() {
        this._isFullscreen = !this._isFullscreen;
        if (this._isFullscreen) {
            this._position = { x: null, y: null };
        }
    }

    _handleEscape(e) {
        if (e.key === 'Escape' && this.open) {
            this.close();
        }
    }

    _handleOverlayClick(e) {
        if (e.target === e.currentTarget) {
            this.close();
        }
    }

    _handleMouseDown(e) {
        if (this._isFullscreen) return;
        if (e.button !== 0) {
            return;
        }
        for (const node of e.composedPath()) {
            if (node === this.shadowRoot || node === this) {
                break;
            }
            if (node instanceof HTMLElement) {
                const tag = node.tagName;
                if (
                    tag === 'BUTTON' ||
                    tag === 'INPUT' ||
                    tag === 'TEXTAREA' ||
                    tag === 'SELECT' ||
                    tag === 'A' ||
                    node.getAttribute('role') === 'button'
                ) {
                    return;
                }
            }
        }

        const modal = this.shadowRoot?.querySelector('.modal');
        if (!modal) return;

        this._isDragging = true;
        const rect = modal.getBoundingClientRect();

        if (this._position.x === null) {
            this._position = {
                x: rect.left + rect.width / 2,
                y: rect.top + rect.height / 2,
            };
        }

        this._dragStart = {
            x: e.clientX - this._position.x,
            y: e.clientY - this._position.y,
        };

        document.addEventListener('mousemove', this._boundMouseMove);
        document.addEventListener('mouseup', this._boundMouseUp);
    }

    _handleMouseMove(e) {
        if (!this._isDragging) return;

        this._position = {
            x: e.clientX - this._dragStart.x,
            y: e.clientY - this._dragStart.y,
        };
        this.requestUpdate();
    }

    _handleMouseUp() {
        this._isDragging = false;
        document.removeEventListener('mousemove', this._boundMouseMove);
        document.removeEventListener('mouseup', this._boundMouseUp);
    }

    _handlePanelEnterAnimationEnd(e) {
        if (e.animationName !== 'glassModalPanelIn') {
            return;
        }
        if (!this.open) {
            return;
        }
        this._panelEnterActive = false;
    }

    willUpdate(changedProperties) {
        super.willUpdate(changedProperties);
        if (changedProperties.has('open')) {
            if (this.open) {
                this._panelEnterActive = true;
            } else {
                this._panelEnterActive = false;
            }
        }
        if (changedProperties.has('open') && this.open) {
            this._clearPortalCloseHooks();
            const z = this.style.getPropertyValue('--platform-modal-layer-z').trim();
            if (!z) {
                this.style.setProperty(
                    '--platform-modal-layer-z',
                    String(nextModalLayerZIndex()),
                );
            }
            this._attachPortalToBody();
        }
    }

    async getUpdateComplete() {
        const complete = await super.getUpdateComplete();
        if (this.open) {
            this._attachPortalToBody();
        } else if (this.parentNode === document.body) {
            this._schedulePortalRestoreAfterCloseAnimation();
        }
        return complete;
    }

    _clearPortalCloseHooks() {
        if (typeof this._portalTransitionCleanup === 'function') {
            this._portalTransitionCleanup();
            this._portalTransitionCleanup = null;
        }
        if (this._portalRestoreFallbackTimer !== null) {
            clearTimeout(this._portalRestoreFallbackTimer);
            this._portalRestoreFallbackTimer = null;
        }
    }

    _attachPortalToBody() {
        if (!this.open || this.parentNode === document.body) {
            if (this.parentNode === document.body) {
                this.setAttribute('data-portal', '');
            }
            return;
        }
        this._portalRestoreParent = this.parentNode;
        this._portalRestoreNext = this.nextSibling;
        document.body.appendChild(this);
        this.setAttribute('data-portal', '');
    }

    _schedulePortalRestoreAfterCloseAnimation() {
        this._clearPortalCloseHooks();
        const restore = () => {
            if (!this.open && this.parentNode === document.body) {
                this._restorePortalToOriginalParent();
            }
        };
        requestAnimationFrame(() => {
            requestAnimationFrame(restore);
        });
        this._portalRestoreFallbackTimer = setTimeout(() => {
            this._portalRestoreFallbackTimer = null;
            restore();
        }, 500);
    }

    _restorePortalToOriginalParent() {
        if (this.open) {
            return;
        }
        if (this.parentNode !== document.body) {
            this._portalRestoreParent = null;
            this._portalRestoreNext = null;
            this.removeAttribute('data-portal');
            return;
        }
        const parent = this._portalRestoreParent;
        if (!parent || !parent.isConnected) {
            this._portalRestoreParent = null;
            this._portalRestoreNext = null;
            this.removeAttribute('data-portal');
            return;
        }
        const next = this._portalRestoreNext;
        if (next && next.parentNode === parent) {
            parent.insertBefore(this, next);
        } else {
            parent.appendChild(this);
        }
        this._portalRestoreParent = null;
        this._portalRestoreNext = null;
        this.removeAttribute('data-portal');
    }

    connectedCallback() {
        super.connectedCallback();
        document.addEventListener('keydown', this._boundEscape);
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._clearPortalCloseHooks();
        document.removeEventListener('keydown', this._boundEscape);
        document.removeEventListener('mousemove', this._boundMouseMove);
        document.removeEventListener('mouseup', this._boundMouseUp);
        if (this.parentNode === document.body && this._portalRestoreParent?.isConnected) {
            this._restorePortalToOriginalParent();
        }
    }

    renderHeader() {
        return this.heading || this.title || '';
    }

    renderHeaderActions() {
        return '';
    }

    renderSaveHeaderButton() {
        return html``;
    }

    _renderHeaderSaveIcon(options) {
        const { onClick, disabled = false, title } = options;
        if (!title) {
            throw new Error('GlassModal._renderHeaderSaveIcon: title is required');
        }
        const saveClass = this.headerSavePrimary ? 'header-save-btn--primary' : '';
        return html`
            <button
                type="button"
                class="header-btn header-save-btn ${saveClass}"
                title=${title}
                aria-label=${title}
                ?disabled=${disabled}
                @click=${onClick}
            >
                <platform-icon name="save" size="16"></platform-icon>
            </button>
        `;
    }

    renderBody() {
        return html`<slot name="content"></slot>`;
    }

    renderFooter() {
        return html`<slot name="actions"></slot>`;
    }

    _getModalStyle() {
        if (this._position.x !== null && this._position.y !== null && !this._isFullscreen) {
            return `position: fixed; left: ${this._position.x}px; top: ${this._position.y}px; z-index: 2; transform: translate(-50%, -50%) ${this.open ? 'scale(1)' : 'scale(0.95)'};`;
        }
        return '';
    }

    render() {
        const modalClasses = [
            'modal',
            this.size,
            this._isFullscreen ? 'fullscreen' : '',
            this._isDragging ? 'dragging' : '',
            this.open && this._panelEnterActive ? 'panel-enter-active' : '',
        ].filter(Boolean).join(' ');

        const tm = (key) => (this.t(key) || key);
        return html`
            <div class="modal-svg-hidden" aria-hidden="true">
                <svg width="0" height="0">
                    <defs>
                        <filter id="liquidGlassFilter" x="-10%" y="-10%" width="120%" height="120%">
                            <feTurbulence
                                type="fractalNoise"
                                baseFrequency="0.012 0.012"
                                numOctaves="3"
                                seed="15"
                                result="noise"
                            />
                            <feDisplacementMap
                                in="SourceGraphic"
                                in2="noise"
                                scale="6"
                                xChannelSelector="R"
                                yChannelSelector="G"
                            />
                        </filter>
                    </defs>
                </svg>
            </div>

            <div class="modal-overlay" @click=${this._handleOverlayClick}>
                <div class="modal-scrim" aria-hidden="true" @click=${() => this.close()}></div>
                <div
                    class="${modalClasses}"
                    style="${this._getModalStyle()}"
                    @animationend=${this._handlePanelEnterAnimationEnd}
                    @click=${(e) => e.stopPropagation()}
                >
                    <div class="modal-header" @mousedown=${this._handleMouseDown}>
                        <h2 class="modal-title">${this.renderHeader()}</h2>
                        <div class="header-buttons">
                            ${this.renderHeaderActions()}
                            ${this.renderSaveHeaderButton()}
                            <button
                                class="header-btn fullscreen-btn"
                                @click=${this.toggleFullscreen}
                                title="${this._isFullscreen ? tm('modal.fullscreen_exit') : tm('modal.fullscreen_enter')}"
                            >
                                <platform-icon
                                    name="${this._isFullscreen ? 'minimize' : 'maximize'}"
                                    size="16"
                                ></platform-icon>
                            </button>
                            ${this.hideHeaderClose
                                ? ''
                                : html`
                                      <button
                                          class="header-btn"
                                          @click=${() => this.close()}
                                          title=${tm('modal.close')}
                                      >
                                          <platform-icon name="close" size="16"></platform-icon>
                                      </button>
                                  `}
                        </div>
                    </div>

                    <div class="modal-content">
                        ${this.renderBody()}
                    </div>

                    <div class="modal-actions">
                        ${this.renderFooter()}
                    </div>
                </div>
            </div>
        `;
    }
}

customElements.define('glass-modal', GlassModal);

export { GlassModal as PlatformModal };
