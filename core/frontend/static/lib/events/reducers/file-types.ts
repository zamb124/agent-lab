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
import { isPlainRecord, payloadFields } from '../payload.js';

export interface FileTypeEntry extends Record<string, unknown> {
    category: string;
    extension: string;
    mime_types: string[];
}

export interface FileTypesState {
    loaded: boolean;
    categories: string[];
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

function unknownItems(value: unknown, label: string): unknown[] {
    if (!Array.isArray(value)) {
        throw new Error(`file_types/registry/loaded: ${label} must be an array`);
    }
    const items: unknown[] = [];
    for (const item of value) items.push(item);
    return items;
}

function categoryNames(value: unknown): string[] {
    const names: string[] = [];
    for (const item of unknownItems(value, 'categories')) {
        if (typeof item !== 'string' || item.length === 0) {
            throw new Error('file_types/registry/loaded: categories item must be a non-empty string');
        }
        names.push(item);
    }
    return names;
}

function isFileTypeEntry(value: unknown): value is FileTypeEntry {
    if (!isPlainRecord(value)) return false;
    if (typeof value.category !== 'string' || value.category.length === 0) return false;
    if (typeof value.extension !== 'string' || value.extension.length === 0) return false;
    if (!Array.isArray(value.mime_types)) return false;
    for (const mime of value.mime_types) {
        if (typeof mime !== 'string' || mime.length === 0) return false;
    }
    return true;
}

function registryEntries(value: unknown): FileTypeEntry[] {
    const entries: FileTypeEntry[] = [];
    for (const item of unknownItems(value, 'registry')) {
        if (!isFileTypeEntry(item)) {
            throw new Error('file_types/registry/loaded: registry item must be an object');
        }
        entries.push(item);
    }
    return entries;
}

export function fileTypesReducer(state: FileTypesState = initialFileTypesState, event: PlatformEvent): FileTypesState {
    switch (event.type) {
        case FILE_TYPES_EVENTS.LOADED: {
            const p = payloadFields(event);
            return {
                loaded: true,
                categories: categoryNames(p.categories),
                registry: registryEntries(p.registry),
                error: null,
            };
        }
        case FILE_TYPES_EVENTS.LOAD_FAILED:
            const msg = (payloadFields(event)).message;
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
