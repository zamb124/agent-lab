import { describe, it, expect } from 'vitest';
import { themeReducer, initialThemeState } from '@platform/lib/events/reducers/theme.js';
import { CoreEvents } from '@platform/lib/events/contract.js';

const ev = (type, payload = null) => ({ id: `id_${type}`, type, payload, meta: { ts: 0, source: 'local' } });

describe('themeReducer', () => {
    it('initial: dark/system', () => {
        expect(initialThemeState).toEqual({ mode: 'dark', source: 'system' });
        expect(Object.isFrozen(initialThemeState)).toBe(true);
    });

    it('THEME_CHANGED меняет mode + source (default user)', () => {
        const next = themeReducer(initialThemeState, ev(CoreEvents.THEME_CHANGED, { mode: 'light' }));
        expect(next).toEqual({ mode: 'light', source: 'user' });
    });

    it('THEME_CHANGED с явным source', () => {
        const next = themeReducer(initialThemeState, ev(CoreEvents.THEME_CHANGED, { mode: 'light', source: 'storage' }));
        expect(next.source).toBe('storage');
    });

    it('THEME_CHANGED неизвестный mode — no-op', () => {
        const next = themeReducer(initialThemeState, ev(CoreEvents.THEME_CHANGED, { mode: 'bright' }));
        expect(next).toBe(initialThemeState);
    });

    it('THEME_SYSTEM_CHANGED меняет mode только если source=system', () => {
        const next = themeReducer(initialThemeState, ev(CoreEvents.THEME_SYSTEM_CHANGED, { mode: 'light' }));
        expect(next.mode).toBe('light');
        const userMode = { mode: 'dark', source: 'user' };
        expect(themeReducer(userMode, ev(CoreEvents.THEME_SYSTEM_CHANGED, { mode: 'light' }))).toBe(userMode);
    });

    it('тот же mode + source → identity', () => {
        const next = themeReducer(initialThemeState, ev(CoreEvents.THEME_CHANGED, { mode: 'dark', source: 'system' }));
        expect(next).toBe(initialThemeState);
    });
});
