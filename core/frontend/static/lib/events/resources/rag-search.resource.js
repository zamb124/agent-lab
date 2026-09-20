/**
 * Search — семантический поиск в одном namespace через WS RPC.
 *
 * POST /rag/api/v1/namespaces/{namespace_id}/search → тот же op_search_namespace.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';

export const searchOp = createAsyncOp({
    name: 'rag/search',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 20_000,
    commandType: 'rag/search/namespace_requested',
    restMirror: { method: 'POST', path: '/rag/api/v1/namespaces/:namespace_id/search' },
});

export const searchDefaultsOp = createAsyncOp({
    name: 'rag/search_defaults',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'rag/search/defaults_requested',
    restMirror: { method: 'GET', path: '/rag/api/v1/search-defaults' },
});
