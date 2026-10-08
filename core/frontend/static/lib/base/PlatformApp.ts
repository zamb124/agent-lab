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
 *   - static platformAssistant = { serviceId, branchId, showLauncher, launcherPosition? }
 *     — глобальный authenticated drawer Lara. `launcherPosition`: `'bottom-right'`
 *     (дефолт) | `'bottom-left'` — только стартовый угол, пока пользователь не
 *     двигал кластер. Drag/resize живут в `<flow-ui-drawer>`, не в сервисе.
 *     Контекст точки входа — getPlatformAssistantContextVariables(routeKey, params).
 */

import { html, css, nothing } from 'lit';
import type { CSSResultGroup, PropertyValues, TemplateResult } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import { bootstrapPlatformBus, completeBootstrap, getPlatformBus, hasPlatformBus } from '../events/index.js';
import { CoreEvents } from '../events/contract.js';
import type { PlatformEvent } from '../events/contract.js';
import { isI18nBundleReady, translate } from '../events/effects/i18n.effect.js';
import { mergePlatformI18nVars } from '../utils/platform-i18n-vars.js';
import { CoreAuthEvents } from '../events/effects/auth.effect.js';
import { redirectToLogin } from '../utils/auth-redirect.js';
import { nextModalLayerZIndex } from '../utils/modal-z-stack.js';
import { registerFactory } from '../events/factory-registry.js';
import type { PlatformFactory } from '../events/factory-registry.js';
import { collectFactories } from '../events/factories/register.js';
import type { CollectableFactory } from '../events/factories/register.js';
import {
    worktrackerWorkItemFactories,
    createWorktrackerWorkItemCountsAuthEffect,
} from '../events/resources/work-items.resource.js';
import {
    platformAgentDeviceFactories,
    createPlatformAgentDevicesAuthEffect,
} from '../events/resources/agent-devices.resource.js';
import { setDefaultI18nNamespace } from '../utils/i18n-namespace.js';
import { prefersReducedMotion } from '../utils/motion.js';
import { resolveVoiceHttpOrigin } from '../voice/voice-http-origin.js';
import { PLATFORM_LARA_TOGGLE_EVENT } from '../flow-ui/shell/preferences.js';
import { setPlatformFilesRouteSegment } from '../utils/platform-files-url.js';
import type { SelectController } from '../events/select-controller.js';
import type { OpController } from './use-resource.js';
import type { SliceDef } from '../events/reducers/index.js';
import type { EventEffect } from '../events/bus.js';
import type { RouterRoute } from '../events/reducers/router.js';
import type { AuthState, AuthStatus, AuthUser } from '../events/reducers/auth.js';
import type { NotifyToast } from '../events/reducers/notify.js';
import type { LauncherPosition } from '../flow-ui/shell/drawer-geometry.js';

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
import '../components/platform-file-picker-modal.js';
import './platform-services-page.js';
import '../flow-ui/shell/drawer.js';

export interface PlatformAssistantStaticConfig {
    serviceId: string;
    branchId: string;
    showLauncher: boolean;
    launcherPosition?: LauncherPosition;
}

interface PlatformAppCtor {
    defaultI18nNamespace?: string;
    factories?: CollectableFactory[];
    bottomNavItems?: unknown[];
    bottomNavHideOnRoutes?: string[];
    topBarEnabled?: boolean;
    topBarHideOnRoutes?: string[];
    routeMotionEnabled?: boolean;
    platformAssistant?: PlatformAssistantStaticConfig;
}

export interface BottomNavItem {
    key: string;
    routeKey?: string;
    params?: Record<string, string>;
    sheet?: string;
    sheetProps?: Record<string, unknown>;
    icon: string;
    labelKey: string;
    badge?: unknown;
    [key: string]: unknown;
}

interface AuthSelection {
    status: AuthStatus;
    user: AuthUser | null;
    activeCompanyId: string | null;
    sessionEndCause: string | null;
}

interface RouteSelection {
    routeKey: string | null;
    params: Record<string, string>;
    notFound: boolean;
}


export function renderPlatformAppShell(app: PlatformApp): TemplateResult | null {
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
    static override styles: CSSResultGroup = [
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

    static override properties = {
        _bootstrapped: { state: true },
        _fatalShell:   { state: true },
        _routeNotFound:{ state: true },
        _notFoundHomeHref: { state: true },
    };

    declare _bootstrapped: boolean;
    declare _fatalShell: string | null;
    declare _routeNotFound: boolean;
    declare _notFoundHomeHref: string;

    _userLoadDispatched: boolean;
    _renderedToastIds: Set<string>;
    _routeMotionSubscribed: boolean;
    _activeRouteTransition: ViewTransition | null;
    _toastsSelect: SelectController<NotifyToast[]>;
    _i18nReadySelect: SelectController<boolean>;
    _authSelect: SelectController<AuthSelection>;
    _routerSelect: SelectController<RouteSelection>;
    _agentDevicesOp: OpController;
    _agentDevicesPollTimer: number | null;
    _platformAssistantContextProvider: () => Promise<Record<string, unknown>>;

    constructor() {
        super();
        const ctor = this.constructor as PlatformAppCtor;
        if (typeof ctor.defaultI18nNamespace === 'string' && ctor.defaultI18nNamespace.length > 0) {
            setDefaultI18nNamespace(ctor.defaultI18nNamespace);
        }
        const factories: CollectableFactory[] = [
            ...(worktrackerWorkItemFactories as CollectableFactory[]),
            ...(platformAgentDeviceFactories as CollectableFactory[]),
            ...(Array.isArray(ctor.factories) ? ctor.factories : []),
        ];
        const factorySlices: Record<string, SliceDef> = {};
        const factoryEffects: EventEffect[] = [
            createWorktrackerWorkItemCountsAuthEffect(),
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
        const mergedSlices: Record<string, SliceDef> = { ...factorySlices };
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
        setPlatformFilesRouteSegment(this.getFilesRouteSegment());
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

        this._toastsSelect = this.select((s) => (s.notify as { toasts: NotifyToast[] }).toasts);
        this._i18nReadySelect = this.select((s) => isI18nBundleReady(s.i18n as Parameters<typeof isI18nBundleReady>[0]));
        this._authSelect = this.select((s) => {
            const auth = s.auth as AuthState;
            return {
                status: auth.status,
                user: auth.user,
                activeCompanyId: auth.activeCompanyId,
                sessionEndCause: auth.sessionEndCause,
            };
        });
        this._routerSelect = this.select((s) => {
            const router = s.router as RouteSelection;
            return {
                routeKey: router.routeKey,
                params: router.params,
                notFound: router.notFound,
            };
        });
        this._agentDevicesOp = this.useOp('platform/agent_devices_load');
        this._agentDevicesPollTimer = null;
        this._platformAssistantContextProvider = async () => {
            const routeValue = this._routerSelect.value;
            const routeKey = routeValue ? routeValue.routeKey : null;
            if (typeof routeKey !== 'string' || routeKey.length === 0) {
                throw new Error('PlatformApp Lara context requires routeKey');
            }
            const params = routeValue ? routeValue.params : null;
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

    getBaseUrl(): string { return ''; }
    /**
     * Ingress segment для Files API (`/crm` → `crm`). Frontend: getBaseUrl `/frontend`.
     */
    getFilesRouteSegment(): string {
        const base = this.getBaseUrl();
        if (typeof base !== 'string') {
            throw new Error('PlatformApp.getFilesRouteSegment: getBaseUrl must return string');
        }
        const segment = base.trim().replace(/^\/+|\/+$/g, '');
        if (segment === '') {
            throw new Error(
                'PlatformApp.getFilesRouteSegment: getBaseUrl must yield non-empty segment',
            );
        }
        return segment;
    }
    getRoutes(): RouterRoute[] { return []; }
    getServiceSlices(): Record<string, SliceDef> { return {}; }
    getServiceEffects(): EventEffect[] { return []; }
    rendersUnauthenticated(): boolean { return false; }
    shouldRenderPlatformAssistant(_routeKey: string | null, _params: Record<string, string>): boolean { return true; }
    async getPlatformAssistantContextVariables(_routeKey: string, _params: Record<string, string>): Promise<Record<string, unknown>> { return {}; }

    /** Подкласс: false — не дергать GET /api/auth/me при connect (публичные страницы). */
    shouldRequestUserLoadOnConnect(): boolean { return true; }


    renderRoute(_routeKey: string | null, _params: Record<string, string>): TemplateResult {
        return html`<slot></slot>`;
    }

    override async connectedCallback(): Promise<void> {
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
        // Публичный OAuth/demo-конфиг — до открытия auth-modal, без скачка высоты.
        this.dispatch(CoreAuthEvents.PROVIDERS_LOAD_REQUESTED, null);
        this.dispatch(CoreAuthEvents.DEMO_STATUS_REQUESTED, null);
        completeBootstrap();
    }

    override disconnectedCallback(): void {
        this._clearAgentDevicesPoll();
        this._routeMotionSubscribed = false;
        this._activeRouteTransition = null;
        super.disconnectedCallback();
    }

    _ensureAgentDevicesPoll(): void {
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

    _clearAgentDevicesPoll(): void {
        if (this._agentDevicesPollTimer === null) {
            return;
        }
        window.clearInterval(this._agentDevicesPollTimer);
        this._agentDevicesPollTimer = null;
    }

    _activeAgentDeviceName(): string {
        const state = this._agentDevicesOp ? this._agentDevicesOp.state : null;
        if (!state || typeof state !== 'object') {
            return '';
        }
        const name = (state as Record<string, unknown>).online_device_name;
        return typeof name === 'string' ? name : '';
    }

    _ensureRouteMotionSubscription(): void {
        if (this._routeMotionSubscribed) return;
        this._routeMotionSubscribed = true;
        this.useEvent(CoreEvents.ROUTER_ROUTE_CHANGED, () => {
            this._startRouteMotion();
        });
    }

    _startRouteMotion(): void {
        if ((this.constructor as PlatformAppCtor).routeMotionEnabled === false) return;
        if (prefersReducedMotion()) return;
        if (typeof document === 'undefined') return;
        if (typeof document.startViewTransition !== 'function') return;
        if (this._activeRouteTransition) return;

        let transition: ViewTransition;
        try {
            transition = document.startViewTransition(async () => {
                await this.updateComplete;
            });
        } catch (error) {
            const name = error && typeof error === 'object' && typeof (error as { name?: unknown }).name === 'string'
                ? (error as { name: string }).name
                : '';
            if (name === 'AbortError' || name === 'InvalidStateError') return;
            throw error;
        }
        this._activeRouteTransition = transition;
        const swallowRouteTransitionAbort = (error: unknown) => {
            const name = error && typeof error === 'object' && typeof (error as { name?: unknown }).name === 'string'
                ? (error as { name: string }).name
                : '';
            if (name !== 'AbortError' && name !== 'InvalidStateError') {
                // Оставляем неожиданные ошибки transition видимыми, но не показываем штатные abort как uncaught promise.
                console.warn('PlatformApp route transition failed', error);
            }
        };
        // Both settled promises can reject on rapid route changes; catch each.
        transition.updateCallbackDone.catch(swallowRouteTransitionAbort);
        transition.finished
            .catch(swallowRouteTransitionAbort)
            .finally(() => {
                if (this._activeRouteTransition === transition) {
                    this._activeRouteTransition = null;
                }
            });
    }

    override updated(changed: PropertyValues<this>): void {
        super.updated(changed);
        this._renderToasts();
        this._handleAuthSideEffects();
    }

    _renderToasts(): void {
        if (!this._i18nReadySelect || !this._i18nReadySelect.value) {
            return;
        }
        const toasts = this._toastsSelect ? this._toastsSelect.value || [] : [];
        for (const t of toasts) {
            if (this._renderedToastIds.has(t.id)) continue;
            this._renderedToastIds.add(t.id);
            const el = document.createElement('glass-toast') as HTMLElement & { type: string; message: string; duration: number };
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

    _resolveToastMessage(t: NotifyToast): string {
        if (!t.i18n_key) return t.message || '';
        const bus = hasPlatformBus() ? getPlatformBus() : null;
        const i18nState = bus ? (bus.getState().i18n as Parameters<typeof translate>[0] | undefined) : null;
        if (!i18nState) return t.message || t.i18n_key;
        const [nsOrKey = '', ...rest] = t.i18n_key.split(':');
        const key = rest.length > 0 ? rest.join(':') : nsOrKey;
        const namespace = rest.length > 0 ? nsOrKey : undefined;
        return translate(i18nState, key, mergePlatformI18nVars(t.i18n_vars as Record<string, string | number> | null | undefined), namespace);
    }

    _handleAuthSideEffects(): void {
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

    _platformAssistantConfig(): PlatformAssistantStaticConfig {
        const config = (this.constructor as PlatformAppCtor).platformAssistant;
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
        if (
            config.launcherPosition !== undefined
            && config.launcherPosition !== 'bottom-right'
            && config.launcherPosition !== 'bottom-left'
        ) {
            throw new Error(
                "PlatformApp platformAssistant.launcherPosition must be 'bottom-right' or 'bottom-left'",
            );
        }
        return config;
    }

    _renderPlatformAssistant(auth: AuthSelection, routeKey: string | null, params: Record<string, string>): TemplateResult | typeof nothing {
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
        const launcherPosition = config.launcherPosition === 'bottom-left'
            ? 'bottom-left'
            : 'bottom-right';
        return html`
            <flow-ui-drawer
                data-embed-position=${launcherPosition}
                .config=${{
                    flowId: 'lara',
                    branchId: config.branchId,
                    baseUrl: '/flows',
                    profile: 'spa',
                    showLauncher: config.showLauncher,
                    launcherPosition,
                    getRequestHeaders: async () => ({}),
                    serviceId: config.serviceId,
                    companyId: companyId.trim(),
                    voiceEnabled,
                    voiceBaseUrl,
                    activeDeviceName,
                    getExtraMetadataVariables: this._platformAssistantContextProvider,
                    toggleEventName: PLATFORM_LARA_TOGGLE_EVENT,
                }}
            ></flow-ui-drawer>
        `;
    }

    override render(): TemplateResult {
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
        const ctor = this.constructor as PlatformAppCtor;
        const self = this as { getBottomNavItems?: () => BottomNavItem[] };
        const bottomNavItems = typeof self.getBottomNavItems === 'function'
            ? self.getBottomNavItems()
            : (Array.isArray(ctor.bottomNavItems) ? ctor.bottomNavItems : []);
        const bottomNavHideOnRoutes = Array.isArray(ctor.bottomNavHideOnRoutes)
            ? ctor.bottomNavHideOnRoutes
            : [];
        const topBarEnabled = ctor.topBarEnabled === true;
        const topBarHideOnRoutes = Array.isArray(ctor.topBarHideOnRoutes)
            ? ctor.topBarHideOnRoutes
            : [];
        const hideTopBar = routeKey !== null && topBarHideOnRoutes.includes(routeKey);
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
