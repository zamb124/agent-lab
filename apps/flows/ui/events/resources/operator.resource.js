/**
 * Operator workbench — очереди и задачи операторов.
 * REST: `apps/flows/src/api/v1/operator.py`.
 *
 * Push-событие `notify/flows/flows_operator_tasks_updated_received`
 * (см. `apps/flows/src/services/operator_tasks_broadcast.py`) триггерит
 * перезагрузку списка задач — подписку оформляет страница оператора.
 *
 * `claim`/`postMessage`/`complete` — `transport: 'ws'`; для каждой задан
 * `commandType` как в `apps/flows/src/realtime/command_router.py` (иначе
 * из имени фабрики получился бы невалидный WS-тип вида
 * `flows/operator_task_claim/requested` без суффикса `_requested` на третьем сегменте).
 */

import { createResourceCollection, createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

export const operatorQueuesResource = createResourceCollection({
    name: 'flows/operator_queues',
    baseUrl: '/flows/api/v1/operator/queues',
    idField: 'id',
    operations: ['list', 'create', 'update'],
    // restMirror.update — реальный path FastAPI
    // (`@router.patch("/queues/{queue_id}")` в `apps/flows/src/api/v1/operator.py`).
    restMirror: {
        update: { method: 'PATCH', path: '/flows/api/v1/operator/queues/:queue_id' },
    },
    toastKeys: {
        create: 'flows:toast.operator_queue_created',
        create_error: 'flows:toast.operator_queue_create_error',
        update: 'flows:toast.operator_queue_updated',
        update_error: 'flows:toast.operator_queue_update_error',
    },
});

export const operatorQueueAddMemberOp = createAsyncOp({
    name: 'flows/operator_queue_add_member',
    successToastKey: 'flows:toast.operator_member_added',
    errorToastKey: 'flows:toast.operator_member_add_error',
    restMirror: { method: 'POST', path: '/flows/api/v1/operator/queues/{queue_id}/members' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.queue_id !== 'string' || !payload.body) {
            throw new Error('operatorQueueAddMemberOp: { queue_id, body } required');
        }
        return httpRequest({
            method: 'POST',
            url: `/flows/api/v1/operator/queues/${encodeURIComponent(payload.queue_id)}/members`,
            body: payload.body,
        });
    },
});

export const operatorQueueRemoveMemberOp = createAsyncOp({
    name: 'flows/operator_queue_remove_member',
    successToastKey: 'flows:toast.operator_member_removed',
    errorToastKey: 'flows:toast.operator_member_remove_error',
    restMirror: { method: 'DELETE', path: '/flows/api/v1/operator/queues/{queue_id}/members/{member_user_id}' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.queue_id !== 'string' || typeof payload.member_user_id !== 'string') {
            throw new Error('operatorQueueRemoveMemberOp: { queue_id, member_user_id } required');
        }
        return httpRequest({
            method: 'DELETE',
            url: `/flows/api/v1/operator/queues/${encodeURIComponent(payload.queue_id)}/members/${encodeURIComponent(payload.member_user_id)}`,
        });
    },
});

export const operatorTasksListOp = createAsyncOp({
    name: 'flows/operator_tasks_list',
    silent: true,
    restMirror: { method: 'GET', path: '/flows/api/v1/operator/tasks' },
    request: async ({ payload }) => {
        const params = new URLSearchParams();
        if (payload && typeof payload === 'object') {
            if (typeof payload.queue_id === 'string') params.append('queue_id', payload.queue_id);
            if (typeof payload.status === 'string') params.append('status', payload.status);
            if (typeof payload.limit === 'number') params.append('limit', String(payload.limit));
            if (typeof payload.offset === 'number') params.append('offset', String(payload.offset));
        }
        const qs = params.toString();
        return httpRequest({
            method: 'GET',
            url: `/flows/api/v1/operator/tasks${qs ? '?' + qs : ''}`,
        });
    },
});

export const operatorTaskGetOp = createAsyncOp({
    name: 'flows/operator_task_get',
    silent: true,
    restMirror: { method: 'GET', path: '/flows/api/v1/operator/tasks/{task_id}' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.task_id !== 'string' || payload.task_id.length === 0) {
            throw new Error('operatorTaskGetOp: { task_id } required');
        }
        return httpRequest({
            method: 'GET',
            url: `/flows/api/v1/operator/tasks/${encodeURIComponent(payload.task_id)}`,
        });
    },
});

export const operatorTaskClaimOp = createAsyncOp({
    name: 'flows/operator_task_claim',
    transport: 'ws',
    wsTimeoutMs: 5_000,
    commandType: 'flows/operator_task/claim_requested',
    successToastKey: 'flows:toast.operator_task_claimed',
    errorToastKey: 'flows:toast.operator_task_claim_error',
    restMirror: { method: 'POST', path: '/flows/api/v1/operator/tasks/{task_id}/claim' },
});

export const operatorTaskPostMessageOp = createAsyncOp({
    name: 'flows/operator_task_post_message',
    transport: 'ws',
    wsTimeoutMs: 5_000,
    commandType: 'flows/operator_task/post_message_requested',
    silent: true,
    restMirror: { method: 'POST', path: '/flows/api/v1/operator/tasks/{task_id}/messages' },
});

export const operatorTaskCompleteOp = createAsyncOp({
    name: 'flows/operator_task_complete',
    transport: 'ws',
    wsTimeoutMs: 5_000,
    commandType: 'flows/operator_task/complete_requested',
    successToastKey: 'flows:toast.operator_task_completed',
    errorToastKey: 'flows:toast.operator_task_complete_error',
    restMirror: { method: 'POST', path: '/flows/api/v1/operator/tasks/{task_id}/complete' },
});
