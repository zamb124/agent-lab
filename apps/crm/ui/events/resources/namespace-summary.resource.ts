/**
 * Namespace summary — агрегаты для дашборда CRM.
 *
 * Backend (`/crm/api/v1/namespaces`):
 *   GET /lara-summary → LaraNamespaceSummaryResponse
 */

import { createAsyncOp } from '@platform/lib/events/index.js';

export const laraSummaryOp = createAsyncOp({
    name: 'crm/lara_summary',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/namespaces/lara_summary_requested',
    restMirror: { method: 'GET', path: '/crm/api/v1/namespaces/lara-summary' },
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'crm/lara_summary': typeof laraSummaryOp;
    }
}
