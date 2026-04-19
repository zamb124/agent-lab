/**
 * FileTypes slice — реестр типов файлов платформы.
 *
 * state.fileTypes:
 *   loaded:     boolean
 *   categories: string[]
 *   registry:   Array<{ extension, mime_types, category }>
 *   error:      string|null
 */

export const FILE_TYPES_EVENTS = Object.freeze({
    LOAD_REQUESTED: 'file_types/registry/load_requested',
    LOADED:         'file_types/registry/loaded',
    LOAD_FAILED:    'file_types/registry/load_failed',
});

export const initialFileTypesState = Object.freeze({
    loaded: false,
    categories: [],
    registry: [],
    error: null,
});

export function fileTypesReducer(state = initialFileTypesState, event) {
    switch (event.type) {
        case FILE_TYPES_EVENTS.LOADED: {
            const p = event.payload || {};
            return {
                loaded: true,
                categories: Array.isArray(p.categories) ? p.categories : [],
                registry: Array.isArray(p.registry) ? p.registry : [],
                error: null,
            };
        }
        case FILE_TYPES_EVENTS.LOAD_FAILED:
            return { ...state, error: (event.payload && event.payload.message) || 'failed' };
        default:
            return state;
    }
}

export const fileTypesSlice = { reducer: fileTypesReducer, initial: initialFileTypesState };

/** Pure helpers поверх fileTypes state. */
export function selectExtensionsFor(state, ...categories) {
    const cats = new Set(categories);
    return state.fileTypes.registry.filter((e) => cats.has(e.category)).map((e) => e.extension);
}

export function selectMimesFor(state, ...categories) {
    const cats = new Set(categories);
    const result = new Set();
    for (const entry of state.fileTypes.registry) {
        if (cats.has(entry.category)) {
            for (const m of entry.mime_types) result.add(m);
        }
    }
    return [...result];
}

export function selectAcceptStringFor(state, ...categories) {
    const cats = new Set(categories);
    const exts = selectExtensionsFor(state, ...categories).sort();
    const wildcards = [];
    if (cats.has('image')) wildcards.push('image/*');
    if (cats.has('audio')) wildcards.push('audio/*');
    if (cats.has('video')) wildcards.push('video/*');
    return [...wildcards, ...exts].join(',');
}

export function selectIsAllowedFile(state, file, ...categories) {
    const allowedMimes = new Set(selectMimesFor(state, ...categories));
    const allowedExts = new Set(selectExtensionsFor(state, ...categories).map((e) => e.replace(/^\./, '')));
    if (allowedMimes.has(file.type)) return true;
    const ext = file.name.includes('.') ? file.name.slice(file.name.lastIndexOf('.') + 1).toLowerCase() : '';
    return allowedExts.has(ext);
}
