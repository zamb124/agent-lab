/**
 * Шапка лендинга — шапка лендинга с навигацией
 */
import { html, css } from 'lit';
import { classMap } from 'lit/directives/class-map.js';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

import { isAllowedLandingScrollSectionId, storePendingLandingSectionTarget } from './landing-section-scroll.js';
import { getPlatformBrandBootstrap } from '@platform/lib/utils/platform-brand.js';
import type {CSSResultGroup, PropertyDeclarations, TemplateResult} from 'lit';
import type { SelectController } from '@platform/lib/events/select-controller.js';

const INTERNAL_HREF_TO_ROUTE = Object.freeze({
    '/': 'landing',
    '/products/agents':    'product-agents',
    '/products/rag':       'product-rag',
    '/products/crm':       'product-crm',
    '/products/sync':      'product-sync',
    '/products/documents': 'product-documents',
    '/products/geo':       'product-geo',
    '/products/wiki':      'product-wiki',
    '/products/shop':      'product-shop',
    '/support':            'support',
    '/dashboard':          'dashboard',
    '/blog':               'blog',
    '/about':              'about',
    '/roadmap':            'roadmap',
});

function hasOwnKey<T extends object>(catalog: T, key: string): key is Extract<keyof T, string> {
    return Object.prototype.hasOwnProperty.call(catalog, key);
}

export class LandingHeader extends PlatformElement {
    static i18nNamespace = 'landing';

    static override styles: CSSResultGroup = [
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
                background: var(--marketing-header-bg);
                backdrop-filter: blur(10px);
                border-bottom: 1px solid var(--glass-border-medium);
            }
            
            .header-container {
                max-width: 1440px;
                width: 100%;
                min-width: 0;
                margin: 0 auto;
                padding-block: max(20px, var(--platform-safe-top)) max(20px, var(--platform-safe-bottom));
                padding-inline: max(
                    20px,
                    var(--platform-safe-left),
                    var(--platform-safe-right)
                );
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
                flex: 0 0 auto;
                overflow: visible;
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
                font-family: var(--font-sans); letter-spacing: var(--tracking-tight);
                font-size: 18px;
                font-weight: 500;
                color: var(--text-secondary);
                overflow: hidden;
                text-overflow: ellipsis;
            }

            .logo-wordmark {
                height: 40px;
                width: auto;
                object-fit: contain;
                display: block;
                flex: 0 0 auto;
                filter: none;
            }
            
            .nav {
                display: none;
                align-items: center;
                gap: clamp(16px, 1.5vw, 24px);
                flex: 0 1 auto;
                margin: 0 auto;
            }
            
            .nav-link {
                font-family: var(--font-sans);
                font-size: 16px;
                text-decoration: none;
                transition: color 0.3s;
                white-space: nowrap;
            }

            /* PlatformElement has a more specific :any-link rule inside Shadow DOM. */
            .nav a.nav-link:any-link,
            button.nav-dropdown-trigger {
                color: var(--text-secondary);
                font-size: 14px;
                letter-spacing: 0.06em;
                text-transform: uppercase;
            }

            .nav a.nav-link:any-link:hover,
            button.nav-dropdown-trigger:hover {
                color: var(--accent);
            }

            .nav-dropdown {
                position: relative;
            }
            
            button.nav-dropdown-trigger {
                display: flex;
                align-items: center;
                gap: 6px;
                font-family: var(--font-sans);
                font-weight: 400;
                text-decoration: none;
                transition: color 0.3s;
                white-space: nowrap;
                cursor: pointer;
                background: none;
                border: none;
                padding: 0;
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
                transform: translateX(-50%) translateY(8px) scale(0.97);
                transform-origin: top center;
                margin-top: 16px;
                min-width: 620px;
                max-width: calc(100vw - 48px);
                background: var(--glass-solid-strong);
                backdrop-filter: blur(24px);
                border: 1px solid var(--glass-border-medium);
                border-radius: var(--radius-lg, 16px);
                padding: 14px;
                display: none;
                grid-template-columns: repeat(4, 1fr);
                gap: 8px;
                box-shadow: var(--glass-shadow-strong), 0 0 40px rgba(61, 220, 255, 0.08);
                max-height: calc(100vh - 96px);
                overflow-y: auto;
                opacity: 0;
            }

            .nav-dropdown.open .nav-dropdown-menu {
                display: grid;
                animation: nav-menu-in 0.32s cubic-bezier(0.22, 1.4, 0.36, 1) forwards;
            }

            @keyframes nav-menu-in {
                to {
                    opacity: 1;
                    transform: translateX(-50%) translateY(0) scale(1);
                }
            }

            .nav-dropdown-item {
                position: relative;
                display: flex;
                flex-direction: column;
                align-items: flex-start;
                gap: 10px;
                padding: 16px 14px;
                color: var(--text-secondary);
                text-decoration: none;
                border-radius: var(--radius-md, 12px);
                border: 1px solid transparent;
                background: color-mix(in srgb, var(--glass-bg-subtle, rgba(10, 16, 28, 0.5)) 60%, transparent);
                overflow: hidden;
                transition: var(--motion-transition-interactive);
                opacity: 0;
            }

            .nav-dropdown.open .nav-dropdown-item {
                animation: nav-tile-in 0.4s cubic-bezier(0.22, 1.3, 0.36, 1) forwards;
            }

            .nav-dropdown.open .nav-dropdown-item:nth-child(1) { animation-delay: 0.02s; }
            .nav-dropdown.open .nav-dropdown-item:nth-child(2) { animation-delay: 0.05s; }
            .nav-dropdown.open .nav-dropdown-item:nth-child(3) { animation-delay: 0.08s; }
            .nav-dropdown.open .nav-dropdown-item:nth-child(4) { animation-delay: 0.11s; }
            .nav-dropdown.open .nav-dropdown-item:nth-child(5) { animation-delay: 0.14s; }
            .nav-dropdown.open .nav-dropdown-item:nth-child(6) { animation-delay: 0.17s; }
            .nav-dropdown.open .nav-dropdown-item:nth-child(7) { animation-delay: 0.20s; }
            .nav-dropdown.open .nav-dropdown-item:nth-child(8) { animation-delay: 0.23s; }

            @keyframes nav-tile-in {
                from {
                    opacity: 0;
                    transform: translateY(10px) scale(0.94);
                }
                to {
                    opacity: 1;
                    transform: translateY(0) scale(1);
                }
            }

            .nav-dropdown-item::before {
                content: '';
                position: absolute;
                inset: 0;
                border-radius: inherit;
                background: radial-gradient(
                    120px circle at var(--tile-glow-x, 50%) var(--tile-glow-y, 0%),
                    rgba(61, 220, 255, 0.14),
                    transparent 70%
                );
                opacity: 0;
                transition: opacity 0.3s ease;
                pointer-events: none;
            }

            .nav-dropdown-item:hover {
                border-color: color-mix(in srgb, var(--accent) 40%, transparent);
                color: var(--text-primary);
                transform: translateY(-3px);
                box-shadow: 0 8px 28px rgba(3, 5, 8, 0.5), 0 0 24px rgba(61, 220, 255, 0.14);
            }

            .nav-dropdown-item:hover::before {
                opacity: 1;
            }

            .nav-dropdown-item-icon {
                width: 34px;
                height: 34px;
                flex-shrink: 0;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: 10px;
                background: color-mix(in srgb, var(--accent) 10%, transparent);
                border: 1px solid color-mix(in srgb, var(--accent) 18%, transparent);
                transition: var(--motion-transition-interactive);
            }

            .nav-dropdown-item-icon img {
                width: 22px;
                height: 22px;
                object-fit: contain;
            }

            .nav-dropdown-item:hover .nav-dropdown-item-icon {
                background: color-mix(in srgb, var(--accent) 20%, transparent);
                border-color: color-mix(in srgb, var(--accent) 45%, transparent);
                box-shadow: 0 0 16px rgba(61, 220, 255, 0.35);
                transform: scale(1.06);
            }

            .nav-dropdown-item-content {
                display: flex;
                flex-direction: column;
                gap: 3px;
            }

            .nav-dropdown-item-title {
                font-family: var(--font-sans);
                font-size: 14px;
                font-weight: 600;
                color: var(--text-primary);
                letter-spacing: -0.01em;
            }

            .nav-dropdown-item-desc {
                font-family: var(--font-sans);
                font-size: 11px;
                line-height: 1.4;
                color: var(--text-tertiary, var(--text-secondary));
            }

            @media (max-width: 1400px) {
                .nav-dropdown-menu {
                    min-width: 480px;
                    grid-template-columns: repeat(2, 1fr);
                }
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
                color: var(--text-secondary);
                font-family: var(--font-sans);
                font-size: 14px;
            }
            
            .lang-option {
                border: 0;
                background: transparent;
                padding: 4px 8px;
                color: var(--text-secondary);
                font: inherit;
                cursor: pointer;
                transition: color 0.3s;
            }
            
            .lang-option.active {
                color: var(--text-secondary);
            }
            
            .lang-option:hover {
                color: var(--accent);
            }
            
            .lang-separator {
                color: var(--text-disabled);
            }

            .theme-toggle {
                width: 34px;
                height: 34px;
                border: 1px solid var(--glass-border-medium);
                border-radius: 50%;
                display: grid;
                place-items: center;
                color: var(--text-secondary);
                background: var(--glass-bg-subtle);
                cursor: pointer;
                transition: var(--motion-transition-interactive);
            }

            .theme-toggle:hover {
                color: var(--accent);
                border-color: var(--accent);
                transform: translateY(-1px);
            }
            
            .login-btn {
                display: flex;
                padding: 8px 20px;
                background: var(--platform-btn-primary-bg);
                border: none;
                border-radius: 0;
                clip-path: var(--marketing-cosmic-btn-clip);
                color: var(--platform-btn-primary-text);
                font-family: var(--font-sans);
                font-size: 14px;
                font-weight: 500;
                cursor: pointer;
                transition: background 0.3s;
                white-space: nowrap;
            }

            .login-btn:hover {
                background: var(--platform-btn-primary-bg-hover);
            }

            .dashboard-btn {
                display: flex;
                padding: 8px 20px;
                background: transparent;
                border: 1px solid var(--accent);
                border-radius: 0;
                clip-path: var(--marketing-cosmic-btn-clip);
                color: var(--text-secondary);
                font-family: var(--font-sans);
                font-size: 14px;
                font-weight: 500;
                cursor: pointer;
                transition: var(--motion-transition-interactive);
                white-space: nowrap;
                text-decoration: none;
            }
            
            .dashboard-btn:hover {
                background: var(--accent);
                color: var(--text-on-accent);
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
                background: var(--text-secondary);
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
                top: var(--marketing-header-height);
                box-sizing: border-box;
                padding: clamp(16px, 4vw, 28px) clamp(16px, 5vw, 24px) max(24px, env(safe-area-inset-bottom));
                flex-direction: column;
                align-items: stretch;
                gap: clamp(12px, 3vw, 20px);
                z-index: 10000;
                background: var(--marketing-cosmic-bg, var(--marketing-page-bg));
                overflow-y: auto;
                -webkit-overflow-scrolling: touch;
                min-height: calc(100vh - var(--marketing-header-height));
                min-height: calc(100dvh - var(--marketing-header-height));
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
                    padding-block: max(16px, var(--platform-safe-top)) max(16px, var(--platform-safe-bottom));
                    padding-inline: max(
                        12px,
                        var(--platform-safe-left),
                        var(--platform-safe-right)
                    );
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
                
                .lang-switcher {
                    display: flex;
                }
                
                .login-btn,
                .dashboard-btn {
                    display: block;
                }
            }
            
            @media (min-width: 1500px) {
                .nav {
                    display: flex;
                }
                
                .burger {
                    display: none;
                }
            }
            
            /*
             * The expanded navigation needs more than a 1440px viewport in RU.
             * Enabling it earlier makes the non-wrapping links push actions off-screen.
             */
            @media (min-width: 1800px) {
                .header-container {
                    max-width: 1680px;
                    padding: 30px 56px;
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
                    gap: 26px;
                }
                
                .nav a.nav-link:any-link,
                button.nav-dropdown-trigger {
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
                border-top: 1px solid var(--glass-border-medium);
            }
            
            .mobile-products-title {
                font-family: var(--font-sans);
                font-size: 12px;
                color: var(--text-disabled);
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
                color: var(--text-secondary);
                text-decoration: none;
                font-family: var(--font-sans);
                font-size: clamp(16px, 4.2vw, 18px);
                border-radius: 8px;
                transition: background 0.2s;
                justify-content: flex-start;
                box-sizing: border-box;
                width: 100%;
                min-height: 48px;
            }
            
            .mobile-product-link:hover {
                background: color-mix(in srgb, var(--accent) 15%, transparent);
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
                border-top: 1px solid var(--glass-border-medium);
            }
        `
    ];

    static override properties: PropertyDeclarations = {
        mobileMenuOpen: { type: Boolean },
        productsDropdownOpen: { type: Boolean }
    }
    declare mobileMenuOpen: boolean;
    declare productsDropdownOpen: boolean;
    private _headerResizeObserver: ResizeObserver | null = null;
;

    constructor() {
        super();
        this.mobileMenuOpen = false;
        this.productsDropdownOpen = false;
        this._authSel = this.select((s) => ({ status: s.auth.status, user: s.auth.user }));
        this._localeSel = this.select((s) => s.i18n.locale);
        this._themeSel = this.select((s) => s.theme.mode);
    }
    private _authSel: SelectController<any>;
    private _localeSel: SelectController<any>;
    private _themeSel: SelectController<any>;


    get isAuthenticated() {
        const v = this._authSel.value;
        return !!(v && v.status === 'authenticated');
    }

    get user() {
        const v = this._authSel.value;
        if (!v || !v.user) return null;
        if (v.user.raw) return v.user.raw;
        return v.user;
    }

    _lt(key: string) {
        return this.t(key);
    }

    _toggleMobileMenu() {
        this.mobileMenuOpen = !this.mobileMenuOpen;
    }

    _closeMobileMenu() {
        this.mobileMenuOpen = false;
    }

    _onMobileMenuShellClick(e: Event) {
        if (e.target === e.currentTarget) {
            this._closeMobileMenu();
        }
    }

    _onHeaderBarClick(e: Event) {
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

    _setLang(lang: string) {
        if (lang !== 'ru' && lang !== 'en') {
            throw new Error(`LandingHeader._setLang: invalid locale "${lang}"`);
        }
        if (this._localeSel.value === lang) {
            return;
        }
        this.setLocale(lang);
    }

    _toggleTheme() {
        const mode = this._themeSel.value;
        if (mode !== 'dark' && mode !== 'light') {
            throw new Error(`LandingHeader._toggleTheme: invalid theme "${mode}"`);
        }
        this.setTheme(mode === 'dark' ? 'light' : 'dark');
    }

    _navigateRoute(routeKey: string) {
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

    _scrollToLandingSection(sectionId: string) {
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

    _handleNavClick(e: Event) {
        const target = e.currentTarget;
        if (!(target instanceof Element)) {
            throw new Error('landing-header: nav click target required');
        }
        const href = target.getAttribute('href');
        if (typeof href === 'string' && href.startsWith('#')) {
            e.preventDefault();
            const sectionId = href.slice(1);
            if (this._resolveLandingPage()) {
                this._scrollToLandingSection(sectionId);
            } else if (isAllowedLandingScrollSectionId(sectionId)) {
                storePendingLandingSectionTarget(sectionId);
                this.navigate('landing');
            }
        } else if (typeof href === 'string' && hasOwnKey(INTERNAL_HREF_TO_ROUTE, href)) {
            e.preventDefault();
            this._navigateRoute(INTERNAL_HREF_TO_ROUTE[href]);
        }
        this._closeMobileMenu();
        this._closeProductsDropdown();
    }

    _toggleProductsDropdown(e: Event) {
        e.preventDefault();
        e.stopPropagation();
        this.productsDropdownOpen = !this.productsDropdownOpen;
    }

    _closeProductsDropdown() {
        this.productsDropdownOpen = false;
    }

    _onDropdownPointerMove(e: PointerEvent) {
        const item = (e.target as Element).closest?.('.nav-dropdown-item');
        if (!(item instanceof HTMLElement)) return;
        const r = item.getBoundingClientRect();
        item.style.setProperty('--tile-glow-x', `${e.clientX - r.left}px`);
        item.style.setProperty('--tile-glow-y', `${e.clientY - r.top}px`);
    }

    override connectedCallback(): void {
        super.connectedCallback();
        this._handleOutsideClick = this._handleOutsideClick.bind(this);
        this._syncLandingHeaderHeight = this._syncLandingHeaderHeight.bind(this);
        this.useDomEvent(document, 'click', this._handleOutsideClick);
    }

    override firstUpdated() {
        this._headerResizeObserver = new ResizeObserver(() => {
            this._syncLandingHeaderHeight();
        });
        this._headerResizeObserver.observe(this);
        this._syncLandingHeaderHeight();
    }

    override disconnectedCallback(): void {
        if (this._headerResizeObserver !== null) {
            this._headerResizeObserver.disconnect();
            this._headerResizeObserver = null;
        }
        super.disconnectedCallback();
    }

    _syncLandingHeaderHeight() {
        const headerHeightPx = Math.ceil(this.getBoundingClientRect().height);
        if (headerHeightPx <= 0) {
            throw new Error('landing-header: header height must be positive');
        }
        document.documentElement.style.setProperty('--landing-header-height', `${headerHeightPx}px`);
    }

    _handleOutsideClick(e: Event) {
        const path = e.composedPath();
        const dropdown = this.shadowRoot?.querySelector('.nav-dropdown');
        if (dropdown && !path.includes(dropdown)) {
            this._closeProductsDropdown();
        }
    }

    _handleLoginClick() {
        this.openModal('auth.login');
    }

    override render(): TemplateResult {
        const uiLocale = this._localeSel.value;
        const themeMode = this._themeSel.value;
        if (themeMode !== 'dark' && themeMode !== 'light') {
            throw new Error(`LandingHeader.render: invalid theme "${themeMode}"`);
        }
        const h = (sub: string) => this._lt(`header.${sub}`);
        const brand = getPlatformBrandBootstrap();
        if (!brand) {
            throw new Error('landing-header: platform brand bootstrap required');
        }
        return html`
            <header class="header-container" @click=${this._onHeaderBarClick}>
                <a href="/" class="logo" @click=${this._closeMobileMenu}>
                    <img class="logo-wordmark" src="/static/core/assets/service_logos/linnex_test.png" alt="${brand.platformName}" />
                </a>
                
                <nav class="nav">
                    <a href="#about" class="nav-link" @click=${this._handleNavClick}>${h('anchor_about')}</a>
                    <a href="#abilities" class="nav-link" @click=${this._handleNavClick}>${h('features')}</a>
                    <div class=${classMap({ 'nav-dropdown': true, 'open': this.productsDropdownOpen })}>
                        <button class="nav-dropdown-trigger" @click=${this._toggleProductsDropdown}>
                            ${h('solutions')}
                            <platform-icon name="arrow-down" size="12"></platform-icon>
                        </button>
                        <div class="nav-dropdown-menu" @pointermove=${this._onDropdownPointerMove}>
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
                            <a href="/products/wiki" class="nav-dropdown-item" @click=${this._handleNavClick}>
                                <div class="nav-dropdown-item-icon">
                                    <img src="/static/core/assets/service_logos/wiki_logo.svg" alt=${h('product_wiki_title')} />
                                </div>
                                <div class="nav-dropdown-item-content">
                                    <span class="nav-dropdown-item-title">${h('product_wiki_title')}</span>
                                    <span class="nav-dropdown-item-desc">${h('product_wiki_desc')}</span>
                                </div>
                            </a>
                            <a href="/products/shop" class="nav-dropdown-item" @click=${this._handleNavClick}>
                                <div class="nav-dropdown-item-icon">
                                    <img src="/static/core/assets/service_logos/shop_logo.svg" alt=${h('product_shop_title')} />
                                </div>
                                <div class="nav-dropdown-item-content">
                                    <span class="nav-dropdown-item-title">${h('product_shop_title')}</span>
                                    <span class="nav-dropdown-item-desc">${h('product_shop_desc')}</span>
                                </div>
                            </a>
                            <a href="/products/geo" class="nav-dropdown-item" @click=${this._handleNavClick}>
                                <div class="nav-dropdown-item-icon">
                                    <img src="/static/core/assets/service_logos/geo_logo.svg" alt=${h('product_geo_title')} />
                                </div>
                                <div class="nav-dropdown-item-content">
                                    <span class="nav-dropdown-item-title">${h('product_geo_title')}</span>
                                    <span class="nav-dropdown-item-desc">${h('product_geo_desc')}</span>
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
                        <button
                            type="button"
                            class=${classMap({ 'lang-option': true, active: uiLocale === 'en' })}
                            @click=${() => void this._setLang('en')}
                        >en</button>
                        <span class="lang-separator">|</span>
                        <button
                            type="button"
                            class=${classMap({ 'lang-option': true, active: uiLocale === 'ru' })}
                            @click=${() => void this._setLang('ru')}
                        >ru</button>
                    </div>

                    <button
                        class="theme-toggle"
                        type="button"
                        title=${themeMode === 'dark' ? h('theme_light') : h('theme_dark')}
                        aria-label=${themeMode === 'dark' ? h('theme_light') : h('theme_dark')}
                        @click=${this._toggleTheme}
                    >
                        <platform-icon name=${themeMode === 'dark' ? 'sun' : 'moon'} size="17"></platform-icon>
                    </button>
                    
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
                    <a href="/products/wiki" class="mobile-product-link" @click=${this._handleNavClick}>
                        <div class="mobile-product-icon">
                            <img src="/static/core/assets/service_logos/wiki_logo.svg" alt=${h('product_wiki_title')} />
                        </div>
                        ${h('product_wiki_title')}
                    </a>
                    <a href="/products/shop" class="mobile-product-link" @click=${this._handleNavClick}>
                        <div class="mobile-product-icon">
                            <img src="/static/core/assets/service_logos/shop_logo.svg" alt=${h('product_shop_title')} />
                        </div>
                        ${h('product_shop_title')}
                    </a>
                    <a href="/products/geo" class="mobile-product-link" @click=${this._handleNavClick}>
                        <div class="mobile-product-icon">
                            <img src="/static/core/assets/service_logos/geo_logo.svg" alt=${h('product_geo_title')} />
                        </div>
                        ${h('product_geo_title')}
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
