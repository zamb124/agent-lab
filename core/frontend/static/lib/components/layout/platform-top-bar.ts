/**
 * platform-top-bar — единая мобильная верхняя полоса (mobile shell 2026).
 *
 * Видна только на `max-width: 767px`. На десктопе хост `display: none`.
 *
 * Структура (слоты):
 *   <left>   — back-кнопка (по умолчанию), либо аватар сервиса; кастомизация через slot="left"
 *   <center> — title (по умолчанию из state.router.routes[routeKey].titleKey + t());
 *              кастомизация через slot="center" (workspace pill, breadcrumbs)
 *   <right>  — actions страницы / уведомления; slot="right"
 *
 * Источник правды для title — `state.router.routes`:
 *   { key, path, parent?, titleKey? }
 *
 * Если у текущего routeKey есть parent — отображается кнопка back (history.back()).
 *
 * Свайп от левого края (>20px) → history.back() (как видимая альтернатива дублирующая жест).
 */

import { html, css } from 'lit';
import type { CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult } from '../../lit-shim.js';
import { PlatformElement } from '../../platform-element/index.js';
import type { RouterRoute } from '../../events/reducers/router.js';
import type { SelectController } from '../../events/select-controller.js';
import '../platform-icon.js';

const EDGE_SWIPE_START_X = 20;
const EDGE_SWIPE_TRIGGER_DX = 60;

export class PlatformTopBar extends PlatformElement {
    static override properties: PropertyDeclarations = {
        /** Кастомный titleKey. Если не задан — берётся из state.router.routes. */
        titleKey: { type: String, attribute: 'title-key' },
        /** Прямой текст заголовка (если не нужен i18n). */
        titleText: { type: String, attribute: 'title-text' },
        /** Имя namespace для t(titleKey) — по умолчанию i18n namespace по умолчанию сервиса. */
        titleNamespace: { type: String, attribute: 'title-namespace' },
        /** Скрыть кнопку back (для root-страниц). По умолчанию авто-определение по parent. */
        hideBack: { type: Boolean, attribute: 'hide-back' },
        /** Свернуть в один title без правых actions (для просмотра). */
        compact: { type: Boolean, reflect: true },
        _routeKey: { state: true },
        _routes: { state: true },
    };
    declare titleKey: string;
    declare titleText: string;
    declare titleNamespace: string;
    declare hideBack: boolean;
    declare compact: boolean;
    declare _routeKey: string | null;
    declare _routes: readonly RouterRoute[];

    private _routerSelect: SelectController<{ routeKey: string | null; routes: readonly RouterRoute[] }>;
    private _boundTouchStart: (e: TouchEvent) => void;
    private _boundTouchMove: (e: TouchEvent) => void;
    private _boundTouchEnd: (e: TouchEvent) => void;
    private _edgeSwipeStartX: number | null = null;
    private _edgeSwipeStartY: number | null = null;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        css`
            :host {
                display: none;
            }

            @media (max-width: 767px) {
                :host {
                    display: block;
                    position: sticky;
                    top: 0;
                    z-index: var(--platform-top-bar-z-index);
                    background: var(--glass-solid-strong);
                    border-bottom: 1px solid var(--glass-border-subtle);
                    padding: max(var(--space-2), env(safe-area-inset-top, 0px))
                        max(var(--space-3), env(safe-area-inset-right, 0px))
                        var(--space-2)
                        max(var(--space-3), env(safe-area-inset-left, 0px));
                    box-sizing: border-box;
                }
            }

            .bar {
                display: grid;
                grid-template-columns: auto 1fr auto;
                align-items: center;
                gap: var(--space-2);
                min-height: var(--platform-top-bar-height);
            }

            .slot-left,
            .slot-right {
                display: flex;
                align-items: center;
                gap: var(--space-1);
                min-width: 36px;
            }

            .slot-center {
                min-width: 0;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: var(--space-2);
            }

            .title {
                font-size: var(--text-base);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                margin: 0;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
                letter-spacing: var(--tracking-tight);
            }

            .icon-btn {
                width: 36px;
                height: 36px;
                display: flex;
                align-items: center;
                justify-content: center;
                background: var(--glass-tint-medium);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                color: var(--text-primary);
                cursor: pointer;
                transition: var(--motion-transition-interactive);
                flex-shrink: 0;
            }

            .icon-btn:hover {
                background: var(--glass-tint-strong);
            }

            .icon-btn:active {
                transform: scale(0.94);
            }

            .icon-btn:focus-visible {
                outline: 2px solid var(--accent);
                outline-offset: 2px;
            }
        `,
    ];

    constructor() {
        super();
        this.titleKey = '';
        this.titleText = '';
        this.titleNamespace = '';
        this.hideBack = false;
        this.compact = false;
        this._routeKey = null;
        this._routes = [];
        this._routerSelect = this.select((s) => ({
            routeKey: s.router.routeKey,
            routes: s.router.routes,
        }));
        this._boundTouchStart = (e: TouchEvent) => this._onTouchStart(e);
        this._boundTouchMove = (e: TouchEvent) => this._onTouchMove(e);
        this._boundTouchEnd = () => this._onTouchEnd();
    }

    override connectedCallback(): void {
        super.connectedCallback();
        document.addEventListener('touchstart', this._boundTouchStart, { passive: true });
        document.addEventListener('touchmove', this._boundTouchMove, { passive: true });
        document.addEventListener('touchend', this._boundTouchEnd, { passive: true });
    }

    override disconnectedCallback(): void {
        super.disconnectedCallback();
        document.removeEventListener('touchstart', this._boundTouchStart);
        document.removeEventListener('touchmove', this._boundTouchMove);
        document.removeEventListener('touchend', this._boundTouchEnd);
    }

    override updated(changed: PropertyValues<this>): void {
        super.updated && super.updated(changed);
        const v = this._routerSelect ? this._routerSelect.value : null;
        if (v) {
            this._routeKey = v.routeKey;
            this._routes = Array.isArray(v.routes) ? v.routes : [];
        }
    }

    _findRoute(key: string | null): RouterRoute | null {
        if (!key) return null;
        for (const r of this._routes) {
            if (r && r.key === key) return r;
        }
        return null;
    }

    _hasParent(): boolean {
        const r = this._findRoute(this._routeKey);
        return Boolean(r && typeof r.parent === 'string' && r.parent.length > 0);
    }

    _resolveTitle(): string {
        if (typeof this.titleText === 'string' && this.titleText.length > 0) {
            return this.titleText;
        }
        const key = this.titleKey || (() => {
            const r = this._findRoute(this._routeKey);
            return r && typeof r.titleKey === 'string' ? r.titleKey : '';
        })();
        if (!key) return '';
        const ns = this.titleNamespace.length === 0 ? undefined : this.titleNamespace;
        return this.t(key, null, ns);
    }

    _onBackClick(): void {
        if (typeof history !== 'undefined' && history.length > 1) {
            history.back();
        }
    }

    _onTouchStart(e: TouchEvent) {
        if (window.innerWidth > 767) return;
        if (!e.touches || e.touches.length !== 1) return;
        const t = e.touches.item(0);
        if (!t) return;
        if (t.clientX <= EDGE_SWIPE_START_X) {
            this._edgeSwipeStartX = t.clientX;
            this._edgeSwipeStartY = t.clientY;
        }
    }

    _onTouchMove(e: TouchEvent) {
        if (this._edgeSwipeStartX === null) return;
        if (!e.touches || e.touches.length !== 1) return;
        const t = e.touches.item(0);
        if (!t) return;
        const dx = t.clientX - this._edgeSwipeStartX;
        const startY = this._edgeSwipeStartY;
        const dy = Math.abs(t.clientY - (startY === null ? 0 : startY));
        if (dy > 40) {
            this._edgeSwipeStartX = null;
            this._edgeSwipeStartY = null;
            return;
        }
        if (dx >= EDGE_SWIPE_TRIGGER_DX) {
            this._edgeSwipeStartX = null;
            this._edgeSwipeStartY = null;
            if (this._hasParent() && !this.hideBack) {
                this._onBackClick();
            }
        }
    }

    _onTouchEnd(): void {
        this._edgeSwipeStartX = null;
        this._edgeSwipeStartY = null;
    }

    _renderLeft(): TemplateResult {
        const hasSlot = this.querySelector('[slot="left"]');
        if (hasSlot) {
            return html`<slot name="left"></slot>`;
        }
        const showBack = this._hasParent() && !this.hideBack;
        if (!showBack) return html`<span aria-hidden="true"></span>`;
        const aria = this.t('top_bar.back_aria', null, 'platform');
        return html`
            <button
                type="button"
                class="icon-btn"
                aria-label=${aria}
                @click=${this._onBackClick}
            >
                <platform-icon name="chevron-left" size="20"></platform-icon>
            </button>
        `;
    }

    _renderCenter(): TemplateResult {
        const hasSlot = this.querySelector('[slot="center"]');
        if (hasSlot) {
            return html`<slot name="center"></slot>`;
        }
        const title = this._resolveTitle();
        if (!title) return html``;
        return html`<h1 class="title">${title}</h1>`;
    }

    _renderRight(): TemplateResult {
        return html`<slot name="right"></slot>`;
    }

    override render(): TemplateResult {
        return html`
            <div class="bar">
                <div class="slot-left">${this._renderLeft()}</div>
                <div class="slot-center">${this._renderCenter()}</div>
                <div class="slot-right">${this._renderRight()}</div>
            </div>
        `;
    }
}

customElements.define('platform-top-bar', PlatformTopBar);
