/**
 * platform/work_item_* фабрики: get/counts/list/move/assign + push merge.
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { CoreEvents } from '@platform/lib/events/contract.js';
import { registerFactory } from '@platform/lib/events/factory-registry.js';
import {
    createPlatformWorkItemCountsAuthEffect,
    platformWorkItemAssignOp,
    platformWorkItemCountsOp,
    platformWorkItemFactories,
    platformWorkItemGetOp,
    platformWorkItemMoveOp,
    platformWorkItemsResource,
} from '@platform/lib/events/resources/platform-work-item.resource.js';
import { buildCtx } from '../helpers/bus-fixtures.js';
import { installFetchMock } from '../helpers/mock-fetch.js';
import { resetFactories } from '../helpers/factory-fixtures.js';

let fetchMock;

beforeEach(() => {
    resetFactories();
    fetchMock = installFetchMock();
});
afterEach(() => {
    fetchMock.uninstall();
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

describe('platformWorkItemFactories', () => {
    it('экспортирует все фабрики WorkItem', () => {
        expect(platformWorkItemFactories).toEqual([
            platformWorkItemGetOp,
            platformWorkItemCountsOp,
            platformWorkItemsResource,
            platformWorkItemMoveOp,
            platformWorkItemAssignOp,
        ]);
    });
});

describe('platformWorkItemGetOp', () => {
    it('run без work_item_id — throw', async () => {
        registerFactory(platformWorkItemGetOp);
        await expect(platformWorkItemGetOp.run({}, buildCtx(() => ({}), []))).rejects.toThrow(/work_item_id/);
    });

    it('GET по work_item_id', async () => {
        registerFactory(platformWorkItemGetOp);
        fetchMock.respondJson('GET', '/worktracker/api/v1/work-items/wi-1', {
            work_item_id: 'wi-1',
            title: 'Task',
        });
        const dispatched = [];
        await platformWorkItemGetOp.run({ work_item_id: 'wi-1' }, buildCtx(() => ({}), dispatched));
        expect(fetchMock.calls[0].url).toBe('/worktracker/api/v1/work-items/wi-1');
        const ok = dispatched.find((d) => d.type === platformWorkItemGetOp.events.SUCCEEDED);
        expect(ok.payload.result.work_item_id).toBe('wi-1');
    });
});

describe('platformWorkItemCountsOp', () => {
    it('extraReducer сохраняет счётчики из SUCCEEDED', () => {
        const next = platformWorkItemCountsOp.reducer(countsState, {
            type: platformWorkItemCountsOp.events.SUCCEEDED,
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

    it('extraReducer: REQUESTED и невалидный result не трогают счётчики', () => {
        const requested = platformWorkItemCountsOp.reducer(countsState, {
            type: platformWorkItemCountsOp.events.REQUESTED,
            payload: {},
        });
        expect(requested.assigned_open_count).toBe(0);
        expect(requested.queue_inbox_count).toBe(0);
        expect(requested.busy).toBe(true);

        const nullResult = platformWorkItemCountsOp.reducer(countsState, {
            type: platformWorkItemCountsOp.events.SUCCEEDED,
            payload: { result: null },
        });
        expect(nullResult.assigned_open_count).toBe(0);
        expect(nullResult.work_queue_ids).toEqual([]);

        const defaults = platformWorkItemCountsOp.reducer(countsState, {
            type: platformWorkItemCountsOp.events.SUCCEEDED,
            payload: { result: { assigned_open_count: 'x', queue_inbox_count: null } },
        });
        expect(defaults.assigned_open_count).toBe(0);
        expect(defaults.queue_inbox_count).toBe(0);
        expect(defaults.work_queue_ids).toEqual([]);
    });

    it('request ходит в mine/summary', async () => {
        registerFactory(platformWorkItemCountsOp);
        fetchMock.respondJson('GET', '/worktracker/api/v1/work-items/mine/summary', {
            assigned_open_count: 1,
            queue_inbox_count: 4,
            work_queue_ids: ['q'],
        });
        const dispatched = [];
        await platformWorkItemCountsOp.run({}, buildCtx(() => ({}), dispatched));
        expect(fetchMock.calls[0].url).toBe('/worktracker/api/v1/work-items/mine/summary');
        const ok = dispatched.find((d) => d.type === platformWorkItemCountsOp.events.SUCCEEDED);
        expect(ok.payload.result.queue_inbox_count).toBe(4);
    });
});

describe('platformWorkItemsResource', () => {
    it('listQuery собирает фильтры, exclude_terminal и пагинацию', async () => {
        fetchMock.respondJson(
            'GET',
            (url) => url.startsWith('/worktracker/api/v1/work-items?'),
            { items: [], total: 0 },
        );
        const dispatched = [];
        await platformWorkItemsResource.effect(
            {
                type: platformWorkItemsResource.events.LIST_REQUESTED,
                payload: {
                    board_id: 'b1',
                    namespace: 'ns',
                    kind: 'hitl',
                    state: 'open',
                    work_queue_id: 'q1',
                    assignee_user_id: 'u1',
                    assignee_flow_id: 'f1',
                    exclude_terminal: true,
                    limit: 25,
                    offset: 10,
                    ignored: 'x',
                },
                id: 'list1',
                meta: {},
            },
            buildCtx(() => ({}), dispatched),
        );
        const url = fetchMock.calls[0].url;
        expect(url).toContain('board_id=b1');
        expect(url).toContain('namespace=ns');
        expect(url).toContain('kind=hitl');
        expect(url).toContain('state=open');
        expect(url).toContain('work_queue_id=q1');
        expect(url).toContain('assignee_user_id=u1');
        expect(url).toContain('assignee_flow_id=f1');
        expect(url).toContain('exclude_terminal=true');
        expect(url).toContain('limit=25');
        expect(url).toContain('offset=10');
        expect(url).not.toContain('ignored=');
        expect(dispatched.some((d) => d.type === platformWorkItemsResource.events.LIST_LOADED)).toBe(true);
    });

    it('listQuery без payload — только limit/offset по умолчанию', async () => {
        fetchMock.respondJson(
            'GET',
            (url) => url.startsWith('/worktracker/api/v1/work-items?'),
            { items: [], total: 0 },
        );
        await platformWorkItemsResource.effect(
            {
                type: platformWorkItemsResource.events.LIST_REQUESTED,
                payload: null,
                id: 'list2',
                meta: {},
            },
            buildCtx(() => ({}), []),
        );
        expect(fetchMock.calls[0].url).toBe('/worktracker/api/v1/work-items?limit=100&offset=0');
    });

    it('push created/updated мержит work_item в items и byId', () => {
        const initial = platformWorkItemsResource.slice.initial;
        const created = platformWorkItemsResource.reducer(initial, {
            type: 'worktracker/work_item/created',
            payload: { work_item: { work_item_id: 'wi-1', title: 'A' } },
        });
        expect(created.items).toEqual([{ work_item_id: 'wi-1', title: 'A' }]);
        expect(created.byId['wi-1'].title).toBe('A');

        const updated = platformWorkItemsResource.reducer(created, {
            type: 'worktracker/work_item/updated',
            payload: { work_item: { work_item_id: 'wi-1', title: 'B' } },
        });
        expect(updated.items).toEqual([{ work_item_id: 'wi-1', title: 'B' }]);
        expect(updated.byId['wi-1'].title).toBe('B');
    });

    it('push без валидного work_item не меняет state', () => {
        const initial = platformWorkItemsResource.slice.initial;
        expect(
            platformWorkItemsResource.reducer(initial, {
                type: 'worktracker/work_item/moved',
                payload: null,
            }),
        ).toBe(initial);
        expect(
            platformWorkItemsResource.reducer(initial, {
                type: 'worktracker/work_item/completed',
                payload: { work_item: { title: 'no-id' } },
            }),
        ).toBe(initial);
        expect(
            platformWorkItemsResource.reducer(initial, {
                type: 'other/event',
                payload: { work_item: { work_item_id: 'x' } },
            }),
        ).toBe(initial);
    });
});

describe('platformWorkItemMoveOp', () => {
    it('без work_item_id — throw', async () => {
        registerFactory(platformWorkItemMoveOp);
        await expect(platformWorkItemMoveOp.run({}, buildCtx(() => ({}), []))).rejects.toThrow(/work_item_id/);
    });

    it('POST move с board_column_id и state', async () => {
        registerFactory(platformWorkItemMoveOp);
        fetchMock.respondJson('POST', '/worktracker/api/v1/work-items/wi-1/move', {
            work_item_id: 'wi-1',
            state: 'done',
        });
        const dispatched = [];
        await platformWorkItemMoveOp.run(
            { work_item_id: 'wi-1', board_column_id: 'col-2', state: 'done' },
            buildCtx(() => ({}), dispatched),
        );
        expect(fetchMock.calls[0].url).toBe('/worktracker/api/v1/work-items/wi-1/move');
        expect(JSON.parse(fetchMock.calls[0].init.body)).toEqual({
            board_column_id: 'col-2',
            state: 'done',
        });
        expect(dispatched.some((d) => d.type === platformWorkItemMoveOp.events.SUCCEEDED)).toBe(true);
    });
});

describe('platformWorkItemAssignOp', () => {
    it('без work_item_id / assignment — throw', async () => {
        registerFactory(platformWorkItemAssignOp);
        await expect(platformWorkItemAssignOp.run({}, buildCtx(() => ({}), []))).rejects.toThrow(/work_item_id/);
        await expect(
            platformWorkItemAssignOp.run({ work_item_id: 'wi-1' }, buildCtx(() => ({}), [])),
        ).rejects.toThrow(/assignment/);
    });

    it('POST assign с assignment', async () => {
        registerFactory(platformWorkItemAssignOp);
        fetchMock.respondJson('POST', '/worktracker/api/v1/work-items/wi-1/assign', {
            work_item_id: 'wi-1',
        });
        const dispatched = [];
        await platformWorkItemAssignOp.run(
            { work_item_id: 'wi-1', assignment: { kind: 'user', user_id: 'u1' } },
            buildCtx(() => ({}), dispatched),
        );
        expect(fetchMock.calls[0].url).toBe('/worktracker/api/v1/work-items/wi-1/assign');
        expect(JSON.parse(fetchMock.calls[0].init.body)).toEqual({
            assignment: { kind: 'user', user_id: 'u1' },
        });
        expect(dispatched.some((d) => d.type === platformWorkItemAssignOp.events.SUCCEEDED)).toBe(true);
    });
});

describe('createPlatformWorkItemCountsAuthEffect', () => {
    it('AUTH_USER_LOADED запрашивает summary', async () => {
        registerFactory(platformWorkItemCountsOp);
        fetchMock.respondJson('GET', '/worktracker/api/v1/work-items/mine/summary', {
            assigned_open_count: 1,
            queue_inbox_count: 2,
        });
        const dispatched = [];
        await createPlatformWorkItemCountsAuthEffect()(
            { type: CoreEvents.AUTH_USER_LOADED, id: 'auth1', payload: {}, meta: { ts: 0, source: 'local' } },
            buildCtx(() => ({}), dispatched),
        );
        expect(fetchMock.calls.some((call) => call.url.includes('/work-items/mine/summary'))).toBe(true);
    });
});
