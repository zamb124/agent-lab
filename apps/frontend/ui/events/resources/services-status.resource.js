/**
 * Services status resource — health всех микросервисов платформы.
 *
 * API: GET /frontend/api/services/status → { services: [{id, name, healthy, ...}] }
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
    }),
});
