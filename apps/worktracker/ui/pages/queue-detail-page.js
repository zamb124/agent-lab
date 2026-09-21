/**
 * QueueDetailPage — inbox очереди и участники.
 *
 * Участники добавляются из `state.team.members` (поиск по имени/email), не по raw user_id.
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { TEAM_EVENTS } from '@platform/lib/events/index.js';
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
        _membersFilter: { state: true },
    };

    static styles = [
        PlatformPage.styles,
        buttonStyles,
        worktrackerSurfacesStyles,
        css`
            :host { display: flex; flex-direction: column; min-height: 0; flex: 1; width: 100%; }
            .sections { display: flex; flex-direction: column; gap: var(--space-6); }
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
            .add-block {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                margin-bottom: var(--space-3);
            }
            .candidates {
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
                max-height: 16rem;
                overflow-y: auto;
            }
            .candidate-row {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                border: none;
                border-radius: var(--radius-md);
                background: var(--bg-primary);
                cursor: pointer;
                text-align: left;
                width: 100%;
                color: inherit;
            }
            .candidate-row:hover {
                background: var(--glass-tint-subtle);
            }
            .empty { padding: var(--space-4); color: var(--text-tertiary); text-align: center; }
            .hint { font-size: var(--text-sm); color: var(--text-secondary); margin: 0; }
        `,
    ];

    constructor() {
        super();
        this.workQueueId = '';
        this._membersFilter = '';
        this._workItems = this.useResource('worktracker/work_items');
        this._queues = this.useResource('worktracker/work_queues');
        this._membersOp = this.useOp('worktracker/work_queue_members_list');
        this._addMemberOp = this.useOp('worktracker/work_queue_member_add');
        this._removeMemberOp = this.useOp('worktracker/work_queue_member_remove');
        this._teamMembersSel = this.select((s) => s.team.members);
        this._teamLoadingSel = this.select((s) => s.team.loading);
    }

    connectedCallback() {
        super.connectedCallback();
        this._ensureTeamMembers();
        this._reload();
    }

    updated(changed) {
        super.updated(changed);
        if (changed.has('workQueueId')) {
            this._reload();
        }
    }

    _ensureTeamMembers() {
        const members = this._teamMembersSel.value;
        const loading = this._teamLoadingSel.value;
        if ((!Array.isArray(members) || members.length === 0) && !loading) {
            this.dispatch(TEAM_EVENTS.MEMBERS_LOAD_REQUESTED, null);
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

    _memberUserIds() {
        const members = this._membersOp.state.items || [];
        const ids = new Set();
        if (!Array.isArray(members)) {
            return ids;
        }
        for (const row of members) {
            const member = row && row.member;
            if (member && member.actor_kind === 'user' && typeof member.user_id === 'string' && member.user_id.length > 0) {
                ids.add(member.user_id);
            }
        }
        return ids;
    }

    _candidateMembers() {
        const team = this._teamMembersSel.value;
        if (!Array.isArray(team)) {
            return [];
        }
        const already = this._memberUserIds();
        const q = this._membersFilter.trim().toLowerCase();
        return team
            .filter((m) => m && typeof m.user_id === 'string' && m.user_id.length > 0 && !already.has(m.user_id))
            .filter((m) => {
                if (q.length === 0) {
                    return true;
                }
                const name = typeof m.name === 'string' ? m.name.toLowerCase() : '';
                const email = typeof m.email === 'string' ? m.email.toLowerCase() : '';
                return name.includes(q) || email.includes(q) || m.user_id.toLowerCase().includes(q);
            });
    }

    _addMember(userId) {
        if (!userId || !this.workQueueId) {
            return;
        }
        this._addMemberOp.run({
            work_queue_id: this.workQueueId,
            member: { actor_kind: 'user', user_id: userId },
            role: 'member',
        });
    }

    _removeMember(userId) {
        if (!this.workQueueId || !userId) {
            return;
        }
        this._removeMemberOp.run({
            work_queue_id: this.workQueueId,
            member: { actor_kind: 'user', user_id: userId },
        });
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

    _renderCandidates() {
        const candidates = this._candidateMembers();
        const teamLoading = this._teamLoadingSel.value;
        if (teamLoading && candidates.length === 0) {
            return html`<p class="hint">${this.t('queue_detail_page.members_loading')}</p>`;
        }
        if (candidates.length === 0) {
            return html`<p class="hint">${this.t('queue_detail_page.no_candidates')}</p>`;
        }
        return html`
            <div class="candidates">
                ${candidates.map((m) => html`
                    <button
                        type="button"
                        class="candidate-row"
                        @click=${() => this._addMember(m.user_id)}
                    >
                        <platform-user-chip user-id=${m.user_id} size="sm" .interactive=${false}></platform-user-chip>
                        <span>${this.t('queue_detail_page.add_member')}</span>
                    </button>
                `)}
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
                    <p class="hint">${this.t('queue_detail_page.members_hint')}</p>
                    <div class="add-block">
                        <platform-field
                            type="string"
                            mode="edit"
                            input-type="search"
                            .label=${this.t('queue_detail_page.members_filter')}
                            .placeholder=${this.t('queue_detail_page.members_filter_placeholder')}
                            .value=${this._membersFilter}
                            @change=${(e) => {
                                if (!e.detail || typeof e.detail.value !== 'string') {
                                    throw new Error('queue-detail: members filter expects detail.value string');
                                }
                                this._membersFilter = e.detail.value;
                            }}
                        ></platform-field>
                        ${this._renderCandidates()}
                    </div>
                    ${this._renderMembers()}
                </section>
            </div>
        `;
    }
}

customElements.define('worktracker-queue-detail-page', WorktrackerQueueDetailPage);
