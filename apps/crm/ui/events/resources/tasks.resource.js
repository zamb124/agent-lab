/**
 * Tasks — фоновые задачи CRM (knowledge_import, note_analyze, daily_summary,
 * period_summary).
 *
 * В реальном времени: WebSocket ``crm/task/updated`` (payload ``{ task: TaskResponse }``)
 * мержится в slice без поллинга.
 *
 * Бэкенд (`/crm/api/v1/tasks`):
 *   GET  /                                → OffsetPage[TaskResponse]
 *   GET  /{task_id}                       → TaskResponse (`taskGetOp`)
 *   GET  /{task_id}/created-entities      → TaskCreatedEntitiesResponse
 *   POST /knowledge-import                → TaskResponse (start)
 *   POST /note-analyze                    → TaskResponse (start)
 *   POST /daily-summary                   → TaskResponse (start)
 *   POST /period-summary                  → TaskResponse (start)
 *   POST /{task_id}/review-complete       → TaskResponse
 *   POST /{task_id}/cancel                → TaskResponse
 *   POST /{task_id}/rollback              → TaskResponse
 *   POST /{task_id}/retry                 → TaskResponse
 */

import {
    createResourceCollection,
    createAsyncOp,
    CoreEvents,
} from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

const CRM_TASK_UPDATED = 'crm/task/updated';

/**
 * Строка `detail` из HTTP-ошибки платформы (не объект `{code, message}`).
 * @param {object} err
 * @returns {string | null}
 */
function _httpErrorDetailText(err) {
    if (!err || typeof err !== 'object') {
        return null;
    }
    const body = err.body;
    if (!body || typeof body !== 'object') {
        return null;
    }
    const detail = body.detail;
    if (typeof detail === 'string' && detail.length > 0) {
        return detail;
    }
    return null;
}

/**
 * 409 active_task_exists — задача уже идёт;
 * строковый detail — текст с бэка; иначе generic fail.
 * @param {object} ctx
 * @param {object} err
 * @param {object} event
 * @param {string} alreadyRunningKey
 * @param {string} failedKey
 */
function _toastOnActiveTaskConflict(ctx, err, event, alreadyRunningKey, failedKey) {
    const code = err && err.body && err.body.detail && err.body.detail.code;
    if (err && err.status === 409 && code === 'active_task_exists') {
        ctx.dispatch(
            CoreEvents.UI_TOAST_SHOW,
            { type: 'warning', i18n_key: alreadyRunningKey },
            { causation_id: event.id },
        );
        return;
    }
    const detailText = _httpErrorDetailText(err);
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

/**
 * @param {object} state
 * @param {object} task
 * @param {string} idField
 * @returns {object}
 */
function _mergeTaskIntoCollectionState(state, task, idField) {
    const id = task[idField];
    const idx = state.items.findIndex((x) => x && x[idField] === id);
    const items = idx === -1 ? [...state.items, task] : state.items.map((x, i) => (i === idx ? task : x));
    const byId = { ...state.byId, [id]: task };
    return {
        ...state,
        items,
        byId,
    };
}

/**
 * HTTP TaskResponse → тот же merge, что и WS `crm/task/updated`.
 * @param {object} ctx
 * @param {object} result
 * @param {object} event
 */
function _dispatchLocalTaskUpdated(ctx, result, event) {
    if (!result || typeof result !== 'object' || typeof result.task_id !== 'string') {
        throw new Error('crm task mutation success: TaskResponse with task_id required');
    }
    ctx.dispatch(
        CRM_TASK_UPDATED,
        { task: result },
        { causation_id: event.id, source: 'local' },
    );
}

export const taskGetOp = createAsyncOp({
    name: 'crm/task_get',
    silent: true,
    restMirror: { method: 'GET', path: '/crm/api/v1/tasks/:task_id' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.task_id !== 'string') {
            throw new Error('taskGetOp: payload.task_id required');
        }
        return await httpRequest({
            method: 'GET',
            url: `/crm/api/v1/tasks/${encodeURIComponent(payload.task_id)}`,
        });
    },
});

export const tasksResource = createResourceCollection({
    name: 'crm/tasks',
    baseUrl: '/crm/api/v1/tasks',
    idField: 'task_id',
    operations: ['list', 'get'],
    listQuery: (payload) => {
        if (!payload || typeof payload !== 'object') {
            throw new Error('tasksResource.listQuery: payload required (object)');
        }
        const limit = typeof payload.limit === 'number' ? payload.limit : 50;
        const offset = typeof payload.offset === 'number' ? payload.offset : 0;
        const query = { limit, offset };
        if (typeof payload.namespace === 'string' && payload.namespace.length > 0) {
            query.namespace = payload.namespace;
        }
        if (typeof payload.task_type === 'string' && payload.task_type.length > 0) {
            query.task_type = payload.task_type;
        }
        if (typeof payload.note_id === 'string' && payload.note_id.length > 0) {
            query.note_id = payload.note_id;
        }
        return query;
    },
    extraReducer: (state, event) => {
        if (event.type !== CRM_TASK_UPDATED) {
            return state;
        }
        const payload = event.payload;
        if (!payload || typeof payload !== 'object') {
            return state;
        }
        const task = payload.task;
        if (!task || typeof task !== 'object' || typeof task.task_id !== 'string') {
            return state;
        }
        return _mergeTaskIntoCollectionState(state, task, 'task_id');
    },
});

export const taskCreatedEntitiesOp = createAsyncOp({
    name: 'crm/task_created_entities',
    silent: true,
    restMirror: { method: 'GET', path: '/crm/api/v1/tasks/:task_id/created-entities' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.task_id !== 'string') {
            throw new Error('taskCreatedEntitiesOp: payload.task_id required');
        }
        return await httpRequest({
            method: 'GET',
            url: `/crm/api/v1/tasks/${encodeURIComponent(payload.task_id)}/created-entities`,
        });
    },
});

export const taskKnowledgeImportStartOp = createAsyncOp({
    name: 'crm/task_knowledge_import_start',
    silent: true,
    restMirror: { method: 'POST', path: '/crm/api/v1/tasks/knowledge-import' },
    request: async ({ payload }) => {
        if (!payload || typeof payload !== 'object') {
            throw new Error('taskKnowledgeImportStartOp: payload required');
        }
        return await httpRequest({
            method: 'POST',
            url: '/crm/api/v1/tasks/knowledge-import',
            body: payload,
        });
    },
    onSuccess: (ctx, _result, event) => {
        ctx.dispatch(
            CoreEvents.UI_TOAST_SHOW,
            { type: 'success', i18n_key: 'crm:toast.task.knowledge_import_started' },
            { causation_id: event.id },
        );
    },
    onFailure: (ctx, err, event) => {
        _toastOnActiveTaskConflict(
            ctx,
            err,
            event,
            'crm:toast.task.knowledge_import_already_running',
            'crm:toast.task.knowledge_import_start_failed',
        );
    },
});

export const taskDailySummaryStartOp = createAsyncOp({
    name: 'crm/task_daily_summary_start',
    silent: true,
    restMirror: { method: 'POST', path: '/crm/api/v1/tasks/daily-summary' },
    request: async ({ payload }) => {
        if (!payload || typeof payload !== 'object') {
            throw new Error('taskDailySummaryStartOp: payload required');
        }
        return await httpRequest({
            method: 'POST',
            url: '/crm/api/v1/tasks/daily-summary',
            body: payload,
        });
    },
    onSuccess: (ctx, _result, event) => {
        ctx.dispatch(
            CoreEvents.UI_TOAST_SHOW,
            { type: 'success', i18n_key: 'crm:toast.task.daily_summary_started' },
            { causation_id: event.id },
        );
    },
    onFailure: (ctx, err, event) => {
        _toastOnActiveTaskConflict(
            ctx,
            err,
            event,
            'crm:toast.task.daily_summary_already_running',
            'crm:toast.task.daily_summary_start_failed',
        );
    },
});

export const taskPeriodSummaryStartOp = createAsyncOp({
    name: 'crm/task_period_summary_start',
    silent: true,
    restMirror: { method: 'POST', path: '/crm/api/v1/tasks/period-summary' },
    request: async ({ payload }) => {
        if (!payload || typeof payload !== 'object') {
            throw new Error('taskPeriodSummaryStartOp: payload required');
        }
        return await httpRequest({
            method: 'POST',
            url: '/crm/api/v1/tasks/period-summary',
            body: payload,
        });
    },
    onSuccess: (ctx, _result, event) => {
        ctx.dispatch(
            CoreEvents.UI_TOAST_SHOW,
            { type: 'success', i18n_key: 'crm:toast.task.period_summary_started' },
            { causation_id: event.id },
        );
    },
    onFailure: (ctx, err, event) => {
        _toastOnActiveTaskConflict(
            ctx,
            err,
            event,
            'crm:toast.task.period_summary_already_running',
            'crm:toast.task.period_summary_start_failed',
        );
    },
});

export const taskReviewCompleteOp = createAsyncOp({
    name: 'crm/task_review_complete',
    successToastKey: 'crm:toast.task.review_completed',
    errorToastKey: 'crm:toast.task.review_complete_failed',
    restMirror: { method: 'POST', path: '/crm/api/v1/tasks/:task_id/review-complete' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.task_id !== 'string') {
            throw new Error('taskReviewCompleteOp: payload.task_id required');
        }
        return await httpRequest({
            method: 'POST',
            url: `/crm/api/v1/tasks/${encodeURIComponent(payload.task_id)}/review-complete`,
        });
    },
    onSuccess: _dispatchLocalTaskUpdated,
});

export const taskCancelOp = createAsyncOp({
    name: 'crm/task_cancel',
    successToastKey: 'crm:toast.task.cancelled',
    errorToastKey: 'crm:toast.task.cancel_failed',
    restMirror: { method: 'POST', path: '/crm/api/v1/tasks/:task_id/cancel' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.task_id !== 'string') {
            throw new Error('taskCancelOp: payload.task_id required');
        }
        return await httpRequest({
            method: 'POST',
            url: `/crm/api/v1/tasks/${encodeURIComponent(payload.task_id)}/cancel`,
        });
    },
    onSuccess: _dispatchLocalTaskUpdated,
});

export const taskRollbackOp = createAsyncOp({
    name: 'crm/task_rollback',
    successToastKey: 'crm:toast.task.rolled_back',
    errorToastKey: 'crm:toast.task.rollback_failed',
    restMirror: { method: 'POST', path: '/crm/api/v1/tasks/:task_id/rollback' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.task_id !== 'string') {
            throw new Error('taskRollbackOp: payload.task_id required');
        }
        return await httpRequest({
            method: 'POST',
            url: `/crm/api/v1/tasks/${encodeURIComponent(payload.task_id)}/rollback`,
        });
    },
    onSuccess: _dispatchLocalTaskUpdated,
});

export const taskRetryOp = createAsyncOp({
    name: 'crm/task_retry',
    silent: true,
    restMirror: { method: 'POST', path: '/crm/api/v1/tasks/:task_id/retry' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.task_id !== 'string') {
            throw new Error('taskRetryOp: payload.task_id required');
        }
        return await httpRequest({
            method: 'POST',
            url: `/crm/api/v1/tasks/${encodeURIComponent(payload.task_id)}/retry`,
        });
    },
    onSuccess: (ctx, result, event) => {
        _dispatchLocalTaskUpdated(ctx, result, event);
        ctx.dispatch(
            CoreEvents.UI_TOAST_SHOW,
            { type: 'success', i18n_key: 'crm:toast.task.retried' },
            { causation_id: event.id },
        );
    },
    onFailure: (ctx, err, event) => {
        _toastOnActiveTaskConflict(
            ctx,
            err,
            event,
            'crm:toast.task.retry_already_running',
            'crm:toast.task.retry_failed',
        );
    },
});
