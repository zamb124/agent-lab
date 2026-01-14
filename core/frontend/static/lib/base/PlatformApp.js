/**
 * PlatformApp - Базовый класс для всех приложений платформы
 */
import { html, css } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import { ServiceRegistry } from '../services/ServiceRegistry.js';

// PWA Install Banner для iOS/Android
import '../components/pwa-install-banner.js';

export class PlatformApp extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            .loading-container {
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                min-height: 100vh;
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
    };

    constructor() {
        super();
        this.router = null;
        this._servicesInitialized = false;
        this._authChecked = false;
        this._isAuthenticated = false;
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
    }

    /**
     * Роутинг. Переопределяется в наследниках.
     */
    setupRoutes() {
        return {};
    }

    /**
     * Проверка авторизации. Переопределяется в наследниках.
     */
    async checkAuth() {
        return true;
    }

    /**
     * Редирект на страницу авторизации
     */
    redirectToAuth() {
        const currentUrl = window.location.href;
        const currentHost = window.location.host;
        const protocol = window.location.protocol;
        
        // Определяем базовый домен без subdomain
        const parts = currentHost.split('.');
        let baseDomain;
        
        if (parts[parts.length - 1].includes(':')) {
            // Локальная разработка с портом (lvh.me:8001)
            const [lastPart, port] = parts[parts.length - 1].split(':');
            parts[parts.length - 1] = lastPart;
            const frontendPort = ':8002'; // Frontend всегда на 8002
            baseDomain = parts.slice(-2).join('.') + frontendPort;
        } else {
            // Продакшн без порта (humanitec.ru)
            baseDomain = parts.slice(-2).join('.');
        }
        
        const loginUrl = `${protocol}//${baseDomain}/login?redirect_uri=${encodeURIComponent(currentUrl)}`;
        window.location.href = loginUrl;
    }

    async connectedCallback() {
        // Инициализация сервисов ДО super.connectedCallback()
        // чтобы Store был доступен для StoreController.hostConnected()
        if (!this._servicesInitialized) {
            await this.initServices();
            this._servicesInitialized = true;
        }
        
        super.connectedCallback();

        // Проверка авторизации
        if (!this._authChecked) {
            this._isAuthenticated = await this.checkAuth();
            this._authChecked = true;
            
            if (!this._isAuthenticated) {
                this.redirectToAuth();
                return;
            }
        }

        // Настройка роутинга
        const routes = this.setupRoutes();
        if (Object.keys(routes).length > 0) {
            const { Router } = await import('../router/Router.js');
            this.router = new Router(this, routes);
            this.router.start();
        }
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        if (this.router) {
            this.router.stop();
        }
    }

    render() {
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

