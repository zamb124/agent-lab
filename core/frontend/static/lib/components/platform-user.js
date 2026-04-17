/**
 * Универсальный компонент пользователя для всех сервисов платформы.
 * 
 * Особенности:
 * - Автоматическая загрузка данных пользователя через auth сервис
 * - Выпадающее меню с полным функционалом
 * - Поддержка service-specific атрибутов
 * - Смена компании (если доступно несколько)
 * - Реактивность через AppEvents
 */

import { html, css } from 'lit';
import { classMap } from 'lit/directives/class-map.js';
import { PlatformElement } from '../platform-element/index.js';
import { openUrlSameWindowOrTab } from '../utils/native-app-shell.js';
import { AppEvents } from '../utils/types.js';
import { buildScenarioDocumentationUrl } from '../utils/documentation-url.js';
import { buildCompanySubdomainUrl } from '../utils/tenant-url.js';
import { createAvatarRetry } from '../utils/avatar-retry.js';
import { buildServiceEntryUrl, setLastVisitedService } from '../utils/last-visited-service.js';
import './platform-icon.js';

export class PlatformUser extends PlatformElement {
    static properties = {
        user: { type: Object },
        serviceAttrs: { type: Object },
        companies: { type: Array },
        _menuOpen: { type: Boolean },
        _companySelectorOpen: { type: Boolean },
        _appsMenuOpen: { type: Boolean },
        _avatarRetryTick: { type: Number, state: true },
        /** Необязательный тег сценария (docs/scenarios/<service>/<tag>/), если UI привязан к процессу */
        documentationTag: { type: String },
    };

    constructor() {
        super();
        this.user = null;
        this.serviceAttrs = null;
        this.companies = [];
        this._menuOpen = false;
        this._companySelectorOpen = false;
        this._appsMenuOpen = false;
        this._avatarRetry = createAvatarRetry(() => this.requestUpdate());
        this.documentationTag = null;
        this._boundRepositionMenu = this._syncCollapsedMenuPosition.bind(this);
        this._boundDocumentClick = (e) => this._handleDocumentClick(e);
        this._boundCompanySwitchStorage = (e) => this._handleCompanySwitchStorage(e);
        this._boundWindowFocus = () => this._scheduleCompanyAlignmentCheck();
        this._boundWindowPageShow = () => {
            this._companyAlignmentSkipUntil = 0;
            this._scheduleCompanyAlignmentCheck();
        };
        this._boundVisibilityChange = () => {
            if (document.visibilityState === 'visible') {
                this._companyAlignmentSkipUntil = 0;
                this._scheduleCompanyAlignmentCheck();
            }
        };
        this._companyAlignmentIntervalId = null;
        this._companyAlignmentInFlight = false;
        this._companyAlignmentQueued = false;
        this._companyAlignmentSkipUntil = 0;
        this._companyAlignmentNetworkFailures = 0;
        this._boundOnline = () => this._onBrowserOnline();
        this._i18nUnsub = null;
    }

    /**
     * Сетевой сбой (сервер не слушает, DNS, offline): fetch бросает TypeError, не HTTP-ответ.
     */
    _isAuthMeNetworkFailure(error) {
        if (!error || typeof error !== 'object') {
            return false;
        }
        const name = error.name;
        const message = typeof error.message === 'string' ? error.message : '';
        if (name === 'TypeError' && message.includes('fetch')) {
            return true;
        }
        return false;
    }

    _onBrowserOnline() {
        this._companyAlignmentSkipUntil = 0;
        this._companyAlignmentNetworkFailures = 0;
        this._scheduleCompanyAlignmentCheck();
    }

    _pt(key, params = {}) {
        return this.i18n.t(key, params, 'platform');
    }

    connectedCallback() {
        super.connectedCallback();
        this._loadUser();
        window.addEventListener(AppEvents.AUTH_CHANGE, () => this._loadUser());
        document.addEventListener('click', this._boundDocumentClick);
        window.addEventListener('storage', this._boundCompanySwitchStorage);
        window.addEventListener('focus', this._boundWindowFocus);
        window.addEventListener('pageshow', this._boundWindowPageShow);
        window.addEventListener('online', this._boundOnline);
        document.addEventListener('visibilitychange', this._boundVisibilityChange);
        this._companyAlignmentIntervalId = window.setInterval(() => {
            this._scheduleCompanyAlignmentCheck();
        }, 5000);
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._avatarRetry.cancel();
        document.removeEventListener('click', this._boundDocumentClick);
        window.removeEventListener('storage', this._boundCompanySwitchStorage);
        window.removeEventListener('focus', this._boundWindowFocus);
        window.removeEventListener('pageshow', this._boundWindowPageShow);
        window.removeEventListener('online', this._boundOnline);
        document.removeEventListener('visibilitychange', this._boundVisibilityChange);
        if (this._companyAlignmentIntervalId !== null) {
            window.clearInterval(this._companyAlignmentIntervalId);
            this._companyAlignmentIntervalId = null;
        }
        this._detachCollapsedMenuListeners();
        this._clearCollapsedMenuPosition();
    }

    updated(changedProperties) {
        super.updated(changedProperties);
        if (changedProperties.has('_menuOpen')) {
            if (this._menuOpen) {
                this._attachCollapsedMenuListeners();
                this.updateComplete.then(() => this._syncCollapsedMenuPosition());
            } else {
                this._detachCollapsedMenuListeners();
                this._clearCollapsedMenuPosition();
            }
        }
    }

    _attachCollapsedMenuListeners() {
        window.addEventListener('resize', this._boundRepositionMenu);
        window.addEventListener('scroll', this._boundRepositionMenu, true);
    }

    _detachCollapsedMenuListeners() {
        window.removeEventListener('resize', this._boundRepositionMenu);
        window.removeEventListener('scroll', this._boundRepositionMenu, true);
    }

    _clearCollapsedMenuPosition() {
        this.style.removeProperty('--user-menu-fixed-left');
        this.style.removeProperty('--user-menu-fixed-bottom');
        this.style.removeProperty('--user-menu-fixed-width');
    }

    _syncCollapsedMenuPosition() {
        if (!this._menuOpen) {
            return;
        }
        const sidebar = this.closest('platform-sidebar');
        if (!sidebar?.hasAttribute('collapsed')) {
            this._clearCollapsedMenuPosition();
            return;
        }
        const anchor = this.renderRoot?.querySelector('.user-bar');
        if (!anchor) {
            return;
        }
        const rect = anchor.getBoundingClientRect();
        const margin = 8;
        const maxW = Math.min(240, window.innerWidth - 2 * margin);
        let left = rect.left;
        if (left + maxW > window.innerWidth - margin) {
            left = window.innerWidth - maxW - margin;
        }
        if (left < margin) {
            left = margin;
        }
        const bottom = window.innerHeight - rect.top + margin;
        this.style.setProperty('--user-menu-fixed-left', `${left}px`);
        this.style.setProperty('--user-menu-fixed-bottom', `${bottom}px`);
        this.style.setProperty('--user-menu-fixed-width', `${maxW}px`);
    }

    async _loadUser() {
        if (!this.auth) {
            this.user = null;
            return;
        }

        const userData = await this.auth.get('/api/auth/me');
        this.user = userData;
        this._avatarRetry.reset();
        await this._loadCompanies();
        this._ensureCompanyAlignment();
        await this._loadServiceAttrs();
    }

    async _loadCompanies() {
        const body = await this.auth.get('/api/companies/me');
        if (!body || typeof body !== 'object' || !Array.isArray(body.items)) {
            throw new Error('Некорректный ответ /api/companies/me: ожидался объект с массивом items');
        }
        const companyItems = body.items;

        this.companies = companyItems.map((company) => ({
            company_id: company.company_id,
            subdomain: company.subdomain,
            name: company.subdomain,
            roles: company.role
        }));
    }

    async _loadServiceAttrs() {
        const service = this._getCurrentService();
        if (!service) return;
        
        try {
            this.serviceAttrs = await this.auth.getServiceAttrs(service);
        } catch (error) {
            console.error(`[PlatformUser] Failed to load ${service} attrs:`, error);
        }
    }

    _getCurrentService() {
        const path = window.location.pathname;
        const match = path.match(/^\/([^\/]+)/);
        const service = match?.[1];
        
        if (!service || ['static', 'api', 'ws'].includes(service)) {
            return null;
        }
        
        return service;
    }

    async _updateServiceAttrs(attrs) {
        const service = this._getCurrentService();
        if (!service) {
            throw new Error('Cannot determine current service');
        }
        
        return await this.auth.updateServiceAttrs(service, attrs);
    }

    _toggleMenu(e) {
        e.stopPropagation();
        const nextOpen = !this._menuOpen;
        this._menuOpen = nextOpen;
        if (!nextOpen) {
            this._companySelectorOpen = false;
            this._appsMenuOpen = false;
        }
        this.requestUpdate();
    }

    _handleDocumentClick(e) {
        const path = e.composedPath();
        const inside = path.includes(this);
        if (!inside && this._menuOpen) {
            this._menuOpen = false;
            this._companySelectorOpen = false;
            this._appsMenuOpen = false;
            this.requestUpdate();
        }
    }

    _toggleAppsMenu(e) {
        e.stopPropagation();
        this._appsMenuOpen = !this._appsMenuOpen;
        this.requestUpdate();
    }

    _serviceAppEntries() {
        return [
            { id: 'flows', logo: '/static/core/assets/service_logos/agents_logo.svg' },
            { id: 'crm', logo: '/static/core/assets/service_logos/crm_logo.svg' },
            { id: 'rag', logo: '/static/core/assets/service_logos/rag_logo.svg' },
            { id: 'sync', logo: '/static/core/assets/service_logos/sync_logo.svg' },
            { id: 'documents', logo: '/static/core/assets/service_logos/documents_logo.svg' },
            { id: 'frontend', logo: '/static/core/assets/service_logos/frontend_logo.svg' },
        ];
    }

    async _setUiLocale(lang, e) {
        e.stopPropagation();
        try {
            await this.i18n.setLocale(lang);
        } catch (err) {
            this.error(err instanceof Error ? err.message : String(err));
            throw err;
        }
    }

    _openServiceApp(serviceId, event) {
        event.stopPropagation();
        setLastVisitedService(serviceId);
        const url = buildServiceEntryUrl(serviceId);
        openUrlSameWindowOrTab(url);
    }

    _getUserInitials() {
        if (!this.user) return '?';
        const name = this.user.name || this.user.emails?.[0] || '';
        return name.charAt(0).toUpperCase();
    }

    _avatarDisplayUrl() {
        const raw = this.user?.avatar_url;
        if (typeof raw !== 'string') {
            return null;
        }
        const trimmed = raw.trim();
        return trimmed !== '' ? trimmed : null;
    }

    _renderAvatar() {
        const originalUrl = this._avatarDisplayUrl();
        const src = this._avatarRetry.currentSrc(originalUrl);
        if (src) {
            return html`
                <div class="user-avatar has-image" aria-hidden="true">
                    <img
                        class="avatar-img"
                        src=${src}
                        alt=""
                        @load=${() => this._avatarRetry.onLoad()}
                        @error=${() => this._avatarRetry.onError(originalUrl)}
                    />
                </div>
            `;
        }
        return html`
            <div class="user-avatar" aria-hidden="true">${this._getUserInitials()}</div>
        `;
    }

    async _openProfileModal() {
        this._menuOpen = false;
        
        try {
            await import('./user-profile-modal.js');
            
            console.log('[PlatformUser] About to createElement...');
            console.log('[PlatformUser] customElements.get result:', customElements.get('user-profile-modal'));
            console.log('[PlatformUser] Trying new instead...');
            
            // Пробуем напрямую через конструктор
            const ModalClass = customElements.get('user-profile-modal');
            const modal = new ModalClass();
            
            console.log('[PlatformUser] Modal created via new:', modal);
            
            modal.user = this.user;
            modal.activeCompanyName = this._getCompanyName(this.user.active_company_id || this.user.company_id);
            modal.open = true;
            document.body.appendChild(modal);
            
            modal.addEventListener('close', () => {
                modal.remove();
            });
            modal.addEventListener('updated', () => this._loadUser());
        } catch (error) {
            console.error('[PlatformUser] Failed to open profile modal:', error);
        }
    }

    _toggleCompanySelector(e) {
        e.stopPropagation();
        this._companySelectorOpen = !this._companySelectorOpen;
        this.requestUpdate();
    }

    async _switchCompany(companyId, e) {
        e.stopPropagation();
        
        if (companyId === this.user?.active_company_id) {
            return;
        }

        try {
            await this.auth.switchCompany(companyId);
            const company = this.companies.find((item) => item.company_id === companyId);
            if (!company?.subdomain) {
                throw new Error(this._pt('company.subdomain_missing'));
            }
            this.success(this._pt('company.switched'));
            this._broadcastCompanySwitch(company);
            const targetPath = `${window.location.pathname}${window.location.search}${window.location.hash}`;
            const targetUrl = buildCompanySubdomainUrl(company.subdomain, targetPath);
            window.location.href = targetUrl;
        } catch (error) {
            console.error('[PlatformUser] Failed to switch company:', error);
            const msg = error instanceof Error ? error.message : String(error);
            this.error(this._pt('company.switch_error', { message: msg }));
        }
    }

    _broadcastCompanySwitch(company) {
        const payload = `${Date.now()}|${company.company_id}|${company.subdomain}`;
        window.localStorage.setItem('platform:company-switch', payload);
    }

    _handleCompanySwitchStorage(event) {
        if (event.key !== 'platform:company-switch' || !event.newValue) {
            return;
        }

        const parts = event.newValue.split('|');
        if (parts.length !== 3) {
            return;
        }

        const [, , targetSubdomain] = parts;
        if (!targetSubdomain) {
            return;
        }

        const targetPath = `${window.location.pathname}${window.location.search}${window.location.hash}`;
        const targetUrl = buildCompanySubdomainUrl(targetSubdomain, targetPath);
        if (targetUrl === window.location.href) {
            return;
        }
        window.location.href = targetUrl;
    }

    _scheduleCompanyAlignmentCheck() {
        if (this._companyAlignmentInFlight) {
            this._companyAlignmentQueued = true;
            return;
        }
        this._checkCompanyAlignment();
    }

    async _checkCompanyAlignment() {
        if (typeof Date.now === 'function' && Date.now() < this._companyAlignmentSkipUntil) {
            return;
        }
        this._companyAlignmentInFlight = true;
        try {
            try {
                const userData = await this.auth.get('/api/auth/me');
                this._companyAlignmentNetworkFailures = 0;
                this._companyAlignmentSkipUntil = 0;
                this.user = userData;
                if (!Array.isArray(this.companies) || this.companies.length === 0) {
                    await this._loadCompanies();
                }
                this._ensureCompanyAlignment();
            } catch (error) {
                if (this._isAuthMeNetworkFailure(error)) {
                    this._companyAlignmentNetworkFailures += 1;
                    const exp = Math.min(this._companyAlignmentNetworkFailures, 6);
                    const delayMs = Math.min(120000, 5000 * 2 ** exp);
                    this._companyAlignmentSkipUntil = Date.now() + delayMs;
                    return;
                }
                throw error;
            }
        } finally {
            this._companyAlignmentInFlight = false;
            if (this._companyAlignmentQueued) {
                this._companyAlignmentQueued = false;
                this._scheduleCompanyAlignmentCheck();
            }
        }
    }

    _ensureCompanyAlignment() {
        if (!this.user?.company_id) {
            return;
        }
        const selectedCompany = this.companies.find((company) => company.company_id === this.user.company_id);
        if (!selectedCompany?.subdomain) {
            return;
        }

        const currentSubdomain = this._getCurrentSubdomain();
        if (currentSubdomain === selectedCompany.subdomain) {
            return;
        }

        const targetPath = `${window.location.pathname}${window.location.search}${window.location.hash}`;
        const targetUrl = buildCompanySubdomainUrl(selectedCompany.subdomain, targetPath);
        if (targetUrl === window.location.href) {
            return;
        }
        window.location.href = targetUrl;
    }

    _getCurrentSubdomain() {
        const hostname = window.location.hostname;
        if (hostname.endsWith('.lvh.me')) {
            return hostname.slice(0, -'.lvh.me'.length);
        }
        if (hostname.endsWith('.localhost')) {
            return hostname.slice(0, -'.localhost'.length);
        }
        if (hostname.endsWith('.humanitec.ru')) {
            return hostname.slice(0, -'.humanitec.ru'.length);
        }
        if (hostname.endsWith('.agents-lab.ru')) {
            return hostname.slice(0, -'.agents-lab.ru'.length);
        }
        return null;
    }

    _openSettings() {
        this._menuOpen = false;
        
        const service = this._getCurrentService() || 'frontend';
        window.location.href = `/${service}/settings`;
    }

    async _openCalendar() {
        this._menuOpen = false;
        await import('./platform-calendar-modal.js');
        const modal = document.createElement('platform-calendar-modal');
        document.body.appendChild(modal);
        modal.showModal();
        const cleanup = () => modal.remove();
        modal.addEventListener('modal-closed', cleanup, { once: true });
    }

    _openDocumentation() {
        this._menuOpen = false;
        const tag =
            typeof this.documentationTag === 'string' && this.documentationTag.trim()
                ? this.documentationTag.trim()
                : null;
        const url = buildScenarioDocumentationUrl({ tag });
        openUrlSameWindowOrTab(url);
    }

    _toggleTheme() {
        this.theme?.toggle();
    }

    async _logout() {
        this._menuOpen = false;
        
        try {
            await this.auth?.logout();
            window.location.href = '/';
        } catch (error) {
            console.error('[PlatformUser] Logout failed:', error);
            window.location.href = '/';
        }
    }

    _getCompanyName(companyId) {
        const company = this.companies.find(c => c.company_id === companyId);
        return company?.name || '';
    }

    render() {
        if (!this.user) {
            return html``;
        }

        const currentCompanyName = this._getCompanyName(this.user.active_company_id || this.user.company_id);
        const hasMultipleCompanies = this.companies.length > 1;
        const uiLocale = this.i18n.getCurrentLocale();

        return html`
            <div class="user-container">
                <div class="user-bar">
                    <button
                        type="button"
                        class="user-button"
                        @click=${this._toggleMenu}
                        title=${this._pt('menu.user_button_title')}
                        aria-expanded=${this._menuOpen ? 'true' : 'false'}
                        aria-haspopup="true"
                    >
                        ${this._renderAvatar()}
                        <div class="user-info">
                            <div class="user-name">${this.user.name || this._pt('menu.user_fallback')}</div>
                            <div class="user-email">${this.user.emails?.[0] || ''}</div>
                        </div>
                        <span class="user-lang-badge" aria-hidden="true">${uiLocale.toUpperCase()}</span>
                    </button>
                    <span class="user-toolbar-wrap"><slot name="user-toolbar"></slot></span>
                    <button
                        type="button"
                        class="user-menu-chevron"
                        @click=${this._toggleMenu}
                        title=${this._pt('menu.user_button_title')}
                        aria-expanded=${this._menuOpen ? 'true' : 'false'}
                        aria-haspopup="true"
                    >
                        <platform-icon name="chevron-down" size="12" class="chevron ${this._menuOpen ? 'open' : ''}"></platform-icon>
                    </button>
                </div>

                ${this._menuOpen ? html`
                    <div class="user-menu">
                        <button class="menu-item apps-item" @click=${this._toggleAppsMenu}>
                            <img class="apps-menu-logo" src="/static/core/assets/service_logos/agents_logo.svg" alt="" />
                            <span>${this._pt('menu.apps')}</span>
                            <platform-icon name="chevron-right" size="12" class="expand-icon ${this._appsMenuOpen ? 'open' : ''}"></platform-icon>
                        </button>

                        ${this._appsMenuOpen ? html`
                            <div class="apps-grid">
                                ${this._serviceAppEntries().map((service) => html`
                                    <button class="app-card" @click=${(event) => this._openServiceApp(service.id, event)}>
                                        <span class="app-card-header">
                                            <img class="app-logo" src="${service.logo}" alt="" />
                                            <platform-icon name="arrow-right" size="16" class="app-go-icon"></platform-icon>
                                        </span>
                                        <span class="app-card-name">${this._pt(`apps.${service.id}.name`)}</span>
                                        <span class="app-card-description">${this._pt(`apps.${service.id}.description`)}</span>
                                    </button>
                                `)}
                            </div>
                        ` : ''}

                        <div class="menu-divider"></div>

                        <button class="menu-item" @click=${this._openProfileModal}>
                            <platform-icon name="user" size="18" class="menu-icon"></platform-icon>
                            <span>${this._pt('menu.profile')}</span>
                        </button>
                        
                        ${hasMultipleCompanies ? html`
                            <div class="menu-divider"></div>
                            <button class="menu-item company-selector" @click=${this._toggleCompanySelector}>
                                <platform-icon name="building-one" size="18" class="menu-icon company-building-icon"></platform-icon>
                                <span class="company-name company-name-inline">
                                    <span>${currentCompanyName}</span>
                                </span>
                                <platform-icon name="chevron-right" size="12" class="expand-icon ${this._companySelectorOpen ? 'open' : ''}"></platform-icon>
                            </button>
                            
                            ${this._companySelectorOpen ? html`
                                <div class="company-list">
                                    ${this.companies.map(company => html`
                                        <button 
                                            class="company-item ${company.company_id === (this.user.active_company_id || this.user.company_id) ? 'active' : ''}"
                                            @click=${(e) => this._switchCompany(company.company_id, e)}
                                        >
                                            <span class="company-item-name">
                                                <platform-icon name="building-one" size="14" class="company-building-icon"></platform-icon>
                                                <span>${company.name}</span>
                                            </span>
                                            ${company.company_id === (this.user.active_company_id || this.user.company_id) ? html`
                                                <platform-icon name="check" size="14" class="check-icon"></platform-icon>
                                            ` : ''}
                                        </button>
                                    `)}
                                </div>
                            ` : ''}
                        ` : ''}
                        
                        <div class="menu-divider"></div>
                        
                        <button class="menu-item" @click=${this._openSettings}>
                            <platform-icon name="settings" size="18" class="menu-icon"></platform-icon>
                            <span>${this._pt('menu.settings')}</span>
                        </button>

                        <button class="menu-item" @click=${this._openCalendar}>
                            <platform-icon name="calendar" size="18" class="menu-icon"></platform-icon>
                            <span>${this._pt('menu.calendar')}</span>
                        </button>
                        
                        <button class="menu-item" @click=${this._openDocumentation}>
                            <platform-icon name="book-open" size="18" class="menu-icon"></platform-icon>
                            <span>${this._pt('menu.documentation')}</span>
                        </button>

                        <div class="lang-row" @click=${(e) => e.stopPropagation()}>
                            <platform-icon name="globe" size="18" class="menu-icon"></platform-icon>
                            <span class="lang-row-label">${this._pt('menu.language')}</span>
                            <div class="lang-switcher" role="group" aria-label=${this._pt('menu.language')}>
                                <button
                                    type="button"
                                    class=${classMap({ 'lang-option': true, active: uiLocale === 'en' })}
                                    @click=${(e) => this._setUiLocale('en', e)}
                                >en</button>
                                <span class="lang-separator" aria-hidden="true">|</span>
                                <button
                                    type="button"
                                    class=${classMap({ 'lang-option': true, active: uiLocale === 'ru' })}
                                    @click=${(e) => this._setUiLocale('ru', e)}
                                >ru</button>
                            </div>
                        </div>
                        
                        <button class="menu-item" @click=${this._toggleTheme}>
                            <platform-icon name="${this.theme?.isDark ? 'sun' : 'moon'}" size="18" class="menu-icon"></platform-icon>
                            <span>${this.theme?.isDark ? this._pt('menu.theme_light') : this._pt('menu.theme_dark')}</span>
                        </button>
                        
                        <div class="menu-divider"></div>
                        
                        <button class="menu-item danger" @click=${this._logout}>
                            <platform-icon name="logout" size="18" class="menu-icon"></platform-icon>
                            <span>${this._pt('menu.logout')}</span>
                        </button>
                    </div>
                ` : ''}
            </div>
        `;
    }

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: inline-block;
                position: relative;
            }
            
            :host([block]) {
                display: block;
                width: 100%;
            }

            :host-context(platform-sidebar[collapsed]) .user-info,
            :host-context(platform-sidebar[collapsed]) .user-menu-chevron {
                display: none;
            }

            .user-toolbar-wrap {
                display: flex;
                align-items: center;
                flex-shrink: 0;
            }

            .user-toolbar-wrap ::slotted(platform-notification-manager) {
                flex-shrink: 0;
            }

            .user-lang-badge {
                display: flex;
                align-items: center;
                justify-content: center;
                flex-shrink: 0;
                box-sizing: border-box;
                min-width: 30px;
                height: 22px;
                padding: 0 7px;
                font-size: 10px;
                font-weight: var(--font-semibold);
                line-height: 1;
                letter-spacing: 0.04em;
                color: var(--text-secondary);
                background: var(--glass-solid-medium);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                pointer-events: none;
            }

            :host-context(platform-sidebar[collapsed]) .user-toolbar-wrap {
                display: none;
            }

            :host-context(platform-sidebar[collapsed]) .user-lang-badge {
                position: absolute;
                top: -4px;
                right: -4px;
                min-width: 16px;
                height: 13px;
                padding: 0 3px;
                font-size: 8px;
                font-weight: var(--font-bold);
                margin: 0;
                color: var(--text-primary);
                background: var(--glass-solid-strong);
                border: 1px solid var(--glass-border-medium);
                border-radius: 4px;
                z-index: 1;
            }

            :host-context(platform-sidebar[collapsed]) .user-container {
                display: flex;
                justify-content: center;
                width: 100%;
                min-width: 0;
                box-sizing: border-box;
            }

            :host-context(platform-sidebar[collapsed]) .user-bar {
                justify-content: center;
                width: 100%;
                min-width: 0;
                padding: 0;
                background: transparent;
                border: none;
                box-shadow: none;
            }

            :host-context(platform-sidebar[collapsed]) .user-bar:hover {
                background: transparent;
                box-shadow: none;
            }

            :host-context(platform-sidebar[collapsed]) .user-button {
                position: relative;
                justify-content: center;
                align-items: center;
                width: 40px;
                height: 40px;
                min-width: 40px;
                min-height: 40px;
                flex-shrink: 0;
                gap: 0;
                padding: 0;
                background: transparent;
                border: none;
                border-radius: var(--radius-full);
                box-shadow: none;
                box-sizing: border-box;
                overflow: visible;
            }

            :host-context(platform-sidebar[collapsed]) .user-button:hover {
                background: var(--glass-solid-subtle);
                box-shadow: none;
            }

            :host-context(platform-sidebar[collapsed]) .user-menu {
                position: fixed;
                left: var(--user-menu-fixed-left, 0px);
                bottom: var(--user-menu-fixed-bottom, auto);
                right: auto;
                top: auto;
                width: var(--user-menu-fixed-width, min(240px, calc(100vw - 16px)));
                min-width: 200px;
                max-height: min(70vh, calc(var(--app-vh, 100vh) - 24px));
                overflow-x: hidden;
                overflow-y: auto;
                z-index: var(--z-modal, 5000);
            }

            .user-container {
                position: relative;
                width: 100%;
            }

            .user-bar {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                width: 100%;
                box-sizing: border-box;
                padding: var(--space-3);
                color: var(--text-secondary);
                background: var(--glass-solid-subtle);
                border-radius: var(--radius-lg);
                border: 1px solid var(--glass-border-subtle);
                box-shadow: 0 1px 4px rgba(0,0,0,0.1);
                transition: background var(--duration-fast), box-shadow var(--duration-fast);
            }

            .user-bar:hover {
                background: var(--glass-solid-medium);
                box-shadow: 0 2px 6px rgba(0,0,0,0.15);
            }

            .user-button {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                flex: 1;
                min-width: 0;
                padding: 0;
                margin: 0;
                border: none;
                background: transparent;
                cursor: pointer;
                font: inherit;
                color: inherit;
                text-align: left;
                box-shadow: none;
                box-sizing: border-box;
            }

            .user-menu-chevron {
                display: flex;
                align-items: center;
                justify-content: center;
                flex-shrink: 0;
                width: 28px;
                height: 28px;
                padding: 0;
                margin: 0;
                border: none;
                border-radius: var(--radius-md);
                background: transparent;
                cursor: pointer;
                color: inherit;
                transition: background var(--duration-fast);
            }

            .user-menu-chevron:hover {
                background: var(--glass-solid-medium);
            }

            .user-avatar {
                width: 40px;
                height: 40px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-full);
                background: var(--accent-gradient);
                color: white;
                font-weight: var(--font-bold);
                font-size: var(--text-sm);
                box-shadow: 0 4px 12px rgba(153, 166, 249, 0.25);
                flex-shrink: 0;
                overflow: hidden;
            }

            .user-avatar.has-image {
                padding: 0;
                background: var(--glass-solid-subtle);
            }

            .user-avatar .avatar-img {
                width: 100%;
                height: 100%;
                object-fit: cover;
                display: block;
            }

            .user-info {
                flex: 1;
                min-width: 0;
            }

            .user-name {
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: inherit;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }

            .user-email {
                font-size: var(--text-xs);
                font-weight: var(--font-normal);
                color: var(--text-tertiary);
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
                margin-top: 2px;
            }

            .chevron {
                color: var(--text-tertiary);
                transition: transform var(--duration-fast);
            }

            .chevron.open {
                transform: rotate(180deg);
            }

            .user-menu {
                position: absolute;
                bottom: calc(100% + 8px);
                left: 0;
                right: 0;
                background: var(--glass-solid-strong);
                backdrop-filter: blur(var(--glass-blur-strong));
                -webkit-backdrop-filter: blur(var(--glass-blur-strong));
                border: 1px solid var(--glass-border-medium);
                border-radius: var(--radius-xl);
                box-shadow: var(--glass-shadow-medium), 0 8px 32px rgba(0,0,0,0.2);
                z-index: 1000;
                animation: slideUp 0.2s ease;
                max-height: min(70vh, calc(var(--app-vh, 100vh) - 24px));
                overflow-x: hidden;
                overflow-y: auto;
            }

            @keyframes slideUp {
                from {
                    opacity: 0;
                    transform: translateY(10px);
                }
                to {
                    opacity: 1;
                    transform: translateY(0);
                }
            }

            .menu-item {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                width: 100%;
                padding: var(--space-2) var(--space-3);
                background: transparent;
                border: none;
                cursor: pointer;
                font-family: inherit;
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-secondary);
                transition: background var(--duration-fast), color var(--duration-fast);
                text-align: left;
            }

            .menu-item:hover {
                background: var(--hover-color);
                color: var(--text-primary);
            }

            .menu-item.danger {
                color: var(--error);
            }

            .menu-item.danger:hover {
                background: var(--error-bg);
                color: var(--error);
            }

            .menu-item.danger:hover .menu-icon {
                color: var(--error);
            }

            .menu-item.company-selector {
                justify-content: space-between;
            }

            .menu-item.apps-item {
                background: var(--accent-subtle);
                color: var(--accent);
                border: 1px solid var(--accent);
                border-radius: var(--radius-lg);
                margin: var(--space-2);
                width: calc(100% - var(--space-4));
            }

            .menu-item.apps-item .menu-icon,
            .menu-item.apps-item .expand-icon {
                color: var(--accent);
            }

            .menu-item.apps-item:hover {
                background: var(--accent-subtle);
                color: var(--accent);
            }

            .menu-item.apps-item:hover .menu-icon,
            .menu-item.apps-item:hover .expand-icon {
                color: var(--accent);
            }

            .apps-menu-logo {
                width: 18px;
                height: 18px;
                min-width: 18px;
                display: block;
                object-fit: contain;
            }

            .menu-icon {
                min-width: 20px;
                display: flex;
                align-items: center;
                justify-content: center;
                color: var(--text-tertiary);
            }

            .menu-item:hover .menu-icon {
                color: var(--text-secondary);
            }

            .company-name {
                font-size: var(--text-sm);
                color: inherit;
                font-weight: inherit;
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
            }

            .company-name-inline {
                flex: 1;
            }

            .company-building-icon {
                color: var(--text-tertiary);
                flex-shrink: 0;
                filter: grayscale(1) saturate(0) brightness(0.75);
                opacity: 0.9;
            }

            .expand-icon {
                color: var(--text-tertiary);
                transition: transform var(--duration-fast);
                display: flex;
                align-items: center;
            }

            .expand-icon.open {
                transform: rotate(90deg);
            }

            .company-list {
                background: var(--glass-solid-subtle);
                padding: var(--space-1) var(--space-2);
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
                margin: 0 var(--space-2) var(--space-2);
                border-left: 2px solid var(--glass-border-medium);
                padding-left: var(--space-3);
                border-radius: 0 var(--radius-md) var(--radius-md) 0;
            }

            .apps-grid {
                display: grid;
                grid-template-columns: minmax(0, 1fr);
                gap: var(--space-2);
                padding: 0 var(--space-2) var(--space-2);
            }

            .app-card {
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
                padding: var(--space-2);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-lg);
                background: var(--glass-solid-medium);
                text-align: left;
                cursor: pointer;
                font-family: inherit;
                font-weight: var(--font-medium);
                color: var(--text-secondary);
                transition: all var(--duration-fast);
            }

            .app-card:hover {
                border-color: var(--border-default);
                background: var(--glass-solid-strong);
                color: var(--text-primary);
                transform: translateY(-1px);
            }

            .app-card-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                width: 100%;
            }

            .app-logo {
                width: 20px;
                height: 20px;
                object-fit: contain;
                display: block;
            }

            .app-go-icon {
                color: var(--text-tertiary);
            }

            .app-card-name {
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: inherit;
            }

            .app-card-description {
                font-size: var(--text-xs);
                font-weight: var(--font-normal);
                color: var(--text-tertiary);
                line-height: 1.4;
            }

            .app-card:hover .app-card-description {
                color: var(--text-secondary);
            }

            @media (min-width: 380px) {
                .apps-grid {
                    grid-template-columns: repeat(2, minmax(0, 1fr));
                }
            }

            .company-item {
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: var(--space-2) var(--space-3);
                background: var(--surface-color);
                border: 1px solid transparent;
                border-radius: var(--radius-md);
                cursor: pointer;
                font-family: inherit;
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-secondary);
                transition: all var(--duration-fast);
            }

            .company-item-name {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                min-width: 0;
            }

            .company-item:hover {
                background: var(--hover-color);
                border-color: var(--border-color);
            }

            .company-item.active {
                background: var(--accent-subtle);
                border-color: var(--accent);
                color: var(--accent);
                font-weight: var(--font-medium);
            }

            .check-icon {
                color: var(--accent);
                display: flex;
                align-items: center;
            }

            .lang-row {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                width: 100%;
                box-sizing: border-box;
            }

            .lang-row-label {
                flex: 1;
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-secondary);
                min-width: 0;
            }

            .lang-switcher {
                display: inline-flex;
                align-items: center;
                gap: 4px;
                flex-shrink: 0;
            }

            .lang-option {
                padding: 4px 6px;
                background: transparent;
                border: none;
                cursor: pointer;
                font-size: var(--text-xs);
                font-family: inherit;
                font-weight: var(--font-medium);
                color: var(--text-tertiary);
                transition: color var(--duration-fast);
            }

            .lang-option.active {
                color: var(--text-secondary);
                font-weight: var(--font-medium);
            }

            .lang-option:hover {
                color: var(--accent);
            }

            .lang-separator {
                color: var(--text-tertiary);
                opacity: 0.5;
                user-select: none;
            }

            .menu-divider {
                height: 1px;
                background: var(--glass-border-subtle);
                margin: var(--space-1) 0;
            }
        `
    ];
}

customElements.define('platform-user', PlatformUser);

