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
 *   POST  /crm/api/v1/entities/notes/{note_id}/analysis-draft-repair → 202 TaskIQ (AI-починка черновика)
 *   POST  /crm/api/v1/tasks/note-analyze                       → TaskResponse (start_note_analyze)
 *   GET   /crm/api/v1/entities/search?q=&entity_type=note&search_mode= → CursorPage[Entity]
 *   POST  /crm/api/v1/entities/cards/bulk                      → { [entity_id]: card }
 */

import {
    createCursorList,
    createAsyncOp,
    CoreEvents,
} from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

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
    restMirror: { method: 'POST', path: '/crm/api/v1/entities/query' },
    request: async ({ payload }) => {
        const body = {
            entity_type: 'note',
            limit: 50,
        };
        if (payload && typeof payload.namespace === 'string' && payload.namespace.length > 0) {
            body.namespace = payload.namespace;
        }
        if (payload && typeof payload.entity_subtype === 'string' && payload.entity_subtype.length > 0) {
            body.entity_subtype = payload.entity_subtype;
        }
        return await httpRequest({
            method: 'POST',
            url: '/crm/api/v1/entities/query',
            body,
        });
    },
});

/** PATCH body: expected_version, remove_*, patch_entities, patch_relationships?, add_entities?, add_relationships?. */
export const noteAnalysisDraftSaveOp = createAsyncOp({
    name: 'crm/note_analysis_draft_save',
    silent: true,
    restMirror: { method: 'PATCH', path: '/crm/api/v1/entities/notes/:note_id/analysis-draft' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.note_id !== 'string' || !payload.draft) {
            throw new Error('noteAnalysisDraftSaveOp: { note_id, draft } required');
        }
        return await httpRequest({
            method: 'PATCH',
            url: `/crm/api/v1/entities/notes/${encodeURIComponent(payload.note_id)}/analysis-draft`,
            body: payload.draft,
        });
    },
});

export const noteAnalysisDraftDiscardOp = createAsyncOp({
    name: 'crm/note_analysis_draft_discard',
    silent: true,
    restMirror: {
        method: 'DELETE',
        path: '/crm/api/v1/entities/notes/:note_id/analysis-draft',
    },
    request: async ({ payload }) => {
        if (!payload || typeof payload.note_id !== 'string') {
            throw new Error('noteAnalysisDraftDiscardOp: note_id required');
        }
        return await httpRequest({
            method: 'DELETE',
            url: `/crm/api/v1/entities/notes/${encodeURIComponent(payload.note_id)}/analysis-draft`,
        });
    },
});

export const noteAnalysisErrorDismissOp = createAsyncOp({
    name: 'crm/note_analysis_error_dismiss',
    silent: true,
    restMirror: {
        method: 'DELETE',
        path: '/crm/api/v1/entities/notes/:note_id/analysis-error',
    },
    request: async ({ payload }) => {
        if (!payload || typeof payload.note_id !== 'string') {
            throw new Error('noteAnalysisErrorDismissOp: note_id required');
        }
        return await httpRequest({
            method: 'DELETE',
            url: `/crm/api/v1/entities/notes/${encodeURIComponent(payload.note_id)}/analysis-error`,
        });
    },
});

export const noteAnalysisDraftRepairOp = createAsyncOp({
    name: 'crm/note_analysis_draft_repair',
    silent: true,
    restMirror: {
        method: 'POST',
        path: '/crm/api/v1/entities/notes/:note_id/analysis-draft-repair',
    },
    request: async ({ payload }) => {
        if (!payload || typeof payload.note_id !== 'string') {
            throw new Error('noteAnalysisDraftRepairOp: note_id required');
        }
        return await httpRequest({
            method: 'POST',
            url: `/crm/api/v1/entities/notes/${encodeURIComponent(payload.note_id)}/analysis-draft-repair`,
            body: {},
        });
    },
    onSuccess: (ctx, _result, event) => {
        ctx.dispatch(
            CoreEvents.UI_TOAST_SHOW,
            { type: 'success', i18n_key: 'crm:toast.note.draft_repair_queued' },
            { causation_id: event.id },
        );
    },
    onFailure: (ctx, err, event) => {
        const code = err && err.body && err.body.detail && err.body.detail.code;
        if (err && err.status === 409 && code === 'active_task_exists') {
            ctx.dispatch(
                CoreEvents.UI_TOAST_SHOW,
                { type: 'warning', i18n_key: 'crm:toast.note.draft_repair_already_running' },
                { causation_id: event.id },
            );
            return;
        }
        ctx.dispatch(
            CoreEvents.UI_TOAST_SHOW,
            { type: 'error', i18n_key: 'crm:toast.note.draft_repair_queue_failed' },
            { causation_id: event.id },
        );
    },
});

export const noteSearchOp = createAsyncOp({
    name: 'crm/note_search',
    silent: true,
    restMirror: { method: 'POST', path: '/crm/api/v1/entities/query' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.q !== 'string' || payload.q.length === 0) {
            throw new Error('noteSearchOp: payload.q (non-empty string) required');
        }
        const search_mode = typeof payload.search_mode === 'string' && payload.search_mode.length > 0
            ? payload.search_mode
            : 'hybrid';
        const limit = typeof payload.limit === 'number' && payload.limit > 0 ? payload.limit : 50;
        const body = {
            query: payload.q,
            entity_type: 'note',
            search_mode,
            limit,
        };
        if (typeof payload.namespace === 'string' && payload.namespace.length > 0) {
            body.namespace = payload.namespace;
        }
        return await httpRequest({
            method: 'POST',
            url: '/crm/api/v1/entities/query',
            body,
        });
    },
});

export const entityCardsBulkOp = createAsyncOp({
    name: 'crm/entity_cards_bulk',
    silent: true,
    restMirror: { method: 'POST', path: '/crm/api/v1/entities/cards/bulk' },
    request: async ({ payload }) => {
        if (!payload || !Array.isArray(payload.entity_ids) || payload.entity_ids.length === 0) {
            throw new Error('entityCardsBulkOp: payload.entity_ids (non-empty array) required');
        }
        return await httpRequest({
            method: 'POST',
            url: '/crm/api/v1/entities/cards/bulk',
            body: { entity_ids: payload.entity_ids },
        });
    },
});

export const noteAnalyzeStartOp = createAsyncOp({
    name: 'crm/note_analyze_start',
    silent: true,
    restMirror: { method: 'POST', path: '/crm/api/v1/tasks/note-analyze' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.note_id !== 'string') {
            throw new Error('noteAnalyzeStartOp: payload.note_id required');
        }
        const body = { note_id: payload.note_id };
        if (typeof payload.mode === 'string' && payload.mode.length > 0) {
            body.mode = payload.mode;
        }
        return await httpRequest({
            method: 'POST',
            url: '/crm/api/v1/tasks/note-analyze',
            body,
        });
    },
    onSuccess: (ctx, result, event) => {
        if (result && typeof result === 'object' && typeof result.task_id === 'string') {
            ctx.dispatch(
                'crm/task/updated',
                { task: result },
                { causation_id: event.id, source: 'http' },
            );
        }
        ctx.dispatch(
            CoreEvents.UI_TOAST_SHOW,
            { type: 'success', i18n_key: 'crm:toast.note.analyze_started' },
            { causation_id: event.id },
        );
    },
    onFailure: (ctx, err, event) => {
        const code = err && err.body && err.body.detail && err.body.detail.code;
        if (err && err.status === 409 && code === 'active_task_exists') {
            ctx.dispatch(
                CoreEvents.UI_TOAST_SHOW,
                { type: 'warning', i18n_key: 'crm:toast.note.analyze_already_running' },
                { causation_id: event.id },
            );
            return;
        }
        ctx.dispatch(
            CoreEvents.UI_TOAST_SHOW,
            { type: 'error', i18n_key: 'crm:toast.note.analyze_start_failed' },
            { causation_id: event.id },
        );
    },
});

export const noteMarkdownFormatOp = createAsyncOp({
    name: 'crm/note_markdown_format',
    silent: true,
    restMirror: { method: 'POST', path: '/crm/api/v1/entities/notes/:note_id/format-markdown' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.note_id !== 'string' || payload.note_id.length === 0) {
            throw new Error('noteMarkdownFormatOp: payload.note_id required');
        }
        return await httpRequest({
            method: 'POST',
            url: `/crm/api/v1/entities/notes/${encodeURIComponent(payload.note_id)}/format-markdown`,
        });
    },
    onSuccess: (ctx, _result, event) => {
        ctx.dispatch(
            CoreEvents.UI_TOAST_SHOW,
            { type: 'info', i18n_key: 'crm:toast.note.markdown_format_started' },
            { causation_id: event.id },
        );
    },
    onFailure: (ctx, _err, event) => {
        ctx.dispatch(
            CoreEvents.UI_TOAST_SHOW,
            { type: 'error', i18n_key: 'crm:toast.note.markdown_format_failed' },
            { causation_id: event.id },
        );
    },
});
