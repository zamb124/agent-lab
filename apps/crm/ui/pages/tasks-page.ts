/**
 * CRMTasksPage — first-class workspace задач namespace (WorkItem kind=crm_activity).
 */

import { html, css, nothing } from 'lit';
import { CRMNamespacePage } from './crm-namespace-page.js';
import { isMobileViewport } from '@platform/lib/utils/work-item-deeplink.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-breadcrumbs.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-work-item-row.js';
import '@platform/lib/components/platform-work-item-board.js';
import '@platform/lib/components/platform-work-item-detail.js';
import '@platform/lib/components/platform-spinner.js';
import '@platform/lib/components/platform-empty-state.js';
import '../modals/activity-task-create-modal.js';
import type {
    CSSResultGroup,
    PropertyDeclarations,
    PropertyValues,
    TemplateResult,
} from 'lit';
import type {
    OpController,
    ResourceController,
} from '@platform/lib/base/use-resource.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';

export class CRMTasksPage extends CRMNamespacePage {
    static override properties: PropertyDeclarations = {
        ...CRMNamespacePage.properties,
        _viewMode: { state: true },
        _selectedId: { state: true },
        _selectedItem: { state: true },
    };
    declare _viewMode: 'list' | 'board';
    declare _selectedId: string;
    declare _selectedItem: Record<string, unknown> | null;

    static override styles: CSSResultGroup = [
        CRMNamespacePage.styles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                min-height: 0;
                height: 100%;
            }
            .page {
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
                padding: var(--space-4) var(--space-6);
                min-height: 0;
                flex: 1;
            }
            .workspace {
                display: grid;
                grid-template-columns: minmax(0, 1fr) minmax(320px, 400px);
                gap: var(--space-4);
                min-height: 0;
                flex: 1;
            }
            :host([data-no-panel]) .workspace {
                grid-template-columns: minmax(0, 1fr);
            }
            @media (max-width: 960px) {
                .workspace {
                    grid-template-columns: minmax(0, 1fr);
                }
                .panel {
                    display: none;
                }
            }
            .toolbar {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                flex-wrap: wrap;
            }
            .list {
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
                min-height: 0;
                overflow: auto;
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                background: var(--bg-elevated);
            }
            .panel {
                min-height: 0;
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                overflow: hidden;
                background: var(--bg-elevated);
            }
        `,
    ];

    private _routeParamsSel: SelectController<Record<string, unknown> | undefined>;
    private _workItems: ResourceController | null;
    private _createOp!: OpController;
    private _lastNs: string | null | undefined = null;

    constructor() {
        super();
        this._viewMode = 'list';
        this._selectedId = '';
        this._selectedItem = null;
        this._workItems = null;
        this._routeParamsSel = this.select((s) => s.router.params);
    }

    override connectedCallback(): void {
        super.connectedCallback();
        this._workItems = this.useResource('worktracker/work_items', { autoload: false });
        this._createOp = this.useOp('crm/activity_task_create');
        this._reload();
    }

    override updated(changed: PropertyValues<this>): void {
        super.updated?.(changed);
        const ns = this._crmNamespaceSel.value;
        if (ns !== this._lastNs) {
            this._lastNs = ns;
            this._reload();
        }
        const params = this._routeParamsSel.value;
        const routeId = params && typeof params.workItemId === 'string' ? params.workItemId : '';
        if (routeId && routeId !== this._selectedId) {
            this._selectedId = routeId;
            const workItems = this._workItems;
            const items = workItems === null ? [] : workItems.items;
            const fromList = items.find((item) => isPlainRecord(item) && item.work_item_id === routeId);
            this._selectedItem = isPlainRecord(fromList) ? fromList : null;
            if (!this._selectedItem) {
                if (workItems === null) {
                    throw new Error('tasks-page: work items resource required');
                }
                workItems.get(routeId);
            }
        }
    }

    _reload() {
        if (!this._workItems) {
            return;
        }
        const namespace = this._crmNamespaceSel.value;
        const query: Record<string, unknown> = {
            kind: 'crm_activity',
            limit: 100,
            offset: 0,
        };
        if (typeof namespace === 'string' && namespace.length > 0) {
            query.namespace = namespace;
        }
        this._workItems.load(query);
    }

    _openCreate() {
        const namespace = this._crmNamespaceSel.value;
        if (typeof namespace !== 'string' || namespace.length === 0) {
            throw new Error('CRMTasksPage._openCreate: namespace required');
        }
        this.openModal('crm.activity_task_create', { namespace });
    }

    _onOpen(detail: { work_item_id?: unknown; mobile?: unknown; item?: unknown } | null) {
        if (!detail || typeof detail.work_item_id !== 'string') {
            throw new Error('CRMTasksPage: work_item_id required');
        }
        const mobile = detail.mobile === true || isMobileViewport();
        this._selectedId = detail.work_item_id;
        this._selectedItem = isPlainRecord(detail.item) ? detail.item : null;
        if (mobile) {
            this.navigate('task', { workItemId: detail.work_item_id });
            return;
        }
        this.toggleAttribute('data-no-panel', false);
    }

    _closePanel() {
        this._selectedId = '';
        this._selectedItem = null;
    }

    _onOpenEntity(detail: { entity_id?: unknown } | null) {
        if (!detail || typeof detail.entity_id !== 'string') {
            throw new Error('CRMTasksPage: entity_id required');
        }
        this.navigate('entity', { itemId: detail.entity_id });
    }

    override render(): TemplateResult {
        const items = Array.isArray(this._workItems?.items) ? this._workItems.items : [];
        const loading = Boolean(this._workItems?.loading);
        const selectedId = this._selectedId;
        const showPanel = Boolean(selectedId) && !isMobileViewport();
        this.toggleAttribute('data-no-panel', !showPanel);

        const routeKey = this.select((s) => s.router.routeKey).value;
        const fromCache = selectedId && this._workItems && this._workItems.byId
            ? this._workItems.byId[selectedId]
            : null;
        const selectedItem = this._selectedItem !== null
            ? this._selectedItem
            : (fromCache === null || fromCache === undefined ? null : fromCache);
        if (routeKey === 'task' && selectedId) {
            return html`
                <div class="page">
                    <platform-breadcrumbs></platform-breadcrumbs>
                    <platform-work-item-detail
                        layout="page"
                        work-item-id=${selectedId}
                        .item=${selectedItem}
                        show-graph-link
                        @open-crm-entity=${(e: CustomEvent) => this._onOpenEntity(e.detail)}
                    ></platform-work-item-detail>
                </div>
            `;
        }

        return html`
            <div class="page">
                <platform-breadcrumbs></platform-breadcrumbs>
                <page-header .title=${this.t('tasks_page.title')}>
                    <div slot="actions" class="toolbar">
                        <platform-button
                            variant=${this._viewMode === 'list' ? 'secondary' : 'ghost'}
                            size="sm"
                            @click=${() => { this._viewMode = 'list'; }}
                        >
                            <platform-icon name="list" size="16"></platform-icon>
                        </platform-button>
                        <platform-button
                            variant=${this._viewMode === 'board' ? 'secondary' : 'ghost'}
                            size="sm"
                            @click=${() => { this._viewMode = 'board'; }}
                        >
                            <platform-icon name="layers" size="16"></platform-icon>
                        </platform-button>
                        <platform-button variant="primary" @click=${() => this._openCreate()}>
                            ${this.t('tasks_page.create')}
                        </platform-button>
                    </div>
                </page-header>

                ${loading
                    ? html`<platform-empty-state loading></platform-empty-state>`
                    : items.length === 0
                        ? html`
                            <platform-empty-state icon="checklist" title=${this.t('tasks_page.empty')}>
                                <platform-button variant="primary" @click=${() => this._openCreate()}>
                                    ${this.t('tasks_page.create')}
                                </platform-button>
                            </platform-empty-state>
                          `
                        : html`
                            <div class="workspace">
                                <div class="main">
                                    ${this._viewMode === 'board'
                                        ? html`
                                            <platform-work-item-board
                                                .items=${items}
                                                selected-work-item-id=${selectedId}
                                                @work-item-open=${(e: CustomEvent) => this._onOpen(e.detail)}
                                                @work-item-changed=${() => this._reload()}
                                            ></platform-work-item-board>
                                          `
                                        : html`
                                            <div class="list">
                                                ${items.map(
                                                    (item) => html`
                                                        <platform-work-item-row
                                                            data-no-default-nav
                                                            .item=${item}
                                                            ?selected=${item.work_item_id === selectedId}
                                                            @work-item-open=${(e: CustomEvent) => this._onOpen(e.detail)}
                                                        ></platform-work-item-row>
                                                    `,
                                                )}
                                            </div>
                                          `}
                                </div>
                                ${showPanel
                                    ? html`
                                        <aside class="panel">
                                            <platform-work-item-detail
                                                layout="panel"
                                                work-item-id=${selectedId}
                                                .item=${this._selectedItem}
                                                show-graph-link
                                                @close-requested=${() => this._closePanel()}
                                                @open-crm-entity=${(e: CustomEvent) => this._onOpenEntity(e.detail)}
                                                @work-item-changed=${() => this._reload()}
                                            ></platform-work-item-detail>
                                        </aside>
                                      `
                                    : nothing}
                            </div>
                          `}
            </div>
        `;
    }
}

customElements.define('crm-tasks-page', CRMTasksPage);
