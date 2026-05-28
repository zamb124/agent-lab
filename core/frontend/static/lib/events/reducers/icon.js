/**
 * Слайс icon — кэш загруженных SVG.
 *
 * state.icon:
 *   uiCache:   { [name: string]: string } — UI иконки
 *   fileCache: { [basename: string]: string } — файловые иконки
 *   loading:   { [key: string]: true }
 *   errors:    { [key: string]: string }
 */

export const ICON_EVENTS = Object.freeze({
    UI_LOAD_REQUESTED:    'icon/ui_asset/load_requested',
    UI_LOADED:            'icon/ui_asset/loaded',
    UI_FAILED:            'icon/ui_asset/failed',
    FILE_LOAD_REQUESTED:  'icon/file_asset/load_requested',
    FILE_LOADED:          'icon/file_asset/loaded',
    FILE_FAILED:          'icon/file_asset/failed',
});

export const initialIconState = Object.freeze({
    uiCache: {},
    fileCache: {},
    loading: {},
    errors: {},
});

export function iconReducer(state = initialIconState, event) {
    switch (event.type) {
        case ICON_EVENTS.UI_LOAD_REQUESTED: {
            const name = event.payload && event.payload.name;
            if (!name || state.uiCache[name] || state.loading[`ui:${name}`]) return state;
            return { ...state, loading: { ...state.loading, [`ui:${name}`]: true } };
        }
        case ICON_EVENTS.UI_LOADED: {
            const { name, svg } = event.payload || {};
            if (!name || typeof svg !== 'string') return state;
            const loading = { ...state.loading };
            delete loading[`ui:${name}`];
            return { ...state, uiCache: { ...state.uiCache, [name]: svg }, loading };
        }
        case ICON_EVENTS.UI_FAILED: {
            const { name, message } = event.payload || {};
            if (!name) return state;
            const loading = { ...state.loading };
            delete loading[`ui:${name}`];
            return { ...state, loading, errors: { ...state.errors, [`ui:${name}`]: message || 'failed' } };
        }
        case ICON_EVENTS.FILE_LOAD_REQUESTED: {
            const basename = event.payload && event.payload.basename;
            if (!basename || state.fileCache[basename] || state.loading[`file:${basename}`]) return state;
            return { ...state, loading: { ...state.loading, [`file:${basename}`]: true } };
        }
        case ICON_EVENTS.FILE_LOADED: {
            const { basename, svg } = event.payload || {};
            if (!basename || typeof svg !== 'string') return state;
            const loading = { ...state.loading };
            delete loading[`file:${basename}`];
            return { ...state, fileCache: { ...state.fileCache, [basename]: svg }, loading };
        }
        case ICON_EVENTS.FILE_FAILED: {
            const { basename, message } = event.payload || {};
            if (!basename) return state;
            const loading = { ...state.loading };
            delete loading[`file:${basename}`];
            return { ...state, loading, errors: { ...state.errors, [`file:${basename}`]: message || 'failed' } };
        }
        default:
            return state;
    }
}

export const iconSlice = { reducer: iconReducer, initial: initialIconState };
