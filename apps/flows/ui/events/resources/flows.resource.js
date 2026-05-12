/**
 * Flows — каталог потоков (flow_id, конфиг, версии).
 *
 * REST-зеркало живёт в `apps/flows/src/api/v1/flows.py`.
 * Все операции — `transport: 'http'` (CRUD без долгоживущей подписки).
 */

import { createResourceCollection, createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';
import { fetchFlowVoiceSessionQueryDict } from '@platform/lib/voice/fetch-flow-voice-session-query.js';

export const flowsResource = createResourceCollection({
    name: 'flows/flows',
    baseUrl: '/flows/api/v1/flows',
    idField: 'flow_id',
    operations: ['list', 'get', 'create', 'remove'],
    toastKeys: {
        create: 'flows:toast.flow_created',
        create_error: 'flows:toast.flow_create_error',
        remove: 'flows:toast.flow_removed',
        remove_error: 'flows:toast.flow_remove_error',
    },
    listQuery: (payload) => {
        const query = {};
        if (payload && typeof payload === 'object') {
            if (typeof payload.limit === 'number') query.limit = payload.limit;
            if (typeof payload.offset === 'number') query.offset = payload.offset;
        }
        return query;
    },
});

// Backend требует PUT (а не PATCH, как у дефолтного `createResourceCollection.update`),
// поэтому update вынесен в отдельный AsyncOp.
export const flowUpdateOp = createAsyncOp({
    name: 'flows/flow_update',
    successToastKey: 'flows:toast.flow_updated',
    errorToastKey: 'flows:toast.flow_update_error',
    restMirror: { method: 'PUT', path: '/flows/api/v1/flows/{flow_id}' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.flow_id !== 'string' || payload.flow_id.length === 0 || !payload.body) {
            throw new Error('flowUpdateOp: { flow_id, body } required');
        }
        return httpRequest({
            method: 'PUT',
            url: `/flows/api/v1/flows/${encodeURIComponent(payload.flow_id)}`,
            body: payload.body,
        });
    },
});

export const flowReloadFromBundleOp = createAsyncOp({
    name: 'flows/flow_reload_from_bundle',
    successToastKey: 'flows:toast.flow_reloaded',
    errorToastKey: 'flows:toast.flow_reload_error',
    restMirror: { method: 'POST', path: '/flows/api/v1/flows/{flow_id}/reload-from-bundle' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.flow_id !== 'string' || payload.flow_id.length === 0) {
            throw new Error('flowReloadFromBundleOp: { flow_id } required');
        }
        return httpRequest({
            method: 'POST',
            url: `/flows/api/v1/flows/${encodeURIComponent(payload.flow_id)}/reload-from-bundle`,
            body: {},
        });
    },
    onSuccess: (ctx, _result, event) => {
        const id = event?.payload?.flow_id;
        if (typeof id !== 'string' || id.length === 0) {
            throw new Error('flowReloadFromBundleOp.onSuccess: payload.flow_id required');
        }
        ctx.dispatch(
            flowsResource.events.ITEM_REQUESTED,
            { flow_id: id },
            { causation_id: event.id, source: 'local' },
        );
    },
});

export const flowVersionsListOp = createAsyncOp({
    name: 'flows/flow_versions_list',
    silent: true,
    restMirror: { method: 'GET', path: '/flows/api/v1/flows/{flow_id}/versions' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.flow_id !== 'string' || payload.flow_id.length === 0) {
            throw new Error('flowVersionsListOp: { flow_id } required');
        }
        return httpRequest({
            method: 'GET',
            url: `/flows/api/v1/flows/${encodeURIComponent(payload.flow_id)}/versions`,
        });
    },
});

export const flowStoreBundlesOp = createAsyncOp({
    name: 'flows/flow_store_bundles',
    silent: true,
    restMirror: { method: 'GET', path: '/flows/api/v1/flows/store/bundles' },
    request: async () => {
        return httpRequest({
            method: 'GET',
            url: '/flows/api/v1/flows/store/bundles',
        });
    },
});

export const flowValidateOp = createAsyncOp({
    name: 'flows/flow_validate',
    silent: true,
    restMirror: { method: 'POST', path: '/flows/api/v1/flows/validate' },
    request: async ({ payload }) => {
        if (!payload || typeof payload !== 'object') {
            throw new Error('flowValidateOp: payload required');
        }
        return httpRequest({
            method: 'POST',
            url: '/flows/api/v1/flows/validate',
            body: payload,
        });
    },
});

export const flowVoiceSessionQueryOp = createAsyncOp({
    name: 'flows/flow_voice_session_query',
    silent: true,
    restMirror: {
        method: 'GET',
        path: '/flows/api/v1/flows/{flow_id}/voice-session-query',
    },
    request: async ({ payload }) => {
        if (!payload || typeof payload.flow_id !== 'string' || payload.flow_id.length === 0) {
            throw new Error('flowVoiceSessionQueryOp: flow_id required');
        }
        const branchRaw =
            typeof payload.branch_id === 'string' && payload.branch_id.trim() !== ''
                ? payload.branch_id
                : undefined;
        const query = await fetchFlowVoiceSessionQueryDict({
            flowsApiRoot: '/flows',
            flowId: payload.flow_id,
            branchId: branchRaw,
            credentials: 'include',
            getHeaders: async () => ({}),
        });
        return { query };
    },
});

export const flowPreviewShareOp = createAsyncOp({
    name: 'flows/flow_preview_share',
    silent: true,
    restMirror: { method: 'POST', path: '/flows/api/v1/flows/{flow_id}/preview-share' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.flow_id !== 'string' || payload.flow_id.length === 0) {
            throw new Error('flowPreviewShareOp: { flow_id, branch_id? } required');
        }
        const branchRaw = typeof payload.branch_id === 'string' && payload.branch_id.trim() !== ''
            ? payload.branch_id.trim()
            : 'default';
        const body = { branch_id: branchRaw };
        if (payload.guest_max_user_messages != null) {
            if (typeof payload.guest_max_user_messages !== 'number' || !Number.isFinite(payload.guest_max_user_messages)) {
                throw new Error('flowPreviewShareOp: guest_max_user_messages must be a finite number when set');
            }
            body.guest_max_user_messages = Math.trunc(payload.guest_max_user_messages);
        }
        return httpRequest({
            method: 'POST',
            url: `/flows/api/v1/flows/${encodeURIComponent(payload.flow_id)}/preview-share`,
            body,
        });
    },
});

// Ветки графа (HTTP в `apps/flows/src/api/a2a.py`, тот же prefix `/flows/api/v1`).
export const branchCreateOp = createAsyncOp({
    name: 'flows/branch_create',
    successToastKey: 'flows:toast.branch_created',
    errorToastKey: 'flows:toast.branch_create_error',
    restMirror: { method: 'POST', path: '/flows/api/v1/{flow_id}/branches' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.flow_id !== 'string' || !payload.body) {
            throw new Error('branchCreateOp: { flow_id, body } required');
        }
        return httpRequest({
            method: 'POST',
            url: `/flows/api/v1/${encodeURIComponent(payload.flow_id)}/branches`,
            body: payload.body,
        });
    },
});

export const branchUpdateOp = createAsyncOp({
    name: 'flows/branch_update',
    successToastKey: 'flows:toast.branch_updated',
    errorToastKey: 'flows:toast.branch_update_error',
    restMirror: { method: 'PUT', path: '/flows/api/v1/{flow_id}/branches/{branch_id}' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.flow_id !== 'string' || typeof payload.branch_id !== 'string' || !payload.body) {
            throw new Error('branchUpdateOp: { flow_id, branch_id, body } required');
        }
        return httpRequest({
            method: 'PUT',
            url: `/flows/api/v1/${encodeURIComponent(payload.flow_id)}/branches/${encodeURIComponent(payload.branch_id)}`,
            body: payload.body,
        });
    },
});

export const branchRemoveOp = createAsyncOp({
    name: 'flows/branch_remove',
    successToastKey: 'flows:toast.branch_removed',
    errorToastKey: 'flows:toast.branch_remove_error',
    restMirror: { method: 'DELETE', path: '/flows/api/v1/{flow_id}/branches/{branch_id}' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.flow_id !== 'string' || typeof payload.branch_id !== 'string') {
            throw new Error('branchRemoveOp: { flow_id, branch_id } required');
        }
        return httpRequest({
            method: 'DELETE',
            url: `/flows/api/v1/${encodeURIComponent(payload.flow_id)}/branches/${encodeURIComponent(payload.branch_id)}`,
        });
    },
});
