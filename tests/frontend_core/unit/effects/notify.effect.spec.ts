import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { createNotifyEffect } from '@platform/lib/events/effects/notify.effect.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
import { buildCtx } from '../../helpers/bus-fixtures.js';

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

const ev = (type, payload) => ({ id: `id_${type}`, type, payload, meta: { ts: 0, source: 'local' } });

describe('notifyEffect', () => {
    it('не реагирует на чужие события', async () => {
        const dispatched = [];
        await createNotifyEffect()(ev('foo/bar/baz', null), buildCtx(() => ({ notify: { toasts: [] } }), dispatched));
        expect(dispatched).toHaveLength(0);
    });

    it('после duration шлёт UI_TOAST_DISMISS', async () => {
        const dispatched = [];
        const state = { notify: { toasts: [{ id: 't1' }] } };
        const effect = createNotifyEffect();
        await effect(ev(CoreEvents.UI_TOAST_SHOW, { id: 't1', duration: 100 }), buildCtx(() => state, dispatched));
        expect(dispatched).toHaveLength(0);
        await vi.advanceTimersByTimeAsync(150);
        const dismiss = dispatched.find((d) => d.type === CoreEvents.UI_TOAST_DISMISS);
        expect(dismiss.payload.id).toBe('t1');
    });

    it('duration=0 → no-op', async () => {
        const dispatched = [];
        await createNotifyEffect()(ev(CoreEvents.UI_TOAST_SHOW, { duration: 0 }), buildCtx(() => ({ notify: { toasts: [] } }), dispatched));
        await vi.advanceTimersByTimeAsync(5000);
        expect(dispatched).toHaveLength(0);
    });

    it('без id берёт последний toast из state', async () => {
        const dispatched = [];
        const state = { notify: { toasts: [{ id: 'a' }, { id: 'b' }] } };
        await createNotifyEffect()(ev(CoreEvents.UI_TOAST_SHOW, { duration: 100 }), buildCtx(() => state, dispatched));
        await vi.advanceTimersByTimeAsync(150);
        expect(dispatched.find((d) => d.type === CoreEvents.UI_TOAST_DISMISS).payload.id).toBe('b');
    });
});
