/**
 * WorkItemDetailEditor — orchestrator for task detail (panel / page / inspector-only).
 */

import { html, css, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
import {
    WORK_ITEM_EVENTS,
    WORK_ITEM_MUTATION_SUCCEEDED,
} from '../events/resources/work-items.resource.js';
import {
    TERMINAL_STATES,
    WORK_ITEM_STATES,
    WORK_ITEM_PRIORITIES,
    assigneeIsQueue,
    assigneeUserId,
    queueUnclaimed,
    workItemFromEventPayload,
} from '../utils/work-item-detail-shared.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { normalizeIsoDateTimeForField } from '@platform/lib/utils/format-platform-date.js';
import { worktrackerDetailEditorLayoutStyles } from '../styles/worktracker-detail-editor-layout.styles.js';
import { worktrackerSurfacesStyles } from '../styles/worktracker-surfaces.styles.js';
import './worktracker-detail-content.js';
import './worktracker-activity-thread.js';
import './worktracker-detail-inspector.js';
import '@platform/lib/components/platform-icon.js';

export class WorkItemDetailEditor extends PlatformElement {
    static i18nNamespace = 'worktracker';

    static properties = {
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

    static styles = [
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
        this._localeSel = this.select((s) => s.i18n.locale);
        this._teamSel = this.select((s) => s.team.members);

        const syncItem = (event) => {
            const item = workItemFromEventPayload(event.payload);
            if (!item || typeof item.work_item_id !== 'string' || item.work_item_id !== this.workItemId) {
                return;
            }
            this._applyItemDrafts(item);
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

    connectedCallback() {
        super.connectedCallback();
        if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
            this._mql = window.matchMedia('(max-width: 767px)');
            this._isMobile = this._mql.matches;
            this._mql.addEventListener('change', this._onMqlChange);
        }
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        if (this._mql) {
            this._mql.removeEventListener('change', this._onMqlChange);
        }
    }

    _onMqlChange(event) {
        this._isMobile = event.matches;
    }

    updated(changed) {
        super.updated(changed);
        const validLayouts = new Set(['panel', 'page', 'inspector-only']);
        if (!validLayouts.has(this.layout)) {
            throw new Error(`WorkItemDetailEditor: invalid layout "${this.layout}"`);
        }
        if ((changed.has('workItemId') || changed.has('active')) && this.active && this.workItemId) {
            this._load();
        }
        if (changed.has('workItemId')) {
            const item = this._item();
            if (item) {
                this._applyItemDrafts(item);
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

    _cloneVariables(raw) {
        if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
            return {};
        }
        return JSON.parse(JSON.stringify(raw));
    }

    _cloneFileRefs(raw) {
        if (!Array.isArray(raw)) {
            return [];
        }
        return raw.filter((row) => row && typeof row === 'object').map((row) => ({ ...row }));
    }

    _applyItemDrafts(item) {
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

    _load() {
        if (!this.workItemId) {
            return;
        }
        this._workItems.get(this.workItemId);
        this._commentsOp.run({ work_item_id: this.workItemId });
    }

    _item() {
        if (!this.workItemId) {
            return null;
        }
        const cached = this._workItems.byId[this.workItemId];
        if (cached && typeof cached === 'object') {
            return cached;
        }
        const fromList = (this._workItems.items || []).find((row) => row && row.work_item_id === this.workItemId);
        return fromList || null;
    }

    _saveTitle() {
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

    _saveDescription() {
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

    _saveAttachments(files) {
        const item = this._item();
        if (!item || !Array.isArray(files)) {
            return;
        }
        this._workItems.update(item.work_item_id, { attachments: files });
    }

    _saveVariables(variables) {
        const item = this._item();
        if (!item || !variables || typeof variables !== 'object' || Array.isArray(variables)) {
            return;
        }
        const currentFingerprint = JSON.stringify(item.variables || {});
        const nextFingerprint = JSON.stringify(variables);
        if (currentFingerprint === nextFingerprint) {
            return;
        }
        this._workItems.update(item.work_item_id, { variables });
    }

    _savePriority(value) {
        const item = this._item();
        if (!item || typeof value !== 'string' || value.length === 0 || value === item.priority) {
            return;
        }
        this._workItems.update(item.work_item_id, { priority: value });
    }

    _saveLabels(values) {
        const item = this._item();
        if (!item || !Array.isArray(values)) {
            return;
        }
        this._workItems.update(item.work_item_id, { labels: values });
    }

    _saveDueDate(value) {
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

    _saveStatus(value) {
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

    _saveAssignee(userId) {
        const item = this._item();
        if (!item || typeof userId !== 'string' || userId.length === 0) {
            return;
        }
        this._assignOp.run({
            work_item_id: item.work_item_id,
            assignment: { assignee_kind: 'users', user_ids: [userId] },
        });
    }

    _claim() {
        if (!this.workItemId) {
            return;
        }
        this._claimOp.run({ work_item_id: this.workItemId });
    }

    _complete() {
        if (!this.workItemId) {
            return;
        }
        this._completeOp.run({ work_item_id: this.workItemId, resolution_text: '' });
    }

    _cancel() {
        if (!this.workItemId) {
            return;
        }
        this._cancelOp.run({ work_item_id: this.workItemId });
    }

    _submitComment() {
        const text = this._commentDraft.trim();
        const files = Array.isArray(this._commentFilesDraft) ? this._commentFilesDraft : [];
        if ((!text && files.length === 0) || !this.workItemId) {
            return;
        }
        this._commentOp.run({ work_item_id: this.workItemId, text, files });
        this._commentDraft = '';
        this._commentFilesDraft = [];
    }

    _priorityEnumConfig() {
        return {
            values: WORK_ITEM_PRIORITIES.map((value) => ({
                value,
                label: this.t(`priority.${value}`),
            })),
        };
    }

    _statusEnumConfig(item) {
        if (typeof item.board_id === 'string' && item.board_id.length > 0) {
            const board = this._boards.byId[item.board_id];
            if (board && Array.isArray(board.columns) && board.columns.length > 0) {
                return {
                    values: board.columns.map((col) => ({
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

    _statusValue(item) {
        if (typeof item.board_id === 'string' && item.board_id.length > 0 && typeof item.board_column_id === 'string') {
            return item.board_column_id;
        }
        return typeof item.state === 'string' ? item.state : 'open';
    }

    _stateLabel(item) {
        if (typeof item.board_id === 'string' && item.board_id.length > 0 && typeof item.board_column_id === 'string') {
            const board = this._boards.byId[item.board_id];
            if (board && Array.isArray(board.columns)) {
                const column = board.columns.find((col) => col && col.board_column_id === item.board_column_id);
                if (column && typeof column.label === 'string') {
                    return column.label;
                }
            }
        }
        return typeof item.state === 'string' ? this.t('state.' + item.state) : '';
    }

    _teamMemberOptions() {
        const members = this._teamSel.value;
        if (!Array.isArray(members)) {
            return [];
        }
        return members
            .filter((member) => member && typeof member.user_id === 'string' && member.user_id.length > 0)
            .map((member) => {
                const name = typeof member.name === 'string' && member.name.length > 0
                    ? member.name
                    : member.user_id;
                return { value: member.user_id, label: name };
            });
    }

    _boardLabel(item) {
        if (typeof item.board_id !== 'string' || item.board_id.length === 0) {
            return '';
        }
        const board = this._boards.byId[item.board_id];
        if (!board || typeof board.name !== 'string') {
            return item.board_id;
        }
        return board.name;
    }

    _queueLabel(item) {
        if (!assigneeIsQueue(item)) {
            return '';
        }
        const queueId = item.assignment.work_queue_id;
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

    _openBoard(item) {
        if (typeof item.board_id !== 'string' || item.board_id.length === 0) {
            return;
        }
        this.navigate('board', {}, { search: `?board_id=${encodeURIComponent(item.board_id)}` });
    }

    _resolutionText(item) {
        if (!item.resolution || typeof item.resolution !== 'object') {
            return '';
        }
        return typeof item.resolution.text === 'string' ? item.resolution.text : '';
    }

    _resolutionFiles(item) {
        if (!item.resolution || typeof item.resolution !== 'object') {
            return [];
        }
        return this._cloneFileRefs(item.resolution.files);
    }

    _renderInspector(item, showTitle) {
        const isTerminal = TERMINAL_STATES.has(item.state);
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
                    ?show-claim=${showClaim}
                    @wt-complete=${() => this._complete()}
                    @wt-cancel=${() => this._cancel()}
                    @wt-claim=${() => this._claim()}
                    @wt-status-change=${(e) => {
                        const value = e.detail && typeof e.detail.value === 'string' ? e.detail.value : '';
                        this._saveStatus(value);
                    }}
                    @wt-priority-change=${(e) => {
                        const value = e.detail && typeof e.detail.value === 'string' ? e.detail.value : '';
                        this._savePriority(value);
                    }}
                    @wt-assignee-change=${(e) => {
                        const userId = e.detail && typeof e.detail.user_id === 'string' ? e.detail.user_id : '';
                        this._saveAssignee(userId);
                    }}
                    @wt-due-date-change=${(e) => {
                        const value = e.detail && typeof e.detail.value === 'string' ? e.detail.value : '';
                        this._dueDateDraft = value;
                        this._saveDueDate(value);
                    }}
                    @wt-labels-change=${(e) => {
                        const values = e.detail && Array.isArray(e.detail.values) ? e.detail.values : [];
                        this._labelsDraft = values;
                        this._saveLabels(values);
                    }}
                    @wt-variables-change=${(e) => {
                        const variables = e.detail && e.detail.variables && typeof e.detail.variables === 'object'
                            ? e.detail.variables
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

    _renderContent(item, loading, state) {
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
                @wt-title-change=${(e) => {
                    this._titleDraft = e.detail && typeof e.detail.value === 'string' ? e.detail.value : '';
                }}
                @wt-title-blur=${() => this._saveTitle()}
                @wt-description-change=${(e) => {
                    this._descriptionDraft = e.detail && typeof e.detail.value === 'string' ? e.detail.value : '';
                }}
                @wt-description-blur=${() => this._saveDescription()}
                @wt-attachments-change=${(e) => {
                    const files = e.detail && Array.isArray(e.detail.files) ? e.detail.files : [];
                    this._attachmentsDraft = files;
                    this._saveAttachments(files);
                }}
            ></worktracker-detail-content>
        `;
    }

    _renderActivity() {
        return html`
            <worktracker-activity-thread
                ?embedded=${this.layout === 'page'}
                work-item-id=${this.workItemId}
                .comments=${this._commentsOp.state.items || []}
                comment-draft=${this._commentDraft}
                .commentFiles=${this._commentFilesDraft}
                locale=${this._localeSel.value}
                @wt-comment-change=${(e) => {
                    this._commentDraft = e.detail && typeof e.detail.value === 'string' ? e.detail.value : '';
                }}
                @wt-comment-files-change=${(e) => {
                    this._commentFilesDraft = e.detail && Array.isArray(e.detail.files) ? e.detail.files : [];
                }}
                @wt-comment-submit=${() => this._submitComment()}
            ></worktracker-activity-thread>
        `;
    }

    _renderPropertiesToggle(expanded) {
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

    render() {
        if (!this.active) {
            return nothing;
        }
        const item = this._item();
        const loading = Boolean(this.workItemId) && !item && this._workItems.isBusy(this.workItemId);

        if (this.layout === 'inspector-only') {
            if (!item) {
                return html`<div class="wt-loading">${this.t('detail_panel.loading')}</div>`;
            }
            return this._renderInspector(item, false);
        }

        const state = item && typeof item.state === 'string' ? item.state : 'open';
        const expanded = !this._isMobile || this._propertiesExpanded;

        if (this.layout === 'page') {
            return html`
                <div class="wt-page-main">
                    <div class="wt-card wt-detail-card">
                        <div class="wt-card-section wt-detail-card-inner">
                            ${this._renderContent(item, loading, state)}
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
                ${this._renderActivity()}
            </div>
            ${item ? this._renderInspector(item, true) : nothing}
        `;
    }
}

customElements.define('work-item-detail-editor', WorkItemDetailEditor);
