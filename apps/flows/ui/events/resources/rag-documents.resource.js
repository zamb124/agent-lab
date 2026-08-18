/**
 * Документы RAG namespace в редакторе resource-ноды на канве.
 *
 * HTTP — peer RAG (`restMirror.service: 'rag'`). Статус индексации —
 * push `rag/document/status_updated`, без HTTP poll.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
import { httpRequest } from '@platform/lib/events/http.js';
import { buildRagDocumentFileCreateSpecJson } from '@platform/lib/utils/file-create-spec.js';
import { uploadPlatformFile } from '@platform/lib/utils/platform-file-upload.js';

const RAG_DOCUMENT_STATUS_UPDATED = 'rag/document/status_updated';
export const FLOWS_RAG_DOCUMENTS_LIST_LIMIT = 100;

function _isPlainObject(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
}

export const flowsRagDocumentsOp = createAsyncOp({
    name: 'flows/rag_documents',
    silent: true,
    transport: 'http',
    restMirror: { method: 'GET', path: '/rag/api/v1/namespaces/:namespace_id/documents', service: 'rag' },
    request: ({ payload }) => {
        if (!payload || typeof payload.namespaceId !== 'string' || payload.namespaceId.length === 0) {
            throw new Error('flows/rag_documents: payload.namespaceId required');
        }
        if (typeof payload.limit !== 'number' || !Number.isFinite(payload.limit) || payload.limit < 1) {
            throw new Error('flows/rag_documents: payload.limit >= 1 required');
        }
        if (typeof payload.offset !== 'number' || !Number.isFinite(payload.offset) || payload.offset < 0) {
            throw new Error('flows/rag_documents: payload.offset >= 0 required');
        }
        return httpRequest({
            method: 'GET',
            url: `/rag/api/v1/namespaces/${encodeURIComponent(payload.namespaceId)}/documents`,
            query: { limit: payload.limit, offset: payload.offset },
        });
    },
    extraInitial: { items: [], loadedNamespaceId: null },
    extraReducer: (state, event, events) => {
        if (event.type === events.REQUESTED) {
            const ns = event.payload && event.payload.namespaceId;
            if (typeof ns !== 'string' || ns.length === 0) {
                throw new Error('flows/rag_documents: REQUESTED payload.namespaceId required');
            }
            return { ...state, items: [], loadedNamespaceId: ns };
        }
        if (event.type === events.SUCCEEDED) {
            const result = event.payload.result;
            if (!result || !Array.isArray(result.items)) {
                throw new Error('flows/rag_documents: SUCCEEDED result.items required (array)');
            }
            return { ...state, items: result.items };
        }
        if (event.type === RAG_DOCUMENT_STATUS_UPDATED) {
            const payload = event.payload;
            if (!_isPlainObject(payload)) {
                return state;
            }
            const documentId = payload.document_id;
            const namespaceId = payload.namespace_id;
            const status = payload.status;
            if (typeof documentId !== 'string' || documentId.length === 0) {
                return state;
            }
            if (typeof status !== 'string' || status.length === 0) {
                return state;
            }
            if (
                typeof namespaceId === 'string'
                && namespaceId.length > 0
                && state.loadedNamespaceId !== null
                && namespaceId !== state.loadedNamespaceId
            ) {
                return state;
            }
            const idx = state.items.findIndex((item) => item && item.document_id === documentId);
            if (idx === -1) {
                return state;
            }
            const prev = state.items[idx];
            const nextItem = { ...prev, status };
            if (typeof payload.document_name === 'string') {
                nextItem.name = payload.document_name;
            }
            if (typeof payload.chunks_count === 'number') {
                nextItem.chunks_count = payload.chunks_count;
            }
            if (typeof payload.error_message === 'string' || typeof payload.chunks_count === 'number') {
                if (!_isPlainObject(prev.metadata)) {
                    throw new Error('flows/rag_documents: item.metadata object required');
                }
                const metadata = { ...prev.metadata };
                if (typeof payload.error_message === 'string') {
                    metadata.error_message = payload.error_message;
                }
                if (typeof payload.chunks_count === 'number') {
                    metadata.chunks_count = payload.chunks_count;
                }
                nextItem.metadata = metadata;
            }
            const items = state.items.map((item, i) => (i === idx ? nextItem : item));
            return { ...state, items };
        }
        return state;
    },
    extraEffect: async (event, ctx, events) => {
        if (event.type !== RAG_DOCUMENT_STATUS_UPDATED) {
            return false;
        }
        const payload = event.payload;
        if (!_isPlainObject(payload)) {
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
        const slice = ctx.getState().flowsRagDocuments;
        if (slice === undefined) {
            throw new Error('flows/rag_documents: slice flowsRagDocuments missing');
        }
        if (slice.loadedNamespaceId !== namespaceId) {
            return true;
        }
        ctx.dispatch(
            events.REQUESTED,
            { namespaceId, limit: FLOWS_RAG_DOCUMENTS_LIST_LIMIT, offset: 0 },
            { causation_id: event.id, source: 'ws' },
        );
        return true;
    },
});

export const flowsRagDocumentStatusOp = createAsyncOp({
    name: 'flows/rag_document_status',
    silent: true,
    transport: 'http',
    restMirror: { method: 'GET', path: '/rag/api/v1/documents/:document_id/status', service: 'rag' },
    request: ({ payload }) => {
        if (!payload || typeof payload.documentId !== 'string' || payload.documentId.length === 0) {
            throw new Error('flows/rag_document_status: payload.documentId required');
        }
        return httpRequest({
            method: 'GET',
            url: `/rag/api/v1/documents/${encodeURIComponent(payload.documentId)}/status`,
        });
    },
    onSuccess: (ctx, status, event) => {
        if (!_isPlainObject(status) || typeof status.status !== 'string') {
            throw new Error('flows/rag_document_status: result.status required');
        }
        const documentId = event.payload.documentId;
        const documentName = typeof status.document_name === 'string' ? status.document_name : documentId;
        if (status.status === 'completed') {
            ctx.dispatch(
                CoreEvents.UI_TOAST_SHOW,
                {
                    type: 'success',
                    i18n_key: 'flows:rag_resource_editor.toast_document_processed',
                    i18n_vars: { name: documentName },
                },
                { causation_id: event.id },
            );
            return;
        }
        if (status.status === 'failed') {
            ctx.dispatch(
                CoreEvents.UI_TOAST_SHOW,
                {
                    type: 'error',
                    i18n_key: 'flows:rag_resource_editor.toast_document_process_failed',
                    i18n_vars: { name: documentName },
                },
                { causation_id: event.id },
            );
        }
    },
    extraReducer: (state, event) => {
        if (event.type !== RAG_DOCUMENT_STATUS_UPDATED) {
            return state;
        }
        const payload = event.payload;
        if (!_isPlainObject(payload)) {
            return state;
        }
        const documentId = payload.document_id;
        if (typeof documentId !== 'string' || documentId.length === 0) {
            return state;
        }
        if (typeof payload.status !== 'string' || payload.status.length === 0) {
            return state;
        }
        const nextStatus = {
            document_id: documentId,
            status: payload.status,
            document_name: typeof payload.document_name === 'string' ? payload.document_name : documentId,
            error_message: typeof payload.error_message === 'string' ? payload.error_message : null,
            chunks_count: typeof payload.chunks_count === 'number' ? payload.chunks_count : null,
            namespace_id: payload.namespace_id,
        };
        return {
            ...state,
            lastResult: nextStatus,
            busy: false,
            error: null,
        };
    },
});

export const flowsRagDocumentUploadOp = createAsyncOp({
    name: 'flows/rag_document_upload',
    transport: 'http',
    restMirror: {
        method: 'POST',
        path: '/rag/api/v1/namespaces/:namespace_id/documents/index-file',
        service: 'rag',
    },
    successToastKey: 'flows:rag_resource_editor.toast_document_uploaded',
    errorToastKey: 'flows:rag_resource_editor.toast_document_upload_failed',
    request: async ({ payload }) => {
        if (!payload || typeof payload.namespaceId !== 'string' || payload.namespaceId.length === 0) {
            throw new Error('flows/rag_document_upload: payload.namespaceId required');
        }
        if (!(payload.file instanceof File)) {
            throw new Error('flows/rag_document_upload: payload.file File required');
        }
        const metadata = _isPlainObject(payload.metadata) ? payload.metadata : null;
        if (metadata === null) {
            throw new Error('flows/rag_document_upload: payload.metadata object required');
        }
        const spec = buildRagDocumentFileCreateSpecJson({
            namespaceId: payload.namespaceId,
            ragMetadata: metadata,
        });
        const fileRecord = await uploadPlatformFile({ file: payload.file, spec });
        if (!fileRecord || typeof fileRecord.file_id !== 'string') {
            throw new Error('flows/rag_document_upload: file create response.file_id required');
        }
        return httpRequest({
            method: 'POST',
            url: `/rag/api/v1/namespaces/${encodeURIComponent(payload.namespaceId)}/documents/index-file`,
            body: {
                file_id: fileRecord.file_id,
                document_name: payload.file.name,
                metadata,
            },
        });
    },
    onSuccess: (ctx, result, event) => {
        const { namespaceId } = event.payload;
        if (!result || typeof result.document_id !== 'string') {
            throw new Error('flows/rag_document_upload: response.document_id required');
        }
        ctx.dispatch(
            flowsRagDocumentStatusOp.events.REQUESTED,
            { documentId: result.document_id, namespaceId },
            { causation_id: event.id, source: 'local' },
        );
        ctx.dispatch(
            flowsRagDocumentsOp.events.REQUESTED,
            { namespaceId, limit: FLOWS_RAG_DOCUMENTS_LIST_LIMIT, offset: 0 },
            { causation_id: event.id, source: 'local' },
        );
    },
});

export const flowsRagDocumentRemoveOp = createAsyncOp({
    name: 'flows/rag_document_remove',
    transport: 'http',
    restMirror: {
        method: 'DELETE',
        path: '/rag/api/v1/namespaces/:namespace_id/documents/:document_id',
        service: 'rag',
    },
    successToastKey: 'flows:rag_resource_editor.toast_document_deleted',
    errorToastKey: 'flows:rag_resource_editor.toast_document_delete_failed',
    request: ({ payload }) => {
        if (!payload || typeof payload.namespaceId !== 'string' || payload.namespaceId.length === 0) {
            throw new Error('flows/rag_document_remove: payload.namespaceId required');
        }
        if (typeof payload.documentId !== 'string' || payload.documentId.length === 0) {
            throw new Error('flows/rag_document_remove: payload.documentId required');
        }
        return httpRequest({
            method: 'DELETE',
            url: `/rag/api/v1/namespaces/${encodeURIComponent(payload.namespaceId)}/documents/${encodeURIComponent(payload.documentId)}`,
        });
    },
    onSuccess: (ctx, _result, event) => {
        ctx.dispatch(
            flowsRagDocumentsOp.events.REQUESTED,
            {
                namespaceId: event.payload.namespaceId,
                limit: FLOWS_RAG_DOCUMENTS_LIST_LIMIT,
                offset: 0,
            },
            { causation_id: event.id, source: 'local' },
        );
    },
});
