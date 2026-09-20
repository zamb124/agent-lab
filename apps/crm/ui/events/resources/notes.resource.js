/**
 * Notes — заметки CRM. В БД канонически `entity_type === 'note'`, подтип —
 * `entity_subtype` (type_id из ветки note: meeting, call, …). При создании через API
 * с `entity_type` = листовой type_id из этой ветки сервис нормализует в note+subtype.
 * Лента (`entity_type: 'note'` в query) подхватывает и старые строки, где в колонке
 * `entity_type` ошибочно лежал только листовой type_id.
 *
 * Бэкенд:
 *   PATCH /crm/api/v1/entities/notes/{note_id}/analysis-draft → AIAnalysisDraftStored
 *   DELETE /crm/api/v1/entities/notes/{note_id}/analysis-draft → сброс черновика
 *   DELETE /crm/api/v1/entities/notes/{note_id}/analysis-error → сброс только ошибки apply
 *   POST  /crm/api/v1/entities/notes/{note_id}/analysis-draft-repair → 202 TaskIQ
 *   POST  /crm/api/v1/tasks/note-analyze                       → TaskResponse
 *   POST  /crm/api/v1/entities/query                           → CursorPage[Entity]
 *   POST  /crm/api/v1/entities/cards/bulk                      → { [entity_id]: card }
 *
 * `crm/notes_list` остаётся HTTP: createCursorList шлёт UI-filters,
 * а команда `crm/entities/query_requested` принимает EntitySearchQueryRequest.
 * `noteSearchOp` / `noteLatestRangeOp` — те же имена фабрик (causation_id в daily-notes),
 * commandType = `crm/entities/query_requested`, payload = EntitySearchQueryRequest.
 */

import {
    createCursorList,
    createAsyncOp,
    CoreEvents,
} from '@platform/lib/events/index.js';

/**
 * 409 / conflict — задача уже идёт;
 * строковый detail или message — текст с бэка; иначе generic fail.
 * @param {object} ctx
 * @param {object} err
 * @param {object} event
 * @param {string} alreadyRunningKey
 * @param {string} failedKey
 */
function _toastOnActiveTaskConflict(ctx, err, event, alreadyRunningKey, failedKey) {
    const conflict = (err && err.status === 409) || (err && err.code === 'conflict');
    if (conflict) {
        ctx.dispatch(
            CoreEvents.UI_TOAST_SHOW,
            { type: 'warning', i18n_key: alreadyRunningKey },
            { causation_id: event.id },
        );
        return;
    }
    const body = err && err.body;
    const detail = body && typeof body === 'object' ? body.detail : null;
    const detailText = typeof detail === 'string' && detail.length > 0
        ? detail
        : (typeof err.message === 'string' && err.message.length > 0 ? err.message : null);
    if (detailText !== null) {
        ctx.dispatch(
            CoreEvents.UI_TOAST_SHOW,
            { type: 'error', message: detailText },
            { causation_id: event.id },
        );
        return;
    }
    ctx.dispatch(
        CoreEvents.UI_TOAST_SHOW,
        { type: 'error', i18n_key: failedKey },
        { causation_id: event.id },
    );
}

function _buildNoteDateFilter(filters) {
    const leaves = [];
    if (typeof filters.date_from === 'string' && filters.date_from.length > 0) {
        leaves.push({ field: 'note_date', op: '$gte', value: filters.date_from });
    }
    if (typeof filters.date_to === 'string' && filters.date_to.length > 0) {
        leaves.push({ field: 'note_date', op: '$lte', value: filters.date_to });
    }
    if (leaves.length === 0) return null;
    if (leaves.length === 1) return leaves[0];
    return { $and: leaves };
}

/**
 * @param {object} note
 * @param {object} filters
 * @returns {boolean}
 */
function _noteMatchesListFilters(note, filters) {
    if (!filters || typeof filters !== 'object') {
        return true;
    }
    if (typeof filters.namespace === 'string' && filters.namespace.length > 0) {
        if (note.namespace !== filters.namespace) {
            return false;
        }
    }
    if (typeof filters.entity_subtype === 'string' && filters.entity_subtype.length > 0) {
        if (note.entity_subtype !== filters.entity_subtype) {
            return false;
        }
    }
    if (typeof filters.q === 'string' && filters.q.length > 0) {
        return true;
    }
    const noteDate = typeof note.note_date === 'string' ? note.note_date : null;
    if (typeof filters.date_from === 'string' && filters.date_from.length > 0) {
        if (noteDate === null || noteDate < filters.date_from) {
            return false;
        }
    }
    if (typeof filters.date_to === 'string' && filters.date_to.length > 0) {
        if (noteDate === null || noteDate > filters.date_to) {
            return false;
        }
    }
    return true;
}

export const notesListResource = createCursorList({
    name: 'crm/notes_list',
    baseUrl: '/crm/api/v1/entities/query',
    pageSize: 50,
    httpMethod: 'POST',
    restMirror: { method: 'POST', path: '/crm/api/v1/entities/query' },
    buildQuery: (filters) => {
        if (!filters || typeof filters !== 'object') {
            throw new Error('notesListResource.buildQuery: filters required');
        }
        const body = { entity_type: 'note' };
        if (typeof filters.namespace === 'string' && filters.namespace.length > 0) {
            body.namespace = filters.namespace;
        }
        if (typeof filters.entity_subtype === 'string' && filters.entity_subtype.length > 0) {
            body.entity_subtype = filters.entity_subtype;
        }
        if (typeof filters.q === 'string' && filters.q.length > 0) {
            body.query = filters.q;
        }
        const dsl = _buildNoteDateFilter(filters);
        if (dsl !== null) body.filters = dsl;
        return body;
    },
    errorToastKey: 'crm:toast.notes_list.failed',
    extraReducer: (state, event) => {
        if (event.type !== 'crm/note/updated') {
            return state;
        }
        const payload = event.payload;
        if (!payload || typeof payload !== 'object') {
            return state;
        }
        const mf = payload.markdown_format;
        if (mf && (mf.phase === 'partial' || mf.phase === 'started')) {
            return state;
        }
        const noteId = payload.note_id;
        if (typeof noteId !== 'string' || noteId.length === 0) {
            return state;
        }
        const filters = state.filters && typeof state.filters === 'object' ? state.filters : {};
        const items = Array.isArray(state.items) ? state.items : [];

        if (payload.action === 'deleted') {
            const nextItems = items.filter((item) => item && item.entity_id !== noteId);
            if (nextItems.length === items.length) {
                return state;
            }
            return { ...state, items: nextItems };
        }

        const note = payload.note;
        if (!note || typeof note !== 'object' || typeof note.entity_id !== 'string') {
            return state;
        }
        if (!_noteMatchesListFilters(note, filters)) {
            const nextItems = items.filter((item) => item && item.entity_id !== noteId);
            if (nextItems.length === items.length) {
                return state;
            }
            return { ...state, items: nextItems };
        }
        const idx = items.findIndex((item) => item && item.entity_id === noteId);
        if (idx === -1) {
            return { ...state, items: [note, ...items] };
        }
        const nextItems = items.map((item, i) => (i === idx ? note : item));
        return { ...state, items: nextItems };
    },
});

export const noteLatestRangeOp = createAsyncOp({
    name: 'crm/note_latest_range',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/entities/query_requested',
    restMirror: { method: 'POST', path: '/crm/api/v1/entities/query' },
});

/** PATCH body: note_id + expected_version, remove_*, patch_entities, patch_relationships?, add_entities?, add_relationships?. */
export const noteAnalysisDraftSaveOp = createAsyncOp({
    name: 'crm/note_analysis_draft_save',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/notes/analysis_draft_save_requested',
    restMirror: { method: 'PATCH', path: '/crm/api/v1/entities/notes/:note_id/analysis-draft' },
});

export const noteAnalysisDraftDiscardOp = createAsyncOp({
    name: 'crm/note_analysis_draft_discard',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/notes/analysis_draft_discard_requested',
    restMirror: {
        method: 'DELETE',
        path: '/crm/api/v1/entities/notes/:note_id/analysis-draft',
    },
});

export const noteAnalysisErrorDismissOp = createAsyncOp({
    name: 'crm/note_analysis_error_dismiss',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/notes/analysis_error_dismiss_requested',
    restMirror: {
        method: 'DELETE',
        path: '/crm/api/v1/entities/notes/:note_id/analysis-error',
    },
});

export const noteAnalysisDraftRepairOp = createAsyncOp({
    name: 'crm/note_analysis_draft_repair',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/notes/analysis_draft_repair_requested',
    restMirror: {
        method: 'POST',
        path: '/crm/api/v1/entities/notes/:note_id/analysis-draft-repair',
    },
    onSuccess: (ctx, _result, event) => {
        ctx.dispatch(
            CoreEvents.UI_TOAST_SHOW,
            { type: 'success', i18n_key: 'crm:toast.note.draft_repair_queued' },
            { causation_id: event.id },
        );
    },
    onFailure: (ctx, err, event) => {
        _toastOnActiveTaskConflict(
            ctx,
            err,
            event,
            'crm:toast.note.draft_repair_already_running',
            'crm:toast.note.draft_repair_queue_failed',
        );
    },
});

export const noteSearchOp = createAsyncOp({
    name: 'crm/note_search',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/entities/query_requested',
    restMirror: { method: 'POST', path: '/crm/api/v1/entities/query' },
});

export const entityCardsBulkOp = createAsyncOp({
    name: 'crm/entity_cards_bulk',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/entities/cards_bulk_requested',
    restMirror: { method: 'POST', path: '/crm/api/v1/entities/cards/bulk' },
});

export const noteAnalyzeStartOp = createAsyncOp({
    name: 'crm/note_analyze_start',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/notes/analyze_requested',
    restMirror: { method: 'POST', path: '/crm/api/v1/tasks/note-analyze' },
    onSuccess: (ctx, result, event) => {
        if (result && typeof result === 'object' && typeof result.task_id === 'string') {
            ctx.dispatch(
                'crm/task/updated',
                { task: result },
                { causation_id: event.id },
            );
        }
        ctx.dispatch(
            CoreEvents.UI_TOAST_SHOW,
            { type: 'success', i18n_key: 'crm:toast.note.analyze_started' },
            { causation_id: event.id },
        );
    },
    onFailure: (ctx, err, event) => {
        _toastOnActiveTaskConflict(
            ctx,
            err,
            event,
            'crm:toast.note.analyze_already_running',
            'crm:toast.note.analyze_start_failed',
        );
    },
});

export const noteMarkdownFormatOp = createAsyncOp({
    name: 'crm/note_markdown_format',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/notes/markdown_format_requested',
    restMirror: { method: 'POST', path: '/crm/api/v1/entities/notes/:note_id/format-markdown' },
    onSuccess: (ctx, _result, event) => {
        ctx.dispatch(
            CoreEvents.UI_TOAST_SHOW,
            { type: 'info', i18n_key: 'crm:toast.note.markdown_format_started' },
            { causation_id: event.id },
        );
    },
    onFailure: (ctx, err, event) => {
        _toastOnActiveTaskConflict(
            ctx,
            err,
            event,
            'crm:toast.note.markdown_format_already_running',
            'crm:toast.note.markdown_format_failed',
        );
    },
});
