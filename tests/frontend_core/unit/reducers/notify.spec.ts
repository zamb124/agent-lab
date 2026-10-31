import { describe, it, expect } from 'vitest';
import { notifyReducer, initialNotifyState } from '@platform/lib/events/reducers/notify.js';
import { CoreEvents } from '@platform/lib/events/contract.js';

const ev = (type, payload, ts = 1234) => ({ id: `id_${type}`, type, payload, meta: { ts, source: 'local' } });

describe('notifyReducer', () => {
    it('initial: пустой список', () => {
        expect(initialNotifyState.toasts).toEqual([]);
    });

    it('UI_TOAST_SHOW добавляет toast (с message)', () => {
        const next = notifyReducer(initialNotifyState, ev(CoreEvents.UI_TOAST_SHOW, { message: 'hi', type: 'success' }, 555));
        expect(next.toasts).toHaveLength(1);
        expect(next.toasts[0]).toMatchObject({ message: 'hi', type: 'success', ts: 555, duration: 3000 });
        expect(next.toasts[0].id).toMatch(/^toast_/);
    });

    it('UI_TOAST_SHOW c i18n_key', () => {
        const next = notifyReducer(initialNotifyState, ev(CoreEvents.UI_TOAST_SHOW, { i18n_key: 'svc:ok' }));
        expect(next.toasts[0].i18n_key).toBe('svc:ok');
        expect(next.toasts[0].type).toBe('info'); // default
    });

    it('UI_TOAST_SHOW без message и без i18n_key → no-op', () => {
        const next = notifyReducer(initialNotifyState, ev(CoreEvents.UI_TOAST_SHOW, {}));
        expect(next).toBe(initialNotifyState);
    });

    it('UI_TOAST_DISMISS убирает по id', () => {
        let state = notifyReducer(initialNotifyState, ev(CoreEvents.UI_TOAST_SHOW, { id: 't1', message: 'a' }));
        state = notifyReducer(state, ev(CoreEvents.UI_TOAST_SHOW, { id: 't2', message: 'b' }));
        const next = notifyReducer(state, ev(CoreEvents.UI_TOAST_DISMISS, { id: 't1' }));
        expect(next.toasts.map((t) => t.id)).toEqual(['t2']);
    });

    it('UI_TOAST_DISMISS неизвестный id → identity', () => {
        const seeded = notifyReducer(initialNotifyState, ev(CoreEvents.UI_TOAST_SHOW, { id: 't1', message: 'a' }));
        const next = notifyReducer(seeded, ev(CoreEvents.UI_TOAST_DISMISS, { id: 'missing' }));
        expect(next).toBe(seeded);
    });

    it('UI_TOAST_CLEAR чистит всё', () => {
        const seeded = notifyReducer(initialNotifyState, ev(CoreEvents.UI_TOAST_SHOW, { message: 'a' }));
        const next = notifyReducer(seeded, ev(CoreEvents.UI_TOAST_CLEAR, null));
        expect(next.toasts).toEqual([]);
    });

    it('UI_TOAST_CLEAR на пустом — identity', () => {
        const next = notifyReducer(initialNotifyState, ev(CoreEvents.UI_TOAST_CLEAR, null));
        expect(next).toBe(initialNotifyState);
    });
});
