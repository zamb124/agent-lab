/**
 * WorkItem — фабрики владельца домена worktracker для всех SPA.
 */

import { createAsyncOp, createForm, createResourceCollection } from '../index.js';
import { CoreEvents } from '../contract.js';
import type { PlatformEvent, EffectCtx } from '../contract.js';
import { isPlatformEventType, isPlainRecord } from '../payload.js';
import type { ResourceCollectionSlice } from '../factories/resource-collection.js';
import type { AsyncOpSlice } from '../factories/async-op.js';
import type {
    WorkItem,
    WorkItemComment,
    WorkItemCommentsList,
    WorkItemMineSummary,
} from '../wire/worktracker.gen.js';

type JsonObject = Record<string, unknown>;

function isWorkItemSlice(state: ResourceCollectionSlice<WorkItem>): state is WorkItemSlice {
    return Array.isArray(state.items) && isPlainRecord(state.byId);
}

function isWorkItem(value: unknown): value is WorkItem {
    return (
        isPlainRecord(value)
        && typeof value.work_item_id === 'string'
        && typeof value.company_id === 'string'
        && typeof value.title === 'string'
        && isPlainRecord(value.created_by)
        && typeof value.created_at === 'string'
        && typeof value.updated_at === 'string'
    );
}

function workItemRecord(value: unknown): WorkItem | null {
    return isWorkItem(value) ? value : null;
}

function payloadResult(payload: unknown): JsonObject | null {
    if (!isPlainRecord(payload) || !('result' in payload) || !isPlainRecord(payload.result)) {
        return null;
    }
    return payload.result;
}

function requireEventName(name: string | undefined, label: string): string {
    if (name === undefined) {
        throw new Error(`${label} missing`);
    }
    return name;
}

interface WorkItemSlice extends ResourceCollectionSlice<WorkItem> {
    byId: Readonly<Record<string, WorkItem>>;
    items: readonly WorkItem[];
}

export const WORK_ITEM_EVENTS = [
    'worktracker/work_item/created',
    'worktracker/work_item/updated',
    'worktracker/work_item/moved',
    'worktracker/work_item/completed',
    'worktracker/work_item/comment_created',
] as const;

export const WORK_ITEM_MUTATION_SUCCEEDED = [
    'worktracker/work_item_move/succeeded',
    'worktracker/work_item_claim/succeeded',
    'worktracker/work_item_complete/succeeded',
    'worktracker/work_item_cancel/succeeded',
    'worktracker/work_item_assign/succeeded',
];

function _mergeWorkItem(state: WorkItemSlice, item: WorkItem): WorkItemSlice {
    const id = String(item.work_item_id);
    const existing = state.byId[id];
    let merged = item;
    if (
        isPlainRecord(existing)
        && isPlainRecord(existing.interaction_policy)
        && !isPlainRecord(item.interaction_policy)
    ) {
        const prev = existing.interaction_policy;
        const isTerminal = item.state === 'done' || item.state === 'cancelled' || item.state === 'failed';
        merged = {
            ...item,
            interaction_policy: {
                ...prev,
                can_send: isTerminal ? false : Boolean(prev.can_send),
                can_complete: isTerminal ? false : Boolean(prev.can_complete),
            },
        };
    }
    const idx = state.items.findIndex((x) => x && x.work_item_id === item.work_item_id);
    const items = idx === -1 ? [...state.items, merged] : state.items.map((x, i) => (i === idx ? merged : x));
    return { ...state, items, byId: { ...state.byId, [id]: merged } };
}

export const workItemGetOp = createAsyncOp<WorkItem>({
    name: 'worktracker/work_item_get',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 5_000,
    commandType: 'worktracker/work_items/item_requested',
    restMirror: { method: 'GET', path: '/worktracker/api/v1/work-items/:work_item_id' },
});

export const workItemCountsOp = createAsyncOp<WorkItemMineSummary>({
    name: 'worktracker/work_item_counts',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 5_000,
    commandType: 'worktracker/work_items/mine_summary_requested',
    restMirror: { method: 'GET', path: '/worktracker/api/v1/work-items/mine/summary' },
    extraInitial: {
        assigned_open_count: 0,
        queue_inbox_count: 0,
        total_open_count: 0,
        work_queue_ids: [],
    },
    extraReducer: (state, event, events) => {
        if (event.type !== events.SUCCEEDED || !isPlainRecord(event.payload) || !('result' in event.payload)) {
            return state;
        }
        const result = event.payload.result;
        if (!isPlainRecord(result)) {
            throw new Error('workItemCountsOp: SUCCEEDED result must be object');
        }
        if (typeof result.assigned_open_count !== 'number' || typeof result.queue_inbox_count !== 'number') {
            throw new Error('workItemCountsOp: assigned_open_count and queue_inbox_count required numbers');
        }
        const workQueueIds = Array.isArray(result.work_queue_ids)
            ? result.work_queue_ids.filter((id): id is string => typeof id === 'string' && id.length > 0)
            : [];
        return {
            ...state,
            assigned_open_count: result.assigned_open_count,
            queue_inbox_count: result.queue_inbox_count,
            total_open_count: result.assigned_open_count + result.queue_inbox_count,
            work_queue_ids: workQueueIds,
        };
    },
});

export const workItemsResource = createResourceCollection<WorkItem>({
    name: 'worktracker/work_items',
    baseUrl: '/worktracker/api/v1/work-items',
    idField: 'work_item_id',
    operations: ['list', 'get', 'create', 'update'],
    transport: 'ws',
    wsTimeoutMs: 5_000,
    listQuery: (payload) => {
        const query: Record<string, unknown> = {};
        if (!payload || typeof payload !== 'object') {
            query.limit = 200;
            query.offset = 0;
            return query;
        }
        for (const key of [
            'board_id',
            'namespace',
            'kind',
            'state',
            'work_queue_id',
            'assignee_user_id',
            'assignee_flow_id',
        ]) {
            if (typeof payload[key] === 'string' && payload[key].length > 0) {
                query[key] = payload[key];
            }
        }
        if (payload.exclude_terminal === true) {
            query.exclude_terminal = true;
        }
        if (payload.queue_unclaimed_only === true) {
            query.queue_unclaimed_only = true;
        }
        if (Array.isArray(payload.work_queue_ids) && payload.work_queue_ids.length > 0) {
            query.work_queue_ids = payload.work_queue_ids;
        }
        query.limit = typeof payload.limit === 'number' ? payload.limit : 200;
        query.offset = typeof payload.offset === 'number' ? payload.offset : 0;
        return query;
    },
    toastKeys: {
        create: 'worktracker:toast.work_item_created',
        create_error: 'worktracker:toast.work_item_create_failed',
        update: 'platform:work_item.update_success',
        update_error: 'platform:work_item.update_error',
    },
    extraReducer: (state, event) => {
        if (WORK_ITEM_MUTATION_SUCCEEDED.includes(event.type)) {
            const result = payloadResult(event.payload);
            if (!isWorkItem(result)) {
                return state;
            }
            if (!isWorkItemSlice(state)) {
                throw new Error('worktracker/work_items: slice is invalid');
            }
            return _mergeWorkItem(state, result);
        }
        if (!isPlatformEventType(event, WORK_ITEM_EVENTS)) {
            return state;
        }
        const payload = event.payload;
        if (isPlatformEventType(event, 'worktracker/work_item/comment_created')) {
            const workItemId = event.payload.work_item_id;
            if (!isWorkItemSlice(state)) {
                throw new Error('worktracker/work_items: slice is invalid');
            }
            const existing = state.byId[workItemId];
            if (!existing || typeof existing !== 'object') {
                return state;
            }
            const commentCount = typeof existing.comment_count === 'number' ? existing.comment_count + 1 : 1;
            const updated = { ...existing, comment_count: commentCount };
            return _mergeWorkItem(state, updated);
        }
        const item = workItemRecord(payload.work_item);
        if (item === null) {
            return state;
        }
        if (!isWorkItemSlice(state)) {
            throw new Error('worktracker/work_items: slice is invalid');
        }
        return _mergeWorkItem(state, item);
    },
    extraEffect: async (event, ctx, events) => {
        if (!isPlatformEventType(event, 'flows/hitl_conversation/turn_appended')) {
            return false;
        }
        const workItemId = event.payload.work_item_id;
        if (workItemId.length === 0) {
            return true;
        }
        ctx.dispatch(
            requireEventName(events.ITEM_REQUESTED, 'worktracker/work_items ITEM_REQUESTED'),
            { work_item_id: workItemId },
            { causation_id: event.id, source: 'ws' },
        );
        return true;
    },
});

export const workItemMoveOp = createAsyncOp<WorkItem>({
    name: 'worktracker/work_item_move',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 5_000,
    commandType: 'worktracker/work_items/move_requested',
    restMirror: { method: 'POST', path: '/worktracker/api/v1/work-items/:work_item_id/move' },
});

export const workItemClaimOp = createAsyncOp<WorkItem>({
    name: 'worktracker/work_item_claim',
    transport: 'ws',
    wsTimeoutMs: 5_000,
    commandType: 'worktracker/work_items/claim_requested',
    successToastKey: 'worktracker:toast.work_item_claimed',
    errorToastKey: 'worktracker:toast.work_item_claim_failed',
    restMirror: { method: 'POST', path: '/worktracker/api/v1/work-items/:work_item_id/claim' },
});

export const workItemCompleteOp = createAsyncOp<WorkItem>({
    name: 'worktracker/work_item_complete',
    transport: 'ws',
    wsTimeoutMs: 5_000,
    commandType: 'worktracker/work_items/complete_requested',
    successToastKey: 'worktracker:toast.work_item_completed',
    errorToastKey: 'worktracker:toast.work_item_complete_failed',
    restMirror: { method: 'POST', path: '/worktracker/api/v1/work-items/:work_item_id/complete' },
});

export const workItemCancelOp = createAsyncOp<WorkItem>({
    name: 'worktracker/work_item_cancel',
    transport: 'ws',
    wsTimeoutMs: 5_000,
    commandType: 'worktracker/work_items/cancel_requested',
    successToastKey: 'worktracker:toast.work_item_cancelled',
    errorToastKey: 'worktracker:toast.work_item_cancel_failed',
    restMirror: { method: 'POST', path: '/worktracker/api/v1/work-items/:work_item_id/cancel' },
});

export const workItemAssignOp = createAsyncOp<WorkItem>({
    name: 'worktracker/work_item_assign',
    transport: 'ws',
    wsTimeoutMs: 5_000,
    commandType: 'worktracker/work_items/assign_requested',
    successToastKey: 'platform:work_item.assign_success',
    errorToastKey: 'platform:work_item.assign_error',
    restMirror: { method: 'POST', path: '/worktracker/api/v1/work-items/:work_item_id/assign' },
});

export const workItemCommentOp = createAsyncOp<WorkItemComment>({
    name: 'worktracker/work_item_comment',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 5_000,
    commandType: 'worktracker/work_items/comment_requested',
    restMirror: { method: 'POST', path: '/worktracker/api/v1/work-items/:work_item_id/comments' },
});

export const workItemCommentsListOp = createAsyncOp<WorkItemCommentsList>({
    name: 'worktracker/work_item_comments_list',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 5_000,
    commandType: 'worktracker/work_items/comments_list_requested',
    restMirror: { method: 'GET', path: '/worktracker/api/v1/work-items/:work_item_id/comments' },
    extraInitial: { items: [] },
    extraReducer: (state, event, events) => {
        if (event.type !== events.SUCCEEDED || !isPlainRecord(event.payload) || !('result' in event.payload)) {
            return state;
        }
        const result = event.payload.result;
        if (!isPlainRecord(result) || !Array.isArray(result.items)) {
            throw new Error('workItemCommentsListOp: expected {items: comment[]}');
        }
        return { ...state, items: result.items };
    },
});

export const workItemCreateForm = createForm({
    name: 'worktracker/work_item_create_form',
    schema: {
        title: { required: true, minLength: 1, maxLength: 255, errorKey: 'form.title_required' },
        description: {},
        board_id: {},
        priority: {},
    },
    initial: { title: '', description: '', board_id: '', priority: 'normal' },
    submitEvent: workItemsResource.events.CREATE_REQUESTED,
    buildPayload: (draft) => {
        const payload: Record<string, unknown> = {
            title: typeof draft.title === 'string' ? draft.title.trim() : '',
            description: typeof draft.description === 'string' ? draft.description : '',
            priority: typeof draft.priority === 'string' && draft.priority ? draft.priority : 'normal',
        };
        if (typeof draft.board_id === 'string' && draft.board_id.length > 0) {
            payload.board_id = draft.board_id;
        }
        return payload;
    },
});

export const worktrackerWorkItemFactories = [
    workItemGetOp,
    workItemCountsOp,
    workItemsResource,
    workItemMoveOp,
    workItemClaimOp,
    workItemCompleteOp,
    workItemCancelOp,
    workItemAssignOp,
    workItemCommentOp,
    workItemCommentsListOp,
    workItemCreateForm,
];

export function createWorktrackerWorkItemCountsAuthEffect(): (event: PlatformEvent, ctx: EffectCtx) => void {
    return (event: PlatformEvent, ctx: EffectCtx): void => {
        if (event.type === CoreEvents.AUTH_USER_LOADED) {
            workItemCountsOp.run({}, ctx);
        }
    };
}

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'worktracker/work_item_get': typeof workItemGetOp;
        'worktracker/work_item_counts': typeof workItemCountsOp;
        'worktracker/work_items': typeof workItemsResource;
        'worktracker/work_item_move': typeof workItemMoveOp;
        'worktracker/work_item_claim': typeof workItemClaimOp;
        'worktracker/work_item_complete': typeof workItemCompleteOp;
        'worktracker/work_item_cancel': typeof workItemCancelOp;
        'worktracker/work_item_assign': typeof workItemAssignOp;
        'worktracker/work_item_comment': typeof workItemCommentOp;
        'worktracker/work_item_comments_list': typeof workItemCommentsListOp;
        'worktracker/work_item_create_form': typeof workItemCreateForm;
    }
}
