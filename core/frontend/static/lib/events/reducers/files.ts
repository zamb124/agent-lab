/**
 * Слайс files — мета-инфо загруженных файлов и upload-операций.
 *
 * state.files:
 *   byId:    { [fileId]: object }
 *   uploads: { [correlationId]: { name, status: 'pending'|'completed'|'failed', fileId?, error? } }
 */

import { buildPlatformFileDownloadUrl } from '../../utils/platform-files-url.js';

import type { PlatformEvent } from '../contract.js';

export interface PlatformFileRecord extends Record<string, unknown> {
    id?: string;
}

export interface FileUploadEntry {
    name?: string;
    status: 'pending' | 'completed' | 'failed';
    fileId?: string;
    error?: string;
}

export interface FilesState {
    byId: Record<string, PlatformFileRecord>;
    uploads: Record<string, FileUploadEntry>;
}

export const FILES_EVENTS = Object.freeze({
    UPLOAD_REQUESTED: 'files/upload/requested',
    UPLOAD_COMPLETED: 'files/upload/completed',
    UPLOAD_FAILED:    'files/upload/failed',
    LOAD_REQUESTED:   'files/file/load_requested',
    LOADED:           'files/file/loaded',
    LOAD_FAILED:      'files/file/load_failed',
    OPEN_REQUESTED:   'files/file/open_requested',
    OPEN_FAILED:      'files/file/open_failed',
    EDITOR_SYNC_REQUESTED: 'files/editor/sync_requested',
    EDITOR_SYNC_COMPLETED: 'files/editor/sync_completed',
    EDITOR_SYNC_FAILED:    'files/editor/sync_failed',
});

export const initialFilesState: FilesState = Object.freeze({
    byId: {},
    uploads: {},
});

export function filesReducer(state: FilesState = initialFilesState, event: PlatformEvent): FilesState {
    switch (event.type) {
        case FILES_EVENTS.UPLOAD_REQUESTED: {
            const cid = event.meta.correlation_id || event.id;
            const name = ((event.payload || {}) as { name?: unknown }).name;
            return {
                ...state,
                uploads: { ...state.uploads, [cid]: { name: typeof name === 'string' ? name : undefined, status: 'pending' } },
            };
        }
        case FILES_EVENTS.UPLOAD_COMPLETED: {
            const p = (event.payload || {}) as { correlation_id?: unknown; file?: PlatformFileRecord; message?: unknown };
            const cid = event.meta.correlation_id || p.correlation_id;
            if (typeof cid !== 'string' || !cid) return state;
            const file = p.file;
            const next = { ...state.uploads };
            const cur = next[cid];
            if (cur) next[cid] = { ...cur, status: 'completed', fileId: file && file.id };
            const byId = file && file.id ? { ...state.byId, [file.id]: file } : state.byId;
            return { ...state, uploads: next, byId };
        }
        case FILES_EVENTS.UPLOAD_FAILED: {
            const p = (event.payload || {}) as { correlation_id?: unknown; message?: unknown };
            const cid = event.meta.correlation_id || p.correlation_id;
            if (typeof cid !== 'string' || !cid) return state;
            const next = { ...state.uploads };
            const cur = next[cid];
            if (cur) next[cid] = { ...cur, status: 'failed', error: typeof p.message === 'string' ? p.message : undefined };
            return { ...state, uploads: next };
        }
        case FILES_EVENTS.LOADED: {
            const file = ((event.payload || {}) as { file?: PlatformFileRecord }).file;
            if (!file || typeof file.id !== 'string' || !file.id) return state;
            return { ...state, byId: { ...state.byId, [file.id]: file } };
        }
        default:
            return state;
    }
}

export const filesSlice = { reducer: filesReducer, initial: initialFilesState };

export function buildFileDownloadUrl(fileId: string): string {
    return buildPlatformFileDownloadUrl(fileId);
}
