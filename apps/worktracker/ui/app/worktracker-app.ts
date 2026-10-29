/**
 * WorktrackerApp — корневой компонент сервиса задач (`/worktracker`).
 */

import { html, css } from 'lit';
import { PlatformApp } from '@platform/lib/base/PlatformApp.js';
import type { PlatformEvent } from '@platform/lib/events/contract.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';
import type { OpController } from '@platform/lib/base/use-resource.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
import { createRouterEffect } from '@platform/lib/events/effects/router.effect.js';

import { platformFileCreateOp } from '@platform/lib/events/factories/platform-file-create.js';
import { boardsResource, boardCreateForm } from '../events/resources/boards.resource.js';
import {
    workQueuesResource,
    workQueueMembersListOp,
    workQueueMemberAddOp,
    workQueueMemberRemoveOp,
} from '../events/resources/queues.resource.js';
import { WorktrackerUiEvents } from '../events/types.js';
import {
    replaceWorkItemUrl,
    readWorkItemIdFromLocation,
    readWorkItemIdFromPathname,
    hasLegacyWorkItemQuery,
} from '@platform/lib/utils/work-item-deeplink.js';
import { buildWorktrackerAssistantContext } from '../_helpers/platform-assistant-context.js';

import '@platform/lib/components/layout/platform-island.js';
import '../components/worktracker-sidebar.js';
import '../components/work-item-detail-panel.js';
import '../pages/inbox-page.js';
import '../pages/my-tasks-page.js';
import '../pages/board-page.js';
import '../pages/queues-page.js';
import '../pages/queue-detail-page.js';
import '../pages/work-item-detail-page.js';
import '../modals/work-item-create-modal.js';
import '../modals/board-create-modal.js';
import '../modals/board-settings-modal.js';
import '../components/sheets/worktracker-task-properties-sheet.js';

const WORKTRACKER_ROUTES = [
    { key: 'inbox',            path: '',                              titleKey: 'routes.inbox' },
    { key: 'my',               path: 'my',                            parent: 'inbox', titleKey: 'routes.my' },
    { key: 'board',            path: 'board',                         parent: 'inbox', titleKey: 'routes.board' },
    { key: 'queues',           path: 'queues',                        parent: 'inbox', titleKey: 'routes.queues' },
    { key: 'queue_detail',     path: 'queues/:workQueueId',           parent: 'queues', titleKey: 'routes.queue_detail' },
    { key: 'work_item_detail', path: 'tasks/:workItemId',             parent: 'inbox', titleKey: 'routes.work_item_detail' },
];

const WORKTRACKER_BOTTOM_NAV_ITEMS = [
    { key: 'inbox',   routeKey: 'inbox',  icon: 'inbox',      labelKey: 'bottom_nav.inbox' },
    { key: 'board',   routeKey: 'board',  icon: 'list-check', labelKey: 'bottom_nav.board' },
    { key: 'profile', sheet: 'platform.service_switcher', icon: 'user', labelKey: 'bottom_nav.profile' },
];

export class WorktrackerApp extends PlatformApp {
    static defaultI18nNamespace = 'worktracker';
    static bottomNavHideOnRoutes = ['work_item_detail'];
    static platformAssistant = {
        branchId: 'worktracker',
        serviceId: 'worktracker',
        showLauncher: true,
    };

    static factories = [
        platformFileCreateOp,
        boardCreateForm,
        boardsResource,
        workQueuesResource,
        workQueueMembersListOp,
        workQueueMemberAddOp,
        workQueueMemberRemoveOp,
    ];

    static override get properties() {

        return {
        _detailWorkItemId: { state: true },
    

            ...PlatformApp.properties,

        };

    };

    static override styles = [
        PlatformApp.styles,
        css`
            :host {
                display: flex;
                flex-direction: row;
                width: var(--app-vw, 100vw);
                height: var(--app-vh, 100vh);
                overflow: hidden;
                background: var(--bg-gradient);
            }
            .sidebar {
                height: var(--app-vh, 100vh);
                flex-shrink: 0;
            }
            .workspace {
                flex: 1;
                min-width: 0;
                min-height: 0;
                display: grid;
                grid-template-columns: 1fr;
            }
            .workspace.detail-open {
                grid-template-columns: minmax(0, 1fr) var(--worktracker-panel-width);
            }
            .main {
                min-width: 0;
                min-height: 0;
                display: flex;
                flex-direction: column;
                padding: var(--space-4);
                overflow: hidden;
            }
            .main.task-detail {
                padding: 0;
            }
            platform-island {
                flex: 1;
                min-height: 0;
                min-width: 0;
            }
            platform-island[padding="none"] {
                padding: 0;
            }
            @media (max-width: 767px) {
                .main { padding: 0; }
                .main.task-detail { padding: 0; }
                .sidebar {
                    position: absolute;
                    width: 0;
                    height: 0;
                    overflow: visible;
                }
            }
        `,
    ];

    declare _detailWorkItemId: string;
    private _countsOp: OpController;
    private _routeSel: SelectController<unknown>;

    constructor() {
        super();
        this._detailWorkItemId = '';
        this._countsOp = this.useOp('worktracker/work_item_counts');
        this._routeSel = this.select((state) => state.router.routeKey);
        this.useEvent(WorktrackerUiEvents.DETAIL_OPEN, (event: PlatformEvent) => {
            this._openWorkItemDetailPanel(event.payload);
        });
        this.useEvent(CoreEvents.PLATFORM_WORK_ITEM_DETAIL_OPEN_REQUESTED, (event: PlatformEvent) => {
            this._openWorkItemDetailPanel(event.payload);
        });
        this.useEvent(WorktrackerUiEvents.DETAIL_CLOSE, () => {
            this._detailWorkItemId = '';
            replaceWorkItemUrl('');
        });
        this.useEvent(CoreEvents.ROUTER_ROUTE_CHANGED, (event: PlatformEvent) => {
            const payload = event.payload;
            if (!isPlainRecord(payload) || payload.routeKey !== 'work_item_detail') {
                return;
            }
            this._detailWorkItemId = '';
            replaceWorkItemUrl('');
        });
    }

    private _openWorkItemDetailPanel(payload: unknown) {
        if (!isPlainRecord(payload) || typeof payload.work_item_id !== 'string' || payload.work_item_id.length === 0) {
            throw new Error('WorktrackerApp: work_item_detail_open requires work_item_id');
        }
        const workItemId = payload.work_item_id;
        const routeKey = this._routeSel.value;
        if (routeKey === 'work_item_detail') {
            return;
        }
        this._detailWorkItemId = workItemId;
        replaceWorkItemUrl(workItemId);
    }

    override async connectedCallback(): Promise<void> {
        await super.connectedCallback();
        if (typeof window === 'undefined' || typeof window.location === 'undefined') {
            return;
        }
        const location = window.location;
        const fromPath = readWorkItemIdFromPathname(location.pathname);
        if (fromPath.length > 0) {
            return;
        }
        if (hasLegacyWorkItemQuery(location)) {
            const workItemId = readWorkItemIdFromLocation(location);
            this.dispatch(
                CoreEvents.ROUTER_NAVIGATE_REQUESTED,
                {
                    routeKey: 'work_item_detail',
                    params: { workItemId },
                    replace: true,
                },
                { source: 'local' },
            );
            return;
        }
        const workItemId = readWorkItemIdFromLocation(location);
        if (workItemId.length > 0) {
            this._detailWorkItemId = workItemId;
        }
    }

    getBottomNavItems() {
        const totalOpen = this._countsOp.state.total_open_count;
        const badge = typeof totalOpen === 'number' && totalOpen > 0 ? totalOpen : undefined;
        return WORKTRACKER_BOTTOM_NAV_ITEMS.map((item) => (
            item.key === 'inbox' ? { ...item, badge } : item
        ));
    }

    override getBaseUrl() { return '/worktracker'; }

    override getRoutes() { return []; }

    override getServiceEffects() {
        return [
            createRouterEffect({ baseUrl: '/worktracker', routes: WORKTRACKER_ROUTES }),
        ];
    }

    override shouldRenderPlatformAssistant(_routeKey: string | null) {
        return true;
    }

    override async getPlatformAssistantContextVariables(routeKey: string, params: Record<string, string>) {
        return buildWorktrackerAssistantContext(routeKey, params, this._detailWorkItemId);
    }

    private _renderPage(routeKey: string | null, params: Record<string, string>) {
        switch (routeKey) {
            case 'my':
                return html`<worktracker-my-tasks-page></worktracker-my-tasks-page>`;
            case 'board':
                return html`<worktracker-board-page></worktracker-board-page>`;
            case 'queues':
                return html`<worktracker-queues-page></worktracker-queues-page>`;
            case 'queue_detail':
                return html`<worktracker-queue-detail-page work-queue-id=${params.workQueueId}></worktracker-queue-detail-page>`;
            case 'work_item_detail':
                return html`<worktracker-work-item-detail-page work-item-id=${params.workItemId}></worktracker-work-item-detail-page>`;
            case 'inbox':
            default:
                return html`<worktracker-inbox-page></worktracker-inbox-page>`;
        }
    }

    override renderRoute(routeKey: string | null, params: Record<string, string>) {
        const isTaskDetail = routeKey === 'work_item_detail';
        const detailOpen = !isTaskDetail
            && typeof this._detailWorkItemId === 'string'
            && this._detailWorkItemId.length > 0;
        return html`
            <div class="sidebar"><worktracker-sidebar></worktracker-sidebar></div>
            <div class="workspace ${detailOpen ? 'detail-open' : ''}">
                <div class="main ${isTaskDetail ? 'task-detail' : ''}">
                    <platform-island padding=${isTaskDetail ? 'none' : 'md'} variant=${isTaskDetail ? 'subtle' : 'default'}>
                        ${this._renderPage(routeKey, params)}
                    </platform-island>
                </div>
                ${detailOpen ? html`
                    <work-item-detail-panel
                        panel-open
                        work-item-id=${this._detailWorkItemId}
                    ></work-item-detail-panel>
                ` : null}
            </div>
        `;
    }
}

customElements.define('worktracker-app', WorktrackerApp);
