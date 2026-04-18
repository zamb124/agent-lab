/**
 * PlatformApp - Базовый класс для всех приложений платформы
 */
import { html, css } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import { ServiceRegistry } from '../services/ServiceRegistry.js';
import { AppEvents } from '../utils/types.js';
import { redirectToLogin } from '../utils/auth-redirect.js';
import { nextModalLayerZIndex } from '../utils/modal-z-stack.js';
import { serviceIdFromBaseUrl, setLastVisitedService } from '../utils/last-visited-service.js';
import { i18nDefaultNamespaceForBaseUrl } from '../../services/i18n/i18n-default-namespace.js';

// PWA Install Banner для iOS/Android
import '../components/pwa-install-banner.js';
import '../components/glass-toast.js';
import '../components/platform-shell-page.js';

/**
 * Общий рендер 404 / 500 shell для любого наследника PlatformApp.
 * Вынесен в функцию, чтобы подклассы не полагались на lookup this._renderShellPages
 * (в части окружений имя может пересекаться с полями Lit).
 */
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
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                min-height: var(--app-vh, 100vh);
                padding: 40px;
            }
            
            .loading-spinner {
                width: 48px;
                height: 48px;
                border: 4px solid var(--glass-border-medium);
                border-top-color: var(--accent);
                border-radius: 50%;
                animation: loading-spin 1s linear infinite;
                margin-bottom: 24px;
            }
            
            .loading-text {
                font-size: 16px;
                color: var(--text-muted);
            }
            
            @keyframes loading-spin {
                to { transform: rotate(360deg); }
            }
        `
    ];
    
    static properties = {
        _servicesInitialized: { state: true },
        _authChecked: { state: true },
        _isAuthenticated: { state: true },
        _routeNotFound: { state: true },
        _notFoundHomeHref: { state: true },
        _fatalShell: { state: true },
    };

    constructor() {
        super();
        this.router = null;
        this._servicesInitialized = false;
        this._authChecked = false;
        this._isAuthenticated = false;
        this._routeNotFound = false;
        this._notFoundHomeHref = '/';
        this._fatalShell = null;
        /** @private Слушатель window toast-show: один раз на экземпляр, до await initServices */
        this._toastListenerAttached = false;
        this._handleToast = this._handleToast.bind(this);
        this._pushAuthListenerAttached = false;
        this._onAuthChangeForPush = this._onAuthChangeForPush.bind(this);
    }

    _handleToast(e) {
        const detail = e.detail || {};
        const type = detail.type ?? 'info';
        const message = detail.message ?? '';
        const duration = detail.duration ?? 3000;
        if (!message) {
            return;
        }
        const toast = document.createElement('glass-toast');
        toast.type = type;
        toast.message = message;
        toast.duration = duration;
        toast.style.zIndex = String(nextModalLayerZIndex());
        document.body.appendChild(toast);
    }

    /**
     * Store для приложения. Переопределяется в наследниках.
     */
    setupStore() {
        return null;
    }

    /**
     * Базовый URL сервиса. Переопределяется в наследниках.
     */
    getBaseUrl() {
        return '';
    }

    /**
     * Инициализация сервисов. Переопределяется в наследниках.
     */
    async initServices() {
        const store = this.setupStore();
        if (store) {
            window.__PLATFORM_STORE__ = store;
        }
        
        await ServiceRegistry.registerCore(this.getBaseUrl());
        const i18nNs = i18nDefaultNamespaceForBaseUrl(this.getBaseUrl());
        if (i18nNs.length > 0) {
            ServiceRegistry.get('i18n').setDefaultNamespace(i18nNs);
        }
    }

    /**
     * Настройка Router. Переопределяется в наследниках.
     * @returns {Object|null} Конфигурация Router { routes: [...], baseUrl, store }
     */
    setupRouter() {
        return null;
    }

    /**
     * Проверка авторизации. Переопределяется в наследниках.
     */
    async checkAuth() {
        return true;
    }

    /**
     * До checkAuth: можно пропустить стандартный вход (например, показать 404 без редиректа).
     * Возвращает null или объект { skip, authenticated, _routeNotFound?, _notFoundHomeHref?, _fatalShell? }.
     */
    async _preAuthCheck() {
        return null;
    }

    _isFatalServerError(err) {
        if (!err) {
            return false;
        }
        if (err.code === 'AUTH_SERVER_ERROR') {
            return true;
        }
        const msg = String(err.message || '');
        return msg.includes('HTTP 500');
    }

    /**
     * Редирект на страницу авторизации
     */
    redirectToAuth() {
        redirectToLogin();
    }

    _renderShellPages() {
        return renderPlatformAppShell(this);
    }

    _recordLastVisitedServiceFromApp() {
        const id = serviceIdFromBaseUrl(this.getBaseUrl());
        if (id) {
            setLastVisitedService(id);
        }
    }

    _maybeRegisterPushSubscriptions() {
        if (!this._isAuthenticated || !ServiceRegistry.isInitialized || !ServiceRegistry.has('pwa')) {
            return;
        }
        queueMicrotask(() => {
            ServiceRegistry.get('pwa')
                .ensurePushRegistration()
                .catch((err) => {
                    console.error('[PlatformApp] ensurePushRegistration:', err);
                });
        });
    }

    _onAuthChangeForPush(ev) {
        if (ev.detail?.isAuthenticated) {
            this._maybeRegisterPushSubscriptions();
        }
    }

    async connectedCallback() {
        try {
            if (!this._toastListenerAttached) {
                window.addEventListener(AppEvents.TOAST_SHOW, this._handleToast);
                this._toastListenerAttached = true;
            }

            if (!this._servicesInitialized) {
                await this.initServices();
                this._servicesInitialized = true;
            }

            super.connectedCallback();

            if (!this._authChecked) {
                const pre = await this._preAuthCheck();
                if (pre && pre.skip) {
                    this._routeNotFound = !!pre._routeNotFound;
                    this._notFoundHomeHref = pre._notFoundHomeHref || '/';
                    if (pre._fatalShell) {
                        this._fatalShell = pre._fatalShell;
                    }
                    this._isAuthenticated = pre.authenticated === true;
                    this._authChecked = true;
                    return;
                }

                try {
                    this._isAuthenticated = await this.checkAuth();
                } catch (authErr) {
                    if (this._isFatalServerError(authErr)) {
                        this._fatalShell = 'server-error';
                        this._isAuthenticated = false;
                        this._authChecked = true;
                        return;
                    }
                    throw authErr;
                }

                this._authChecked = true;

                if (!this._isAuthenticated) {
                    this.redirectToAuth();
                    return;
                }

                this._recordLastVisitedServiceFromApp();
                this._maybeRegisterPushSubscriptions();
                if (!this._pushAuthListenerAttached) {
                    window.addEventListener(AppEvents.AUTH_CHANGE, this._onAuthChangeForPush);
                    this._pushAuthListenerAttached = true;
                }
            }

            const routerConfig = this.setupRouter();
            if (routerConfig) {
                const { Router } = await import('../router/Router.js');
                this.router = new Router(this, {
                    baseUrl: this.getBaseUrl(),
                    store: this.setupStore() || null,
                });
                
                if (routerConfig.routes) {
                    this.router.registerRoutes(routerConfig.routes);
                }
                
                this.router.start();
                window.__PLATFORM_ROUTER__ = this.router;
            }
        } catch (err) {
            console.error('[PlatformApp] Ошибка инициализации:', err);
            if (this._isFatalServerError(err)) {
                this._fatalShell = 'server-error';
                this._servicesInitialized = true;
                this._authChecked = true;
                this._isAuthenticated = false;
                return;
            }
            this.redirectToAuth();
        }
    }

    disconnectedCallback() {
        if (this._pushAuthListenerAttached) {
            window.removeEventListener(AppEvents.AUTH_CHANGE, this._onAuthChangeForPush);
            this._pushAuthListenerAttached = false;
        }
        if (this._toastListenerAttached) {
            window.removeEventListener(AppEvents.TOAST_SHOW, this._handleToast);
            this._toastListenerAttached = false;
        }
        super.disconnectedCallback();
        if (this.router) {
            this.router.stop();
        }
    }

    render() {
        const shell = renderPlatformAppShell(this);
        if (shell !== null) {
            return shell;
        }

        if (!this._servicesInitialized || !this._authChecked) {
            return html`<div>Loading...</div>`;
        }

        if (!this._isAuthenticated) {
            return html`<div>Redirecting to auth...</div>`;
        }

        // Если есть роутер - он сам отрендерит нужную страницу
        if (this.router) {
            return html`
                ${this.router.render()}
                <pwa-install-banner></pwa-install-banner>
            `;
        }

        // По умолчанию пустой контент - наследники переопределяют
        return html`
            <slot></slot>
            <pwa-install-banner></pwa-install-banner>
        `;
    }
}

