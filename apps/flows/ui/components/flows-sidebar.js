/**
 * FlowsSidebar — оболочка `platform-service-sidebar`; каталог flow’ов —
 * единый компонент `<flows-catalog-list>` (тот же, что на мобильной главной /flows).
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { sidebarStyles, sidebarNavItemStyles } from '@platform/lib/styles/shared/sidebar.styles.js';
import { readShellSidebarCollapsed } from '@platform/lib/utils/shell-sidebar-preference.js';
import '@platform/lib/components/layout/platform-service-sidebar.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-user.js';
import '@platform/lib/components/platform-notification-manager.js';
import '@platform/lib/components/platform-deployment-version.js';
import './flows-catalog-list.js';
import { isPlainObject } from '../_helpers/flows-resolvers.js';

export class FlowsSidebar extends PlatformElement {
    static properties = {
        collapsed: { type: Boolean, reflect: true },
        mobileOpen: { type: Boolean, reflect: true, attribute: 'mobile-open' },
    };

    static styles = [
        PlatformElement.styles,
        sidebarStyles,
        sidebarNavItemStyles,
        css`
            :host {
                display: block;
                height: 100%;
                flex-shrink: 0;
            }
            platform-service-sidebar {
                height: 100%;
            }
            flows-catalog-list {
                flex: 1;
                min-height: 0;
            }
            .home-link {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                width: calc(100% - var(--space-4));
                margin: var(--space-2) var(--space-2) var(--space-3);
                padding: var(--space-3);
                border-radius: var(--radius-md);
                border: 1px solid transparent;
                background: transparent;
                color: var(--text-secondary);
                cursor: pointer;
                font: inherit;
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                text-align: left;
                box-sizing: border-box;
                transition: background var(--duration-fast), border-color var(--duration-fast), color var(--duration-fast);
            }
            .home-link:hover {
                color: var(--text-primary);
                background: var(--glass-solid-medium);
                border-color: var(--glass-border-subtle);
            }
            .home-link[active] {
                color: var(--accent);
                background: var(--accent-subtle);
                border-color: var(--accent);
            }
            .home-link platform-icon {
                flex-shrink: 0;
            }
            platform-service-sidebar[collapsed] .home-link {
                justify-content: center;
                width: 40px;
                height: 40px;
                margin-inline: auto;
                padding: 0;
            }
            platform-service-sidebar[collapsed] .home-link span {
                display: none;
            }
        `,
    ];

    constructor() {
        super();
        this.collapsed = readShellSidebarCollapsed();
        this.mobileOpen = false;
        this._routeKeySel = this.select((s) => {
            const r = isPlainObject(s.router) && typeof s.router.routeKey === 'string' ? s.router.routeKey : '';
            return r;
        });
    }

    _shell() {
        return this.renderRoot?.querySelector('platform-service-sidebar');
    }

    toggleMobile() {
        this._shell()?.toggleMobile();
    }

    closeMobile() {
        this._shell()?.closeMobile();
    }

    _openHome() {
        this.navigate('list', {});
        this.closeMobile();
    }

    _onCatalogDismissMobile() {
        this.closeMobile();
    }

    render() {
        const routeKey = this._routeKeySel.value;

        return html`
            <platform-service-sidebar
                logo-src="/static/core/assets/service_logos/agents_logo.svg"
                logo-text="Flows"
                ?logo-opens-services=${true}
                ?collapsed=${this.collapsed}
                ?mobile-open=${this.mobileOpen}
                @collapse-change=${(e) => { this.collapsed = e.detail.collapsed; }}
                @mobile-change=${(e) => { this.mobileOpen = e.detail.open; }}
            >
                <button
                    type="button"
                    class="home-link"
                    ?active=${routeKey === 'list'}
                    title=${this.t('flows_sidebar.home_title')}
                    @click=${this._openHome}
                >
                    <platform-icon name="apps" size="18"></platform-icon>
                    <span>${this.t('flows_sidebar.home')}</span>
                </button>
                <flows-catalog-list
                    mode="sidebar"
                    .collapsedSidebar=${this.collapsed}
                    @flows-catalog-dismiss-mobile=${this._onCatalogDismissMobile}
                ></flows-catalog-list>
                <div slot="footer">
                    <platform-user block>
                        <platform-notification-manager slot="user-toolbar"></platform-notification-manager>
                    </platform-user>
                    <platform-deployment-version base-url="/flows" footer></platform-deployment-version>
                </div>
            </platform-service-sidebar>
        `;
    }
}

customElements.define('flows-sidebar', FlowsSidebar);
