/**
 * Вложения — файлы, прикреплённые к сущностям CRM.
 *
 * Байты: uploadPlatformFile (chunked Files API) — HTTP.
 * Привязка / список / удаление — `crm/attachments/*_requested`.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';
import { uploadPlatformFile } from '@platform/lib/utils/platform-file-upload.js';
import { buildCrmEntityFileCreateSpecJson } from '@platform/lib/utils/file-create-spec.js';

export const attachmentsListOp = createAsyncOp({
    name: 'crm/attachments_list',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/attachments/list_requested',
    restMirror: { method: 'GET', path: '/crm/api/v1/entities/:entity_id/attachments' },
});

export const attachmentUploadOp = createAsyncOp({
    name: 'crm/attachment_upload',
    successToastKey: 'crm:toast.attachment.uploaded',
    errorToastKey: 'crm:toast.attachment.upload_failed',
    restMirror: { method: 'POST', path: '/crm/api/v1/entities/:entity_id/attachments' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.entity_id !== 'string' || !(payload.file instanceof File)) {
            throw new Error('attachmentUploadOp: { entity_id, file: File } required');
        }
        if (typeof payload.entity_type !== 'string' || payload.entity_type.length === 0) {
            throw new Error('attachmentUploadOp: payload.entity_type required');
        }
        const uploaded = await uploadPlatformFile({
            file: payload.file,
            spec: buildCrmEntityFileCreateSpecJson({
                entityId: payload.entity_id,
                entityType: payload.entity_type,
                entityTitle: payload.entity_title,
            }),
        });
        if (typeof uploaded.file_id !== 'string' || uploaded.file_id.length === 0) {
            throw new Error('attachmentUploadOp: upload result.file_id required');
        }
        return await httpRequest({
            method: 'POST',
            url: `/crm/api/v1/entities/${encodeURIComponent(payload.entity_id)}/attachments`,
            body: { file_id: uploaded.file_id },
        });
    },
});

export const attachmentDeleteOp = createAsyncOp({
    name: 'crm/attachment_delete',
    successToastKey: 'crm:toast.attachment.removed',
    errorToastKey: 'crm:toast.attachment.remove_failed',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/attachments/remove_requested',
    restMirror: { method: 'DELETE', path: '/crm/api/v1/entities/:entity_id/attachments/:attachment_id' },
});
