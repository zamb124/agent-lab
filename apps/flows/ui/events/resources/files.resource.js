/**
 * Files — multipart upload в чат/редактор.
 * REST: `/flows/api/v1/files/`.
 *
 * REST-only (multipart не помещается в WS-фрейм).
 */

import { createMultipartFileUploadOp } from '@platform/lib/events/index.js';

export const fileUploadOp = createMultipartFileUploadOp({
    name: 'flows/file_upload',
    url: '/flows/api/v1/files/',
});
