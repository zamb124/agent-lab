/**
 * InboxPage — назначенные задачи и inbox очередей (только очереди, где юзер — member).
 */

import { html, css, nothing } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import type { PlatformEvent } from '@platform/lib/events/contract.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';
import type { OpController, ResourceController } from '@platform/lib/base/use-resource.js';
import type { WorkItemLike } from '../_helpers/work-item-detail-shared.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';
import type { AuthUser } from '@platform/lib/events/reducers/auth.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
import { WorktrackerUiEvents } from '../events/types.js';
import { worktrackerSurfacesStyles } from '../styles/worktracker-surfaces.styles.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import '../components/worktracker-work-item-card.js';
import '../components/worktracker-icon-action.js';
import '../components/worktracker-list-section.js';
import '../components/worktracker-page-header.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-empty-state.js';

function eventRecord(payload: unknown): Record<string, unknown> | null {
    return isPlainRecord(payload) ? payload : null;
}

function workItemLike(value: unknown): WorkItemLike | null {
    if (!isPlainRecord(value)) return null;
    const workItemId = value.work_item_id;
    if (typeof workItemId !== 'string' || workItemId.length === 0) return null;
    const item: WorkItemLike = {};
    for (const [key, field] of Object.entries(value)) item[key] = field;
    item.work_item_id = workItemId;
    return item;
}

function workItemList(value: unknown): WorkItemLike[] {
    if (!Array.isArray(value)) {
        throw new Error('WorktrackerInboxPage: list_loaded payload.items required');
    }
    const items: WorkItemLike[] = [];
    for (const entry of value) {
        const item = workItemLike(entry);
        if (item === null) {
            throw new Error('WorktrackerInboxPage: list item work_item_id required');
        }
        items.push(item);
    }
    return items;
}

export class WorktrackerInboxPage extends PlatformPage {
    static i18nNamespace = 'worktracker';
    declare _assignedItems: WorkItemLike[];
    declare _queueItems: WorkItemLike[];
    declare _selectedWorkItemId: string;
    declare _memberQueueIds: string[];
    declare _queuesLoaded: boolean;
    private _reloadGeneration: number;
    private _workItems: ResourceController;
    private _countsOp: OpController;
    private _userSel: SelectController<AuthUser | null>;


    static override properties = {
        _assignedItems: { state: true },
        _queueItems: { state: true },
        _selectedWorkItemId: { state: true },
        _memberQueueIds: { state: true },
        _queuesLoaded: { state: true },
    };

    static override styles = [
        PlatformPage.styles,
        buttonStyles,
        worktrackerSurfacesStyles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                min-height: 0;
                flex: 1;
                width: 100%;
            }
            .queue-empty-cta {
                margin-top: var(--space-3);
            }
        `,
    ];

    constructor() {
        super();
        this._assignedItems = [];
        this._queueItems = [];
        this._selectedWorkItemId = '';
        this._memberQueueIds = [];
        this._queuesLoaded = false;
        this._reloadGeneration = 0;
        this._workItems = this.useResource('worktracker/work_items');
        this._countsOp = this.useOp('worktracker/work_item_counts');
        this._userSel = this.select((s) => s.auth.user);
        this.useEvent(CoreEvents.AUTH_USER_LOADED, () => {
            this._reload();
        });
        this.useEvent(WorktrackerUiEvents.DETAIL_OPEN, (event: PlatformEvent) => {
            const payload = eventRecord(event.payload);
            const workItemId = payload === null ? undefined : payload.work_item_id;
            if (typeof workItemId !== 'string') {
                throw new Error('WorktrackerInboxPage: detail_open requires work_item_id');
            }
            this._selectedWorkItemId = workItemId;
        });
        this.useEvent(CoreEvents.PLATFORM_WORK_ITEM_DETAIL_OPEN_REQUESTED, (event: PlatformEvent) => {
            const payload = eventRecord(event.payload);
            const workItemId = payload === null ? undefined : payload.work_item_id;
            if (typeof workItemId !== 'string') {
                throw new Error('WorktrackerInboxPage: work_item_detail_open requires work_item_id');
            }
            this._selectedWorkItemId = workItemId;
        });
        this.useEvent(WorktrackerUiEvents.DETAIL_CLOSE, () => {
            this._selectedWorkItemId = '';
        });
        this.useEvent(this._workItems.resource.events.CREATED, (event: PlatformEvent) => {
            const payload = eventRecord(event.payload);
            const item = payload === null ? null : workItemLike(payload.item);
            if (item === null) {
                throw new Error('WorktrackerInboxPage: CREATED payload.item.work_item_id required');
            }
            this._mergeCreatedItem(item);
        });
    }

    override connectedCallback() {
        super.connectedCallback();
        if (this._currentUserId().length > 0) {
            void this._reload();
        }
    }

    private _awaitListLoaded(requestedId: string): Promise<WorkItemLike[]> {
        const events = this._workItems.resource.events;
        return new Promise((resolve, reject) => {
            let unsubLoaded: (() => void) | null = null;
            let unsubFailed: (() => void) | null = null;
            const cleanup = () => {
                if (typeof unsubLoaded === 'function') unsubLoaded();
                if (typeof unsubFailed === 'function') unsubFailed();
            };
            unsubLoaded = this.bus.subscribeType(events.LIST_LOADED, (event: PlatformEvent) => {
                if (!event || !event.meta || event.meta.causation_id !== requestedId) {
                    return;
                }
                cleanup();
                const payload = eventRecord(event.payload);
                if (payload === null || !Array.isArray(payload.items)) {
                    reject(new Error('WorktrackerInboxPage: list_loaded payload.items required'));
                    return;
                }
                resolve(workItemList(payload.items));
            });
            unsubFailed = this.bus.subscribeType(events.LIST_FAILED, (event: PlatformEvent) => {
                if (!event || !event.meta || event.meta.causation_id !== requestedId) {
                    return;
                }
                cleanup();
                const payload = eventRecord(event.payload);
                const message = payload !== null && typeof payload.message === 'string' ? payload.message : 'work items list failed';
                reject(new Error(message));
            });
        });
    }

    private _memberQueueIdsFromSummary(summary: unknown): string[] {
        if (!isPlainRecord(summary)) {
            throw new Error('WorktrackerInboxPage: mine summary result required');
        }
        const ids = summary.work_queue_ids;
        if (!Array.isArray(ids)) {
            throw new Error('WorktrackerInboxPage: mine summary.work_queue_ids required');
        }
        return ids.filter((id) => typeof id === 'string' && id.length > 0);
    }

    private _currentUserId(): string {
        const user = this._userSel.value;
        if (user === null) return '';
        const userId = user.user_id;
        return typeof userId === 'string' ? userId : '';
    }

    private _mergeCreatedItem(item: WorkItemLike) {
        const userId = this._currentUserId();
        if (userId.length === 0) {
            return;
        }
        const assignment = item.assignment && typeof item.assignment === 'object' ? item.assignment : null;
        if (!assignment || typeof assignment.assignee_kind !== 'string') {
            return;
        }
        if (assignment.assignee_kind === 'users') {
            const userIds = Array.isArray(assignment.user_ids) ? assignment.user_ids : [];
            if (userIds.includes(userId)) {
                if (!this._assignedItems.some((row) => row && row.work_item_id === item.work_item_id)) {
                    this._assignedItems = [item, ...this._assignedItems];
                }
            }
            return;
        }
        if (assignment.assignee_kind === 'queue') {
            const queueId = typeof assignment.work_queue_id === 'string' ? assignment.work_queue_id : null;
            const claimedBy = typeof assignment.claimed_by_user_id === 'string'
                ? assignment.claimed_by_user_id
                : null;
            if (
                queueId !== null
                && this._memberQueueIds.includes(queueId)
                && claimedBy === null
            ) {
                if (!this._queueItems.some((row) => row && row.work_item_id === item.work_item_id)) {
                    this._queueItems = [item, ...this._queueItems];
                }
            }
        }
    }

    private async _reload(): Promise<void> {
        const userId = this._currentUserId();
        if (userId.length === 0) {
            return;
        }
        const generation = this._reloadGeneration + 1;
        this._reloadGeneration = generation;
        this._assignedItems = [];
        this._queueItems = [];
        this._queuesLoaded = false;

        const assignedRequested = this._workItems.load({
            assignee_user_id: userId,
            exclude_terminal: true,
        });
        if (!assignedRequested || typeof assignedRequested.id !== 'string') {
            throw new Error('WorktrackerInboxPage: assignee list dispatch returned no event id');
        }
        const assignedItems = await this._awaitListLoaded(assignedRequested.id);
        if (generation !== this._reloadGeneration) {
            return;
        }
        this._assignedItems = assignedItems;

        const summary = await this._countsOp.run({});
        if (generation !== this._reloadGeneration) {
            return;
        }
        if (summary === null) {
            throw new Error('WorktrackerInboxPage: mine summary failed');
        }
        const memberQueueIds = this._memberQueueIdsFromSummary(summary);
        this._memberQueueIds = memberQueueIds;
        this._queuesLoaded = true;

        if (memberQueueIds.length === 0) {
            this._queueItems = [];
            return;
        }

        const queueRequested = this._workItems.load({
            queue_unclaimed_only: true,
            exclude_terminal: true,
            work_queue_ids: memberQueueIds,
        });
        if (!queueRequested || typeof queueRequested.id !== 'string') {
            throw new Error('WorktrackerInboxPage: queue list dispatch returned no event id');
        }
        const queueItems = await this._awaitListLoaded(queueRequested.id);
        if (generation !== this._reloadGeneration) {
            return;
        }
        this._queueItems = queueItems;
    }

    private _renderRow(item: WorkItemLike) {
        const workItemId = item.work_item_id;
        const selected = this._selectedWorkItemId === workItemId;
        return html`
            <div class="wt-list-row" ?selected=${selected}>
                <worktracker-work-item-card
                    .item=${item}
                    variant="row"
                    ?selected=${selected}
                    show-preview
                    @changed=${() => this._reload()}
                ></worktracker-work-item-card>
            </div>
        `;
    }

    private _renderEmpty(messageKey: string) {
        return html`
            <platform-empty-state icon="inbox" title=${this.t(messageKey)}></platform-empty-state>
        `;
    }

    private _renderNoQueueMembership() {
        return html`
            <platform-empty-state icon="inbox" title=${this.t('inbox_page.empty_no_queue_membership')}>
                <button
                    type="button"
                    class="btn btn-primary queue-empty-cta"
                    @click=${() => this.navigate('queues', {})}
                >${this.t('inbox_page.go_to_queues')}</button>
            </platform-empty-state>
        `;
    }

    private _renderAssignedSection() {
        return html`
            <worktracker-list-section
                title=${this.t('inbox_page.section_assigned')}
                .count=${this._assignedItems.length}
            >
                ${this._assignedItems.map((item) => this._renderRow(item))}
            </worktracker-list-section>
        `;
    }

    private _renderQueueSection() {
        return html`
            <worktracker-list-section
                title=${this.t('inbox_page.section_queue')}
                .count=${this._queueItems.length}
            >
                ${this._queueItems.map((item) => this._renderRow(item))}
            </worktracker-list-section>
        `;
    }

    private _renderBody() {
        const hasAssigned = this._assignedItems.length > 0;
        const hasQueue = this._queueItems.length > 0;
        if (!this._queuesLoaded) {
            return hasAssigned ? this._renderAssignedSection() : this._renderEmpty('inbox_page.empty_assigned');
        }
        if (this._memberQueueIds.length === 0) {
            return hasAssigned
                ? this._renderAssignedSection()
                : this._renderNoQueueMembership();
        }
        if (!hasAssigned && !hasQueue) {
            return this._renderEmpty('inbox_page.empty_all');
        }
        return html`
            ${hasAssigned ? this._renderAssignedSection() : nothing}
            ${hasQueue ? this._renderQueueSection() : nothing}
        `;
    }

    private _openCreateTask() {
        this.openModal('worktracker.work_item_create', {});
    }

    override render() {
        return html`
            <worktracker-page-header title=${this.t('inbox_page.title')}>
                <worktracker-icon-action
                    slot="actions"
                    icon="plus"
                    .title=${this.t('inbox_page.create_task')}
                    @action=${() => this._openCreateTask()}
                ></worktracker-icon-action>
            </worktracker-page-header>
            <div class="wt-page">
                ${this._renderBody()}
            </div>
        `;
    }
}

customElements.define('worktracker-inbox-page', WorktrackerInboxPage);
