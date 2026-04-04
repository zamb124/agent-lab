/**
 * PlatformServiceSidebar — единая оболочка shell-сайдбара сервисов.
 * Делегирует разметку и поведение в platform-sidebar; отражает collapsed / mobile-open на хосте для стилей приложения.
 *
 * Слоты (пробрасываются в platform-sidebar): header, default (nav), footer.
 * Слот logo пробрасывается только если у хоста есть дочерний узел со slot="logo" (иначе пустой <slot> ломал бы logo-src/logo-text).
 * События: collapse-change, mobile-change (проброс с внутреннего platform-sidebar).
 *
 * Методы: toggleMobile(), closeMobile() — для вызова из родительского App (меню).
 */
import { html, css } from 'lit';
import { PlatformElement } from '../../platform-element/index.js';
import './platform-sidebar.js';

export class PlatformServiceSidebar extends PlatformElement {
    static properties = {
        collapsed: { type: Boolean, reflect: true },
        mobileOpen: { type: Boolean, reflect: true, attribute: 'mobile-open' },
        logoSrc: { type: String, attribute: 'logo-src' },
        logoText: { type: String, attribute: 'logo-text' },
        width: { type: String },
        collapsedWidth: { type: String, attribute: 'collapsed-width' },
        mobileBreakpoint: { type: Number, attribute: 'mobile-breakpoint' },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                height: 100%;
            }
            platform-sidebar {
                height: 100%;
            }
        `,
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
    }

    _innerSidebar() {
        return this.renderRoot?.querySelector('platform-sidebar') ?? null;
    }

    toggleMobile() {
        this._innerSidebar()?.toggleMobile();
    }

    closeMobile() {
        this._innerSidebar()?.closeMobile();
    }

    _onCollapseChange(e) {
        e.stopPropagation();
        const next = e.detail?.collapsed;
        if (typeof next !== 'boolean') {
            throw new Error('platform-sidebar collapse-change: expected detail.collapsed boolean');
        }
        this.collapsed = next;
        this.emit('collapse-change', { collapsed: next });
    }

    _onMobileChange(e) {
        e.stopPropagation();
        const open = e.detail?.open;
        if (typeof open !== 'boolean') {
            throw new Error('platform-sidebar mobile-change: expected detail.open boolean');
        }
        this.mobileOpen = open;
        this.emit('mobile-change', { open });
    }

    _userLogoSlotPresent() {
        return Array.from(this.children).some((n) => n.getAttribute?.('slot') === 'logo');
    }

    render() {
        const logoBridge = this._userLogoSlotPresent()
            ? html`<slot name="logo" slot="logo"></slot>`
            : null;
        return html`
            <platform-sidebar
                logo-src=${this.logoSrc}
                logo-text=${this.logoText}
                width=${this.width}
                collapsed-width=${this.collapsedWidth}
                mobile-breakpoint=${this.mobileBreakpoint}
                ?collapsed=${this.collapsed}
                ?mobile-open=${this.mobileOpen}
                @collapse-change=${this._onCollapseChange}
                @mobile-change=${this._onMobileChange}
            >
                ${logoBridge}
                <slot name="header" slot="header"></slot>
                <slot></slot>
                <slot name="footer" slot="footer"></slot>
            </platform-sidebar>
        `;
    }
}

customElements.define('platform-service-sidebar', PlatformServiceSidebar);
