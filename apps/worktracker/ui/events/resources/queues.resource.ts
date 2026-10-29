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

const WORK_QUEUE_MEMBER_REMOVE_SUCCEEDED = 'worktracker/work_queue_member_remove/succeeded';

function isWorkQueueMember(value: unknown): value is WorkQueueMember {
    return isJsonObject(value);
}

function isWorkQueueActor(value: unknown): value is WorkQueueActor {
    return isJsonObject(value);
}

function memberList(value: unknown): WorkQueueMember[] {
    if (!Array.isArray(value)) {
        return [];
    }
    const rows: WorkQueueMember[] = [];
    for (const item of value) {
        if (!isWorkQueueMember(item)) {
            throw new Error('workQueueMembersListOp: member list item must be an object');
        }
        rows.push(item);
    }
    return rows;
}

function listedQueueId(state: AsyncOpSlice): unknown {
    const lastRequest = state.lastRequest;
    if (lastRequest === null) {
        return null;
    }
    const requestPayload = lastRequest.payload;
    if (!isJsonObject(requestPayload)) {
        return null;
    }
    return requestPayload.work_queue_id;
}

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
        const payload = event.payload;
        const items = memberList(state.items);
        const queueId = listedQueueId(state);
        if (event.type === events.SUCCEEDED) {
            const result = payload.result;
            if (!isJsonObject(result) || !Array.isArray(result.items)) {
                throw new Error('workQueueMembersListOp: expected {items: member[]}');
            }
            return { ...state, items: memberList(result.items) };
        }
        if (event.type === WORK_QUEUE_MEMBER_ADD_SUCCEEDED) {
            const member = payload.result;
            if (!isWorkQueueMember(member) || member.work_queue_id !== queueId) {
                return state;
            }
            const added = member.member;
            const actor = isWorkQueueActor(added) ? added : undefined;
            const rest = items.filter((item) => !_sameActor(item.member, actor));
            return { ...state, items: [...rest, member] };
        }
        if (event.type === WORK_QUEUE_MEMBER_REMOVE_SUCCEEDED) {
            const request = payload.request;
            if (!isJsonObject(request) || request.work_queue_id !== queueId) {
                return state;
            }
            const removed = request.member;
            if (!isWorkQueueActor(removed)) {
                return state;
            }
            return { ...state, items: items.filter((item) => !_sameActor(item.member, removed)) };
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
