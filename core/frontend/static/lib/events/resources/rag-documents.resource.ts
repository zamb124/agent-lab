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
import type { EffectCtx } from '../contract.js';
import { isPlainRecord } from '../payload.js';

type JsonObject = Record<string, unknown>;

function documentRows(value: unknown): JsonObject[] {
    if (!Array.isArray(value)) {
        throw new Error('rag/documents: items must be an array');
    }
    const rows: JsonObject[] = [];
    for (const item of value) {
        if (!isPlainRecord(item)) {
            throw new Error('rag/documents: document row must be an object');
        }
        rows.push(item);
    }
    return rows;
}

function copyMetadata(value: unknown): JsonObject {
    if (value === undefined || value === null) {
        return {};
    }
    if (!isPlainRecord(value)) {
        throw new Error('rag/documents: document metadata must be an object');
    }
    const metadata: JsonObject = {};
    for (const [key, field] of Object.entries(value)) {
        metadata[key] = field;
    }
    return metadata;
}

function loadedNamespaceId(state: unknown): string | null {
    if (!isPlainRecord(state) || !isPlainRecord(state.ragDocuments)) {
        throw new Error('rag/documents: slice ragDocuments missing');
    }
    const loaded = state.ragDocuments.loadedNamespaceId;
    if (loaded === undefined || loaded === null) {
        return null;
    }
    if (typeof loaded !== 'string') {
        throw new Error('rag/documents: loadedNamespaceId must be a string');
    }
    return loaded;
}

function uploadFields(payload: unknown): { namespaceId: string; file: File | Blob; metadata: JsonObject } {
    if (!isPlainRecord(payload) || typeof payload.namespace_id !== 'string' || payload.namespace_id.length === 0) {
        throw new Error('rag/document_upload: payload.namespace_id required');
    }
    const file = payload.file;
    if (!(file instanceof File) && !(file instanceof Blob)) {
        throw new Error('rag/document_upload: payload.file (File|Blob) required');
    }
    if (payload.metadata === undefined) {
        return { namespaceId: payload.namespace_id, file, metadata: {} };
    }
    if (!isPlainRecord(payload.metadata)) {
        throw new Error('rag/document_upload: payload.metadata must be an object');
    }
    return { namespaceId: payload.namespace_id, file, metadata: payload.metadata };
}

function removeNamespaceId(payload: unknown): string {
    if (!isPlainRecord(payload) || typeof payload.namespace_id !== 'string' || payload.namespace_id.length === 0) {
        throw new Error('rag/document_remove: payload.namespace_id required');
    }
    return payload.namespace_id;
}

function requireEventName(name: string | undefined, label: string): string {
    if (name === undefined) {
        throw new Error(`${label} missing`);
    }
    return name;
}

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
            if (!isPlainRecord(event.payload) || typeof event.payload.namespace_id !== 'string') {
                throw new Error('rag/documents: REQUESTED payload.namespace_id required');
            }
            return { ...state, items: [], loadedNamespaceId: event.payload.namespace_id };
        }
        if (event.type === events.SUCCEEDED) {
            const result = isPlainRecord(event.payload) ? event.payload.result : undefined;
            if (!isPlainRecord(result) || !Array.isArray(result.items)) {
                throw new Error('rag/documents: SUCCEEDED result.items required (array)');
            }
            return { ...state, items: documentRows(result.items) };
        }
        if (event.type === 'rag/document/status_updated') {
            const payload = event.payload;
            if (!isPlainRecord(payload)) {
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
            const items0 = documentRows(state.items);
            const idx = items0.findIndex((item) => item.document_id === documentId);
            if (idx === -1) {
                return state;
            }
            const prev = items0[idx];
            if (prev === undefined) {
                throw new Error('rag/documents: document row missing');
            }
            const nextItem = {
                ...prev,
                status,
                name: typeof payload.document_name === 'string' ? payload.document_name : prev.name,
                metadata: {
                    ...copyMetadata(prev.metadata),
                    error_message: typeof payload.error_message === 'string' ? payload.error_message : null,
                    chunks_count: typeof payload.chunks_count === 'number' ? payload.chunks_count : null,
                },
            };
            const items = items0.map((item, i) => (i === idx ? nextItem : item));
            return { ...state, items };
        }
        return state;
    },
    extraEffect: async (event, ctx, events) => {
        if (event.type !== 'rag/document/status_updated') {
            return false;
        }
        const payload = event.payload;
        if (!isPlainRecord(payload)) {
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
        if (loadedNamespaceId(ctx.getState()) !== namespaceId) {
            return true;
        }
        ctx.dispatch(
            requireEventName(events.REQUESTED, 'rag/documents REQUESTED'),
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
        const fields = uploadFields(payload);
        const spec = buildRagDocumentFileCreateSpecJson({
            namespaceId: fields.namespaceId,
            ragMetadata: fields.metadata,
        });
        const file =
            fields.file instanceof File
                ? fields.file
                : new File([fields.file], 'document.bin', {
                    type: fields.file.type.length > 0 ? fields.file.type : 'application/octet-stream',
                });
        const fileRecord = await uploadPlatformFile({ file, spec });
        if (!fileRecord || typeof fileRecord.file_id !== 'string') {
            throw new Error('rag/document_upload: file create response.file_id required');
        }
        return httpRequest({
            method: 'POST',
            url: `/rag/api/v1/namespaces/${encodeURIComponent(fields.namespaceId)}/documents/index-file`,
            body: {
                file_id: fileRecord.file_id,
                document_name: file.name,
                metadata: fields.metadata,
            },
        });
    },
    onSuccess: (ctx, result, event) => {
        if (!isPlainRecord(result) || typeof result.document_id !== 'string') {
            throw new Error('rag/document_upload: response.document_id required');
        }
        ctx.dispatch(
            requireEventName(documentStatusResource.events.REQUESTED, 'rag/document_status REQUESTED'),
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
            { namespace_id: removeNamespaceId(event.payload) },
            { causation_id: event.id, source: 'local' },
        );
    },
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'rag/documents': typeof documentsResource;
        'rag/document_upload': typeof documentUploadOp;
        'rag/document_remove': typeof documentRemoveOp;
    }
}
