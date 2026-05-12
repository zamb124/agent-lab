/**
 * FlowsSidebar — оболочка `platform-service-sidebar` + футер; каталог flow’ов —
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
import { asString, isPlainObject } from '../_helpers/flows-resolvers.js';

const OPERATOR_ROLES = new Set(['admin', 'owner']);

function userCanManageOperator(user, activeCompanyId) {
    if (!user || typeof user !== 'object' || typeof activeCompanyId !== 'string') return false;
    const direct = isPlainObject(user.companies) ? user.companies : null;
    const rawCompanies = isPlainObject(user.raw) && isPlainObject(user.raw.companies) ? user.raw.companies : null;
    const companies = direct !== null ? direct : rawCompanies;
    if (!companies) return false;
    const entry = companies[activeCompanyId];
    if (!entry) return false;
    const list = Array.isArray(entry) ? entry : [entry];
    for (const r of list) {
        if (typeof r !== 'string') continue;
        if (OPERATOR_ROLES.has(r.trim().toLowerCase())) return true;
    }
    return false;
}

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
            .footer-links {
                display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-2);
                margin-bottom: var(--space-3);
            }
            .footer-link {
                display: flex; align-items: center; gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-lg);
                font-size: var(--text-sm);
                color: var(--text-secondary);
                background: var(--glass-solid-subtle);
                border: none;
                text-decoration: none;
                cursor: pointer;
                transition: all var(--duration-fast);
            }
            .footer-link:hover {
                background: var(--glass-solid-medium);
                color: var(--text-primary);
            }
            platform-service-sidebar[collapsed] .footer-links {
                display: flex; flex-direction: column; align-items: center;
            }
            platform-service-sidebar[collapsed] .footer-link {
                width: 36px; height: 36px; padding: 0; justify-content: center;
            }
            platform-service-sidebar[collapsed] .footer-link span {
                display: none;
            }
        `,
    ];

    constructor() {
        super();
        this.collapsed = readShellSidebarCollapsed();
        this.mobileOpen = false;
        this._currentFlowSel = this.select((s) => {
            const params = isPlainObject(s.router) && isPlainObject(s.router.params) ? s.router.params : {};
            return typeof params.flowId === 'string' ? params.flowId : null;
        });
        this._routeKeySel = this.select((s) => {
            const r = isPlainObject(s.router) && typeof s.router.routeKey === 'string' ? s.router.routeKey : '';
            return r;
        });
        this._authSel = this.select((s) => ({
            user: isPlainObject(s.auth) && isPlainObject(s.auth.user) ? s.auth.user : null,
            companyId: isPlainObject(s.auth) && typeof s.auth.activeCompanyId === 'string' ? s.auth.activeCompanyId : null,
        }));
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

    _openSessions() {
        const flowId = this._currentFlowSel.value;
        this.openModal('flows.sessions', { flowId: asString(flowId) });
    }

    _openMcp() {
        this.openModal('flows.mcp_servers', {});
    }

    _openVariables() {
        const flowId = this._currentFlowSel.value;
        const routeKey = this._routeKeySel.value;
        const inFlowEditor = routeKey === 'flow_editor' || routeKey === 'flow_editor_branch';
        if (inFlowEditor && typeof flowId === 'string' && flowId.length > 0) {
            this.openModal('flows.variables', { scope: 'flow', flowId });
            return;
        }
        this.openModal('flows.variables', { scope: 'company' });
    }

    _openIntegrations() {
        this.openModal('flows.integrations', {});
    }

    _openOperator() {
        this.navigate('operator', {});
    }

    _onCatalogDismissMobile() {
        this.closeMobile();
    }

    render() {
        const auth = this._authSel.value;
        const operatorAllowed = userCanManageOperator(auth.user, auth.companyId);

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
                <flows-catalog-list
                    mode="sidebar"
                    ?collapsedSidebar=${this.collapsed}
                    @flows-catalog-dismiss-mobile=${this._onCatalogDismissMobile}
                ></flows-catalog-list>
                <div slot="footer">
                    <div class="footer-links">
                        ${operatorAllowed
                            ? html`
                                <button type="button" class="footer-link" @click=${this._openOperator}>
                                    <platform-icon name="users" size="16"></platform-icon>
                                    <span>${this.t('flows_sidebar.footer_operator_tasks')}</span>
                                </button>
                            `
                            : ''}
                        <button type="button" class="footer-link" @click=${this._openSessions}>
                            <platform-icon name="chat" size="16"></platform-icon>
                            <span>${this.t('flows_sidebar.footer_sessions')}</span>
                        </button>
                        <button type="button" class="footer-link" @click=${this._openMcp}>
                            <platform-icon name="cloud" size="16"></platform-icon>
                            <span>${this.t('flows_sidebar.footer_mcp')}</span>
                        </button>
                        <button type="button" class="footer-link" @click=${this._openVariables}>
                            <platform-icon name="key" size="16"></platform-icon>
                            <span>${this.t('flows_sidebar.footer_vars')}</span>
                        </button>
                        <button type="button" class="footer-link" @click=${this._openIntegrations}>
                            <platform-icon name="link" size="16"></platform-icon>
                            <span>${this.t('flows_sidebar.footer_integrations')}</span>
                        </button>
                    </div>
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
