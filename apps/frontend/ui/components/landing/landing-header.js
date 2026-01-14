/**
 * Landing Header - Шапка лендинга с навигацией
 */
import { html, css } from 'lit';
import { classMap } from 'lit/directives/class-map.js';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

export class LandingHeader extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                position: sticky;
                top: 0;
                z-index: 100;
                background: rgba(15, 15, 15, 0.9);
                backdrop-filter: blur(10px);
                border-bottom: 1px solid rgba(255, 255, 255, 0.1);
            }
            
            .header-container {
                max-width: 1440px;
                margin: 0 auto;
                padding: 20px;
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 20px;
            }
            
            .logo {
                display: flex;
                align-items: center;
                gap: 10px;
                text-decoration: none;
                white-space: nowrap;
            }
            
            .logo-icon {
                width: 32px;
                height: 32px;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            
            .logo-icon img {
                width: 100%;
                height: 100%;
                object-fit: contain;
            }
            
            .logo-text {
                font-family: 'Fira Sans Condensed', sans-serif;
                font-size: 18px;
                font-weight: 500;
                color: var(--landing-secondary, #E8E8E8);
            }
            
            .nav {
                display: none;
                align-items: center;
                gap: 30px;
            }
            
            .nav-link {
                font-family: 'Fira Sans', sans-serif;
                font-size: 16px;
                color: var(--landing-secondary, #E8E8E8);
                text-decoration: none;
                transition: color 0.3s;
                white-space: nowrap;
            }
            
            .nav-link:hover {
                color: var(--landing-primary, #5768FE);
            }
            
            .nav-dropdown {
                position: relative;
            }
            
            .nav-dropdown-trigger {
                display: flex;
                align-items: center;
                gap: 6px;
                font-family: 'Fira Sans', sans-serif;
                font-size: 16px;
                color: var(--landing-secondary, #E8E8E8);
                text-decoration: none;
                transition: color 0.3s;
                white-space: nowrap;
                cursor: pointer;
                background: none;
                border: none;
                padding: 0;
            }
            
            .nav-dropdown-trigger:hover {
                color: var(--landing-primary, #5768FE);
            }
            
            .nav-dropdown-trigger svg {
                width: 12px;
                height: 12px;
                transition: transform 0.3s;
            }
            
            .nav-dropdown.open .nav-dropdown-trigger svg {
                transform: rotate(180deg);
            }
            
            .nav-dropdown-menu {
                position: absolute;
                top: 100%;
                left: 50%;
                transform: translateX(-50%);
                margin-top: 16px;
                min-width: 220px;
                background: rgba(30, 30, 30, 0.98);
                backdrop-filter: blur(20px);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 12px;
                padding: 12px;
                display: none;
                flex-direction: column;
                gap: 4px;
                box-shadow: 0 20px 40px rgba(0, 0, 0, 0.4);
            }
            
            .nav-dropdown.open .nav-dropdown-menu {
                display: flex;
            }
            
            .nav-dropdown-item {
                display: flex;
                align-items: center;
                gap: 12px;
                padding: 12px 16px;
                color: var(--landing-secondary, #E8E8E8);
                text-decoration: none;
                border-radius: 8px;
                transition: all 0.2s;
            }
            
            .nav-dropdown-item:hover {
                background: rgba(87, 104, 254, 0.15);
                color: var(--landing-primary, #5768FE);
            }
            
            .nav-dropdown-item-icon {
                width: 24px;
                height: 24px;
                flex-shrink: 0;
            }
            
            .nav-dropdown-item-icon img {
                width: 100%;
                height: 100%;
                object-fit: contain;
            }
            
            .nav-dropdown-item-content {
                display: flex;
                flex-direction: column;
                gap: 2px;
            }
            
            .nav-dropdown-item-title {
                font-family: 'Fira Sans', sans-serif;
                font-size: 15px;
                font-weight: 500;
            }
            
            .nav-dropdown-item-desc {
                font-family: 'Fira Sans', sans-serif;
                font-size: 12px;
                color: rgba(232, 232, 232, 0.6);
            }
            
            .header-actions {
                display: flex;
                align-items: center;
                gap: 16px;
            }
            
            .lang-switcher {
                display: flex;
                align-items: center;
                gap: 4px;
                background: transparent;
                border: none;
                color: var(--landing-secondary);
                font-family: 'Fira Sans', sans-serif;
                font-size: 14px;
                cursor: pointer;
            }
            
            .lang-option {
                padding: 4px 8px;
                color: rgba(232, 232, 232, 0.6);
                transition: color 0.3s;
            }
            
            .lang-option.active {
                color: var(--landing-secondary);
            }
            
            .lang-option:hover {
                color: var(--landing-primary);
            }
            
            .lang-separator {
                color: rgba(232, 232, 232, 0.3);
            }
            
            .login-btn {
                display: flex;
                padding: 8px 20px;
                background: var(--landing-primary);
                border: none;
                border-radius: 24px;
                color: var(--landing-secondary);
                font-family: 'Fira Sans', sans-serif;
                font-size: 14px;
                font-weight: 500;
                cursor: pointer;
                transition: background 0.3s;
                white-space: nowrap;
            }
            
            .login-btn:hover {
                background: #6877ff;
            }
            
            .dashboard-btn {
                display: flex;
                padding: 8px 20px;
                background: transparent;
                border: 1px solid var(--landing-primary);
                border-radius: 24px;
                color: var(--landing-secondary);
                font-family: 'Fira Sans', sans-serif;
                font-size: 14px;
                font-weight: 500;
                cursor: pointer;
                transition: all 0.3s;
                white-space: nowrap;
                text-decoration: none;
            }
            
            .dashboard-btn:hover {
                background: var(--landing-primary);
                color: var(--landing-secondary);
            }
            
            .burger {
                display: flex;
                flex-direction: column;
                gap: 4px;
                background: none;
                border: none;
                cursor: pointer;
                padding: 8px;
            }
            
            .burger-line {
                width: 24px;
                height: 2px;
                background: var(--landing-secondary);
                transition: all 0.3s;
            }
            
            .burger.active .burger-line:nth-child(1) {
                transform: rotate(45deg) translateY(7px);
            }
            
            .burger.active .burger-line:nth-child(2) {
                opacity: 0;
            }
            
            .burger.active .burger-line:nth-child(3) {
                transform: rotate(-45deg) translateY(-7px);
            }
            
            .mobile-menu {
                display: none;
                position: fixed;
                top: 71px;
                left: 0;
                right: 0;
                bottom: 0;
                background: rgba(15, 15, 15, 0.98);
                backdrop-filter: blur(20px);
                padding: 40px 20px;
                flex-direction: column;
                gap: 24px;
                z-index: 99;
            }
            
            .mobile-menu.active {
                display: flex;
            }
            
            .mobile-menu .nav-link {
                font-size: 24px;
                text-align: center;
            }
            
            .mobile-menu .login-btn,
            .mobile-menu .dashboard-btn {
                display: block;
                width: 100%;
                padding: 16px;
                font-size: 18px;
                text-align: center;
            }
            
            @media (min-width: 768px) {
                .header-container {
                    padding: 24px 40px;
                }
                
                .logo-icon {
                    width: 36px;
                    height: 36px;
                }
                
                .logo-text {
                    font-size: 20px;
                }
                
                .nav {
                    display: flex;
                }
                
                .nav-link {
                    font-size: 18px;
                }
                
                .nav-dropdown-trigger {
                    font-size: 18px;
                }
                
                .lang-switcher {
                    display: flex;
                }
                
                .login-btn,
                .dashboard-btn {
                    display: block;
                }
                
                .burger {
                    display: none;
                }
            }
            
            @media (min-width: 1440px) {
                .header-container {
                    padding: 30px 80px;
                }
                
                .logo-icon {
                    width: 40px;
                    height: 40px;
                }
                
                .logo-text {
                    font-size: 22px;
                }
                
                .lang-switcher {
                    font-size: 16px;
                }
                
                .login-btn {
                    padding: 10px 24px;
                    font-size: 16px;
                }
                
                .nav {
                    gap: 40px;
                }
                
                .nav-link {
                    font-size: 20px;
                }
                
                .nav-dropdown-trigger {
                    font-size: 20px;
                }
                
                .login-btn,
                .dashboard-btn {
                    padding: 12px 24px;
                    font-size: 18px;
                }
            }
            
            .mobile-products-group {
                display: flex;
                flex-direction: column;
                gap: 8px;
            }
            
            .mobile-products-title {
                font-family: 'Fira Sans', sans-serif;
                font-size: 14px;
                color: rgba(232, 232, 232, 0.5);
                text-transform: uppercase;
                letter-spacing: 1px;
                padding: 0 8px;
            }
            
            .mobile-product-link {
                display: flex;
                align-items: center;
                gap: 12px;
                padding: 12px 16px;
                color: var(--landing-secondary, #E8E8E8);
                text-decoration: none;
                font-family: 'Fira Sans', sans-serif;
                font-size: 18px;
                border-radius: 8px;
                transition: background 0.2s;
            }
            
            .mobile-product-link:hover {
                background: rgba(87, 104, 254, 0.15);
            }
            
            .mobile-product-icon {
                width: 24px;
                height: 24px;
                flex-shrink: 0;
            }
            
            .mobile-product-icon img {
                width: 100%;
                height: 100%;
                object-fit: contain;
            }
        `
    ];

    static properties = {
        mobileMenuOpen: { type: Boolean },
        currentLang: { type: String },
        isAuthenticated: { type: Boolean },
        user: { type: Object },
        productsDropdownOpen: { type: Boolean }
    };

    constructor() {
        super();
        this.mobileMenuOpen = false;
        this.currentLang = 'ru';
        this.isAuthenticated = false;
        this.user = null;
        this.productsDropdownOpen = false;
    }

    async _checkAuth() {
        try {
            const response = await fetch('/frontend/api/auth/me', {
                credentials: 'include'
            });
            if (response.ok) {
                this.user = await response.json();
                this.isAuthenticated = true;
            }
        } catch (e) {
            // Пользователь не авторизован
        }
    }

    _toggleMobileMenu() {
        this.mobileMenuOpen = !this.mobileMenuOpen;
    }

    _closeMobileMenu() {
        this.mobileMenuOpen = false;
    }

    _setLang(lang) {
        if (this.currentLang === lang) return;
        this.currentLang = lang;
        this.dispatchEvent(new CustomEvent('lang-changed', { 
            detail: { lang: this.currentLang }
        }));
    }

    _handleNavClick(e) {
        this._closeMobileMenu();
        this._closeProductsDropdown();
    }

    _toggleProductsDropdown(e) {
        e.preventDefault();
        e.stopPropagation();
        this.productsDropdownOpen = !this.productsDropdownOpen;
    }

    _closeProductsDropdown() {
        this.productsDropdownOpen = false;
    }

    connectedCallback() {
        super.connectedCallback();
        this._checkAuth();
        this._handleOutsideClick = this._handleOutsideClick.bind(this);
        document.addEventListener('click', this._handleOutsideClick);
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        document.removeEventListener('click', this._handleOutsideClick);
    }

    _handleOutsideClick(e) {
        const path = e.composedPath();
        const dropdown = this.shadowRoot?.querySelector('.nav-dropdown');
        if (dropdown && !path.includes(dropdown)) {
            this._closeProductsDropdown();
        }
    }

    _handleLoginClick() {
        console.log('🔵 Login button clicked');
        this.dispatchEvent(new CustomEvent('open-auth-modal', {
            bubbles: true,
            composed: true
        }));
    }

    render() {
        return html`
            <header class="header-container">
                <a href="#" class="logo" @click=${this._closeMobileMenu}>
                    <div class="logo-icon">
                        <img src="/static/core/assets/service_logos/frontend_logo.svg" alt="Humanitec" />
                    </div>
                    <span class="logo-text">Humanitec</span>
                </a>
                
                <nav class="nav">
                    <a href="#about" class="nav-link">О нас</a>
                    <a href="#abilities" class="nav-link">Возможности</a>
                    <div class=${classMap({ 'nav-dropdown': true, 'open': this.productsDropdownOpen })}>
                        <button class="nav-dropdown-trigger" @click=${this._toggleProductsDropdown}>
                            Наши решения
                            <svg viewBox="0 0 12 12" fill="currentColor">
                                <path d="M2.5 4.5L6 8L9.5 4.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
                            </svg>
                        </button>
                        <div class="nav-dropdown-menu">
                            <a href="/products/agents" class="nav-dropdown-item" @click=${this._handleNavClick}>
                                <div class="nav-dropdown-item-icon">
                                    <img src="/static/core/assets/service_logos/agents_logo.svg" alt="AI Studio" />
                                </div>
                                <div class="nav-dropdown-item-content">
                                    <span class="nav-dropdown-item-title">AI Studio</span>
                                    <span class="nav-dropdown-item-desc">Конструктор AI-агентов</span>
                                </div>
                            </a>
                            <a href="/products/rag" class="nav-dropdown-item" @click=${this._handleNavClick}>
                                <div class="nav-dropdown-item-icon">
                                    <img src="/static/core/assets/service_logos/rag_logo.svg" alt="Knowledge Base" />
                                </div>
                                <div class="nav-dropdown-item-content">
                                    <span class="nav-dropdown-item-title">Knowledge Base</span>
                                    <span class="nav-dropdown-item-desc">База знаний с поиском</span>
                                </div>
                            </a>
                            <a href="/products/crm" class="nav-dropdown-item" @click=${this._handleNavClick}>
                                <div class="nav-dropdown-item-icon">
                                    <img src="/static/core/assets/service_logos/crm_logo.svg" alt="NetWorkle" />
                                </div>
                                <div class="nav-dropdown-item-content">
                                    <span class="nav-dropdown-item-title">NetWorkle</span>
                                    <span class="nav-dropdown-item-desc">Умная записная книжка</span>
                                </div>
                            </a>
                        </div>
                    </div>
                    <a href="/docs" class="nav-link">Документация</a>
                </nav>
                
                <div class="header-actions">
                    <div class="lang-switcher">
                        <span 
                            class=${classMap({ 'lang-option': true, active: this.currentLang === 'en' })}
                            @click=${() => this._setLang('en')}
                        >en</span>
                        <span class="lang-separator">|</span>
                        <span 
                            class=${classMap({ 'lang-option': true, active: this.currentLang === 'ru' })}
                            @click=${() => this._setLang('ru')}
                        >ru</span>
                    </div>
                    
                    ${this.isAuthenticated
                        ? html`<a href="/dashboard" class="dashboard-btn">Dashboard</a>`
                        : html`<button class="login-btn" @click=${this._handleLoginClick}>Войти</button>`
                    }
                    
                    <button 
                        class=${classMap({ burger: true, active: this.mobileMenuOpen })}
                        @click=${this._toggleMobileMenu}
                        aria-label="Меню"
                    >
                        <span class="burger-line"></span>
                        <span class="burger-line"></span>
                        <span class="burger-line"></span>
                    </button>
                </div>
            </header>
            
            <div class=${classMap({ 'mobile-menu': true, active: this.mobileMenuOpen })}>
                <a href="#about" class="nav-link" @click=${this._handleNavClick}>О нас</a>
                <a href="#abilities" class="nav-link" @click=${this._handleNavClick}>Возможности</a>
                
                <div class="mobile-products-group">
                    <span class="mobile-products-title">Наши решения</span>
                    <a href="/products/agents" class="mobile-product-link" @click=${this._handleNavClick}>
                        <div class="mobile-product-icon">
                            <img src="/static/core/assets/service_logos/agents_logo.svg" alt="AI Studio" />
                        </div>
                        AI Studio
                    </a>
                    <a href="/products/rag" class="mobile-product-link" @click=${this._handleNavClick}>
                        <div class="mobile-product-icon">
                            <img src="/static/core/assets/service_logos/rag_logo.svg" alt="Knowledge Base" />
                        </div>
                        Knowledge Base
                    </a>
                    <a href="/products/crm" class="mobile-product-link" @click=${this._handleNavClick}>
                        <div class="mobile-product-icon">
                            <img src="/static/core/assets/service_logos/crm_logo.svg" alt="NetWorkle" />
                        </div>
                        NetWorkle
                    </a>
                </div>
                
                <a href="/docs" class="nav-link" @click=${this._handleNavClick}>Документация</a>
                ${this.isAuthenticated
                    ? html`<a href="/dashboard" class="dashboard-btn" @click=${this._closeMobileMenu}>Dashboard</a>`
                    : html`<button class="login-btn" @click=${() => { this._closeMobileMenu(); this._handleLoginClick(); }}>Войти</button>`
                }
            </div>
        `;
    }
}

customElements.define('landing-header', LandingHeader);

