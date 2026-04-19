/**
 * Sync Git Resources — git-ссылки в каналах.
 *
 * Транспорт WS (низкочастотные мутации, но через единый канал).
 * REST-зеркало: `apps/sync/api/git.py`.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';

export const gitResourceUpsertOp = createAsyncOp({
    name: 'sync/git_resources_upsert',
    transport: 'ws',
    wsTimeoutMs: 5_000,
    successToastKey: 'sync:git_resources.toast_upserted',
    errorToastKey: 'sync:git_resources.err_upsert',
    commandType: 'sync/git_resources/upsert_requested',
    restMirror: { method: 'POST', path: '/sync/api/v1/git/resources' },
});

export const gitResourceGetOp = createAsyncOp({
    name: 'sync/git_resource_get',
    transport: 'http',
    silent: true,
    restMirror: { method: 'GET', path: '/sync/api/v1/git/resources/:git_ref_id' },
    request: async ({ payload }) => {
        const { httpRequest } = await import('@platform/lib/events/http.js');
        return httpRequest({
            method: 'GET',
            url: `/sync/api/v1/git/resources/${encodeURIComponent(payload.git_ref_id)}`,
        });
    },
});
