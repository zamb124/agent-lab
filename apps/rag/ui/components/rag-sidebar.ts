/**
 * RagSidebar — навигация сервиса RAG.
 *
 * Active route подсвечивается по `state.router.routeKey`. Переходы — через
 * `this.navigate(routeKey)`. Триггерит первичную загрузку списка провайдеров
 * (`useResource('rag/providers')`) при монтировании; использует фабричный
 * `rag-provider-status` для отображения активного провайдера.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';
import type { OpController } from '@platform/lib/base/use-resource.js';
import { sidebarStyles, sidebarNavItemStyles } from '@platform/lib/styles/shared/sidebar.styles.js';
import { readShellSidebarCollapsed } from '@platform/lib/utils/shell-sidebar-preference.js';
import { PlatformServiceSidebar } from '@platform/lib/components/layout/platform-service-sidebar.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-user.js';
import '@platform/lib/components/platform-deployment-version.js';
import '@platform/lib/components/platform-notification-manager.js';
import './rag-provider-status.js';

const NAV_ITEMS = [
    { route: 'namespaces', icon: 'folder',   label_key: 'sidebar.menu_namespaces' },
    { route: 'search',     icon: 'eye',      label_key: 'sidebar.menu_search' },
    { route: 'settings',   icon: 'settings', label_key: 'sidebar.menu_settings' },
];

const NAMESPACE_DETAIL_PARENT = 'namespaces';

export class RagSidebar extends PlatformElement {
    static i18nNamespace = 'rag';

    private _routeKeySel: SelectController<string | null>;
    private _providers: OpController;

    static override styles = [
        PlatformElement.styles,
        sidebarStyles,
        sidebarNavItemStyles,
        css`
            :host { display: block; height: 100%; }
            .nav-item {
                display: flex; align-items: center; gap: var(--space-3);
                padding: var(--space-3) var(--space-4);
                border-radius: var(--radius-xl);
                cursor: pointer; background: transparent;
                border: 1px solid transparent;
                color: var(--text-secondary);
                font-size: var(--text-sm); font-weight: var(--font-medium);
                transition: var(--motion-transition-interactive);
                margin-bottom: var(--space-2);
                width: 100%; text-align: left;
            }
            .nav-item:hover {
                background: var(--glass-solid-medium);
                border-color: var(--glass-border-subtle);
                box-shadow: var(--glass-shadow-subtle);
                color: var(--text-primary);
                transform: translateX(4px);
            }
            .nav-item.active {
                background: var(--accent-subtle);
                border-color: var(--accent);
                color: var(--accent);
                font-weight: var(--font-semibold);
                box-shadow: 0 4px 16px rgba(153, 166, 249, 0.15);
            }
            .nav-label { flex: 1; }
            .provider-section {
                margin-top: auto;
                padding-top: var(--space-4);
                border-top: 1px solid var(--glass-border-subtle);
            }
            platform-service-sidebar[collapsed] .nav-label,
            platform-service-sidebar[collapsed] .provider-section { display: none; }
            platform-service-sidebar[collapsed] .nav-item { justify-content: center; padding: var(--space-3); }
            platform-service-sidebar[collapsed] .nav-item:hover { transform: none; }
        `,
    ];

    declare collapsed: boolean;
    declare mobileOpen: boolean;

    static override properties = {
        collapsed: { type: Boolean, reflect: true },
        mobileOpen: { type: Boolean, reflect: true, attribute: 'mobile-open' },
    };

    constructor() {
        super();
        this.collapsed = readShellSidebarCollapsed();
        this.mobileOpen = false;
        this._routeKeySel = this.select((s) => s.router.routeKey);
        this._providers = this.useOp('rag/providers');
    }

    override connectedCallback() {
        super.connectedCallback();
        if (!this._providers.lastResult && !this._providers.busy) {
            this._providers.run({});
        }
    }

    private _shell(): PlatformServiceSidebar | null {
        const root = this.renderRoot;
        if (!root) return null;
        const shell = root.querySelector('platform-service-sidebar');
        if (shell === null) return null;
        if (!(shell instanceof PlatformServiceSidebar)) {
            throw new Error('rag-sidebar: service sidebar required');
        }
        return shell;
    }
    closeMobile() {
        this._shell()?.closeMobile();
    }

    private _navigate(routeKey: string) {
        this.navigate(routeKey);
        this.closeMobile();
    }

    private _isActive(route: string) {
        const current = this._routeKeySel.value;
        if (route === NAMESPACE_DETAIL_PARENT) {
            return current === 'namespaces' || current === 'namespace_detail';
        }
        return current === route;
    }

    private _renderNavItem(item: { route: string; icon: string; label_key: string }) {
        return html`
            <button
                class="nav-item ${this._isActive(item.route) ? 'active' : ''}"
                @click=${() => this._navigate(item.route)}
            >
                <platform-icon name=${item.icon} size="18"></platform-icon>
                <span class="nav-label">${this.t(item.label_key)}</span>
            </button>
        `;
    }

    override render() {
        return html`
            <platform-service-sidebar
                logo-src="/static/core/assets/service_logos/rag_logo.svg"
                logo-text=${this.t('sidebar.title')}
                ?logo-opens-services=${true}
                ?collapsed=${this.collapsed}
                ?mobile-open=${this.mobileOpen}
                @collapse-change=${(e: CustomEvent<{ collapsed: boolean }>) => { this.collapsed = e.detail.collapsed; }}
                @mobile-change=${(e: CustomEvent<{ open: boolean }>) => { this.mobileOpen = e.detail.open; }}
            >
                <nav>
                    ${NAV_ITEMS.map((item) => this._renderNavItem(item))}
                </nav>

                <div class="provider-section" data-hide-collapsed>
                    <rag-provider-status></rag-provider-status>
                </div>

                <div slot="footer">
                    <platform-user block>
                        <platform-notification-manager slot="user-toolbar"></platform-notification-manager>
                    </platform-user>
                    <platform-deployment-version base-url="/rag" footer></platform-deployment-version>
                </div>
            </platform-service-sidebar>
        `;
    }
}

customElements.define('rag-sidebar', RagSidebar);
