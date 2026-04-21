/**
 * platform-user — кросс-сервисный компонент пользовательского меню.
 *
 * Канон: PlatformElement + Event Sourcing.
 *   - чтение: this.select(...) по auth/companies/theme/i18n
 *   - действия: this.dispatch(...), this.switchCompany(...), this.setTheme(...),
 *     this.setLocale(...), this.openModal(...)
 *   - смена компании: dispatch AUTH_COMPANY_SWITCH_REQUESTED → подписка на
 *     AUTH_COMPANY_SWITCHED → редирект на subdomain выбранной компании.
 *     Cross-tab синхронизация через localStorage 'platform:company-switch'.
 *   - меню: Apps grid (Flows, NetWorkle, RAG, Sync, Documents, Console),
 *     Профиль (открывает `platform.user_info` модалку с формой профиля),
 *     Компания (если их > 1), Календарь, Документация, язык (en|ru),
 *     переключатель темы, Выйти.
 *   - в свернутом sidebar (`platform-sidebar[collapsed]`) меню переходит
 *     в `position: fixed` через CSS-переменные `--user-menu-fixed-*`.
 *
 * i18n namespace: 'platform' (см. core/i18n/translations/{ru,en}/platform.json).
 */

import { html, css } from 'lit';
import { classMap } from 'lit/directives/class-map.js';
import { PlatformElement } from '../platform-element/index.js';
import { CoreEvents } from '../events/contract.js';
import { COMPANIES_EVENTS } from '../events/reducers/companies.js';
import { redirectToLogin } from '../utils/auth-redirect.js';
import { buildCompanySubdomainUrl } from '../utils/tenant-url.js';
import { buildScenarioDocumentationUrl } from '../utils/documentation-url.js';
import { resolveAvatarImageSrc } from '../utils/placeholder-avatar.js';
import './platform-icon.js';
import './platform-calendar-modal.js';

const COMPANY_SWITCH_STORAGE_KEY = 'platform:company-switch';
const SERVICE_LOGO_BASE = '/static/core/assets/service_logos';

const SERVICE_APPS = Object.freeze([
    { id: 'flows',     logo: `${SERVICE_LOGO_BASE}/agents_logo.svg`,    i18n: 'apps.flows' },
    { id: 'crm',       logo: `${SERVICE_LOGO_BASE}/crm_logo.svg`,       i18n: 'apps.crm' },
    { id: 'rag',       logo: `${SERVICE_LOGO_BASE}/rag_logo.svg`,       i18n: 'apps.rag' },
    { id: 'sync',      logo: `${SERVICE_LOGO_BASE}/sync_logo.svg`,      i18n: 'apps.sync' },
    { id: 'documents', logo: `${SERVICE_LOGO_BASE}/documents_logo.svg`, i18n: 'apps.documents' },
    { id: 'frontend',  logo: `${SERVICE_LOGO_BASE}/frontend_logo.svg`,  i18n: 'apps.frontend' },
]);

const SERVICE_DEV_PORTS = Object.freeze({
    flows: '8001',
    frontend: '8002',
    crm: '8003',
    rag: '8004',
    sync: '8005',
    documents: '8008',
});

export class PlatformUser extends PlatformElement {
    static i18nNamespace = 'platform';

    static properties = {
        block: { type: Boolean, reflect: true },
        documentationTag: { type: String, attribute: 'documentation-tag' },
        _menuOpen: { state: true },
        _companySelectorOpen: { state: true },
        _appsMenuOpen: { state: true },
        _avatarFallbackLevel: { state: true },
    };

    constructor() {
        super();
        this.block = false;
        this.documentationTag = null;
        this._menuOpen = false;
        this._companySelectorOpen = false;
        this._appsMenuOpen = false;
        this._avatarFallbackLevel = 0;
        this._menuAvatarSig = '';

        this._authSelect = this.select((s) => ({
            status: s.auth.status,
            user: s.auth.user,
            activeCompanyId: s.auth.activeCompanyId,
        }));
        this._companiesSelect = this.select((s) => s.companies.list);
        this._themeSelect = this.select((s) => s.theme.mode);
        this._localeSelect = this.select((s) => s.i18n.locale);

        this._companiesLoaded = false;
        this._pendingSwitchCompanyId = null;

        this._onDocumentClick = this._onDocumentClick.bind(this);
        this._onStorage = this._onStorage.bind(this);
        this._onResize = this._syncCollapsedMenuPosition.bind(this);
    }

    connectedCallback() {
        super.connectedCallback();
        document.addEventListener('click', this._onDocumentClick);
        window.addEventListener('storage', this._onStorage);
        this.useEvent(CoreEvents.AUTH_COMPANY_SWITCHED, (event) => this._onCompanySwitched(event));
    }

    disconnectedCallback() {
        document.removeEventListener('click', this._onDocumentClick);
        window.removeEventListener('storage', this._onStorage);
        this._detachCollapsedListeners();
        this._clearCollapsedMenuPosition();
        super.disconnectedCallback();
    }

    updated(changedProperties) {
        super.updated(changedProperties);

        const auth = this._authSelect.value;
        if (auth.status === 'authenticated' && auth.user && !this._companiesLoaded) {
            this._companiesLoaded = true;
            this.dispatch(COMPANIES_EVENTS.LOAD_REQUESTED, null);
        }

        const menuUser = auth.user;
        if (menuUser) {
            const raw = menuUser.raw;
            const uid = raw && typeof raw.user_id === 'string' ? raw.user_id : '';
            const url = this._avatarUrl(menuUser);
            const sig = `${uid}|${url || ''}`;
            if (this._menuAvatarSig !== sig) {
                this._menuAvatarSig = sig;
                this._avatarFallbackLevel = 0;
            }
        }

        if (changedProperties.has('_menuOpen')) {
            if (this._menuOpen) {
                this._attachCollapsedListeners();
                this.updateComplete.then(() => this._syncCollapsedMenuPosition());
            } else {
                this._detachCollapsedListeners();
                this._clearCollapsedMenuPosition();
            }
        }
    }

    _onDocumentClick(e) {
        if (!this._menuOpen) return;
        const path = e.composedPath();
        if (!path.includes(this)) {
            this._menuOpen = false;
            this._companySelectorOpen = false;
            this._appsMenuOpen = false;
        }
    }

    _toggleMenu(e) {
        e.stopPropagation();
        const next = !this._menuOpen;
        this._menuOpen = next;
        if (!next) {
            this._companySelectorOpen = false;
            this._appsMenuOpen = false;
        }
    }

    _toggleAppsMenu(e) {
        e.stopPropagation();
        this._appsMenuOpen = !this._appsMenuOpen;
    }

    _toggleCompanySelector(e) {
        e.stopPropagation();
        this._companySelectorOpen = !this._companySelectorOpen;
    }

    _switchCompany(companyId, e) {
        e.stopPropagation();
        const auth = this._authSelect.value;
        const currentCompanyId = this._currentCompanyId(auth);
        if (companyId === currentCompanyId) {
            this._companySelectorOpen = false;
            return;
        }
        this._pendingSwitchCompanyId = companyId;
        this.switchCompany(companyId);
    }

    _onCompanySwitched(event) {
        const companyId = event.payload && event.payload.company_id;
        if (!companyId) return;
        if (this._pendingSwitchCompanyId !== companyId) {
            return;
        }
        this._pendingSwitchCompanyId = null;
        const company = this._companiesSelect.value.find((c) => c.company_id === companyId);
        if (!company || !company.subdomain) {
            this.toast('company.subdomain_missing', { type: 'error' });
            return;
        }
        this.toast('company.switched', { type: 'success' });
        this._broadcastCompanySwitch(company);
        this._redirectToCompany(company);
    }

    _broadcastCompanySwitch(company) {
        const payload = `${Date.now()}|${company.company_id}|${company.subdomain}`;
        window.localStorage.setItem(COMPANY_SWITCH_STORAGE_KEY, payload);
    }

    _onStorage(event) {
        if (event.key !== COMPANY_SWITCH_STORAGE_KEY || !event.newValue) return;
        const parts = event.newValue.split('|');
        if (parts.length !== 3) return;
        const targetSubdomain = parts[2];
        if (!targetSubdomain) return;
        this._redirectToSubdomain(targetSubdomain);
    }

    _redirectToCompany(company) {
        this._redirectToSubdomain(company.subdomain);
    }

    _redirectToSubdomain(subdomain) {
        const targetPath = `${window.location.pathname}${window.location.search}${window.location.hash}`;
        const targetUrl = buildCompanySubdomainUrl(subdomain, targetPath);
        if (targetUrl === window.location.href) return;
        window.location.href = targetUrl;
    }

    _setLocale(locale, e) {
        e.stopPropagation();
        this.setLocale(locale);
    }

    _toggleTheme() {
        const next = this._themeSelect.value === 'dark' ? 'light' : 'dark';
        this.setTheme(next);
    }

    _openUserInfo() {
        this._menuOpen = false;
        const auth = this._authSelect.value;
        const user = auth.user;
        if (!user) return;
        const userId = (user.raw && user.raw.user_id) || user.id;
        if (!userId) return;
        this.openModal('platform.user_info', { userId });
    }

    _openCalendar() {
        this._menuOpen = false;
        this.openModal('platform.calendar', {});
    }

    _openDocumentation() {
        this._menuOpen = false;
        const tag = (typeof this.documentationTag === 'string' && this.documentationTag.trim())
            ? this.documentationTag.trim()
            : null;
        const url = buildScenarioDocumentationUrl({ tag });
        window.open(url, '_blank', 'noopener,noreferrer');
    }

    _openServiceApp(serviceId, event) {
        event.stopPropagation();
        const url = this._buildServiceUrl(serviceId);
        if (PlatformUser._isStandalonePwaMode()) {
            window.location.href = url;
            return;
        }
        window.open(url, '_blank', 'noopener,noreferrer');
    }

    _buildServiceUrl(serviceId) {
        const servicePath = `/${serviceId}`;
        const hostname = window.location.hostname;
        if (!PlatformUser._isLocalHost(hostname)) {
            return servicePath;
        }
        const targetPort = SERVICE_DEV_PORTS[serviceId];
        if (!targetPort) {
            throw new Error(`platform-user: unknown service id "${serviceId}"`);
        }
        if (window.location.port === targetPort) {
            return servicePath;
        }
        return `${window.location.protocol}//${hostname}:${targetPort}${servicePath}`;
    }

    static _isLocalHost(hostname) {
        return hostname === 'localhost'
            || hostname === '127.0.0.1'
            || hostname.endsWith('.localhost')
            || hostname.endsWith('.lvh.me');
    }

    _logout() {
        this._menuOpen = false;
        this.dispatch(CoreEvents.AUTH_LOGOUT_REQUESTED, null);
        redirectToLogin();
    }

    _currentCompanyId(auth) {
        if (auth.activeCompanyId) return auth.activeCompanyId;
        const raw = auth.user && auth.user.raw;
        if (raw) {
            if (raw.active_company_id) return raw.active_company_id;
            if (raw.company_id) return raw.company_id;
        }
        return auth.user && auth.user.company_id ? auth.user.company_id : null;
    }

    _companyName(companyId) {
        if (!companyId) return '';
        const company = this._companiesSelect.value.find((c) => c.company_id === companyId);
        return company ? company.name : '';
    }

    _displayName(user) {
        if (user.name) return user.name;
        const raw = user.raw;
        if (raw && raw.name) return raw.name;
        return this.t('menu.user_fallback');
    }

    _displayEmail(user) {
        const raw = user.raw;
        if (!raw) return '';
        if (Array.isArray(raw.emails) && raw.emails.length > 0) return raw.emails[0];
        return '';
    }

    _avatarUrl(user) {
        const raw = user.raw;
        if (!raw || typeof raw.avatar_url !== 'string') return null;
        const trimmed = raw.avatar_url.trim();
        return trimmed === '' ? null : trimmed;
    }

    _avatarLetter(user) {
        const sources = [user.name, user.raw && user.raw.name, this._displayEmail(user)];
        for (const src of sources) {
            if (typeof src === 'string' && src.trim().length > 0) {
                return src.trim().charAt(0).toUpperCase();
            }
        }
        return '?';
    }

    _onMenuAvatarError() {
        const auth = this._authSelect.value;
        const user = auth.user;
        if (!user) return;
        const url = this._avatarUrl(user);
        if (this._avatarFallbackLevel === 0 && url) {
            this._avatarFallbackLevel = 1;
        } else {
            this._avatarFallbackLevel = 2;
        }
    }

    _attachCollapsedListeners() {
        window.addEventListener('resize', this._onResize);
        window.addEventListener('scroll', this._onResize, true);
    }

    _detachCollapsedListeners() {
        window.removeEventListener('resize', this._onResize);
        window.removeEventListener('scroll', this._onResize, true);
    }

    _clearCollapsedMenuPosition() {
        this.style.removeProperty('--user-menu-fixed-left');
        this.style.removeProperty('--user-menu-fixed-bottom');
        this.style.removeProperty('--user-menu-fixed-width');
    }

    _syncCollapsedMenuPosition() {
        if (!this._menuOpen) return;
        const sidebar = this.closest('platform-sidebar');
        if (!sidebar || !sidebar.hasAttribute('collapsed')) {
            this._clearCollapsedMenuPosition();
            return;
        }
        const button = this.renderRoot.querySelector('.user-button');
        if (!button) return;
        const rect = button.getBoundingClientRect();
        const margin = 8;
        const maxW = Math.min(260, window.innerWidth - 2 * margin);
        let left = rect.left;
        if (left + maxW > window.innerWidth - margin) left = window.innerWidth - maxW - margin;
        if (left < margin) left = margin;
        const bottom = window.innerHeight - rect.top + margin;
        this.style.setProperty('--user-menu-fixed-left', `${left}px`);
        this.style.setProperty('--user-menu-fixed-bottom', `${bottom}px`);
        this.style.setProperty('--user-menu-fixed-width', `${maxW}px`);
    }

    static _isStandalonePwaMode() {
        const mq = window.matchMedia('(display-mode: standalone)');
        if (mq && mq.matches) return true;
        return window.navigator.standalone === true;
    }

    render() {
        const auth = this._authSelect.value;
        const user = auth.user;
        if (!user) return html``;

        const companies = this._companiesSelect.value;
        const currentCompanyId = this._currentCompanyId(auth);
        const currentCompanyName = this._companyName(currentCompanyId);
        const hasMultipleCompanies = companies.length > 1;
        const themeMode = this._themeSelect.value;
        const locale = this._localeSelect.value;
        const avatarUrl = this._avatarUrl(user);
        const raw = user.raw;
        if (!raw || typeof raw.user_id !== 'string' || raw.user_id === '') {
            throw new Error('platform-user: auth.user.raw.user_id required');
        }
        const avatarSeed = raw.user_id;
        const menuAvatarSrc = this._avatarFallbackLevel >= 2
            ? null
            : resolveAvatarImageSrc({
                avatarUrl: this._avatarFallbackLevel === 0 && avatarUrl ? avatarUrl : null,
                seed: avatarSeed,
            }).src;

        return html`
            <button
                class="user-button"
                @click=${this._toggleMenu}
                title=${this.t('menu.user_button_title')}
            >
                ${this._avatarFallbackLevel >= 2 ? html`
                    <span class="user-avatar">${this._avatarLetter(user)}</span>
                ` : html`
                    <span class="user-avatar has-image">
                        <img class="avatar-img" src=${menuAvatarSrc} alt="" @error=${this._onMenuAvatarError} />
                    </span>
                `}
                <span class="user-info">
                    <span class="user-name">${this._displayName(user)}</span>
                    <span class="user-email">${this._displayEmail(user)}</span>
                </span>
                <span class="toolbar-slot"><slot name="user-toolbar"></slot></span>
                <platform-icon
                    class=${classMap({ chevron: true, open: this._menuOpen })}
                    name="chevron-down"
                    size="14"
                ></platform-icon>
            </button>

            ${this._menuOpen ? html`
                <div class="user-menu" @click=${(e) => e.stopPropagation()}>
                    <button class="menu-item apps-item" @click=${this._toggleAppsMenu}>
                        <img class="apps-menu-logo" src="${SERVICE_LOGO_BASE}/agents_logo.svg" alt="" />
                        <span class="menu-item-label">${this.t('menu.apps')}</span>
                        <platform-icon
                            class=${classMap({ 'expand-icon': true, open: this._appsMenuOpen })}
                            name="chevron-right"
                            size="12"
                        ></platform-icon>
                    </button>

                    ${this._appsMenuOpen ? html`
                        <div class="apps-grid">
                            ${SERVICE_APPS.map((service) => html`
                                <button class="app-card" @click=${(e) => this._openServiceApp(service.id, e)}>
                                    <span class="app-card-header">
                                        <img class="app-logo" src=${service.logo} alt="" />
                                        <platform-icon class="app-go-icon" name="arrow-right" size="16"></platform-icon>
                                    </span>
                                    <span class="app-card-name">${this.t(`${service.i18n}.name`)}</span>
                                    <span class="app-card-description">${this.t(`${service.i18n}.description`)}</span>
                                </button>
                            `)}
                        </div>
                    ` : ''}

                    <div class="menu-divider"></div>

                    <button class="menu-item" @click=${this._openUserInfo}>
                        <platform-icon class="menu-icon" name="user" size="18"></platform-icon>
                        <span class="menu-item-label">${this.t('menu.profile')}</span>
                    </button>

                    ${hasMultipleCompanies ? html`
                        <button class="menu-item company-selector" @click=${this._toggleCompanySelector}>
                            <platform-icon class="menu-icon" name="building-one" size="18"></platform-icon>
                            <span class="menu-item-label">${currentCompanyName}</span>
                            <platform-icon
                                class=${classMap({ 'expand-icon': true, open: this._companySelectorOpen })}
                                name="chevron-right"
                                size="12"
                            ></platform-icon>
                        </button>
                        ${this._companySelectorOpen ? html`
                            <div class="company-list">
                                ${companies.map((company) => html`
                                    <button
                                        class=${classMap({ 'company-item': true, active: company.company_id === currentCompanyId })}
                                        @click=${(e) => this._switchCompany(company.company_id, e)}
                                    >
                                        <span class="company-item-name">
                                            <platform-icon name="building-one" size="14"></platform-icon>
                                            <span>${company.name}</span>
                                        </span>
                                        ${company.company_id === currentCompanyId ? html`
                                            <platform-icon class="check-icon" name="check" size="14"></platform-icon>
                                        ` : ''}
                                    </button>
                                `)}
                            </div>
                        ` : ''}
                    ` : ''}

                    <div class="menu-divider"></div>

                    <button class="menu-item" @click=${this._openCalendar}>
                        <platform-icon class="menu-icon" name="calendar" size="18"></platform-icon>
                        <span class="menu-item-label">${this.t('menu.calendar')}</span>
                    </button>

                    <button class="menu-item" @click=${this._openDocumentation}>
                        <platform-icon class="menu-icon" name="book-open" size="18"></platform-icon>
                        <span class="menu-item-label">${this.t('menu.documentation')}</span>
                    </button>

                    <div class="lang-row">
                        <platform-icon class="menu-icon" name="globe" size="18"></platform-icon>
                        <span class="menu-item-label">${this.t('menu.language')}</span>
                        <span class="lang-switcher">
                            <button
                                class=${classMap({ 'lang-option': true, active: locale === 'en' })}
                                @click=${(e) => this._setLocale('en', e)}
                            >en</button>
                            <span class="lang-separator">|</span>
                            <button
                                class=${classMap({ 'lang-option': true, active: locale === 'ru' })}
                                @click=${(e) => this._setLocale('ru', e)}
                            >ru</button>
                        </span>
                    </div>

                    <button class="menu-item" @click=${this._toggleTheme}>
                        <platform-icon class="menu-icon" name=${themeMode === 'dark' ? 'sun' : 'moon'} size="18"></platform-icon>
                        <span class="menu-item-label">
                            ${themeMode === 'dark' ? this.t('menu.theme_light') : this.t('menu.theme_dark')}
                        </span>
                    </button>

                    <div class="menu-divider"></div>

                    <button class="menu-item danger" @click=${this._logout}>
                        <platform-icon class="menu-icon" name="logout" size="18"></platform-icon>
                        <span class="menu-item-label">${this.t('menu.logout')}</span>
                    </button>
                </div>
            ` : ''}
        `;
    }

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: inline-block; position: relative; }
            :host([block]) { display: block; width: 100%; }

            :host-context(platform-sidebar[collapsed]) .user-info,
            :host-context(platform-sidebar[collapsed]) .chevron,
            :host-context(platform-sidebar[collapsed]) .toolbar-slot {
                display: none;
            }

            :host-context(platform-sidebar[collapsed]) .user-button {
                justify-content: center;
                width: 40px;
                height: 40px;
                min-width: 40px;
                min-height: 40px;
                gap: 0;
                padding: 0;
                background: transparent;
                border: none;
                border-radius: var(--radius-full);
                box-shadow: none;
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
                width: var(--user-menu-fixed-width, min(260px, calc(100vw - 16px)));
                z-index: var(--z-modal, 5000);
            }

            .user-button {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                padding: var(--space-3);
                width: 100%;
                box-sizing: border-box;
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                box-shadow: 0 1px 4px rgba(0, 0, 0, 0.1);
                cursor: pointer;
                color: var(--text-primary);
                transition: all var(--duration-fast);
                text-align: left;
            }
            .user-button:hover {
                background: var(--glass-solid-medium);
                box-shadow: 0 2px 6px rgba(0, 0, 0, 0.15);
            }

            .user-avatar {
                width: 40px;
                height: 40px;
                flex-shrink: 0;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-full);
                background: var(--accent-gradient);
                color: white;
                font-weight: var(--font-bold);
                font-size: var(--text-sm);
                box-shadow: 0 4px 12px rgba(16, 185, 129, 0.25);
                overflow: hidden;
            }
            .user-avatar.has-image {
                padding: 0;
                background: var(--glass-solid-subtle);
                box-shadow: none;
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
                display: flex;
                flex-direction: column;
            }
            .user-name {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }
            .user-email {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
                margin-top: 2px;
            }

            .toolbar-slot { display: inline-flex; align-items: center; }

            .chevron {
                color: var(--text-tertiary);
                transition: transform var(--duration-fast);
            }
            .chevron.open { transform: rotate(180deg); }

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
                box-shadow: var(--glass-shadow-medium), 0 8px 32px rgba(0, 0, 0, 0.2);
                z-index: var(--z-dropdown, 1000);
                padding: var(--space-1) 0;
                max-height: min(70vh, calc(var(--app-vh, 100vh) - 24px));
                overflow-y: auto;
                animation: pmu-slide-up 0.18s ease;
            }

            @keyframes pmu-slide-up {
                from { opacity: 0; transform: translateY(8px); }
                to   { opacity: 1; transform: translateY(0); }
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
                font-size: var(--text-sm);
                color: var(--text-primary);
                text-align: left;
            }
            .menu-item:hover { background: var(--glass-solid-medium); }
            .menu-item.danger { color: var(--error); }
            .menu-item.danger:hover { background: var(--error-bg); }
            .menu-item.company-selector { justify-content: space-between; }

            .menu-item.apps-item {
                background: var(--accent-subtle);
                color: var(--accent);
                border: 1px solid var(--accent);
                border-radius: var(--radius-lg);
                margin: var(--space-2);
                width: calc(100% - var(--space-4));
                padding: var(--space-2) var(--space-3);
            }
            .menu-item.apps-item .menu-item-label { color: var(--accent); }
            .menu-item.apps-item .expand-icon { color: var(--accent); }
            .menu-item.apps-item:hover { background: var(--accent-subtle); }

            .menu-icon {
                min-width: 20px;
                color: var(--text-secondary);
                display: inline-flex;
                align-items: center;
                justify-content: center;
            }

            .menu-item-label { flex: 1; min-width: 0; }
            .expand-icon {
                color: var(--text-tertiary);
                transition: transform var(--duration-fast);
            }
            .expand-icon.open { transform: rotate(90deg); }

            .menu-divider {
                height: 1px;
                background: var(--glass-border-subtle);
                margin: var(--space-1) 0;
            }

            .apps-menu-logo {
                width: 18px;
                height: 18px;
                min-width: 18px;
                object-fit: contain;
                display: block;
            }

            .apps-grid {
                display: grid;
                grid-template-columns: minmax(0, 1fr);
                gap: var(--space-2);
                padding: 0 var(--space-2) var(--space-2);
            }
            @media (min-width: 380px) {
                .apps-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
            }

            .app-card {
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
                padding: var(--space-2);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-lg);
                background: var(--glass-solid-medium);
                cursor: pointer;
                color: var(--text-primary);
                text-align: left;
                transition: all var(--duration-fast);
            }
            .app-card:hover {
                border-color: var(--border-default);
                background: var(--glass-solid-strong);
                transform: translateY(-1px);
            }
            .app-card-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
            }
            .app-logo { width: 20px; height: 20px; object-fit: contain; }
            .app-go-icon { color: var(--text-tertiary); }
            .app-card-name {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }
            .app-card-description {
                font-size: var(--text-xs);
                color: var(--text-secondary);
                line-height: 1.4;
            }

            .company-list {
                background: var(--glass-solid-subtle);
                margin: 0 var(--space-2) var(--space-2);
                padding: var(--space-1) var(--space-2) var(--space-1) var(--space-3);
                border-left: 2px solid var(--glass-border-medium);
                border-radius: 0 var(--radius-md) var(--radius-md) 0;
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
            }
            .company-item {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: var(--space-2) var(--space-3);
                background: transparent;
                border: 1px solid transparent;
                border-radius: var(--radius-md);
                cursor: pointer;
                font-size: var(--text-sm);
                color: var(--text-primary);
            }
            .company-item:hover {
                background: var(--glass-solid-medium);
                border-color: var(--glass-border-subtle);
            }
            .company-item.active {
                background: var(--accent-subtle);
                border-color: var(--accent);
                color: var(--accent);
                font-weight: var(--font-semibold);
            }
            .company-item-name {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                min-width: 0;
            }
            .check-icon { color: var(--accent); }

            .lang-row {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                padding: var(--space-2) var(--space-3);
                font-size: var(--text-sm);
                color: var(--text-primary);
            }
            .lang-switcher { display: inline-flex; align-items: center; gap: 2px; }
            .lang-option {
                padding: 2px 8px;
                background: transparent;
                border: none;
                color: var(--text-tertiary);
                cursor: pointer;
                border-radius: var(--radius-sm);
                font-size: var(--text-sm);
            }
            .lang-option.active { color: var(--accent); font-weight: var(--font-semibold); }
            .lang-separator { color: var(--text-tertiary); }
        `,
    ];
}

customElements.define('platform-user', PlatformUser);
