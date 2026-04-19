/**
 * CRMSidebar — навигация и SPACE-селектор сервиса CRM на event-driven каноне.
 *
 * Логотип «NetWorkle» с градиентом через CSS-токены core
 * (`--sidebar-logo-text-gradient`, `--sidebar-logo-text-clip`,
 * `--sidebar-logo-text-fill`).
 *
 * SPACE-селектор: <select> со списком namespaces из фабрики `crm/namespaces`
 * (autoload), кнопка `+` открывает модалку `crm.namespace_create`. Выбор
 * пишется в bus через `setPlatformNamespaceSelection`, ui.effect персистит
 * в localStorage и эмитит `UI_NAMESPACE_CHANGED` + `UI_DOCUMENTS_RELOAD_REQUESTED`,
 * на которые подписаны страницы.
 *
 * Навигация: две nav-секции — Notes/Entities/Graph и ORGANIZATION с
 * Tasks/AI Analysis/Settings. Подсветка активного по `state.router.routeKey`.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { sidebarStyles, sidebarNavItemStyles } from '@platform/lib/styles/shared/sidebar.styles.js';
import { readShellSidebarCollapsed } from '@platform/lib/utils/shell-sidebar-preference.js';
import {
    getPlatformNamespaceSidebarSelection,
    setPlatformNamespaceSelection,
} from '@platform/lib/utils/platform-namespace.js';
import '@platform/lib/components/layout/platform-service-sidebar.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-user.js';
import '@platform/lib/components/platform-deployment-version.js';
import '@platform/lib/components/platform-notification-manager.js';

const PRIMARY_NAV = [
    { route: 'notes',    icon: 'list',     label_key: 'sidebar.nav.notes' },
    { route: 'entities', icon: 'database', label_key: 'sidebar.nav.entities' },
    { route: 'graph',    icon: 'share',    label_key: 'sidebar.nav.graph' },
];

const ORG_NAV = [
    { route: 'tasks',              icon: 'check',    label_key: 'sidebar.nav.tasks' },
    { route: 'access_requests',    icon: 'lock',     label_key: 'sidebar.nav.access_requests' },
    { route: 'namespace_imports',  icon: 'ai',       label_key: 'sidebar.nav.ai_analysis' },
    { route: 'settings',           icon: 'settings', label_key: 'sidebar.nav.settings' },
];

const SETTINGS_ALIASES = new Set(['settings', 'spaces', 'templates', 'relationship_types']);

export class CRMSidebar extends PlatformElement {
    static i18nNamespace = 'crm';

    static styles = [
        PlatformElement.styles,
        sidebarStyles,
        sidebarNavItemStyles,
        css`
            :host { display: block; height: 100%; }

            platform-service-sidebar {
                --sidebar-logo-text-weight: 700;
                --sidebar-logo-text-gradient: var(--crm-main-gradient);
                --sidebar-logo-text-clip: text;
                --sidebar-logo-text-fill: transparent;
            }

            .ns-section {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2);
                margin-bottom: var(--space-4);
                background: var(--crm-surface-muted);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-lg);
                width: 100%;
                box-sizing: border-box;
            }
            .ns-label {
                font-size: 10px;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.05em;
                color: var(--text-tertiary);
                white-space: nowrap;
                flex-shrink: 0;
            }
            .ns-select {
                flex: 1;
                min-width: 0;
                background: transparent;
                border: none;
                color: var(--text-primary);
                font-size: var(--text-sm);
                font-weight: 500;
                cursor: pointer;
                outline: none;
                padding: var(--space-1) var(--space-2);
                overflow: hidden;
                text-overflow: ellipsis;
            }
            .ns-select option {
                background: var(--crm-surface-elevated);
                color: var(--text-primary);
            }
            .ns-add-btn {
                display: flex;
                align-items: center;
                justify-content: center;
                width: 24px;
                height: 24px;
                border: none;
                background: var(--crm-main-gradient);
                color: var(--text-inverse);
                border-radius: var(--radius-md);
                cursor: pointer;
                transition: transform var(--duration-fast);
                flex-shrink: 0;
            }
            .ns-add-btn:hover { transform: scale(1.05); }
            .ns-edit-btn {
                display: flex;
                align-items: center;
                justify-content: center;
                width: 24px;
                height: 24px;
                border: 1px solid var(--crm-stroke);
                background: transparent;
                color: var(--text-secondary);
                border-radius: var(--radius-md);
                cursor: pointer;
                transition: background var(--duration-fast),
                            color var(--duration-fast),
                            border-color var(--duration-fast);
                flex-shrink: 0;
            }
            .ns-edit-btn:hover {
                background: var(--crm-selected-bg);
                color: var(--crm-selected-text);
                border-color: var(--crm-selected-stroke);
            }

            .nav-section { margin-bottom: var(--space-6); }
            .nav-title {
                font-size: 12px;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.08em;
                color: var(--text-tertiary);
                margin-bottom: var(--space-3);
                padding: 0 var(--space-3);
            }
            .nav-item {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                padding: var(--space-3);
                margin-bottom: var(--space-1);
                background: transparent;
                border: none;
                border-radius: var(--radius-lg);
                color: var(--text-primary);
                font-size: var(--text-base);
                font-weight: 500;
                cursor: pointer;
                transition: background var(--duration-fast), border-color var(--duration-fast), color var(--duration-fast);
                width: 100%;
                text-align: left;
            }
            .nav-item:hover { background: var(--glass-solid-subtle); }
            .nav-item.active {
                background: var(--crm-selected-bg);
                border: 1px solid var(--crm-selected-stroke);
                color: var(--crm-selected-text);
            }

            .nav-icon-wrapper {
                width: 32px;
                height: 32px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-md);
                border: 1px solid var(--crm-stroke);
                background: var(--crm-surface-muted);
                color: var(--text-secondary);
                flex-shrink: 0;
            }
            .nav-item.active .nav-icon-wrapper {
                border-color: var(--crm-selected-stroke);
                color: var(--crm-selected-text);
                background: var(--crm-selected-bg);
            }
            .nav-label { flex: 1; font-size: var(--text-base); }

            .user-section {
                display: flex;
                flex-direction: column;
                align-items: stretch;
                gap: var(--space-2);
                width: 100%;
                min-width: 0;
            }

            platform-service-sidebar[collapsed] .ns-section,
            platform-service-sidebar[collapsed] .nav-label,
            platform-service-sidebar[collapsed] .nav-title { display: none; }
            platform-service-sidebar[collapsed] .nav-item { justify-content: center; padding: var(--space-3); }
        `,
    ];

    static properties = {
        collapsed: { type: Boolean, reflect: true },
        mobileOpen: { type: Boolean, reflect: true, attribute: 'mobile-open' },
    };

    constructor() {
        super();
        this.collapsed = readShellSidebarCollapsed();
        this.mobileOpen = false;
        this._routeKeySel = this.select((s) => s.router.routeKey);
        this._authSel = this.select((s) => s.auth.user);
        this._namespaces = this.useResource('crm/namespaces', { autoload: true });
    }

    _navigate(routeKey) {
        this.navigate(routeKey);
        this.renderRoot?.querySelector('platform-service-sidebar')?.closeMobile?.();
    }

    _onNamespaceChange(event) {
        const user = this._authSel.value;
        if (!user || typeof user.company_id !== 'string') {
            throw new Error('CRMSidebar: cannot change namespace without active company_id');
        }
        const value = event.target.value;
        setPlatformNamespaceSelection(user.company_id, value === '' ? null : value);
    }

    _openCreateNamespace() {
        this.openModal('crm.namespace', { mode: 'create' });
    }

    _openEditNamespace(name) {
        if (typeof name !== 'string' || name.length === 0) {
            throw new Error('CRMSidebar._openEditNamespace: name required');
        }
        this.openModal('crm.namespace', { mode: 'edit', name });
    }

    _isActive(route) {
        const current = this._routeKeySel.value;
        if (route === 'settings') {
            return SETTINGS_ALIASES.has(current);
        }
        return current === route;
    }

    _renderNavItem(item) {
        return html`
            <button
                class="nav-item ${this._isActive(item.route) ? 'active' : ''}"
                @click=${() => this._navigate(item.route)}
            >
                <span class="nav-icon-wrapper">
                    <platform-icon name=${item.icon} size="18"></platform-icon>
                </span>
                <span class="nav-label">${this.t(item.label_key)}</span>
            </button>
        `;
    }

    render() {
        const user = this._authSel.value;
        const companyId = user && typeof user.company_id === 'string' ? user.company_id : null;
        const sidebarSelection = companyId ? getPlatformNamespaceSidebarSelection(companyId) : 'all';
        const selectValue = sidebarSelection === 'all' ? '' : sidebarSelection;
        const items = this._namespaces.items;

        return html`
            <platform-service-sidebar
                logo-src="/crm/ui/static/assets/icons/networkle_logo.svg"
                logo-text="NetWorkle"
                ?collapsed=${this.collapsed}
                ?mobile-open=${this.mobileOpen}
                @collapse-change=${(e) => { this.collapsed = e.detail.collapsed; }}
                @mobile-change=${(e) => { this.mobileOpen = e.detail.open; }}
            >
                <div slot="header">
                    <div class="ns-section">
                        <span class="ns-label">${this.t('sidebar.namespace_label')}</span>
                        <select class="ns-select" .value=${selectValue} @change=${this._onNamespaceChange}>
                            <option value="">${this.t('sidebar.all_namespaces')}</option>
                            ${items.map((ns) => html`
                                <option value=${ns.name} ?selected=${ns.name === selectValue}>
                                    ${ns.title || ns.name}
                                </option>
                            `)}
                        </select>
                        ${selectValue !== '' ? html`
                            <button
                                class="ns-edit-btn"
                                type="button"
                                title=${this.t('sidebar.edit_space_tooltip')}
                                @click=${() => this._openEditNamespace(selectValue)}
                            >
                                <platform-icon name="edit" size="14"></platform-icon>
                            </button>
                        ` : ''}
                        <button
                            class="ns-add-btn"
                            type="button"
                            title=${this.t('sidebar.create_space_tooltip')}
                            @click=${this._openCreateNamespace}
                        >
                            <platform-icon name="plus" size="14"></platform-icon>
                        </button>
                    </div>
                </div>

                <div class="nav-section">
                    ${PRIMARY_NAV.map((item) => this._renderNavItem(item))}
                </div>

                <div class="nav-section">
                    <div class="nav-title">${this.t('sidebar.org_section')}</div>
                    ${ORG_NAV.map((item) => this._renderNavItem(item))}
                </div>

                <div slot="footer" class="user-section">
                    <platform-user block>
                        <platform-notification-manager slot="user-toolbar"></platform-notification-manager>
                    </platform-user>
                    <platform-deployment-version base-url="/crm" footer></platform-deployment-version>
                </div>
            </platform-service-sidebar>
        `;
    }
}

customElements.define('crm-sidebar', CRMSidebar);
