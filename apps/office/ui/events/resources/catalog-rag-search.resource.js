/**
 * Office catalog semantic search — POST rag-index/search.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';
import { nsHeader } from './_namespace-header.js';

function _catalogIdFromPayload(payload, opName) {
    if (!payload || typeof payload.catalogId !== 'string' || payload.catalogId.length === 0) {
        throw new Error(`${opName}: payload.catalogId required`);
    }
    return payload.catalogId;
}

export const catalogRagSearchOp = createAsyncOp({
    name: 'office/catalog_rag_search',
    silent: true,
    restMirror: {
        method: 'POST',
        path: '/documents/api/v1/catalogs/:catalog_id/rag-index/search',
    },
    request: ({ payload, ctx }) => {
        const catalogId = _catalogIdFromPayload(payload, 'office/catalog_rag_search');
        const query = payload && typeof payload.query === 'string' ? payload.query.trim() : '';
        if (query.length === 0) {
            throw new Error('office/catalog_rag_search: payload.query required');
        }
        const limit = payload && typeof payload.limit === 'number' ? payload.limit : 20;
        return httpRequest({
            method: 'POST',
            url: `/documents/api/v1/catalogs/${encodeURIComponent(catalogId)}/rag-index/search`,
            headers: nsHeader(ctx),
            body: { query, limit },
        });
    },
});
