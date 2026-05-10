/**
 * Theme effect.
 *
 * Применяет тему к DOM (data-theme на <html>, meta theme-color), persists выбор
 * пользователя в localStorage, слушает изменения системной темы и эмитит события.
 * Если на <html> задан data-platform-theme-lock="dark"|"light", в DOM всегда эта тема
 * (публичные страницы frontend), при этом state/localStorage сохраняют выбор для консоли.
 */

import { CoreEvents } from '../contract.js';

const STORAGE_KEY = 'platform_theme';

/** @returns {'dark' | 'light' | null} */
function _lockedDomThemeMode() {
    const lock = document.documentElement.getAttribute('data-platform-theme-lock');
    if (lock === 'dark' || lock === 'light') {
        return lock;
    }
    return null;
}

function _applyToDom(mode) {
    const locked = _lockedDomThemeMode();
    const applied = locked !== null ? locked : mode;
    document.documentElement.setAttribute('data-theme', applied);
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) {
        meta.setAttribute('content', applied === 'dark' ? '#0a0a0c' : '#ffffff');
    }
}

/**
 * Повторно применить тему к document с учётом data-platform-theme-lock (маршрут публичного фронта).
 *
 * @param {'dark' | 'light'} mode — текущий mode из state.theme (без lock снимет выбранную тему).
 */
export function syncPlatformThemeDom(mode) {
    if (mode !== 'dark' && mode !== 'light') {
        throw new Error('syncPlatformThemeDom: mode must be dark or light');
    }
    if (typeof document === 'undefined') {
        return;
    }
    _applyToDom(mode);
}

export function createThemeEffect() {
    let listenerInstalled = false;

    function installSystemListener(ctx) {
        if (listenerInstalled) return;
        listenerInstalled = true;
        const mq = window.matchMedia('(prefers-color-scheme: dark)');
        mq.addEventListener('change', (e) => {
            const mode = e.matches ? 'dark' : 'light';
            ctx.dispatch(CoreEvents.THEME_SYSTEM_CHANGED, { mode }, { source: 'system' });
        });
    }

    return async function themeEffect(event, ctx) {
        installSystemListener(ctx);

        switch (event.type) {
            case CoreEvents.APP_BOOTSTRAP_STARTED: {
                const stored = localStorage.getItem(STORAGE_KEY);
                let mode;
                let source;
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
                localStorage.setItem(STORAGE_KEY, next);
                ctx.dispatch(CoreEvents.THEME_CHANGED, { mode: next, source: 'user' }, { causation_id: event.id });
                return;
            }

            case CoreEvents.THEME_SET_REQUESTED: {
                const mode = event.payload && event.payload.mode;
                if (mode !== 'dark' && mode !== 'light') return;
                _applyToDom(mode);
                localStorage.setItem(STORAGE_KEY, mode);
                ctx.dispatch(CoreEvents.THEME_CHANGED, { mode, source: 'user' }, { causation_id: event.id });
                return;
            }

            case CoreEvents.THEME_SYSTEM_CHANGED: {
                if (ctx.getState().theme.source !== 'system') return;
                const mode = event.payload && event.payload.mode;
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
