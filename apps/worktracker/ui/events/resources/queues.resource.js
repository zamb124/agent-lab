/**
 * Work queues — очереди задач (операторские и общие).
 */

import { createAsyncOp } from '@platform/lib/events/index.js';

export { workQueuesResource } from '@platform/lib/events/resources/work-queues.resource.js';

const WORK_QUEUE_MEMBER_ADD_SUCCEEDED = 'worktracker/work_queue_member_add/succeeded';
const WORK_QUEUE_MEMBER_REMOVE_SUCCEEDED = 'worktracker/work_queue_member_remove/succeeded';

function _sameActor(left, right) {
    if (!left || !right || left.actor_kind !== right.actor_kind) {
        return false;
    }
    return left.actor_kind === 'system' || left.user_id === right.user_id;
}

export const workQueueMembersListOp = createAsyncOp({
    name: 'worktracker/work_queue_members_list',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 5_000,
    commandType: 'worktracker/work_queues/members_list_requested',
    restMirror: { method: 'GET', path: '/worktracker/api/v1/work-queues/:work_queue_id/members' },
    extraInitial: { items: [] },
    // Исходы add/remove мержатся в список участников открытой очереди.
    extraReducer: (state, event, events) => {
        if (event.type === events.SUCCEEDED) {
            const result = event.payload.result;
            if (!result || typeof result !== 'object' || !Array.isArray(result.items)) {
                throw new Error('workQueueMembersListOp: expected {items: member[]}');
            }
            return { ...state, items: result.items };
        }
        const listedQueueId = state.lastRequest && state.lastRequest.payload
            ? state.lastRequest.payload.work_queue_id
            : null;
        if (event.type === WORK_QUEUE_MEMBER_ADD_SUCCEEDED) {
            const member = event.payload.result;
            if (!member || member.work_queue_id !== listedQueueId) {
                return state;
            }
            const items = state.items.filter((item) => !_sameActor(item.member, member.member));
            return { ...state, items: [...items, member] };
        }
        if (event.type === WORK_QUEUE_MEMBER_REMOVE_SUCCEEDED) {
            const request = event.payload.request;
            if (!request || request.work_queue_id !== listedQueueId || !request.member) {
                return state;
            }
            return { ...state, items: state.items.filter((item) => !_sameActor(item.member, request.member)) };
        }
        return state;
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
