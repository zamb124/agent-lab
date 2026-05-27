/**
 * Landing Header - Шапка лендинга с навигацией
 */
import { html, css } from 'lit';
import { classMap } from 'lit/directives/class-map.js';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

import { isAllowedLandingScrollSectionId, storePendingLandingSectionTarget } from './landing-section-scroll.js';

const INTERNAL_HREF_TO_ROUTE = Object.freeze({
    '/': 'landing',
    '/products/agents':    'product-agents',
    '/products/rag':       'product-rag',
    '/products/crm':       'product-crm',
    '/products/sync':      'product-sync',
    '/products/documents': 'product-documents',
    '/support':            'support',
    '/dashboard':          'dashboard',
    '/blog':               'blog',
    '/about':              'about',
    '/roadmap':            'roadmap',
});

export class LandingHeader extends PlatformElement {
    static i18nNamespace = 'landing';

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                position: sticky;
                top: 0;
                z-index: 100;
                width: 100%;
                max-width: 100%;
                box-sizing: border-box;
                overflow-x: clip;
                background: rgba(15, 15, 15, 0.9);
                backdrop-filter: blur(10px);
                border-bottom: 1px solid rgba(255, 255, 255, 0.1);
            }
            
            .header-container {
                max-width: 1440px;
                width: 100%;
                min-width: 0;
                margin: 0 auto;
                padding: max(20px, var(--platform-safe-top)) max(20px, var(--platform-safe-right))
                    max(20px, var(--platform-safe-bottom)) max(20px, var(--platform-safe-left));
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 20px;
                box-sizing: border-box;
            }
            
            .logo {
                display: flex;
                align-items: center;
                gap: 10px;
                text-decoration: none;
                white-space: nowrap;
                flex: 1 1 0;
                min-width: 0;
                overflow: hidden;
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
                overflow: hidden;
                text-overflow: ellipsis;
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
                transition: var(--motion-transition-interactive);
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
                flex: 0 0 auto;
                min-width: 0;
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
                transition: var(--motion-transition-interactive);
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
                transition: var(--motion-transition-interactive);
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
                inset: 0;
                top: 71px;
                box-sizing: border-box;
                padding: clamp(16px, 4vw, 28px) clamp(16px, 5vw, 24px) max(24px, env(safe-area-inset-bottom));
                flex-direction: column;
                align-items: stretch;
                gap: clamp(12px, 3vw, 20px);
                z-index: 10000;
                background: #0f0f0f;
                overflow-y: auto;
                -webkit-overflow-scrolling: touch;
                min-height: calc(100vh - 71px);
                min-height: calc(100dvh - 71px);
                max-width: 100vw;
            }
            
            .mobile-menu.active {
                display: flex;
            }
            
            .mobile-menu .nav-link {
                box-sizing: border-box;
                display: block;
                width: 100%;
                padding: 12px 0;
                font-size: clamp(17px, 4.6vw, 20px);
                font-weight: 500;
                line-height: 1.3;
                text-align: start;
                text-decoration: none;
            }
            
            .mobile-menu-footer {
                margin-top: auto;
                padding-top: clamp(12px, 3vw, 20px);
            }
            
            .mobile-menu .login-btn,
            .mobile-menu .dashboard-btn {
                display: block;
                box-sizing: border-box;
                width: 100%;
                padding: 14px 20px;
                font-size: 17px;
                text-align: center;
            }

            /* Шапка: CTA только в нижней части выезжающего меню, без дубля рядом с бургером */
            @media (max-width: 1099px) {
                .header-actions > .login-btn,
                .header-actions > .dashboard-btn {
                    display: none;
                }
            }
            
            @media (max-width: 480px) {
                .header-container {
                    gap: 8px;
                    padding: max(16px, var(--platform-safe-top)) max(12px, var(--platform-safe-right))
                        max(16px, var(--platform-safe-bottom)) max(12px, var(--platform-safe-left));
                }
            
                .header-actions {
                    gap: 6px;
                }

                .header-actions > .login-btn,
                .header-actions > .dashboard-btn {
                    padding: 6px 12px;
                    font-size: 12px;
                }
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
            }
            
            @media (min-width: 1100px) {
                .nav {
                    display: flex;
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
                gap: 4px;
                width: 100%;
                box-sizing: border-box;
                padding-top: 4px;
                border-top: 1px solid rgba(255, 255, 255, 0.08);
            }
            
            .mobile-products-title {
                font-family: 'Fira Sans', sans-serif;
                font-size: 12px;
                color: rgba(232, 232, 232, 0.5);
                text-transform: uppercase;
                letter-spacing: 0.08em;
                padding: 12px 0 8px;
                text-align: start;
                margin: 0;
            }
            
            .mobile-product-link {
                display: flex;
                align-items: center;
                gap: 12px;
                padding: 12px 12px;
                color: var(--landing-secondary, #E8E8E8);
                text-decoration: none;
                font-family: 'Fira Sans', sans-serif;
                font-size: clamp(16px, 4.2vw, 18px);
                border-radius: 8px;
                transition: background 0.2s;
                justify-content: flex-start;
                box-sizing: border-box;
                width: 100%;
                min-height: 48px;
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

            .mobile-menu-secondary {
                display: flex;
                flex-direction: column;
                width: 100%;
                box-sizing: border-box;
                padding-top: 4px;
                border-top: 1px solid rgba(255, 255, 255, 0.08);
            }
        `
    ];

    static properties = {
        mobileMenuOpen: { type: Boolean },
        productsDropdownOpen: { type: Boolean }
    };

    constructor() {
        super();
        this.mobileMenuOpen = false;
        this.productsDropdownOpen = false;
        this._authSel = this.select((s) => ({ status: s.auth.status, user: s.auth.user }));
        this._localeSel = this.select((s) => s.i18n.locale);
    }

    get isAuthenticated() {
        const v = this._authSel.value;
        return !!(v && v.status === 'authenticated');
    }

    get user() {
        const v = this._authSel.value;
        return (v && v.user && v.user.raw) || (v && v.user) || null;
    }

    _lt(key) {
        return this.t(key);
    }

    _toggleMobileMenu() {
        this.mobileMenuOpen = !this.mobileMenuOpen;
    }

    _closeMobileMenu() {
        this.mobileMenuOpen = false;
    }

    _onMobileMenuShellClick(e) {
        if (e.target === e.currentTarget) {
            this._closeMobileMenu();
        }
    }

    _onHeaderBarClick(e) {
        if (!this.mobileMenuOpen) {
            return;
        }
        const path = e.composedPath();
        const burger = this.shadowRoot?.querySelector('.burger');
        if (burger && path.includes(burger)) {
            return;
        }
        this._closeMobileMenu();
    }

    _setLang(lang) {
        if (this._localeSel.value === lang) {
            return;
        }
        this.setLocale(lang);
    }

    _navigateRoute(routeKey) {
        this.navigate(routeKey);
    }

    _resolveLandingPage() {
        const root = this.getRootNode();
        if (!(root instanceof ShadowRoot)) {
            return null;
        }
        const host = root.host;
        if (host?.tagName?.toLowerCase() !== 'landing-page') {
            return null;
        }
        return host;
    }

    _scrollToLandingSection(sectionId) {
        const page = this._resolveLandingPage();
        if (!page) {
            return;
        }
        const target = page.shadowRoot?.getElementById(sectionId);
        if (!target) {
            return;
        }
        target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    _handleNavClick(e) {
        const href = e.currentTarget.getAttribute('href');
        if (href?.startsWith('#')) {
            e.preventDefault();
            const sectionId = href.slice(1);
            if (this._resolveLandingPage()) {
                this._scrollToLandingSection(sectionId);
            } else if (isAllowedLandingScrollSectionId(sectionId)) {
                storePendingLandingSectionTarget(sectionId);
                this.navigate('landing');
            }
        } else {
            const routeKey = INTERNAL_HREF_TO_ROUTE[href];
            if (routeKey) {
                e.preventDefault();
                this._navigateRoute(routeKey);
            }
        }
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
        this._handleOutsideClick = this._handleOutsideClick.bind(this);
        document.addEventListener('click', this._handleOutsideClick);
    }

    disconnectedCallback() {
        document.removeEventListener('click', this._handleOutsideClick);
        super.disconnectedCallback();
    }

    _handleOutsideClick(e) {
        const path = e.composedPath();
        const dropdown = this.shadowRoot?.querySelector('.nav-dropdown');
        if (dropdown && !path.includes(dropdown)) {
            this._closeProductsDropdown();
        }
    }

    _handleLoginClick() {
        this.openModal('auth.login');
    }

    render() {
        const uiLocale = this._localeSel.value;
        const h = (sub) => this._lt(`header.${sub}`);
        return html`
            <header class="header-container" @click=${this._onHeaderBarClick}>
                <a href="/" class="logo" @click=${this._closeMobileMenu}>
                    <div class="logo-icon">
                        <img src="/static/core/assets/service_logos/frontend_logo.svg" alt="Humanitec" />
                    </div>
                    <span class="logo-text">Humanitec</span>
                </a>
                
                <nav class="nav">
                    <a href="#about" class="nav-link" @click=${this._handleNavClick}>${h('anchor_about')}</a>
                    <a href="#abilities" class="nav-link" @click=${this._handleNavClick}>${h('features')}</a>
                    <div class=${classMap({ 'nav-dropdown': true, 'open': this.productsDropdownOpen })}>
                        <button class="nav-dropdown-trigger" @click=${this._toggleProductsDropdown}>
                            ${h('solutions')}
                            <platform-icon name="arrow-down" size="12"></platform-icon>
                        </button>
                        <div class="nav-dropdown-menu">
                            <a href="/products/agents" class="nav-dropdown-item" @click=${this._handleNavClick}>
                                <div class="nav-dropdown-item-icon">
                                    <img src="/static/core/assets/service_logos/agents_logo.svg" alt=${h('product_agents_title')} />
                                </div>
                                <div class="nav-dropdown-item-content">
                                    <span class="nav-dropdown-item-title">${h('product_agents_title')}</span>
                                    <span class="nav-dropdown-item-desc">${h('product_agents_desc')}</span>
                                </div>
                            </a>
                            <a href="/products/rag" class="nav-dropdown-item" @click=${this._handleNavClick}>
                                <div class="nav-dropdown-item-icon">
                                    <img src="/static/core/assets/service_logos/rag_logo.svg" alt=${h('product_rag_title')} />
                                </div>
                                <div class="nav-dropdown-item-content">
                                    <span class="nav-dropdown-item-title">${h('product_rag_title')}</span>
                                    <span class="nav-dropdown-item-desc">${h('product_rag_desc')}</span>
                                </div>
                            </a>
                            <a href="/products/crm" class="nav-dropdown-item" @click=${this._handleNavClick}>
                                <div class="nav-dropdown-item-icon">
                                    <img src="/static/core/assets/service_logos/crm_logo.svg" alt=${h('product_crm_title')} />
                                </div>
                                <div class="nav-dropdown-item-content">
                                    <span class="nav-dropdown-item-title">${h('product_crm_title')}</span>
                                    <span class="nav-dropdown-item-desc">${h('product_crm_desc')}</span>
                                </div>
                            </a>
                            <a href="/products/sync" class="nav-dropdown-item" @click=${this._handleNavClick}>
                                <div class="nav-dropdown-item-icon">
                                    <img src="/static/core/assets/service_logos/sync_logo.svg" alt=${h('product_sync_title')} />
                                </div>
                                <div class="nav-dropdown-item-content">
                                    <span class="nav-dropdown-item-title">${h('product_sync_title')}</span>
                                    <span class="nav-dropdown-item-desc">${h('product_sync_desc')}</span>
                                </div>
                            </a>
                            <a href="/products/documents" class="nav-dropdown-item" @click=${this._handleNavClick}>
                                <div class="nav-dropdown-item-icon">
                                    <img src="/static/core/assets/service_logos/documents_logo.svg" alt=${h('product_documents_title')} />
                                </div>
                                <div class="nav-dropdown-item-content">
                                    <span class="nav-dropdown-item-title">${h('product_documents_title')}</span>
                                    <span class="nav-dropdown-item-desc">${h('product_documents_desc')}</span>
                                </div>
                            </a>
                        </div>
                    </div>
                    <a href="/documentation" class="nav-link">${h('docs')}</a>
                    <a href="/support" class="nav-link" @click=${this._handleNavClick}>${h('support')}</a>
                    <a href="/blog" class="nav-link" @click=${this._handleNavClick}>${h('blog')}</a>
                    <a href="/about" class="nav-link" @click=${this._handleNavClick}>${h('company_page')}</a>
                    <a href="/roadmap" class="nav-link" @click=${this._handleNavClick}>${h('roadmap')}</a>
                </nav>
                
                <div class="header-actions">
                    <div class="lang-switcher">
                        <span 
                            class=${classMap({ 'lang-option': true, active: uiLocale === 'en' })}
                            @click=${() => void this._setLang('en')}
                        >en</span>
                        <span class="lang-separator">|</span>
                        <span 
                            class=${classMap({ 'lang-option': true, active: uiLocale === 'ru' })}
                            @click=${() => void this._setLang('ru')}
                        >ru</span>
                    </div>
                    
                    ${this.isAuthenticated
                        ? html`<a href="/dashboard" class="dashboard-btn" @click=${this._handleNavClick}>${h('dashboard')}</a>`
                        : html`<button class="login-btn" @click=${this._handleLoginClick}>${h('login')}</button>`
                    }
                    
                    <button 
                        class=${classMap({ burger: true, active: this.mobileMenuOpen })}
                        @click=${this._toggleMobileMenu}
                        aria-label=${h('mobile_nav_aria')}
                    >
                        <span class="burger-line"></span>
                        <span class="burger-line"></span>
                        <span class="burger-line"></span>
                    </button>
                </div>
            </header>
            
            <div
                class=${classMap({ 'mobile-menu': true, active: this.mobileMenuOpen })}
                @click=${this._onMobileMenuShellClick}
            >
                <a href="#about" class="nav-link" @click=${this._handleNavClick}>${h('anchor_about')}</a>
                <a href="#abilities" class="nav-link" @click=${this._handleNavClick}>${h('features')}</a>
                
                <div class="mobile-products-group">
                    <span class="mobile-products-title">${h('solutions')}</span>
                    <a href="/products/agents" class="mobile-product-link" @click=${this._handleNavClick}>
                        <div class="mobile-product-icon">
                            <img src="/static/core/assets/service_logos/agents_logo.svg" alt=${h('product_agents_title')} />
                        </div>
                        ${h('product_agents_title')}
                    </a>
                    <a href="/products/rag" class="mobile-product-link" @click=${this._handleNavClick}>
                        <div class="mobile-product-icon">
                            <img src="/static/core/assets/service_logos/rag_logo.svg" alt=${h('product_rag_title')} />
                        </div>
                        ${h('product_rag_title')}
                    </a>
                    <a href="/products/crm" class="mobile-product-link" @click=${this._handleNavClick}>
                        <div class="mobile-product-icon">
                            <img src="/static/core/assets/service_logos/crm_logo.svg" alt=${h('product_crm_title')} />
                        </div>
                        ${h('product_crm_title')}
                    </a>
                    <a href="/products/sync" class="mobile-product-link" @click=${this._handleNavClick}>
                        <div class="mobile-product-icon">
                            <img src="/static/core/assets/service_logos/sync_logo.svg" alt=${h('product_sync_title')} />
                        </div>
                        ${h('product_sync_title')}
                    </a>
                    <a href="/products/documents" class="mobile-product-link" @click=${this._handleNavClick}>
                        <div class="mobile-product-icon">
                            <img src="/static/core/assets/service_logos/documents_logo.svg" alt=${h('product_documents_title')} />
                        </div>
                        ${h('product_documents_title')}
                    </a>
                </div>
                
                <div class="mobile-menu-secondary">
                    <a href="/documentation" class="nav-link" @click=${this._handleNavClick}>${h('docs')}</a>
                    <a href="/support" class="nav-link" @click=${this._handleNavClick}>${h('support')}</a>
                    <a href="/blog" class="nav-link" @click=${this._handleNavClick}>${h('blog')}</a>
                    <a href="/about" class="nav-link" @click=${this._handleNavClick}>${h('company_page')}</a>
                    <a href="/roadmap" class="nav-link" @click=${this._handleNavClick}>${h('roadmap')}</a>
                </div>
                <div class="mobile-menu-footer">
                    ${this.isAuthenticated
                        ? html`<a href="/dashboard" class="dashboard-btn" @click=${this._handleNavClick}>${h('dashboard')}</a>`
                        : html`<button class="login-btn" @click=${() => {
                            this._closeMobileMenu();
                            this._handleLoginClick();
                        }}>${h('login')}</button>`}
                </div>
            </div>
        `;
    }
}

customElements.define('landing-header', LandingHeader);
