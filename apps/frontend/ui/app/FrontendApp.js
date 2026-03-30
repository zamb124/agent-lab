/**
 * FrontendApp - Главное приложение фронтенд сервиса
 */
import { html, css } from 'lit';
import { PlatformApp, renderPlatformAppShell } from '@platform/lib/base/PlatformApp.js';
import { CompaniesService } from '@platform/services/companies.service.js';
import { TeamService } from '../services/team.service.js';
import { ApiKeysService } from '../services/api-keys.service.js';
import { BillingService } from '../services/billing.service.js';
import { SettingsService } from '../services/settings.service.js';
import { ServicesStatusService } from '../services/services-status.service.js';
import { EmbedService } from '../services/embed.service.js';
import { FlowsCatalogService } from '../services/flows-catalog.service.js';
import { SchedulerTasksService } from '../services/scheduler-tasks.service.js';
import { FrontendStore } from '../store/frontend.store.js';
import '@platform/lib/components/layout/platform-island.js';
import '@platform/lib/components/auth-modal.js';

export class FrontendApp extends PlatformApp {

    static styles = [
        PlatformApp.styles,
        css`
            :host {
                display: flex !important;
                flex-direction: row !important;
                width: var(--app-vw, 100vw);
                height: var(--app-vh, 100vh);
                overflow: hidden;
                background: var(--bg-gradient);
            }
            
            :host([landing]) {
                display: block !important;
                overflow-y: auto;
            }
            
            landing-page,
            legal-page,
            select-company-page,
            product-agents-page,
            product-rag-page,
            product-crm-page,
            product-sync-page {
                display: block;
                width: 100%;
                min-height: var(--app-vh, 100vh);
            }
            
            .sidebar {
                height: var(--app-vh, 100vh);
                flex-shrink: 0;
                overflow: visible;
                background: transparent;
            }
            
            .main {
                flex: 1;
                height: var(--app-vh, 100vh);
                overflow-y: auto;
                display: flex;
                padding: var(--space-4);
            }
            
            platform-island {
                flex: 1;
                min-height: calc(var(--app-vh, 100vh) - 2rem);
            }

            @media (max-width: 767px) {
                .sidebar {
                    position: absolute;
                    width: 0;
                    height: 0;
                    overflow: visible;
                }

                .main {
                    padding: 0;
                }
            }
            
            .loading-container {
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                width: 100%;
                height: 100%;
                background: var(--bg-gradient);
            }
            
            .loading-spinner {
                width: 48px;
                height: 48px;
                border: 4px solid var(--glass-border-subtle);
                border-top: 4px solid var(--accent);
                border-radius: 50%;
                animation: spin 1s linear infinite;
                margin-bottom: var(--space-4);
            }
            
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
            
            .loading-text {
                font-size: var(--text-base);
                color: var(--text-secondary);
            }

            .login-shell {
                display: block;
                width: 100%;
                min-height: var(--app-vh, 100vh);
                background: var(--bg-gradient);
            }
        `
    ];

    constructor() {
        super();
        this._isLanding = false;
        
        this.state = this.use((s) => ({
            currentView: s.ui.currentView,
        }));
    }

    /**
     * Персистентный ui.currentView и URL расходятся: сайдбар меняет только store.
     * При заходе по /dashboard в store мог остаться другой таб (например scheduler-tasks),
     * плюс при откате деплоя старый бандл без case для нового view падает с Unknown view.
     */
    static _VIEW_BY_PATH = new Map([
        ['/dashboard', 'dashboard'],
        ['/team', 'team'],
        ['/api-keys', 'api-keys'],
        ['/billing', 'billing'],
        ['/embed-configs', 'embed-configs'],
        ['/settings', 'settings'],
        ['/scheduler-tasks', 'scheduler-tasks'],
    ]);

    _syncCurrentViewFromPathname() {
        const path = window.location.pathname;
        let view = FrontendApp._VIEW_BY_PATH.get(path);
        if (!view && path.startsWith('/settings/')) {
            view = 'settings';
        }
        if (view) {
            FrontendStore.setCurrentView(view);
        }
    }

    connectedCallback() {
        this._syncCurrentViewFromPathname();
        super.connectedCallback();
    }

    setupStore() {
        return FrontendStore;
    }

    getBaseUrl() {
        return '/frontend';
    }

    async initServices() {
        await super.initServices();
        
        const baseUrl = this.getBaseUrl();
        this.services.register('companies', new CompaniesService(baseUrl));
        this.services.register('team', new TeamService(baseUrl));
        this.services.register('apiKeys', new ApiKeysService(baseUrl));
        this.services.register('billing', new BillingService(baseUrl));
        this.services.register('settings', new SettingsService(baseUrl));
        this.services.register('servicesStatus', new ServicesStatusService(baseUrl));
        this.services.register('embed', new EmbedService(baseUrl));
        this.services.register('flowsCatalog', new FlowsCatalogService());
        this.services.register('schedulerTasks', new SchedulerTasksService(baseUrl));
    }

    _isKnownRoute(path) {
        const exact = new Set([
            '/',
            '/login',
            '/frontend/login',
            '/select-company',
            '/join',
            '/policy',
            '/terms',
            '/products/agents',
            '/products/rag',
            '/products/crm',
            '/products/sync',
            '/dashboard',
            '/team',
            '/api-keys',
            '/billing',
            '/embed-configs',
            '/scheduler-tasks',
        ]);
        if (exact.has(path)) {
            return true;
        }
        if (path === '/settings' || path.startsWith('/settings/')) {
            return true;
        }
        return false;
    }

    async _preAuthCheck() {
        const path = window.location.pathname;
        if (!this._isKnownRoute(path)) {
            let homeHref = path.startsWith('/products/') ? '/' : '/';
            try {
                if (await this.auth.validateToken()) {
                    homeHref = '/dashboard';
                }
            } catch (e) {
                if (e.code === 'AUTH_SERVER_ERROR') {
                    throw e;
                }
            }
            return {
                skip: true,
                authenticated: false,
                _routeNotFound: true,
                _notFoundHomeHref: homeHref,
            };
        }
        return null;
    }

    _loginReturnPathFromQuery() {
        const raw = new URLSearchParams(window.location.search).get('redirect_uri');
        if (!raw) {
            return '/dashboard';
        }
        let parsed;
        try {
            // Поддерживаем как абсолютный URL, так и относительный путь.
            parsed = new URL(raw, window.location.origin);
        } catch {
            return '/dashboard';
        }
        if (parsed.origin !== window.location.origin) {
            return '/dashboard';
        }
        if (!parsed.pathname.startsWith('/')) {
            return '/dashboard';
        }
        return `${parsed.pathname}${parsed.search}${parsed.hash}`;
    }

    async checkAuth() {
        const path = window.location.pathname;
        
        // Публичные страницы без авторизации
        if (path === '/' || path.startsWith('/products/') || path === '/policy' || path === '/terms') {
            this._isLanding = true;
            this._productPage = path.startsWith('/products/') ? path : null;
            return true;
        }

        if (path === '/login' || path === '/frontend/login') {
            this._isLanding = true;
            this._productPage = null;
            return true;
        }
        
        if (path === '/select-company') {
            this._isLanding = true;
            this._productPage = null;
            return await this.auth.validateToken();
        }

        // Страница принятия инвайта — публичная, компонент сам проверяет auth
        if (path === '/join') {
            this._isLanding = true;
            this._productPage = null;
            return true;
        }
        
        this._isLanding = false;
        this._productPage = null;
        return await this.auth.validateToken();
    }
    
    _normalizeCurrentView(currentView) {
        const normalizedView = String(currentView ?? '')
            .trim()
            .replace(/^\/+/, '')
            .replace(/\/+$/, '')
            .split('?')[0]
            .split('#')[0]
            .replace(/_/g, '-')
            .toLowerCase();

        if (!normalizedView) {
            throw new Error('currentView must be a non-empty string');
        }

        return normalizedView;
    }

    _renderContent() {
        const { currentView } = this.state.value;
        const normalizedView = this._normalizeCurrentView(currentView);

        switch (normalizedView) {
            case 'dashboard':
                return html`<dashboard-page></dashboard-page>`;
            case 'team':
                return html`<team-page></team-page>`;
            case 'api-keys':
                return html`<api-keys-page></api-keys-page>`;
            case 'billing':
                return html`<billing-page></billing-page>`;
            case 'embed-configs':
                return html`<embed-configs-page></embed-configs-page>`;
            case 'settings':
                return html`<settings-page></settings-page>`;
            case 'scheduler-tasks':
                return html`<scheduler-tasks-page></scheduler-tasks-page>`;
            default:
                throw new Error(`Unknown view: ${normalizedView}`);
        }
    }

    render() {
        const shell = renderPlatformAppShell(this);
        if (shell !== null) {
            return shell;
        }

        if (!this._servicesInitialized || !this._authChecked) {
            return html`
                <div class="loading-container">
                    <div class="loading-spinner"></div>
                    <div class="loading-text">Загрузка Frontend...</div>
                </div>
            `;
        }

        if (!this._isAuthenticated) {
            return html`
                <div class="loading-container">
                    <div class="loading-spinner"></div>
                    <div class="loading-text">Перенаправление на вход...</div>
                </div>
            `;
        }

        if (this._isLanding) {
            this.setAttribute('landing', '');
            const path = window.location.pathname;
            
            if (path === '/select-company') {
                return html`<select-company-page></select-company-page>`;
            }

            if (path === '/join') {
                return html`<join-page></join-page>`;
            }

            if (path === '/policy') {
                return html`<legal-page docType="policy"></legal-page>`;
            }

            if (path === '/terms') {
                return html`<legal-page docType="terms"></legal-page>`;
            }

            if (path === '/login' || path === '/frontend/login') {
                const returnPath = this._loginReturnPathFromQuery();
                return html`
                    <div class="login-shell">
                        <auth-modal .open=${true} .returnPath=${returnPath}></auth-modal>
                    </div>
                `;
            }

            if (path === '/products/agents') {
                return html`<product-agents-page></product-agents-page>`;
            }
            
            if (path === '/products/rag') {
                return html`<product-rag-page></product-rag-page>`;
            }
            
            if (path === '/products/crm') {
                return html`<product-crm-page></product-crm-page>`;
            }
            
            if (path === '/products/sync') {
                return html`<product-sync-page></product-sync-page>`;
            }
            
            return html`<landing-page></landing-page>`;
        }

        this.removeAttribute('landing');
        
        return html`
            <div class="sidebar">
                <frontend-sidebar></frontend-sidebar>
            </div>

            <div class="main">
                <platform-island>
                    ${this._renderContent()}
                </platform-island>
            </div>
        `;
    }
}

customElements.define('frontend-app', FrontendApp);
