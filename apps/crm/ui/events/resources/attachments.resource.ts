/**
 * Вложения — файлы, прикреплённые к сущностям CRM.
 *
 * Байты: uploadPlatformFile (chunked Files API) — HTTP.
 * Привязка / список / удаление — `crm/attachments/*_requested`.
 */

import { createAsyncOp, rerunLastRequest } from '@platform/lib/events/index.js';
import type { EffectCtx } from '@platform/lib/events/contract.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';
import { httpRequest } from '@platform/lib/events/http.js';
import { uploadPlatformFile } from '@platform/lib/utils/platform-file-upload.js';
import { buildCrmEntityFileCreateSpecJson } from '@platform/lib/utils/file-create-spec.js';

function entityIdOf(payload: unknown): string {
    if (!isPlainRecord(payload)) {
        throw new Error('crm attachments: payload.entity_id required');
    }
    const entityId = payload.entity_id;
    if (typeof entityId !== 'string' || entityId.length === 0) {
        throw new Error('crm attachments: payload.entity_id required');
    }
    return entityId;
}

function uploadFields(payload: unknown): { entityId: string; entityType: string; entityTitle: string | undefined; file: File } {
    if (!isPlainRecord(payload)) {
        throw new Error('attachmentUploadOp: { entity_id, file: File } required');
    }
    const entityId = payload.entity_id;
    const file = payload.file;
    if (typeof entityId !== 'string' || !(file instanceof File)) {
        throw new Error('attachmentUploadOp: { entity_id, file: File } required');
    }
    const entityType = payload.entity_type;
    if (typeof entityType !== 'string' || entityType.length === 0) {
        throw new Error('attachmentUploadOp: payload.entity_type required');
    }
    const entityTitle = payload.entity_title;
    return {
        entityId,
        entityType,
        entityTitle: typeof entityTitle === 'string' ? entityTitle : undefined,
        file,
    };
}

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

function _rerunAttachmentsFor(ctx: EffectCtx, entityId: string) {
    rerunLastRequest(ctx, attachmentsListOp, {
        when: (request) => isPlainRecord(request) && request.entity_id === entityId,
    });
}

export const attachmentUploadOp = createAsyncOp({
    name: 'crm/attachment_upload',
    successToastKey: 'crm:toast.attachment.uploaded',
    errorToastKey: 'crm:toast.attachment.upload_failed',
    restMirror: { method: 'POST', path: '/crm/api/v1/entities/:entity_id/attachments' },
    onSuccess: (ctx, _result, event) => _rerunAttachmentsFor(ctx, entityIdOf(event.payload)),
    request: async ({ payload }) => {
        const fields = uploadFields(payload);
        const uploaded = await uploadPlatformFile({
            file: fields.file,
            spec: buildCrmEntityFileCreateSpecJson({
                entityId: fields.entityId,
                entityType: fields.entityType,
                entityTitle: fields.entityTitle,
            }),
        });
        if (typeof uploaded.file_id !== 'string' || uploaded.file_id.length === 0) {
            throw new Error('attachmentUploadOp: upload result.file_id required');
        }
        return await httpRequest({
            method: 'POST',
            url: `/crm/api/v1/entities/${encodeURIComponent(fields.entityId)}/attachments`,
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
    onSuccess: (ctx, _result, event) => _rerunAttachmentsFor(ctx, entityIdOf(event.payload)),
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'crm/attachments_list': typeof attachmentsListOp;
        'crm/attachment_upload': typeof attachmentUploadOp;
        'crm/attachment_delete': typeof attachmentDeleteOp;
    }
}
