/**
 * Human copy keys + phase tags for durable workflow event types.
 * Titles live in flows.durable_history_modal.events.<EventType>.
 */

const EVENT_PHASE_BY_TYPE = Object.freeze({
    RunStarted: 'run',
    UserInputApplied: 'run',
    VariablesResolved: 'run',
    StateProjectionCommitted: 'run',
    ConversationMessageAppended: 'run',
    RunTerminal: 'terminal',
    SuperstepStarted: 'node',
    NodeScheduled: 'node',
    NodeWriteRecorded: 'node',
    NodeCompleted: 'node',
    NodeFailed: 'fail',
    SuperstepCommitted: 'node',
    EdgeActivated: 'node',
    ActivityScheduled: 'activity',
    ActivityStarted: 'activity',
    ActivityCompleted: 'activity',
    ActivityFailed: 'fail',
    ChildWorkflowStarted: 'child',
    ChildWorkflowSuspended: 'child',
    ChildWorkflowCompleted: 'child',
    ChildWorkflowFailed: 'fail',
    InterruptRaised: 'interrupt',
    BreakpointHit: 'interrupt',
    HandoffRequested: 'interrupt',
    HandoffCompleted: 'interrupt',
    HandoffRejected: 'interrupt',
    HandoffResumed: 'interrupt',
    HandoffInitiated: 'interrupt',
    HandoffAccepted: 'interrupt',
    HandbackRequested: 'interrupt',
    HandbackCompleted: 'interrupt',
    ForkCreated: 'branch',
    RewindCommitted: 'branch',
    ManualStatePatchApplied: 'branch',
    RetryScheduled: 'branch',
});

const KNOWN_EVENT_TYPES = new Set(Object.keys(EVENT_PHASE_BY_TYPE));

const BRANCH_REASONS = new Set([
    'start',
    'fork',
    'rewind',
    'retry',
    'manual_patch',
]);

const SUBTITLE_PAYLOAD_KEYS = Object.freeze([
    'node_id',
    'node_type',
    'activity_id',
    'activity_type',
    'child_session_id',
    'handoff_command_id',
    'source_execution_branch_id',
    'terminal_task_state',
    'error',
]);

/**
 * @param {string} eventType
 * @returns {string}
 */
export function durableEventTitleKey(eventType) {
    if (typeof eventType !== 'string' || eventType.length === 0) {
        throw new Error('flows-durable-event-copy: eventType string required');
    }
    if (!KNOWN_EVENT_TYPES.has(eventType)) {
        return 'durable_history_modal.events.unknown';
    }
    return `durable_history_modal.events.${eventType}`;
}

/**
 * @param {string} eventType
 * @returns {'run'|'node'|'activity'|'child'|'interrupt'|'branch'|'terminal'|'fail'|'unknown'}
 */
export function durableEventPhase(eventType) {
    if (typeof eventType !== 'string' || eventType.length === 0) {
        throw new Error('flows-durable-event-copy: eventType string required');
    }
    const phase = EVENT_PHASE_BY_TYPE[eventType];
    if (typeof phase !== 'string') {
        return 'unknown';
    }
    return phase;
}

/**
 * @param {string} reason
 * @returns {string}
 */
export function durableBranchReasonKey(reason) {
    if (typeof reason !== 'string' || reason.length === 0) {
        return 'durable_history_modal.branch_reason.unknown';
    }
    if (!BRANCH_REASONS.has(reason)) {
        return 'durable_history_modal.branch_reason.unknown';
    }
    return `durable_history_modal.branch_reason.${reason}`;
}

/**
 * @param {string} branchId
 * @returns {string}
 */
export function formatDurableBranchLabel(branchId) {
    if (typeof branchId !== 'string' || branchId.length === 0) {
        throw new Error('flows-durable-event-copy: branchId string required');
    }
    if (branchId.length <= 14) {
        return branchId;
    }
    return `${branchId.slice(0, 8)}…${branchId.slice(-4)}`;
}

/**
 * @param {Record<string, unknown>} payload
 * @returns {string}
 */
export function durableEventSubtitleFromPayload(payload) {
    if (payload === null || typeof payload !== 'object' || Array.isArray(payload)) {
        return '';
    }
    for (const key of SUBTITLE_PAYLOAD_KEYS) {
        const value = payload[key];
        if (typeof value === 'string' && value.length > 0) {
            return value;
        }
        if (Number.isInteger(value)) {
            return String(value);
        }
        if (Array.isArray(value) && value.length > 0) {
            const first = value[0];
            if (typeof first === 'string' && first.length > 0) {
                return value.length === 1 ? first : `${first} +${value.length - 1}`;
            }
        }
    }
    return '';
}

/**
 * @param {string} eventType
 * @returns {boolean}
 */
export function isDurableFailedEventType(eventType) {
    if (typeof eventType !== 'string') {
        return false;
    }
    return eventType.endsWith('Failed') || eventType === 'NodeFailed' || durableEventPhase(eventType) === 'fail';
}

/**
 * @param {string} eventType
 * @returns {boolean}
 */
export function isDurableTerminalEventType(eventType) {
    return eventType === 'RunTerminal';
}
