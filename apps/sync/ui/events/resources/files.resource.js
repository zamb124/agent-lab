/**
 * Sync Files — загрузка файлов в чат.
 *
 * REST-only (`transport: 'http'`): multipart upload не помещается в WS-фрейм
 * (бинарные данные, размеры до сотен МБ). Файл загружается в S3 через
 * `POST /sync/api/v1/files/`, затем `file_id` подставляется в content-блок
 * следующего сообщения.
 *
 * `request` использует FormData; httpRequest в `core/.../events/http.js`
 * детектит FormData и не подставляет Content-Type (браузер сам).
 */

import { createAsyncOp } from '@platform/lib/events/index.js';

export const fileUploadOp = createAsyncOp({
    name: 'sync/file_upload',
    transport: 'http',
    silent: true,
    restMirror: { method: 'POST', path: '/sync/api/v1/files/' },
    request: async ({ payload }) => {
        const { httpRequest } = await import('@platform/lib/events/http.js');
        if (!payload || !(payload.file instanceof File)) {
            throw new Error('fileUploadOp: payload.file (File) required');
        }
        const formData = new FormData();
        formData.append('file', payload.file, payload.file.name);
        if (typeof payload.purpose === 'string') {
            formData.append('purpose', payload.purpose);
        }
        return httpRequest({
            method: 'POST',
            url: '/sync/api/v1/files/',
            body: formData,
        });
    },
});
