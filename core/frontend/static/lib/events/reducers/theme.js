/**
 * Slice темы.
 *
 * Поля state.theme:
 *   mode:   'dark' | 'light'
 *   source: 'user' | 'system' | 'storage'
 */

import { CoreEvents } from '../contract.js';

export const initialThemeState = Object.freeze({
    mode: 'dark',
    source: 'system',
});

export function themeReducer(state = initialThemeState, event) {
    switch (event.type) {
        case CoreEvents.THEME_CHANGED: {
            const mode = event.payload && event.payload.mode;
            const source = (event.payload && event.payload.source) || 'user';
            if (mode !== 'dark' && mode !== 'light') return state;
            if (state.mode === mode && state.source === source) return state;
            return { mode, source };
        }
        case CoreEvents.THEME_SYSTEM_CHANGED: {
            if (state.source !== 'system') return state;
            const mode = event.payload && event.payload.mode;
            if (mode !== 'dark' && mode !== 'light') return state;
            if (state.mode === mode) return state;
            return { ...state, mode };
        }
        default:
            return state;
    }
}
