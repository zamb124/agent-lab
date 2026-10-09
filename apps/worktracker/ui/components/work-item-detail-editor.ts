/**
 * WorkItemDetailEditor — orchestrator for task detail (panel / page / inspector-only).
 */

import { html, css, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
import { TEAM_EVENTS } from '@platform/lib/events/index.js';
import {
    WORK_ITEM_EVENTS,
    WORK_ITEM_MUTATION_SUCCEEDED,
} from '@platform/lib/events/resources/work-items.resource.js';
import {
    TERMINAL_STATES,
    WORK_ITEM_STATES,
    WORK_ITEM_PRIORITIES,
    assigneeIsQueue,
    assigneeUserId,
    queueUnclaimed,
    workItemFromEventPayload,
    workItemAllowsSilentComplete,
} from '../_helpers/work-item-detail-shared.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { normalizeIsoDateTimeForField } from '@platform/lib/utils/format-platform-date.js';
import { worktrackerDetailEditorLayoutStyles } from '../styles/worktracker-detail-editor-layout.styles.js';
import { worktrackerSurfacesStyles } from '../styles/worktracker-surfaces.styles.js';
import './worktracker-detail-content.js';
import './worktracker-activity-thread.js';
import './worktracker-detail-inspector.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/flow-ui/components/platform-flow-ui.js';
import '@platform/lib/components/glass-spinner.js';
import type { CSSResultGroup, PropertyValues } from 'lit';
import type { PlatformEvent } from '@platform/lib/events/contract.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';
import type { OpController, ResourceController } from '@platform/lib/base/use-resource.js';
import type { WorkItemLike } from '../_helpers/work-item-detail-shared.js';

interface TeamMemberLike {
    user_id?: unknown;
    name?: unknown;
    [key: string]: unknown;
}

interface TeamSlice {
    members?: TeamMemberLike[];
    loading?: boolean;
}

interface WorkItemRecord extends WorkItemLike {
    work_item_id: string;
}

export class WorkItemDetailEditor extends PlatformElement {
    static i18nNamespace = 'worktracker';
    declare workItemId: string;
    declare layout: string;
    declare active: boolean;
    declare _titleDraft: string;
    declare _descriptionDraft: string;
    declare _commentDraft: string;
    declare _labelsDraft: unknown[];
    declare _dueDateDraft: string;
    declare _attachmentsDraft: Record<string, unknown>[];
    declare _variablesDraft: Record<string, unknown>;
    declare _commentFilesDraft: unknown[];
    declare _savingTitle: boolean;
    declare _savingDescription: boolean;
    declare _propertiesExpanded: boolean;
    declare _isMobile: boolean;
    private _workItems: ResourceController;
    private _boards: ResourceController;
    private _queues: ResourceController;
    private _commentsOp: OpController;
    private _claimOp: OpController;
    private _completeOp: OpController;
    private _cancelOp: OpController;
    private _commentOp: OpController;
    private _moveOp: OpController;
    private _assignOp: OpController;
    private _localeSel: SelectController<unknown>;
    private _teamSel: SelectController<TeamMemberLike[] | undefined>;
    private _teamLoadingSel: SelectController<boolean | undefined>;
    private _mql: MediaQueryList | null = null;


    static override properties = {
        workItemId: { type: String, attribute: 'work-item-id' },
        layout: { type: String },
        active: { type: Boolean },
        _titleDraft: { state: true },
        _descriptionDraft: { state: true },
        _commentDraft: { state: true },
        _labelsDraft: { state: true },
        _dueDateDraft: { state: true },
        _attachmentsDraft: { state: true },
        _variablesDraft: { state: true },
        _commentFilesDraft: { state: true },
        _savingTitle: { state: true },
        _savingDescription: { state: true },
        _propertiesExpanded: { state: true },
        _isMobile: { state: true },
    };

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        buttonStyles,
        worktrackerSurfacesStyles,
        worktrackerDetailEditorLayoutStyles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                min-height: 0;
                min-width: 0;
                flex: 1;
            }
            :host([layout="page"]) {
                display: flex;
                flex-direction: row;
                align-items: flex-start;
                flex-wrap: nowrap;
                flex: 1 1 auto;
                align-self: stretch;
                width: 100%;
                height: auto;
                min-width: 0;
                gap: var(--space-5);
            }
            :host([layout="page"]) .wt-page-main {
                flex: 1 1 0;
                min-width: 0;
            }
            :host([layout="page"]) .wt-inspector-sticky {
                flex: 0 0 var(--worktracker-inspector-width);
                width: var(--worktracker-inspector-width);
            }
            :host([layout="panel"]) {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }
            :host([layout="inspector-only"]) {
                display: block;
            }
            :host([layout="inspector-only"]) worktracker-detail-inspector {
                width: 100%;
            }
            .wt-page-main,
            .wt-panel-stack {
                min-width: 0;
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
                height: auto;
            }
            .wt-page-main worktracker-detail-content,
            .wt-page-main worktracker-activity-thread {
                flex: 0 0 auto;
                width: 100%;
            }
            .wt-detail-card {
                display: flex;
                flex-direction: column;
                width: 100%;
                height: auto;
                box-sizing: border-box;
            }
            .wt-inspector-card {
                width: 100%;
                box-sizing: border-box;
                padding: var(--worktracker-surface-padding);
            }
            .wt-hitl {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                min-width: 0;
            }
            .wt-hitl-title {
                margin: 0;
                font-size: var(--font-size-sm);
                font-weight: 600;
                color: var(--text-secondary);
            }
            .wt-hitl-hint {
                margin: 0;
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                line-height: 1.4;
            }
            .wt-hitl-chat {
                display: flex;
                flex-direction: column;
                min-height: 360px;
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-lg);
                overflow: hidden;
            }
            /*
             * Conversation shell is height:100% and does not size to content.
             * min-height is not a specified height for % children — page layout
             * is document-flow (height:auto), so the host must set a real height.
             */
            :host([layout="page"]) .wt-hitl-chat {
                height: min(70vh, 40rem);
                min-height: 22rem;
            }
            .wt-hitl-chat platform-flow-ui {
                flex: 1 1 auto;
                align-self: stretch;
                width: 100%;
                min-width: 0;
                min-height: 0;
                height: 100%;
            }
            .wt-hitl-complete {
                display: flex;
                justify-content: flex-end;
            }
        `,
    ];

    constructor() {
        super();
        this.workItemId = '';
        this.layout = 'panel';
        this.active = true;
        this._titleDraft = '';
        this._descriptionDraft = '';
        this._commentDraft = '';
        this._labelsDraft = [];
        this._dueDateDraft = '';
        this._attachmentsDraft = [];
        this._variablesDraft = {};
        this._commentFilesDraft = [];
        this._savingTitle = false;
        this._savingDescription = false;
        this._propertiesExpanded = false;
        this._isMobile = false;
        this._workItems = this.useResource('worktracker/work_items');
        this._boards = this.useResource('worktracker/boards');
        this._queues = this.useResource('worktracker/work_queues');
        this._commentsOp = this.useOp('worktracker/work_item_comments_list');
        this._claimOp = this.useOp('worktracker/work_item_claim');
        this._completeOp = this.useOp('worktracker/work_item_complete');
        this._cancelOp = this.useOp('worktracker/work_item_cancel');
        this._commentOp = this.useOp('worktracker/work_item_comment');
        this._moveOp = this.useOp('worktracker/work_item_move');
        this._assignOp = this.useOp('worktracker/work_item_assign');
        this._localeSel = this.select((state) => (state.i18n as Record<string, unknown>).locale);
        this._teamSel = this.select((s) => (s.team as TeamSlice).members);
        this._teamLoadingSel = this.select((s) => (s.team as TeamSlice).loading);

        const syncItem = (event: PlatformEvent) => {
            const item = workItemFromEventPayload(event.payload);
            if (!item || typeof item.work_item_id !== 'string' || item.work_item_id !== this.workItemId) {
                return;
            }
            this._applyItemDrafts(item as WorkItemRecord);
        };

        this.useEvent(this._workItems.resource.events.ITEM_LOADED, syncItem);
        this.useEvent(this._workItems.resource.events.UPDATED, syncItem);
        for (const eventType of WORK_ITEM_MUTATION_SUCCEEDED) {
            this.useEvent(eventType, syncItem);
        }
        for (const eventType of WORK_ITEM_EVENTS) {
            this.useEvent(eventType, syncItem);
        }
        this.useEvent('worktracker/work_item_comment/succeeded', () => {
            if (this.active && this.workItemId) {
                this._commentsOp.run({ work_item_id: this.workItemId });
            }
        });
        this.useEvent(CoreEvents.AUTH_USER_LOADED, () => {
            if (this.active && this.workItemId) {
                this._load();
            }
        });
        this._onMqlChange = this._onMqlChange.bind(this);
    }

    override connectedCallback() {
        super.connectedCallback();
        this._ensureTeamMembers();
        if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
            this._mql = window.matchMedia('(max-width: 767px)');
            this._isMobile = this._mql.matches;
            this._mql.addEventListener('change', this._onMqlChange);
        }
    }

    override disconnectedCallback() {
        super.disconnectedCallback();
        if (this._mql) {
            this._mql.removeEventListener('change', this._onMqlChange);
        }
    }

    private _onMqlChange(event: MediaQueryListEvent) {
        this._isMobile = event.matches;
    }

    override updated(changed: PropertyValues<this>) {
        super.updated(changed);
        const validLayouts = new Set(['panel', 'page', 'inspector-only']);
        if (!validLayouts.has(this.layout)) {
            throw new Error(`WorkItemDetailEditor: invalid layout "${this.layout}"`);
        }
        if ((changed.has('workItemId') || changed.has('active')) && this.active && this.workItemId) {
            this._ensureTeamMembers();
            this._load();
        }
        if (changed.has('workItemId')) {
            const item = this._item();
            if (item) {
                this._applyItemDrafts(item as WorkItemRecord);
            } else {
                this._titleDraft = '';
                this._descriptionDraft = '';
                this._labelsDraft = [];
                this._dueDateDraft = '';
                this._attachmentsDraft = [];
                this._variablesDraft = {};
            }
        }
    }

    private _cloneVariables(raw: unknown): Record<string, unknown> {
        if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
            return {};
        }
        return JSON.parse(JSON.stringify(raw));
    }

    private _cloneFileRefs(raw: unknown): Record<string, unknown>[] {
        if (!Array.isArray(raw)) {
            return [];
        }
        return raw.filter((row): row is Record<string, unknown> => Boolean(row && typeof row === 'object')).map((row) => ({ ...row }));
    }

    private _applyItemDrafts(item: WorkItemRecord) {
        if (!item || typeof item !== 'object') {
            return;
        }
        this._titleDraft = typeof item.title === 'string' ? item.title : '';
        this._descriptionDraft = typeof item.description === 'string' ? item.description : '';
        this._labelsDraft = Array.isArray(item.labels) ? [...item.labels] : [];
        this._dueDateDraft = item.due_date !== null && item.due_date !== undefined && typeof item.due_date === 'string'
            ? normalizeIsoDateTimeForField(item.due_date)
            : '';
        this._attachmentsDraft = this._cloneFileRefs(item.attachments);
        this._variablesDraft = this._cloneVariables(item.variables);
        if (typeof item.board_id === 'string' && item.board_id.length > 0) {
            this._boards.get(item.board_id);
        }
        if (assigneeIsQueue(item)) {
            if (!Array.isArray(this._queues.items) || this._queues.items.length === 0) {
                this._queues.load();
            }
        }
    }

    private _ensureTeamMembers() {
        const members = this._teamSel.value;
        const loading = this._teamLoadingSel.value;
        if ((!Array.isArray(members) || members.length === 0) && !loading) {
            this.dispatch(TEAM_EVENTS.MEMBERS_LOAD_REQUESTED, null);
        }
    }

    private _load() {
        if (!this.workItemId) {
            return;
        }
        this._ensureTeamMembers();
        this._workItems.get(this.workItemId);
        this._commentsOp.run({ work_item_id: this.workItemId });
    }

    private _item(): WorkItemRecord | null {
        if (!this.workItemId) {
            return null;
        }
        const cached = this._workItems.byId[this.workItemId];
        if (cached && typeof cached === 'object') {
            return cached as WorkItemRecord;
        }
        const fromList = (this._workItems.items || []).find((row) => row && row.work_item_id === this.workItemId);
        return (fromList as WorkItemRecord | undefined) || null;
    }

    private _saveTitle() {
        const item = this._item();
        if (!item || this._savingTitle) {
            return;
        }
        const nextTitle = this._titleDraft.trim();
        if (!nextTitle || nextTitle === item.title) {
            return;
        }
        this._savingTitle = true;
        this._workItems.update(item.work_item_id, { title: nextTitle });
        this._savingTitle = false;
    }

    private _saveDescription() {
        const item = this._item();
        if (!item || this._savingDescription) {
            return;
        }
        if (this._descriptionDraft === item.description) {
            return;
        }
        this._savingDescription = true;
        this._workItems.update(item.work_item_id, { description: this._descriptionDraft });
        this._savingDescription = false;
    }

    private _saveAttachments(files: unknown) {
        const item = this._item();
        if (!item || !Array.isArray(files)) {
            return;
        }
        this._workItems.update(item.work_item_id, { attachments: files });
    }

    private _saveVariables(variables: unknown) {
        const item = this._item();
        if (!item || !variables || typeof variables !== 'object' || Array.isArray(variables)) {
            return;
        }
        const currentFingerprint = JSON.stringify(item.variables || {});
        const nextFingerprint = JSON.stringify(variables);
        if (currentFingerprint === nextFingerprint) {
            return;
        }
        this._workItems.update(item.work_item_id, { variables: variables as Record<string, unknown> });
    }

    private _savePriority(value: unknown) {
        const item = this._item();
        if (!item || typeof value !== 'string' || value.length === 0 || value === item.priority) {
            return;
        }
        this._workItems.update(item.work_item_id, { priority: value });
    }

    private _saveLabels(values: unknown) {
        const item = this._item();
        if (!item || !Array.isArray(values)) {
            return;
        }
        this._workItems.update(item.work_item_id, { labels: values });
    }

    private _saveDueDate(value: unknown) {
        const item = this._item();
        if (!item) {
            return;
        }
        const normalized = typeof value === 'string' && value.length > 0
            ? normalizeIsoDateTimeForField(value)
            : null;
        const current = item.due_date !== null && item.due_date !== undefined && typeof item.due_date === 'string'
            ? normalizeIsoDateTimeForField(item.due_date)
            : null;
        if (normalized === current) {
            return;
        }
        this._workItems.update(item.work_item_id, { due_date: normalized });
    }

    private _saveStatus(value: unknown) {
        const item = this._item();
        if (!item || typeof value !== 'string' || value.length === 0) {
            return;
        }
        if (typeof item.board_id === 'string' && item.board_id.length > 0) {
            const board = this._boards.byId[item.board_id];
            if (board && Array.isArray(board.columns)) {
                const column = board.columns.find((col) => col && col.board_column_id === value);
                if (column) {
                    this._moveOp.run({
                        work_item_id: item.work_item_id,
                        board_column_id: value,
                    });
                    return;
                }
            }
        }
        if (value === item.state) {
            return;
        }
        this._moveOp.run({
            work_item_id: item.work_item_id,
            state: value,
        });
    }

    private _saveAssignee(userId: unknown) {
        const item = this._item();
        if (!item || typeof userId !== 'string' || userId.length === 0) {
            return;
        }
        this._assignOp.run({
            work_item_id: item.work_item_id,
            assignment: { assignee_kind: 'users', user_ids: [userId] },
        });
    }

    private _claim() {
        if (!this.workItemId) {
            return;
        }
        this._claimOp.run({ work_item_id: this.workItemId });
    }

    private async _complete(): Promise<void> {
        if (!this.workItemId) {
            return;
        }
        await this._completeOp.run({ work_item_id: this.workItemId, resolution_text: '' });
    }

    private _cancel() {
        if (!this.workItemId) {
            return;
        }
        this._cancelOp.run({ work_item_id: this.workItemId });
    }

    private _submitComment() {
        const text = this._commentDraft.trim();
        const files = Array.isArray(this._commentFilesDraft) ? this._commentFilesDraft : [];
        if ((!text && files.length === 0) || !this.workItemId) {
            return;
        }
        this._commentOp.run({ work_item_id: this.workItemId, text, files });
        this._commentDraft = '';
        this._commentFilesDraft = [];
    }

    private _priorityEnumConfig() {
        return {
            values: WORK_ITEM_PRIORITIES.map((value) => ({
                value,
                label: this.t(`priority.${value}`),
            })),
        };
    }

    private _statusEnumConfig(item: WorkItemRecord) {
        if (typeof item.board_id === 'string' && item.board_id.length > 0) {
            const board = this._boards.byId[item.board_id];
            if (board && Array.isArray(board.columns) && board.columns.length > 0) {
                return {
                    values: (board.columns as { board_column_id?: unknown; label?: unknown }[]).map((col) => ({
                        value: col.board_column_id,
                        label: col.label,
                    })),
                };
            }
        }
        return {
            values: WORK_ITEM_STATES.map((value) => ({
                value,
                label: this.t(`state.${value}`),
            })),
        };
    }

    private _statusValue(item: WorkItemRecord) {
        if (typeof item.board_id === 'string' && item.board_id.length > 0 && typeof item.board_column_id === 'string') {
            return item.board_column_id;
        }
        return typeof item.state === 'string' ? item.state : 'open';
    }

    private _stateLabel(item: WorkItemRecord) {
        if (typeof item.board_id === 'string' && item.board_id.length > 0 && typeof item.board_column_id === 'string') {
            const board = this._boards.byId[item.board_id];
            if (board && Array.isArray(board.columns)) {
                const column = (board.columns as { board_column_id?: unknown; label?: unknown }[]).find((col) => col && col.board_column_id === item.board_column_id);
                if (column && typeof column.label === 'string') {
                    return column.label;
                }
            }
        }
        return typeof item.state === 'string' ? this.t('state.' + item.state) : '';
    }

    private _teamMemberOptions() {
        const members = this._teamSel.value;
        if (!Array.isArray(members)) {
            return [];
        }
        const flowBadge = this.t('detail_page.assignee_flow_badge');
        return members
            .filter((member): member is TeamMemberLike => Boolean(member && typeof member.user_id === 'string' && member.user_id.length > 0))
            .map((member) => {
                const userId = member.user_id as string;
                const name = typeof member.name === 'string' && member.name.length > 0
                    ? member.name
                    : userId;
                const label = member.is_flow_employee === true
                    ? `${name} (${flowBadge})`
                    : name;
                return { value: userId, label };
            });
    }

    private _boardLabel(item: WorkItemRecord) {
        if (typeof item.board_id !== 'string' || item.board_id.length === 0) {
            return '';
        }
        const board = this._boards.byId[item.board_id];
        if (!board || typeof board.name !== 'string') {
            return item.board_id;
        }
        return board.name;
    }

    private _queueLabel(item: WorkItemRecord) {
        if (!assigneeIsQueue(item)) {
            return '';
        }
        const queueId = item.assignment?.work_queue_id;
        if (typeof queueId !== 'string' || queueId.length === 0) {
            return '';
        }
        const queue = (this._queues.items || []).find(
            (row) => row && row.work_queue_id === queueId,
        );
        if (queue && typeof queue.name === 'string') {
            return queue.name;
        }
        return queueId;
    }

    private _openBoard(item: WorkItemRecord) {
        if (typeof item.board_id !== 'string' || item.board_id.length === 0) {
            return;
        }
        this.navigate('board', {}, { search: `?board_id=${encodeURIComponent(item.board_id)}` });
    }

    private _resolutionText(item: WorkItemRecord) {
        const resolution = item.resolution as { text?: unknown } | null | undefined;
        if (!resolution || typeof resolution !== 'object') {
            return '';
        }
        return typeof resolution.text === 'string' ? resolution.text : '';
    }

    private _resolutionFiles(item: WorkItemRecord) {
        const resolution = item.resolution as { files?: unknown } | null | undefined;
        if (!resolution || typeof resolution !== 'object') {
            return [];
        }
        return this._cloneFileRefs(resolution.files);
    }

    private _renderInspector(item: WorkItemRecord, showTitle: boolean) {
        const isTerminal = typeof item.state === 'string' && TERMINAL_STATES.has(item.state);
        const showClaim = queueUnclaimed(item);
        return html`
            <div class="wt-inspector-sticky">
                <div class="wt-card wt-inspector-card">
                    <worktracker-detail-inspector
                    .item=${item}
                    due-date-draft=${this._dueDateDraft}
                    .labelsDraft=${this._labelsDraft}
                    .variablesDraft=${this._variablesDraft}
                    status-value=${this._statusValue(item)}
                    .statusConfig=${this._statusEnumConfig(item)}
                    .priorityConfig=${this._priorityEnumConfig()}
                    .teamOptions=${this._teamMemberOptions()}
                    queue-label=${this._queueLabel(item)}
                    board-label=${this._boardLabel(item)}
                    locale=${this._localeSel.value}
                    ?show-title=${showTitle}
                    ?show-lifecycle-actions=${!isTerminal}
                    .showComplete=${workItemAllowsSilentComplete(item)}
                    ?show-claim=${showClaim}
                    @wt-complete=${() => this._complete()}
                    @wt-cancel=${() => this._cancel()}
                    @wt-claim=${() => this._claim()}
                    @wt-status-change=${(e: CustomEvent<{ value?: unknown }>) => {
                        const value = e.detail && typeof e.detail.value === 'string' ? e.detail.value : '';
                        this._saveStatus(value);
                    }}
                    @wt-priority-change=${(e: CustomEvent<{ value?: unknown }>) => {
                        const value = e.detail && typeof e.detail.value === 'string' ? e.detail.value : '';
                        this._savePriority(value);
                    }}
                    @wt-assignee-change=${(e: CustomEvent<{ user_id?: unknown }>) => {
                        const userId = e.detail && typeof e.detail.user_id === 'string' ? e.detail.user_id : '';
                        this._saveAssignee(userId);
                    }}
                    @wt-due-date-change=${(e: CustomEvent<{ value?: unknown }>) => {
                        const value = e.detail && typeof e.detail.value === 'string' ? e.detail.value : '';
                        this._dueDateDraft = value;
                        this._saveDueDate(value);
                    }}
                    @wt-labels-change=${(e: CustomEvent<{ values?: unknown }>) => {
                        const values = e.detail && Array.isArray(e.detail.values) ? e.detail.values : [];
                        this._labelsDraft = values;
                        this._saveLabels(values);
                    }}
                    @wt-variables-change=${(e: CustomEvent<{ variables?: unknown }>) => {
                        const variables = e.detail && e.detail.variables && typeof e.detail.variables === 'object' && !Array.isArray(e.detail.variables)
                            ? e.detail.variables as Record<string, unknown>
                            : {};
                        this._variablesDraft = variables;
                        this._saveVariables(variables);
                    }}
                    @wt-board-open=${() => this._openBoard(item)}
                    ></worktracker-detail-inspector>
                </div>
            </div>
        `;
    }

    private _renderContent(item: WorkItemRecord | null, loading: boolean, state: string) {
        return html`
            <worktracker-detail-content
                layout=${this.layout}
                work-item-id=${this.workItemId}
                state=${state}
                state-label=${item ? this._stateLabel(item) : ''}
                title-draft=${this._titleDraft}
                description-draft=${this._descriptionDraft}
                resolution-text=${item ? this._resolutionText(item) : ''}
                .resolutionFiles=${item ? this._resolutionFiles(item) : []}
                .attachments=${this._attachmentsDraft}
                .descriptionVariables=${this._variablesDraft}
                ?loading=${loading}
                @wt-title-change=${(e: CustomEvent<{ value?: unknown }>) => {
                    this._titleDraft = e.detail && typeof e.detail.value === 'string' ? e.detail.value : '';
                }}
                @wt-title-blur=${() => this._saveTitle()}
                @wt-description-change=${(e: CustomEvent<{ value?: unknown }>) => {
                    this._descriptionDraft = e.detail && typeof e.detail.value === 'string' ? e.detail.value : '';
                }}
                @wt-description-blur=${() => this._saveDescription()}
                @wt-attachments-change=${(e: CustomEvent<{ files?: unknown }>) => {
                    const files = e.detail && Array.isArray(e.detail.files) ? e.detail.files : [];
                    this._attachmentsDraft = files;
                    this._saveAttachments(files);
                }}
            ></worktracker-detail-content>
        `;
    }

    private _isHandoff(item: WorkItemRecord | null): item is WorkItemRecord {
        return item !== null && item.kind === 'operator_handoff';
    }

    private _renderHitlChat(item: WorkItemRecord) {
        const policy = item.interaction_policy && typeof item.interaction_policy === 'object'
            ? item.interaction_policy
            : null;
        if (!policy || policy.mode === 'none') {
            return nothing;
        }
        const canSend = policy.can_send === true;
        const canComplete = policy.can_complete === true;
        const isTakeover = policy.mode === 'takeover';
        const modeHint = policy.mode === 'single_reply'
            ? this.t('hitl_chat.hint_single_reply')
            : policy.mode === 'takeover'
                ? this.t('hitl_chat.hint_takeover')
                : '';
        return html`
            <section class="wt-hitl">
                <h3 class="wt-hitl-title">${this.t('hitl_chat.title')}</h3>
                ${modeHint
                    ? html`<p class="wt-hitl-hint">${modeHint}</p>`
                    : nothing}
                ${!canSend && !(typeof item.state === 'string' && TERMINAL_STATES.has(item.state))
                    ? html`<p class="wt-hitl-hint">${this.t('hitl_chat.hint_need_queue_access')}</p>`
                    : nothing}
                <div class="wt-hitl-chat">
                    <platform-flow-ui
                        profile="operator_handoff"
                        display="page"
                        work-item-id=${this.workItemId}
                        base-url="/flows"
                        .readonly=${!canSend}
                        .interactionPolicy=${policy}
                    ></platform-flow-ui>
                </div>
                ${isTakeover && canComplete && !(typeof item.state === 'string' && TERMINAL_STATES.has(item.state))
                    ? html`
                        <div class="wt-hitl-complete">
                            <button
                                type="button"
                                class="btn btn-primary"
                                @click=${() => void this._complete()}
                            >${this.t('hitl_chat.complete_takeover')}</button>
                        </div>
                    `
                    : nothing}
            </section>
        `;
    }

    private _renderActivity() {
        const item = this._item();
        const handoffSubtitle = this._isHandoff(item)
            ? this.t('hitl_chat.activity_internal_hint')
            : '';
        return html`
            <worktracker-activity-thread
                ?embedded=${this.layout === 'page'}
                work-item-id=${this.workItemId}
                .comments=${this._commentsOp.state.items || []}
                comment-draft=${this._commentDraft}
                .commentFiles=${this._commentFilesDraft}
                locale=${this._localeSel.value}
                subtitle=${handoffSubtitle}
                @wt-comment-change=${(e: CustomEvent<{ value?: unknown }>) => {
                    this._commentDraft = e.detail && typeof e.detail.value === 'string' ? e.detail.value : '';
                }}
                @wt-comment-files-change=${(e: CustomEvent<{ files?: unknown }>) => {
                    this._commentFilesDraft = e.detail && Array.isArray(e.detail.files) ? e.detail.files : [];
                }}
                @wt-comment-submit=${() => this._submitComment()}
            ></worktracker-activity-thread>
        `;
    }

    private _renderPropertiesToggle(expanded: boolean) {
        return html`
            <button
                type="button"
                class="wt-properties-toggle"
                @click=${() => { this._propertiesExpanded = !this._propertiesExpanded; }}
                aria-expanded=${String(expanded)}
            >
                <span>${this.t('detail_page.section_properties')}</span>
                <platform-icon name=${expanded ? 'chevron-up' : 'chevron-down'} size="16"></platform-icon>
            </button>
        `;
    }

    override render() {
        if (!this.active) {
            return nothing;
        }
        const item = this._item();
        const loading = Boolean(this.workItemId) && !item && this._workItems.isBusy(this.workItemId);

        if (this.layout === 'inspector-only') {
            if (!item) {
                return html`<div class="wt-loading"><glass-spinner></glass-spinner></div>`;
            }
            return this._renderInspector(item, false);
        }

        const state = item && typeof item.state === 'string' ? item.state : 'open';
        const expanded = !this._isMobile || this._propertiesExpanded;

        const isHandoff = this._isHandoff(item);

        if (this.layout === 'page') {
            return html`
                <div class="wt-page-main">
                    <div class="wt-card wt-detail-card">
                        <div class="wt-card-section wt-detail-card-inner">
                            ${this._renderContent(item, loading, state)}
                            ${isHandoff ? html`
                                <hr class="wt-card-divider wt-card-divider-inset" />
                                ${this._renderHitlChat(item)}
                            ` : nothing}
                            <hr class="wt-card-divider wt-card-divider-inset" />
                            ${this._renderActivity()}
                        </div>
                    </div>
                </div>
                ${item ? html`
                    ${this._isMobile ? this._renderPropertiesToggle(expanded) : nothing}
                    <div class="wt-properties-collapsible" data-expanded=${expanded ? 'true' : 'false'}>
                        ${this._renderInspector(item, true)}
                    </div>
                ` : nothing}
            `;
        }

        return html`
            <div class="wt-panel-stack">
                ${this._renderContent(item, loading, state)}
                ${isHandoff ? this._renderHitlChat(item) : nothing}
                ${this._renderActivity()}
            </div>
            ${item ? this._renderInspector(item, true) : nothing}
        `;
    }
}

customElements.define('work-item-detail-editor', WorkItemDetailEditor);
