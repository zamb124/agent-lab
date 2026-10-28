/**
 * Мерж-хелперы фабрик: upsertItem/removeItem и повторный запрос последнего payload.
 */

import { describe, expect, it, vi } from 'vitest';
import type { EffectCtx } from '@platform/lib/events/contract.js';
import { reloadLastList, removeItem, rerunLastRequest, upsertItem } from '@platform/lib/events/factories/merge.js';

interface Row extends Record<string, unknown> {
    id: string;
    title: string;
}

interface State extends Record<string, unknown> {
    items: readonly (Row | null)[];
    byId: Readonly<Record<string, Row | null>>;
}

const initial: State = {
    items: [{ id: 'a', title: 'A' }],
    byId: { a: { id: 'a', title: 'A' } },
};

describe('upsertItem', () => {
    it('добавляет новый элемент в конец и в byId', () => {
        const next = upsertItem(initial, { id: 'b', title: 'B' }, 'id');
        expect(next.items.map((row) => row?.id)).toEqual(['a', 'b']);
        expect(next.byId.b).toEqual({ id: 'b', title: 'B' });
    });

    it('заменяет существующий элемент на месте', () => {
        const next = upsertItem(initial, { id: 'a', title: 'A2' }, 'id');
        expect(next.items).toEqual([{ id: 'a', title: 'A2' }]);
        expect(next.byId.a).toEqual({ id: 'a', title: 'A2' });
        expect(initial.items).toEqual([{ id: 'a', title: 'A' }]);
    });

    it('бросает без значения id-поля', () => {
        expect(() => upsertItem(initial, { title: 'x' }, 'id')).toThrow(/item\.id required/);
        expect(() => upsertItem(initial, { id: '', title: 'x' }, 'id')).toThrow(/item\.id required/);
        expect(() => upsertItem(initial, { id: null, title: 'x' }, 'id')).toThrow(/item\.id required/);
    });
});

describe('removeItem', () => {
    it('удаляет элемент из items и byId', () => {
        const next = removeItem(initial, 'a', 'id');
        expect(next.items).toEqual([]);
        expect(next.byId).toEqual({});
    });

    it('возвращает тот же state, если элемента нет', () => {
        expect(removeItem(initial, 'zzz', 'id')).toBe(initial);
    });
});

function ctxWith(state: Record<string, unknown>): { ctx: EffectCtx; dispatch: ReturnType<typeof vi.fn> } {
    const dispatch = vi.fn();
    return { ctx: { dispatch, getState: () => state }, dispatch };
}

const opFactory: Parameters<typeof rerunLastRequest>[1] = {
    kind: 'async-op',
    name: 'svc/op',
    sliceKey: 'svc_op',
    events: { REQUESTED: 'svc/op/run_requested' },
};

const resourceFactory: Parameters<typeof reloadLastList>[1] = {
    kind: 'resource-collection',
    name: 'svc/res',
    sliceKey: 'svc_res',
    events: { LIST_REQUESTED: 'svc/res/list_requested' },
};

describe('rerunLastRequest', () => {
    it('повторяет последний payload', () => {
        const { ctx, dispatch } = ctxWith({ svc_op: { lastRequest: { payload: { id: 1 } } } });
        expect(rerunLastRequest(ctx, opFactory)).toBe(true);
        expect(dispatch).toHaveBeenCalledWith('svc/op/run_requested', { id: 1 });
    });

    it('не трогает фабрику, которая не запускалась', () => {
        const { ctx, dispatch } = ctxWith({ svc_op: { lastRequest: null } });
        expect(rerunLastRequest(ctx, opFactory)).toBe(false);
        expect(rerunLastRequest(ctxWith({}).ctx, opFactory)).toBe(false);
        expect(dispatch).not.toHaveBeenCalled();
    });

    it('when отсекает повтор', () => {
        const { ctx, dispatch } = ctxWith({ svc_op: { lastRequest: { payload: { id: 1 } } } });
        expect(rerunLastRequest(ctx, opFactory, { when: () => false })).toBe(false);
        expect(dispatch).not.toHaveBeenCalled();
        expect(rerunLastRequest(ctx, opFactory, { when: (payload) => JSON.stringify(payload) === '{"id":1}' })).toBe(true);
    });

    it('требует async-op', () => {
        expect(() => Reflect.apply(rerunLastRequest, undefined, [ctxWith({}).ctx, resourceFactory])).toThrow(/async-op factory required/);
    });
});

describe('reloadLastList', () => {
    it('повторяет последний запрос списка', () => {
        const { ctx, dispatch } = ctxWith({ svc_res: { lastListQuery: { payload: { limit: 5 } } } });
        expect(reloadLastList(ctx, resourceFactory)).toBe(true);
        expect(dispatch).toHaveBeenCalledWith('svc/res/list_requested', { limit: 5 });
    });

    it('не трогает коллекцию без запроса и уважает when', () => {
        const { ctx, dispatch } = ctxWith({ svc_res: { lastListQuery: { payload: { limit: 5 } } } });
        expect(reloadLastList(ctxWith({}).ctx, resourceFactory)).toBe(false);
        expect(reloadLastList(ctxWith({ svc_res: { lastListQuery: null } }).ctx, resourceFactory)).toBe(false);
        expect(reloadLastList(ctx, resourceFactory, { when: () => false })).toBe(false);
        expect(dispatch).not.toHaveBeenCalled();
    });

    it('требует resource-collection', () => {
        expect(() => Reflect.apply(reloadLastList, undefined, [ctxWith({}).ctx, opFactory])).toThrow(/resource-collection factory required/);
    });
});
