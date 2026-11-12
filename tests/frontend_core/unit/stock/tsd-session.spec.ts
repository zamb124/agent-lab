/**
 * @vitest-environment node
 *
 * Редьюсер `stock/tsd_session`: применение шага, отказ машины,
 * открытие прогона, очистка и восстановление сессии после
 * перезагрузки терминала (persist-эффект гидратирует контекст).
 */

import { beforeEach, describe, expect, it } from 'vitest';
import type { PlatformEvent } from '@platform/lib/events/contract.js';
import { resetFactories } from '../../helpers/factory-fixtures.js';
import {
    stockTsdSessionSlice,
    type StockTsdSessionState,
} from '../../../../apps/stock/ui/events/resources/stock-tsd.resource.js';

beforeEach(() => {
    resetFactories();
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

const reduce = (state: StockTsdSessionState | undefined, event: PlatformEvent): StockTsdSessionState =>
    stockTsdSessionSlice.reducer(state, event);

const initial = (): StockTsdSessionState => stockTsdSessionSlice.slice.initial as StockTsdSessionState;

const context = (overrides: Record<string, unknown> = {}): Record<string, unknown> => ({
    flow: 'pick',
    step: 'product',
    lines: [],
    ...overrides,
});

describe('stock/tsd_session reducer', () => {
    it('stepApplied хранит код ошибки отдельно от hint', () => {
        const state = reduce(initial(), ev(stockTsdSessionSlice.events.STEP_APPLIED, {
            context: context(),
            resolution: null,
            barcode: 'BC-1',
            error: 'scan_unexpected_step',
            hint: 'expect_commit',
            expected: null,
        }));
        expect(state.outcome).toBe('error');
        expect(state.error).toBe('scan_unexpected_step');
        expect(state.hint).toBe('expect_commit');
    });

    it('stepApplied без ошибки очищает error', () => {
        let state = reduce(initial(), ev(stockTsdSessionSlice.events.STEP_APPLIED, {
            context: context(),
            resolution: null,
            barcode: 'BC-1',
            error: 'scan_entity_mismatch',
            hint: '',
            expected: null,
        }));
        state = reduce(state, ev(stockTsdSessionSlice.events.STEP_APPLIED, {
            context: context({ step: 'quantity' }),
            resolution: null,
            barcode: 'BC-2',
            error: null,
            hint: '',
            expected: null,
        }));
        expect(state.outcome).toBe('ok');
        expect(state.error).toBeNull();
    });

    it('runOpened требует move_id и чистит флаги', () => {
        const state = reduce(initial(), ev(stockTsdSessionSlice.events.RUN_OPENED, {
            context: context(),
            move_id: 'mv-1',
            expected: null,
        }));
        expect(state.move_id).toBe('mv-1');
        expect(state.outcome).toBe('');
        expect(state.error).toBeNull();
        expect(() => reduce(initial(), ev(stockTsdSessionSlice.events.RUN_OPENED, {
            context: context(),
            move_id: '',
        }))).toThrow(/move_id required/);
    });

    it('sessionHydrated восстанавливает контекст и move_id', () => {
        const state = reduce(initial(), ev(stockTsdSessionSlice.events.SESSION_HYDRATED, {
            context: context({ lines: [{ product_id: 'p1', quantity: '2' }] }),
            move_id: 'mv-9',
        }));
        expect(state.context?.step).toBe('product');
        expect(state.move_id).toBe('mv-9');
        expect(state.outcome).toBe('');
        expect(state.expected).toBeNull();
    });

    it('sessionHydrated с пустым контекстом сбрасывает сессию', () => {
        let state = reduce(initial(), ev(stockTsdSessionSlice.events.RUN_OPENED, {
            context: context(),
            move_id: 'mv-1',
            expected: null,
        }));
        state = reduce(state, ev(stockTsdSessionSlice.events.SESSION_HYDRATED, {
            context: null,
            move_id: '',
        }));
        expect(state.context).toBeNull();
        expect(state.move_id).toBe('');
    });

    it('sessionHydrated отклоняет битый payload', () => {
        expect(() => reduce(initial(), ev(stockTsdSessionSlice.events.SESSION_HYDRATED, 'junk')))
            .toThrow(/payload required/);
    });

    it('lineRemoved убирает строку на review без потери сессии', () => {
        const lines = [
            { product_id: 'p1', quantity: '1' },
            { product_id: 'p2', quantity: '2' },
        ];
        let state = reduce(initial(), ev(stockTsdSessionSlice.events.STEP_APPLIED, {
            context: context({ step: 'review', lines }),
            resolution: null,
            barcode: '',
            error: null,
            hint: '',
            expected: null,
        }));
        state = reduce(state, ev(stockTsdSessionSlice.events.LINE_REMOVED, { index: 0 }));
        expect(state.context?.lines).toHaveLength(1);
        expect(state.context?.lines?.[0]?.product_id).toBe('p2');
        expect(state.context?.step).toBe('review');
    });

    it('lineRemoved вне review игнорируется', () => {
        const state = reduce(initial(), ev(stockTsdSessionSlice.events.STEP_APPLIED, {
            context: context({ step: 'product' }),
            resolution: null,
            barcode: '',
            error: null,
            hint: '',
            expected: null,
        }));
        const next = reduce(state, ev(stockTsdSessionSlice.events.LINE_REMOVED, { index: 0 }));
        expect(next.context?.step).toBe('product');
    });
});
