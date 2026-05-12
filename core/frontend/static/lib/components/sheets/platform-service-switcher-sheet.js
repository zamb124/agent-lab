/**
 * platform-service-switcher-sheet — единый универсальный bottom-sheet (mobile shell 2026).
 *
 * Открывается с правой вкладки 'Профиль' любого сервисного <platform-bottom-nav>.
 * Содержит:
 *   - блок контекста: сверху текущая компания и раскрывающийся список смены (+ создание, если owner),
 *     ниже строка аккаунта (имя/email как в platform-user)
 *   - сетка переключения сервисов (platform-services-launcher)
 *   - быстрые ссылки на консольные страницы (Settings / Team / Billing / API keys)
 *   - профиль: `platform.user_info` с `userId` текущего пользователя (как `platform-user`)
 *   - тёмная/светлая тема (this.setTheme)
 *   - уведомления (platform-notification-manager)
 *   - logout (AUTH_LOGOUT_REQUESTED)
 *
 * kind: 'platform.service_switcher'
 */

import { html, css } from 'lit';
import { classMap } from 'lit/directives/class-map.js';
import { PlatformBottomSheet } from '../layout/platform-bottom-sheet.js';
import { registerBottomSheetKind } from '../../utils/bottom-sheet-registry.js';
import { CoreEvents } from '../../events/contract.js';
import { COMPANIES_EVENTS } from '../../events/reducers/companies.js';
import { buildServiceEntryUrl, isStandalonePwaMode } from '../../utils/build-service-entry-url.js';
import { buildScenarioDocumentationUrl } from '../../utils/documentation-url.js';
import '../platform-icon.js';
import '../platform-services-launcher.js';
import '../platform-notification-manager.js';
import '../platform-calendar-modal.js';

export class PlatformServiceSwitcherSheet extends PlatformBottomSheet {
    static bottomSheetKind = 'platform.service_switcher';
    static i18nNamespace = 'platform';

    static properties = {
        ...PlatformBottomSheet.properties,
        _companyPickerOpen: { state: true },
    };

    static styles = [
        PlatformBottomSheet.styles,
        css`
            :host([open]) {
                --service-switcher-section-gap: var(--space-5);
            }

            .switcher-body {
                display: flex;
                flex-direction: column;
                gap: var(--service-switcher-section-gap);
            }

            .user-card {
                display: flex;
                flex-direction: column;
                align-items: stretch;
                gap: 0;
                padding: var(--space-3);
                border-radius: var(--radius-xl);
                background: var(--glass-tint-medium);
                border: 1px solid var(--glass-border-subtle);
            }

            .user-card-info {
                display: flex;
                flex-direction: column;
                min-width: 0;
                width: 100%;
            }

            .user-card-name {
                font-size: var(--text-base);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }

            .user-card-meta {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }

            .user-card-meta--muted {
                font-style: italic;
            }

            .user-card-company-row {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                min-width: 0;
            }

            .user-card-company-row > :first-child {
                flex: 1 1 auto;
                min-width: 0;
                margin: 0;
            }

            .user-card-account-line {
                margin-top: var(--space-1);
            }

            .company-picker-toggle {
                flex-shrink: 0;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 36px;
                height: 36px;
                margin: 0;
                padding: 0;
                border: none;
                border-radius: var(--radius-lg);
                background: transparent;
                color: var(--text-secondary);
                cursor: pointer;
                transition: background var(--duration-fast), color var(--duration-fast);
            }

            .company-picker-toggle:hover {
                background: var(--glass-hover);
                color: var(--text-primary);
            }

            .picker-chevron {
                transition: transform var(--duration-fast) var(--easing-default);
            }

            .picker-chevron.open {
                transform: rotate(180deg);
            }

            .company-picker-list {
                margin-top: var(--space-3);
                padding-top: var(--space-3);
                border-top: 1px solid var(--glass-border-subtle);
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
            }

            .company-picker-item {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
                width: 100%;
                padding: var(--space-2) var(--space-3);
                border: 1px solid transparent;
                border-radius: var(--radius-lg);
                background: var(--glass-tint-subtle);
                color: var(--text-primary);
                font: inherit;
                font-size: var(--text-sm);
                text-align: left;
                cursor: pointer;
                transition: background var(--duration-fast), border-color var(--duration-fast);
                box-sizing: border-box;
            }

            .company-picker-item:hover {
                background: var(--glass-tint-medium);
            }

            .company-picker-item.active {
                border-color: var(--accent);
                background: var(--accent-subtle);
            }

            .company-picker-item-label {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                min-width: 0;
            }

            .company-picker-item-label span {
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            .company-picker-item--create {
                border-style: dashed;
                border-color: var(--glass-border-medium);
            }

            .section-title {
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                color: var(--text-tertiary);
                text-transform: uppercase;
                letter-spacing: 0.08em;
                margin: 0 0 var(--space-2);
            }

            .links {
                display: grid;
                grid-template-columns: repeat(2, minmax(0, 1fr));
                gap: var(--space-2);
            }

            .link-btn {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-3);
                background: var(--glass-tint-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                color: var(--text-primary);
                font: inherit;
                font-size: var(--text-sm);
                text-align: left;
                cursor: pointer;
                transition: all var(--duration-fast) var(--easing-default);
            }

            .link-btn:hover {
                background: var(--glass-tint-medium);
                border-color: var(--glass-border-medium);
            }

            .link-btn:active {
                transform: scale(0.98);
            }

            .theme-row {
                display: flex;
                gap: var(--space-2);
            }

            .theme-pill {
                flex: 1;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: var(--space-2);
                padding: var(--space-3);
                background: var(--glass-tint-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                color: var(--text-primary);
                font: inherit;
                font-size: var(--text-sm);
                cursor: pointer;
                transition: all var(--duration-fast) var(--easing-default);
            }

            .theme-pill.active {
                background: var(--accent-subtle);
                border-color: var(--accent);
                color: var(--accent);
                font-weight: var(--font-semibold);
            }

            .logout-row {
                margin-top: var(--space-2);
            }

            .logout-btn {
                width: 100%;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: var(--space-2);
                padding: var(--space-3);
                background: var(--error-bg);
                border: 1px solid var(--error-border);
                border-radius: var(--radius-lg);
                color: var(--error);
                font: inherit;
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                cursor: pointer;
                transition: all var(--duration-fast) var(--easing-default);
            }

            .logout-btn:hover {
                background: color-mix(in srgb, var(--error-bg) 80%, transparent);
            }

            .notifications-host {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
                padding: var(--space-3);
                background: var(--glass-tint-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
            }

            .notifications-label {
                font-size: var(--text-sm);
                color: var(--text-primary);
                font-weight: var(--font-medium);
            }
        `,
    ];

    constructor() {
        super();
        this.snap = 'full';
        this._companyPickerOpen = false;
        this._companiesBootstrapDispatched = false;
        this._authSelect = this.select((s) => ({
            status: s.auth.status,
            user: s.auth.user,
            activeCompanyId: s.auth.activeCompanyId,
        }));
        this._companiesSelect = this.select((s) => s.companies.list);
        this._themeSelect = this.select((s) => s.theme.mode);
    }

    connectedCallback() {
        super.connectedCallback();
        this.heading = this.t('service_switcher.heading');
    }

    updated(changed) {
        super.updated(changed);
        if (!changed.has('open')) {
            return;
        }
        if (!this.open) {
            this._companyPickerOpen = false;
            return;
        }
        const auth = this._authSelect.value || {};
        if (auth.status === 'authenticated' && auth.user && !this._companiesBootstrapDispatched) {
            this._companiesBootstrapDispatched = true;
            this.dispatch(COMPANIES_EVENTS.LOAD_REQUESTED, null);
        }
    }

    _onServiceLaunch(e) {
        e.stopPropagation();
        const d = e.detail;
        if (!d || typeof d.serviceId !== 'string' || d.serviceId.length === 0) {
            throw new Error('platform-service-switcher-sheet: service-launch without serviceId');
        }
        const url = buildServiceEntryUrl(d.serviceId);
        this._requestClose();
        if (isStandalonePwaMode()) {
            window.location.href = url;
        } else {
            window.open(url, '_blank', 'noopener,noreferrer');
        }
    }

    _onConsoleLink(routeKey) {
        this._requestClose();
        // Консольные маршруты живут в сервисе frontend. Если мы уже там — внутренняя
        // навигация. Иначе — переход на frontend сервис с deep-link path.
        const frontendUrl = buildServiceEntryUrl('frontend');
        const path = this._routePathFor(routeKey);
        if (typeof location !== 'undefined' && location.pathname.startsWith('/dashboard') === false
            && !frontendUrl.startsWith('/')) {
            window.location.href = `${frontendUrl.replace(/\/dashboard$/, '')}${path}`;
            return;
        }
        // На самой консоли — обычная маршрутизация.
        this.dispatch(CoreEvents.ROUTER_NAVIGATE_REQUESTED, { routeKey, params: {} });
    }

    _routePathFor(routeKey) {
        // Стабильные публичные маршруты консоли (frontend-app.js FRONTEND_ROUTES).
        switch (routeKey) {
            case 'dashboard': return '/dashboard';
            case 'team': return '/dashboard/team';
            case 'billing': return '/dashboard/billing';
            case 'api-keys': return '/dashboard/api-keys';
            case 'settings': return '/dashboard/settings';
            default: return '/dashboard';
        }
    }

    _onThemeSelect(mode) {
        this.setTheme(mode);
    }

    _openCalendar() {
        this._requestClose();
        this.openModal('platform.calendar', {});
    }

    _openDocumentation() {
        this._requestClose();
        const url = buildScenarioDocumentationUrl({ tag: null });
        window.open(url, '_blank', 'noopener,noreferrer');
    }

    _openUserProfile() {
        this._requestClose();
        const auth = this._authSelect.value || {};
        const user = auth.user;
        if (!user) return;
        const rawId =
            user.raw && typeof user.raw.user_id === 'string'
                ? user.raw.user_id.trim()
                : '';
        const fallbackId = typeof user.id === 'string' ? user.id.trim() : '';
        const userId = rawId !== '' ? rawId : fallbackId;
        if (typeof userId !== 'string' || userId === '') return;
        this.openModal('platform.user_info', { userId });
    }

    _onLogout() {
        this._requestClose();
        this.dispatch(CoreEvents.AUTH_LOGOUT_REQUESTED, null);
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

    _companyRecordById(companyId) {
        if (!companyId) return undefined;
        const companies = this._companiesSelect.value || [];
        return companies.find((c) => c && c.company_id === companyId);
    }

    _companyNameForId(companyId) {
        const company = this._companyRecordById(companyId);
        return company && typeof company.name === 'string' ? company.name : '';
    }

    _isOwnerOfCompany(companyRecord) {
        if (!companyRecord || !Array.isArray(companyRecord.role)) {
            return false;
        }
        return companyRecord.role.includes('owner');
    }

    _resolveSwitchCardTitle(user) {
        if (!user) return '';
        if (typeof user.name === 'string' && user.name.trim() !== '') return user.name.trim();
        const raw = user.raw;
        if (raw && typeof raw.name === 'string' && raw.name.trim() !== '') return raw.name.trim();
        if (raw && Array.isArray(raw.emails) && raw.emails.length > 0) {
            const em = raw.emails[0];
            if (typeof em === 'string' && em.trim() !== '') return em.trim();
        }
        if (raw) {
            const first = typeof raw.first_name === 'string' ? raw.first_name.trim() : '';
            const last = typeof raw.last_name === 'string' ? raw.last_name.trim() : '';
            const duo = `${first} ${last}`.trim();
            if (duo !== '') return duo;
        }
        return this.t('menu.user_fallback');
    }

    _resolveCompanyName() {
        const auth = this._authSelect.value || {};
        const currentId = this._currentCompanyId(auth);
        const name = this._companyNameForId(currentId);
        return typeof name === 'string' ? name : '';
    }

    _toggleCompanyPicker(e) {
        e.stopPropagation();
        this._companyPickerOpen = !this._companyPickerOpen;
    }

    _switchCompanyFromPicker(companyId, e) {
        e.stopPropagation();
        const auth = this._authSelect.value || {};
        const currentId = this._currentCompanyId(auth);
        if (companyId === currentId) {
            this._companyPickerOpen = false;
            return;
        }
        this.switchCompany(companyId);
    }

    _openCreateCompany(e) {
        e.stopPropagation();
        this._companyPickerOpen = false;
        this._requestClose();
        this.openModal('platform.company_create', null);
    }

    renderBody() {
        const auth = this._authSelect.value || {};
        const user = auth.user || null;
        const themeMode = this._themeSelect.value || 'dark';
        const companies = this._companiesSelect.value || [];
        const cardTitle = this._resolveSwitchCardTitle(user);
        const companyName = this._resolveCompanyName();
        const currentCompanyId = this._currentCompanyId(auth);
        const hasCompaniesMenu = companies.length >= 1;
        const activeCompanyRecord = currentCompanyId
            ? this._companyRecordById(currentCompanyId)
            : undefined;
        const canCreateCompany = this._isOwnerOfCompany(activeCompanyRecord);
        return html`
            <div class="switcher-body">
                <div class="user-card">
                    <div class="user-card-info">
                        <div class="user-card-company-row">
                            ${companyName
                                ? html`<span class="user-card-name">${companyName}</span>`
                                : html`<span class="user-card-meta user-card-meta--muted">${this.t('service_switcher.no_company')}</span>`
                            }
                            ${hasCompaniesMenu
                                ? html`
                                    <button
                                        type="button"
                                        class="company-picker-toggle"
                                        aria-expanded=${this._companyPickerOpen ? 'true' : 'false'}
                                        aria-label=${this.t('service_switcher.company_list_aria')}
                                        title=${this.t('service_switcher.company_list_aria')}
                                        @click=${this._toggleCompanyPicker}
                                    >
                                        <platform-icon
                                            class=${classMap({ 'picker-chevron': true, open: this._companyPickerOpen })}
                                            name="chevron-down"
                                            size="18"
                                        ></platform-icon>
                                    </button>
                                `
                                : ''}
                        </div>
                        ${cardTitle
                            ? html`
                                <div class="user-card-account-line">
                                    <span class="user-card-meta">${cardTitle}</span>
                                </div>
                            `
                            : ''}
                    </div>
                    ${hasCompaniesMenu && this._companyPickerOpen
                        ? html`
                            <div class="company-picker-list" role="list">
                                ${companies.map((company) => html`
                                    <button
                                        type="button"
                                        class=${classMap({
                                            'company-picker-item': true,
                                            active: company.company_id === currentCompanyId,
                                        })}
                                        role="listitem"
                                        @click=${(e) => this._switchCompanyFromPicker(company.company_id, e)}
                                    >
                                        <span class="company-picker-item-label">
                                            <platform-icon name="building-one" size="14"></platform-icon>
                                            <span>${company.name}</span>
                                        </span>
                                        ${company.company_id === currentCompanyId
                                            ? html`<platform-icon class="check-icon" name="check" size="14"></platform-icon>`
                                            : ''}
                                    </button>
                                `)}
                                ${canCreateCompany
                                    ? html`
                                        <button
                                            type="button"
                                            class="company-picker-item company-picker-item--create"
                                            @click=${this._openCreateCompany}
                                        >
                                            <span class="company-picker-item-label">
                                                <platform-icon name="plus" size="14"></platform-icon>
                                                <span>${this.t('menu.create_company')}</span>
                                            </span>
                                        </button>
                                    `
                                    : ''}
                            </div>
                        `
                        : ''}
                </div>

                <section>
                    <h3 class="section-title">${this.t('service_switcher.services_title')}</h3>
                    <platform-services-launcher
                        layout="menu"
                        navigate-mode="event-only"
                        @service-launch=${(e) => this._onServiceLaunch(e)}
                    ></platform-services-launcher>
                </section>

                <section>
                    <h3 class="section-title">${this.t('service_switcher.quick_title')}</h3>
                    <div class="links">
                        <button type="button" class="link-btn" @click=${() => this._openUserProfile()}>
                            <platform-icon name="user" size="20"></platform-icon>
                            <span>${this.t('service_switcher.quick_profile')}</span>
                        </button>
                        <button type="button" class="link-btn" @click=${() => this._openCalendar()}>
                            <platform-icon name="calendar" size="20"></platform-icon>
                            <span>${this.t('service_switcher.quick_calendar')}</span>
                        </button>
                        <button type="button" class="link-btn" @click=${() => this._openDocumentation()}>
                            <platform-icon name="book-open" size="20"></platform-icon>
                            <span>${this.t('service_switcher.quick_documentation')}</span>
                        </button>
                    </div>
                </section>

                <section>
                    <h3 class="section-title">${this.t('service_switcher.settings_title')}</h3>
                    <div class="links">
                        <button type="button" class="link-btn" @click=${() => this._onConsoleLink('dashboard')}>
                            <platform-icon name="building-one" size="20"></platform-icon>
                            <span>${this.t('service_switcher.settings_console')}</span>
                        </button>
                        <button type="button" class="link-btn" @click=${() => this._onConsoleLink('team')}>
                            <platform-icon name="users" size="20"></platform-icon>
                            <span>${this.t('service_switcher.settings_team')}</span>
                        </button>
                        <button type="button" class="link-btn" @click=${() => this._onConsoleLink('billing')}>
                            <platform-icon name="chart" size="20"></platform-icon>
                            <span>${this.t('service_switcher.settings_billing')}</span>
                        </button>
                        <button type="button" class="link-btn" @click=${() => this._onConsoleLink('api-keys')}>
                            <platform-icon name="key" size="20"></platform-icon>
                            <span>${this.t('service_switcher.settings_api_keys')}</span>
                        </button>
                    </div>
                </section>

                <section>
                    <h3 class="section-title">${this.t('service_switcher.notifications_title')}</h3>
                    <div class="notifications-host">
                        <span class="notifications-label">${this.t('notifications.title')}</span>
                        <platform-notification-manager></platform-notification-manager>
                    </div>
                </section>

                <section>
                    <h3 class="section-title">${this.t('service_switcher.preferences_title')}</h3>
                    <div class="theme-row">
                        <button
                            type="button"
                            class="theme-pill ${themeMode === 'light' ? 'active' : ''}"
                            @click=${() => this._onThemeSelect('light')}
                        >
                            <platform-icon name="sun" size="18"></platform-icon>
                            <span>${this.t('service_switcher.theme_light')}</span>
                        </button>
                        <button
                            type="button"
                            class="theme-pill ${themeMode === 'dark' ? 'active' : ''}"
                            @click=${() => this._onThemeSelect('dark')}
                        >
                            <platform-icon name="moon" size="18"></platform-icon>
                            <span>${this.t('service_switcher.theme_dark')}</span>
                        </button>
                    </div>
                </section>

                <div class="logout-row">
                    <button type="button" class="logout-btn" @click=${() => this._onLogout()}>
                        <platform-icon name="logout" size="18"></platform-icon>
                        <span>${this.t('service_switcher.logout')}</span>
                    </button>
                </div>
            </div>
        `;
    }
}

customElements.define('platform-service-switcher-sheet', PlatformServiceSwitcherSheet);
registerBottomSheetKind(
    PlatformServiceSwitcherSheet.bottomSheetKind,
    'platform-service-switcher-sheet',
);
