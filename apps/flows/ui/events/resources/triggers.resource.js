/**
 * Triggers — триггеры flow'а (telegram polling, webhook).
 * REST: `apps/flows/src/api/v1/triggers.py`.
 *
 * Триггеры скоупятся по `flow_id` через явные операции (URL вида
 * `/flows/{flow_id}/triggers`), поэтому стандартный `createResourceCollection`
 * с одним `baseUrl` не подходит — используем явные `createAsyncOp`.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

const triggersBase = (flowId) => `/flows/api/v1/flows/${encodeURIComponent(flowId)}/triggers`;

export const triggersListOp = createAsyncOp({
    name: 'flows/triggers_list',
    silent: true,
    restMirror: { method: 'GET', path: '/flows/api/v1/flows/{flow_id}/triggers' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.flow_id !== 'string' || payload.flow_id.length === 0) {
            throw new Error('triggersListOp: { flow_id } required');
        }
        return httpRequest({ method: 'GET', url: triggersBase(payload.flow_id) });
    },
});

export const triggerGetOp = createAsyncOp({
    name: 'flows/trigger_get',
    silent: true,
    restMirror: { method: 'GET', path: '/flows/api/v1/flows/{flow_id}/triggers/{trigger_id}' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.flow_id !== 'string' || typeof payload.trigger_id !== 'string') {
            throw new Error('triggerGetOp: { flow_id, trigger_id } required');
        }
        return httpRequest({
            method: 'GET',
            url: `${triggersBase(payload.flow_id)}/${encodeURIComponent(payload.trigger_id)}`,
        });
    },
});

export const triggerCreateOp = createAsyncOp({
    name: 'flows/trigger_create',
    successToastKey: 'flows:toast.trigger_created',
    errorToastKey: 'flows:toast.trigger_create_error',
    restMirror: { method: 'POST', path: '/flows/api/v1/flows/{flow_id}/triggers' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.flow_id !== 'string' || !payload.body) {
            throw new Error('triggerCreateOp: { flow_id, body } required');
        }
        return httpRequest({
            method: 'POST',
            url: triggersBase(payload.flow_id),
            body: payload.body,
        });
    },
});

export const triggerUpdateOp = createAsyncOp({
    name: 'flows/trigger_update',
    successToastKey: 'flows:toast.trigger_updated',
    errorToastKey: 'flows:toast.trigger_update_error',
    restMirror: { method: 'PUT', path: '/flows/api/v1/flows/{flow_id}/triggers/{trigger_id}' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.flow_id !== 'string' || typeof payload.trigger_id !== 'string' || !payload.body) {
            throw new Error('triggerUpdateOp: { flow_id, trigger_id, body } required');
        }
        return httpRequest({
            method: 'PUT',
            url: `${triggersBase(payload.flow_id)}/${encodeURIComponent(payload.trigger_id)}`,
            body: payload.body,
        });
    },
});

export const triggerRemoveOp = createAsyncOp({
    name: 'flows/trigger_remove',
    successToastKey: 'flows:toast.trigger_removed',
    errorToastKey: 'flows:toast.trigger_remove_error',
    restMirror: { method: 'DELETE', path: '/flows/api/v1/flows/{flow_id}/triggers/{trigger_id}' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.flow_id !== 'string' || typeof payload.trigger_id !== 'string') {
            throw new Error('triggerRemoveOp: { flow_id, trigger_id } required');
        }
        return httpRequest({
            method: 'DELETE',
            url: `${triggersBase(payload.flow_id)}/${encodeURIComponent(payload.trigger_id)}`,
        });
    },
});

export const triggerTestOp = createAsyncOp({
    name: 'flows/trigger_test',
    successToastKey: 'flows:toast.trigger_tested',
    errorToastKey: 'flows:toast.trigger_test_error',
    restMirror: { method: 'POST', path: '/flows/api/v1/flows/{flow_id}/triggers/{trigger_id}/test' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.flow_id !== 'string' || typeof payload.trigger_id !== 'string') {
            throw new Error('triggerTestOp: { flow_id, trigger_id } required');
        }
        return httpRequest({
            method: 'POST',
            url: `${triggersBase(payload.flow_id)}/${encodeURIComponent(payload.trigger_id)}/test`,
            body: payload.body || {},
        });
    },
});
