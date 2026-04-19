/**
 * Files effect — загрузка/получение файлов через /api/v1/files/.
 */

import { httpRequest } from '../http.js';
import { FILES_EVENTS } from '../reducers/files.js';

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
                    ctx.dispatch(FILES_EVENTS.UPLOAD_FAILED, { message: String(err && err.message ? err.message : err) }, { correlation_id: event.meta.correlation_id || event.id, causation_id: event.id, source: 'http' });
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
                    ctx.dispatch(FILES_EVENTS.LOAD_FAILED, { file_id: fileId, message: String(err && err.message ? err.message : err) }, { causation_id: event.id, source: 'http' });
                }
                return;
            }
            default:
                return;
        }
    };
}
