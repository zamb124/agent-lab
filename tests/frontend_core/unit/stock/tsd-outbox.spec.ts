/**
 * @vitest-environment node
 *
 * Редьюсер и хелперы `stock/tsd_outbox`: постановка, доставка, попытки,
 * сброс, гидратация и фиксация ключа идемпотентности до первой отправки.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { PlatformEvent } from '@platform/lib/events/contract.js';
import { resetFactories } from '../../helpers/factory-fixtures.js';
import {
    stockTsdOutboxSlice,
    tsdOutboxItem,
    TSD_OUTBOX_LIMIT,
    type StockTsdOutboxState,
    type TsdOutboxItem,
} from '../../../../apps/stock/ui/events/resources/stock-tsd.resource.js';

beforeEach(() => {
    resetFactories();
});
afterEach(() => {
    vi.restoreAllMocks();
});

const ev = (type: string | undefined, payload: unknown, id = 't1'): PlatformEvent => {
    if (type === undefined) throw new Error('ev: event type required');
    return {
        id,
        type,
        payload,
        meta: { ts: 0, source: 'local', causation_id: null, correlation_id: null, trace_id: null },
    };
};

const reduce = (state: StockTsdOutboxState | undefined, event: PlatformEvent): StockTsdOutboxState =>
    stockTsdOutboxSlice.reducer(state, event);

const initial = (): StockTsdOutboxState => stockTsdOutboxSlice.slice.initial as StockTsdOutboxState;

const enqueue = (state: StockTsdOutboxState, item: TsdOutboxItem): StockTsdOutboxState =>
    reduce(state, ev(stockTsdOutboxSlice.events.ENQUEUED, item));

function makeItem(overrides: Partial<TsdOutboxItem> = {}): TsdOutboxItem {
    return {
        outbox_id: 'obx-1',
        op: 'stock/scan_commit',
        payload: { move_id: 'm1', context: {}, idempotency_key: 'idem-1' },
        enqueued_at: '2026-08-01T12:00:00Z',
        attempts: 0,
        last_error: '',
        ...overrides,
    };
}

describe('tsdOutboxItem', () => {
    it('фиксирует idempotency_key до первой попытки отправки', () => {
        const item = tsdOutboxItem('stock/scan_commit', { move_id: 'm1', context: {} });
        expect(typeof item.payload.idempotency_key).toBe('string');
        expect(String(item.payload.idempotency_key).length).toBeGreaterThan(0);
    });

    it('не перетирает готовый idempotency_key', () => {
        const item = tsdOutboxItem('stock/scan_commit', { idempotency_key: 'idem-fixed' });
        expect(item.payload.idempotency_key).toBe('idem-fixed');
    });

    it('два вызова дают разные outbox_id', () => {
        const a = tsdOutboxItem('stock/scan_commit', {});
        const b = tsdOutboxItem('stock/scan_commit', {});
        expect(a.outbox_id).not.toBe(b.outbox_id);
    });
});

describe('stock/tsd_outbox reducer', () => {
    it('enqueued добавляет легальную команду', () => {
        const state = enqueue(initial(), makeItem());
        expect(state.items).toHaveLength(1);
        expect(state.items[0]?.op).toBe('stock/scan_commit');
    });

    it('enqueued принимает все queueable op из TSD_OUTBOX_OPS', () => {
        let state = initial();
        const ops = [
            'stock/scan_commit',
            'stock/scan_count_commit',
            'stock/scan_adhoc_commit',
            'stock/move_lines_exception',
            'stock/container_move',
        ];
        ops.forEach((op, i) => {
            state = enqueue(state, makeItem({ outbox_id: `obx-${i}`, op }));
        });
        expect(state.items).toHaveLength(ops.length);
    });

    it('enqueued отклоняет команду вне whitelist', () => {
        expect(() => enqueue(initial(), makeItem({ op: 'stock/products_create' }))).toThrow(/op not queueable/);
    });

    it('enqueued отклоняет запись без outbox_id и payload', () => {
        expect(() => enqueue(initial(), makeItem({ outbox_id: '' }))).toThrow(/outbox_id required/);
        const bad = { ...makeItem(), payload: null };
        expect(() => reduce(initial(), ev(stockTsdOutboxSlice.events.ENQUEUED, bad))).toThrow(/payload required/);
    });

    it('enqueued отклоняет переполнение очереди', () => {
        let state = initial();
        for (let i = 0; i < TSD_OUTBOX_LIMIT; i += 1) {
            state = enqueue(state, makeItem({ outbox_id: `obx-${i}` }));
        }
        expect(() => enqueue(state, makeItem({ outbox_id: 'overflow' }))).toThrow(/queue full/);
    });

    it('delivered снимает элемент по outbox_id', () => {
        let state = enqueue(initial(), makeItem({ outbox_id: 'a' }));
        state = enqueue(state, makeItem({ outbox_id: 'b' }));
        state = reduce(state, ev(stockTsdOutboxSlice.events.DELIVERED, 'a'));
        expect(state.items.map((i) => i.outbox_id)).toEqual(['b']);
    });

    it('dropped снимает элемент по outbox_id', () => {
        let state = enqueue(initial(), makeItem({ outbox_id: 'a' }));
        state = reduce(state, ev(stockTsdOutboxSlice.events.DROPPED, 'a'));
        expect(state.items).toHaveLength(0);
    });

    it('attemptFailed инкрементирует attempts и пишет last_error', () => {
        let state = enqueue(initial(), makeItem({ outbox_id: 'a' }));
        state = reduce(state, ev(stockTsdOutboxSlice.events.ATTEMPT_FAILED, { outbox_id: 'a', error: 'ws_timeout' }));
        state = reduce(state, ev(stockTsdOutboxSlice.events.ATTEMPT_FAILED, { outbox_id: 'a', error: 'conflict' }));
        const item = state.items[0];
        expect(item?.attempts).toBe(2);
        expect(item?.last_error).toBe('conflict');
    });

    it('hydrated фильтрует битые записи и режет до лимита', () => {
        const items = [
            makeItem({ outbox_id: 'ok' }),
            { outbox_id: 'no-op' },
            { outbox_id: 'bad-op', op: 'stock/products_create', payload: {} },
            { outbox_id: 'no-payload', op: 'stock/scan_commit' },
        ];
        const state = reduce(initial(), ev(stockTsdOutboxSlice.events.HYDRATED, { items }));
        expect(state.items.map((i) => i.outbox_id)).toEqual(['ok']);
    });
});
