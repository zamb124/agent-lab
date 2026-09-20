/**
 * worktracker/work_item_* фабрики: имена, commandType, reducer, push merge.
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import {
    createWorktrackerWorkItemCountsAuthEffect,
    workItemAssignOp,
    workItemCountsOp,
    workItemGetOp,
    workItemMoveOp,
    workItemsResource,
    worktrackerWorkItemFactories,
} from '@platform/lib/events/resources/work-items.resource.js';
import { buildCtx } from '../helpers/bus-fixtures.js';
import { resetFactories } from '../helpers/factory-fixtures.js';

beforeEach(() => {
    resetFactories();
});
afterEach(() => {
    resetFactories();
});

const countsState = {
    busy: false,
    error: null,
    lastResult: null,
    lastRequestId: null,
    assigned_open_count: 0,
    queue_inbox_count: 0,
    total_open_count: 0,
    work_queue_ids: [],
};

describe('worktrackerWorkItemFactories', () => {
    it('экспортирует фабрики владельца worktracker', () => {
        expect(worktrackerWorkItemFactories).toContain(workItemGetOp);
        expect(worktrackerWorkItemFactories).toContain(workItemCountsOp);
        expect(worktrackerWorkItemFactories).toContain(workItemsResource);
        expect(worktrackerWorkItemFactories).toContain(workItemMoveOp);
        expect(worktrackerWorkItemFactories).toContain(workItemAssignOp);
    });

    it('транспорт WS и commandType трёхсегментный', () => {
        expect(workItemGetOp.transport).toBe('ws');
        expect(workItemGetOp.commandType).toBe('worktracker/work_items/item_requested');
        expect(workItemMoveOp.commandType).toBe('worktracker/work_items/move_requested');
        expect(workItemAssignOp.commandType).toBe('worktracker/work_items/assign_requested');
        expect(workItemCountsOp.commandType).toBe('worktracker/work_items/mine_summary_requested');
        expect(workItemsResource.transport).toBe('ws');
    });
});

describe('workItemCountsOp', () => {
    it('extraReducer сохраняет счётчики из SUCCEEDED', () => {
        const next = workItemCountsOp.reducer(countsState, {
            type: workItemCountsOp.events.SUCCEEDED,
            payload: {
                result: {
                    assigned_open_count: 2,
                    queue_inbox_count: 3,
                    work_queue_ids: ['q1', 'q2', '', 7],
                },
            },
        });
        expect(next.assigned_open_count).toBe(2);
        expect(next.queue_inbox_count).toBe(3);
        expect(next.total_open_count).toBe(5);
        expect(next.work_queue_ids).toEqual(['q1', 'q2']);
    });

    it('extraReducer: REQUESTED не трогает счётчики', () => {
        const requested = workItemCountsOp.reducer(countsState, {
            type: workItemCountsOp.events.REQUESTED,
            payload: {},
        });
        expect(requested.assigned_open_count).toBe(0);
        expect(requested.queue_inbox_count).toBe(0);
        expect(requested.busy).toBe(true);
    });

    it('extraReducer бросает на битый result', () => {
        expect(() => workItemCountsOp.reducer(countsState, {
            type: workItemCountsOp.events.SUCCEEDED,
            payload: { result: null },
        })).toThrow(/result must be object/);
        expect(() => workItemCountsOp.reducer(countsState, {
            type: workItemCountsOp.events.SUCCEEDED,
            payload: { result: { assigned_open_count: 'x', queue_inbox_count: null } },
        })).toThrow(/required numbers/);
    });
});

describe('workItemsResource', () => {
    it('push created/updated мержит work_item в items и byId', () => {
        const initial = workItemsResource.slice.initial;
        const created = workItemsResource.reducer(initial, {
            type: 'worktracker/work_item/created',
            payload: { work_item: { work_item_id: 'wi-1', title: 'A' } },
        });
        expect(created.items).toEqual([{ work_item_id: 'wi-1', title: 'A' }]);
        expect(created.byId['wi-1'].title).toBe('A');

        const updated = workItemsResource.reducer(created, {
            type: 'worktracker/work_item/updated',
            payload: { work_item: { work_item_id: 'wi-1', title: 'B' } },
        });
        expect(updated.items).toEqual([{ work_item_id: 'wi-1', title: 'B' }]);
        expect(updated.byId['wi-1'].title).toBe('B');
    });

    it('push без валидного work_item не меняет state', () => {
        const initial = workItemsResource.slice.initial;
        expect(
            workItemsResource.reducer(initial, {
                type: 'worktracker/work_item/moved',
                payload: null,
            }),
        ).toBe(initial);
        expect(
            workItemsResource.reducer(initial, {
                type: 'worktracker/work_item/completed',
                payload: { work_item: { title: 'no-id' } },
            }),
        ).toBe(initial);
        expect(
            workItemsResource.reducer(initial, {
                type: 'other/event',
                payload: { work_item: { work_item_id: 'x' } },
            }),
        ).toBe(initial);
    });
});

describe('createWorktrackerWorkItemCountsAuthEffect', () => {
    it('игнорирует чужие события', () => {
        const dispatched = [];
        createWorktrackerWorkItemCountsAuthEffect()(
            { type: 'other/event', id: 'x', payload: {}, meta: { ts: 0, source: 'local' } },
            buildCtx(() => ({}), dispatched),
        );
        expect(dispatched).toEqual([]);
    });
});
