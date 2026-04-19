/**
 * Document Status — поллинг статуса асинхронной индексации документа.
 *
 * Backend (`/rag/api/v1/documents/{document_id}/status`):
 *   GET → DocumentProcessingStatus { document_id, status, document_name, ... }
 *
 * Семантика:
 *   - dispatch REQUESTED { documentId, namespaceId } — один HTTP-запрос
 *     текущего статуса.
 *   - Если статус `pending`/`processing`, эффект сам перезаписывает
 *     REQUESTED через setTimeout (поллинг).
 *   - Если статус `completed` или `failed`, диспатчим тост из эффекта
 *     (внутри фабрики `dispatch(CoreEvents.UI_TOAST_SHOW, ...)` разрешён
 *     каноном — запрет действует только в pages/modals/components).
 *   - Перезагрузку списка документов делает компонент через
 *     `useEvent(documentStatusResource.events.SUCCEEDED, ...)` —
 *     factory не знает namespaceId списка.
 *
 * Slice фиксирует последний полученный статус, чтобы UI мог отрисовать
 * progress без отдельной подписки на каждое событие.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
import { httpRequest } from '@platform/lib/events/http.js';

const POLL_INTERVAL_MS = 2_000;

export const documentStatusResource = createAsyncOp({
    name: 'rag/document_status',
    silent: true,
    restMirror: { method: 'GET', path: '/rag/api/v1/documents/:document_id/status' },
    request: ({ payload }) => {
        if (!payload || typeof payload.documentId !== 'string' || payload.documentId.length === 0) {
            throw new Error('rag/document_status: payload.documentId required');
        }
        return httpRequest({
            method: 'GET',
            url: `/rag/api/v1/documents/${encodeURIComponent(payload.documentId)}/status`,
        });
    },
    onSuccess: (ctx, status, event) => {
        const { documentId, namespaceId } = event.payload;
        const documentName = typeof status.document_name === 'string' ? status.document_name : documentId;
        if (status.status === 'pending' || status.status === 'processing') {
            setTimeout(() => {
                ctx.dispatch(
                    documentStatusResource.events.REQUESTED,
                    { documentId, namespaceId },
                    { source: 'timer' },
                );
            }, POLL_INTERVAL_MS);
            return;
        }
        if (status.status === 'completed') {
            ctx.dispatch(
                CoreEvents.UI_TOAST_SHOW,
                { type: 'success', i18n_key: 'rag:toast.document_processed', i18n_vars: { name: documentName } },
                { causation_id: event.id },
            );
            return;
        }
        if (status.status === 'failed') {
            ctx.dispatch(
                CoreEvents.UI_TOAST_SHOW,
                { type: 'error', i18n_key: 'rag:toast.document_process_failed', i18n_vars: { name: documentName } },
                { causation_id: event.id },
            );
        }
    },
});
