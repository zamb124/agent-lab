/**
 * Файлы Sync — метаданные после REST upload.
 *
 * Бинарный upload — platform/file_create → POST /frontend/api/v1/files/.
 * После upload UI шлёт WS-команду `sync/files/upload_completed_requested`.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';

export const fileUploadCompletedOp = createAsyncOp({
    name: 'sync/file_upload_completed',
    transport: 'ws',
    wsTimeoutMs: 5_000,
    silent: true,
    commandType: 'sync/files/upload_completed_requested',
    restMirror: { method: 'POST', path: '/sync/api/v1/files/upload-completed' },
});
