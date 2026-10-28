/**
 * FlowsSidebar — оболочка `platform-service-sidebar`; каталог flow’ов —
 * единый компонент `<flows-catalog-list>` (тот же, что на мобильной главной /flows).
 */

import type { SelectController } from '@platform/lib/events/select-controller.js';
import { html, css, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { sidebarStyles, sidebarNavItemStyles } from '@platform/lib/styles/shared/sidebar.styles.js';
import { readShellSidebarCollapsed } from '@platform/lib/utils/shell-sidebar-preference.js';
import '@platform/lib/components/layout/platform-service-sidebar.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-user.js';
import '@platform/lib/components/platform-notification-manager.js';
import '@platform/lib/components/platform-deployment-version.js';
import './flows-catalog-list.js';
import { isPlainObject } from '../_helpers/flows-resolvers.js';
import { AGENT_SKILL_ICON } from '../_helpers/agent-skill-map.js';
import type {CSSResultGroup, PropertyDeclarations, TemplateResult} from 'lit';

export class FlowsSidebar extends PlatformElement {
    static override properties: PropertyDeclarations = {
        collapsed: { type: Boolean, reflect: true },
        mobileOpen: { type: Boolean, reflect: true, attribute: 'mobile-open' },
    }
    declare collapsed: boolean;
    declare mobileOpen: boolean;
;

    static override styles: CSSResultGroup = [
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
            .home-nav-row {
                display: flex;
                flex-direction: row;
                align-items: stretch;
                gap: var(--space-1);
                width: calc(100% - var(--space-4));
                margin: var(--space-2) var(--space-2) var(--space-3);
                box-sizing: border-box;
            }
            .home-nav {
                flex: 1;
                min-width: 0;
                margin: 0;
            }
            .home-nav-skills platform-icon {
                color: var(--accent);
            }
            platform-service-sidebar[collapsed] .home-nav-row {
                flex-direction: column;
                align-items: center;
                width: auto;
                margin-inline: auto;
            }
            platform-service-sidebar[collapsed] .home-nav {
                flex: 0 0 auto;
                width: auto;
            }
            platform-service-sidebar[collapsed] .home-nav-label {
                display: none;
            }
        `,
    ];
    private _routeKeySel: SelectController<string>;

    constructor() {
        super();
        this.collapsed = readShellSidebarCollapsed();
        this.mobileOpen = false;
        this._routeKeySel = this.select((s) => {
            const r = isPlainObject(s.router) && typeof (s as any).router.routeKey === 'string' ? (s as any).router.routeKey : '';
            return r;
        });
    }

    _shell() {
        return this.renderRoot?.querySelector('platform-service-sidebar');
    }

    toggleMobile() {
        (this._shell() as Record<string, any>)?.toggleMobile();
    }

    closeMobile() {
        (this._shell() as Record<string, any>)?.closeMobile();
    }

    _openHome() {
        this.navigate('list', {});
        this.closeMobile();
    }

    _onCatalogDismissMobile() {
        this.closeMobile();
    }

    override render(): TemplateResult {
        const routeKey = this._routeKeySel.value;

        return html`
            <platform-service-sidebar
                logo-src="/static/core/assets/service_logos/agents_logo.svg"
                logo-text="Flows"
                width="320px"
                ?logo-opens-services=${true}
                ?collapsed=${this.collapsed}
                ?mobile-open=${this.mobileOpen}
                @collapse-change=${(e: CustomEvent) => { this.collapsed = e.detail.collapsed; }}
                @mobile-change=${(e: CustomEvent) => { this.mobileOpen = e.detail.open; }}
            >
                <div class="home-nav-row">
                    <platform-button
                        class="home-nav"
                        variant=${routeKey === 'list' ? 'secondary' : 'ghost'}
                        density="compact"
                        ?icon-only=${this.collapsed}
                        aria-label=${this.t('flows_sidebar.home_title')}
                        @click=${this._openHome}
                    >
                        <platform-icon name="apps" size="18"></platform-icon>
                        ${this.collapsed ? nothing : html`<span class="home-nav-label">${this.t('flows_sidebar.home')}</span>`}
                    </platform-button>
                    <platform-button
                        class="home-nav home-nav-skills"
                        variant=${routeKey === 'agent_skills' ? 'secondary' : 'ghost'}
                        density="compact"
                        ?icon-only=${this.collapsed}
                        aria-label=${this.t('flows_sidebar.skills_title')}
                        @click=${() => { this.navigate('agent_skills'); this.closeMobile(); }}
                    >
                        <platform-icon name=${AGENT_SKILL_ICON} size="18"></platform-icon>
                        ${this.collapsed ? nothing : html`<span class="home-nav-label">${this.t('flows_sidebar.skills')}</span>`}
                    </platform-button>
                </div>
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
