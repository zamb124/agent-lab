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
import { isPlainRecord } from '../payload.js';

function booleanMap(value: unknown, label: string): Record<string, boolean> {
    if (!isPlainRecord(value)) {
        throw new Error(`${label} must be an object`);
    }
    const map: Record<string, boolean> = {};
    for (const [key, flag] of Object.entries(value)) {
        if (typeof flag !== 'boolean') {
            throw new Error(`${label}.${key} must be a boolean`);
        }
        map[key] = flag;
    }
    return map;
}

function snapshotMap(value: unknown): Record<string, unknown> {
    if (!isPlainRecord(value)) {
        throw new Error('scheduler redis: snapshotByScheduleTaskId must be an object');
    }
    return value;
}

function scheduleTaskId(value: unknown): string | null {
    if (typeof value !== 'string' || value.length === 0) return null;
    return value;
}

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
        if (!isPlainRecord(event.payload) || !isPlainRecord(event.payload.result) || typeof event.payload.result.schedule_task_id !== 'string') {
            throw new Error('scheduler schedule task: SUCCEEDED result.schedule_task_id required');
        }
        return upsertItem(state, event.payload.result, 'schedule_task_id');
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
        const loadingById = booleanMap(state.loadingByScheduleTaskId, 'scheduler redis: loadingByScheduleTaskId');
        const snapshotById = snapshotMap(state.snapshotByScheduleTaskId);
        if (event.type === events.REQUESTED) {
            const id = isPlainRecord(event.payload) ? scheduleTaskId(event.payload.schedule_task_id) : null;
            if (id === null) {
                throw new Error('scheduler redis: REQUESTED schedule_task_id required');
            }
            return {
                ...state,
                loadingByScheduleTaskId: {
                    ...loadingById,
                    [id]: true,
                },
            };
        }
        if (event.type === events.SUCCEEDED) {
            const payload = event.payload;
            const request = isPlainRecord(payload) && isPlainRecord(payload.request) ? payload.request : null;
            const id = request === null ? null : scheduleTaskId(request.schedule_task_id);
            if (id === null || !isPlainRecord(payload)) {
                throw new Error('scheduler redis: SUCCEEDED request.schedule_task_id required');
            }
            const nextLoading = { ...loadingById };
            delete nextLoading[id];
            return {
                ...state,
                snapshotByScheduleTaskId: {
                    ...snapshotById,
                    [id]: payload.result,
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

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'scheduler/schedule_tasks': typeof schedulerTasksResource;
        'scheduler/schedule_pause': typeof schedulerPauseOp;
        'scheduler/schedule_resume': typeof schedulerResumeOp;
        'scheduler/schedule_cancel': typeof schedulerCancelOp;
        'scheduler/schedule_run_now': typeof schedulerRunNowOp;
        'scheduler/schedule_redis': typeof schedulerRedisOp;
    }
}
