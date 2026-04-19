/**
 * Integrations — OAuth credentials для внешних сервисов (Google, GitHub, Telegram).
 * REST: core/api/integrations.py (`/flows/api/v1/integrations/credentials`).
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

export const integrationsListOp = createAsyncOp({
    name: 'flows/integrations_list',
    silent: true,
    restMirror: { method: 'GET', path: '/flows/api/v1/integrations/credentials' },
    request: async () => {
        return httpRequest({ method: 'GET', url: '/flows/api/v1/integrations/credentials' });
    },
});

export const integrationsRemoveOp = createAsyncOp({
    name: 'flows/integrations_remove',
    successToastKey: 'flows:toast.integration_removed',
    errorToastKey: 'flows:toast.integration_remove_error',
    restMirror: { method: 'DELETE', path: '/flows/api/v1/integrations/credentials/{provider}/{service}' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.provider !== 'string' || typeof payload.service !== 'string') {
            throw new Error('integrationsRemoveOp: { provider, service } required');
        }
        return httpRequest({
            method: 'DELETE',
            url: `/flows/api/v1/integrations/credentials/${encodeURIComponent(payload.provider)}/${encodeURIComponent(payload.service)}`,
        });
    },
});
