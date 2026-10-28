/**
 * Triggers — триггеры flow'а (telegram polling, webhook).
 * REST: `apps/flows/src/api/v1/triggers.py`.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';

export const triggersListOp = createAsyncOp({
    name: 'flows/triggers_list',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/triggers/list_requested',
    restMirror: { method: 'GET', path: '/flows/api/v1/flows/{flow_id}/triggers' },
});

export const triggerGetOp = createAsyncOp({
    name: 'flows/trigger_get',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/triggers/item_requested',
    restMirror: { method: 'GET', path: '/flows/api/v1/flows/{flow_id}/triggers/{trigger_id}' },
});

export const triggerCreateOp = createAsyncOp({
    name: 'flows/trigger_create',
    successToastKey: 'flows:toast.trigger_created',
    errorToastKey: 'flows:toast.trigger_create_error',
    transport: 'ws',
    wsTimeoutMs: 30_000,
    commandType: 'flows/triggers/create_requested',
    restMirror: { method: 'POST', path: '/flows/api/v1/flows/{flow_id}/triggers' },
});

export const triggerUpdateOp = createAsyncOp({
    name: 'flows/trigger_update',
    successToastKey: 'flows:toast.trigger_updated',
    errorToastKey: 'flows:toast.trigger_update_error',
    transport: 'ws',
    wsTimeoutMs: 30_000,
    commandType: 'flows/triggers/update_requested',
    restMirror: { method: 'PUT', path: '/flows/api/v1/flows/{flow_id}/triggers/{trigger_id}' },
});

export const triggerRemoveOp = createAsyncOp({
    name: 'flows/trigger_remove',
    successToastKey: 'flows:toast.trigger_removed',
    errorToastKey: 'flows:toast.trigger_remove_error',
    transport: 'ws',
    wsTimeoutMs: 30_000,
    commandType: 'flows/triggers/remove_requested',
    restMirror: { method: 'DELETE', path: '/flows/api/v1/flows/{flow_id}/triggers/{trigger_id}' },
});

export const triggerVerifyOp = createAsyncOp({
    name: 'flows/trigger_verify',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 30_000,
    commandType: 'flows/triggers/verify_requested',
    restMirror: { method: 'POST', path: '/flows/api/v1/flows/{flow_id}/triggers/verify' },
});

export const triggerReregisterOp = createAsyncOp({
    name: 'flows/trigger_reregister',
    successToastKey: 'flows:toast.trigger_reregistered',
    errorToastKey: 'flows:toast.trigger_reregister_error',
    transport: 'ws',
    wsTimeoutMs: 30_000,
    commandType: 'flows/triggers/reregister_requested',
    restMirror: {
        method: 'POST',
        path: '/flows/api/v1/flows/{flow_id}/triggers/{trigger_id}/reregister',
    },
});

export const platformEventsCatalogOp = createAsyncOp({
    name: 'flows/platform_events_catalog',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/platform_events/catalog_requested',
    restMirror: { method: 'GET', path: '/flows/api/v1/platform-events/catalog' },
});

export const triggerTestOp = createAsyncOp({
    name: 'flows/trigger_test',
    successToastKey: 'flows:toast.trigger_tested',
    errorToastKey: 'flows:toast.trigger_test_error',
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/triggers/test_requested',
    restMirror: { method: 'POST', path: '/flows/api/v1/flows/{flow_id}/triggers/{trigger_id}/test' },
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'flows/triggers_list': typeof triggersListOp;
        'flows/trigger_get': typeof triggerGetOp;
        'flows/trigger_create': typeof triggerCreateOp;
        'flows/trigger_update': typeof triggerUpdateOp;
        'flows/trigger_remove': typeof triggerRemoveOp;
        'flows/trigger_verify': typeof triggerVerifyOp;
        'flows/trigger_reregister': typeof triggerReregisterOp;
        'flows/platform_events_catalog': typeof platformEventsCatalogOp;
        'flows/trigger_test': typeof triggerTestOp;
    }
}
