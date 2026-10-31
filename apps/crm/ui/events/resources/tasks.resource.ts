/**
 * Tasks — фоновые задачи CRM (knowledge_import, note_analyze, daily_summary,
 * period_summary).
 *
 * В реальном времени: WebSocket ``crm/task/updated`` (payload ``{ task: CRMTask }``)
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
    reloadLastList,
} from '@platform/lib/events/index.js';
import type { EffectCtx, PlatformEvent } from '@platform/lib/events/contract.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';

function anyRecord(value: unknown): Record<string, unknown> | null {
    if (!isPlainRecord(value)) return null;
    const row: Record<string, unknown> = {};
    for (const [key, field] of Object.entries(value)) row[key] = field;
    return row;
}

const CRM_TASK_UPDATED = 'crm/task/updated';

/**
 * Строка `detail` из HTTP-ошибки платформы (не объект `{code, message}`).
 * @param {object} err
 * @returns {string | null}
 */
function _httpErrorDetailText(err: unknown): string | null {
    if (!isPlainRecord(err)) {
        return null;
    }
    const body = err.body;
    if (!isPlainRecord(body)) {
        return null;
    }
    const detail = body.detail;
    if (typeof detail === 'string' && detail.length > 0) {
        return detail;
    }
    return null;
}

/**
 * 409 / `conflict` — задача уже идёт;
 * строковый detail — текст с бэка; иначе generic fail.
 * @param {object} ctx
 * @param {object} err
 * @param {object} event
 * @param {string} alreadyRunningKey
 * @param {string} failedKey
 */
function _toastOnActiveTaskConflict(ctx: EffectCtx, err: unknown, event: PlatformEvent, alreadyRunningKey: string, failedKey: string) {
    const conflict = isPlainRecord(err) && (err.status === 409 || err.code === 'conflict');
    if (conflict) {
        ctx.dispatch(
            CoreEvents.UI_TOAST_SHOW,
            { i18n_key: alreadyRunningKey },
            { causation_id: event.id },
        );
        return;
    }
    const detailText = _httpErrorDetailText(err);
    if (detailText !== null) {
        ctx.dispatch(
            CoreEvents.UI_TOAST_SHOW,
            { message: detailText },
            { causation_id: event.id },
        );
        return;
    }
    ctx.dispatch(
        CoreEvents.UI_TOAST_SHOW,
        { i18n_key: failedKey },
        { causation_id: event.id },
    );
}

/**
 * @param {object} state
 * @param {object} task
 * @param {string} idField
 * @returns {object}
 */
function _mergeTaskIntoCollectionState<S extends { items: readonly any[]; byId: Readonly<Record<string, unknown>> }>(state: S, task: Record<string, unknown>, idField: string): S {
    const id = task[idField];
    const idx = state.items.findIndex((x) => x && x[idField] === id);
    const items = idx === -1 ? [...state.items, task] : state.items.map((x, i) => (i === idx ? task : x));
    const byId = { ...state.byId, [String(id)]: task };
    return {
        ...state,
        items,
        byId,
    };
}

/**
 * TaskResponse → тот же merge, что и WS `crm/task/updated`.
 * @param {object} ctx
 * @param {object} result
 * @param {object} event
 */
function _dispatchLocalTaskUpdated(ctx: EffectCtx, result: unknown, event: PlatformEvent) {
    const task = anyRecord(result);
    const taskId = task === null ? undefined : task.task_id;
    if (typeof taskId !== 'string') {
        throw new Error('crm task mutation success: TaskResponse with task_id required');
    }
    ctx.dispatch(
        CRM_TASK_UPDATED,
        { task },
        { causation_id: event.id, source: 'local' },
    );
}

export const taskGetOp = createAsyncOp({
    name: 'crm/task_get',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/tasks/item_requested',
    restMirror: { method: 'GET', path: '/crm/api/v1/tasks/:task_id' },
});

const ACTIVE_TASK_STATUSES = new Set(['pending', 'running']);

export const tasksResource = createResourceCollection({
    name: 'crm/tasks',
    baseUrl: '/crm/api/v1/tasks',
    idField: 'task_id',
    operations: ['list', 'get'],
    transport: 'ws',
    wsTimeoutMs: 8_000,
    listQuery: (payload) => {
        if (!payload || typeof payload !== 'object') {
            throw new Error('tasksResource.listQuery: payload required (object)');
        }
        const query: Record<string, unknown> = {};
        if ('limit' in payload) {
            if (typeof payload.limit !== 'number') {
                throw new Error('tasksResource.listQuery: payload.limit must be number');
            }
            query.limit = payload.limit;
        }
        if ('offset' in payload) {
            if (typeof payload.offset !== 'number') {
                throw new Error('tasksResource.listQuery: payload.offset must be number');
            }
            query.offset = payload.offset;
        }
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
        const payload = anyRecord(event.payload);
        if (payload === null) {
            throw new Error('crm/tasks extraReducer: push payload required');
        }
        const task = anyRecord(payload.task);
        if (task === null || typeof task.task_id !== 'string') {
            throw new Error('crm/tasks extraReducer: payload.task with task_id required');
        }
        return _mergeTaskIntoCollectionState(state, task, 'task_id');
    },
    // Пока сокет был оборван, push'и по активным задачам потеряны — досинхронизация
    // последнего списка делается здесь, а не в страницах.
    extraEffect: async (event, ctx) => {
        if (event.type !== CoreEvents.WS_CONNECTED) {
            return false;
        }
        const root = anyRecord(ctx.getState());
        const slice = root === null ? null : anyRecord(root[tasksResource.sliceKey]);
        const items = slice !== null && Array.isArray(slice.items) ? slice.items : [];
        const hasActive = items.some((task) => {
            const row = anyRecord(task);
            const status = row === null ? undefined : row.status;
            return typeof status === 'string' && ACTIVE_TASK_STATUSES.has(status);
        });
        if (hasActive) {
            reloadLastList(ctx, tasksResource);
        }
        return false;
    },
});

export const taskCreatedEntitiesOp = createAsyncOp({
    name: 'crm/task_created_entities',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/tasks/created_entities_requested',
    restMirror: { method: 'GET', path: '/crm/api/v1/tasks/:task_id/created-entities' },
});

export const taskKnowledgeImportStartOp = createAsyncOp({
    name: 'crm/task_knowledge_import_start',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/tasks/knowledge_import_start_requested',
    restMirror: { method: 'POST', path: '/crm/api/v1/tasks/knowledge-import' },
    onSuccess: (ctx, _result, event) => {
        ctx.dispatch(
            CoreEvents.UI_TOAST_SHOW,
            { i18n_key: 'crm:toast.task.knowledge_import_started' },
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
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/tasks/daily_summary_start_requested',
    restMirror: { method: 'POST', path: '/crm/api/v1/tasks/daily-summary' },
    onSuccess: (ctx, _result, event) => {
        ctx.dispatch(
            CoreEvents.UI_TOAST_SHOW,
            { i18n_key: 'crm:toast.task.daily_summary_started' },
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
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/tasks/period_summary_start_requested',
    restMirror: { method: 'POST', path: '/crm/api/v1/tasks/period-summary' },
    onSuccess: (ctx, _result, event) => {
        ctx.dispatch(
            CoreEvents.UI_TOAST_SHOW,
            { i18n_key: 'crm:toast.task.period_summary_started' },
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
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/tasks/review_complete_requested',
    restMirror: { method: 'POST', path: '/crm/api/v1/tasks/:task_id/review-complete' },
    onSuccess: _dispatchLocalTaskUpdated,
});

export const taskCancelOp = createAsyncOp({
    name: 'crm/task_cancel',
    successToastKey: 'crm:toast.task.cancelled',
    errorToastKey: 'crm:toast.task.cancel_failed',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/tasks/cancel_requested',
    restMirror: { method: 'POST', path: '/crm/api/v1/tasks/:task_id/cancel' },
    onSuccess: _dispatchLocalTaskUpdated,
});

export const taskRollbackOp = createAsyncOp({
    name: 'crm/task_rollback',
    successToastKey: 'crm:toast.task.rolled_back',
    errorToastKey: 'crm:toast.task.rollback_failed',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/tasks/rollback_requested',
    restMirror: { method: 'POST', path: '/crm/api/v1/tasks/:task_id/rollback' },
    onSuccess: _dispatchLocalTaskUpdated,
});

export const taskRetryOp = createAsyncOp({
    name: 'crm/task_retry',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/tasks/retry_requested',
    restMirror: { method: 'POST', path: '/crm/api/v1/tasks/:task_id/retry' },
    onSuccess: (ctx, result, event) => {
        _dispatchLocalTaskUpdated(ctx, result, event);
        ctx.dispatch(
            CoreEvents.UI_TOAST_SHOW,
            { i18n_key: 'crm:toast.task.retried' },
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

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'crm/task_get': typeof taskGetOp;
        'crm/tasks': typeof tasksResource;
        'crm/task_created_entities': typeof taskCreatedEntitiesOp;
        'crm/task_knowledge_import_start': typeof taskKnowledgeImportStartOp;
        'crm/task_daily_summary_start': typeof taskDailySummaryStartOp;
        'crm/task_period_summary_start': typeof taskPeriodSummaryStartOp;
        'crm/task_review_complete': typeof taskReviewCompleteOp;
        'crm/task_cancel': typeof taskCancelOp;
        'crm/task_rollback': typeof taskRollbackOp;
        'crm/task_retry': typeof taskRetryOp;
    }
}
