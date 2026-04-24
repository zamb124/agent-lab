/**
 * Theme effect.
 *
 * Применяет тему к DOM (data-theme на <html>, meta theme-color), persists выбор
 * пользователя в localStorage, слушает изменения системной темы и эмитит события.
 */

import { CoreEvents } from '../contract.js';

const STORAGE_KEY = 'platform_theme';

function _applyToDom(mode) {
    document.documentElement.setAttribute('data-theme', mode);
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) {
        meta.setAttribute('content', mode === 'dark' ? '#0a0a0c' : '#ffffff');
    }
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
