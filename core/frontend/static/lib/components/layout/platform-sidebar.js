/**
 * PlatformSidebar - унифицированный компонент sidebar
 * Поддержка collapsed mode (только иконки) и mobile mode (slide-in overlay)
 * Transparent design - использует slots для кастомизации
 */
import { html, css } from 'lit';
import { PlatformElement } from '../../platform-element/index.js';
import { sidebarHostStyles, sidebarStyles } from '../../styles/shared/sidebar.styles.js';
import '../platform-icon.js';
import '../platform-deployment-version.js';

export class PlatformSidebar extends PlatformElement {
    static properties = {
        collapsed: { type: Boolean, reflect: true },
        mobileOpen: { type: Boolean, reflect: true, attribute: 'mobile-open' },
        logoSrc: { type: String, attribute: 'logo-src' },
        logoText: { type: String, attribute: 'logo-text' },
        width: { type: String },
        collapsedWidth: { type: String, attribute: 'collapsed-width' },
        mobileBreakpoint: { type: Number, attribute: 'mobile-breakpoint' },
        _isMobile: { type: Boolean, state: true },
    };

    static styles = [
        PlatformElement.styles,
        sidebarHostStyles,
        sidebarStyles,
        css`
            :host {
                --sidebar-width: var(--_sidebar-width, 280px);
                --sidebar-collapsed-width: var(--_sidebar-collapsed-width, 72px);
            }
        `
    ];

    constructor() {
        super();
        this.collapsed = false;
        this.mobileOpen = false;
        this.logoSrc = '';
        this.logoText = '';
        this.width = '280px';
        this.collapsedWidth = '72px';
        this.mobileBreakpoint = 768;
        this._isMobile = false;
        this._resizeObserver = null;
        this._boundKeyHandler = this._handleKeyDown.bind(this);
        this._boundOpenHandler = this._handleGlobalOpen.bind(this);
    }

    connectedCallback() {
        super.connectedCallback();
        this._checkMobile();
        this._setupResizeObserver();
        document.addEventListener('keydown', this._boundKeyHandler);
        // Слушаем глобальное событие открытия сайдбара от platform-island
        window.addEventListener('platform-sidebar-open', this._boundOpenHandler);
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._resizeObserver?.disconnect();
        document.removeEventListener('keydown', this._boundKeyHandler);
        window.removeEventListener('platform-sidebar-open', this._boundOpenHandler);
    }

    _handleGlobalOpen() {
        if (this._isMobile) {
            this.mobileOpen = true;
            this._notifyMobileChange(true);
        }
    }

    updated(changedProps) {
        super.updated(changedProps);
        
        if (changedProps.has('width')) {
            this.style.setProperty('--_sidebar-width', this.width);
        }
        if (changedProps.has('collapsedWidth')) {
            this.style.setProperty('--_sidebar-collapsed-width', this.collapsedWidth);
        }
    }

    _setupResizeObserver() {
        this._resizeObserver = new ResizeObserver(() => {
            this._checkMobile();
        });
        this._resizeObserver.observe(document.body);
    }

    _checkMobile() {
        const wasMobile = this._isMobile;
        this._isMobile = window.innerWidth < this.mobileBreakpoint;
        
        if (wasMobile && !this._isMobile) {
            this.mobileOpen = false;
        }
    }

    _handleKeyDown(e) {
        if (e.key === 'Escape' && this.mobileOpen) {
            this.closeMobile();
        }
    }

    toggleCollapse() {
        if (this._isMobile) return;
        
        this.collapsed = !this.collapsed;
        this.emit('collapse-change', { collapsed: this.collapsed });
    }

    toggleMobile() {
        this.mobileOpen = !this.mobileOpen;
        this._notifyMobileChange(this.mobileOpen);
    }

    closeMobile() {
        if (this.mobileOpen) {
            this.mobileOpen = false;
            this._notifyMobileChange(false);
        }
    }

    _notifyMobileChange(open) {
        this.emit('mobile-change', { open });
        // Глобальное событие для platform-sidebar-trigger
        window.dispatchEvent(new CustomEvent('platform-sidebar-mobile-change', {
            detail: { open },
        }));
    }

    _handleBackdropClick() {
        this.closeMobile();
    }

    _renderLogo() {
        const hasLogoSlot = this.querySelector('[slot="logo"]');
        
        if (hasLogoSlot) {
            return html`<slot name="logo"></slot>`;
        }

        const logoTitle = this._isMobile ? '' : (this.collapsed ? 'Развернуть сайдбар' : 'Свернуть сайдбар');
        return html`
            <div class="sidebar-logo">
                ${this.logoSrc ? html`
                    <div
                        class="sidebar-logo-icon ${this._isMobile ? '' : 'clickable'}"
                        @click=${this._isMobile ? null : this.toggleCollapse}
                        title=${logoTitle}
                    >
                        <img src="${this.logoSrc}" alt="${this.logoText || 'Logo'}">
                    </div>
                ` : ''}
                ${this.logoText ? html`
                    <span class="sidebar-logo-text">${this.logoText}</span>
                ` : ''}
            </div>
        `;
    }

    render() {
        return html`
            <div class="mobile-backdrop" @click=${this._handleBackdropClick}></div>
            
            <div class="sidebar-content">
                ${this._renderLogo()}
                
                <div class="sidebar-header">
                    <slot name="header"></slot>
                </div>
                
                <nav class="sidebar-nav">
                    <slot></slot>
                </nav>
                
                <div class="sidebar-footer">
                    <slot name="footer"></slot>
                </div>
            </div>
        `;
    }
}

customElements.define('platform-sidebar', PlatformSidebar);
