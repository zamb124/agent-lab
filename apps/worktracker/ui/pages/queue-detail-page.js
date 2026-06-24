/**
 * QueueDetailPage — inbox очереди и участники.
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { worktrackerSurfacesStyles } from '../styles/worktracker-surfaces.styles.js';
import '@platform/lib/components/platform-user-chip.js';
import '../components/worktracker-work-item-card.js';
import '../components/worktracker-list-section.js';
import '../components/worktracker-page-header.js';
import '@platform/lib/components/fields/platform-field.js';

export class WorktrackerQueueDetailPage extends PlatformPage {
    static i18nNamespace = 'worktracker';

    static properties = {
        workQueueId: { type: String, attribute: 'work-queue-id' },
        _memberUserId: { state: true },
    };

    static styles = [
        PlatformPage.styles,
        buttonStyles,
        worktrackerSurfacesStyles,
        css`
            :host { display: flex; flex-direction: column; min-height: 0; flex: 1; width: 100%; }
            .sections { display: flex; flex-direction: column; gap: var(--space-6); }
            .section-title {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-secondary);
                margin-bottom: var(--space-2);
            }
            .rows { display: flex; flex-direction: column; gap: var(--space-2); }
            .members { display: flex; flex-direction: column; gap: var(--space-2); }
            .member-row {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-md);
                background: var(--glass-tint-subtle);
            }
            .add-row { display: flex; gap: var(--space-2); align-items: flex-end; flex-wrap: wrap; margin-bottom: var(--space-3); }
            .empty { padding: var(--space-4); color: var(--text-tertiary); text-align: center; }
        `,
    ];

    constructor() {
        super();
        this.workQueueId = '';
        this._memberUserId = '';
        this._workItems = this.useResource('worktracker/work_items');
        this._queues = this.useResource('worktracker/work_queues');
        this._membersOp = this.useOp('worktracker/work_queue_members_list');
        this._addMemberOp = this.useOp('worktracker/work_queue_member_add');
        this._removeMemberOp = this.useOp('worktracker/work_queue_member_remove');
    }

    connectedCallback() {
        super.connectedCallback();
        this._reload();
    }

    updated(changed) {
        super.updated(changed);
        if (changed.has('workQueueId')) {
            this._reload();
        }
    }

    _reload() {
        if (!this.workQueueId) {
            return;
        }
        this._queues.load({});
        this._workItems.load({
            work_queue_id: this.workQueueId,
            queue_unclaimed_only: true,
            exclude_terminal: true,
        });
        this._membersOp.run({ work_queue_id: this.workQueueId });
    }

    _queue() {
        const queues = this._queues.items || [];
        return queues.find((row) => row && row.work_queue_id === this.workQueueId) || null;
    }

    _addMember() {
        const userId = this._memberUserId.trim();
        if (!userId || !this.workQueueId) {
            return;
        }
        this._addMemberOp.run({
            work_queue_id: this.workQueueId,
            member: { actor_kind: 'user', user_id: userId },
            role: 'member',
        });
        this._memberUserId = '';
        this._membersOp.run({ work_queue_id: this.workQueueId });
    }

    _removeMember(userId) {
        if (!this.workQueueId || !userId) {
            return;
        }
        this._removeMemberOp.run({
            work_queue_id: this.workQueueId,
            member: { actor_kind: 'user', user_id: userId },
        });
        this._membersOp.run({ work_queue_id: this.workQueueId });
    }

    _renderMembers() {
        const members = this._membersOp.state.items || [];
        if (!Array.isArray(members) || members.length === 0) {
            return html`<div class="empty">${this.t('queue_detail_page.empty_members')}</div>`;
        }
        return html`
            <div class="members">
                ${members.map((row) => {
                    const member = row.member;
                    const userId = member && member.actor_kind === 'user' && typeof member.user_id === 'string'
                        ? member.user_id
                        : '';
                    if (!userId) {
                        return null;
                    }
                    return html`
                        <div class="member-row">
                            <platform-user-chip user-id=${userId} size="sm" .interactive=${false}></platform-user-chip>
                            <button class="btn btn-secondary" @click=${() => this._removeMember(userId)}>
                                ${this.t('queue_detail_page.remove_member')}
                            </button>
                        </div>
                    `;
                })}
            </div>
        `;
    }

    render() {
        const queue = this._queue();
        const items = this._workItems.items || [];
        const queueLabel = queue && typeof queue.name === 'string' ? queue.name : this.workQueueId;
        return html`
            <worktracker-page-header
                title=${this.t('queue_detail_page.title', { name: queueLabel })}
                show-breadcrumbs
                breadcrumb-label=${queueLabel}
            ></worktracker-page-header>
            <div class="wt-page sections">
                ${items.length > 0 ? html`
                    <worktracker-list-section title=${this.t('queue_detail_page.inbox')} .count=${items.length}>
                        ${items.map((item) => html`
                            <div class="wt-list-row">
                                <worktracker-work-item-card
                                    .item=${item}
                                    variant="row"
                                    ?show-preview=${false}
                                    @changed=${() => this._reload()}
                                ></worktracker-work-item-card>
                            </div>
                        `)}
                    </worktracker-list-section>
                ` : html`<div class="empty">${this.t('queue_detail_page.empty_inbox')}</div>`}
                <section class="wt-section">
                    <h2 class="wt-section-title">${this.t('queue_detail_page.members')}</h2>
                    <div class="add-row">
                        <platform-field
                            type="string"
                            mode="edit"
                            .label=${this.t('queue_detail_page.label_member_user_id')}
                            .value=${this._memberUserId}
                            @change=${(e) => {
                                this._memberUserId = e.detail && typeof e.detail.value === 'string' ? e.detail.value : '';
                            }}
                        ></platform-field>
                        <button class="btn btn-primary" @click=${() => this._addMember()}>
                            ${this.t('queue_detail_page.add_member')}
                        </button>
                    </div>
                    ${this._renderMembers()}
                </section>
            </div>
        `;
    }
}

customElements.define('worktracker-queue-detail-page', WorktrackerQueueDetailPage);
