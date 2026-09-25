/**
 * Общие хелперы для UI деталей WorkItem.
 */

export const TERMINAL_STATES = new Set(['done', 'cancelled', 'failed']);

export const WORK_ITEM_STATES = [
    'open',
    'in_progress',
    'blocked',
    'done',
    'cancelled',
    'failed',
];

export const WORK_ITEM_PRIORITIES = ['low', 'normal', 'high', 'urgent'];

export function assigneeIsQueue(item) {
    const assignment = item && item.assignment;
    return assignment && typeof assignment === 'object' && assignment.assignee_kind === 'queue';
}

export function queueUnclaimed(item) {
    if (!assigneeIsQueue(item)) {
        return false;
    }
    const claimed = item.assignment.claimed_by_user_id;
    return typeof claimed !== 'string' || claimed.length === 0;
}

export function assigneeUserId(item) {
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

export function workItemFromEventPayload(payload) {
    if (!payload || typeof payload !== 'object') {
        return null;
    }
    if ('item' in payload && payload.item && typeof payload.item === 'object') {
        return payload.item;
    }
    if ('work_item' in payload && payload.work_item && typeof payload.work_item === 'object') {
        return payload.work_item;
    }
    if ('result' in payload && payload.result && typeof payload.result === 'object') {
        return payload.result;
    }
    return null;
}

export function truncateWorkItemId(workItemId) {
    if (typeof workItemId !== 'string' || workItemId.length === 0) {
        return '';
    }
    if (workItemId.length <= 12) {
        return workItemId;
    }
    return `${workItemId.slice(0, 8)}…`;
}

/** Header/kebab Complete without reply: HITL only when takeover and can_complete. */
export function workItemAllowsSilentComplete(item) {
    if (!item || typeof item !== 'object') return true;
    if (item.kind !== 'operator_handoff') return true;
    const policy = item.interaction_policy;
    if (!policy || typeof policy !== 'object') return false;
    if (policy.mode === 'single_reply') return false;
    if (policy.mode !== 'takeover') return false;
    return policy.can_complete === true;
}
