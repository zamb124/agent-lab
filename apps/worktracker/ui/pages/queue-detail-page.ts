/**
 * QueueDetailPage — inbox очереди и участники.
 *
 * Участники добавляются из `state.team.members` (поиск по имени/email), не по raw user_id.
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';
import type { OpController, ResourceController } from '@platform/lib/base/use-resource.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';
import type { TeamMemberRecord } from '@platform/lib/events/reducers/team.js';
import { TEAM_EVENTS } from '@platform/lib/events/index.js';
import { worktrackerSurfacesStyles } from '../styles/worktracker-surfaces.styles.js';
import '@platform/lib/components/platform-user-chip.js';
import '@platform/lib/components/platform-empty-state.js';
import '../components/worktracker-work-item-card.js';
import '../components/worktracker-list-section.js';
import '../components/worktracker-page-header.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import type { PropertyValues } from 'lit';

function missingAsEmpty(value: unknown): string {
    if (value === undefined || value === null) return '';
    return String(value);
}

function listOrEmpty(value: unknown, label: string): unknown[] {
    if (value === undefined || value === null) return [];
    if (!Array.isArray(value)) throw new Error(`${label} must be an array`);
    return value;
}

function queueMemberUserIds(items: unknown[]): string[] {
    const ids: string[] = [];
    for (const row of items) {
        if (!isPlainRecord(row)) continue;
        const member = row.member;
        if (!isPlainRecord(member)) continue;
        if (member.actor_kind !== 'user') continue;
        const userId = member.user_id;
        if (typeof userId !== 'string' || userId.length === 0) continue;
        ids.push(userId);
    }
    return ids;
}

export class WorktrackerQueueDetailPage extends PlatformPage {
    static i18nNamespace = 'worktracker';
    declare workQueueId: string;
    declare _membersFilter: string;


    static override properties = {
        workQueueId: { type: String, attribute: 'work-queue-id' },
        _membersFilter: { state: true },
    };

    static override styles = [
        PlatformPage.styles,
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

    private _workItems: ResourceController;
    private _queues: ResourceController;
    private _membersOp: OpController;
    private _addMemberOp: OpController;
    private _removeMemberOp: OpController;
    private _teamMembersSel: SelectController<TeamMemberRecord[]>;
    private _teamLoadingSel: SelectController<boolean>;

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

    override connectedCallback() {
        super.connectedCallback();
        this._ensureTeamMembers();
        this._reload();
    }

    override updated(changed: PropertyValues<this>) {
        super.updated(changed);
        if (changed.has('workQueueId')) {
            this._reload();
        }
    }

    private _ensureTeamMembers() {
        const members = this._teamMembersSel.value;
        const loading = this._teamLoadingSel.value;
        if (members.length === 0 && loading === false) {
            this.dispatch(TEAM_EVENTS.MEMBERS_LOAD_REQUESTED, null);
        }
    }

    private _reload() {
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

    private _queue(): Record<string, unknown> | null {
        const queues = this._queues.items;
        const found = queues.find((row) => row && row.work_queue_id === this.workQueueId);
        return found === undefined ? null : found;
    }

    private _memberUserIds(): Set<string> {
        return new Set(queueMemberUserIds(listOrEmpty(this._membersOp.state.items, 'worktracker queue members')));
    }

    private _candidateMembers(): TeamMemberRecord[] {
        const team = this._teamMembersSel.value;
        const already = this._memberUserIds();
        const q = this._membersFilter.trim().toLowerCase();
        return team
            .filter((m) => m && typeof m.user_id === 'string' && m.user_id.length > 0 && !already.has(m.user_id as string))
            .filter((m) => {
                if (q.length === 0) {
                    return true;
                }
                const name = typeof m.name === 'string' ? m.name.toLowerCase() : '';
                const email = typeof m.email === 'string' ? m.email.toLowerCase() : '';
                return name.includes(q) || email.includes(q) || (m.user_id as string).toLowerCase().includes(q);
            });
    }

    private _addMember(userId: string) {
        if (!userId || !this.workQueueId) {
            return;
        }
        this._addMemberOp.run({
            work_queue_id: this.workQueueId,
            member: { actor_kind: 'user', user_id: userId },
            role: 'member',
        });
    }

    private _removeMember(userId: string) {
        if (!this.workQueueId || !userId) {
            return;
        }
        this._removeMemberOp.run({
            work_queue_id: this.workQueueId,
            member: { actor_kind: 'user', user_id: userId },
        });
    }

    private _renderMembers() {
        const members = queueMemberUserIds(listOrEmpty(this._membersOp.state.items, 'worktracker queue members'));
        if (members.length === 0) {
            return html`<platform-empty-state icon="users" title=${this.t('queue_detail_page.empty_members')}></platform-empty-state>`;
        }
        return html`
            <div class="members">
                ${members.map((userId) => html`
                    <div class="member-row">
                        <platform-user-chip user-id=${userId} size="sm" .interactive=${false}></platform-user-chip>
                        <platform-button
                            variant="ghost"
                            danger
                            icon-only
                            density="dense"
                            title=${this.t('queue_detail_page.remove_member')}
                            aria-label=${this.t('queue_detail_page.remove_member')}
                            @click=${() => this._removeMember(userId)}
                        ><platform-icon name="x" size="16"></platform-icon></platform-button>
                    </div>
                `)}
            </div>
        `;
    }

    private _renderCandidates() {
        const candidates = this._candidateMembers();
        const teamLoading = this._teamLoadingSel.value;
        if (teamLoading && candidates.length === 0) {
            return html`<p class="hint"><platform-spinner size="xs"></platform-spinner> ${this.t('queue_detail_page.members_loading')}</p>`;
        }
        if (candidates.length === 0) {
            return html`<p class="hint">${this.t('queue_detail_page.no_candidates')}</p>`;
        }
        return html`
            <div class="candidates">
                ${candidates.map((m: TeamMemberRecord) => html`
                    <button
                        type="button"
                        class="candidate-row"
                        @click=${() => this._addMember(missingAsEmpty(m.user_id))}
                    >
                        <platform-user-chip user-id=${missingAsEmpty(m.user_id)} size="sm" .interactive=${false}></platform-user-chip>
                        <span>${this.t('queue_detail_page.add_member')}</span>
                    </button>
                `)}
            </div>
        `;
    }

    override render() {
        const queue = this._queue();
        const items = this._workItems.items;
        const queueLabel = queue && typeof queue.name === 'string' ? queue.name : this.workQueueId;
        return html`
            <worktracker-page-header
                title=${this.t('queue_detail_page.title', { name: queueLabel })}
                show-breadcrumbs
                breadcrumb-label=${queueLabel}
            ></worktracker-page-header>
            <div class="wt-page sections">
                ${this._workItems.loading && items.length === 0
                    ? html`<platform-empty-state loading></platform-empty-state>`
                : items.length > 0 ? html`
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
                ` : html`<platform-empty-state icon="inbox" title=${this.t('queue_detail_page.empty_inbox')}></platform-empty-state>`}
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
                            @change=${(e: CustomEvent<{ value?: unknown }>) => {
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
