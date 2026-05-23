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
 *   - schedulerRedisOp: createAsyncOp, silent, держит snapshot Redis по schedule_task_id в slice
 *     (`snapshotByScheduleTaskId`) — UI показывает inline под строкой задачи без модалки.
 *
 * schedule_task_id — основной идентификатор записи платформенного scheduler.
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
    baseUrl: '/frontend/api/scheduler/schedules',
    idField: 'schedule_task_id',
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
    restMirror: { method: 'POST', path: '/frontend/api/scheduler/schedules/:schedule_task_id/pause' },
    request: async ({ payload }) => {
        const scheduleTaskId = payload && payload.schedule_task_id;
        if (!scheduleTaskId) throw new Error('schedulerPauseOp: schedule_task_id required');
        return await httpRequest({
            method: 'POST',
            url: `${BASE}/${encodeURIComponent(scheduleTaskId)}/pause`,
        });
    },
    onSuccess: (ctx) => _reloadList(ctx),
});

export const schedulerResumeOp = createAsyncOp({
    name: 'frontend/scheduler_resume',
    silent: true,
    restMirror: { method: 'POST', path: '/frontend/api/scheduler/schedules/:schedule_task_id/resume' },
    request: async ({ payload }) => {
        const scheduleTaskId = payload && payload.schedule_task_id;
        if (!scheduleTaskId) throw new Error('schedulerResumeOp: schedule_task_id required');
        return await httpRequest({
            method: 'POST',
            url: `${BASE}/${encodeURIComponent(scheduleTaskId)}/resume`,
        });
    },
    onSuccess: (ctx) => _reloadList(ctx),
});

export const schedulerCancelOp = createAsyncOp({
    name: 'frontend/scheduler_cancel',
    silent: true,
    restMirror: { method: 'POST', path: '/frontend/api/scheduler/schedules/:schedule_task_id/cancel' },
    request: async ({ payload }) => {
        const scheduleTaskId = payload && payload.schedule_task_id;
        if (!scheduleTaskId) throw new Error('schedulerCancelOp: schedule_task_id required');
        return await httpRequest({
            method: 'POST',
            url: `${BASE}/${encodeURIComponent(scheduleTaskId)}/cancel`,
        });
    },
    onSuccess: (ctx) => _reloadList(ctx),
});

export const schedulerRunNowOp = createAsyncOp({
    name: 'frontend/scheduler_run_now',
    silent: true,
    restMirror: { method: 'POST', path: '/frontend/api/scheduler/schedules/:schedule_task_id/run-now' },
    request: async ({ payload }) => {
        const scheduleTaskId = payload && payload.schedule_task_id;
        if (!scheduleTaskId) throw new Error('schedulerRunNowOp: schedule_task_id required');
        return await httpRequest({
            method: 'POST',
            url: `${BASE}/${encodeURIComponent(scheduleTaskId)}/run-now`,
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
    restMirror: { method: 'GET', path: '/frontend/api/scheduler/schedules/:schedule_task_id/redis' },
    request: async ({ payload }) => {
        const scheduleTaskId = payload && payload.schedule_task_id;
        if (!scheduleTaskId) throw new Error('schedulerRedisOp: schedule_task_id required');
        const snapshot = await httpRequest({
            method: 'GET',
            url: `${BASE}/${encodeURIComponent(scheduleTaskId)}/redis`,
        });
        return { schedule_task_id: scheduleTaskId, snapshot };
    },
    extraInitial: { snapshotByScheduleTaskId: {}, loadingByScheduleTaskId: {} },
    extraReducer: (state, event, events) => {
        if (event.type === events.REQUESTED) {
            const scheduleTaskId = event.payload && event.payload.schedule_task_id;
            if (!scheduleTaskId) return state;
            return {
                ...state,
                loadingByScheduleTaskId: {
                    ...state.loadingByScheduleTaskId,
                    [scheduleTaskId]: true,
                },
            };
        }
        if (event.type === events.SUCCEEDED) {
            const r = event.payload && event.payload.result;
            if (!r || !r.schedule_task_id) return state;
            const nextLoading = { ...state.loadingByScheduleTaskId };
            delete nextLoading[r.schedule_task_id];
            return {
                ...state,
                snapshotByScheduleTaskId: {
                    ...state.snapshotByScheduleTaskId,
                    [r.schedule_task_id]: r.snapshot,
                },
                loadingByScheduleTaskId: nextLoading,
            };
        }
        if (event.type === events.FAILED) {
            return { ...state, loadingByScheduleTaskId: {} };
        }
        return state;
    },
});
