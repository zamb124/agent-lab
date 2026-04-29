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
 *   - `show-graph`              → openModal('crm.note_graph').
 *   - `delete-note`             → openModal('crm.entity_delete', redirectRoute='notes').
 *   - `entity-open` { entityId} → toast (страница entity-detail в G/4).
 */

import { html, css, nothing } from 'lit';
import { CRMNamespacePage } from '../base/crm-namespace-page.js';
import { CoreEvents } from '@platform/lib/events/index.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-breadcrumbs.js';
import '@platform/lib/components/platform-icon.js';
import '../components/note-card-view.js';

const ACTIVE_ANALYZE_TASK_STATUSES = new Set(['pending', 'running']);
const ANALYZE_TASK_POLL_MS = 2500;
const TASK_RELATIONSHIP_TYPE = 'related_to';

export class CRMNotePage extends CRMNamespacePage {
    static i18nNamespace = 'crm';

    static properties = {
        noteId: { type: String },
        _card: { state: true },
        _cardError: { state: true },
        _mode: { state: true },
    };

    static styles = [
        CRMNamespacePage.styles,
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
                border: 1px solid var(--crm-stroke, var(--glass-border-medium));
                border-radius: var(--radius-md);
                background: var(--glass-tint-subtle);
                color: var(--text-primary);
                font-size: var(--text-sm);
                cursor: pointer;
                transition: background var(--duration-fast);
            }
            .back-btn:hover { background: var(--glass-tint-medium); }
        `,
    ];

    constructor() {
        super();
        this.noteId = '';
        this._card = null;
        this._cardError = '';
        this._mode = 'view';
        this._lastRequestedId = '';
        this._entities = this.useResource('crm/entities');
        this._relationships = this.useResource('crm/relationships');
        this._cardOp = this.useOp('crm/entity_card');
        this._entityUpdate = this.useOp('crm/entity_update');
        this._relTypes = this.useResource('crm/relationship_types', { autoload: true });
        this._tasks = this.useResource('crm/tasks');
        this._analyzeOp = this.useOp('crm/note_analyze_start');
        this._analyzeTaskPollTimer = null;
        this._draftVersionInitialized = false;
        this._lastDraftVersion = null;
        this._lastAutoOpenedDraftVersion = null;
    }

    connectedCallback() {
        super.connectedCallback();
        this.useEvent('crm/note/updated', (event) => {
            const noteId = event && event.payload ? event.payload.note_id : null;
            if (typeof noteId !== 'string' || noteId !== this.noteId) {
                return;
            }
            this._reloadCurrent();
        });
        this.useEvent(this._cardOp.op.events.SUCCEEDED, (event) => {
            const result = event.payload && event.payload.result ? event.payload.result : null;
            if (!result || typeof result !== 'object') {
                throw new Error('crm/entity_card SUCCEEDED: payload.result missing');
            }
            this._card = result;
            this._cardError = '';
        });
        this.useEvent(this._cardOp.op.events.FAILED, (event) => {
            const err = event.payload && event.payload.error ? event.payload.error : null;
            this._card = null;
            this._cardError = err && typeof err.message === 'string' ? err.message : 'load_failed';
        });
        this.useEvent(this._tasks.resource.events.LIST_LOADED, () => this._syncAnalyzeTaskPolling());
        this.useEvent(this._analyzeOp.op.events.SUCCEEDED, () => {
            this._loadAnalyzeTasks();
            this._syncAnalyzeTaskPolling();
        });
        this.useEvent(this._analyzeOp.op.events.FAILED, () => this._syncAnalyzeTaskPolling());
        this.useEvent(CoreEvents.UI_NAMESPACE_CHANGED, () => this.requestUpdate());
    }

    willUpdate(changed) {
        if (!changed.has('noteId')) {
            return;
        }
        if (typeof this.noteId !== 'string' || this.noteId.length === 0) {
            this._stopAnalyzeTaskPolling();
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
            this._stopAnalyzeTaskPolling();
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
        this._reloadCurrent();
    }

    updated(changed) {
        super.updated(changed);
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

    _isDraftId(value) {
        return value === 'new' || (typeof value === 'string' && value.startsWith('draft-'));
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

    disconnectedCallback() {
        this._stopAnalyzeTaskPolling();
        super.disconnectedCallback();
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
        return items.find((task) => {
            const data = task && typeof task.data === 'object' && task.data !== null ? task.data : null;
            const taskNoteId = data && typeof data.note_id === 'string' ? data.note_id : null;
            return taskNoteId === this.noteId && ACTIVE_ANALYZE_TASK_STATUSES.has(task.status);
        }) || null;
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

    _syncAnalyzeTaskPolling() {
        if (this._isAnalyzingNow()) {
            this._startAnalyzeTaskPolling();
            return;
        }
        this._stopAnalyzeTaskPolling();
    }

    _startAnalyzeTaskPolling() {
        if (this._analyzeTaskPollTimer !== null) {
            return;
        }
        this._analyzeTaskPollTimer = window.setInterval(() => {
            this._loadAnalyzeTasks();
        }, ANALYZE_TASK_POLL_MS);
    }

    _stopAnalyzeTaskPolling() {
        if (this._analyzeTaskPollTimer === null) {
            return;
        }
        window.clearInterval(this._analyzeTaskPollTimer);
        this._analyzeTaskPollTimer = null;
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
        this._syncAnalyzeTaskPolling();
        this._loadAnalyzeTasks();
    }

    _resolveNote() {
        const byId = this._entities.byId;
        if (byId && byId[this.noteId]) {
            return byId[this.noteId];
        }
        return null;
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

    _onEntityOpen(event) {
        const entityId = event.detail && event.detail.entityId ? event.detail.entityId : '';
        if (typeof entityId !== 'string' || entityId.length === 0) {
            return;
        }
        this.navigate('entity', { itemId: entityId });
    }

    _onShowGraph() {
        this.openModal('crm.note_graph', { noteId: this.noteId });
    }

    _onDeleteNote() {
        this.openModal('crm.entity_delete', { entityId: this.noteId, redirectRoute: 'notes' });
    }

    _onEditNote() {
        this._mode = 'edit';
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

    _onEditCreated(event) {
        const created = event.detail && event.detail.entity ? event.detail.entity : null;
        if (!created || typeof created.entity_id !== 'string') return;
        this.navigate('note', { itemId: created.entity_id });
    }

    _waitForResourceResult(controller, requestedId) {
        const bus = controller.bus;
        const successType = controller.resource.events.CREATED;
        const failedType = controller.resource.events.CREATE_FAILED;
        return new Promise((resolve, reject) => {
            let offSuccess = null;
            let offFailed = null;
            const cleanup = () => {
                if (typeof offSuccess === 'function') offSuccess();
                if (typeof offFailed === 'function') offFailed();
            };
            offSuccess = bus.subscribeType(successType, (event) => {
                if (!event.meta || event.meta.causation_id !== requestedId) {
                    return;
                }
                cleanup();
                const item = event.payload && typeof event.payload.item === 'object'
                    ? event.payload.item
                    : null;
                resolve(item);
            });
            offFailed = bus.subscribeType(failedType, (event) => {
                if (!event.meta || event.meta.causation_id !== requestedId) {
                    return;
                }
                cleanup();
                const message = event.payload && typeof event.payload.message === 'string'
                    ? event.payload.message
                    : 'resource create failed';
                reject(new Error(message));
            });
        });
    }

    async _createEntity(payload) {
        const requested = this._entities.create(payload);
        if (!requested || typeof requested.id !== 'string') {
            throw new Error('CRMNotePage._createEntity: create dispatch returned no id');
        }
        return await this._waitForResourceResult(this._entities, requested.id);
    }

    async _createRelationship(payload) {
        const requested = this._relationships.create(payload);
        if (!requested || typeof requested.id !== 'string') {
            throw new Error('CRMNotePage._createRelationship: create dispatch returned no id');
        }
        return await this._waitForResourceResult(this._relationships, requested.id);
    }

    _taskById(taskId) {
        const related = this._card && Array.isArray(this._card.related_entities)
            ? this._card.related_entities
            : [];
        return related.find((item) => item && item.entity_type === 'task' && item.entity_id === taskId) || null;
    }

    async _onTaskAdd(event) {
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
                attributes: { status: 'todo' },
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

    async _onTaskToggle(event) {
        const taskId = event.detail && typeof event.detail.entityId === 'string' ? event.detail.entityId : '';
        const completed = Boolean(event.detail && event.detail.completed === true);
        if (taskId.length === 0) {
            return;
        }
        const task = this._taskById(taskId);
        const currentAttributes = task && typeof task.attributes === 'object' && task.attributes !== null
            ? task.attributes
            : {};
        try {
            await this._entityUpdate.run({
                id: taskId,
                body: {
                    attributes: {
                        ...currentAttributes,
                        status: completed ? 'done' : 'todo',
                    },
                },
            });
            this._reloadCardOnly();
        } catch (error) {
            const message = error instanceof Error ? error.message : this.t('note_edit.err_save');
            this.toast('crm:toast.entity.update_failed', { type: 'error', vars: { message } });
        }
    }

    _onTaskRemove(event) {
        const taskId = event.detail && typeof event.detail.entityId === 'string' ? event.detail.entityId : '';
        if (taskId.length === 0) {
            return;
        }
        this._entities.remove(taskId);
        this._reloadCardOnly();
    }

    _noteLabel(note) {
        if (!note) return '';
        if (typeof note.name === 'string' && note.name.trim().length > 0) return note.name.trim();
        if (typeof note.entity_id === 'string') return note.entity_id;
        return '';
    }

    _draftVersion(note) {
        const attrs = note && typeof note.attributes === 'object' && note.attributes !== null
            ? note.attributes
            : null;
        const draft = attrs && typeof attrs.ai_analysis_draft === 'object' && attrs.ai_analysis_draft !== null
            ? attrs.ai_analysis_draft
            : null;
        if (draft === null || typeof draft.draft_version !== 'number') {
            return null;
        }
        return draft.draft_version;
    }

    render() {
        if (typeof this.noteId !== 'string' || this.noteId.length === 0) {
            return html`
                <div class="body">
                    <div class="center">
                        <platform-icon class="icon" name="info" size="48"></platform-icon>
                        <h2>${this.t('note_page.no_id_title')}</h2>
                        <p>${this.t('note_page.no_id_message')}</p>
                        <button class="back-btn" type="button" @click=${this._onBackToNotes}>
                            <platform-icon name="arrow-left" size="16"></platform-icon>
                            ${this.t('note_page.back_to_notes')}
                        </button>
                    </div>
                </div>
            `;
        }

        if (this._isDraftId(this.noteId)) {
            return html`
                <div class="breadcrumbs-wrap">
                    <platform-breadcrumbs current-label=${this.t('note_page.draft_breadcrumb')}></platform-breadcrumbs>
                </div>
                <div class="body edit">
                    <crm-note-card-view
                        .note=${null}
                        mode="edit"
                        defaultNamespace=${this._currentNamespace()}
                        @cancel=${this._onEditCancel}
                        @created=${this._onEditCreated}
                    ></crm-note-card-view>
                </div>
            `;
        }

        if (this._cardError) {
            return html`
                <div class="body">
                    <div class="center">
                        <platform-icon class="icon" name="warning" size="48"></platform-icon>
                        <h2>${this.t('note_page.not_found_title')}</h2>
                        <p>${this._cardError}</p>
                        <button class="back-btn" type="button" @click=${this._onBackToNotes}>
                            <platform-icon name="arrow-left" size="16"></platform-icon>
                            ${this.t('note_page.back_to_notes')}
                        </button>
                    </div>
                </div>
            `;
        }

        const note = this._resolveNote();
        const entityLoading = this._entities.loading;

        if (!note || entityLoading) {
            return html`
                <div class="body">
                    <div class="center">
                        <glass-spinner size="lg"></glass-spinner>
                        <p>${this.t('note_page.loading')}</p>
                    </div>
                </div>
            `;
        }

        if (this._mode === 'edit') {
            return html`
                <div class="breadcrumbs-wrap">
                    <platform-breadcrumbs current-label=${this._noteLabel(note)}></platform-breadcrumbs>
                </div>
                <div class="body edit">
                    <crm-note-card-view
                        .note=${note}
                        .card=${this._card}
                        mode="edit"
                        @cancel=${this._onEditCancel}
                        @saved=${this._onEditSaved}
                    ></crm-note-card-view>
                </div>
            `;
        }

        if (!this._card) {
            return html`
                <div class="body">
                    <div class="center">
                        <glass-spinner size="lg"></glass-spinner>
                        <p>${this.t('note_page.loading')}</p>
                    </div>
                </div>
            `;
        }

        const relationshipTypes = Array.isArray(this._relTypes.items) ? this._relTypes.items : [];
        return html`
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
                    mode="view"
                    @entity-open=${this._onEntityOpen}
                    @show-graph=${this._onShowGraph}
                    @delete-note=${this._onDeleteNote}
                    @edit-note=${this._onEditNote}
                    @refresh-summary=${this._onRefreshSummary}
                    @task-add=${this._onTaskAdd}
                    @task-toggle=${this._onTaskToggle}
                    @task-remove=${this._onTaskRemove}
                ></crm-note-card-view>
            </div>
            ${nothing}
        `;
    }
}

customElements.define('crm-note-page', CRMNotePage);
