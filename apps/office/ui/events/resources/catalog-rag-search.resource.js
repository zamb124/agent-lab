/**
 * Office catalog semantic search — POST rag-index/search.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';

export const catalogRagSearchOp = createAsyncOp({
    name: 'office/catalog_rag_search',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 12_000,
    commandType: 'office/catalogs/rag_search_requested',
    restMirror: {
        method: 'POST',
        path: '/documents/api/v1/catalogs/:catalog_id/rag-index/search',
    },
});
