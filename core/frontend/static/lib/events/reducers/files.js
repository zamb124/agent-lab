/**
 * Files slice — мета-инфо загруженных файлов и upload-операций.
 *
 * state.files:
 *   byId:    { [fileId]: object }
 *   uploads: { [correlationId]: { name, status: 'pending'|'completed'|'failed', fileId?, error? } }
 */

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

export const initialFilesState = Object.freeze({
    byId: {},
    uploads: {},
});

export function filesReducer(state = initialFilesState, event) {
    switch (event.type) {
        case FILES_EVENTS.UPLOAD_REQUESTED: {
            const cid = event.meta.correlation_id || event.id;
            const name = event.payload && event.payload.name;
            return {
                ...state,
                uploads: { ...state.uploads, [cid]: { name, status: 'pending' } },
            };
        }
        case FILES_EVENTS.UPLOAD_COMPLETED: {
            const cid = event.meta.correlation_id || event.payload?.correlation_id;
            if (!cid) return state;
            const file = event.payload && event.payload.file;
            const next = { ...state.uploads };
            const cur = next[cid];
            if (cur) next[cid] = { ...cur, status: 'completed', fileId: file && file.id };
            const byId = file && file.id ? { ...state.byId, [file.id]: file } : state.byId;
            return { ...state, uploads: next, byId };
        }
        case FILES_EVENTS.UPLOAD_FAILED: {
            const cid = event.meta.correlation_id || event.payload?.correlation_id;
            if (!cid) return state;
            const next = { ...state.uploads };
            const cur = next[cid];
            if (cur) next[cid] = { ...cur, status: 'failed', error: event.payload && event.payload.message };
            return { ...state, uploads: next };
        }
        case FILES_EVENTS.LOADED: {
            const file = event.payload && event.payload.file;
            if (!file || !file.id) return state;
            return { ...state, byId: { ...state.byId, [file.id]: file } };
        }
        default:
            return state;
    }
}

export const filesSlice = { reducer: filesReducer, initial: initialFilesState };

/** Pure helper: URL для скачивания файла. */
export function buildFileDownloadUrl(baseUrl, fileId) {
    if (typeof fileId !== 'string' || fileId === '') {
        throw new Error('buildFileDownloadUrl: fileId required');
    }
    return `${baseUrl}/api/v1/files/download/${encodeURIComponent(fileId)}`;
}
