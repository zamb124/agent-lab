import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import {
    suggestsListOp,
    suggestResolveOp,
    suggestDismissOp,
} from '../../../../apps/crm/ui/events/resources/suggests.resource.js';
import { resetFactories } from '../../helpers/factory-fixtures.js';

beforeEach(() => {
    resetFactories();
});

afterEach(() => {
    resetFactories();
});

function listedState(items, total) {
    return suggestsListOp.reducer(suggestsListOp.slice.initial, {
        type: suggestsListOp.events.SUCCEEDED,
        payload: {
            result: {
                items,
                total,
                limit: 50,
                offset: 0,
            },
        },
    });
}

describe('crm/suggests resource ops', () => {
    it('WS transport, commandType и restMirror', () => {
        expect(suggestsListOp.transport).toBe('ws');
        expect(suggestsListOp.commandType).toBe('crm/suggests/list_requested');
        expect(suggestsListOp.restMirror).toEqual({
            method: 'GET',
            path: '/crm/api/v1/namespaces/:namespace/suggests',
        });

        expect(suggestResolveOp.transport).toBe('ws');
        expect(suggestResolveOp.commandType).toBe('crm/suggests/resolve_requested');
        expect(suggestResolveOp.restMirror).toEqual({
            method: 'POST',
            path: '/crm/api/v1/namespaces/:namespace/suggests/:suggest_id/resolve',
        });

        expect(suggestDismissOp.transport).toBe('ws');
        expect(suggestDismissOp.commandType).toBe('crm/suggests/dismiss_requested');
        expect(suggestDismissOp.restMirror).toEqual({
            method: 'POST',
            path: '/crm/api/v1/namespaces/:namespace/suggests/:suggest_id/dismiss',
        });
    });

    it('resolve/dismiss succeeded убирает suggest из lastResult', () => {
        const listed = listedState(
            [
                { suggest_id: 'sug_1', status: 'pending' },
                { suggest_id: 'sug_2', status: 'pending' },
            ],
            2,
        );
        expect(listed.lastResult.items.map((row) => row.suggest_id)).toEqual(['sug_1', 'sug_2']);

        const afterResolve = suggestsListOp.reducer(listed, {
            type: suggestResolveOp.events.SUCCEEDED,
            payload: { result: { suggest_id: 'sug_1', status: 'resolved' } },
        });
        expect(afterResolve.lastResult.items.map((row) => row.suggest_id)).toEqual(['sug_2']);
        expect(afterResolve.lastResult.total).toBe(1);

        const afterDismiss = suggestsListOp.reducer(afterResolve, {
            type: suggestDismissOp.events.SUCCEEDED,
            payload: { result: { suggest_id: 'sug_2', status: 'dismissed' } },
        });
        expect(afterDismiss.lastResult.items).toEqual([]);
        expect(afterDismiss.lastResult.total).toBe(0);
    });

    it('extraReducer не трогает lastResult без matching suggest_id', () => {
        const listed = listedState(
            [{ suggest_id: 'sug_1', status: 'pending' }],
            1,
        );
        const next = suggestsListOp.reducer(listed, {
            type: suggestResolveOp.events.SUCCEEDED,
            payload: { result: { suggest_id: 'sug_missing', status: 'resolved' } },
        });
        expect(next).toBe(listed);
    });
});
