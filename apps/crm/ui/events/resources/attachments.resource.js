/**
 * Attachments — файлы, прикреплённые к сущностям CRM.
 *
 * Backend:
 *   GET    /crm/api/v1/entities/{entity_id}/attachments               → list
 *   POST   /crm/api/v1/entities/{entity_id}/attachments               → upload (multipart/form-data)
 *   DELETE /crm/api/v1/entities/{entity_id}/attachments/{attachment_id} → 204
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

export const attachmentsListOp = createAsyncOp({
    name: 'crm/attachments_list',
    silent: true,
    request: async ({ payload }) => {
        if (!payload || typeof payload.entity_id !== 'string') {
            throw new Error('attachmentsListOp: payload.entity_id required');
        }
        return await httpRequest({
            method: 'GET',
            url: `/crm/api/v1/entities/${encodeURIComponent(payload.entity_id)}/attachments`,
        });
    },
});

export const attachmentUploadOp = createAsyncOp({
    name: 'crm/attachment_upload',
    successToastKey: 'crm:toast.attachment.uploaded',
    errorToastKey: 'crm:toast.attachment.upload_failed',
    request: async ({ payload }) => {
        if (!payload || typeof payload.entity_id !== 'string' || !(payload.file instanceof File)) {
            throw new Error('attachmentUploadOp: { entity_id, file: File } required');
        }
        const formData = new FormData();
        formData.append('file', payload.file);
        return await httpRequest({
            method: 'POST',
            url: `/crm/api/v1/entities/${encodeURIComponent(payload.entity_id)}/attachments`,
            body: formData,
        });
    },
});

export const attachmentDeleteOp = createAsyncOp({
    name: 'crm/attachment_delete',
    successToastKey: 'crm:toast.attachment.removed',
    errorToastKey: 'crm:toast.attachment.remove_failed',
    request: async ({ payload }) => {
        if (!payload || typeof payload.entity_id !== 'string' || typeof payload.attachment_id !== 'string') {
            throw new Error('attachmentDeleteOp: { entity_id, attachment_id } required');
        }
        await httpRequest({
            method: 'DELETE',
            url: `/crm/api/v1/entities/${encodeURIComponent(payload.entity_id)}/attachments/${encodeURIComponent(payload.attachment_id)}`,
        });
        return { entity_id: payload.entity_id, attachment_id: payload.attachment_id };
    },
});
