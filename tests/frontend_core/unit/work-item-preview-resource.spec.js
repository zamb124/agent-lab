/**
 * platform/work_item_get и platform/work_item_counts.
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { CoreEvents } from '@platform/lib/events/contract.js';
import { registerFactory } from '@platform/lib/events/factory-registry.js';
import {
    createPlatformWorkItemCountsAuthEffect,
    platformWorkItemCountsOp,
    platformWorkItemGetOp,
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

describe('platformWorkItemGetOp', () => {
    it('run без work_item_id — throw', async () => {
        registerFactory(platformWorkItemGetOp);
        await expect(platformWorkItemGetOp.run({}, buildCtx(() => ({}), []))).rejects.toThrow(/work_item_id/);
    });
});

describe('platformWorkItemCountsOp', () => {
    it('extraReducer сохраняет счётчики из SUCCEEDED', () => {
        const state = {
            busy: false,
            error: null,
            lastResult: null,
            lastRequestId: null,
            assigned_open_count: 0,
            queue_inbox_count: 0,
            total_open_count: 0,
        };
        const next = platformWorkItemCountsOp.reducer(state, {
            type: platformWorkItemCountsOp.events.SUCCEEDED,
            payload: {
                result: {
                    assigned_open_count: 2,
                    queue_inbox_count: 3,
                },
            },
        });
        expect(next.assigned_open_count).toBe(2);
        expect(next.queue_inbox_count).toBe(3);
        expect(next.total_open_count).toBe(5);
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
