/**
 * flows-catalog-list — единый каталог flow’ов для боковой панели и мобильной главной (/flows).
 *
 * Режим `sidebar`: встроен в `flows-sidebar` (десктоп), соблюдает `collapsedSidebar`
 * как прежний `sidebar-section` + тулбар.
 * Режим `page`: полноэкранный список на мобильном корне `/flows`, тот же поиск и
 * `flow-card`, что на десктопе в сайдбаре (mobile shell 2026 — как Sync `sync-chat-list`).
 */

import { html, css } from 'lit';
import { repeat } from 'lit/directives/repeat.js';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { sidebarStyles, sidebarNavItemStyles, sidebarSectionStyles } from '@platform/lib/styles/shared/sidebar.styles.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-help-hint.js';
import './flow-card.js';
import { asArray, isPlainObject } from '../_helpers/flows-resolvers.js';

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

export class FlowsCatalogList extends PlatformElement {
    static properties = {
        mode: { type: String, reflect: true },
        collapsedSidebar: { type: Boolean, reflect: true, attribute: 'collapsed-sidebar' },
        _expanded: { state: true },
        _flowSearchQuery: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        sidebarStyles,
        sidebarNavItemStyles,
        sidebarSectionStyles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                flex: 1;
                min-height: 0;
                box-sizing: border-box;
                --flows-toolbar-control-size: calc(
                    2px + (var(--space-2) * 2) + (var(--text-sm) * 1.25)
                );
            }
            .flows-catalog-root {
                display: flex;
                flex-direction: column;
                flex: 1;
                min-height: 0;
            }
            :host([mode='page']) .flows-catalog-root {
                overflow: hidden;
            }
            :host([mode='page']) .section-content.catalog-scroll {
                padding-left: var(--space-3);
                padding-right: var(--space-3);
                padding-bottom: max(var(--space-4), env(safe-area-inset-bottom, 0px));
                -webkit-overflow-scrolling: touch;
            }
            :host([mode='sidebar']) .section-header.catalog-toolbar-host {
                padding-left: var(--space-3);
                padding-right: var(--space-3);
            }
            :host([collapsed-sidebar]) .section-header.catalog-toolbar-host {
                display: none;
            }

            .create-btn {
                box-sizing: border-box;
                width: var(--flows-toolbar-control-size);
                height: var(--flows-toolbar-control-size);
                display: flex; align-items: center; justify-content: center;
                border-radius: var(--radius-lg);
                color: white;
                background: var(--accent);
                border: none;
                cursor: pointer;
                box-shadow: 0 2px 6px rgba(153, 166, 249, 0.2);
                transition: var(--motion-transition-interactive);
                flex-shrink: 0;
            }
            .create-btn:hover {
                background: var(--accent-hover);
                transform: scale(1.06);
                box-shadow: 0 3px 8px rgba(153, 166, 249, 0.3);
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
            .catalog-help {
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
                height: var(--flows-toolbar-control-size);
                padding: 0 var(--space-2) 0 calc(var(--space-2) + 22px);
                border-radius: var(--radius-lg);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary);
                font: inherit;
                font-size: var(--text-sm);
                line-height: calc(var(--flows-toolbar-control-size) - 2px);
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
            .flows-search-empty {
                font-size: var(--text-sm);
                color: var(--text-tertiary);
                text-align: center;
                padding: var(--space-4) var(--space-2);
            }
            :host([mode='page']) .section-header.catalog-toolbar-host {
                position: sticky;
                top: 0;
                z-index: 2;
                background: var(--glass-tint-subtle, rgba(255, 255, 255, 0.03));
                backdrop-filter: blur(var(--glass-blur-medium));
                -webkit-backdrop-filter: blur(var(--glass-blur-medium));
                padding-top: var(--space-3);
                padding-bottom: var(--space-2);
                border-bottom: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.06));
            }
            .catalog-inner-cards {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }
        `,
    ];

    constructor() {
        super();
        this.mode = 'sidebar';
        this.collapsedSidebar = false;
        this._expanded = {};
        this._flowSearchQuery = '';
        this._flows = this.useResource('flows/flows', { autoload: true });
        this._branchRemove = this.useOp('flows/branch_remove');
        this._currentFlowSel = this.select((s) => {
            const params = isPlainObject(s.router) && isPlainObject(s.router.params) ? s.router.params : {};
            return typeof params.flowId === 'string' ? params.flowId : null;
        });
    }

    _requestDismissMobile() {
        this.emit('flows-catalog-dismiss-mobile', null);
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

    _onFlowAction(e) {
        const { action, flowId, branchId } = isPlainObject(e.detail) ? e.detail : {};
        switch (action) {
            case 'chat':
                if (branchId) {
                    this.navigate('flow_chat_branch', { flowId, branchId });
                } else {
                    this.navigate('flow_chat', { flowId });
                }
                this._requestDismissMobile();
                break;
            case 'edit':
                if (branchId) {
                    this.navigate('flow_editor_branch', { flowId, branchId });
                } else {
                    this.navigate('flow_editor', { flowId });
                }
                this._requestDismissMobile();
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

    _createFlow() {
        this.openModal('flows.flow_create', {});
    }

    _onFlowSearchInput(e) {
        const t = e.target;
        if (!(t instanceof HTMLInputElement)) {
            throw new Error('FlowsCatalogList._onFlowSearchInput: expected input');
        }
        this._flowSearchQuery = typeof t.value === 'string' ? t.value : '';
    }

    render() {
        const items = asArray(this._flows.items);
        const qTrimmed = typeof this._flowSearchQuery === 'string' ? this._flowSearchQuery.trim() : '';
        const qNorm = qTrimmed.toLowerCase();
        const filteredItems = items.filter((f) => flowMatchesSidebarSearch(f, qNorm));
        const currentFlowId = this._currentFlowSel.value;
        const cardCollapsed = this.mode === 'sidebar' && this.collapsedSidebar;

        return html`
            <div class="section flows-catalog-root">
                <div class="section-header section-header--custom catalog-toolbar-host">
                    <div
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
                            type="button"
                            class="create-btn"
                            title=${this.t('flows_sidebar.create_flow_tooltip')}
                            aria-label=${this.t('flows_sidebar.create_flow_tooltip')}
                            data-action="create-flow"
                            @click=${this._createFlow}
                        >
                            <platform-icon name="plus" size="16"></platform-icon>
                        </button>
                        <platform-help-hint
                            class="catalog-help"
                            .label=${this.t('flows_sidebar.catalog_help_label')}
                            .summary=${this.t('flows_sidebar.catalog_help_summary')}
                            .details=${this.t('flows_sidebar.catalog_help_details')}
                            .docHref=${'/documentation/scenarios/flows/flows-home-overview/'}
                            .docLabel=${this.t('help_hints.open_scenario')}
                        ></platform-help-hint>
                    </div>
                </div>
                <div class="section-content catalog-scroll catalog-inner-cards">
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
                                        ?collapsed=${cardCollapsed}
                                        @flow-action=${this._onFlowAction}
                                    ></flow-card>
                                `,
                            )}
                </div>
            </div>
        `;
    }
}

customElements.define('flows-catalog-list', FlowsCatalogList);
