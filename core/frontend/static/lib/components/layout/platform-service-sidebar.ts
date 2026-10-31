/**
 * PlatformServiceSidebar — единая оболочка shell-сайдбара сервисов.
 * Делегирует разметку и поведение в platform-sidebar; отражает collapsed / mobile-open на хосте для стилей приложения.
 *
 * Слоты (пробрасываются в platform-sidebar): header, default (nav), footer.
 * Слот logo пробрасывается только если у хоста есть дочерний узел со slot="logo" (иначе пустой <slot> ломал бы logo-src/logo-text).
 * События: collapse-change, mobile-change (проброс с внутреннего platform-sidebar).
 * Десктоп collapsed: начальное значение и запись в localStorage — shell-sidebar-preference.
 *
 * Методы: toggleMobile(), closeMobile() — для вызова из родительского App (меню).
 */
import { html, css } from 'lit';
import type { CSSResultGroup, PropertyDeclarations, TemplateResult } from 'lit';
import { PlatformElement } from '../../platform-element/index.js';
import {
    readShellSidebarCollapsed,
    writeShellSidebarCollapsed,
} from '../../utils/shell-sidebar-preference.js';
import { PlatformSidebar } from './platform-sidebar.js';

export class PlatformServiceSidebar extends PlatformElement {
    static override properties: PropertyDeclarations = {
        collapsed: { type: Boolean, reflect: true },
        mobileOpen: { type: Boolean, reflect: true, attribute: 'mobile-open' },
        logoSrc: { type: String, attribute: 'logo-src' },
        logoText: { type: String, attribute: 'logo-text' },
        width: { type: String },
        collapsedWidth: { type: String, attribute: 'collapsed-width' },
        mobileBreakpoint: { type: Number, attribute: 'mobile-breakpoint' },
        logoOpensServices: { type: Boolean, attribute: 'logo-opens-services' },
    };

    declare collapsed: boolean;
    declare mobileOpen: boolean;
    declare logoSrc: string;
    declare logoText: string;
    declare width: string;
    declare collapsedWidth: string;
    declare mobileBreakpoint: number;
    declare logoOpensServices: boolean;

    static override styles: CSSResultGroup = [
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
        this.collapsed = readShellSidebarCollapsed();
        this.mobileOpen = false;
        this.logoSrc = '';
        this.logoText = '';
        this.width = '280px';
        this.collapsedWidth = '72px';
        this.mobileBreakpoint = 768;
        this.logoOpensServices = false;
    }

    _innerSidebar(): PlatformSidebar | null {
        const root = this.renderRoot;
        if (root === undefined || root === null) return null;
        const sidebar = root.querySelector('platform-sidebar');
        if (sidebar === null) return null;
        if (!(sidebar instanceof PlatformSidebar)) {
            throw new Error('platform-service-sidebar: inner sidebar must be platform-sidebar');
        }
        return sidebar;
    }

    toggleMobile(): void {
        this._innerSidebar()?.toggleMobile();
    }

    closeMobile(): void {
        this._innerSidebar()?.closeMobile();
    }

    _onCollapseChange(e: CustomEvent<{ collapsed?: unknown }>): void {
        e.stopPropagation();
        const next = e.detail?.collapsed;
        if (typeof next !== 'boolean') {
            throw new Error('platform-sidebar collapse-change: expected detail.collapsed boolean');
        }
        this.collapsed = next;
        writeShellSidebarCollapsed(next);
        this.emit('collapse-change', { collapsed: next });
    }

    _onMobileChange(e: CustomEvent<{ open?: unknown }>): void {
        e.stopPropagation();
        const open = e.detail?.open;
        if (typeof open !== 'boolean') {
            throw new Error('platform-sidebar mobile-change: expected detail.open boolean');
        }
        this.mobileOpen = open;
        this.emit('mobile-change', { open });
    }

    _userLogoSlotPresent(): boolean {
        return Array.from(this.children).some((n) => n instanceof Element && n.getAttribute('slot') === 'logo');
    }

    override render(): TemplateResult {
        const logoBridge = this._userLogoSlotPresent()
            ? html`<slot name="logo" slot="logo"></slot>`
            : null;
        return html`
            <platform-sidebar
                logo-src=${this.logoSrc}
                logo-text=${this.logoText}
                ?logo-opens-services=${this.logoOpensServices}
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
