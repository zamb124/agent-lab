/**
 * platform-user — кросс-сервисный компонент пользовательского меню.
 *
 * Канон: PlatformElement + Event Sourcing.
 *   - чтение: this.select(...) по auth/companies/theme/i18n
 *   - действия: this.dispatch(...), this.switchCompany(...), this.setTheme(...),
 *     this.setLocale(...), this.openModal(...)
 *   - смена компании: dispatch AUTH_COMPANY_SWITCH_REQUESTED → AUTH_COMPANY_SWITCHED
 *     (auth-company-navigation.effect: редирект на subdomain).
 *     Между вкладками: storage-ключ COMPANY_SWITCH_STORAGE_KEY + storage listener.
 *   - меню: пункт Apps (модалка `platform.services`), затем Профиль
 *     (открывает `platform.user_info` модалку с формой профиля),
 *     Компания (если есть хотя бы одна в списке; «Создать компанию» — только
 *     при роли owner текущей компании), Календарь, Документация, язык (en|ru),
 *     переключатель темы, Выйти.
 *   - меню живёт в `platform-popover` (top layer), поэтому одинаково работает
 *     в развёрнутом и свёрнутом sidebar и не обрезается его `overflow`.
 *
 * i18n namespace: 'platform' (см. core/i18n/translations/{ru,en}/platform.json).
 */

import { html, css } from 'lit';
import type { CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult } from 'lit';
import { classMap } from 'lit/directives/class-map.js';
import { PlatformElement } from '../platform-element/index.js';
import { CoreEvents } from '../events/contract.js';
import { COMPANIES_EVENTS } from '../events/reducers/companies.js';
import { buildCompanySubdomainUrl } from '../utils/company-url.js';
import { COMPANY_SWITCH_STORAGE_KEY } from '../events/effects/auth-company-navigation.effect.js';
import { buildScenarioDocumentationUrl } from '../utils/documentation-url.js';
import { resolveAvatarImageSrc } from '../utils/placeholder-avatar.js';
import { isPlainRecord } from '../events/payload.js';
import { PlatformPopover } from './platform-popover.js';
import type { SelectController } from '../events/select-controller.js';
import './platform-icon.js';
import './platform-calendar-modal.js';
import './platform-mail-modal.js';

function menuUserId(raw: unknown): string {
    if (raw === undefined) return '';
    if (!isPlainRecord(raw)) {
        throw new Error('platform-user: auth user raw must be an object');
    }
    const userId = raw.user_id;
    return typeof userId === 'string' ? userId : '';
}

function hasOwnerRole(role: unknown): boolean {
    if (!Array.isArray(role)) return false;
    for (const item of role) {
        if (item === 'owner') return true;
    }
    return false;
}

interface AuthUserRecord {
    id?: string;
    name?: string;
    company_id?: string;
    raw?: Record<string, unknown>;
}

interface AuthSliceView {
    status?: string;
    user?: AuthUserRecord;
    activeCompanyId?: string | null;
}

interface CompanyRecord {
    company_id?: string;
    name?: string;
    role?: unknown;
}

export class PlatformUser extends PlatformElement {
    static i18nNamespace = 'platform';

    static override properties: PropertyDeclarations = {
        block: { type: Boolean, reflect: true },
        documentationTag: { type: String, attribute: 'documentation-tag' },
        _menuOpen: { state: true },
        _anchor: { state: true },
        _companySelectorOpen: { state: true },
        _avatarFallbackLevel: { state: true },
    };

    constructor() {
        super();
        this.block = false;
        this.documentationTag = null;
        this._menuOpen = false;
        this._companySelectorOpen = false;
        this._avatarFallbackLevel = 0;
        this._menuAvatarSig = '';

        this._authSelect = this.select((s): AuthSliceView => ({
            status: s.auth.status,
            user: s.auth.user === null ? undefined : s.auth.user,
            activeCompanyId: s.auth.activeCompanyId,
        }));
        this._companiesSelect = this.select((s) => s.companies.list);
        this._themeSelect = this.select((s) => s.theme.mode);
        this._localeSelect = this.select((s) => s.i18n.locale);

        this._companiesLoaded = false;

        this._anchor = null;
    }

    override connectedCallback(): void {
        super.connectedCallback();
        this.useDomEvent(document, 'click', (e) => this._onDocumentClick(e));
        this.useDomEvent(window, 'storage', (e: StorageEvent) => this._onStorage(e));
    }

    override disconnectedCallback(): void {
        super.disconnectedCallback();
    }

    override updated(changed: PropertyValues<this>): void {
        super.updated(changed);

        const auth = this._authSelect.value;
        if (auth.status === 'authenticated' && auth.user && !this._companiesLoaded) {
            this._companiesLoaded = true;
            this.dispatch(COMPANIES_EVENTS.LOAD_REQUESTED, null);
        }

        const menuUser = auth.user;
        if (menuUser) {
            const uid = menuUserId(menuUser.raw);
            const url = this._avatarUrl(menuUser);
            const sig = `${uid}|${url === null ? '' : url}`;
            if (this._menuAvatarSig !== sig) {
                this._menuAvatarSig = sig;
                this._avatarFallbackLevel = 0;
            }
        }

        if (this._anchor === null) {
            const button = this.renderRoot?.querySelector('.user-button');
            if (button instanceof HTMLElement) {
                this._anchor = button;
            }
        }
        if (this._menuOpen) {
            const popover = this.renderRoot.querySelector('platform-popover');
            if (!(popover instanceof PlatformPopover)) {
                throw new Error('platform-user: open menu popover is missing');
            }
            popover.reposition();
        }
    }

    _onDocumentClick(e: Event) {
        if (!this._menuOpen) return;
        const path = e.composedPath();
        if (!path.includes(this)) {
            this._menuOpen = false;
            this._companySelectorOpen = false;
        }
    }

    _toggleMenu(e: Event): void {
        e.stopPropagation();
        const next = !this._menuOpen;
        this._menuOpen = next;
        if (!next) {
            this._companySelectorOpen = false;
        }
    }

    _closeMenu(): void {
        this._menuOpen = false;
        this._companySelectorOpen = false;
    }

    _toggleCompanySelector(e: Event): void {
        e.stopPropagation();
        this._companySelectorOpen = !this._companySelectorOpen;
    }

    _switchCompany(companyId: string | undefined, e: Event): void {
        e.stopPropagation();
        const auth = this._authSelect.value;
        const currentCompanyId = this._currentCompanyId(auth);
        if (!companyId || companyId === currentCompanyId) {
            this._companySelectorOpen = false;
            return;
        }
        this.switchCompany(companyId);
    }

    _onStorage(event: StorageEvent): void {
        if (event.key !== COMPANY_SWITCH_STORAGE_KEY || !event.newValue) return;
        const parts = event.newValue.split('|');
        if (parts.length !== 3) return;
        const targetSubdomain = parts[2];
        if (!targetSubdomain) return;
        this._redirectToSubdomain(targetSubdomain);
    }

    _redirectToSubdomain(subdomain: string): void {
        const targetPath = `${window.location.pathname}${window.location.search}${window.location.hash}`;
        const targetUrl = buildCompanySubdomainUrl(subdomain, targetPath);
        if (targetUrl === window.location.href) return;
        window.location.href = targetUrl;
    }

    _setLocale(locale: string, e: Event): void {
        e.stopPropagation();
        this.setLocale(locale);
    }

    _toggleTheme(): void {
        const next = this._themeSelect.value === 'dark' ? 'light' : 'dark';
        this.setTheme(next);
    }

    _openUserInfo(): void {
        this._menuOpen = false;
        const auth = this._authSelect.value;
        const user = auth.user;
        if (!user) return;
        const userId = (user.raw && user.raw.user_id as string | undefined) || user.id;
        if (!userId) return;
        this.openModal('platform.user_info', { userId });
    }

    _openCalendar(): void {
        this._menuOpen = false;
        this.openModal('platform.calendar', {});
    }

    _openMail(): void {
        this._menuOpen = false;
        this.openModal('platform.mail', {});
    }

    _openDocumentation(): void {
        this._menuOpen = false;
        const tag = (typeof this.documentationTag === 'string' && this.documentationTag.trim())
            ? this.documentationTag.trim()
            : null;
        const url = buildScenarioDocumentationUrl({
            tag,
            locale: this._localeSelect.value,
        });
        window.open(url, '_blank', 'noopener,noreferrer');
    }

    _openServicesHub(e: Event): void {
        e.stopPropagation();
        this._menuOpen = false;
        this.openModal('platform.services', {});
    }

    _openCreateCompany(e: Event): void {
        e.stopPropagation();
        this._menuOpen = false;
        this._companySelectorOpen = false;
        this.openModal('platform.company_create', null);
    }

    _isOwnerOfCompany(companyRecord: CompanyRecord | undefined): boolean {
        if (!companyRecord) return false;
        return hasOwnerRole(companyRecord.role);
    }

    _logout(): void {
        this._menuOpen = false;
        this.dispatch(CoreEvents.AUTH_LOGOUT_REQUESTED, null);
    }

    _currentCompanyId(auth: AuthSliceView): string | null {
        if (auth.activeCompanyId) return auth.activeCompanyId;
        const raw = auth.user && auth.user.raw;
        if (raw) {
            if (typeof raw.active_company_id === 'string' && raw.active_company_id) return raw.active_company_id;
            if (typeof raw.company_id === 'string' && raw.company_id) return raw.company_id;
        }
        return auth.user && auth.user.company_id ? auth.user.company_id : null;
    }

    _companyName(companyId: string | null): string {
        if (!companyId) return '';
        const company = this._companiesSelect.value.find((c) => c.company_id === companyId);
        return company && company.name ? company.name : '';
    }

    _displayName(user: AuthUserRecord): string {
        if (user.name) return user.name;
        const raw = user.raw;
        if (raw && typeof raw.name === 'string' && raw.name) return raw.name;
        return this.t('menu.user_fallback');
    }

    _displayEmail(user: AuthUserRecord): string {
        const raw = user.raw;
        if (!raw) return '';
        if (Array.isArray(raw.emails) && raw.emails.length > 0 && typeof raw.emails[0] === 'string') {
            return raw.emails[0];
        }
        return '';
    }

    _avatarUrl(user: AuthUserRecord): string | null {
        const raw = user.raw;
        if (!raw || typeof raw.avatar_url !== 'string') return null;
        const trimmed = raw.avatar_url.trim();
        return trimmed === '' ? null : trimmed;
    }

    _avatarLetter(user: AuthUserRecord): string {
        const sources = [user.name, user.raw && user.raw.name, this._displayEmail(user)];
        for (const src of sources) {
            if (typeof src === 'string' && src.trim().length > 0) {
                return src.trim().charAt(0).toUpperCase();
            }
        }
        return '?';
    }

    _onMenuAvatarError(): void {
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

    override render(): TemplateResult {
        const auth = this._authSelect.value;
        const user = auth.user;
        if (!user) return html``;

        const companies = this._companiesSelect.value;
        const currentCompanyId = this._currentCompanyId(auth);
        const currentCompanyName = this._companyName(currentCompanyId);
        const hasCompaniesMenu = companies.length >= 1;
        const activeCompanyRecord = currentCompanyId
            ? companies.find((c) => c.company_id === currentCompanyId)
            : undefined;
        const canCreateCompany = this._isOwnerOfCompany(activeCompanyRecord);
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

            <platform-popover
                trigger="manual"
                role="menu"
                placement="top-start"
                offset="8"
                .anchor=${this._anchor}
                ?open=${this._menuOpen}
                @popover-dismiss=${this._closeMenu}
            >
            ${this._menuOpen ? html`
                <div
                    class="user-menu"
                    @click=${(e: Event) => e.stopPropagation()}
                >
                    <button class="menu-item" type="button" data-menu-action="apps" @click=${this._openServicesHub}>
                        <platform-icon class="menu-icon" name="apps" size="18"></platform-icon>
                        <span class="menu-item-label">${this.t('menu.apps')}</span>
                    </button>

                    <div class="menu-divider"></div>

                    <button class="menu-item" data-menu-action="profile" @click=${this._openUserInfo}>
                        <platform-icon class="menu-icon" name="user" size="18"></platform-icon>
                        <span class="menu-item-label">${this.t('menu.profile')}</span>
                    </button>

                    ${hasCompaniesMenu ? html`
                        <button class="menu-item company-selector" data-menu-action="company-selector" @click=${this._toggleCompanySelector}>
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
                                        type="button"
                                        @click=${(e: Event) => this._switchCompany(company.company_id, e)}
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
                                ${canCreateCompany ? html`
                                    <button
                                        type="button"
                                        class="company-create-item"
                                        data-menu-action="create-company"
                                        @click=${this._openCreateCompany}
                                    >
                                        <span class="company-item-name">
                                            <platform-icon name="plus" size="14"></platform-icon>
                                            <span>${this.t('menu.create_company')}</span>
                                        </span>
                                    </button>
                                ` : ''}
                            </div>
                        ` : ''}
                    ` : ''}

                    <div class="menu-divider"></div>

                    <button class="menu-item" data-menu-action="calendar" @click=${this._openCalendar}>
                        <platform-icon class="menu-icon" name="calendar" size="18"></platform-icon>
                        <span class="menu-item-label">${this.t('menu.calendar')}</span>
                    </button>

                    <button class="menu-item" data-menu-action="mail" @click=${this._openMail}>
                        <platform-icon class="menu-icon" name="mail" size="18"></platform-icon>
                        <span class="menu-item-label">${this.t('menu.mail')}</span>
                    </button>

                    <button class="menu-item" data-menu-action="documentation" @click=${this._openDocumentation}>
                        <platform-icon class="menu-icon" name="book-open" size="18"></platform-icon>
                        <span class="menu-item-label">${this.t('menu.documentation')}</span>
                    </button>

                    <div class="lang-row" data-menu-action="language">
                        <platform-icon class="menu-icon" name="globe" size="18"></platform-icon>
                        <span class="menu-item-label">${this.t('menu.language')}</span>
                        <span class="lang-switcher">
                            <button
                                class=${classMap({ 'lang-option': true, active: locale === 'en' })}
                                data-locale="en"
                                @click=${(e: Event) => this._setLocale('en', e)}
                            >en</button>
                            <span class="lang-separator">|</span>
                            <button
                                class=${classMap({ 'lang-option': true, active: locale === 'ru' })}
                                data-locale="ru"
                                @click=${(e: Event) => this._setLocale('ru', e)}
                            >ru</button>
                        </span>
                    </div>

                    <button class="menu-item" data-menu-action="theme" @click=${this._toggleTheme}>
                        <platform-icon class="menu-icon" name=${themeMode === 'dark' ? 'sun' : 'moon'} size="18"></platform-icon>
                        <span class="menu-item-label">
                            ${themeMode === 'dark' ? this.t('menu.theme_light') : this.t('menu.theme_dark')}
                        </span>
                    </button>

                    <div class="menu-divider"></div>

                    <button class="menu-item danger" data-menu-action="logout" @click=${this._logout}>
                        <platform-icon class="menu-icon" name="logout" size="18"></platform-icon>
                        <span class="menu-item-label">${this.t('menu.logout')}</span>
                    </button>
                </div>
            ` : ''}
            </platform-popover>
        `;
    }
    declare block: boolean;
    declare documentationTag: string | null;
    declare _menuOpen: boolean;
    declare _anchor: HTMLElement | null;
    declare _companySelectorOpen: boolean;
    declare _avatarFallbackLevel: number;

    private _menuAvatarSig: string;
    private _authSelect: SelectController<AuthSliceView>;
    private _companiesSelect: SelectController<CompanyRecord[]>;
    private _themeSelect: SelectController<'dark' | 'light'>;
    private _localeSelect: SelectController<string>;
    private _companiesLoaded: boolean;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        css`
            :host { display: inline-block; position: relative; }
            :host([block]) { display: block; width: 100%; }

            :host-context(platform-sidebar[collapsed]):host([block]),
            :host-context(platform-service-sidebar[collapsed]):host([block]) {
                display: flex;
                justify-content: center;
                width: 100%;
            }

            :host-context(platform-sidebar[collapsed]) .user-info,
            :host-context(platform-sidebar[collapsed]) .chevron,
            :host-context(platform-sidebar[collapsed]) .toolbar-slot,
            :host-context(platform-service-sidebar[collapsed]) .user-info,
            :host-context(platform-service-sidebar[collapsed]) .chevron,
            :host-context(platform-service-sidebar[collapsed]) .toolbar-slot {
                display: none;
            }

            :host-context(platform-sidebar[collapsed]) .user-button,
            :host-context(platform-service-sidebar[collapsed]) .user-button {
                justify-content: center;
                width: 40px;
                height: 40px;
                min-width: 40px;
                min-height: 40px;
                margin: 0 auto;
                gap: 0;
                padding: 0;
                background: transparent;
                border: none;
                border-radius: var(--radius-full);
                box-shadow: none;
            }

            :host-context(platform-sidebar[collapsed]) .user-button:hover,
            :host-context(platform-service-sidebar[collapsed]) .user-button:hover {
                background: var(--glass-solid-subtle);
                box-shadow: none;
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
                transition: var(--motion-transition-interactive);
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
                font-size: var(--text-base);
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
                font-size: var(--text-base);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }
            .user-email {
                font-size: var(--text-sm);
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
                padding: var(--space-1) 0;
                min-width: min(280px, calc(100vw - 16px));
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
                font-size: var(--text-base);
                color: var(--text-primary);
                text-align: left;
            }
            .menu-item:hover { background: var(--glass-solid-medium); }
            .menu-item.danger { color: var(--error); }
            .menu-item.danger:hover { background: var(--error-bg); }
            .menu-item.company-selector { justify-content: space-between; }

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
                font-size: var(--text-base);
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

            .company-create-item {
                display: flex;
                align-items: center;
                width: 100%;
                padding: var(--space-2) var(--space-3);
                margin-top: var(--space-1);
                background: transparent;
                border: 1px dashed var(--glass-border-medium);
                border-radius: var(--radius-md);
                cursor: pointer;
                font-size: var(--text-sm);
                color: var(--accent);
                font-weight: var(--font-medium);
                text-align: left;
            }
            .company-create-item:hover {
                background: var(--glass-solid-medium);
                border-color: var(--accent);
            }

            .lang-row {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                padding: var(--space-2) var(--space-3);
                font-size: var(--text-base);
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
                font-size: var(--text-base);
            }
            .lang-option.active { color: var(--accent); font-weight: var(--font-semibold); }
            .lang-separator { color: var(--text-tertiary); }
        `,
    ];
}

customElements.define('platform-user', PlatformUser);
