/**
 * Слайс icon — кэш загруженных SVG.
 *
 * state.icon:
 *   uiCache:   { [name: string]: string } — UI иконки
 *   fileCache: { [basename: string]: string } — файловые иконки
 *   loading:   { [key: string]: true }
 *   errors:    { [key: string]: string }
 */

import type { PlatformEvent } from '../contract.js';

export interface IconState {
    uiCache: Record<string, string>;
    fileCache: Record<string, string>;
    loading: Record<string, boolean>;
    errors: Record<string, string>;
}

export const ICON_EVENTS = Object.freeze({
    UI_LOAD_REQUESTED:    'icon/ui_asset/load_requested',
    UI_LOADED:            'icon/ui_asset/loaded',
    UI_FAILED:            'icon/ui_asset/failed',
    FILE_LOAD_REQUESTED:  'icon/file_asset/load_requested',
    FILE_LOADED:          'icon/file_asset/loaded',
    FILE_FAILED:          'icon/file_asset/failed',
});

export const initialIconState: IconState = Object.freeze({
    uiCache: {},
    fileCache: {},
    loading: {},
    errors: {},
});

export function iconReducer(state: IconState = initialIconState, event: PlatformEvent): IconState {
    switch (event.type) {
        case ICON_EVENTS.UI_LOAD_REQUESTED: {
            const name = ((event.payload || {}) as { name?: unknown }).name;
            if (typeof name !== 'string' || !name || state.uiCache[name] || state.loading[`ui:${name}`]) return state;
            return { ...state, loading: { ...state.loading, [`ui:${name}`]: true } };
        }
        case ICON_EVENTS.UI_LOADED: {
            const p = (event.payload || {}) as { name?: unknown; svg?: unknown };
            if (typeof p.name !== 'string' || !p.name || typeof p.svg !== 'string') return state;
            const loading = { ...state.loading };
            delete loading[`ui:${p.name}`];
            return { ...state, uiCache: { ...state.uiCache, [p.name]: p.svg }, loading };
        }
        case ICON_EVENTS.UI_FAILED: {
            const p = (event.payload || {}) as { name?: unknown; message?: unknown };
            if (typeof p.name !== 'string' || !p.name) return state;
            const loading = { ...state.loading };
            delete loading[`ui:${p.name}`];
            return { ...state, loading, errors: { ...state.errors, [`ui:${p.name}`]: typeof p.message === 'string' ? p.message : 'failed' } };
        }
        case ICON_EVENTS.FILE_LOAD_REQUESTED: {
            const basename = ((event.payload || {}) as { basename?: unknown }).basename;
            if (typeof basename !== 'string' || !basename || state.fileCache[basename] || state.loading[`file:${basename}`]) return state;
            return { ...state, loading: { ...state.loading, [`file:${basename}`]: true } };
        }
        case ICON_EVENTS.FILE_LOADED: {
            const p = (event.payload || {}) as { basename?: unknown; svg?: unknown };
            if (typeof p.basename !== 'string' || !p.basename || typeof p.svg !== 'string') return state;
            const loading = { ...state.loading };
            delete loading[`file:${p.basename}`];
            return { ...state, fileCache: { ...state.fileCache, [p.basename]: p.svg }, loading };
        }
        case ICON_EVENTS.FILE_FAILED: {
            const p = (event.payload || {}) as { basename?: unknown; message?: unknown };
            if (typeof p.basename !== 'string' || !p.basename) return state;
            const loading = { ...state.loading };
            delete loading[`file:${p.basename}`];
            return { ...state, loading, errors: { ...state.errors, [`file:${p.basename}`]: typeof p.message === 'string' ? p.message : 'failed' } };
        }
        default:
            return state;
    }
}

export const iconSlice = { reducer: iconReducer, initial: initialIconState };
