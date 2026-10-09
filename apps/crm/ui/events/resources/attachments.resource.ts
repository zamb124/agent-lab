/**
 * Вложения — файлы, прикреплённые к сущностям CRM.
 *
 * Байты: uploadPlatformFile (chunked Files API) — HTTP.
 * Привязка / список / удаление — `crm/attachments/*_requested`.
 */

import { createAsyncOp, rerunLastRequest } from '@platform/lib/events/index.js';
import type { EffectCtx } from '@platform/lib/events/contract.js';
import { httpRequest } from '@platform/lib/events/http.js';
import { uploadPlatformFile } from '@platform/lib/utils/platform-file-upload.js';
import { buildCrmEntityFileCreateSpecJson } from '@platform/lib/utils/file-create-spec.js';

/**
 * Список вложений сущности; после upload/remove фабрика перечитывает его сама:
 * результат привязки не содержит полной записи, а статус обработки меняется асинхронно.
 */
export const attachmentsListOp = createAsyncOp({
    name: 'crm/attachments_list',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/attachments/list_requested',
    restMirror: { method: 'GET', path: '/crm/api/v1/entities/:entity_id/attachments' },
});

function _rerunAttachmentsFor(ctx: EffectCtx, entityId: unknown) {
    rerunLastRequest(ctx, attachmentsListOp, {
        when: (request) => Boolean(request) && (request as Record<string, unknown>).entity_id === entityId,
    });
}

export const attachmentUploadOp = createAsyncOp({
    name: 'crm/attachment_upload',
    successToastKey: 'crm:toast.attachment.uploaded',
    errorToastKey: 'crm:toast.attachment.upload_failed',
    restMirror: { method: 'POST', path: '/crm/api/v1/entities/:entity_id/attachments' },
    onSuccess: (ctx, _result, event) => _rerunAttachmentsFor(ctx, (event.payload as Record<string, any>).entity_id),
    request: async ({ payload }) => {
        const p = payload as Record<string, any> | null;
        if (!p || typeof p.entity_id !== 'string' || !(p.file instanceof File)) {
            throw new Error('attachmentUploadOp: { entity_id, file: File } required');
        }
        if (typeof p.entity_type !== 'string' || p.entity_type.length === 0) {
            throw new Error('attachmentUploadOp: payload.entity_type required');
        }
        const uploaded = await uploadPlatformFile({
            file: p.file,
            spec: buildCrmEntityFileCreateSpecJson({
                entityId: p.entity_id,
                entityType: p.entity_type,
                entityTitle: p.entity_title,
            }),
        });
        if (typeof uploaded.file_id !== 'string' || uploaded.file_id.length === 0) {
            throw new Error('attachmentUploadOp: upload result.file_id required');
        }
        return await httpRequest({
            method: 'POST',
            url: `/crm/api/v1/entities/${encodeURIComponent(p.entity_id)}/attachments`,
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
    onSuccess: (ctx, _result, event) => _rerunAttachmentsFor(ctx, (event.payload as Record<string, any>).entity_id),
});
