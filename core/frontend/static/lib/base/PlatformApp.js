/**
 * PlatformApp — канонический Event Sourcing корень приложения.
 *
 * Подклассы переопределяют:
 *   - getBaseUrl()        — префикс сервиса для URL
 *   - getRoutes()         — массив { key, path, parent?, title? }
 *   - getServiceSlices()  — { [name]: { reducer, initial } } (для не-фабричных slices)
 *   - getServiceEffects() — массив effect-функций (для не-фабричных effects)
 *   - renderRoute(routeKey, params) — что рисуем для каждого маршрута
 *   - rendersUnauthenticated() — true для landing/login (по умолчанию false)
 *
 * Декларативные статики:
 *   - static factories = []           — список фабрик ресурсов/операций сервиса.
 *     При boot'е PlatformApp вызывает registerFactory(f) и через collectFactories
 *     собирает их slices/effects, мерджа с тем, что вернули getServiceSlices()
 *     и getServiceEffects().
 *   - static defaultI18nNamespace     — namespace по умолчанию для this.t(...)
 *     во всех компонентах сервиса. Приземляется через setDefaultI18nNamespace.
 *   - static bottomNavItems = []      — конфигурация мобильной первичной навигации
 *     (mobile shell 2026). Видна только на <= 767px. Каждый item:
 *       { key, routeKey, params?, sheet?, sheetProps?, icon, labelKey, badge? }
 *     Пустой массив = bottom-nav скрыт (публичные/landing страницы).
 *   - static bottomNavHideOnRoutes = []  — список routeKeys, на которых bottom-nav
 *     дополнительно скрывается (полноэкранные редакторы: flow_editor, document_editor).
 *   - static topBarEnabled = false    — рендерит <platform-top-bar> сверху на мобиле.
 *     Default false — сервисы, у которых страницы уже рендерят `<page-header>` со sticky-mobile,
 *     могут адоптировать постепенно. Включи `true` при отказе от per-page sticky-header.
 *   - static topBarHideOnRoutes = []  — список routeKeys, на которых top-bar скрыт.
 *   - static routeMotionEnabled = true — route changes используют View Transition API,
 *     если браузер поддерживает document.startViewTransition и не включён reduced motion.
 */

import { html, css } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import { bootstrapPlatformBus, completeBootstrap, getPlatformBus, hasPlatformBus } from '../events/index.js';
import { CoreEvents } from '../events/contract.js';
import { translate } from '../events/effects/i18n.effect.js';
import { CoreAuthEvents } from '../events/effects/auth.effect.js';
import { redirectToLogin } from '../utils/auth-redirect.js';
import { nextModalLayerZIndex } from '../utils/modal-z-stack.js';
import { serviceIdFromBaseUrl, setLastVisitedService } from '../utils/last-visited-service.js';
import { registerFactory } from '../events/factory-registry.js';
import { collectFactories } from '../events/factories/register.js';
import { setDefaultI18nNamespace } from '../utils/i18n-namespace.js';
import { prefersReducedMotion } from '../utils/motion.js';

import '../components/pwa-install-banner.js';
import '../components/glass-toast.js';
import '../components/platform-shell-page.js';
import '../components/platform-modal-stack.js';
import '../components/platform-bottom-sheet-stack.js';
import '../components/layout/platform-bottom-nav.js';
import '../components/layout/platform-top-bar.js';
import '../components/sheets/platform-service-switcher-sheet.js';
import '../components/platform-user-chip.js';
import '../components/platform-user-info-modal.js';
import '../components/platform-services-modal.js';
import './platform-services-page.js';

export function renderPlatformAppShell(app) {
    if (app._fatalShell === 'server-error') {
        return html`
            <platform-shell-page kind="server-error"></platform-shell-page>
            <pwa-install-banner></pwa-install-banner>
        `;
    }
    if (app._routeNotFound) {
        return html`
            <platform-shell-page
                kind="not-found"
                .homeHref=${app._notFoundHomeHref}
            ></platform-shell-page>
            <pwa-install-banner></pwa-install-banner>
        `;
    }
    return null;
}

export class PlatformApp extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            .loading-container {
                box-sizing: border-box;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                align-self: stretch;
                flex: 1 1 auto;
                width: 100%;
                min-width: 0;
                min-height: var(--app-vh, 100vh);
                padding: 40px;
            }
            .loading-spinner {
                width: 48px; height: 48px;
                border: 4px solid var(--glass-border-medium);
                border-top-color: var(--accent);
                border-radius: 50%;
                animation: loading-spin 1s linear infinite;
                margin-bottom: 24px;
            }
            .loading-text { font-size: 16px; color: var(--text-muted); }
            @keyframes loading-spin { to { transform: rotate(360deg); } }
        `,
    ];

    static properties = {
        _bootstrapped: { state: true },
        _fatalShell:   { state: true },
        _routeNotFound:{ state: true },
        _notFoundHomeHref: { state: true },
    };

    constructor() {
        super();
        const ctor = this.constructor;
        if (typeof ctor.defaultI18nNamespace === 'string' && ctor.defaultI18nNamespace.length > 0) {
            setDefaultI18nNamespace(ctor.defaultI18nNamespace);
        }
        const factories = Array.isArray(ctor.factories) ? ctor.factories : [];
        const factorySlices = {};
        const factoryEffects = [];
        if (factories.length > 0) {
            for (const factory of factories) {
                registerFactory(factory);
            }
            const collected = collectFactories(factories);
            Object.assign(factorySlices, collected.slices);
            factoryEffects.push(...collected.effects);
        }
        const serviceSlices = this.getServiceSlices();
        const mergedSlices = { ...factorySlices };
        for (const [key, slice] of Object.entries(serviceSlices || {})) {
            if (mergedSlices[key]) {
                throw new Error(`PlatformApp: sliceKey "${key}" collision between factory and getServiceSlices()`);
            }
            mergedSlices[key] = slice;
        }
        const mergedEffects = [...factoryEffects, ...(this.getServiceEffects() || [])];
        // Bus поднимается в конструкторе до того как Lit активирует controllers.
        // Это инвариант: ни один SelectController, созданный в полях подкласса,
        // не должен встретить отсутствующий bus в hostConnected.
        if (!hasPlatformBus()) {
            bootstrapPlatformBus({
                baseUrl: this.getBaseUrl(),
                routes: this.getRoutes(),
                slices: mergedSlices,
                effects: mergedEffects,
                devMode: typeof location !== 'undefined' && /[?&]platform_devtools=1\b/.test(location.search),
            });
        }
        this._bootstrapped = true;
        this._userLoadDispatched = false;
        this._fatalShell = null;
        this._routeNotFound = false;
        this._notFoundHomeHref = '/';
        this._renderedToastIds = new Set();
        this._routeMotionSubscribed = false;
        this._activeRouteTransition = null;

        this._toastsSelect = this.select((s) => s.notify.toasts);
        this._authSelect = this.select((s) => ({
            status: s.auth.status,
            user: s.auth.user,
            sessionEndCause: s.auth.sessionEndCause,
        }));
        this._routerSelect = this.select((s) => ({
            routeKey: s.router.routeKey,
            params: s.router.params,
            notFound: s.router.notFound,
        }));
    }

    getBaseUrl() { return ''; }
    getRoutes() { return []; }
    getServiceSlices() { return {}; }
    getServiceEffects() { return []; }
    rendersUnauthenticated() { return false; }

    /** Подкласс: false — не дергать GET /api/auth/me при connect (публичные страницы). */
    shouldRequestUserLoadOnConnect() { return true; }

    renderRoute(routeKey, params) {
        return html`<slot></slot>`;
    }

    async connectedCallback() {
        super.connectedCallback();
        this._ensureRouteMotionSubscription();
        if (this._userLoadDispatched) return;
        this._userLoadDispatched = true;
        if (this.shouldRequestUserLoadOnConnect()) {
            this.dispatch(CoreAuthEvents.USER_LOAD_REQUESTED, null);
        } else {
            this.dispatch(CoreEvents.AUTH_ASSUMED_ANONYMOUS, null);
        }
        completeBootstrap();
    }

    _ensureRouteMotionSubscription() {
        if (this._routeMotionSubscribed) return;
        this._routeMotionSubscribed = true;
        this.useEvent(CoreEvents.ROUTER_ROUTE_CHANGED, () => {
            this._startRouteMotion();
        });
    }

    _startRouteMotion() {
        if (this.constructor.routeMotionEnabled === false) return;
        if (prefersReducedMotion()) return;
        if (typeof document === 'undefined') return;
        if (typeof document.startViewTransition !== 'function') return;
        if (this._activeRouteTransition) return;

        const transition = document.startViewTransition(async () => {
            await this.updateComplete;
        });
        this._activeRouteTransition = transition;
        transition.finished
            .catch((error) => {
                const name = error && typeof error.name === 'string' ? error.name : '';
                if (name !== 'AbortError' && name !== 'InvalidStateError') {
                    // Keep unexpected transition failures visible without surfacing benign aborts as uncaught promises.
                    console.warn('PlatformApp route transition failed', error);
                }
            })
            .finally(() => {
                if (this._activeRouteTransition === transition) {
                    this._activeRouteTransition = null;
                }
            });
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._routeMotionSubscribed = false;
        this._activeRouteTransition = null;
    }

    updated(changed) {
        if (super.updated) super.updated(changed);
        this._renderToasts();
        this._handleAuthSideEffects();
    }

    _renderToasts() {
        const toasts = this._toastsSelect ? this._toastsSelect.value || [] : [];
        for (const t of toasts) {
            if (this._renderedToastIds.has(t.id)) continue;
            this._renderedToastIds.add(t.id);
            const el = document.createElement('glass-toast');
            el.type = t.type;
            el.message = this._resolveToastMessage(t);
            el.duration = t.duration;
            el.style.zIndex = String(nextModalLayerZIndex());
            el.addEventListener('close', () => {
                this.dispatch(CoreEvents.UI_TOAST_DISMISS, { id: t.id });
            });
            document.body.appendChild(el);
        }
    }

    _resolveToastMessage(t) {
        if (!t.i18n_key) return t.message || '';
        const bus = hasPlatformBus() ? getPlatformBus() : null;
        const i18nState = bus ? bus.getState().i18n : null;
        if (!i18nState) return t.message || t.i18n_key;
        const [nsOrKey, ...rest] = t.i18n_key.split(':');
        const key = rest.length > 0 ? rest.join(':') : nsOrKey;
        const namespace = rest.length > 0 ? nsOrKey : undefined;
        return translate(i18nState, key, t.i18n_vars || undefined, namespace);
    }

    _handleAuthSideEffects() {
        const auth = this._authSelect ? this._authSelect.value : null;
        if (!auth) return;
        if (auth.status === 'authenticated' && auth.user) {
            const id = serviceIdFromBaseUrl(this.getBaseUrl());
            if (id && id !== 'frontend') {
                setLastVisitedService(id);
            }
        }
        if (
            auth.status === 'unauthenticated'
            && !this.rendersUnauthenticated()
            && auth.sessionEndCause !== 'logout'
        ) {
            redirectToLogin();
        }
    }

    render() {
        const shell = renderPlatformAppShell(this);
        if (shell !== null) return shell;

        const auth = this._authSelect ? this._authSelect.value : null;
        const route = this._routerSelect ? this._routerSelect.value : null;

        if (!auth || auth.status === 'unknown' || auth.status === 'validating') {
            return html`
                <div class="loading-container">
                    <div class="loading-spinner"></div>
                    <div class="loading-text">${this.t('loading', {}, 'common')}</div>
                </div>
            `;
        }
        if (auth.status === 'unauthenticated' && !this.rendersUnauthenticated()) {
            return html`<div>Redirecting...</div>`;
        }
        if (auth.status === 'error') {
            return html`<platform-shell-page kind="server-error"></platform-shell-page>`;
        }

        if (route && route.notFound) {
            return html`<platform-shell-page kind="not-found" .homeHref=${this._notFoundHomeHref}></platform-shell-page>`;
        }

        const routeKey = route ? route.routeKey : null;
        const params = route ? route.params || {} : {};
        const ctor = this.constructor;
        const bottomNavItems = Array.isArray(ctor.bottomNavItems) ? ctor.bottomNavItems : [];
        const bottomNavHideOnRoutes = Array.isArray(ctor.bottomNavHideOnRoutes)
            ? ctor.bottomNavHideOnRoutes
            : [];
        const topBarEnabled = ctor.topBarEnabled === true;
        const topBarHideOnRoutes = Array.isArray(ctor.topBarHideOnRoutes)
            ? ctor.topBarHideOnRoutes
            : [];
        const hideTopBar = topBarHideOnRoutes.includes(routeKey);
        return html`
            ${topBarEnabled && !hideTopBar
                ? html`<platform-top-bar></platform-top-bar>`
                : ''}
            ${this.renderRoute(routeKey, params)}
            ${bottomNavItems.length > 0
                ? html`
                    <platform-bottom-nav
                        .items=${bottomNavItems}
                        .hideOnRoutes=${bottomNavHideOnRoutes}
                    ></platform-bottom-nav>
                `
                : ''}
            <pwa-install-banner></pwa-install-banner>
            <platform-modal-stack></platform-modal-stack>
            <platform-bottom-sheet-stack></platform-bottom-sheet-stack>
        `;
    }
}

export function platformBus() {
    return getPlatformBus();
}
