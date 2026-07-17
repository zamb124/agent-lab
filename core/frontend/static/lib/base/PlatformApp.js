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
 *     (mobile shell 2026). Видна только на <= 767px. Каждый элемент:
 *       { key, routeKey, params?, sheet?, sheetProps?, icon, labelKey, badge? }
 *     Пустой массив = bottom-nav скрыт (публичные/landing страницы).
 *   - static bottomNavHideOnRoutes = []  — список routeKeys, на которых bottom-nav
 *     дополнительно скрывается (полноэкранные редакторы: flow_editor, document_editor).
 *   - static topBarEnabled = false    — рендерит <platform-top-bar> сверху на мобиле.
 *     По умолчанию false — сервисы, у которых страницы уже рендерят `<page-header>` со sticky-mobile,
 *     могут адаптировать постепенно. Включи `true` при отказе от sticky-header на каждой странице.
 *   - static topBarHideOnRoutes = []  — список routeKeys, на которых top-bar скрыт.
 *   - static routeMotionEnabled = true — route changes используют View Transition API,
 *     если браузер поддерживает document.startViewTransition и не включён reduced motion.
 *   - static platformAssistant = { serviceId, branchId, showLauncher } — глобальный
 *     authenticated drawer Lara. Контекст точки входа возвращает
 *     getPlatformAssistantContextVariables(routeKey, params).
 */

import { html, css, nothing } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import { bootstrapPlatformBus, completeBootstrap, getPlatformBus, hasPlatformBus } from '../events/index.js';
import { CoreEvents } from '../events/contract.js';
import { translate } from '../events/effects/i18n.effect.js';
import { mergePlatformI18nVars } from '../utils/platform-i18n-vars.js';
import { CoreAuthEvents } from '../events/effects/auth.effect.js';
import { redirectToLogin } from '../utils/auth-redirect.js';
import { nextModalLayerZIndex } from '../utils/modal-z-stack.js';
import { registerFactory } from '../events/factory-registry.js';
import { collectFactories } from '../events/factories/register.js';
import {
    platformWorkItemFactories,
    createPlatformWorkItemCountsAuthEffect,
} from '../events/resources/platform-work-item.resource.js';
import {
    platformAgentDeviceFactories,
    createPlatformAgentDevicesAuthEffect,
} from '../events/resources/agent-devices.resource.js';
import { setDefaultI18nNamespace } from '../utils/i18n-namespace.js';
import { prefersReducedMotion } from '../utils/motion.js';
import { resolveVoiceHttpOrigin } from '../voice/voice-http-origin.js';
import { PLATFORM_LARA_TOGGLE_EVENT } from '../chat/chat-window-toggle.js';

const AGENT_DEVICES_POLL_MS = 45000;
import '../components/pwa-install-banner.js';
import '../components/platform-spinner.js';
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
import '../components/platform-file-viewer-modal.js';
import './platform-services-page.js';
import '../chat/platform-chat.js';

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
        const factories = [
            ...platformWorkItemFactories,
            ...platformAgentDeviceFactories,
            ...(Array.isArray(ctor.factories) ? ctor.factories : []),
        ];
        const factorySlices = {};
        const factoryEffects = [
            createPlatformWorkItemCountsAuthEffect(),
            createPlatformAgentDevicesAuthEffect(),
        ];
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
            activeCompanyId: s.auth.activeCompanyId,
            sessionEndCause: s.auth.sessionEndCause,
        }));
        this._routerSelect = this.select((s) => ({
            routeKey: s.router.routeKey,
            params: s.router.params,
            notFound: s.router.notFound,
        }));
        this._agentDevicesOp = this.useOp('platform/agent_devices_load');
        this._agentDevicesPollTimer = null;
        this._platformAssistantContextProvider = async () => {
            const routeValue = this._routerSelect.value;
            const routeKey = routeValue.routeKey;
            if (typeof routeKey !== 'string' || routeKey.length === 0) {
                throw new Error('PlatformApp Lara context requires routeKey');
            }
            const params = routeValue.params;
            if (!params || typeof params !== 'object' || Array.isArray(params)) {
                throw new Error('PlatformApp Lara context requires route params object');
            }
            const config = this._platformAssistantConfig();
            const serviceContext = await this.getPlatformAssistantContextVariables(routeKey, params);
            if (!serviceContext || typeof serviceContext !== 'object' || Array.isArray(serviceContext)) {
                throw new Error('PlatformApp Lara context hook must return an object');
            }
            return {
                service: config.serviceId,
                route_key: routeKey,
                screen: routeKey,
                ...serviceContext,
            };
        };
    }

    getBaseUrl() { return ''; }
    getRoutes() { return []; }
    getServiceSlices() { return {}; }
    getServiceEffects() { return []; }
    rendersUnauthenticated() { return false; }
    shouldRenderPlatformAssistant() { return true; }
    async getPlatformAssistantContextVariables() { return {}; }

    /** Подкласс: false — не дергать GET /api/auth/me при connect (публичные страницы). */
    shouldRequestUserLoadOnConnect() { return true; }

    renderRoute(routeKey, params) {
        return html`<slot></slot>`;
    }

    async connectedCallback() {
        super.connectedCallback();
        this._ensureRouteMotionSubscription();
        this._ensureAgentDevicesPoll();
        if (this._userLoadDispatched) return;
        this._userLoadDispatched = true;
        if (this.shouldRequestUserLoadOnConnect()) {
            this.dispatch(CoreAuthEvents.USER_LOAD_REQUESTED, null);
        } else {
            // Публичная страница: сразу считаем анонимом, чтобы рендер не ждал /me,
            // но фоновой пробой проверяем активную сессию — залогиненный пользователь
            // увидит «Dashboard» в шапке после ответа /api/auth/me.
            this.dispatch(CoreEvents.AUTH_ASSUMED_ANONYMOUS, null);
            this.dispatch(CoreAuthEvents.USER_SILENT_PROBE_REQUESTED, null);
        }
        completeBootstrap();
    }

    disconnectedCallback() {
        this._clearAgentDevicesPoll();
        super.disconnectedCallback();
    }

    _ensureAgentDevicesPoll() {
        if (this._agentDevicesPollTimer !== null) {
            return;
        }
        this._agentDevicesPollTimer = window.setInterval(() => {
            const auth = this._authSelect ? this._authSelect.value : null;
            if (!auth || auth.status !== 'authenticated') {
                return;
            }
            this._agentDevicesOp.run(null);
        }, AGENT_DEVICES_POLL_MS);
    }

    _clearAgentDevicesPoll() {
        if (this._agentDevicesPollTimer === null) {
            return;
        }
        window.clearInterval(this._agentDevicesPollTimer);
        this._agentDevicesPollTimer = null;
    }

    _activeAgentDeviceName() {
        const state = this._agentDevicesOp ? this._agentDevicesOp.state : null;
        if (!state || typeof state !== 'object') {
            return '';
        }
        return typeof state.online_device_name === 'string' ? state.online_device_name : '';
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
                    // Оставляем неожиданные ошибки transition видимыми, но не показываем штатные abort как uncaught promise.
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
        return translate(i18nState, key, mergePlatformI18nVars(t.i18n_vars || undefined), namespace);
    }

    _handleAuthSideEffects() {
        const auth = this._authSelect ? this._authSelect.value : null;
        if (!auth) return;
        if (
            auth.status === 'unauthenticated'
            && !this.rendersUnauthenticated()
            && auth.sessionEndCause !== 'logout'
        ) {
            redirectToLogin();
        }
    }

    _platformAssistantConfig() {
        const config = this.constructor.platformAssistant;
        if (!config || typeof config !== 'object' || Array.isArray(config)) {
            throw new Error('PlatformApp subclass must define static platformAssistant');
        }
        if (typeof config.serviceId !== 'string' || !/^[a-z][a-z0-9_]*$/.test(config.serviceId)) {
            throw new Error('PlatformApp platformAssistant.serviceId must be lowercase snake_case');
        }
        if (typeof config.branchId !== 'string' || !/^[a-z][a-z0-9_]*$/.test(config.branchId)) {
            throw new Error('PlatformApp platformAssistant.branchId must be lowercase snake_case');
        }
        if (typeof config.showLauncher !== 'boolean') {
            throw new Error('PlatformApp platformAssistant.showLauncher must be boolean');
        }
        return config;
    }

    _renderPlatformAssistant(auth, routeKey, params) {
        if (auth.status !== 'authenticated') {
            return nothing;
        }
        if (!this.shouldRenderPlatformAssistant(routeKey, params)) {
            return nothing;
        }
        const config = this._platformAssistantConfig();
        const companyId = auth.activeCompanyId;
        if (typeof companyId !== 'string' || companyId.trim() === '') {
            throw new Error('PlatformApp Lara requires active company_id');
        }
        const voiceBaseUrl = resolveVoiceHttpOrigin();
        const voiceEnabled = voiceBaseUrl !== '';
        const activeDeviceName = this._activeAgentDeviceName();
        return html`
            <platform-chat
                display="drawer"
                profile="spa"
                toggle-event-name=${PLATFORM_LARA_TOGGLE_EVENT}
                event-namespace="assistant"
                flow-id="lara"
                branch-id=${config.branchId}
                launcher-storage-scope=${config.serviceId}
                .flowsBaseUrl=${'/flows'}
                ?use-credentials=${true}
                .showLauncher=${config.showLauncher}
                assistant-title="Lara"
                ?voice-enabled=${voiceEnabled}
                voice-base-url=${voiceBaseUrl}
                company-id=${companyId.trim()}
                active-device-name=${activeDeviceName}
                .getExtraMetadataVariables=${this._platformAssistantContextProvider}
            ></platform-chat>
        `;
    }

    render() {
        const shell = renderPlatformAppShell(this);
        if (shell !== null) return shell;

        const auth = this._authSelect ? this._authSelect.value : null;
        const route = this._routerSelect ? this._routerSelect.value : null;

        if (!auth || auth.status === 'unknown' || auth.status === 'validating') {
            return html`
                <div class="loading-container">
                    <platform-spinner size="xl"></platform-spinner>
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
        const bottomNavItems = typeof this.getBottomNavItems === 'function'
            ? this.getBottomNavItems()
            : (Array.isArray(ctor.bottomNavItems) ? ctor.bottomNavItems : []);
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
            ${this._renderPlatformAssistant(auth, routeKey, params)}
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
