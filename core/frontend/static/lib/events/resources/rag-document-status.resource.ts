/**
 * Document Status — снимок GET через WS RPC; push `rag/document/status_updated`.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
import type { PlatformEvent, EffectCtx } from '@platform/lib/events/contract.js';
import { isPlainRecord } from '../payload.js';
import type { AsyncOpSlice } from '../factories/async-op.js';
import type {
    DocumentProcessingStatus,
    RagDocumentStatusUpdatedEventPayload,
} from '../wire/rag.gen.js';

/**
 * Push `rag/document/status_updated` без company_id — форма, которую
 * reducer складывает в lastResult; полный payload — RagEventMap.
 */
type DocumentStatusView = Omit<RagDocumentStatusUpdatedEventPayload, 'company_id'>;

const RAG_DOCUMENT_STATUS_UPDATED = 'rag/document/status_updated';

function requestDocumentId(payload: unknown): string {
    if (!isPlainRecord(payload)) return '';
    const documentId = payload.document_id;
    return typeof documentId === 'string' ? documentId : '';
}

function _toastTerminal(ctx: EffectCtx, status: Record<string, unknown>, documentId: string, causationId: string): void {
    const name = status.document_name;
    const documentName = typeof name === 'string' ? name : documentId;
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

export const documentStatusResource = createAsyncOp<
    DocumentProcessingStatus,
    AsyncOpSlice<DocumentProcessingStatus | DocumentStatusView>
>({
    name: 'rag/document_status',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'rag/documents/status_requested',
    restMirror: { method: 'GET', path: '/rag/api/v1/documents/:document_id/status' },
    onSuccess: (ctx, status, event) => {
        if (!isPlainRecord(status)) {
            throw new Error('rag document status: result must be an object');
        }
        _toastTerminal(ctx, status, requestDocumentId(event.payload), event.id);
    },
    extraReducer: (state, event) => {
        if (event.type !== RAG_DOCUMENT_STATUS_UPDATED) {
            return state;
        }
        if (!isPlainRecord(event.payload)) {
            return state;
        }
        const payload = event.payload;
        const documentId = payload.document_id;
        const status = payload.status;
        const namespaceId = payload.namespace_id;
        if (typeof documentId !== 'string' || documentId.length === 0) {
            return state;
        }
        if (typeof status !== 'string' || typeof namespaceId !== 'string') {
            return state;
        }
        const documentName = payload.document_name;
        const errorMessage = payload.error_message;
        const chunksCount = payload.chunks_count;
        const nextStatus: DocumentStatusView = {
            document_id: documentId,
            status,
            document_name: typeof documentName === 'string' ? documentName : documentId,
            error_message: typeof errorMessage === 'string' ? errorMessage : null,
            chunks_count: typeof chunksCount === 'number' ? chunksCount : null,
            namespace_id: namespaceId,
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

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'rag/document_status': typeof documentStatusResource;
    }
}
