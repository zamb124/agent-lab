import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { createThemeEffect, syncPlatformThemeDom } from '@platform/lib/events/effects/theme.effect.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
import { installDomShim } from '../../helpers/dom-shim.js';
import { installFakeStorage } from '../../helpers/fake-storage.js';
import { buildCtx } from '../../helpers/bus-fixtures.js';

let dom;
let storage;

beforeEach(() => {
    dom = installDomShim();
    storage = installFakeStorage();
});
afterEach(() => {
    storage.uninstall();
    dom.uninstall();
});

const ev = (type, payload = null) => ({ id: `id_${type}`, type, payload, meta: { ts: 0, source: 'system' } });

describe('themeEffect: bootstrap', () => {
    it('из storage применяет mode и эмитит THEME_CHANGED', async () => {
        storage.localStorage.setItem('platform_theme', 'light');
        const effect = createThemeEffect();
        const dispatched = [];
        await effect(ev(CoreEvents.APP_BOOTSTRAP_STARTED), buildCtx(() => ({ theme: { mode: 'dark', source: 'system' } }), dispatched));
        expect(dom.documentElement.getAttribute('data-theme')).toBe('light');
        const changed = dispatched.find((d) => d.type === CoreEvents.THEME_CHANGED);
        expect(changed.payload).toEqual({ mode: 'light', source: 'storage' });
    });

    it('data-platform-theme-lock=dark: DOM тёмный, state из storage светлый', async () => {
        storage.localStorage.setItem('platform_theme', 'light');
        dom.documentElement.setAttribute('data-platform-theme-lock', 'dark');
        const effect = createThemeEffect();
        const dispatched = [];
        await effect(ev(CoreEvents.APP_BOOTSTRAP_STARTED), buildCtx(() => ({ theme: { mode: 'dark', source: 'system' } }), dispatched));
        expect(dom.documentElement.getAttribute('data-theme')).toBe('dark');
        const changed = dispatched.find((d) => d.type === CoreEvents.THEME_CHANGED);
        expect(changed.payload).toEqual({ mode: 'light', source: 'storage' });
    });

    it('без storage — тёмная тема (не из системы)', async () => {
        dom.uninstall();
        dom = installDomShim({ systemDark: false });
        const effect = createThemeEffect();
        const dispatched = [];
        await effect(ev(CoreEvents.APP_BOOTSTRAP_STARTED), buildCtx(() => ({ theme: { mode: 'dark', source: 'system' } }), dispatched));
        expect(dom.documentElement.getAttribute('data-theme')).toBe('dark');
        const changed = dispatched.find((d) => d.type === CoreEvents.THEME_CHANGED);
        expect(changed.payload).toEqual({ mode: 'dark', source: 'system' });
    });
});

describe('themeEffect: SET_REQUESTED', () => {
    it('сохраняет в storage и применяет к DOM', async () => {
        const effect = createThemeEffect();
        const dispatched = [];
        await effect(ev(CoreEvents.THEME_SET_REQUESTED, { mode: 'light' }), buildCtx(() => ({ theme: { mode: 'dark', source: 'system' } }), dispatched));
        expect(storage.localStorage.getItem('platform_theme')).toBe('light');
        expect(dom.documentElement.getAttribute('data-theme')).toBe('light');
        const changed = dispatched.find((d) => d.type === CoreEvents.THEME_CHANGED);
        expect(changed.payload).toEqual({ mode: 'light', source: 'user' });
    });

    it('при lock dark в DOM остаётся dark', async () => {
        dom.documentElement.setAttribute('data-platform-theme-lock', 'dark');
        const effect = createThemeEffect();
        const dispatched = [];
        await effect(ev(CoreEvents.THEME_SET_REQUESTED, { mode: 'light' }), buildCtx(() => ({ theme: { mode: 'dark', source: 'system' } }), dispatched));
        expect(storage.localStorage.getItem('platform_theme')).toBe('light');
        expect(dom.documentElement.getAttribute('data-theme')).toBe('dark');
        expect(dom.themeColorMeta.getAttribute('content')).toBe('#0a0a0c');
    });

    it('невалидный mode → no-op', async () => {
        const effect = createThemeEffect();
        const dispatched = [];
        await effect(ev(CoreEvents.THEME_SET_REQUESTED, { mode: 'cosmic' }), buildCtx(() => ({ theme: { mode: 'dark', source: 'system' } }), dispatched));
        expect(dispatched).toHaveLength(0);
    });
});

describe('themeEffect: TOGGLE_REQUESTED', () => {
    it('меняет на противоположный', async () => {
        const effect = createThemeEffect();
        const dispatched = [];
        await effect(ev(CoreEvents.THEME_TOGGLE_REQUESTED), buildCtx(() => ({ theme: { mode: 'dark', source: 'user' } }), dispatched));
        const changed = dispatched.find((d) => d.type === CoreEvents.THEME_CHANGED);
        expect(changed.payload).toEqual({ mode: 'light', source: 'user' });
    });
});

describe('themeEffect: SYSTEM_CHANGED', () => {
    it('применяется только при source=system', async () => {
        const effect = createThemeEffect();
        await effect(ev(CoreEvents.THEME_SYSTEM_CHANGED, { mode: 'light' }), buildCtx(() => ({ theme: { mode: 'dark', source: 'system' } }), []));
        expect(dom.documentElement.getAttribute('data-theme')).toBe('light');
    });

    it('lock dark удерживает DOM dark при system light', async () => {
        dom.documentElement.setAttribute('data-platform-theme-lock', 'dark');
        const effect = createThemeEffect();
        await effect(ev(CoreEvents.THEME_SYSTEM_CHANGED, { mode: 'light' }), buildCtx(() => ({ theme: { mode: 'dark', source: 'system' } }), []));
        expect(dom.documentElement.getAttribute('data-theme')).toBe('dark');
    });

    it('игнорируется если source=user', async () => {
        const effect = createThemeEffect();
        await effect(ev(CoreEvents.THEME_SYSTEM_CHANGED, { mode: 'light' }), buildCtx(() => ({ theme: { mode: 'dark', source: 'user' } }), []));
        expect(dom.documentElement.getAttribute('data-theme')).toBeNull();
    });
});

describe('syncPlatformThemeDom', () => {
    it('учитывает data-platform-theme-lock', () => {
        dom.documentElement.setAttribute('data-platform-theme-lock', 'dark');
        syncPlatformThemeDom('light');
        expect(dom.documentElement.getAttribute('data-theme')).toBe('dark');
    });

    it('без lock применяет переданный mode', () => {
        syncPlatformThemeDom('light');
        expect(dom.documentElement.getAttribute('data-theme')).toBe('light');
    });
});
