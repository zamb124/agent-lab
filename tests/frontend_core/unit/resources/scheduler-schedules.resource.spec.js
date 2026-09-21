/**
 * Ресурс владельца scheduler в core: команды `scheduler/schedule_tasks/*` по WS,
 * исходы мутаций мержатся в коллекцию, redis-snapshot ложится по schedule_task_id.
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
import { resetFactories } from '../../helpers/factory-fixtures.js';

const BASE = '/scheduler/api/v1/schedules';

beforeEach(() => {
    resetFactories();
});
afterEach(() => {
    resetFactories();
});

describe('scheduler schedules resource', () => {
    it('коллекция и операции — WS-команды владельца с REST-зеркалом', () => {
        expect(schedulerTasksResource.name).toBe('scheduler/schedule_tasks');
        expect(schedulerTasksResource.transport).toBe('ws');
        expect(schedulerTasksResource.baseUrl).toBe(BASE);
        expect(schedulerTasksResource.idField).toBe('schedule_task_id');
        for (const [op, action, verb] of [
            [schedulerPauseOp, 'pause', 'pause'],
            [schedulerResumeOp, 'resume', 'resume'],
            [schedulerCancelOp, 'cancel', 'cancel'],
            [schedulerRunNowOp, 'run-now', 'run_now'],
        ]) {
            expect(op.transport).toBe('ws');
            expect(op.commandType).toBe(`scheduler/schedule_tasks/${verb}_requested`);
            expect(op.restMirror).toEqual({ method: 'POST', path: `${BASE}/:schedule_task_id/${action}` });
        }
        expect(schedulerRedisOp.commandType).toBe('scheduler/schedule_tasks/redis_snapshot_requested');
        expect(schedulerRedisOp.restMirror).toEqual({ method: 'GET', path: `${BASE}/:schedule_task_id/redis` });
    });

    it('исход pause/resume/cancel/run-now мержится в коллекцию без reload', () => {
        const listed = schedulerTasksResource.reducer(schedulerTasksResource.slice.initial, {
            type: schedulerTasksResource.events.LIST_LOADED,
            payload: { items: [{ schedule_task_id: 'task-1', status: 'pending' }], total: 1 },
        });
        for (const op of [schedulerPauseOp, schedulerResumeOp, schedulerCancelOp, schedulerRunNowOp]) {
            const merged = schedulerTasksResource.reducer(listed, {
                type: op.events.SUCCEEDED,
                payload: { result: { schedule_task_id: 'task-1', status: op.name }, request: { schedule_task_id: 'task-1' } },
            });
            expect(merged.items).toHaveLength(1);
            expect(merged.byId['task-1'].status).toBe(op.name);
        }
    });

    it('redis кладёт snapshot по schedule_task_id из request', () => {
        const snapshot = { schedule_id: 'sched-2', present: true };
        const requested = schedulerRedisOp.reducer(schedulerRedisOp.slice.initial, {
            type: schedulerRedisOp.events.REQUESTED,
            payload: { schedule_task_id: 'task-2' },
        });
        expect(requested.loadingByScheduleTaskId['task-2']).toBe(true);
        const state = schedulerRedisOp.reducer(requested, {
            type: schedulerRedisOp.events.SUCCEEDED,
            payload: { result: snapshot, request: { schedule_task_id: 'task-2' } },
        });
        expect(state.snapshotByScheduleTaskId['task-2']).toEqual(snapshot);
        expect(state.loadingByScheduleTaskId['task-2']).toBeFalsy();
    });
});
