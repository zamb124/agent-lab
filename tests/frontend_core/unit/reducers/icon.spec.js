import { describe, it, expect } from 'vitest';
import { iconReducer, initialIconState, ICON_EVENTS, iconSlice } from '@platform/lib/events/reducers/icon.js';

const ev = (type, payload = null) => ({ id: `id_${type}`, type, payload, meta: { ts: 0, source: 'local' } });

describe('iconReducer', () => {
    it('initial: пустые caches', () => {
        expect(initialIconState.uiCache).toEqual({});
        expect(initialIconState.fileCache).toEqual({});
        expect(iconSlice.initial).toBe(initialIconState);
    });

    it('UI_LOAD_REQUESTED → loading[ui:name]=true', () => {
        const next = iconReducer(initialIconState, ev(ICON_EVENTS.UI_LOAD_REQUESTED, { name: 'plus' }));
        expect(next.loading['ui:plus']).toBe(true);
    });

    it('UI_LOAD_REQUESTED повторно для уже кешированного — no-op', () => {
        const seeded = iconReducer(initialIconState, ev(ICON_EVENTS.UI_LOADED, { name: 'plus', svg: '<svg/>' }));
        const next = iconReducer(seeded, ev(ICON_EVENTS.UI_LOAD_REQUESTED, { name: 'plus' }));
        expect(next).toBe(seeded);
    });

    it('UI_LOADED помещает svg в uiCache', () => {
        const next = iconReducer(initialIconState, ev(ICON_EVENTS.UI_LOADED, { name: 'plus', svg: '<svg/>' }));
        expect(next.uiCache.plus).toBe('<svg/>');
        expect(next.loading['ui:plus']).toBeUndefined();
    });

    it('UI_FAILED фиксирует error', () => {
        const next = iconReducer(initialIconState, ev(ICON_EVENTS.UI_FAILED, { name: 'x', message: 'no svg' }));
        expect(next.errors['ui:x']).toBe('no svg');
    });

    it('FILE_LOAD_REQUESTED + LOADED', () => {
        let s = iconReducer(initialIconState, ev(ICON_EVENTS.FILE_LOAD_REQUESTED, { basename: 'pdf' }));
        expect(s.loading['file:pdf']).toBe(true);
        s = iconReducer(s, ev(ICON_EVENTS.FILE_LOADED, { basename: 'pdf', svg: '<svg/>' }));
        expect(s.fileCache.pdf).toBe('<svg/>');
        expect(s.loading['file:pdf']).toBeUndefined();
    });

    it('FILE_LOAD_REQUESTED без basename — no-op', () => {
        const next = iconReducer(initialIconState, ev(ICON_EVENTS.FILE_LOAD_REQUESTED, {}));
        expect(next).toBe(initialIconState);
    });
});
