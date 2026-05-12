/**
 * PlatformSidebar — унифицированный desktop-сайдбар сервиса.
 *
 * Поддержка collapsed mode (только иконки). Transparent design — использует slots для кастомизации.
 *
 * Mobile shell 2026: на ширине <= 767px хост скрыт (`display: none` в sidebar.styles.js).
 * Первичная навигация на мобиле — <platform-bottom-nav> + <platform-top-bar>,
 * вторичная — <platform-bottom-sheet>. `mobile-open`/`UI_SIDEBAR_*` живут только
 * для совместимости (no-op на мобиле); код будет упразднён при следующем рефакторинге.
 */
import { html, css } from 'lit';
import { PlatformElement } from '../../platform-element/index.js';
import { CoreEvents } from '../../events/contract.js';
import { sidebarHostStyles, sidebarStyles } from '../../styles/shared/sidebar.styles.js';
import '../platform-icon.js';
import '../platform-deployment-version.js';

export class PlatformSidebar extends PlatformElement {
    static properties = {
        collapsed: { type: Boolean, reflect: true },
        mobileOpen: { type: Boolean, reflect: true, attribute: 'mobile-open' },
        logoSrc: { type: String, attribute: 'logo-src' },
        logoText: { type: String, attribute: 'logo-text' },
        /** Клик по блоку лого (иконка + название) открывает витрину `platform.services`. */
        logoOpensServices: { type: Boolean, attribute: 'logo-opens-services' },
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
        this.logoOpensServices = false;
        this.width = '280px';
        this.collapsedWidth = '72px';
        this.mobileBreakpoint = 768;
        this._isMobile = false;
        this._resizeObserver = null;
        this._boundKeyHandler = this._handleKeyDown.bind(this);
    }

    connectedCallback() {
        super.connectedCallback();
        this._checkMobile();
        this._setupResizeObserver();
        document.addEventListener('keydown', this._boundKeyHandler);
        /*
         * Mobile shell 2026: на мобиле сайдбар скрыт CSS'ом (display:none). Подписки на
         * UI_SIDEBAR_* оставлены для desktop-режимов (collapsed/expanded), но команды
         * mobileOpen игнорируются при `_isMobile` — drawer'а нет.
         */
        this.useEvent(CoreEvents.UI_SIDEBAR_OPEN_REQUESTED, () => {
            if (this._isMobile) return;
        });
        this.useEvent(CoreEvents.UI_SIDEBAR_CLOSE_REQUESTED, () => {
            if (this._isMobile) return;
            if (this.mobileOpen) {
                this.mobileOpen = false;
                this._notifyMobileChange(false);
            }
        });
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._resizeObserver?.disconnect();
        document.removeEventListener('keydown', this._boundKeyHandler);
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
        this.dispatch(CoreEvents.UI_SIDEBAR_COLLAPSE_CHANGED, { collapsed: this.collapsed });
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
        this.dispatch(CoreEvents.UI_SIDEBAR_MOBILE_CHANGED, { open });
        this.emit('mobile-change', { open });
    }

    _handleBackdropClick() {
        this.closeMobile();
    }

    _collapseLabel() {
        if (this._isMobile) {
            return '';
        }
        return this.collapsed
            ? (this.t('sidebar.expand') || 'Expand')
            : (this.t('sidebar.collapse') || 'Collapse');
    }

    _renderCollapseControl() {
        if (this._isMobile) {
            return null;
        }
        const label = this._collapseLabel();
        return html`
            <button
                type="button"
                class="collapse-btn"
                aria-label=${label}
                title=${label}
                aria-expanded=${String(!this.collapsed)}
                @click=${this.toggleCollapse}
            >
                <platform-icon
                    name=${this.collapsed ? 'chevron-right' : 'chevron-left'}
                    size="18"
                ></platform-icon>
            </button>
        `;
    }

    _inlineCollapseIfExpanded() {
        if (this._isMobile || this.collapsed) {
            return null;
        }
        return this._renderCollapseControl();
    }

    _renderCollapseRowBetweenLogoAndNav() {
        if (this._isMobile || !this.collapsed) {
            return null;
        }
        return html`
            <div class="sidebar-collapse-row">${this._renderCollapseControl()}</div>
        `;
    }

    _onLogoServicesClick(e) {
        e.stopPropagation();
        this.openModal('platform.services', {});
        if (this.mobileOpen) {
            this.closeMobile();
        }
    }

    _renderLogo() {
        const hasLogoSlot = this.querySelector('[slot="logo"]');

        if (hasLogoSlot) {
            return html`
                <div class="sidebar-logo sidebar-logo--slot">
                    <slot name="logo"></slot>
                    ${this._inlineCollapseIfExpanded()}
                </div>
            `;
        }

        const ariaLabel = this.t('services_switch.aria', null, 'platform');
        const logoBody = html`
            ${this.logoSrc
                ? html`
                    <div class="sidebar-logo-icon">
                        <img src="${this.logoSrc}" alt="">
                    </div>
                `
                : ''}
            ${this.logoText
                ? html`<span class="sidebar-logo-text">${this.logoText}</span>`
                : ''}
        `;

        if (this.logoOpensServices && (this.logoSrc || this.logoText)) {
            return html`
                <div class="sidebar-logo">
                    <button
                        type="button"
                        class="sidebar-logo-hit"
                        aria-label=${ariaLabel}
                        @click=${this._onLogoServicesClick}
                    >
                        ${logoBody}
                    </button>
                    ${this._inlineCollapseIfExpanded()}
                </div>
            `;
        }

        return html`
            <div class="sidebar-logo">
                ${logoBody}
                ${this._inlineCollapseIfExpanded()}
            </div>
        `;
    }

    render() {
        return html`
            <div class="mobile-backdrop" @click=${this._handleBackdropClick}></div>
            <div class="sidebar-content">
                ${this._renderLogo()}
                ${this._renderCollapseRowBetweenLogoAndNav()}
                <div class="sidebar-header">
                    <slot name="header"></slot>
                </div>
                <nav class="sidebar-nav">
                    <slot></slot>
                </nav>
            </div>
            <div class="sidebar-footer">
                <slot name="footer"></slot>
            </div>
        `;
    }
}

customElements.define('platform-sidebar', PlatformSidebar);
