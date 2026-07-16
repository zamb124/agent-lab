/**
 * Namespace summary — агрегаты для дашборда CRM.
 *
 * Backend (`/crm/api/v1/namespaces`):
 *   GET /lara-summary → LaraNamespaceSummaryResponse
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

export const laraSummaryOp = createAsyncOp({
    name: 'crm/lara_summary',
    silent: true,
    restMirror: { method: 'GET', path: '/crm/api/v1/namespaces/lara-summary' },
    request: async (payload) => {
        if (!payload || typeof payload.namespace !== 'string' || payload.namespace.trim() === '') {
            throw new Error('crm/lara_summary requires namespace');
        }
        const query = new URLSearchParams({ namespace: payload.namespace.trim() });
        return await httpRequest({
            method: 'GET',
            url: `/crm/api/v1/namespaces/lara-summary?${query.toString()}`,
        });
    },
});
