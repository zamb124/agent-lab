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
import { PlatformElement } from '../platform-element/index.js';
import { AppEvents } from '../utils/types.js';
import './platform-icon.js';

export class PlatformUser extends PlatformElement {
    static properties = {
        user: { type: Object },
        serviceAttrs: { type: Object },
        companies: { type: Array },
        _menuOpen: { type: Boolean },
        _companySelectorOpen: { type: Boolean }
    };

    constructor() {
        super();
        this.user = null;
        this.serviceAttrs = null;
        this.companies = [];
        this._menuOpen = false;
        this._companySelectorOpen = false;
    }

    connectedCallback() {
        super.connectedCallback();
        this._loadUser();
        window.addEventListener(AppEvents.AUTH_CHANGE, () => this._loadUser());
        document.addEventListener('click', (e) => this._handleDocumentClick(e));
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        document.removeEventListener('click', (e) => this._handleDocumentClick(e));
    }

    async _loadUser() {
        if (!this.auth) {
            this.user = null;
            return;
        }

        try {
            const userData = await this.auth.get('/api/auth/me');
            this.user = userData;
            
            if (userData.companies && Object.keys(userData.companies).length > 1) {
                this.companies = Object.entries(userData.companies).map(([company_id, roles]) => ({
                    company_id,
                    name: company_id,
                    roles
                }));
            }
            
            await this._loadServiceAttrs();
        } catch (error) {
            console.error('[PlatformUser] Failed to load user:', error);
            this.user = null;
        }
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
        this._menuOpen = !this._menuOpen;
        this.requestUpdate();
    }

    _handleDocumentClick(e) {
        if (!this.contains(e.target) && this._menuOpen) {
            this._menuOpen = false;
            this._companySelectorOpen = false;
            this.requestUpdate();
        }
    }

    _getUserInitials() {
        if (!this.user) return '?';
        const name = this.user.name || this.user.emails?.[0] || '';
        return name.charAt(0).toUpperCase();
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
            this.success('Компания изменена');
            
            setTimeout(() => {
                window.location.reload();
            }, 500);
        } catch (error) {
            console.error('[PlatformUser] Failed to switch company:', error);
            this.error(`Ошибка смены компании: ${error.message}`);
        }
    }

    _openSettings() {
        this._menuOpen = false;
        
        const service = this._getCurrentService() || 'frontend';
        window.location.href = `/${service}/settings`;
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
        return company?.name || companyId;
    }

    render() {
        if (!this.user) {
            return html``;
        }

        const currentCompanyName = this._getCompanyName(this.user.active_company_id || this.user.company_id);
        const hasMultipleCompanies = this.companies.length > 1;

        return html`
            <div class="user-container">
                <button class="user-button" @click=${this._toggleMenu} title="Меню пользователя">
                    <div class="user-avatar">${this._getUserInitials()}</div>
                    <div class="user-info">
                        <div class="user-name">${this.user.name || 'Пользователь'}</div>
                        <div class="user-email">${this.user.emails?.[0] || ''}</div>
                    </div>
                    <platform-icon name="chevron-down" size="12" class="chevron ${this._menuOpen ? 'open' : ''}"></platform-icon>
                </button>

                ${this._menuOpen ? html`
                    <div class="user-menu">
                        <button class="menu-item" @click=${this._openProfileModal}>
                            <platform-icon name="user" size="18" class="menu-icon"></platform-icon>
                            <span>Профиль</span>
                        </button>
                        
                        ${hasMultipleCompanies ? html`
                            <div class="menu-divider"></div>
                            <button class="menu-item company-selector" @click=${this._toggleCompanySelector}>
                                <platform-icon name="box" size="18" class="menu-icon"></platform-icon>
                                <span class="menu-label">
                                    <span class="label-text">Компания</span>
                                    <span class="company-name">${currentCompanyName}</span>
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
                                            <span>${company.name}</span>
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
                            <span>Настройки</span>
                        </button>
                        
                        <button class="menu-item" @click=${this._toggleTheme}>
                            <platform-icon name="${this.theme?.isDark ? 'sun' : 'moon'}" size="18" class="menu-icon"></platform-icon>
                            <span>${this.theme?.isDark ? 'Светлая тема' : 'Темная тема'}</span>
                        </button>
                        
                        <div class="menu-divider"></div>
                        
                        <button class="menu-item danger" @click=${this._logout}>
                            <platform-icon name="logout" size="18" class="menu-icon"></platform-icon>
                            <span>Выйти</span>
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

            .user-container {
                position: relative;
                width: 100%;
            }

            .user-button {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                padding: var(--space-3);
                background: var(--glass-solid-subtle);
                border-radius: var(--radius-lg);
                border: 1px solid var(--glass-border-subtle);
                cursor: pointer;
                transition: all var(--duration-fast);
                box-shadow: 0 1px 4px rgba(0,0,0,0.1);
                width: 100%;
                box-sizing: border-box;
            }

            .user-button:hover {
                background: var(--glass-solid-medium);
                box-shadow: 0 2px 6px rgba(0,0,0,0.15);
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
                box-shadow: 0 4px 12px rgba(16, 185, 129, 0.25);
                flex-shrink: 0;
            }

            .user-info {
                flex: 1;
                min-width: 0;
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
                overflow: hidden;
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
                font-size: var(--text-sm);
                color: var(--text-primary);
                transition: background var(--duration-fast);
                text-align: left;
            }

            .menu-item:hover {
                background: var(--hover-color);
            }

            .menu-item.danger {
                color: var(--error);
            }

            .menu-item.danger:hover {
                background: var(--error-bg);
            }

            .menu-item.company-selector {
                justify-content: space-between;
            }

            .menu-icon {
                min-width: 20px;
                display: flex;
                align-items: center;
                justify-content: center;
                color: var(--text-secondary);
            }

            .menu-label {
                flex: 1;
                display: flex;
                flex-direction: column;
                gap: 2px;
            }

            .label-text {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }

            .company-name {
                font-size: var(--text-sm);
                color: var(--text-primary);
                font-weight: var(--font-medium);
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
                font-size: var(--text-sm);
                color: var(--text-primary);
                transition: all var(--duration-fast);
            }

            .company-item:hover {
                background: var(--hover-color);
                border-color: var(--border-color);
            }

            .company-item.active {
                background: var(--accent-subtle);
                border-color: var(--accent);
                color: var(--accent);
                font-weight: var(--font-semibold);
            }

            .check-icon {
                color: var(--accent);
                display: flex;
                align-items: center;
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

