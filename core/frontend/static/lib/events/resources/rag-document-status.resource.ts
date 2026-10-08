/**
 * Document Status — снимок GET через WS RPC; push `rag/document/status_updated`.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
import type { PlatformEvent, EffectCtx } from '@platform/lib/events/contract.js';

interface DocumentStatusPush {
    document_id: string;
    status?: unknown;
    document_name?: unknown;
    error_message?: unknown;
    chunks_count?: unknown;
    namespace_id?: unknown;
}

const RAG_DOCUMENT_STATUS_UPDATED = 'rag/document/status_updated';

function _toastTerminal(ctx: EffectCtx, status: DocumentStatusPush, documentId: string, causationId: string): void {
    const documentName = typeof status.document_name === 'string' ? status.document_name : documentId;
    if (status.status === 'completed') {
        ctx.dispatch(
            CoreEvents.UI_TOAST_SHOW,
            { type: 'success', i18n_key: 'rag:toast.document_processed', i18n_vars: { name: documentName } },
            { causation_id: causationId },
        );
        return;
    }
    if (status.status === 'failed') {
        ctx.dispatch(
            CoreEvents.UI_TOAST_SHOW,
            { type: 'error', i18n_key: 'rag:toast.document_process_failed', i18n_vars: { name: documentName } },
            { causation_id: causationId },
        );
    }
}

export const documentStatusResource = createAsyncOp({
    name: 'rag/document_status',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'rag/documents/status_requested',
    restMirror: { method: 'GET', path: '/rag/api/v1/documents/:document_id/status' },
    onSuccess: (ctx, status, event) => {
        const documentId = (event.payload as { document_id?: string } | null)?.document_id ?? '';
        _toastTerminal(ctx, status as DocumentStatusPush, documentId, event.id);
    },
    extraReducer: (state, event) => {
        if (event.type !== RAG_DOCUMENT_STATUS_UPDATED) {
            return state;
        }
        const payload = event.payload as DocumentStatusPush | null;
        if (!payload || typeof payload !== 'object') {
            return state;
        }
        const documentId = payload.document_id;
        if (typeof documentId !== 'string' || documentId.length === 0) {
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

export { RAG_DOCUMENT_STATUS_UPDATED };
