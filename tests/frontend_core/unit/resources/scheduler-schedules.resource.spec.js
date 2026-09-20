/**
 * Ресурс владельца scheduler в core: расписания без frontend-прокси.
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import {
    schedulerTasksResource,
    schedulerPauseOp,
    schedulerResumeOp,
    schedulerCancelOp,
    schedulerRunNowOp,
    schedulerRedisOp,
} from '@platform/lib/events/resources/scheduler-schedules.resource.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
import { installFetchMock } from '../../helpers/mock-fetch.js';
import { buildCtx } from '../../helpers/bus-fixtures.js';
import { resetFactories } from '../../helpers/factory-fixtures.js';

const BASE = '/scheduler/api/v1/schedules';

let fetchMock;

beforeEach(() => {
    resetFactories();
    fetchMock = installFetchMock();
});
afterEach(() => {
    fetchMock.uninstall();
});

async function runOp(op, payload) {
    const dispatched = [];
    await op.effect(
        { type: op.events.REQUESTED, payload, id: 'r1', meta: {} },
        buildCtx(() => ({}), dispatched),
    );
    return dispatched;
}

describe('scheduler schedules resource', () => {
    it('коллекция и restMirror операций указывают на API владельца scheduler', () => {
        expect(schedulerTasksResource.name).toBe('scheduler/schedule_tasks');
        expect(schedulerTasksResource.baseUrl).toBe(BASE);
        expect(schedulerTasksResource.idField).toBe('schedule_task_id');
        expect(schedulerPauseOp.restMirror).toEqual({ method: 'POST', path: `${BASE}/:schedule_task_id/pause` });
        expect(schedulerResumeOp.restMirror).toEqual({ method: 'POST', path: `${BASE}/:schedule_task_id/resume` });
        expect(schedulerCancelOp.restMirror).toEqual({ method: 'POST', path: `${BASE}/:schedule_task_id/cancel` });
        expect(schedulerRunNowOp.restMirror).toEqual({ method: 'POST', path: `${BASE}/:schedule_task_id/run-now` });
        expect(schedulerRedisOp.restMirror).toEqual({ method: 'GET', path: `${BASE}/:schedule_task_id/redis` });
    });

    it('pause/resume/cancel зовут владельца и перезагружают список', async () => {
        for (const [op, action] of [
            [schedulerPauseOp, 'pause'],
            [schedulerResumeOp, 'resume'],
            [schedulerCancelOp, 'cancel'],
        ]) {
            fetchMock.respondJson('POST', `${BASE}/task-1/${action}`, { schedule_task_id: 'task-1', status: action });
            const dispatched = await runOp(op, { schedule_task_id: 'task-1' });
            const ok = dispatched.find((d) => d.type === op.events.SUCCEEDED);
            expect(ok, `${op.name} SUCCEEDED`).toBeTruthy();
            expect(ok.payload.result.schedule_task_id).toBe('task-1');
            expect(
                dispatched.some((d) => d.type === schedulerTasksResource.events.LIST_REQUESTED),
                `${op.name} reload списка`,
            ).toBe(true);
            await expect(runOp(op, {})).rejects.toThrow('schedule_task_id required');
        }
    });

    it('run-now эмитит toast и reload; redis кладёт snapshot по schedule_task_id', async () => {
        fetchMock.respondJson('POST', `${BASE}/task-2/run-now`, { schedule_task_id: 'task-2', status: 'pending' });
        const runDispatched = await runOp(schedulerRunNowOp, { schedule_task_id: 'task-2' });
        expect(runDispatched.some((d) => d.type === schedulerRunNowOp.events.SUCCEEDED)).toBe(true);
        const toast = runDispatched.find((d) => d.type === CoreEvents.UI_TOAST_SHOW);
        expect(toast.payload).toEqual({ type: 'success', i18n_key: 'frontend:scheduler_page.toast_run_queued' });
        expect(runDispatched.some((d) => d.type === schedulerTasksResource.events.LIST_REQUESTED)).toBe(true);

        const snapshot = { schedule_id: 'sched-2', present: true };
        fetchMock.respondJson('GET', `${BASE}/task-2/redis`, snapshot);
        const redisDispatched = await runOp(schedulerRedisOp, { schedule_task_id: 'task-2' });
        const ok = redisDispatched.find((d) => d.type === schedulerRedisOp.events.SUCCEEDED);
        expect(ok.payload.result).toEqual({ schedule_task_id: 'task-2', snapshot });
        const requested = schedulerRedisOp.reducer(schedulerRedisOp.initialState, {
            type: schedulerRedisOp.events.REQUESTED,
            payload: { schedule_task_id: 'task-2' },
        });
        const state = schedulerRedisOp.reducer(requested, ok);
        expect(state.snapshotByScheduleTaskId['task-2']).toEqual(snapshot);
        expect(state.loadingByScheduleTaskId['task-2']).toBeFalsy();
    });
});
