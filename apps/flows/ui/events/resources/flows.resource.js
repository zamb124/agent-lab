/**
 * Flows — каталог потоков (flow_id, конфиг, версии).
 *
 * REST-зеркало живёт в `apps/flows/src/api/v1/flows.py`.
 * Каталог, preview-share и voice-session-query — `transport: 'ws'`, тот же `op_*` что и HTTP.
 */

import { createResourceCollection, createAsyncOp } from '@platform/lib/events/index.js';

export const flowsResource = createResourceCollection({
    name: 'flows/flows',
    baseUrl: '/flows/api/v1/flows',
    idField: 'flow_id',
    operations: ['list', 'get', 'create', 'remove'],
    transport: 'ws',
    wsTimeoutMs: 15_000,
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
    extraReducer: (state, event) => {
        if (event.type === 'flows/flow/deleted') {
            const flowId = event.payload && typeof event.payload.flow_id === 'string'
                ? event.payload.flow_id
                : '';
            if (flowId.length === 0) {
                return state;
            }
            const items = state.items.filter((item) => item && item.flow_id !== flowId);
            const byId = { ...state.byId };
            delete byId[flowId];
            return { ...state, items, byId };
        }
        if (event.type === 'flows/flow/updated') {
            const payload = event.payload;
            if (!payload || typeof payload.flow_id !== 'string') {
                return state;
            }
            const existing = state.byId[payload.flow_id];
            if (!existing || typeof existing !== 'object') {
                return state;
            }
            const version = typeof payload.version === 'string' ? payload.version : existing.version;
            const patched = { ...existing, version };
            const idx = state.items.findIndex((x) => x && x.flow_id === payload.flow_id);
            const items = idx === -1
                ? state.items
                : state.items.map((x, i) => (i === idx ? patched : x));
            return {
                ...state,
                items,
                byId: { ...state.byId, [payload.flow_id]: patched },
            };
        }
        return state;
    },
    extraEffect: async (event, ctx, events) => {
        const refreshTypes = new Set([
            'flows/flow/updated',
            'flows/branch/created',
            'flows/branch/updated',
            'flows/branch/deleted',
        ]);
        if (refreshTypes.has(event.type)) {
            const flowId = event.payload && typeof event.payload.flow_id === 'string'
                ? event.payload.flow_id
                : '';
            if (flowId.length === 0) {
                return true;
            }
            ctx.dispatch(
                events.ITEM_REQUESTED,
                { flow_id: flowId },
                { causation_id: event.id, source: 'ws' },
            );
            return true;
        }
        if (event.type === 'flows/flow/deleted') {
            ctx.dispatch(
                events.LIST_REQUESTED,
                {},
                { causation_id: event.id, source: 'ws' },
            );
            return true;
        }
        return false;
    },
});

// Бэкенд требует PUT (а не PATCH, как у дефолтного `createResourceCollection.update`),
// поэтому update вынесен в отдельный AsyncOp.
export const flowUpdateOp = createAsyncOp({
    name: 'flows/flow_update',
    successToastKey: 'flows:toast.flow_updated',
    errorToastKey: 'flows:toast.flow_update_error',
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/flows/update_requested',
    restMirror: { method: 'PUT', path: '/flows/api/v1/flows/{flow_id}' },
});

export const flowReloadFromBundleOp = createAsyncOp({
    name: 'flows/flow_reload_from_bundle',
    successToastKey: 'flows:toast.flow_reloaded',
    errorToastKey: 'flows:toast.flow_reload_error',
    transport: 'ws',
    wsTimeoutMs: 30_000,
    commandType: 'flows/flows/reload_from_bundle_requested',
    restMirror: { method: 'POST', path: '/flows/api/v1/flows/{flow_id}/reload-from-bundle' },
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
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/flows/versions_list_requested',
    restMirror: { method: 'GET', path: '/flows/api/v1/flows/{flow_id}/versions' },
});

export const flowStoreBundlesOp = createAsyncOp({
    name: 'flows/flow_store_bundles',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/flows/store_bundles_requested',
    restMirror: { method: 'GET', path: '/flows/api/v1/flows/store/bundles' },
});

export const flowValidateOp = createAsyncOp({
    name: 'flows/flow_validate',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/flows/validate_requested',
    restMirror: { method: 'POST', path: '/flows/api/v1/flows/validate' },
});

export const flowVoiceSessionQueryOp = createAsyncOp({
    name: 'flows/flow_voice_session_query',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/flows/voice_session_query_requested',
    restMirror: {
        method: 'GET',
        path: '/flows/api/v1/flows/{flow_id}/voice-session-query',
    },
});

export const flowPreviewShareOp = createAsyncOp({
    name: 'flows/flow_preview_share',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/flows/preview_share_requested',
    restMirror: { method: 'POST', path: '/flows/api/v1/flows/{flow_id}/preview-share' },
});

export const branchCreateOp = createAsyncOp({
    name: 'flows/branch_create',
    successToastKey: 'flows:toast.branch_created',
    errorToastKey: 'flows:toast.branch_create_error',
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/flows/branch_create_requested',
    restMirror: { method: 'POST', path: '/flows/api/v1/{flow_id}/branches' },
});

export const branchUpdateOp = createAsyncOp({
    name: 'flows/branch_update',
    successToastKey: 'flows:toast.branch_updated',
    errorToastKey: 'flows:toast.branch_update_error',
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/flows/branch_update_requested',
    restMirror: { method: 'PUT', path: '/flows/api/v1/{flow_id}/branches/{branch_id}' },
});

export const branchRemoveOp = createAsyncOp({
    name: 'flows/branch_remove',
    successToastKey: 'flows:toast.branch_removed',
    errorToastKey: 'flows:toast.branch_remove_error',
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/flows/branch_remove_requested',
    restMirror: { method: 'DELETE', path: '/flows/api/v1/{flow_id}/branches/{branch_id}' },
});
