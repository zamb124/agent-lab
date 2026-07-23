/**
 * CRMTasksPage — first-class workspace задач namespace (WorkItem kind=crm_activity).
 */

import { html, css, nothing } from 'lit';
import { CRMNamespacePage } from '../base/crm-namespace-page.js';
import { isMobileViewport } from '@platform/lib/utils/work-item-deeplink.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-breadcrumbs.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-work-item-row.js';
import '@platform/lib/components/platform-work-item-board.js';
import '@platform/lib/components/platform-work-item-detail.js';
import '@platform/lib/components/glass-spinner.js';
import '../modals/activity-task-create-modal.js';

export class CRMTasksPage extends CRMNamespacePage {
    static properties = {
        ...CRMNamespacePage.properties,
        _viewMode: { state: true },
        _selectedId: { state: true },
        _selectedItem: { state: true },
    };

    static styles = [
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
                background: var(--bg-elevated, var(--glass-solid-medium));
            }
            .panel {
                min-height: 0;
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                overflow: hidden;
                background: var(--bg-elevated, var(--glass-solid-medium));
            }
            .empty {
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                gap: var(--space-3);
                padding: var(--space-10);
                color: var(--text-secondary);
                text-align: center;
            }
            .empty p {
                margin: 0;
                max-width: 28rem;
            }
            .loading {
                display: flex;
                justify-content: center;
                padding: var(--space-8);
            }
        `,
    ];

    constructor() {
        super();
        this._viewMode = 'list';
        this._selectedId = '';
        this._selectedItem = null;
        this._workItems = null;
        this._routeParamsSel = this.select((s) => s.router.params);
    }

    connectedCallback() {
        super.connectedCallback();
        this._workItems = this.useResource('platform/work_items', { autoload: false });
        this._createOp = this.useOp('crm/activity_task_create');
        this.useEvent(this._createOp.op.events.SUCCEEDED, () => this._reload());
        this._reload();
    }

    updated(changed) {
        super.updated?.(changed);
        const ns = this._crmNamespaceSel.value;
        if (changed.has('_crmNamespaceSel') || ns !== this._lastNs) {
            this._lastNs = ns;
            this._reload();
        }
        const params = this._routeParamsSel.value;
        const routeId = params && typeof params.workItemId === 'string' ? params.workItemId : '';
        if (routeId && routeId !== this._selectedId) {
            this._selectedId = routeId;
            const fromList = (this._workItems.items || []).find((i) => i.work_item_id === routeId);
            this._selectedItem = fromList || null;
        }
    }

    _reload() {
        if (!this._workItems) {
            return;
        }
        const namespace = this._crmNamespaceSel.value;
        const query = {
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
        this.openModal('crm.activity_task_create', {
            namespace: typeof namespace === 'string' && namespace.length > 0 ? namespace : 'default',
        });
    }

    _onOpen(detail) {
        if (!detail || typeof detail.work_item_id !== 'string') {
            throw new Error('CRMTasksPage: work_item_id required');
        }
        const mobile = detail.mobile === true || isMobileViewport();
        this._selectedId = detail.work_item_id;
        this._selectedItem = detail.item && typeof detail.item === 'object' ? detail.item : null;
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

    _onOpenEntity(detail) {
        if (!detail || typeof detail.entity_id !== 'string') {
            throw new Error('CRMTasksPage: entity_id required');
        }
        this.navigate('entity', { itemId: detail.entity_id });
    }

    render() {
        const items = Array.isArray(this._workItems?.items) ? this._workItems.items : [];
        const loading = Boolean(this._workItems?.loading);
        const selectedId = this._selectedId;
        const showPanel = Boolean(selectedId) && !isMobileViewport();
        this.toggleAttribute('data-no-panel', !showPanel);

        const routeKey = this.select((s) => s.router.routeKey).value;
        if (routeKey === 'task' && selectedId) {
            return html`
                <div class="page">
                    <platform-breadcrumbs></platform-breadcrumbs>
                    <platform-work-item-detail
                        layout="page"
                        work-item-id=${selectedId}
                        .item=${this._selectedItem}
                        show-graph-link
                        @open-crm-entity=${(e) => this._onOpenEntity(e.detail)}
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
                    ? html`<div class="loading"><glass-spinner></glass-spinner></div>`
                    : items.length === 0
                        ? html`
                            <div class="empty">
                                <platform-icon name="checklist" size="40"></platform-icon>
                                <p>${this.t('tasks_page.empty')}</p>
                                <platform-button variant="primary" @click=${() => this._openCreate()}>
                                    ${this.t('tasks_page.create')}
                                </platform-button>
                            </div>
                          `
                        : html`
                            <div class="workspace">
                                <div class="main">
                                    ${this._viewMode === 'board'
                                        ? html`
                                            <platform-work-item-board
                                                .items=${items}
                                                selected-work-item-id=${selectedId}
                                                @work-item-open=${(e) => this._onOpen(e.detail)}
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
                                                            @work-item-open=${(e) => this._onOpen(e.detail)}
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
                                                @open-crm-entity=${(e) => this._onOpenEntity(e.detail)}
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
