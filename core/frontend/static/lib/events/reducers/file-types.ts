/**
 * Слайс fileTypes — реестр типов файлов платформы.
 *
 * state.fileTypes:
 *   loaded:     boolean
 *   categories: string[]
 *   registry:   Array<{ extension, mime_types, category }>
 *   error:      string|null
 */

import type { PlatformEvent } from '../contract.js';

export interface FileTypeEntry extends Record<string, unknown> {
    category: string;
    extension: string;
    mime_types: string[];
}

export interface FileTypesState {
    loaded: boolean;
    categories: Record<string, unknown>[];
    registry: FileTypeEntry[];
    error: string | null;
}

type StateWithFileTypes = { fileTypes: FileTypesState };

export const FILE_TYPES_EVENTS = Object.freeze({
    LOAD_REQUESTED: 'file_types/registry/load_requested',
    LOADED:         'file_types/registry/loaded',
    LOAD_FAILED:    'file_types/registry/load_failed',
});

export const initialFileTypesState: FileTypesState = Object.freeze({
    loaded: false,
    categories: [],
    registry: [],
    error: null,
});

export function fileTypesReducer(state: FileTypesState = initialFileTypesState, event: PlatformEvent): FileTypesState {
    switch (event.type) {
        case FILE_TYPES_EVENTS.LOADED: {
            const p = (event.payload || {}) as { categories?: unknown; registry?: unknown };
            return {
                loaded: true,
                categories: Array.isArray(p.categories) ? p.categories as Record<string, unknown>[] : [],
                registry: Array.isArray(p.registry) ? p.registry as FileTypeEntry[] : [],
                error: null,
            };
        }
        case FILE_TYPES_EVENTS.LOAD_FAILED:
            const msg = ((event.payload || {}) as { message?: unknown }).message;
            return { ...state, error: typeof msg === 'string' && msg ? msg : 'failed' };
        default:
            return state;
    }
}

export const fileTypesSlice = { reducer: fileTypesReducer, initial: initialFileTypesState };

/** Pure helpers поверх fileTypes state. */
export function selectExtensionsFor(state: StateWithFileTypes, ...categories: string[]): string[] {
    const cats = new Set(categories);
    return state.fileTypes.registry.filter((e) => cats.has(e.category)).map((e) => e.extension);
}

export function selectMimesFor(state: StateWithFileTypes, ...categories: string[]): string[] {
    const cats = new Set(categories);
    const result = new Set<string>();
    for (const entry of state.fileTypes.registry) {
        if (cats.has(entry.category)) {
            for (const m of entry.mime_types) result.add(m);
        }
    }
    return [...result];
}

export function selectAcceptStringFor(state: StateWithFileTypes, ...categories: string[]): string {
    const cats = new Set(categories);
    const exts = selectExtensionsFor(state, ...categories).sort();
    const wildcards: string[] = [];
    if (cats.has('image')) wildcards.push('image/*');
    if (cats.has('audio')) wildcards.push('audio/*');
    if (cats.has('video')) wildcards.push('video/*');
    return [...wildcards, ...exts].join(',');
}

export function selectIsAllowedFile(state: StateWithFileTypes, file: { type: string; name: string }, ...categories: string[]): boolean {
    const allowedMimes = new Set(selectMimesFor(state, ...categories));
    const allowedExts = new Set(selectExtensionsFor(state, ...categories).map((e) => e.replace(/^\./, '')));
    if (allowedMimes.has(file.type)) return true;
    const ext = file.name.includes('.') ? file.name.slice(file.name.lastIndexOf('.') + 1).toLowerCase() : '';
    return allowedExts.has(ext);
}
