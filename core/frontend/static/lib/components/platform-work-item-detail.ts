/**
 * platform-work-item-detail — cross-service panel/page редактор WorkItem.
 * Визуальный канон совпадает с worktracker `work-item-detail-panel` + content/inspector
 * Мутации — worktracker/work_item_* фабрики.
 */

import { html, css, nothing } from '../lit-shim.js';
import { PlatformElement } from '../platform-element/index.js';
import { TEAM_EVENTS } from '../events/reducers/team.js';
import { openWorkItemDetail, navigateToWorkItemPage } from '../utils/work-item-deeplink.js';
import { normalizeIsoDateTimeForField } from '../utils/format-platform-date.js';
import { buildWorkItemFileCreateSpecJson } from '../utils/file-create-spec.js';
import './platform-icon.js';
import './platform-button.js';
import './fields/platform-field.js';
import './platform-markdown-editor.js';
import './platform-file-attachments.js';
import './glass-spinner.js';
import type {CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult} from '../lit-shim.js';
import type { OpController, ResourceController } from '../base/use-resource.js';
import type { SelectController } from '../events/select-controller.js';

interface WorkItemLink {
    link_kind?: unknown;
    entity_id?: unknown;
}

interface WorkItemAssignment {
    assignee_kind?: string;
    user_ids?: unknown;
    claimed_by_user_id?: unknown;
}

interface WorkItemRecord {
    work_item_id: string;
    title?: unknown;
    description?: unknown;
    due_date?: unknown;
    attachments?: unknown;
    links?: unknown;
    assignment?: WorkItemAssignment;
    state?: string;
    priority?: string;
    kind?: string;
    [key: string]: unknown;
}

interface TeamMemberRecord {
    user_id?: unknown;
    name?: unknown;
    [key: string]: unknown;
}

interface FileRefRecord {
    file_id: string;
    [key: string]: unknown;
}

const STATES = Object.freeze(['open', 'in_progress', 'blocked', 'done', 'cancelled', 'failed']);
const PRIORITIES = Object.freeze(['low', 'normal', 'high', 'urgent']);
const TERMINAL = Object.freeze(new Set(['done', 'cancelled', 'failed']));

function _crmEntityId(item: WorkItemRecord | null | undefined): string {
    if (!item || !Array.isArray(item.links)) {
        return '';
    }
    for (const link of item.links as WorkItemLink[]) {
        if (link && link.link_kind === 'crm_entity' && typeof link.entity_id === 'string') {
            return link.entity_id;
        }
    }
    return '';
}

function _assigneeUserId(item: WorkItemRecord | null | undefined): string {
    const assignment = item && item.assignment;
    if (!assignment || typeof assignment !== 'object') {
        return '';
    }
    if (assignment.assignee_kind === 'users' && Array.isArray(assignment.user_ids)) {
        const userId = assignment.user_ids[0];
        return typeof userId === 'string' ? userId : '';
    }
    if (assignment.assignee_kind === 'queue') {
        const claimed = assignment.claimed_by_user_id;
        return typeof claimed === 'string' ? claimed : '';
    }
    return '';
}

function _cloneFileRefs(files: unknown): FileRefRecord[] {
    if (!Array.isArray(files)) {
        return [];
    }
    return files.filter(
        (file): file is FileRefRecord =>
            Boolean(file) && typeof file === 'object' && typeof (file as FileRefRecord).file_id === 'string',
    );
}

export class PlatformWorkItemDetail extends PlatformElement {
    static i18nNamespace = 'platform';

    static override properties: PropertyDeclarations = {
        workItemId: { type: String, attribute: 'work-item-id' },
        item: { attribute: false },
        layout: { type: String },
        showGraphLink: { type: Boolean, attribute: 'show-graph-link' },
        _titleDraft: { state: true },
        _descriptionDraft: { state: true },
        _dueDraft: { state: true },
        _attachmentsDraft: { state: true },
        _draftsReadyForId: { state: true },
    }
    declare workItemId: string;
    declare item: WorkItemRecord | null;
    declare layout: string;
    declare showGraphLink: boolean;
    declare _titleDraft: string;
    declare _descriptionDraft: string;
    declare _dueDraft: string;
    declare _attachmentsDraft: FileRefRecord[];
    declare _draftsReadyForId: string;

    private _getOp: OpController | null;
    private _items: ResourceController | null;
    private _moveOp: OpController | null;
    private _assignOp: OpController | null;
    private _teamSel: SelectController<TeamMemberRecord[]>;
    private _teamLoadingSel: SelectController<boolean>;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                min-height: 0;
                height: 100%;
                background: var(--bg-primary, var(--bg-elevated));
            }
            .head {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
                padding: var(--space-3) var(--space-4);
                border-bottom: 1px solid var(--glass-border-subtle);
                flex-shrink: 0;
            }
            .head-title {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-secondary);
            }
            .head-actions {
                display: flex;
                align-items: center;
                gap: var(--space-1);
            }
            .icon-btn {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 32px;
                height: 32px;
                border: none;
                border-radius: var(--radius-md);
                background: transparent;
                color: var(--text-secondary);
                cursor: pointer;
            }
            .icon-btn:hover {
                background: var(--glass-tint-medium);
                color: var(--text-primary);
            }
            .cta-btn {
                display: inline-flex;
                align-items: center;
                min-height: 32px;
                padding: 0 var(--space-3);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-tint-subtle);
                color: var(--text-primary);
                font: inherit;
                font-size: var(--text-sm);
                cursor: pointer;
            }
            .cta-btn:hover {
                background: var(--glass-tint-medium);
            }
            .body {
                flex: 1;
                min-height: 0;
                overflow-y: auto;
                padding: var(--space-4);
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
            }
            .title-block {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                min-width: 0;
                width: 100%;
            }
            .title-field {
                width: 100%;
                --field-pill-bg: transparent;
                --field-pill-border: 1px solid transparent;
                --field-pill-padding-y: var(--space-1);
                --field-pill-padding-x: var(--space-2);
                --field-pill-input-size: var(--worktracker-detail-title-size, var(--text-2xl));
                --field-pill-input-weight: var(--font-semibold);
                --field-pill-input-line: 1.2;
                border-radius: var(--radius-md);
            }
            .title-field:hover {
                --field-pill-bg: var(--glass-tint-subtle);
                --field-pill-border: 1px solid var(--glass-border-subtle);
            }
            .title-field:focus-within {
                --field-pill-border: 1px solid var(--accent);
                --field-pill-bg: var(--glass-tint-subtle);
                box-shadow: var(--focus-ring);
            }
            :host([layout='page']) .title-field {
                --field-pill-input-size: var(--text-3xl);
                --field-pill-input-weight: var(--font-bold);
                --field-pill-padding-y: var(--space-2);
                --field-pill-padding-x: var(--space-3);
            }
            .desc-editor {
                width: 100%;
                min-width: 0;
                color: var(--text-secondary);
                --editor-min-height: 120px;
            }
            :host([layout='page']) .desc-editor {
                --editor-min-height: 160px;
            }
            .inspector {
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
                min-width: 0;
                width: 100%;
                padding-top: var(--space-2);
                border-top: var(--worktracker-divider, 1px solid var(--glass-border-subtle));
            }
            .inspector-title {
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                color: var(--text-tertiary);
                text-transform: uppercase;
                letter-spacing: 0.04em;
                margin: 0 0 var(--space-2);
            }
            .inspector-row {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                min-height: var(--worktracker-inspector-row-height, 32px);
                min-width: 0;
            }
            .inspector-label {
                flex: 0 0 var(--worktracker-inspector-label-width, 108px);
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                min-width: 0;
            }
            .inspector-control {
                flex: 1;
                min-width: 0;
                display: flex;
                align-items: center;
            }
            .inspector-control glass-spinner {
                width: 16px;
                height: 16px;
            }
            .inspector platform-field {
                width: 100%;
                --field-pill-bg: transparent;
                --field-pill-border: transparent;
                --field-pill-padding-x: 0;
                --field-pill-input-size: var(--text-sm);
                --field-pill-number-spin-height: 32px;
            }
            .inspector platform-field:focus-within {
                --field-pill-bg: var(--glass-tint-subtle);
                --field-pill-border: 1px solid var(--glass-border-subtle);
                --field-pill-padding-x: var(--space-2);
            }
            .section-label {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-secondary);
                margin: 0 0 var(--space-2);
            }
            .actions {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
                padding-top: var(--space-2);
            }
            .empty {
                padding: var(--space-6);
                color: var(--text-tertiary);
                text-align: center;
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
        this.workItemId = '';
        this.item = null;
        this.layout = 'panel';
        this.showGraphLink = false;
        this._titleDraft = '';
        this._descriptionDraft = '';
        this._dueDraft = '';
        this._attachmentsDraft = [];
        this._draftsReadyForId = '';
        this._getOp = null;
        this._items = null;
        this._moveOp = null;
        this._assignOp = null;
        this._teamSel = this.select((s) => {
            const team = s.team as { members?: unknown } | undefined;
            const members = team && team.members;
            return Array.isArray(members) ? (members as TeamMemberRecord[]) : [];
        });
        this._teamLoadingSel = this.select((s) =>
            Boolean((s.team as { loading?: unknown } | undefined)?.loading));
    }

    override connectedCallback(): void {
        super.connectedCallback();
        this._getOp = this.useOp('worktracker/work_item_get');
        this._items = this.useResource('worktracker/work_items', { autoload: false });
        this._moveOp = this.useOp('worktracker/work_item_move');
        this._assignOp = this.useOp('worktracker/work_item_assign');
        this.setAttribute('layout', this.layout);
        this._ensureTeamMembers();
    }

    override updated(changed: PropertyValues): void {
        super.updated(changed);
        if (changed.has('layout')) {
            this.setAttribute('layout', this.layout);
        }
        if (
            (changed.has('workItemId') || changed.has('item'))
            && !this._hasLiveItem()
            && typeof this.workItemId === 'string'
            && this.workItemId.length > 0
        ) {
            void this._getOp!.run({ work_item_id: this.workItemId });
        }
        if (changed.has('workItemId') || changed.has('item')) {
            this._ensureTeamMembers();
        }
        const item = this._resolved();
        if (item && item.work_item_id !== this._draftsReadyForId) {
            this._hydrateDrafts(item);
        }
    }

    _ensureTeamMembers(): void {
        const members = this._teamSel.value;
        const loading = this._teamLoadingSel.value;
        if ((members || []).length === 0 && !loading) {
            this.dispatch(TEAM_EVENTS.MEMBERS_LOAD_REQUESTED, null);
        }
    }

    _hasLiveItem(): boolean {
        return Boolean(this.item) && typeof this.item!.work_item_id === 'string';
    }

    _resolved(): WorkItemRecord | null {
        if (this._hasLiveItem()) {
            return this.item as WorkItemRecord;
        }
        const id = this.workItemId;
        const cached = this._items ? this._items.byId[id] : undefined;
        if (cached && typeof (cached as WorkItemRecord).work_item_id === 'string') {
            return cached as WorkItemRecord;
        }
        const result = this._getOp ? this._getOp.lastResult : null;
        if (result && typeof result === 'object' && typeof (result as WorkItemRecord).work_item_id === 'string') {
            return result as WorkItemRecord;
        }
        return null;
    }

    _hydrateDrafts(item: WorkItemRecord): void {
        this._titleDraft = typeof item.title === 'string' ? item.title : '';
        this._descriptionDraft = typeof item.description === 'string' ? item.description : '';
        this._dueDraft = normalizeIsoDateTimeForField(
            typeof item.due_date === 'string' ? item.due_date : null,
        );
        this._attachmentsDraft = _cloneFileRefs(item.attachments);
        this._draftsReadyForId = typeof item.work_item_id === 'string' ? item.work_item_id : '';
    }

    async _patch(fields: Record<string, unknown>): Promise<void> {
        const item = this._resolved();
        if (!item) {
            throw new Error('platform-work-item-detail: no item');
        }
        this._items!.update(item.work_item_id, fields);
        this.emit('work-item-changed', { work_item_id: item.work_item_id, fields });
    }

    async _setState(state: unknown): Promise<void> {
        const item = this._resolved();
        if (!item) {
            throw new Error('platform-work-item-detail: no item');
        }
        if (item.state && TERMINAL.has(item.state)) {
            return;
        }
        await this._moveOp!.run({ work_item_id: item.work_item_id, state });
        this.emit('work-item-changed', { work_item_id: item.work_item_id, state });
    }

    async _saveTitle(): Promise<void> {
        const item = this._resolved();
        if (!item) {
            return;
        }
        const title = typeof this._titleDraft === 'string' ? this._titleDraft.trim() : '';
        if (!title || title === item.title) {
            return;
        }
        await this._patch({ title });
    }

    async _saveDescription(): Promise<void> {
        const item = this._resolved();
        if (!item) {
            return;
        }
        const description = typeof this._descriptionDraft === 'string' ? this._descriptionDraft : '';
        const current = typeof item.description === 'string' ? item.description : '';
        if (description === current) {
            return;
        }
        await this._patch({ description });
    }

    async _saveDue(value: unknown): Promise<void> {
        const item = this._resolved();
        if (!item) {
            return;
        }
        const normalized = typeof value === 'string' && value.length > 0
            ? normalizeIsoDateTimeForField(value)
            : null;
        const current = item.due_date !== null && item.due_date !== undefined && typeof item.due_date === 'string'
            ? normalizeIsoDateTimeForField(item.due_date)
            : null;
        this._dueDraft = normalized === null ? '' : normalized;
        if (normalized === current) {
            return;
        }
        await this._patch({ due_date: normalized });
    }

    async _saveAssignee(userId: unknown): Promise<void> {
        const item = this._resolved();
        if (!item) {
            throw new Error('platform-work-item-detail: no item');
        }
        const assignment = typeof userId !== 'string' || userId.length === 0
            ? { assignee_kind: 'unassigned' }
            : { assignee_kind: 'users', user_ids: [userId] };
        const result = await this._assignOp!.run({
            work_item_id: item.work_item_id,
            assignment,
        });
        if (result && typeof result === 'object' && typeof (result as WorkItemRecord).work_item_id === 'string') {
            this.item = result as WorkItemRecord;
            this._hydrateDrafts(this.item);
        }
        this.emit('work-item-changed', { work_item_id: item.work_item_id });
    }

    async _saveAttachments(files: unknown): Promise<void> {
        this._attachmentsDraft = _cloneFileRefs(files);
        await this._patch({ attachments: this._attachmentsDraft });
    }

    _openFull(): void {
        const item = this._resolved();
        if (!item) {
            throw new Error('platform-work-item-detail: no item');
        }
        if (this.bus) {
            navigateToWorkItemPage(item.work_item_id, this.bus, { from: 'crm' });
            return;
        }
        openWorkItemDetail(item.work_item_id, this.bus);
    }

    _openGraph(): void {
        const item = this._resolved();
        const entityId = item ? _crmEntityId(item) : '';
        if (!entityId) {
            throw new Error('platform-work-item-detail: no crm_entity link');
        }
        this.emit('open-crm-entity', { entity_id: entityId });
    }

    _teamOptions(): { value: string; label: string }[] {
        const members = this._teamSel.value;
        if (!Array.isArray(members)) {
            return [];
        }
        const values = [];
        for (const member of members) {
            if (!member || typeof member.user_id !== 'string' || member.user_id.length === 0) {
                continue;
            }
            const name = typeof member.name === 'string' && member.name.length > 0
                ? member.name
                : member.user_id;
            values.push({ value: member.user_id, label: name });
        }
        return values;
    }

    _renderAssigneeControl(item: WorkItemRecord): TemplateResult {
        const assignee = _assigneeUserId(item);
        const teamOptions = this._teamOptions();
        const loading = Boolean(this._teamLoadingSel.value);

        if (teamOptions.length === 0 && loading) {
            return html`<glass-spinner></glass-spinner>`;
        }

        return html`
            <platform-field
                type="enum"
                mode="edit"
                pill-density="dense"
                pill-embed
                .label=${''}
                .value=${assignee}
                .config=${{
                    values: [
                        { value: '', label: this.t('work_item.row_unassigned') },
                        ...teamOptions,
                    ],
                }}
                @change=${(e: CustomEvent<{ value?: unknown }>) => void this._saveAssignee(e.detail?.value)}
            ></platform-field>
        `;
    }

    _renderInspector(item: WorkItemRecord): TemplateResult {
        const state = typeof item.state === 'string' && STATES.includes(item.state) ? item.state : 'open';
        const priority = typeof item.priority === 'string' && PRIORITIES.includes(item.priority) ? item.priority : 'normal';
        const terminal = TERMINAL.has(state);

        return html`
            <section class="inspector">
                <h3 class="inspector-title">${this.t('work_item.section_properties')}</h3>
                <div class="inspector-row">
                    <span class="inspector-label">${this.t('work_item.state_label')}</span>
                    <div class="inspector-control">
                        <platform-field
                            type="enum"
                            mode="edit"
                            pill-density="dense"
                            pill-embed
                            .label=${''}
                            .value=${state}
                            ?disabled=${terminal}
                            .config=${{
                                values: STATES.map((s) => ({
                                    value: s,
                                    label: this.t(`work_item_badge.state.${s}`),
                                })),
                            }}
                            @change=${(e: CustomEvent<{ value?: unknown }>) => void this._setState(e.detail?.value)}
                        ></platform-field>
                    </div>
                </div>
                <div class="inspector-row">
                    <span class="inspector-label">${this.t('work_item.priority_label')}</span>
                    <div class="inspector-control">
                        <platform-field
                            type="enum"
                            mode="edit"
                            pill-density="dense"
                            pill-embed
                            .label=${''}
                            .value=${priority}
                            .config=${{
                                values: PRIORITIES.map((p) => ({
                                    value: p,
                                    label: this.t(`work_item_badge.priority.${p}`),
                                })),
                            }}
                            @change=${(e: CustomEvent<{ value?: unknown }>) => void this._patch({ priority: e.detail?.value })}
                        ></platform-field>
                    </div>
                </div>
                <div class="inspector-row">
                    <span class="inspector-label">${this.t('work_item.due_label')}</span>
                    <div class="inspector-control">
                        <platform-field
                            type="datetime"
                            mode="edit"
                            pill-density="dense"
                            pill-embed
                            .label=${''}
                            .value=${this._dueDraft}
                            @change=${(e: CustomEvent<{ value?: unknown }>) => void this._saveDue(e.detail?.value)}
                        ></platform-field>
                    </div>
                </div>
                <div class="inspector-row">
                    <span class="inspector-label">${this.t('work_item.assignee_label')}</span>
                    <div class="inspector-control">
                        ${this._renderAssigneeControl(item)}
                    </div>
                </div>
            </section>
        `;
    }

    override render(): TemplateResult {
        const item = this._resolved();
        if (!item) {
            const loading = Boolean(this._getOp && this._getOp.busy);
            return loading
                ? html`<div class="loading"><glass-spinner></glass-spinner></div>`
                : html`<div class="empty">${this.t('work_item_badge.loading')}</div>`;
        }
        const entityId = _crmEntityId(item);
        const showClose = this.layout === 'panel';

        return html`
            <div class="head">
                <span class="head-title">${this.t('work_item.detail_title')}</span>
                <div class="head-actions">
                    ${item.kind === 'operator_handoff' ? html`
                        <button
                            type="button"
                            class="cta-btn"
                            @click=${() => this._openFull()}
                        >${this.t('work_item.open_in_tasks')}</button>
                    ` : nothing}
                    <button
                        type="button"
                        class="icon-btn"
                        @click=${() => this._openFull()}
                        aria-label=${this.t('work_item.open_full')}
                        title=${this.t('work_item.open_full')}
                    >
                        <platform-icon name="expand" size="18"></platform-icon>
                    </button>
                    ${showClose
                        ? html`
                            <button
                                type="button"
                                class="icon-btn"
                                @click=${() => this.emit('close-requested', null)}
                                aria-label=${this.t('work_item.close_panel')}
                                title=${this.t('work_item.close_panel')}
                            >
                                <platform-icon name="x" size="18"></platform-icon>
                            </button>
                          `
                        : nothing}
                </div>
            </div>
            <div class="body">
                <div class="title-block">
                    <platform-field
                        class="title-field"
                        type="string"
                        mode="edit"
                        pill-embed
                        pill-density=${this.layout === 'page' ? 'default' : 'dense'}
                        .label=${''}
                        .value=${this._titleDraft}
                        @change=${(e: CustomEvent<{ value?: unknown }>) => {
                            this._titleDraft = typeof e.detail?.value === 'string' ? e.detail.value : '';
                        }}
                        @focusout=${() => this._saveTitle()}
                    ></platform-field>
                    <platform-markdown-editor
                        class="desc-editor"
                        variant="embed"
                        .value=${this._descriptionDraft}
                        .enableVariables=${true}
                        .label=${this.t('work_item.description_label')}
                        .placeholder=${this.t('work_item.empty_description')}
                        .showHeader=${true}
                        .showPreview=${false}
                        .showHint=${false}
                        @change=${(e: CustomEvent<{ value?: unknown }>) => {
                            const value = e.detail && typeof e.detail.value === 'string' ? e.detail.value : '';
                            this._descriptionDraft = value;
                        }}
                        @blur=${() => this._saveDescription()}
                    ></platform-markdown-editor>
                </div>

                <section>
                    <h4 class="section-label">${this.t('work_item.section_attachments')}</h4>
                    <platform-file-attachments
                        .files=${this._attachmentsDraft}
                        .uploadSpec=${buildWorkItemFileCreateSpecJson({ workItemId: item.work_item_id })}
                        open-source="platform_work_item_attachments"
                        @files-change=${(e: CustomEvent<{ files?: unknown }>) => {
                            const files = e.detail && Array.isArray(e.detail.files) ? e.detail.files : [];
                            void this._saveAttachments(files);
                        }}
                    ></platform-file-attachments>
                </section>

                ${this._renderInspector(item)}

                ${this.showGraphLink && entityId
                    ? html`
                        <div class="actions">
                            <platform-button variant="ghost" @click=${() => this._openGraph()}>
                                ${this.t('work_item.open_entity')}
                            </platform-button>
                        </div>
                      `
                    : nothing}
            </div>
        `;
    }
}

customElements.define('platform-work-item-detail', PlatformWorkItemDetail);
