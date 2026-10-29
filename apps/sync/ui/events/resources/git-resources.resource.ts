/**
 * Git-ресурсы Sync — git-ссылки в каналах.
 *
 * Транспорт WS (низкочастотные мутации, но через единый канал).
 * REST-зеркало: `apps/sync/api/git.py`.
 * Push `sync/git_resource/upserted` мержится в get-op lastResult / byId cache.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';
import type { AsyncOpSlice } from '@platform/lib/events/factories/async-op.js';

interface SyncGitResourceGetSlice extends AsyncOpSlice {
    byId: Readonly<Record<string, unknown>>;
}

function isGitGetSlice(state: AsyncOpSlice): state is SyncGitResourceGetSlice {
    return isPlainRecord(state.byId);
}

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
    transport: 'ws',
    wsTimeoutMs: 5_000,
    silent: true,
    commandType: 'sync/git_resources/get_requested',
    restMirror: { method: 'GET', path: '/sync/api/v1/git/resources/:git_ref_id' },
    extraInitial: {
        byId: Object.freeze({}),
    },
    extraReducer: (state, event) => {
        if (event.type !== 'sync/git_resource/upserted') {
            return state;
        }
        const payload = event.payload;
        if (!isPlainRecord(payload)) {
            return state;
        }
        const gitRefId = payload.git_ref_id;
        if (typeof gitRefId !== 'string' || gitRefId.length === 0) {
            return state;
        }
        if (!isGitGetSlice(state)) {
            throw new Error('sync/git_resource_get: byId must be an object');
        }
        const byId = Object.freeze({ ...state.byId, [gitRefId]: payload });
        const last = state.lastResult;
        const lastResult = isPlainRecord(last) && last.git_ref_id === gitRefId
            ? payload
            : last;
        return { ...state, byId, lastResult };
    },
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'sync/git_resources_upsert': typeof gitResourceUpsertOp;
        'sync/git_resource_get': typeof gitResourceGetOp;
    }
}
