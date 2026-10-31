/**
 * Плавающий слой, привязанный к якорю.
 *
 * Показывается в top layer через нативный Popover API, поэтому не обрезается
 * `overflow` предков и всегда выше остального интерфейса без гонки z-index.
 * В отличие от переноса узла в `document.body`, элемент остаётся на своём месте
 * в DOM: связи `aria-controls`, наследование CSS-переменных темы и поиск по
 * поддереву владельца продолжают работать.
 *
 * Позиционирование считает `floating-position.js`; здесь только жизненный цикл:
 * подписки на прокрутку и изменение размеров, закрытие по клику мимо и Escape,
 * доступность и режимы открытия.
 *
 * @example
 * <platform-popover trigger="manual" .anchor=${this._buttonEl} ?open=${this._open}
 *                   placement="bottom-start" role="menu"
 *                   @popover-dismiss=${() => { this._open = false; }}>
 *     ...содержимое...
 * </platform-popover>
 */

import { css, html } from 'lit';
import type { CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult } from 'lit';

import { PlatformElement } from '../platform-element/index.js';
import {
    DEFAULT_OFFSET,
    DEFAULT_VIEWPORT_PADDING,
    computeFloatingPosition,
    readViewportSize,
    resolveAnchorRect,
} from '../utils/floating-position.js';
import type { FloatingPlacement, RectLike } from '../utils/floating-position.js';
import { nextModalLayerZIndex } from '../utils/modal-z-stack.js';

const HOVER_OPEN_DELAY_MS = 120;
const HOVER_CLOSE_DELAY_MS = 160;

export type PopoverAnchor = Element | RectLike | { x: number; y: number } | null;

export class PlatformPopover extends PlatformElement {
    static override properties: PropertyDeclarations = {
        /** Элемент, точка `{x, y}` или прямоугольник, к которому привязан слой. */
        anchor: { attribute: false },
        open: { type: Boolean, reflect: true },
        placement: { type: String },
        offset: { type: Number },
        trigger: { type: String },
        role: { type: String, reflect: true },
        matchWidth: { type: Boolean, attribute: 'match-width' },
        flip: { type: Boolean },
        shift: { type: Boolean },
        closeOnScroll: { type: Boolean, attribute: 'close-on-scroll' },
        dismissOnOutside: { type: Boolean, attribute: 'dismiss-on-outside' },
        constrainHeight: { type: Boolean, attribute: 'constrain-height' },
        viewportPadding: { type: Number, attribute: 'viewport-padding' },
        _placement: { state: true },
    };

    declare anchor: PopoverAnchor;
    declare open: boolean;
    declare placement: FloatingPlacement;
    declare offset: number;
    declare trigger: string;
    declare role: string;
    declare matchWidth: boolean;
    declare flip: boolean;
    declare shift: boolean;
    declare closeOnScroll: boolean;
    declare dismissOnOutside: boolean;
    declare constrainHeight: boolean;
    declare viewportPadding: number;
    declare _placement: FloatingPlacement;

    _resizeObserver: ResizeObserver | null;
    _hoverTimer: number | null;
    _outsideListenFrame: number | null;
    private _trackingUnsubs: Array<() => void> = [];
    private _anchorUnsubs: Array<() => void> = [];
    _ignoreOutsideUntil: number;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        css`
            /* UA [popover]: inset:0 + margin:auto центрирует слой. top/left 0 —
               начало containing block, от него reposition считает дельту.
               inset:auto без top/left оставляет static position — внутри
               glass-modal (transform на .modal) список рисуется в углу панели. */
            :host {
                position: fixed;
                top: 0;
                left: 0;
                right: auto;
                bottom: auto;
                margin: 0;
                padding: 0;
                border: none;
                background: transparent;
                overflow: visible;
                width: max-content;
                max-width: 100vw;
            }

            /* Явный display при открытии: иначе после снятия display:none
               custom element остаётся inline и в top layer легко получить
               нулевой box до первого reposition. */
            :host(:popover-open) {
                display: block;
            }

            :host(:not(:popover-open)) {
                display: none;
            }

            :host::backdrop {
                background: transparent;
            }

            .surface {
                box-sizing: border-box;
                overflow: auto;
                overscroll-behavior: contain;
                border-radius: var(--radius-lg, 12px);
                border: 1px solid var(--glass-border-medium, rgba(120, 120, 140, 0.28));
                background: var(--glass-solid-strong, rgba(20, 20, 28, 0.96));
                box-shadow: var(--glass-shadow-strong, 0 16px 48px rgba(0, 0, 0, 0.32));
                backdrop-filter: blur(var(--glass-blur-subtle, 20px));
                color: var(--text-primary);
                animation: platform-popover-in var(--motion-duration-enter, 140ms)
                    var(--motion-ease-decelerate, cubic-bezier(0.2, 0.8, 0.2, 1));
            }

            :host([role='tooltip']) .surface {
                padding: var(--space-2, 8px) var(--space-3, 12px);
                font-size: var(--text-sm, 0.8125rem);
                max-width: 320px;
            }

            @keyframes platform-popover-in {
                from {
                    opacity: 0;
                    transform: translateY(calc(-1 * var(--motion-enter-offset-y, 4px)));
                }
                to {
                    opacity: 1;
                    transform: none;
                }
            }

            @media (prefers-reduced-motion: reduce) {
                .surface {
                    animation: none;
                }
            }
        `,
    ];

    constructor() {
        super();
        this.anchor = null;
        this.open = false;
        this.placement = 'bottom-start';
        this.offset = DEFAULT_OFFSET;
        this.trigger = 'manual';
        this.role = 'dialog';
        this.matchWidth = false;
        this.flip = true;
        this.shift = true;
        this.closeOnScroll = false;
        this.dismissOnOutside = true;
        this.constrainHeight = true;
        this.viewportPadding = DEFAULT_VIEWPORT_PADDING;
        this._placement = this.placement;

        this._resizeObserver = null;
        this._hoverTimer = null;
        this._outsideListenFrame = null;
        // Игнорировать outside-dismiss до этого timestamp (жест открытия).
        this._ignoreOutsideUntil = 0;

        this._onReposition = this._onReposition.bind(this);
        this._onDocumentPointerDown = this._onDocumentPointerDown.bind(this);
        this._onDocumentKeyDown = this._onDocumentKeyDown.bind(this);
        this._onAnchorClick = this._onAnchorClick.bind(this);
        this._onAnchorContextMenu = this._onAnchorContextMenu.bind(this);
        this._onAnchorPointerEnter = this._onAnchorPointerEnter.bind(this);
        this._onAnchorPointerLeave = this._onAnchorPointerLeave.bind(this);
        this._onSelfPointerEnter = this._onSelfPointerEnter.bind(this);
        this._onSelfPointerLeave = this._onSelfPointerLeave.bind(this);
    }

    override connectedCallback(): void {
        super.connectedCallback();
        // Ручной режим: закрытие по клику мимо и Escape обрабатывается здесь,
        // чтобы сообщить причину и не гасить Escape, нужный вложенным слоям.
        this.setAttribute('popover', 'manual');
        this.addEventListener('pointerenter', this._onSelfPointerEnter);
        this.addEventListener('pointerleave', this._onSelfPointerLeave);
        this._attachAnchorListeners(this.anchor);
    }

    override disconnectedCallback(): void {
        super.disconnectedCallback();
        this.removeEventListener('pointerenter', this._onSelfPointerEnter);
        this.removeEventListener('pointerleave', this._onSelfPointerLeave);
        this._detachAnchorListeners(this.anchor);
        this._stopTracking();
        this._clearHoverTimer();
    }

    override willUpdate(changed: PropertyValues<this>): void {
        if (changed.has('anchor')) {
            const previous = changed.get('anchor');
            if (previous !== undefined) {
                this._detachAnchorListeners(previous);
            }
            this._attachAnchorListeners(this.anchor);
        }
    }

    override updated(changed: PropertyValues<this>): void {
        if (changed.has('open')) {
            if (this.open) {
                this._showInTopLayer();
                this._startTracking();
                this.reposition();
                this.emit('popover-open');
            } else {
                this._stopTracking();
                this._hideFromTopLayer();
                this.emit('popover-close');
            }
        } else if (this.open && (changed.has('placement') || changed.has('anchor'))) {
            this.reposition();
        }
    }

    /** Пересчитать положение — вызывается при прокрутке, ресайзе и смене содержимого. */
    reposition(): void {
        if (!this.open) {
            return;
        }
        if (this.anchor instanceof Element && !this.anchor.isConnected) {
            return;
        }
        const anchorRect = resolveAnchorRect(this.anchor);
        if (!anchorRect) {
            return;
        }
        const surface = this.renderRoot?.querySelector<HTMLElement>('.surface');
        if (!surface) {
            return;
        }

        // Ограничение высоты снимается перед замером: иначе слой «запоминает»
        // прошлый лимит и не может вырасти, когда места стало больше.
        surface.style.maxHeight = '';
        if (this.matchWidth) {
            surface.style.width = `${anchorRect.width}px`;
        }

        // Начало containing block (viewport или предок с transform/contain).
        // Дельта от фактического origin до viewport-точки якоря.
        this.style.top = '0px';
        this.style.left = '0px';
        this.style.transform = 'none';
        const origin = this.getBoundingClientRect();
        const rect = surface.getBoundingClientRect();

        const position = computeFloatingPosition({
            anchorRect,
            floatingRect: { width: rect.width, height: rect.height },
            placement: this.placement,
            offset: this.offset,
            flip: this.flip,
            shift: this.shift,
            matchWidth: this.matchWidth,
            viewport: readViewportSize(),
            viewportPadding: this.viewportPadding,
        });

        this.style.left = `${Math.round(position.x - origin.left)}px`;
        this.style.top = `${Math.round(position.y - origin.top)}px`;
        this._placement = position.placement;
        this.setAttribute('data-placement', position.placement);
        if (position.width !== null) {
            surface.style.width = `${position.width}px`;
        }
        if (this.constrainHeight) {
            surface.style.maxHeight = `${position.maxHeight}px`;
        }
    }

    /** Программное открытие; для `trigger="contextmenu"` якорем может быть точка. */
    show(anchor?: PopoverAnchor): void {
        if (anchor !== undefined) {
            this.anchor = anchor;
        }
        this.open = true;
    }

    hide(): void {
        this.open = false;
    }

    toggle(anchor?: PopoverAnchor): void {
        if (this.open) {
            this.hide();
        } else {
            this.show(anchor);
        }
    }

    // --- top layer ---

    _showInTopLayer(): void {
        if (!this.isConnected || this.matches(':popover-open')) {
            return;
        }
        this.showPopover();
        // Внутри модалки уже есть свой top layer, и порядок между слоями там
        // определяется z-index, а не порядком показа.
        this.style.zIndex = String(nextModalLayerZIndex());
    }

    _hideFromTopLayer(): void {
        if (!this.isConnected || !this.matches(':popover-open')) {
            return;
        }
        this.hidePopover();
        this.style.transform = '';
        this.style.top = '';
        this.style.left = '';
    }

    // --- подписки ---

    _startTracking(): void {
        this._trackingUnsubs = [
            this.useDomEvent(window, 'scroll', this._onReposition, true),
            this.useDomEvent(window, 'resize', this._onReposition),
        ];
        if (window.visualViewport) {
            this._trackingUnsubs.push(
                this.useDomEvent(window.visualViewport, 'resize', this._onReposition),
                this.useDomEvent(window.visualViewport, 'scroll', this._onReposition),
            );
        }
        this._trackingUnsubs.push(this.useDomEvent(document, 'keydown', this._onDocumentKeyDown, true));

        // Outside-dismiss после жеста открытия: иначе pointerdown/focus→open
        // в том же turn (или с null-anchor) сразу гасит слой.
        this._ignoreOutsideUntil = performance.now() + 320;
        if (this.dismissOnOutside) {
            if (this._outsideListenFrame !== null) {
                cancelAnimationFrame(this._outsideListenFrame);
            }
            this._outsideListenFrame = requestAnimationFrame(() => {
                this._outsideListenFrame = null;
                if (!this.open || !this.dismissOnOutside) {
                    return;
                }
                this._trackingUnsubs.push(this.useDomEvent(document, 'pointerdown', this._onDocumentPointerDown, true));
            });
        }

        if (typeof ResizeObserver !== 'undefined') {
            this._resizeObserver = new ResizeObserver(() => this.reposition());
            const surface = this.renderRoot?.querySelector<HTMLElement>('.surface');
            if (surface) {
                this._resizeObserver.observe(surface);
            }
            if (this.anchor instanceof Element) {
                this._resizeObserver.observe(this.anchor);
            }
        }
    }

    _stopTracking(): void {
        for (const unsub of this._trackingUnsubs) {
            unsub();
        }
        this._trackingUnsubs = [];
        if (this._outsideListenFrame !== null) {
            cancelAnimationFrame(this._outsideListenFrame);
            this._outsideListenFrame = null;
        }
        this._resizeObserver?.disconnect();
        this._resizeObserver = null;
    }

    _onReposition(): void {
        if (this.closeOnScroll) {
            this._dismiss('scroll');
            return;
        }
        this.reposition();
    }

    _onDocumentPointerDown(event: PointerEvent): void {
        if (performance.now() < this._ignoreOutsideUntil) {
            return;
        }
        const path = event.composedPath();
        if (path.includes(this)) {
            return;
        }
        if (this.anchor instanceof Element && path.includes(this.anchor)) {
            return;
        }
        this._dismiss('outside');
    }

    _onDocumentKeyDown(event: KeyboardEvent): void {
        if (event.key !== 'Escape' || !this.open) {
            return;
        }
        event.stopPropagation();
        this._dismiss('escape');
    }

    _dismiss(reason: string): void {
        this.open = false;
        this.emit('popover-dismiss', { reason });
    }

    // --- режимы открытия ---

    _attachAnchorListeners(anchor: PopoverAnchor): void {
        if (!(anchor instanceof Element)) {
            return;
        }
        if (this.trigger === 'click') {
            this._anchorUnsubs.push(this.useDomEvent(anchor, 'click', this._onAnchorClick));
        } else if (this.trigger === 'contextmenu') {
            this._anchorUnsubs.push(this.useDomEvent(anchor, 'contextmenu', this._onAnchorContextMenu));
        } else if (this.trigger === 'hover') {
            this._anchorUnsubs.push(
                this.useDomEvent(anchor, 'pointerenter', this._onAnchorPointerEnter),
                this.useDomEvent(anchor, 'pointerleave', this._onAnchorPointerLeave),
                this.useDomEvent(anchor, 'focusin', this._onAnchorPointerEnter),
                this.useDomEvent(anchor, 'focusout', this._onAnchorPointerLeave),
            );
        }
    }

    _detachAnchorListeners(anchor: PopoverAnchor): void {
        if (!(anchor instanceof Element)) {
            return;
        }
        for (const unsub of this._anchorUnsubs) {
            unsub();
        }
        this._anchorUnsubs = [];
    }

    _onAnchorClick(): void {
        this.toggle();
    }

    _onAnchorContextMenu(event: Event): void {
        event.preventDefault();
        if (!(event instanceof MouseEvent)) {
            throw new Error('platform-popover: context menu must be a mouse event');
        }
        this.show({ x: event.clientX, y: event.clientY });
    }

    _onAnchorPointerEnter(): void {
        this._clearHoverTimer();
        this._hoverTimer = window.setTimeout(() => {
            this.open = true;
        }, HOVER_OPEN_DELAY_MS);
    }

    _onAnchorPointerLeave(): void {
        this._clearHoverTimer();
        this._hoverTimer = window.setTimeout(() => {
            this.open = false;
        }, HOVER_CLOSE_DELAY_MS);
    }

    _onSelfPointerEnter(): void {
        if (this.trigger === 'hover') {
            this._clearHoverTimer();
        }
    }

    _onSelfPointerLeave(): void {
        if (this.trigger === 'hover') {
            this._onAnchorPointerLeave();
        }
    }

    _clearHoverTimer(): void {
        if (this._hoverTimer !== null) {
            clearTimeout(this._hoverTimer);
            this._hoverTimer = null;
        }
    }

    override render(): TemplateResult {
        return html`
            <div class="surface" part="surface">
                <slot></slot>
            </div>
        `;
    }
}

customElements.define('platform-popover', PlatformPopover);
