/**
 * Файлы Sync — загрузка файлов в чат.
 *
 * Загрузка бинарного потока — REST-only (multipart, до сотен МБ). После
 * upload UI шлёт WS-команду `sync/files/upload_completed_requested` чтобы
 * получить каноничные метаданные файла.
 */

import { createAsyncOp, createMultipartFileUploadOp } from '@platform/lib/events/index.js';

export const fileUploadOp = createMultipartFileUploadOp({
    name: 'sync/file_upload',
    url: '/sync/api/v1/files/',
    extraFields: ['purpose'],
});

export const fileUploadCompletedOp = createAsyncOp({
    name: 'sync/file_upload_completed',
    transport: 'ws',
    wsTimeoutMs: 5_000,
    silent: true,
    commandType: 'sync/files/upload_completed_requested',
    restMirror: { method: 'POST', path: '/sync/api/v1/files/upload-completed' },
});
