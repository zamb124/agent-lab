/**
 * Эффект files — загрузка/получение файлов через /api/v1/files/.
 */

import { httpRequest } from '../http.js';
import { CoreEvents } from '../contract.js';
import { FILES_EVENTS } from '../reducers/files.js';

function _fileIdFromPayload(payload) {
    const file = payload && payload.file && typeof payload.file === 'object' ? payload.file : payload;
    if (!file || typeof file !== 'object') return '';
    const id = file.file_id || file.id;
    return typeof id === 'string' && id.length > 0 ? id : '';
}

function _fileObjectFromPayload(payload, fileId) {
    const file = payload && payload.file && typeof payload.file === 'object' ? payload.file : payload;
    if (file && typeof file === 'object') {
        return { ...file, file_id: fileId };
    }
    return { file_id: fileId };
}

function _errorMessage(err) {
    return String(err && err.message ? err.message : err);
}

export function createFilesEffect({ baseUrl }) {
    const base = baseUrl || '';
    return async function filesEffect(event, ctx) {
        switch (event.type) {
            case FILES_EVENTS.UPLOAD_REQUESTED: {
                const file = event.payload && event.payload.file;
                if (!file) throw new Error('files.effect: payload.file required');
                const fd = new FormData();
                fd.append('file', file);
                try {
                    const result = await httpRequest({ method: 'POST', url: `${base}/api/v1/files/`, body: fd });
                    ctx.dispatch(FILES_EVENTS.UPLOAD_COMPLETED, { file: result }, { correlation_id: event.meta.correlation_id || event.id, causation_id: event.id, source: 'http' });
                } catch (err) {
                    ctx.dispatch(FILES_EVENTS.UPLOAD_FAILED, { message: _errorMessage(err) }, { correlation_id: event.meta.correlation_id || event.id, causation_id: event.id, source: 'http' });
                }
                return;
            }
            case FILES_EVENTS.LOAD_REQUESTED: {
                const fileId = event.payload && event.payload.file_id;
                if (!fileId) throw new Error('files.effect: file_id required');
                try {
                    const file = await httpRequest({ method: 'GET', url: `${base}/api/v1/files/${encodeURIComponent(fileId)}` });
                    ctx.dispatch(FILES_EVENTS.LOADED, { file }, { causation_id: event.id, source: 'http' });
                } catch (err) {
                    ctx.dispatch(FILES_EVENTS.LOAD_FAILED, { file_id: fileId, message: _errorMessage(err) }, { causation_id: event.id, source: 'http' });
                }
                return;
            }
            case FILES_EVENTS.OPEN_REQUESTED: {
                const fileId = _fileIdFromPayload(event.payload);
                if (!fileId) throw new Error('files.effect: file_id required for open');
                const file = _fileObjectFromPayload(event.payload, fileId);
                try {
                    const config = await httpRequest({
                        method: 'GET',
                        url: `/documents/api/v1/files/${encodeURIComponent(fileId)}/editor-config`,
                    });
                    ctx.dispatch(
                        CoreEvents.UI_MODAL_OPEN,
                        { kind: 'platform.file_viewer', props: { fileId, file, config } },
                        { correlation_id: event.meta.correlation_id || event.id, causation_id: event.id, source: 'http' },
                    );
                } catch (err) {
                    const message = _errorMessage(err);
                    ctx.dispatch(
                        FILES_EVENTS.OPEN_FAILED,
                        { file_id: fileId, message },
                        { correlation_id: event.meta.correlation_id || event.id, causation_id: event.id, source: 'http' },
                    );
                    ctx.dispatch(
                        CoreEvents.UI_TOAST_SHOW,
                        {
                            type: 'error',
                            i18n_key: 'platform:file_viewer.open_failed',
                            i18n_vars: { message },
                            duration: 4500,
                        },
                        { correlation_id: event.meta.correlation_id || event.id, causation_id: event.id, source: 'http' },
                    );
                }
                return;
            }
            case FILES_EVENTS.EDITOR_SYNC_REQUESTED: {
                const fileId = event.payload && event.payload.file_id;
                if (!fileId) throw new Error('files.effect: file_id required for editor sync');
                try {
                    const result = await httpRequest({
                        method: 'POST',
                        url: `/documents/api/v1/files/${encodeURIComponent(fileId)}/sync`,
                        body: {
                            close: event.payload.close === true,
                            settle_ms: Number.isFinite(event.payload.settle_ms) ? event.payload.settle_ms : 750,
                            dirty: event.payload.dirty === true ? true : (event.payload.dirty === false ? false : null),
                        },
                    });
                    ctx.dispatch(
                        FILES_EVENTS.EDITOR_SYNC_COMPLETED,
                        { file_id: fileId, result },
                        { correlation_id: event.meta.correlation_id || event.id, causation_id: event.id, source: 'http' },
                    );
                } catch (err) {
                    ctx.dispatch(
                        FILES_EVENTS.EDITOR_SYNC_FAILED,
                        { file_id: fileId, message: _errorMessage(err) },
                        { correlation_id: event.meta.correlation_id || event.id, causation_id: event.id, source: 'http' },
                    );
                }
                return;
            }
            default:
                return;
        }
    };
}
