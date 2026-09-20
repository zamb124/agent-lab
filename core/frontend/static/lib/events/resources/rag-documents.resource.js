/**
 * Documents — документы внутри RAG namespace.
 *
 * Upload байтов остаётся HTTP (chunked Files + index-file). Остальные
 * команды — WS RPC с тем же `op_*`, что и REST.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';
import { buildRagDocumentFileCreateSpecJson } from '@platform/lib/utils/file-create-spec.js';
import { uploadPlatformFile } from '@platform/lib/utils/platform-file-upload.js';
import { documentStatusResource } from './rag-document-status.resource.js';

export const documentsResource = createAsyncOp({
    name: 'rag/documents',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'rag/documents/list_requested',
    restMirror: { method: 'GET', path: '/rag/api/v1/namespaces/:namespace_id/documents' },
    extraInitial: { items: [], loadedNamespaceId: null },
    extraReducer: (state, event, events) => {
        if (event.type === events.REQUESTED) {
            const ns = event.payload && event.payload.namespace_id;
            if (typeof ns !== 'string') {
                throw new Error('rag/documents: REQUESTED payload.namespace_id required');
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
        if (slice === undefined) {
            throw new Error('rag/documents: slice ragDocuments missing');
        }
        if (slice.loadedNamespaceId !== namespaceId) {
            return true;
        }
        ctx.dispatch(
            events.REQUESTED,
            { namespace_id: namespaceId },
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
        if (!payload || typeof payload.namespace_id !== 'string' || payload.namespace_id.length === 0) {
            throw new Error('rag/document_upload: payload.namespace_id required');
        }
        if (!(payload.file instanceof File) && !(payload.file instanceof Blob)) {
            throw new Error('rag/document_upload: payload.file (File|Blob) required');
        }
        const metadata = payload.metadata !== undefined ? payload.metadata : {};
        const spec = buildRagDocumentFileCreateSpecJson({
            namespaceId: payload.namespace_id,
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
            url: `/rag/api/v1/namespaces/${encodeURIComponent(payload.namespace_id)}/documents/index-file`,
            body: {
                file_id: fileRecord.file_id,
                document_name: file.name,
                metadata,
            },
        });
    },
    onSuccess: (ctx, result, event) => {
        if (!result || typeof result.document_id !== 'string') {
            throw new Error('rag/document_upload: response.document_id required');
        }
        ctx.dispatch(
            documentStatusResource.events.REQUESTED,
            { document_id: result.document_id },
            { causation_id: event.id, source: 'local' },
        );
    },
});

export const documentRemoveOp = createAsyncOp({
    name: 'rag/document_remove',
    successToastKey: 'rag:toast.document_deleted',
    errorToastKey: 'rag:toast.document_delete_failed',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'rag/documents/remove_requested',
    restMirror: { method: 'DELETE', path: '/rag/api/v1/namespaces/:namespace_id/documents/:document_id' },
    onSuccess: (ctx, _result, event) => {
        ctx.dispatch(
            documentsResource.events.REQUESTED,
            { namespace_id: event.payload.namespace_id },
            { causation_id: event.id, source: 'local' },
        );
    },
});
