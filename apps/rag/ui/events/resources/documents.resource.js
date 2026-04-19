/**
 * Documents — документы внутри RAG namespace.
 *
 * Backend (`/rag/api/v1/namespaces/{namespace_id}/...`):
 *   GET    /documents                          → OffsetPage[RAGDocument]
 *   POST   /documents (multipart: file, metadata)  → DocumentUploadResponse
 *   POST   /ingest-text   (JSON IngestTextRequest) → IngestTextResponse
 *   DELETE /documents/{document_id}            → { success, document_id }
 *
 * Список documents доступен под разные namespaceId — `createResourceCollection`
 * не подходит (path параметризован), поэтому сделан как `createAsyncOp` с
 * собственным slice-полем `items` и привязкой `loadedNamespaceId` к
 * последнему загруженному namespace. Компоненты сами вызывают
 * `useOp('rag/documents').run({ namespaceId })` при смене страницы.
 *
 * Upload асинхронный: backend кладёт задачу в TaskIQ, фабрика
 * `documentUploadOp.onSuccess` стартует поллинг через
 * `documentStatusResource.events.REQUESTED`. По завершении поллинга
 * страница перезагружает список.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';
import { documentStatusResource } from './document-status.resource.js';

export const documentsResource = createAsyncOp({
    name: 'rag/documents',
    silent: true,
    restMirror: { method: 'GET', path: '/rag/api/v1/namespaces/:namespace_id/documents' },
    request: ({ payload }) => {
        if (!payload || typeof payload.namespaceId !== 'string' || payload.namespaceId.length === 0) {
            throw new Error('rag/documents: payload.namespaceId required');
        }
        const limit = typeof payload.limit === 'number' ? payload.limit : 100;
        const offset = typeof payload.offset === 'number' ? payload.offset : 0;
        return httpRequest({
            method: 'GET',
            url: `/rag/api/v1/namespaces/${encodeURIComponent(payload.namespaceId)}/documents`,
            query: { limit, offset },
        });
    },
    extraInitial: { items: [], loadedNamespaceId: null },
    extraReducer: (state, event, events) => {
        if (event.type === events.REQUESTED) {
            const ns = event.payload && event.payload.namespaceId;
            if (typeof ns !== 'string') {
                throw new Error('rag/documents: REQUESTED payload.namespaceId required');
            }
            return { ...state, items: [], loadedNamespaceId: ns };
        }
        if (event.type === events.SUCCEEDED) {
            const result = event.payload.result;
            if (!result || !Array.isArray(result.items)) {
                throw new Error('rag/documents: SUCCEEDED result.items required (array)');
            }
            return { ...state, items: result.items };
        }
        return state;
    },
});

export const documentUploadOp = createAsyncOp({
    name: 'rag/document_upload',
    successToastKey: 'rag:toast.document_uploaded',
    errorToastKey: 'rag:toast.document_upload_failed',
    restMirror: { method: 'POST', path: '/rag/api/v1/namespaces/:namespace_id/documents' },
    request: ({ payload }) => {
        if (!payload || typeof payload.namespaceId !== 'string' || payload.namespaceId.length === 0) {
            throw new Error('rag/document_upload: payload.namespaceId required');
        }
        if (!(payload.file instanceof File) && !(payload.file instanceof Blob)) {
            throw new Error('rag/document_upload: payload.file (File|Blob) required');
        }
        const fd = new FormData();
        fd.append('file', payload.file);
        fd.append('metadata', JSON.stringify(payload.metadata !== undefined ? payload.metadata : {}));
        return httpRequest({
            method: 'POST',
            url: `/rag/api/v1/namespaces/${encodeURIComponent(payload.namespaceId)}/documents`,
            body: fd,
        });
    },
    onSuccess: (ctx, result, event) => {
        const { namespaceId } = event.payload;
        if (!result || typeof result.document_id !== 'string') {
            throw new Error('rag/document_upload: response.document_id required');
        }
        ctx.dispatch(
            documentStatusResource.events.REQUESTED,
            { documentId: result.document_id, namespaceId },
            { causation_id: event.id, source: 'local' },
        );
    },
});

export const documentRemoveOp = createAsyncOp({
    name: 'rag/document_remove',
    successToastKey: 'rag:toast.document_deleted',
    errorToastKey: 'rag:toast.document_delete_failed',
    restMirror: { method: 'DELETE', path: '/rag/api/v1/namespaces/:namespace_id/documents/:document_id' },
    request: ({ payload }) => {
        if (!payload || typeof payload.namespaceId !== 'string' || payload.namespaceId.length === 0) {
            throw new Error('rag/document_remove: payload.namespaceId required');
        }
        if (typeof payload.documentId !== 'string' || payload.documentId.length === 0) {
            throw new Error('rag/document_remove: payload.documentId required');
        }
        return httpRequest({
            method: 'DELETE',
            url: `/rag/api/v1/namespaces/${encodeURIComponent(payload.namespaceId)}/documents/${encodeURIComponent(payload.documentId)}`,
        });
    },
    onSuccess: (ctx, _result, event) => {
        ctx.dispatch(
            documentsResource.events.REQUESTED,
            { namespaceId: event.payload.namespaceId },
            { causation_id: event.id, source: 'local' },
        );
    },
});

export const documentIngestTextOp = createAsyncOp({
    name: 'rag/document_ingest_text',
    successToastKey: 'rag:toast.text_ingested',
    errorToastKey: 'rag:toast.text_ingest_failed',
    restMirror: { method: 'POST', path: '/rag/api/v1/namespaces/:namespace_id/ingest-text' },
    request: ({ payload }) => {
        if (!payload || typeof payload.namespaceId !== 'string' || payload.namespaceId.length === 0) {
            throw new Error('rag/document_ingest_text: payload.namespaceId required');
        }
        if (typeof payload.text !== 'string' || payload.text.length === 0) {
            throw new Error('rag/document_ingest_text: payload.text required (non-empty string)');
        }
        const body = {
            text: payload.text,
            document_name: payload.documentName !== undefined ? payload.documentName : null,
            metadata: payload.metadata !== undefined ? payload.metadata : {},
            document_id: payload.documentId !== undefined ? payload.documentId : null,
        };
        return httpRequest({
            method: 'POST',
            url: `/rag/api/v1/namespaces/${encodeURIComponent(payload.namespaceId)}/ingest-text`,
            body,
        });
    },
    onSuccess: (ctx, _result, event) => {
        ctx.dispatch(
            documentsResource.events.REQUESTED,
            { namespaceId: event.payload.namespaceId },
            { causation_id: event.id, source: 'local' },
        );
    },
});
