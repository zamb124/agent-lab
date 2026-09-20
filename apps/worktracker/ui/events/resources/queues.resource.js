/**
 * Work queues — очереди задач (операторские и общие).
 */

import { createAsyncOp } from '@platform/lib/events/index.js';

export { workQueuesResource } from '@platform/lib/events/resources/work-queues.resource.js';

export const workQueueMembersListOp = createAsyncOp({
    name: 'worktracker/work_queue_members_list',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 5_000,
    commandType: 'worktracker/work_queues/members_list_requested',
    restMirror: { method: 'GET', path: '/worktracker/api/v1/work-queues/:work_queue_id/members' },
    extraInitial: { items: [] },
    extraReducer: (state, event, events) => {
        if (event.type !== events.SUCCEEDED || !event.payload || !('result' in event.payload)) {
            return state;
        }
        const result = event.payload.result;
        if (!result || typeof result !== 'object' || !Array.isArray(result.items)) {
            throw new Error('workQueueMembersListOp: expected {items: member[]}');
        }
        return { ...state, items: result.items };
    },
});

export const workQueueMemberAddOp = createAsyncOp({
    name: 'worktracker/work_queue_member_add',
    transport: 'ws',
    wsTimeoutMs: 5_000,
    commandType: 'worktracker/work_queues/member_add_requested',
    successToastKey: 'worktracker:toast.queue_member_added',
    errorToastKey: 'worktracker:toast.queue_member_add_failed',
    restMirror: { method: 'POST', path: '/worktracker/api/v1/work-queues/:work_queue_id/members' },
});

export const workQueueMemberRemoveOp = createAsyncOp({
    name: 'worktracker/work_queue_member_remove',
    transport: 'ws',
    wsTimeoutMs: 5_000,
    commandType: 'worktracker/work_queues/member_remove_requested',
    successToastKey: 'worktracker:toast.queue_member_removed',
    errorToastKey: 'worktracker:toast.queue_member_remove_failed',
    restMirror: { method: 'POST', path: '/worktracker/api/v1/work-queues/:work_queue_id/members/remove' },
});
