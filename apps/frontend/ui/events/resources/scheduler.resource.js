/**
 * Scheduler resources — расписания платформенного scheduler (cron / interval / one-time)
 * через прокси `/frontend/api/scheduler/*`.
 *
 * Состав:
 *   - schedulerTasksResource: createResourceCollection (list, create) — основная коллекция
 *     с фильтром через listQuery.
 *   - schedulerPauseOp / schedulerResumeOp / schedulerCancelOp: createAsyncOp, silent,
 *     по успеху перезагружают список (onSuccess).
 *   - schedulerRunNowOp: createAsyncOp, silent, по успеху эмитит toast и перезагружает.
 *   - schedulerRedisOp: createAsyncOp, silent, держит snapshot Redis по task_id в slice
 *     (`snapshotById`) — UI показывает inline под строкой задачи без модалки.
 *
 * task.id — основной идентификатор (поле `id`, не `task_id`).
 */

import {
    createResourceCollection,
    createAsyncOp,
} from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';
import { CoreEvents } from '@platform/lib/events/contract.js';

const BASE = '/frontend/api/scheduler/schedules';

export const schedulerTasksResource = createResourceCollection({
    name: 'frontend/scheduler_tasks',
    baseUrl: BASE,
    idField: 'id',
    operations: ['list', 'create'],
    toastKeys: {
        create: 'frontend:scheduler_modal.toast_created',
    },
    listQuery: (payload) => {
        const q = { limit: 200 };
        if (payload && payload.status) q.status = payload.status;
        if (payload && payload.target_service) q.target_service = payload.target_service;
        if (payload && payload.task_name) q.task_name = payload.task_name;
        return q;
    },
});

function _reloadList(ctx) {
    ctx.dispatch(schedulerTasksResource.events.LIST_REQUESTED, null, { source: 'local' });
}

export const schedulerPauseOp = createAsyncOp({
    name: 'frontend/scheduler_pause',
    silent: true,
    request: async ({ payload }) => {
        const id = payload && payload.task_id;
        if (!id) throw new Error('schedulerPauseOp: task_id required');
        return await httpRequest({
            method: 'POST',
            url: `${BASE}/${encodeURIComponent(id)}/pause`,
        });
    },
    onSuccess: (ctx) => _reloadList(ctx),
});

export const schedulerResumeOp = createAsyncOp({
    name: 'frontend/scheduler_resume',
    silent: true,
    request: async ({ payload }) => {
        const id = payload && payload.task_id;
        if (!id) throw new Error('schedulerResumeOp: task_id required');
        return await httpRequest({
            method: 'POST',
            url: `${BASE}/${encodeURIComponent(id)}/resume`,
        });
    },
    onSuccess: (ctx) => _reloadList(ctx),
});

export const schedulerCancelOp = createAsyncOp({
    name: 'frontend/scheduler_cancel',
    silent: true,
    request: async ({ payload }) => {
        const id = payload && payload.task_id;
        if (!id) throw new Error('schedulerCancelOp: task_id required');
        return await httpRequest({
            method: 'POST',
            url: `${BASE}/${encodeURIComponent(id)}/cancel`,
        });
    },
    onSuccess: (ctx) => _reloadList(ctx),
});

export const schedulerRunNowOp = createAsyncOp({
    name: 'frontend/scheduler_run_now',
    silent: true,
    request: async ({ payload }) => {
        const id = payload && payload.task_id;
        if (!id) throw new Error('schedulerRunNowOp: task_id required');
        return await httpRequest({
            method: 'POST',
            url: `${BASE}/${encodeURIComponent(id)}/run-now`,
        });
    },
    onSuccess: (ctx) => {
        ctx.dispatch(
            CoreEvents.UI_TOAST_SHOW,
            { type: 'success', i18n_key: 'frontend:scheduler_page.toast_run_queued' },
            { source: 'local' },
        );
        _reloadList(ctx);
    },
});

export const schedulerRedisOp = createAsyncOp({
    name: 'frontend/scheduler_redis',
    silent: true,
    request: async ({ payload }) => {
        const id = payload && payload.task_id;
        if (!id) throw new Error('schedulerRedisOp: task_id required');
        const snapshot = await httpRequest({
            method: 'GET',
            url: `${BASE}/${encodeURIComponent(id)}/redis`,
        });
        return { task_id: id, snapshot };
    },
    extraInitial: { snapshotById: {}, loadingById: {} },
    extraReducer: (state, event, events) => {
        if (event.type === events.REQUESTED) {
            const id = event.payload && event.payload.task_id;
            if (!id) return state;
            return { ...state, loadingById: { ...state.loadingById, [id]: true } };
        }
        if (event.type === events.SUCCEEDED) {
            const r = event.payload && event.payload.result;
            if (!r || !r.task_id) return state;
            const nextLoading = { ...state.loadingById };
            delete nextLoading[r.task_id];
            return {
                ...state,
                snapshotById: { ...state.snapshotById, [r.task_id]: r.snapshot },
                loadingById: nextLoading,
            };
        }
        if (event.type === events.FAILED) {
            return { ...state, loadingById: {} };
        }
        return state;
    },
});
