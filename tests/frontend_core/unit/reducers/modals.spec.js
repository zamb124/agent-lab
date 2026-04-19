import { describe, it, expect } from 'vitest';
import { modalsReducer, initialModalsState } from '@platform/lib/events/reducers/modals.js';
import { CoreEvents } from '@platform/lib/events/contract.js';

const ev = (type, payload, ts = 1234) => ({ id: `id_${type}`, type, payload, meta: { ts, source: 'local' } });

describe('modalsReducer', () => {
    it('initial: пустой stack', () => {
        expect(initialModalsState.stack).toEqual([]);
    });

    it('UI_MODAL_OPEN добавляет в stack', () => {
        const next = modalsReducer(initialModalsState, ev(CoreEvents.UI_MODAL_OPEN, { kind: 'frontend.api_key_create', props: { id: 'x' } }));
        expect(next.stack).toHaveLength(1);
        expect(next.stack[0].kind).toBe('frontend.api_key_create');
        expect(next.stack[0].props).toEqual({ id: 'x' });
    });

    it('UI_MODAL_OPEN без kind → no-op', () => {
        expect(modalsReducer(initialModalsState, ev(CoreEvents.UI_MODAL_OPEN, {}))).toBe(initialModalsState);
        expect(modalsReducer(initialModalsState, ev(CoreEvents.UI_MODAL_OPEN, { kind: '' }))).toBe(initialModalsState);
    });

    it('UI_MODAL_CLOSE с id — убирает конкретный', () => {
        let s = modalsReducer(initialModalsState, ev(CoreEvents.UI_MODAL_OPEN, { id: 'm1', kind: 'a.b' }));
        s = modalsReducer(s, ev(CoreEvents.UI_MODAL_OPEN, { id: 'm2', kind: 'a.c' }));
        const next = modalsReducer(s, ev(CoreEvents.UI_MODAL_CLOSE, { id: 'm1' }));
        expect(next.stack.map((m) => m.id)).toEqual(['m2']);
    });

    it('UI_MODAL_CLOSE без id — снимает верхнюю', () => {
        let s = modalsReducer(initialModalsState, ev(CoreEvents.UI_MODAL_OPEN, { kind: 'a.b' }));
        s = modalsReducer(s, ev(CoreEvents.UI_MODAL_OPEN, { kind: 'a.c' }));
        const next = modalsReducer(s, ev(CoreEvents.UI_MODAL_CLOSE, null));
        expect(next.stack).toHaveLength(1);
        expect(next.stack[0].kind).toBe('a.b');
    });

    it('UI_MODAL_CLOSE на пустом — identity', () => {
        const next = modalsReducer(initialModalsState, ev(CoreEvents.UI_MODAL_CLOSE, null));
        expect(next).toBe(initialModalsState);
    });

    it('UI_MODAL_CLOSE с неизвестным id — identity', () => {
        const seeded = modalsReducer(initialModalsState, ev(CoreEvents.UI_MODAL_OPEN, { id: 'm1', kind: 'a.b' }));
        const next = modalsReducer(seeded, ev(CoreEvents.UI_MODAL_CLOSE, { id: 'missing' }));
        expect(next).toBe(seeded);
    });

    it('UI_MODAL_CLOSED ведёт себя как CLOSE', () => {
        const seeded = modalsReducer(initialModalsState, ev(CoreEvents.UI_MODAL_OPEN, { id: 'm1', kind: 'a.b' }));
        const next = modalsReducer(seeded, ev(CoreEvents.UI_MODAL_CLOSED, { id: 'm1' }));
        expect(next.stack).toEqual([]);
    });
});
