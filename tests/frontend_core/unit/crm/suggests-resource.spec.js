import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import {
    suggestsListOp,
    suggestResolveOp,
    suggestDismissOp,
} from '../../../../apps/crm/ui/events/resources/suggests.resource.js';
import { installFetchMock } from '../../helpers/mock-fetch.js';
import { buildCtx } from '../../helpers/bus-fixtures.js';
import { resetFactories } from '../../helpers/factory-fixtures.js';

let fetchMock;

beforeEach(() => {
    resetFactories();
    fetchMock = installFetchMock();
});

afterEach(() => {
    fetchMock.uninstall();
    resetFactories();
});

describe('crm/suggests resource ops', () => {
    it('suggestsListOp calls namespace suggests endpoint', async () => {
        const page = {
            items: [
                {
                    suggest_id: 'sug_1',
                    suggest_type: 'duplicate',
                    status: 'pending',
                    target_entity_ids: ['a', 'b'],
                    payload: {
                        survivor_entity_id: 'a',
                        source_entity_id: 'b',
                        scalar_choices: {},
                        attribute_choices: {},
                    },
                },
            ],
            total: 1,
            limit: 50,
            offset: 0,
        };
        fetchMock.respondJson(
            'GET',
            '/crm/api/v1/namespaces/sales/suggests?status=pending&limit=50&offset=0',
            page,
        );
        const dispatched = [];

        await suggestsListOp.effect(
            {
                type: suggestsListOp.events.REQUESTED,
                payload: { namespace: 'sales', status: 'pending', limit: 50, offset: 0 },
                id: 'r1',
                meta: {},
            },
            buildCtx(() => ({}), dispatched),
        );

        expect(fetchMock.calls[0].url).toBe(
            '/crm/api/v1/namespaces/sales/suggests?status=pending&limit=50&offset=0',
        );
        const succeeded = dispatched.find((event) => event.type === suggestsListOp.events.SUCCEEDED);
        expect(succeeded.payload.result).toEqual(page);
    });

    it('suggestsListOp preserves empty status for all-history filter', async () => {
        const page = { items: [], total: 0, limit: 100, offset: 0 };
        fetchMock.respondJson(
            'GET',
            '/crm/api/v1/namespaces/support/suggests?status=&limit=100&offset=0',
            page,
        );
        const dispatched = [];

        await suggestsListOp.effect(
            {
                type: suggestsListOp.events.REQUESTED,
                payload: { namespace: 'support', status: '', limit: 100, offset: 0 },
                id: 'r2',
                meta: {},
            },
            buildCtx(() => ({}), dispatched),
        );

        expect(fetchMock.calls[0].url).toBe(
            '/crm/api/v1/namespaces/support/suggests?status=&limit=100&offset=0',
        );
        const succeeded = dispatched.find((event) => event.type === suggestsListOp.events.SUCCEEDED);
        expect(succeeded.payload.result).toEqual(page);
    });

    it('suggestResolveOp posts resolve endpoint', async () => {
        const response = {
            suggest_id: 'sug_1',
            suggest_type: 'duplicate',
            status: 'resolved',
            target_entity_ids: ['a', 'b'],
            payload: {},
        };
        fetchMock.respondJson(
            'POST',
            '/crm/api/v1/namespaces/sales/suggests/sug_1/resolve',
            response,
        );
        const dispatched = [];

        await suggestResolveOp.effect(
            {
                type: suggestResolveOp.events.REQUESTED,
                payload: { namespace: 'sales', suggest_id: 'sug_1' },
                id: 'r3',
                meta: {},
            },
            buildCtx(() => ({}), dispatched),
        );

        expect(fetchMock.calls[0].url).toBe('/crm/api/v1/namespaces/sales/suggests/sug_1/resolve');
        const succeeded = dispatched.find((event) => event.type === suggestResolveOp.events.SUCCEEDED);
        expect(succeeded.payload.result).toEqual(response);
    });

    it('suggestDismissOp posts dismiss endpoint', async () => {
        const response = {
            suggest_id: 'sug_2',
            suggest_type: 'missed_entity',
            status: 'dismissed',
            target_entity_ids: ['note_1'],
            payload: {},
        };
        fetchMock.respondJson(
            'POST',
            '/crm/api/v1/namespaces/support/suggests/sug_2/dismiss',
            response,
        );
        const dispatched = [];

        await suggestDismissOp.effect(
            {
                type: suggestDismissOp.events.REQUESTED,
                payload: { namespace: 'support', suggest_id: 'sug_2' },
                id: 'r4',
                meta: {},
            },
            buildCtx(() => ({}), dispatched),
        );

        expect(fetchMock.calls[0].url).toBe('/crm/api/v1/namespaces/support/suggests/sug_2/dismiss');
        const succeeded = dispatched.find((event) => event.type === suggestDismissOp.events.SUCCEEDED);
        expect(succeeded.payload.result).toEqual(response);
    });
});
