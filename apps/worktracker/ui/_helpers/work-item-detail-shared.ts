/**
 * Общие хелперы для UI деталей WorkItem.
 */

import { isPlainRecord } from '@platform/lib/events/payload.js';

export const TERMINAL_STATES = new Set(['done', 'cancelled', 'failed']);

export interface WorkItemAssignment {
    assignee_kind?: string;
    claimed_by_user_id?: unknown;
    user_ids?: unknown;
    [key: string]: unknown;
}

export interface WorkItemLike {
    assignment?: WorkItemAssignment;
    kind?: string;
    interaction_policy?: { mode?: string; can_complete?: boolean; [key: string]: unknown };
    [key: string]: unknown;
}

export const WORK_ITEM_STATES = [
    'open',
    'in_progress',
    'blocked',
    'done',
    'cancelled',
    'failed',
];

export const WORK_ITEM_PRIORITIES = ['low', 'normal', 'high', 'urgent'];

export function assigneeIsQueue(item: WorkItemLike) {
    const assignment = item && item.assignment;
    return assignment && typeof assignment === 'object' && assignment.assignee_kind === 'queue';
}

export function queueUnclaimed(item: WorkItemLike) {
    if (!assigneeIsQueue(item)) {
        return false;
    }
    const claimed = item.assignment?.claimed_by_user_id;
    return typeof claimed !== 'string' || claimed.length === 0;
}

export function assigneeUserId(item: WorkItemLike): string {
    const assignment = item && item.assignment;
    if (!assignment || typeof assignment !== 'object') {
        return '';
    }
    if (assignment.assignee_kind === 'users') {
        if (!Array.isArray(assignment.user_ids) || assignment.user_ids.length === 0) {
            return '';
        }
        const userId = assignment.user_ids[0];
        return typeof userId === 'string' ? userId : '';
    }
    if (assignment.assignee_kind === 'queue') {
        const claimed = assignment.claimed_by_user_id;
        return typeof claimed === 'string' ? claimed : '';
    }
    return '';
}

function readWorkItemField(value: unknown): WorkItemLike | null | undefined {
    if (value == null || typeof value !== 'object') return undefined;
    if (!isPlainRecord(value)) return null;
    const item: WorkItemLike = {};
    for (const [key, field] of Object.entries(value)) item[key] = field;
    return item;
}

export function workItemFromEventPayload(payload: unknown): WorkItemLike | null {
    if (!isPlainRecord(payload)) return null;
    for (const key of ['item', 'work_item', 'result']) {
        if (!Object.prototype.hasOwnProperty.call(payload, key)) continue;
        const item = readWorkItemField(payload[key]);
        if (item === undefined) continue;
        return item;
    }
    return null;
}

export function truncateWorkItemId(workItemId: unknown): string {
    if (typeof workItemId !== 'string' || workItemId.length === 0) {
        return '';
    }
    if (workItemId.length <= 12) {
        return workItemId;
    }
    return `${workItemId.slice(0, 8)}…`;
}

/** Header/kebab Complete without reply: HITL only when takeover and can_complete. */
export function workItemAllowsSilentComplete(item: WorkItemLike | null): boolean {
    if (!item) return true;
    if (item.kind !== 'operator_handoff') return true;
    const policy = item.interaction_policy;
    if (!policy || typeof policy !== 'object') return false;
    if (policy.mode === 'single_reply') return false;
    if (policy.mode !== 'takeover') return false;
    return policy.can_complete === true;
}
