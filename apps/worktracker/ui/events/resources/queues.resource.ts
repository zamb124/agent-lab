/**
 * Work queues — очереди задач (операторские и общие).
 */

import { createAsyncOp } from '@platform/lib/events/index.js';

export { workQueuesResource } from '@platform/lib/events/resources/work-queues.resource.js';

const WORK_QUEUE_MEMBER_ADD_SUCCEEDED = 'worktracker/work_queue_member_add/succeeded';

interface WorkQueueActor {
    actor_kind?: string;
    user_id?: unknown;
    [key: string]: unknown;
}

interface WorkQueueMember {
    member?: WorkQueueActor;
    work_queue_id?: unknown;
    [key: string]: unknown;
}

import type { AsyncOpSlice } from '@platform/lib/events/factories/async-op.js';
import type { PlatformEvent } from '@platform/lib/events/contract.js';
import { isJsonObject } from '@platform/lib/utils/json-object.js';

interface MembersListPayload {
    result?: unknown;
    request?: { work_queue_id?: unknown; member?: WorkQueueActor };
    [key: string]: unknown;
}
const WORK_QUEUE_MEMBER_REMOVE_SUCCEEDED = 'worktracker/work_queue_member_remove/succeeded';

function _sameActor(left: WorkQueueActor | undefined, right: WorkQueueActor | undefined): boolean {
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
    extraReducer: (state: AsyncOpSlice, event: PlatformEvent, events) => {
        if (event.type !== events.SUCCEEDED && event.type !== WORK_QUEUE_MEMBER_ADD_SUCCEEDED && event.type !== WORK_QUEUE_MEMBER_REMOVE_SUCCEEDED) {
            return state;
        }
        if (!isJsonObject(event.payload)) {
            throw new Error(`workQueueMembersListOp: ${event.type} payload object required`);
        }
        const payload = event.payload as MembersListPayload;
        const items = Array.isArray(state.items) ? state.items as WorkQueueMember[] : [];
        const lastRequest = state.lastRequest as { payload?: { work_queue_id?: unknown } } | undefined;
        if (event.type === events.SUCCEEDED) {
            const result = payload.result as { items?: unknown } | undefined;
            if (!result || typeof result !== 'object' || !Array.isArray(result.items)) {
                throw new Error('workQueueMembersListOp: expected {items: member[]}');
            }
            return { ...state, items: result.items as WorkQueueMember[] };
        }
        const listedQueueId = lastRequest && lastRequest.payload
            ? lastRequest.payload.work_queue_id
            : null;
        if (event.type === WORK_QUEUE_MEMBER_ADD_SUCCEEDED) {
            const member = payload.result as WorkQueueMember | undefined;
            if (!member || member.work_queue_id !== listedQueueId) {
                return state;
            }
            const rest = items.filter((item) => !_sameActor(item.member, member.member));
            return { ...state, items: [...rest, member] };
        }
        if (event.type === WORK_QUEUE_MEMBER_REMOVE_SUCCEEDED) {
            const request = payload.request;
            if (!request || request.work_queue_id !== listedQueueId || !request.member) {
                return state;
            }
            return { ...state, items: items.filter((item) => !_sameActor(item.member, request.member)) };
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

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'worktracker/work_queue_members_list': typeof workQueueMembersListOp;
        'worktracker/work_queue_member_add': typeof workQueueMemberAddOp;
        'worktracker/work_queue_member_remove': typeof workQueueMemberRemoveOp;
    }
}
