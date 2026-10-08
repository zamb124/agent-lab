/**
 * Слайс темы.
 *
 * Поля state.theme:
 *   mode:   'dark' | 'light'
 *   source: 'user' | 'system' | 'storage'
 */

import { CoreEvents } from '../contract.js';
import type { PlatformEvent } from '../contract.js';

export interface ThemeState {
    mode: 'dark' | 'light';
    source: 'user' | 'system' | 'storage';
}

export const initialThemeState: ThemeState = Object.freeze({
    mode: 'dark',
    source: 'system',
});

export function themeReducer(state: ThemeState = initialThemeState, event: PlatformEvent): ThemeState {
    switch (event.type) {
        case CoreEvents.THEME_CHANGED: {
            const p = (event.payload || {}) as { mode?: unknown; source?: unknown };
            const mode = p.mode;
            const source = p.source === 'user' || p.source === 'system' || p.source === 'storage' ? p.source : 'user';
            if (mode !== 'dark' && mode !== 'light') return state;
            if (state.mode === mode && state.source === source) return state;
            return { mode, source };
        }
        case CoreEvents.THEME_SYSTEM_CHANGED: {
            if (state.source !== 'system') return state;
            const p = (event.payload || {}) as { mode?: unknown };
            const mode = p.mode;
            if (mode !== 'dark' && mode !== 'light') return state;
            if (state.mode === mode) return state;
            return { ...state, mode };
        }
        default:
            return state;
    }
}
