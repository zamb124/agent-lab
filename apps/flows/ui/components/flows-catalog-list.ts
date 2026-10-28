/**
 * flows-catalog-list — единый каталог flow’ов для боковой панели и мобильной главной (/flows).
 *
 * Режим `sidebar`: встроен в `flows-sidebar` (десктоп), соблюдает `collapsedSidebar`
 * как прежний `sidebar-section` + тулбар.
 * Режим `page`: полноэкранный список на мобильном корне `/flows`, тот же поиск и
 * `flow-card`, что на десктопе в сайдбаре (mobile shell 2026 — как Sync `sync-chat-list`).
 */

import type { SelectController } from '@platform/lib/events/select-controller.js';
import type { OpController, ResourceController } from '@platform/lib/base/use-resource.js';
import { html, css } from 'lit';
import { repeat } from 'lit/directives/repeat.js';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { sidebarStyles, sidebarNavItemStyles, sidebarSectionStyles } from '@platform/lib/styles/shared/sidebar.styles.js';
import { toolbarShellStyles } from '@platform/lib/styles/shared/toolbar-shell.styles.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-help-hint.js';
import '@platform/lib/components/platform-modal-search-field.js';
import '@platform/lib/components/platform-button.js';
import './flow-card.js';
import { asArray, isPlainObject } from '../_helpers/flows-resolvers.js';
import type {CSSResultGroup, PropertyDeclarations, TemplateResult} from 'lit';

function _fieldIncludesSubstring(normalizedQuery: any, value: unknown) {
    if (typeof value !== 'string' || value.length === 0) return false;
    return value.toLowerCase().includes(normalizedQuery);
}

function flowMatchesSidebarSearch(flow: any, normalizedQuery: any) {
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
    static override properties: PropertyDeclarations = {
        mode: { type: String, reflect: true },
        collapsedSidebar: { type: Boolean, reflect: true, attribute: 'collapsed-sidebar' },
        _expanded: { state: true },
        _flowSearchQuery: { state: true },
    }
    declare mode: string;
    declare collapsedSidebar: boolean;
    declare _expanded: Record<string, any>;
    declare _flowSearchQuery: string;
;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        sidebarStyles,
        sidebarNavItemStyles,
        sidebarSectionStyles,
        toolbarShellStyles,
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

            .flows-toolbar platform-modal-search-field {
                flex: 1;
                min-width: 0;
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
                background: var(--glass-tint-subtle);
                backdrop-filter: blur(var(--glass-blur-medium));
                -webkit-backdrop-filter: blur(var(--glass-blur-medium));
                padding-top: var(--space-3);
                padding-bottom: var(--space-2);
                border-bottom: 1px solid var(--border-subtle);
            }
            .catalog-inner-cards {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }
        `,
    ];
    private _flows: ResourceController;
    private _branchRemove: OpController;
    private _currentFlowSel: SelectController<any>;

    constructor() {
        super();
        this.mode = 'sidebar';
        this.collapsedSidebar = false;
        this._expanded = {};
        this._flowSearchQuery = '';
        this._flows = this.useResource('flows/flows', { autoload: true });
        this._branchRemove = this.useOp('flows/branch_remove');
        this._currentFlowSel = this.select((s) => {
            const params = isPlainObject(s.router) && isPlainObject((s as any).router.params) ? (s as any).router.params : {};
            return typeof params.flowId === 'string' ? params.flowId : null;
        });
    }

    _requestDismissMobile() {
        this.emit('flows-catalog-dismiss-mobile', null);
    }

    async _confirmDeleteFlow(flowId: any) {
        const ok = await platformConfirm(
            this.t('flows_sidebar.delete_flow_message', { id: flowId }),
            {
                title: this.t('flows_sidebar.delete_flow_title'),
                variant: 'danger',
                confirmVariant: 'danger',
                confirmText: this.t('context_menu.delete'),
                cancelText: this.t('common.action_cancel'),
            },
        );
        if (!ok) return;
        await this._flows.remove(flowId);
    }

    async _confirmDeleteBranch(flowId: any, branchId: any) {
        const ok = await platformConfirm(
            this.t('flows_sidebar.delete_branch_message', { id: branchId }),
            {
                title: this.t('flows_sidebar.delete_branch_title'),
                variant: 'danger',
                confirmVariant: 'danger',
                confirmText: this.t('context_menu.delete'),
                cancelText: this.t('common.action_cancel'),
            },
        );
        if (!ok) return;
        await this._branchRemove.run({ flow_id: flowId, branch_id: branchId });
        await this._flows.get(flowId);
    }

    _onFlowAction(e: CustomEvent) {
        const { action, flowId, branchId } = (isPlainObject(e.detail) ? e.detail : {}) as Record<string, any>;
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
                this._expanded = { ...this._expanded, [flowId]: !(this._expanded as Record<string, any>)[flowId] };
                break;
        }
    }

    _createFlow() {
        this.openModal('flows.flow_create', {});
    }

    _onFlowSearchChange(e: CustomEvent) {
        const detail = e.detail;
        if (!isPlainObject(detail) || typeof detail.value !== 'string') {
            throw new TypeError('FlowsCatalogList._onFlowSearchChange: expected string detail.value');
        }
        this._flowSearchQuery = detail.value;
    }

    override render(): TemplateResult {
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
                        class="flows-toolbar toolbar-shell--flex"
                        role="group"
                        aria-label=${this.t('flows_sidebar.section_all_flows')}
                    >
                        <platform-modal-search-field
                            layout="fill"
                            .value=${this._flowSearchQuery}
                            placeholder=${this.t('flows_sidebar.search_placeholder')}
                            @change=${this._onFlowSearchChange}
                        >
                            <platform-help-hint
                                slot="suffix"
                                .label=${this.t('flows_sidebar.catalog_help_label')}
                                .summary=${this.t('flows_sidebar.catalog_help_summary')}
                                .details=${this.t('flows_sidebar.catalog_help_details')}
                                .docHref=${'/documentation/scenarios/flows/flows-home-overview/'}
                                .docLabel=${this.t('help_hints.open_scenario')}
                            ></platform-help-hint>
                        </platform-modal-search-field>
                        <platform-button
                            variant="primary"
                            icon-only
                            density="dense"
                            aria-label=${this.t('flows_sidebar.create_flow_tooltip')}
                            title=${this.t('flows_sidebar.create_flow_tooltip')}
                            data-action="create-flow"
                            @click=${this._createFlow}
                        >
                            <platform-icon name="plus" size="16"></platform-icon>
                        </platform-button>
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
                                        ?expanded=${Boolean((this._expanded as any)[flowItem.flow_id])}
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
