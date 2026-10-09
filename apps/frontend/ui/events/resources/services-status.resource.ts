/**
 * Публичная витрина health микросервисов — anonymous `GET /frontend/api/services/status`
 * (`OffsetPage[ServiceStatus]`), доступна и до сессии, поэтому HTTP, не команда.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

export const servicesStatusLoadOp = createAsyncOp({
    name: 'frontend/services_status_load',
    silent: true,
    restMirror: { method: 'GET', path: '/frontend/api/services/status' },
    request: async () => await httpRequest({
        method: 'GET',
        url: '/frontend/api/services/status',
        query: { limit: 100, offset: 0 },
    }),
});
