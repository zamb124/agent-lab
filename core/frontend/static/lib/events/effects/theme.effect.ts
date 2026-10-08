/**
 * Эффект темы.
 *
 * Применяет тему к DOM (data-theme на <html>, meta theme-color), persists выбор
 * пользователя в localStorage, слушает изменения системной темы и эмитит события.
 * Если на <html> задан data-platform-theme-lock="dark"|"light", в DOM всегда эта тема
 * (публичные страницы frontend), при этом state/localStorage сохраняют выбор для консоли.
 */

import { CoreEvents } from '../contract.js';
import type { PlatformEvent, EffectCtx } from '../contract.js';import type { ThemeState } from '../reducers/theme.js';
import { platformStorageKey } from '../../utils/storage-keys.js';
import { storageGet, storageSet } from '../../utils/platform-storage.js';

const STORAGE_KEY = platformStorageKey('core', 'theme');

type ThemeMode = 'dark' | 'light';

function _lockedDomThemeMode(): ThemeMode | null {
    const lock = document.documentElement.getAttribute('data-platform-theme-lock');
    if (lock === 'dark' || lock === 'light') {
        return lock;
    }
    return null;
}

function _applyToDom(mode: ThemeMode): void {
    const locked = _lockedDomThemeMode();
    const applied = locked !== null ? locked : mode;
    document.documentElement.setAttribute('data-theme', applied);
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) {
        meta.setAttribute('content', applied === 'dark' ? '#0a0a0c' : '#ffffff');
    }
}

export function syncPlatformThemeDom(mode: string): void {
    if (mode !== 'dark' && mode !== 'light') {
        throw new Error('syncPlatformThemeDom: mode must be dark or light');
    }
    if (typeof document === 'undefined') {
        return;
    }
    _applyToDom(mode);
}

export function createThemeEffect(): (event: PlatformEvent, ctx: EffectCtx<{ theme: ThemeState }>) => Promise<void> {
    let listenerInstalled = false;

    function installSystemListener(ctx: EffectCtx<{ theme: ThemeState }>): void {
        if (listenerInstalled) return;
        listenerInstalled = true;
        const mq = window.matchMedia('(prefers-color-scheme: dark)');
        mq.addEventListener('change', (e) => {
            const mode = e.matches ? 'dark' : 'light';
            ctx.dispatch(CoreEvents.THEME_SYSTEM_CHANGED, { mode }, { source: 'system' });
        });
    }

    return async function themeEffect(event: PlatformEvent, ctx: EffectCtx<{ theme: ThemeState }>): Promise<void> {
        installSystemListener(ctx);

        switch (event.type) {
            case CoreEvents.APP_BOOTSTRAP_STARTED: {
                const stored = storageGet(STORAGE_KEY);
                let mode: ThemeMode;
                let source: 'storage' | 'system';
                if (stored === 'dark' || stored === 'light') {
                    mode = stored;
                    source = 'storage';
                } else {
                    mode = 'dark';
                    source = 'system';
                }
                _applyToDom(mode);
                ctx.dispatch(CoreEvents.THEME_CHANGED, { mode, source }, { causation_id: event.id, source: 'storage' });
                return;
            }

            case CoreEvents.THEME_TOGGLE_REQUESTED: {
                const cur = ctx.getState().theme.mode;
                const next = cur === 'dark' ? 'light' : 'dark';
                _applyToDom(next);
                storageSet(STORAGE_KEY, next);
                ctx.dispatch(CoreEvents.THEME_CHANGED, { mode: next, source: 'user' }, { causation_id: event.id });
                return;
            }

            case CoreEvents.THEME_SET_REQUESTED: {
                const mode = ((event.payload ?? {}) as { mode?: unknown }).mode;
                if (mode !== 'dark' && mode !== 'light') return;
                _applyToDom(mode);
                storageSet(STORAGE_KEY, mode);
                ctx.dispatch(CoreEvents.THEME_CHANGED, { mode, source: 'user' }, { causation_id: event.id });
                return;
            }

            case CoreEvents.THEME_SYSTEM_CHANGED: {
                if (ctx.getState().theme.source !== 'system') return;
                const mode = ((event.payload ?? {}) as { mode?: unknown }).mode;
                if (mode === 'dark' || mode === 'light') {
                    _applyToDom(mode);
                }
                return;
            }

            default:
                return;
        }
    };
}
