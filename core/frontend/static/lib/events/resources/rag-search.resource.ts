/**
 * Search — семантический поиск в одном namespace через WS RPC.
 *
 * POST /rag/api/v1/namespaces/{namespace_id}/search → тот же op_search_namespace.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import type { RAGSearchOptions, SearchResponse } from '../wire/rag.gen.js';

export const searchOp = createAsyncOp<SearchResponse>({
    name: 'rag/search',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 20_000,
    commandType: 'rag/search/namespace_requested',
    restMirror: { method: 'POST', path: '/rag/api/v1/namespaces/:namespace_id/search' },
});

export const searchDefaultsOp = createAsyncOp<RAGSearchOptions>({
    name: 'rag/search_defaults',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'rag/search/defaults_requested',
    restMirror: { method: 'GET', path: '/rag/api/v1/search-defaults' },
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'rag/search': typeof searchOp;
        'rag/search_defaults': typeof searchDefaultsOp;
    }
}
