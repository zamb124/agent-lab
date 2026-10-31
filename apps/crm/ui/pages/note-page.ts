/**
 * CRMNotePage — детальная страница заметки CRM.
 *
 * Маршрут: `/crm/notes/:itemId`. Поддерживает три случая, всё через один
 * компонент `<crm-note-card-view>`:
 *   - `itemId === 'new'` или `'draft-*'` — создание заметки (mode=`edit`,
 *     note=null).
 *   - `itemId === <real id>` — view-режим (mode=`view`, note=entity), edit
 *     включается по emit `edit-note`.
 *
 * Источники данных:
 *   - `useResource('crm/entities')`           — entity заметки по id.
 *   - `useOp('crm/entity_card')`              — карточка с related/relationships.
 *   - `useResource('crm/relationship_types')` — подписи типов связей.
 *
 * Обработка событий от note-card-view:
 *   - `edit-note`               → mode=`edit`.
 *   - `cancel`                  → mode=`view` (или navigate('notes') для draft).
 *   - `saved` { entity }        → mode=`view` + перезагрузка card.
 *   - `created` { entity }      → navigate на новый id.
 *   - `delete-note`             → openModal('crm.entity_delete', redirectRoute='notes').
 *   - `entity-open` { entityId} → toast (страница entity-detail в G/4).
 */

import { html, css, nothing } from 'lit';
import { CRMNamespacePage } from './crm-namespace-page.js';
import { CoreEvents } from '@platform/lib/events/index.js';
import { CRM_NOTE_UPDATED, CRM_TASK_UPDATED } from '../events/types.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-spinner.js';
import '@platform/lib/components/platform-empty-state.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-breadcrumbs.js';
import '@platform/lib/components/platform-icon.js';
import '../components/note-card-view.js';
import { crmNotePageMobileToolbarHostStyles } from '../styles/crm-note-page-mobile-toolbar-host.styles.js';
import type {
    CSSResultGroup,
    PropertyDeclarations,
    PropertyValues,
    TemplateResult,
} from 'lit';
import type {
    OpController,
    ResourceController,
} from '@platform/lib/base/use-resource.js';
import type { PlatformEvent } from '@platform/lib/events/contract.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';

function anyRecord(value: unknown): Record<string, unknown> | null {
    return isPlainRecord(value) ? value : null;
}

const ACTIVE_ANALYZE_TASK_STATUSES = new Set(['pending', 'running']);
const TASK_RELATIONSHIP_TYPE = 'related_to';
const NOTE_MARKDOWN_FORMAT_UI_TIMEOUT_MS = 180000;

export class CRMNotePage extends CRMNamespacePage {
    static i18nNamespace = 'crm';

    static override properties: PropertyDeclarations = {
        noteId: { type: String },
        _card: { state: true },
        _cardError: { state: true },
        _mode: { state: true },
        _mobileHeaderPanel: { state: true },
        _markdownFormatting: { state: true },
        _markdownFormatProgress: { state: true },
    };
    declare noteId: string;
    declare _card: Record<string, unknown> | null;
    declare _cardError: string;
    declare _mode: 'view' | 'edit';
    declare _mobileHeaderPanel: string;
    declare _markdownFormatting: boolean;
    declare _markdownFormatProgress: { done: number; total: number } | null;

    static override styles: CSSResultGroup = [
        CRMNamespacePage.styles,
        crmNotePageMobileToolbarHostStyles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                width: 100%;
                height: 100%;
                min-height: 0;
                overflow: hidden;
            }

            .breadcrumbs-wrap {
                flex-shrink: 0;
                padding: 0 var(--space-4);
                margin-top: var(--space-2);
                margin-bottom: var(--space-2);
            }

            .body {
                flex: 1;
                min-height: 0;
                padding: 0 var(--space-4) var(--space-4);
                overflow: hidden;
            }

            .center {
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                gap: var(--space-3);
                height: 100%;
                color: var(--text-secondary);
                text-align: center;
                padding: var(--space-6);
            }
            .center .icon { color: var(--text-tertiary); }
            .center h2 {
                margin: 0;
                font-size: var(--text-lg);
                color: var(--text-primary);
            }
            .center p {
                margin: 0;
                font-size: var(--text-sm);
                color: var(--text-secondary);
                max-width: 480px;
            }

            .back-btn {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-md);
                background: var(--glass-tint-subtle);
                color: var(--text-primary);
                font-size: var(--text-sm);
                cursor: pointer;
                transition: background var(--motion-duration-micro);
            }
            .back-btn:hover { background: var(--glass-tint-medium); }
            .note-mobile-header-wrap {
                display: none;
            }
            .note-mobile-header-actions {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
            }
            .note-mobile-header-btn {
                width: 36px;
                height: 36px;
                border: none;
                border-radius: var(--radius-full);
                background: var(--glass-tint-subtle);
                color: var(--text-primary);
                display: inline-flex;
                align-items: center;
                justify-content: center;
                padding: 0;
                cursor: pointer;
            }
            .note-mobile-header-btn.active {
                background: var(--accent);
                color: var(--text-primary);
            }
            @media (max-width: 767px) {
                .note-mobile-header-wrap {
                    display: block;
                    flex-shrink: 0;
                }
                .breadcrumbs-wrap {
                    padding-top: var(--space-3);
                }
            }
        `,
    ];

    private _entities: ResourceController;
    private _relationships: ResourceController;
    private _cardOp: OpController;
    private _entityUpdate: OpController;
    private _relTypes: ResourceController;
    private _tasks: ResourceController;
    private _analyzeOp: OpController;
    private _markdownFormatOp: OpController;
    private _markdownFormatUiTimer: number | null;
    private _lastRequestedId: string;
    private _draftVersionInitialized: boolean;
    private _lastDraftVersion: number | null;
    private _lastAutoOpenedDraftVersion: number | null;
    private _noteToolbarHost: HTMLElement | null;

    constructor() {
        super();
        this.noteId = '';
        this._card = null;
        this._cardError = '';
        this._mode = 'view';
        this._mobileHeaderPanel = '';
        this._markdownFormatting = false;
        this._markdownFormatProgress = null;
        this._markdownFormatUiTimer = null;
        this._lastRequestedId = '';
        this._entities = this.useResource('crm/entities');
        this._relationships = this.useResource('crm/relationships');
        this._cardOp = this.useOp('crm/entity_card');
        this._entityUpdate = this.useOp('crm/entity_update');
        this._relTypes = this.useResource('crm/relationship_types', { autoload: true });
        this._tasks = this.useResource('crm/tasks');
        this._analyzeOp = this.useOp('crm/note_analyze_start');
        this._markdownFormatOp = this.useOp('crm/note_markdown_format');
        this._draftVersionInitialized = false;
        this._lastDraftVersion = null;
        this._lastAutoOpenedDraftVersion = null;
        this._noteToolbarHost = null;
    }

    override connectedCallback(): void {
        super.connectedCallback();
        this.useEvent(CRM_NOTE_UPDATED, (event) => {
            const payload = anyRecord(event.payload);
            const noteId = payload ? payload.note_id : null;
            if (typeof noteId !== 'string' || noteId !== this.noteId) {
                return;
            }
            if (payload === null) {
                return;
            }
            const format = isPlainRecord(payload.markdown_format) ? payload.markdown_format : null;
            const phase = format !== null && typeof format.phase === 'string' ? format.phase : '';
            if (phase === 'started') {
                this._markdownFormatting = true;
                this._markdownFormatProgress = null;
                this._armMarkdownFormatUiTimeout();
                return;
            }
            if (phase === 'partial') {
                const done = format !== null && typeof format.chunks_done === 'number' ? format.chunks_done : 0;
                const total = format !== null && typeof format.chunks_total === 'number' ? format.chunks_total : 0;
                this._markdownFormatProgress = { done, total };
                this.requestUpdate();
                return;
            }
            this._clearMarkdownFormatUiTimeout();
            this._markdownFormatting = false;
            this._markdownFormatProgress = null;
            // Entity fields — из payload.note / crm/entities merge; related-граф
            // не перезагружаем на каждый note push (analyze — через crm/task/updated).
            const note = payload.note;
            if (isPlainRecord(note) && typeof note.entity_id === 'string' && this._card !== null) {
                this._card = { ...this._card, entity: note };
            }
            this.requestUpdate();
        });
        this.useEvent(this._cardOp.op.events.SUCCEEDED, (event) => {
            if (this._isStaleEntityCardOpEvent(event)) {
                return;
            }
            const p = anyRecord(event.payload);
            const result = p !== null && isPlainRecord(p.result) ? p.result : null;
            if (result === null) {
                throw new Error('crm/entity_card SUCCEEDED: payload.result missing');
            }
            this._card = result;
            this._cardError = '';
        });
        this.useEvent(this._cardOp.op.events.FAILED, (event) => {
            if (this._isStaleEntityCardOpEvent(event)) {
                return;
            }
            const p = anyRecord(event.payload);
            const err = p !== null && isPlainRecord(p.error) ? p.error : null;
            this._card = null;
            this._cardError = err !== null && typeof err.message === 'string' ? err.message : 'load_failed';
        });
        this.useEvent(this._tasks.resource.events.LIST_LOADED, () => {
            this.requestUpdate();
        });
        this.useEvent(CRM_TASK_UPDATED, () => {
            this.requestUpdate();
        });

        this.useEvent(this._markdownFormatOp.op.events.FAILED, () => {
            this._clearMarkdownFormatUiTimeout();
            this._markdownFormatting = false;
            this._markdownFormatProgress = null;
        });
        this.useEvent(CoreEvents.UI_NAMESPACE_CHANGED, () => this.requestUpdate());
    }

    override willUpdate(changed: PropertyValues<this>): void {
        if (!changed.has('noteId')) {
            return;
        }
        if (typeof this.noteId !== 'string' || this.noteId.length === 0) {
            this._clearMarkdownFormatUiTimeout();
            this._markdownFormatting = false;
            this._markdownFormatProgress = null;
            this._draftVersionInitialized = false;
            this._lastDraftVersion = null;
            this._lastAutoOpenedDraftVersion = null;
            this._card = null;
            this._cardError = '';
            this._lastRequestedId = '';
            this._mode = 'view';
            return;
        }
        if (this._isDraftId(this.noteId)) {
            this._clearMarkdownFormatUiTimeout();
            this._markdownFormatting = false;
            this._markdownFormatProgress = null;
            this._draftVersionInitialized = false;
            this._lastDraftVersion = null;
            this._lastAutoOpenedDraftVersion = null;
            this._card = null;
            this._cardError = '';
            this._mode = 'edit';
            return;
        }
        if (this._lastRequestedId === this.noteId) {
            return;
        }
        this._lastRequestedId = this.noteId;
        this._mode = 'view';
        this._clearMarkdownFormatUiTimeout();
        this._markdownFormatting = false;
        this._markdownFormatProgress = null;
        this._reloadCurrent();
    }

    override updated(changed: PropertyValues<this>): void {
        super.updated(changed);
        const hostCandidate = this.renderRoot?.querySelector('.crm-note-page-card-toolbar-host');
        const nextToolbarHost = hostCandidate instanceof HTMLElement ? hostCandidate : null;
        if (nextToolbarHost !== this._noteToolbarHost) {
            this._noteToolbarHost = nextToolbarHost;
            this.requestUpdate();
        }

        const note = this._resolveNote();
        if (note === null) {
            return;
        }
        const draftVersion = this._draftVersion(note);
        if (!this._draftVersionInitialized) {
            this._draftVersionInitialized = true;
            this._lastDraftVersion = draftVersion;
            return;
        }
        if (typeof draftVersion === 'number'
            && draftVersion !== this._lastDraftVersion
            && this._lastAutoOpenedDraftVersion !== draftVersion) {
            this._lastAutoOpenedDraftVersion = draftVersion;
            this.openModal('crm.ai_analysis', { noteId: this.noteId });
        }
        this._lastDraftVersion = draftVersion;
    }

    _isDraftId(value: unknown): boolean {
        return value === 'new' || (typeof value === 'string' && value.startsWith('draft-'));
    }

    /**
     * Два быстрых `crm/note/updated` при analyze→apply порождают параллельные GET card;
     * ответ без связей может прийти позже свежего — не перезаписываем UI.
     */
    _isStaleEntityCardOpEvent(event: PlatformEvent | null): boolean {
        const meta = event && event.meta;
        const causationId = meta && typeof meta.causation_id === 'string' ? meta.causation_id : null;
        const latestId = this._cardOp.lastRequestId;
        return causationId !== null && latestId !== null && causationId !== latestId;
    }

    _reloadCurrent() {
        if (typeof this.noteId !== 'string' || this.noteId.length === 0 || this._isDraftId(this.noteId)) {
            return;
        }
        this._entities.get(this.noteId);
        this._reloadCardOnly();
        this._loadAnalyzeTasks();
    }

    _reloadCardOnly() {
        this._cardOp.run({ entity_id: this.noteId }).catch((error) => {
            const message = error instanceof Error ? error.message : 'load_failed';
            this._cardError = message;
        });
    }

    override disconnectedCallback(): void {
        this._clearMarkdownFormatUiTimeout();
        super.disconnectedCallback();
    }

    _clearMarkdownFormatUiTimeout() {
        if (this._markdownFormatUiTimer === null) {
            return;
        }
        window.clearTimeout(this._markdownFormatUiTimer);
        this._markdownFormatUiTimer = null;
    }

    _armMarkdownFormatUiTimeout() {
        this._clearMarkdownFormatUiTimeout();
        this._markdownFormatUiTimer = window.setTimeout(() => {
            this._markdownFormatUiTimer = null;
            if (!this._markdownFormatting) {
                return;
            }
            this._markdownFormatting = false;
            this._markdownFormatProgress = null;
            this.toast('toast.note.markdown_format_timeout', { type: 'warning' });
        }, NOTE_MARKDOWN_FORMAT_UI_TIMEOUT_MS);
    }

    _onMarkdownFormatAttachmentQueued() {
        if (typeof this.noteId !== 'string' || this.noteId.length === 0 || this._isDraftId(this.noteId)) {
            return;
        }
        if (this._markdownFormatting) {
            return;
        }
        this._markdownFormatting = true;
        this._markdownFormatProgress = null;
        this._armMarkdownFormatUiTimeout();
    }

    _onFormatMarkdownRequest() {
        if (typeof this.noteId !== 'string' || this.noteId.length === 0 || this._isDraftId(this.noteId)) {
            throw new Error('CRMNotePage._onFormatMarkdownRequest: noteId required');
        }
        if (this._markdownFormatting) {
            return;
        }
        this._markdownFormatting = true;
        this._markdownFormatProgress = null;
        this._markdownFormatOp.run({ note_id: this.noteId });
        this._armMarkdownFormatUiTimeout();
    }

    _loadAnalyzeTasks() {
        if (typeof this.noteId !== 'string' || this.noteId.length === 0 || this._isDraftId(this.noteId)) {
            return;
        }
        this._tasks.load({
            limit: 20,
            offset: 0,
            task_type: 'note_analyze',
            note_id: this.noteId,
        });
    }

    _activeAnalyzeTask() {
        const items = this._tasks.items;
        const found = items.find((task) => {
            const data = anyRecord(task.data);
            const taskNoteId = data !== null && typeof data.note_id === 'string' ? data.note_id : null;
            return taskNoteId === this.noteId && ACTIVE_ANALYZE_TASK_STATUSES.has(task.status as string);
        });
        return found === undefined ? null : found;
    }

    _isAnalyzingNow() {
        return this._analyzeOp.busy || this._activeAnalyzeTask() !== null;
    }

    _analyzeProgressPct() {
        const activeTask = this._activeAnalyzeTask();
        if (activeTask === null) {
            return 0;
        }
        return typeof activeTask.progress_pct === 'number' ? activeTask.progress_pct : 0;
    }

    _analyzeProgressStage() {
        const activeTask = this._activeAnalyzeTask();
        if (activeTask === null) {
            return '';
        }
        return typeof activeTask.stage === 'string' ? activeTask.stage : '';
    }

    _analyzeProgressStatus() {
        const activeTask = this._activeAnalyzeTask();
        if (activeTask === null) {
            return '';
        }
        return typeof activeTask.status === 'string' ? activeTask.status : '';
    }

    _analyzeStatusText() {
        return this._analyzeOp.busy
            ? this.t('note_view.summary_analyze_starting')
            : this.t('note_view.summary_analyzing');
    }

    _onRefreshSummary() {
        if (typeof this.noteId !== 'string' || this.noteId.length === 0 || this._isDraftId(this.noteId)) {
            throw new Error('CRMNotePage._onRefreshSummary: noteId required');
        }
        this._analyzeOp.run({ note_id: this.noteId, mode: 'analyze' });
        this._loadAnalyzeTasks();
    }

    _resolveNote(): Record<string, unknown> | null {
        return anyRecord(this._entities.byId[this.noteId]);
    }

    _currentNamespace() {
        const raw = this._crmNamespaceSel.value;
        if (raw === null || raw === undefined) {
            return 'default';
        }
        return raw;
    }

    _onBackToNotes() {
        this.navigate('notes');
    }

    _onEntityOpen(event: CustomEvent) {
        const detail = event.detail;
        const rawId = detail && typeof detail.entityId === 'string' ? detail.entityId : '';
        const entityId = rawId.trim();
        if (entityId.length === 0) {
            return;
        }
        const entityType = detail && typeof detail.entity_type === 'string' ? detail.entity_type.trim() : '';
        if (entityType === 'note') {
            this.navigate('note', { itemId: entityId });
            return;
        }
        this.navigate('entity', { itemId: entityId });
    }

    _onDeleteNote() {
        this.openModal('crm.entity_delete', { entityId: this.noteId, redirectRoute: 'notes' });
    }

    _onEditNote() {
        this._mobileHeaderPanel = '';
        this._mode = 'edit';
    }

    _toggleMobileHeaderPanel(panel: string) {
        if (panel !== 'summary' && panel !== 'neighbors' && panel !== 'graph') {
            throw new Error('CRMNotePage._toggleMobileHeaderPanel: unknown panel');
        }
        this._mobileHeaderPanel = this._mobileHeaderPanel === panel ? '' : panel;
    }

    _onOverlayPanelToggle(event: CustomEvent<{ panel?: unknown }>) {
        const panel = event.detail && typeof event.detail.panel === 'string' ? event.detail.panel.trim() : '';
        if (panel !== 'graph') {
            throw new Error('CRMNotePage._onOverlayPanelToggle: expected panel graph');
        }
        this._toggleMobileHeaderPanel(panel);
    }

    _onEditCancel() {
        if (this._isDraftId(this.noteId)) {
            this.navigate('notes');
            return;
        }
        this._mode = 'view';
    }

    _onEditSaved() {
        this._mode = 'view';
        this._reloadCurrent();
    }

    _onEditCreated(event: CustomEvent) {
        const detail = anyRecord(event.detail);
        const created = detail !== null ? anyRecord(detail.entity) : null;
        if (!created || typeof created.entity_id !== 'string') return;
        this.navigate('note', { itemId: created.entity_id });
    }

    _waitForResourceResult(controller: ResourceController, requestedId: string): Promise<Record<string, unknown> | null> {
        const bus = controller.bus;
        const successType = controller.resource.events.CREATED;
        const failedType = controller.resource.events.CREATE_FAILED;
        return new Promise((resolve, reject) => {
            let offSuccess: (() => void) | null = null;
            let offFailed: (() => void) | null = null;
            const cleanup = () => {
                if (typeof offSuccess === 'function') offSuccess();
                if (typeof offFailed === 'function') offFailed();
            };
            offSuccess = bus.subscribeType(successType, (event) => {
                if (!event.meta || event.meta.causation_id !== requestedId) {
                    return;
                }
                cleanup();
                const pl = anyRecord(event.payload);
                const item = pl !== null ? anyRecord(pl.item) : null;
                resolve(item);
            });
            offFailed = bus.subscribeType(failedType, (event) => {
                if (!event.meta || event.meta.causation_id !== requestedId) {
                    return;
                }
                cleanup();
                const pl = anyRecord(event.payload);
                const message = pl && typeof pl.message === 'string'
                    ? pl.message
                    : 'resource create failed';
                reject(new Error(message));
            });
        });
    }

    async _createEntity(payload: Record<string, unknown>) {
        const requested = this._entities.create(payload);
        if (!requested || typeof requested.id !== 'string') {
            throw new Error('CRMNotePage._createEntity: create dispatch returned no id');
        }
        return await this._waitForResourceResult(this._entities, requested.id);
    }

    async _createRelationship(payload: Record<string, unknown>) {
        const requested = this._relationships.create(payload);
        if (!requested || typeof requested.id !== 'string') {
            throw new Error('CRMNotePage._createRelationship: create dispatch returned no id');
        }
        return await this._waitForResourceResult(this._relationships, requested.id);
    }

    async _onTaskAdd(event: CustomEvent<{ text?: unknown }>) {
        const text = event.detail && typeof event.detail.text === 'string' ? event.detail.text.trim() : '';
        const note = this._resolveNote();
        if (text.length === 0 || note === null) {
            return;
        }
        const namespace = typeof note.namespace === 'string' && note.namespace.length > 0
            ? note.namespace
            : this._currentNamespace();
        try {
            const task = await this._createEntity({
                entity_type: 'task',
                namespace,
                name: text,
                description: null,
                attributes: {},
            });
            if (!task || typeof task.entity_id !== 'string') {
                throw new Error('CRMNotePage._onTaskAdd: task create returned empty entity');
            }
            await this._createRelationship({
                source_entity_id: this.noteId,
                target_entity_id: task.entity_id,
                relationship_type: TASK_RELATIONSHIP_TYPE,
                namespace,
            });
            this._reloadCardOnly();
        } catch (error) {
            const message = error instanceof Error ? error.message : this.t('note_edit.err_save');
            this.toast('crm:toast.entity.create_failed', { type: 'error', vars: { message } });
        }
    }

    _onTaskRemove(event: CustomEvent) {
        const taskId = event.detail && typeof event.detail.entityId === 'string' ? event.detail.entityId : '';
        if (taskId.length === 0) {
            return;
        }
        this._entities.remove(taskId);
        this._reloadCardOnly();
    }

    _noteLabel(note: Record<string, unknown> | null): string {
        if (!note) return '';
        if (typeof note.name === 'string' && note.name.trim().length > 0) return note.name.trim();
        if (typeof note.entity_id === 'string') return note.entity_id;
        return '';
    }

    _draftVersion(note: Record<string, unknown> | null): number | null {
        if (note === null || !isPlainRecord(note.attributes)) {
            return null;
        }
        const draft = note.attributes.ai_analysis_draft;
        if (!isPlainRecord(draft) || typeof draft.draft_version !== 'number') {
            return null;
        }
        return draft.draft_version;
    }

    _renderMobilePageHeader(showPanelActions: boolean): TemplateResult {
        return html`
            <div class="note-mobile-header-wrap">
                <page-header
                    title=${this.t('daily_notes_page.section_title')}
                    subtitle=""
                    actions-overflow="visible"
                >
                    <div slot="actions" class="crm-note-page-header-actions-row">
                        ${showPanelActions ? html`
                            <div class="note-mobile-header-actions">
                                <button
                                    type="button"
                                    class=${`note-mobile-header-btn ${this._mobileHeaderPanel === 'summary' ? 'active' : ''}`}
                                    title=${this.t('note_view.summary_title')}
                                    aria-expanded=${String(this._mobileHeaderPanel === 'summary')}
                                    @click=${() => this._toggleMobileHeaderPanel('summary')}
                                >
                                    <platform-icon name="ai" size="18" colored></platform-icon>
                                </button>
                                <button
                                    type="button"
                                    class=${`note-mobile-header-btn ${this._mobileHeaderPanel === 'neighbors' ? 'active' : ''}`}
                                    title=${this.t('entity_card.related_objects_section')}
                                    aria-expanded=${String(this._mobileHeaderPanel === 'neighbors')}
                                    @click=${() => this._toggleMobileHeaderPanel('neighbors')}
                                >
                                    <platform-icon name="folder" size="18"></platform-icon>
                                </button>
                                <button
                                    type="button"
                                    class=${`note-mobile-header-btn ${this._mobileHeaderPanel === 'graph' ? 'active' : ''}`}
                                    title=${this.t('note_view.graph_inline_title')}
                                    aria-expanded=${String(this._mobileHeaderPanel === 'graph')}
                                    @click=${() => this._toggleMobileHeaderPanel('graph')}
                                >
                                    <platform-icon name="git-branch" size="18"></platform-icon>
                                </button>
                            </div>
                        ` : nothing}
                        <div class="crm-note-page-card-toolbar-host"></div>
                    </div>
                </page-header>
            </div>
        `;
    }

    override render(): TemplateResult {
        if (typeof this.noteId !== 'string' || this.noteId.length === 0) {
            return html`
                ${this._renderMobilePageHeader(false)}
                <div class="body">
                    <platform-empty-state icon="info" title=${this.t('note_page.no_id_title')} hint=${this.t('note_page.no_id_message')}>
                        <platform-button variant="secondary" @click=${this._onBackToNotes}>
                            ${this.t('note_page.back_to_notes')}
                        </platform-button>
                    </platform-empty-state>
                </div>
            `;
        }

        if (this._isDraftId(this.noteId)) {
            return html`
                ${this._renderMobilePageHeader(false)}
                <div class="breadcrumbs-wrap">
                    <platform-breadcrumbs current-label=${this.t('note_page.draft_breadcrumb')}></platform-breadcrumbs>
                </div>
                <div class="body edit">
                    <crm-note-card-view
                        .note=${null}
                        mode="edit"
                        defaultNamespace=${this._currentNamespace()}
                        .mobileHeaderActionsHost=${this._noteToolbarHost}
                        @cancel=${this._onEditCancel}
                        @created=${this._onEditCreated}
                    ></crm-note-card-view>
                </div>
            `;
        }

        if (this._cardError) {
            return html`
                ${this._renderMobilePageHeader(false)}
                <div class="body">
                    <platform-empty-state icon="warning" title=${this.t('note_page.not_found_title')} hint=${this._cardError}>
                        <platform-button variant="secondary" @click=${this._onBackToNotes}>
                            ${this.t('note_page.back_to_notes')}
                        </platform-button>
                    </platform-empty-state>
                </div>
            `;
        }

        const note = this._resolveNote();
        const entityLoading = this._entities.loading;

        if (!note || entityLoading) {
            return html`
                ${this._renderMobilePageHeader(false)}
                <div class="body">
                    <platform-empty-state loading></platform-empty-state>
                </div>
            `;
        }

        if (this._mode === 'edit') {
            return html`
                ${this._renderMobilePageHeader(false)}
                <div class="breadcrumbs-wrap">
                    <platform-breadcrumbs current-label=${this._noteLabel(note)}></platform-breadcrumbs>
                </div>
                <div class="body edit">
                    <crm-note-card-view
                        .note=${note}
                        .card=${this._card}
                        mode="edit"
                        .mobileHeaderActionsHost=${this._noteToolbarHost}
                        @cancel=${this._onEditCancel}
                        @saved=${this._onEditSaved}
                    ></crm-note-card-view>
                </div>
            `;
        }

        if (!this._card) {
            return html`
                ${this._renderMobilePageHeader(false)}
                <div class="body">
                    <platform-empty-state loading></platform-empty-state>
                </div>
            `;
        }

        const relationshipTypes = Array.isArray(this._relTypes.items) ? this._relTypes.items : [];
        return html`
            ${this._renderMobilePageHeader(true)}
            <div class="breadcrumbs-wrap">
                <platform-breadcrumbs current-label=${this._noteLabel(note)}></platform-breadcrumbs>
            </div>
            <div class="body">
                <crm-note-card-view
                    .note=${note}
                    .card=${this._card}
                    .relationshipTypes=${relationshipTypes}
                    .aiAnalyzing=${this._isAnalyzingNow()}
                    .aiStatusText=${this._analyzeStatusText()}
                    .aiProgressPct=${this._analyzeProgressPct()}
                    .aiProgressStage=${this._analyzeProgressStage()}
                    .aiProgressStatus=${this._analyzeProgressStatus()}
                    .markdownFormatting=${this._markdownFormatting}
                    .markdownFormatProgress=${this._markdownFormatProgress}
                    .mobileHeaderPanel=${this._mobileHeaderPanel}
                    .mobileHeaderActionsHost=${this._noteToolbarHost}
                    mode="view"
                    @entity-open=${this._onEntityOpen}
                    @delete-note=${this._onDeleteNote}
                    @edit-note=${this._onEditNote}
                    @refresh-summary=${this._onRefreshSummary}
                    @format-markdown-request=${this._onFormatMarkdownRequest}
                    @markdown-format-attachment-queued=${this._onMarkdownFormatAttachmentQueued}
                    @task-add=${this._onTaskAdd}
                    @task-remove=${this._onTaskRemove}
                    @overlay-panel-toggle=${this._onOverlayPanelToggle}
                ></crm-note-card-view>
            </div>
            ${nothing}
        `;
    }
}

customElements.define('crm-note-page', CRMNotePage);
