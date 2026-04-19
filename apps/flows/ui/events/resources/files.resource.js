/**
 * Files — multipart upload в чат/редактор.
 * REST: `/flows/api/v1/files/`.
 *
 * REST-only (multipart не помещается в WS-фрейм).
 */

import { createAsyncOp } from '@platform/lib/events/index.js';

export const fileUploadOp = createAsyncOp({
    name: 'flows/file_upload',
    transport: 'http',
    silent: true,
    restMirror: { method: 'POST', path: '/flows/api/v1/files/' },
    request: async ({ payload }) => {
        const { httpRequest } = await import('@platform/lib/events/http.js');
        if (!payload || !(payload.file instanceof File)) {
            throw new Error('fileUploadOp: payload.file (File) required');
        }
        const formData = new FormData();
        formData.append('file', payload.file, payload.file.name);
        return httpRequest({
            method: 'POST',
            url: '/flows/api/v1/files/',
            body: formData,
        });
    },
});
