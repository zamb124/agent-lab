/**
 * Ресурсы scheduler — расписания платформенного scheduler (cron / interval / one-time),
 * команды `scheduler/schedule_tasks/*` владельца (WS + REST-зеркало `/scheduler/api/v1/schedules/*`).
 *
 * Состав:
 *   - schedulerTasksResource: createResourceCollection (list, create) — основная коллекция
 *     с фильтром через listQuery; исходы pause/resume/cancel/run-now мержатся в неё.
 *   - schedulerPauseOp / schedulerResumeOp / schedulerCancelOp / schedulerRunNowOp: createAsyncOp,
 *     silent; результат — обновлённая PlatformScheduledTask.
 *   - schedulerRedisOp: createAsyncOp, silent, держит snapshot Redis по schedule_task_id в slice
 *     (`snapshotByScheduleTaskId`) — UI показывает inline под строкой задачи без модалки.
 *
 * schedule_task_id — основной идентификатор записи платформенного scheduler.
 */

import {
    createResourceCollection,
    createAsyncOp,
    upsertItem,
} from '../index.js';
import { CoreEvents } from '../contract.js';

const SCHEDULE_TASK_MUTATION_SUCCEEDED = new Set([
    'scheduler/schedule_pause/succeeded',
    'scheduler/schedule_resume/succeeded',
    'scheduler/schedule_cancel/succeeded',
    'scheduler/schedule_run_now/succeeded',
]);

export const schedulerTasksResource = createResourceCollection({
    name: 'scheduler/schedule_tasks',
    baseUrl: '/scheduler/api/v1/schedules',
    idField: 'schedule_task_id',
    operations: ['list', 'create'],
    transport: 'ws',
    wsTimeoutMs: 8_000,
    toastKeys: {
        create: 'frontend:scheduler_modal.toast_created',
    },
    listQuery: (payload) => {
        const q: Record<string, unknown> = { limit: 200 };
        if (payload && payload.status) q.status = payload.status;
        if (payload && payload.target_service) q.target_service = payload.target_service;
        if (payload && payload.task_name) q.task_name = payload.task_name;
        return q;
    },
    extraReducer: (state, event) => {
        if (!SCHEDULE_TASK_MUTATION_SUCCEEDED.has(event.type)) {
            return state;
        }
        const task = (event.payload as { result?: Record<string, unknown> } | null)?.result;
        if (!task || typeof task.schedule_task_id !== 'string') {
            return state;
        }
        return upsertItem(state, task, 'schedule_task_id') as typeof state;
    },
});

export const schedulerPauseOp = createAsyncOp({
    name: 'scheduler/schedule_pause',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'scheduler/schedule_tasks/pause_requested',
    restMirror: { method: 'POST', path: '/scheduler/api/v1/schedules/:schedule_task_id/pause' },
});

export const schedulerResumeOp = createAsyncOp({
    name: 'scheduler/schedule_resume',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'scheduler/schedule_tasks/resume_requested',
    restMirror: { method: 'POST', path: '/scheduler/api/v1/schedules/:schedule_task_id/resume' },
});

export const schedulerCancelOp = createAsyncOp({
    name: 'scheduler/schedule_cancel',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'scheduler/schedule_tasks/cancel_requested',
    restMirror: { method: 'POST', path: '/scheduler/api/v1/schedules/:schedule_task_id/cancel' },
});

export const schedulerRunNowOp = createAsyncOp({
    name: 'scheduler/schedule_run_now',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'scheduler/schedule_tasks/run_now_requested',
    restMirror: { method: 'POST', path: '/scheduler/api/v1/schedules/:schedule_task_id/run-now' },
    onSuccess: (ctx) => {
        ctx.dispatch(
            CoreEvents.UI_TOAST_SHOW,
            { type: 'success', i18n_key: 'frontend:scheduler_page.toast_run_queued' },
            { source: 'local' },
        );
    },
});

export const schedulerRedisOp = createAsyncOp({
    name: 'scheduler/schedule_redis',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'scheduler/schedule_tasks/redis_snapshot_requested',
    restMirror: { method: 'GET', path: '/scheduler/api/v1/schedules/:schedule_task_id/redis' },
    extraInitial: { snapshotByScheduleTaskId: {}, loadingByScheduleTaskId: {} },
    extraReducer: (state, event, events) => {
        const loadingById = state.loadingByScheduleTaskId as Record<string, boolean>;
        const snapshotById = state.snapshotByScheduleTaskId as Record<string, unknown>;
        if (event.type === events.REQUESTED) {
            const p = event.payload as { schedule_task_id?: unknown } | null;
            const scheduleTaskId = p && p.schedule_task_id;
            if (typeof scheduleTaskId !== 'string' || scheduleTaskId.length === 0) return state;
            return {
                ...state,
                loadingByScheduleTaskId: {
                    ...loadingById,
                    [scheduleTaskId]: true,
                },
            };
        }
        if (event.type === events.SUCCEEDED) {
            const p = event.payload as { request?: { schedule_task_id?: unknown }; result?: unknown } | null;
            const scheduleTaskId = p?.request?.schedule_task_id;
            if (typeof scheduleTaskId !== 'string' || scheduleTaskId.length === 0) return state;
            const nextLoading = { ...loadingById };
            delete nextLoading[scheduleTaskId];
            return {
                ...state,
                snapshotByScheduleTaskId: {
                    ...snapshotById,
                    [scheduleTaskId]: p?.result,
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
