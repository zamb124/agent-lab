/**
 * Workspace — агрегаты для дашборда CRM.
 *
 * Backend (`/crm/api/v1/workspace`):
 *   GET /lara-summary → LaraWorkspaceSummaryResponse
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

export const laraSummaryOp = createAsyncOp({
    name: 'crm/lara_summary',
    silent: true,
    restMirror: { method: 'GET', path: '/crm/api/v1/workspace/lara-summary' },
    request: async () => {
        return await httpRequest({
            method: 'GET',
            url: '/crm/api/v1/workspace/lara-summary',
        });
    },
});
