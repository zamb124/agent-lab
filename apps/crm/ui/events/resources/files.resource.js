/**
 * Files — общий аплоад файла в платформенный файловый API.
 *
 * Backend (`POST /crm/api/v1/files/`, multipart/form-data, поле `file`):
 *   200 → FileResponse { file_id, original_name, content_type, size_bytes,
 *                        download_url, ... }
 *
 * Возвращаемый объект используется wizard'ом импорта знаний для построения
 * `source_file_id` / `source_file_ids` в payload `taskKnowledgeImportStartOp`.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

export const fileUploadOp = createAsyncOp({
    name: 'crm/file_upload',
    silent: true,
    restMirror: { method: 'POST', path: '/crm/api/v1/files/' },
    request: async ({ payload }) => {
        if (!payload || !(payload.file instanceof File)) {
            throw new Error('fileUploadOp: { file: File } required');
        }
        const formData = new FormData();
        formData.append('file', payload.file);
        return await httpRequest({
            method: 'POST',
            url: '/crm/api/v1/files/',
            body: formData,
        });
    },
});
