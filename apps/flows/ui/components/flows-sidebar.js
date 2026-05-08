/**
 * FlowsSidebar — список flow'ов в боковой панели.
 *
 * Источник правды — `useResource('flows/flows', { autoload: true })`.
 * Открытие модалок — `this.openModal('flows.<kind>', props)`. Навигация
 * между flow'ами — `this.navigate('flow_chat', { flowId })`.
 *
 * Поиск по каталогу — клиентский фильтр по уже загруженному списку (имя,
 * flow_id, описание, теги, имена веток). Полнота ограничена первой страницей
 * ответа API (limit по умолчанию 500).
 *
 * Локальное состояние UI: строка поиска, `expandedFlows`, `collapsed`/`mobileOpen`.
 */

import { html, css } from 'lit';
import { repeat } from 'lit/directives/repeat.js';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { sidebarStyles, sidebarNavItemStyles } from '@platform/lib/styles/shared/sidebar.styles.js';
import { readShellSidebarCollapsed } from '@platform/lib/utils/shell-sidebar-preference.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';
import '@platform/lib/components/layout/platform-service-sidebar.js';
import '@platform/lib/components/layout/sidebar-section.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-user.js';
import '@platform/lib/components/platform-notification-manager.js';
import '@platform/lib/components/platform-deployment-version.js';
import './flow-card.js';
import { asArray, asString, isPlainObject } from '../_helpers/flows-resolvers.js';

const OPERATOR_ROLES = new Set(['admin', 'owner']);

function _fieldIncludesSubstring(normalizedQuery, value) {
    if (typeof value !== 'string' || value.length === 0) return false;
    return value.toLowerCase().includes(normalizedQuery);
}

function flowMatchesSidebarSearch(flow, normalizedQuery) {
    if (normalizedQuery.length === 0) return true;
    if (!isPlainObject(flow)) return false;
    if (_fieldIncludesSubstring(normalizedQuery, flow.name)) return true;
    if (_fieldIncludesSubstring(normalizedQuery, flow.flow_id)) return true;
    if (_fieldIncludesSubstring(normalizedQuery, flow.description)) return true;
    if (Array.isArray(flow.tags)) {
        for (const tag of flow.tags) {
            if (typeof tag !== 'string') continue;
            if (tag.toLowerCase().includes(normalizedQuery)) return true;
        }
    }
    const branches = flow.branches;
    if (!isPlainObject(branches)) return false;
    for (const key of Object.keys(branches)) {
        const branch = branches[key];
        if (!isPlainObject(branch)) continue;
        if (_fieldIncludesSubstring(normalizedQuery, branch.name)) return true;
    }
    return false;
}

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
        _expanded: { state: true },
        _flowSearchQuery: { state: true },
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
            .create-btn {
                width: 22px; height: 22px;
                display: flex; align-items: center; justify-content: center;
                border-radius: var(--radius-lg);
                color: white;
                background: var(--accent);
                border: none;
                cursor: pointer;
                box-shadow: 0 2px 6px rgba(153, 166, 249, 0.2);
                transition: all var(--duration-normal) var(--easing-default);
            }
            .create-btn:hover {
                background: var(--accent-hover);
                transform: scale(1.1);
                box-shadow: 0 3px 8px rgba(153, 166, 249, 0.3);
            }
            sidebar-section {
                flex: 1; min-height: 0;
                display: flex; flex-direction: column;
            }
            .flows-list {
                display: flex; flex-direction: column; gap: var(--space-2);
                flex: 1; overflow-y: auto; overflow-x: hidden; min-height: 0;
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
            .flows-toolbar {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                width: 100%;
                min-width: 0;
                box-sizing: border-box;
            }
            .flows-toolbar .flows-search {
                flex: 1;
                min-width: 0;
            }
            .flows-toolbar .create-btn {
                flex-shrink: 0;
            }
            .flows-search {
                position: relative;
                flex-shrink: 0;
            }
            .flows-search .search-icon {
                position: absolute;
                left: 10px;
                top: 50%;
                transform: translateY(-50%);
                color: var(--text-tertiary);
                pointer-events: none;
            }
            .flows-search-input {
                width: 100%;
                box-sizing: border-box;
                padding: var(--space-2) var(--space-2) var(--space-2) calc(var(--space-2) + 22px);
                border-radius: var(--radius-lg);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary);
                font: inherit;
                font-size: var(--text-sm);
                line-height: 1.25;
            }
            .flows-search-input:focus {
                outline: none;
                border-color: var(--accent);
                box-shadow: 0 0 0 2px var(--accent-subtle);
            }
            .flows-search-input:disabled {
                opacity: 0.65;
                cursor: not-allowed;
            }
            platform-service-sidebar[collapsed] .flows-toolbar {
                display: none;
            }
            .flows-search-empty {
                font-size: var(--text-sm);
                color: var(--text-tertiary);
                text-align: center;
                padding: var(--space-4) var(--space-2);
            }
        `,
    ];

    constructor() {
        super();
        this.collapsed = readShellSidebarCollapsed();
        this.mobileOpen = false;
        this._expanded = {};
        this._flowSearchQuery = '';
        this._flows = this.useResource('flows/flows', { autoload: true });
        this._branchRemove = this.useOp('flows/branch_remove');
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

    _onFlowAction(e) {
        const { action, flowId, branchId } = isPlainObject(e.detail) ? e.detail : {};
        switch (action) {
            case 'chat':
                if (branchId) {
                    this.navigate('flow_chat_branch', { flowId, branchId });
                } else {
                    this.navigate('flow_chat', { flowId });
                }
                this.closeMobile();
                break;
            case 'edit':
                if (branchId) {
                    this.navigate('flow_editor_branch', { flowId, branchId });
                } else {
                    this.navigate('flow_editor', { flowId });
                }
                break;
            case 'delete':
                this._confirmDeleteFlow(flowId);
                break;
            case 'delete-branch':
                this._confirmDeleteBranch(flowId, branchId);
                break;
            case 'create-branch':
                this.openModal('flows.branch_create', { flowId });
                break;
            case 'toggle':
                this._expanded = { ...this._expanded, [flowId]: !this._expanded[flowId] };
                break;
        }
    }

    async _confirmDeleteFlow(flowId) {
        const ok = await platformConfirm(
            this.t('flows_sidebar.delete_flow_message', { id: flowId }),
            {
                title: this.t('flows_sidebar.delete_flow_title'),
                variant: 'danger',
                confirmVariant: 'danger',
                confirmText: this.t('context_menu.delete'),
                cancelText: this.t('flows_sidebar.action_cancel'),
            },
        );
        if (!ok) return;
        await this._flows.remove(flowId);
    }

    async _confirmDeleteBranch(flowId, branchId) {
        const ok = await platformConfirm(
            this.t('flows_sidebar.delete_branch_message', { id: branchId }),
            {
                title: this.t('flows_sidebar.delete_branch_title'),
                variant: 'danger',
                confirmVariant: 'danger',
                confirmText: this.t('context_menu.delete'),
                cancelText: this.t('flows_sidebar.action_cancel'),
            },
        );
        if (!ok) return;
        await this._branchRemove.run({ flow_id: flowId, branch_id: branchId });
        await this._flows.get(flowId);
    }

    _createFlow() {
        this.openModal('flows.flow_create', {});
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

    _onFlowSearchInput(e) {
        const t = e.target;
        if (!(t instanceof HTMLInputElement)) {
            throw new Error('FlowsSidebar._onFlowSearchInput: expected input');
        }
        this._flowSearchQuery = typeof t.value === 'string' ? t.value : '';
    }

    render() {
        const items = asArray(this._flows.items);
        const qTrimmed = typeof this._flowSearchQuery === 'string' ? this._flowSearchQuery.trim() : '';
        const qNorm = qTrimmed.toLowerCase();
        const filteredItems = items.filter((f) => flowMatchesSidebarSearch(f, qNorm));
        const currentFlowId = this._currentFlowSel.value;
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
                <sidebar-section custom-header ?collapsed=${this.collapsed}>
                    <div
                        slot="header"
                        class="flows-toolbar"
                        role="group"
                        aria-label=${this.t('flows_sidebar.section_all_flows')}
                    >
                        <div class="flows-search">
                            <span class="search-icon" aria-hidden="true">
                                <platform-icon name="search" size="14"></platform-icon>
                            </span>
                            <input
                                type="search"
                                class="flows-search-input"
                                .value=${this._flowSearchQuery}
                                placeholder=${this.t('flows_sidebar.search_placeholder')}
                                aria-label=${this.t('flows_sidebar.search_aria')}
                                ?disabled=${this._flows.loading && items.length === 0}
                                @input=${this._onFlowSearchInput}
                            />
                        </div>
                        <button
                            class="create-btn"
                            title=${this.t('flows_sidebar.create_flow_tooltip')}
                            @click=${this._createFlow}
                        >
                            <platform-icon name="plus" size="12"></platform-icon>
                        </button>
                    </div>
                    <div class="flows-list">
                        ${this._flows.loading && items.length === 0
                            ? html`<glass-spinner></glass-spinner>`
                            : qTrimmed !== '' && items.length > 0 && filteredItems.length === 0
                                ? html`<div class="flows-search-empty">${this.t('flows_sidebar.search_empty')}</div>`
                                : repeat(
                                    filteredItems,
                                    (a) => a.flow_id,
                                    (flowItem) => html`
                                        <flow-card
                                            .flow=${flowItem}
                                            ?active=${flowItem.flow_id === currentFlowId}
                                            ?expanded=${Boolean(this._expanded[flowItem.flow_id])}
                                            ?collapsed=${this.collapsed}
                                            @flow-action=${this._onFlowAction}
                                        ></flow-card>
                                    `,
                                )}
                    </div>
                </sidebar-section>

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
