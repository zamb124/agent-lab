/**
 * Search — семантический поиск в рамках одного namespace.
 *
 * Бэкенд:
 *   POST /rag/api/v1/namespaces/{namespace_id}/search (SearchRequest)
 *     → SearchResponse { results, query, namespace_id, provider }
 *
 * Глобальный поиск `POST /rag/api/v1/search` пока не подключён —
 * UI его не использует. Появится отдельной фабрикой при необходимости.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

export const searchOp = createAsyncOp({
    name: 'rag/search',
    silent: true,
    restMirror: { method: 'POST', path: '/rag/api/v1/namespaces/:namespace_id/search' },
    request: ({ payload }) => {
        if (!payload || typeof payload.namespaceId !== 'string' || payload.namespaceId.length === 0) {
            throw new Error('rag/search: payload.namespaceId required');
        }
        if (typeof payload.query !== 'string' || payload.query.length === 0) {
            throw new Error('rag/search: payload.query required (non-empty string)');
        }
        const limit = typeof payload.limit === 'number' ? payload.limit : 5;
        const body = { query: payload.query, limit };
        if (payload.filters !== undefined && payload.filters !== null) {
            body.filters = payload.filters;
        }
        return httpRequest({
            method: 'POST',
            url: `/rag/api/v1/namespaces/${encodeURIComponent(payload.namespaceId)}/search`,
            body,
        });
    },
});
