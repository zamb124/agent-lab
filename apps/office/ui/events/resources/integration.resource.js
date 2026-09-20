/**
 * OnlyOffice Integration Status — readonly статус конфигурации DS.
 *
 * GET /documents/api/v1/integration/status → OfficeIntegrationStatusResponse.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';

export const integrationStatusOp = createAsyncOp({
    name: 'office/integration_status',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'office/integration/status_requested',
    restMirror: { method: 'GET', path: '/documents/api/v1/integration/status' },
});
