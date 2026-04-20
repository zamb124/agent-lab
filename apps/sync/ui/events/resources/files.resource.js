/**
 * Sync Files — загрузка файлов в чат.
 *
 * Загрузка бинарного потока — REST-only (multipart, до сотен МБ). После
 * upload UI шлёт WS-команду `sync/files/upload_completed_requested` чтобы
 * получить каноничные метаданные файла.
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

export const fileUploadCompletedOp = createAsyncOp({
    name: 'sync/file_upload_completed',
    transport: 'ws',
    wsTimeoutMs: 5_000,
    silent: true,
    commandType: 'sync/files/upload_completed_requested',
    restMirror: { method: 'POST', path: '/sync/api/v1/files/upload-completed' },
});
