/**
 * Каталог провайдеров речи.
 * Flows editor: WS `flows/voice_providers/catalog_requested`.
 * Console: HTTP GET /frontend/api/voice-providers/catalog (frontend без command-router).
 * Оба REST зовут один `op_voice_providers_catalog`.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

export const companyVoiceProvidersCatalogLoadOp = createAsyncOp({
    name: 'frontend/voice_providers_catalog_load',
    silent: true,
    transport: 'http',
    restMirror: {
        method: 'GET',
        path: '/frontend/api/voice-providers/catalog',
    },
    request: async () => httpRequest({
        method: 'GET',
        url: '/frontend/api/voice-providers/catalog',
    }),
});

export const flowsVoiceProvidersCatalogLoadOp = createAsyncOp({
    name: 'flows/voice_providers_catalog_load',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/voice_providers/catalog_requested',
    restMirror: {
        method: 'GET',
        path: '/flows/api/v1/voice-providers/catalog',
    },
});
