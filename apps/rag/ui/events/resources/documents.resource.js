/**
 * Documents — документы внутри RAG namespace.
 *
 * Upload: uploadPlatformFile (chunked) → index-file.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';
import { buildRagDocumentFileCreateSpecJson } from '@platform/lib/utils/file-create-spec.js';
import { uploadPlatformFile } from '@platform/lib/utils/platform-file-upload.js';
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
        if (event.type === 'rag/document/status_updated') {
            const payload = event.payload;
            if (!payload || typeof payload !== 'object') {
                return state;
            }
            const documentId = typeof payload.document_id === 'string' ? payload.document_id : '';
            const namespaceId = typeof payload.namespace_id === 'string' ? payload.namespace_id : '';
            const status = typeof payload.status === 'string' ? payload.status : '';
            if (documentId.length === 0 || status.length === 0) {
                return state;
            }
            if (namespaceId.length > 0 && state.loadedNamespaceId !== null && namespaceId !== state.loadedNamespaceId) {
                return state;
            }
            const idx = state.items.findIndex((item) => item && item.document_id === documentId);
            if (idx === -1) {
                return state;
            }
            const prev = state.items[idx];
            const nextItem = {
                ...prev,
                status,
                name: typeof payload.document_name === 'string' ? payload.document_name : prev.name,
                metadata: {
                    ...(prev.metadata && typeof prev.metadata === 'object' ? prev.metadata : {}),
                    error_message: typeof payload.error_message === 'string' ? payload.error_message : null,
                    chunks_count: typeof payload.chunks_count === 'number' ? payload.chunks_count : null,
                },
            };
            const items = state.items.map((item, i) => (i === idx ? nextItem : item));
            return { ...state, items };
        }
        return state;
    },
    extraEffect: async (event, ctx, events) => {
        if (event.type !== 'rag/document/status_updated') {
            return false;
        }
        const payload = event.payload;
        if (!payload || typeof payload !== 'object') {
            return true;
        }
        const status = typeof payload.status === 'string' ? payload.status : '';
        const namespaceId = typeof payload.namespace_id === 'string' ? payload.namespace_id : '';
        if (status !== 'completed' && status !== 'failed') {
            return true;
        }
        if (namespaceId.length === 0) {
            return true;
        }
        const slice = ctx.getState().ragDocuments;
        if (!slice || slice.loadedNamespaceId !== namespaceId) {
            return true;
        }
        ctx.dispatch(
            events.REQUESTED,
            { namespaceId },
            { causation_id: event.id, source: 'ws' },
        );
        return true;
    },
});

export const documentUploadOp = createAsyncOp({
    name: 'rag/document_upload',
    successToastKey: 'rag:toast.document_uploaded',
    errorToastKey: 'rag:toast.document_upload_failed',
    restMirror: {
        method: 'POST',
        path: '/rag/api/v1/namespaces/:namespace_id/documents/index-file',
    },
    request: async ({ payload }) => {
        if (!payload || typeof payload.namespaceId !== 'string' || payload.namespaceId.length === 0) {
            throw new Error('rag/document_upload: payload.namespaceId required');
        }
        if (!(payload.file instanceof File) && !(payload.file instanceof Blob)) {
            throw new Error('rag/document_upload: payload.file (File|Blob) required');
        }
        const metadata = payload.metadata !== undefined ? payload.metadata : {};
        const spec = buildRagDocumentFileCreateSpecJson({
            namespaceId: payload.namespaceId,
            ragMetadata: metadata,
        });
        const file =
            payload.file instanceof File
                ? payload.file
                : new File([payload.file], 'document.bin', {
                    type: payload.file.type || 'application/octet-stream',
                });
        const fileRecord = await uploadPlatformFile({ file, spec });
        if (!fileRecord || typeof fileRecord.file_id !== 'string') {
            throw new Error('rag/document_upload: file create response.file_id required');
        }
        return httpRequest({
            method: 'POST',
            url: `/rag/api/v1/namespaces/${encodeURIComponent(payload.namespaceId)}/documents/index-file`,
            body: {
                file_id: fileRecord.file_id,
                document_name: file.name,
                metadata,
            },
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
