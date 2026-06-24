/**
 * InboxPage — назначенные задачи и очередь inbox.
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
import { WorktrackerUiEvents } from '../events/worktracker-ui-events.js';
import { worktrackerSurfacesStyles } from '../styles/worktracker-surfaces.styles.js';
import '../components/worktracker-work-item-card.js';
import '../components/worktracker-icon-action.js';
import '../components/worktracker-list-section.js';
import '../components/worktracker-page-header.js';
import '@platform/lib/components/platform-icon.js';

export class WorktrackerInboxPage extends PlatformPage {
    static i18nNamespace = 'worktracker';

    static properties = {
        _assignedItems: { state: true },
        _queueItems: { state: true },
        _selectedWorkItemId: { state: true },
    };

    static styles = [
        PlatformPage.styles,
        worktrackerSurfacesStyles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                min-height: 0;
                flex: 1;
                width: 100%;
            }
        `,
    ];

    constructor() {
        super();
        this._assignedItems = [];
        this._queueItems = [];
        this._selectedWorkItemId = '';
        this._reloadGeneration = 0;
        this._workItems = this.useResource('worktracker/work_items');
        this._countsOp = this.useOp('platform/work_item_counts');
        this._userSel = this.select((s) => s.auth.user);
        this.useEvent(CoreEvents.AUTH_USER_LOADED, () => {
            this._reload();
        });
        this.useEvent(WorktrackerUiEvents.DETAIL_OPEN, (event) => {
            const payload = event.payload;
            if (!payload || typeof payload.work_item_id !== 'string') {
                throw new Error('WorktrackerInboxPage: detail_open requires work_item_id');
            }
            this._selectedWorkItemId = payload.work_item_id;
        });
        this.useEvent(CoreEvents.PLATFORM_WORK_ITEM_DETAIL_OPEN_REQUESTED, (event) => {
            const payload = event.payload;
            if (!payload || typeof payload.work_item_id !== 'string') {
                throw new Error('WorktrackerInboxPage: work_item_detail_open requires work_item_id');
            }
            this._selectedWorkItemId = payload.work_item_id;
        });
        this.useEvent(WorktrackerUiEvents.DETAIL_CLOSE, () => {
            this._selectedWorkItemId = '';
        });
        this.useEvent(this._workItems.resource.events.CREATED, () => {
            this._reload();
        });
    }

    connectedCallback() {
        super.connectedCallback();
        const user = this._userSel.value;
        if (user && typeof user.user_id === 'string' && user.user_id.length > 0) {
            this._reload();
        }
    }

    _awaitListLoaded(requestedId) {
        const events = this._workItems.resource.events;
        return new Promise((resolve, reject) => {
            let unsubLoaded = null;
            let unsubFailed = null;
            const cleanup = () => {
                if (typeof unsubLoaded === 'function') unsubLoaded();
                if (typeof unsubFailed === 'function') unsubFailed();
            };
            unsubLoaded = this.bus.subscribeType(events.LIST_LOADED, (event) => {
                if (!event || !event.meta || event.meta.causation_id !== requestedId) {
                    return;
                }
                cleanup();
                const payload = event.payload;
                if (!payload || !Array.isArray(payload.items)) {
                    reject(new Error('WorktrackerInboxPage: list_loaded payload.items required'));
                    return;
                }
                resolve(payload.items);
            });
            unsubFailed = this.bus.subscribeType(events.LIST_FAILED, (event) => {
                if (!event || !event.meta || event.meta.causation_id !== requestedId) {
                    return;
                }
                cleanup();
                const payload = event.payload;
                const message = payload && typeof payload.message === 'string' ? payload.message : 'work items list failed';
                reject(new Error(message));
            });
        });
    }

    async _reload() {
        const user = this._userSel.value;
        if (!user || typeof user.user_id !== 'string' || user.user_id.length === 0) {
            return;
        }
        const generation = this._reloadGeneration + 1;
        this._reloadGeneration = generation;
        this._assignedItems = [];
        this._queueItems = [];

        const assignedRequested = this._workItems.load({
            assignee_user_id: user.user_id,
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

        const queueRequested = this._workItems.load({
            queue_unclaimed_only: true,
            exclude_terminal: true,
        });
        if (!queueRequested || typeof queueRequested.id !== 'string') {
            throw new Error('WorktrackerInboxPage: queue list dispatch returned no event id');
        }
        const queueItems = await this._awaitListLoaded(queueRequested.id);
        if (generation !== this._reloadGeneration) {
            return;
        }
        this._queueItems = queueItems;
        this._countsOp.run({});
    }

    _renderRow(item) {
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

    _renderEmpty(messageKey) {
        return html`
            <div class="wt-empty">
                <platform-icon class="wt-empty-icon" name="inbox" size="48"></platform-icon>
                <p class="wt-empty-title">${this.t(messageKey)}</p>
            </div>
        `;
    }

    _openCreateTask() {
        this.openModal('worktracker.work_item_create', {});
    }

    render() {
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
                ${this._assignedItems.length > 0 ? html`
                    <worktracker-list-section
                        title=${this.t('inbox_page.section_assigned')}
                        .count=${this._assignedItems.length}
                    >
                        ${this._assignedItems.map((item) => this._renderRow(item))}
                    </worktracker-list-section>
                ` : this._renderEmpty('inbox_page.empty_assigned')}
                ${this._queueItems.length > 0 ? html`
                    <worktracker-list-section
                        title=${this.t('inbox_page.section_queue')}
                        .count=${this._queueItems.length}
                    >
                        ${this._queueItems.map((item) => this._renderRow(item))}
                    </worktracker-list-section>
                ` : this._renderEmpty('inbox_page.empty_queue')}
            </div>
        `;
    }
}

customElements.define('worktracker-inbox-page', WorktrackerInboxPage);
