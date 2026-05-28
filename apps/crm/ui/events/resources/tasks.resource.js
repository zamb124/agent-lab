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
} from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

const CRM_TASK_UPDATED = 'crm/task/updated';

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
    successToastKey: 'crm:toast.task.knowledge_import_started',
    errorToastKey: 'crm:toast.task.knowledge_import_start_failed',
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
});

export const taskDailySummaryStartOp = createAsyncOp({
    name: 'crm/task_daily_summary_start',
    successToastKey: 'crm:toast.task.daily_summary_started',
    errorToastKey: 'crm:toast.task.daily_summary_start_failed',
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
});

export const taskPeriodSummaryStartOp = createAsyncOp({
    name: 'crm/task_period_summary_start',
    successToastKey: 'crm:toast.task.period_summary_started',
    errorToastKey: 'crm:toast.task.period_summary_start_failed',
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
});

export const taskRetryOp = createAsyncOp({
    name: 'crm/task_retry',
    successToastKey: 'crm:toast.task.retried',
    errorToastKey: 'crm:toast.task.retry_failed',
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
});
