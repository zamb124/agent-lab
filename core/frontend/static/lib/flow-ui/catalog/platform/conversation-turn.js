import { isA2UIArtifact } from '../../protocol/a2ui-0-9-1-codec.js';

export const TERMINAL_TASK_STATES = Object.freeze(new Set([
    'TASK_STATE_COMPLETED',
    'TASK_STATE_FAILED',
    'TASK_STATE_CANCELED',
    'TASK_STATE_REJECTED',
]));

function textFromParts(parts) {
    if (!Array.isArray(parts)) return '';
    return parts
        .map((part) => (part && typeof part.text === 'string' ? part.text : ''))
        .join('');
}

function isOrdinaryFeedArtifact(artifact) {
    if (!artifact || typeof artifact !== 'object') return false;
    if (isA2UIArtifact(artifact)) return false;
    const name = typeof artifact.name === 'string' ? artifact.name : '';
    return name !== 'ui.document';
}

function isResponseArtifact(artifact) {
    if (!isOrdinaryFeedArtifact(artifact)) return false;
    const name = typeof artifact.name === 'string' ? artifact.name : '';
    return name === 'response';
}

function isUserMessageArtifact(artifact) {
    if (!isOrdinaryFeedArtifact(artifact)) return false;
    const name = typeof artifact.name === 'string' ? artifact.name : '';
    return name === 'user_message';
}

function messageRole(message) {
    if (!message || typeof message !== 'object') return '';
    const role = typeof message.role === 'string' ? message.role : '';
    return role;
}

function isUserRole(role) {
    return role === 'ROLE_USER' || role === 'user' || role === 'USER';
}

function userMessageArtifacts(task) {
    if (!task || typeof task !== 'object') {
        throw new Error('flow-ui: conversation helpers require task object');
    }
    return (Array.isArray(task.artifacts) ? task.artifacts : [])
        .filter(isUserMessageArtifact);
}

/**
 * User turn text for one Task: user_message artifact first, else ROLE_USER
 * messages scoped to this task_id (never the first-ever user message in the session).
 */
export function conversationUserText(task) {
    const fromArtifacts = userMessageArtifacts(task)
        .map((artifact) => textFromParts(artifact.parts))
        .join('');
    if (fromArtifacts !== '') return fromArtifacts;

    const taskId = typeof task.id === 'string' ? task.id : '';
    const history = Array.isArray(task.history) ? task.history : [];
    for (const message of history) {
        if (!isUserRole(messageRole(message))) continue;
        const messageTaskId = typeof message.task_id === 'string'
            ? message.task_id
            : (typeof message.taskId === 'string' ? message.taskId : '');
        if (taskId !== '' && messageTaskId !== '' && messageTaskId !== taskId) {
            continue;
        }
        const text = textFromParts(message.parts);
        if (text !== '') return text;
    }
    return '';
}

/**
 * FileRefs attached to the user turn (user_message artifact data parts `{files}`).
 */
export function conversationUserFiles(task) {
    const files = [];
    for (const artifact of userMessageArtifacts(task)) {
        for (const part of Array.isArray(artifact.parts) ? artifact.parts : []) {
            const data = part && typeof part === 'object' ? part.data : null;
            if (data && typeof data === 'object' && Array.isArray(data.files)) {
                files.push(...data.files.filter((ref) => ref && typeof ref === 'object'));
            }
        }
    }
    return files;
}

function sessionFileKey(ref) {
    if (!ref || typeof ref !== 'object') return '';
    if (typeof ref.file_id === 'string' && ref.file_id.trim() !== '') {
        return ref.file_id.trim();
    }
    if (typeof ref.url === 'string' && ref.url.trim() !== '') {
        return ref.url.trim();
    }
    if (typeof ref.original_name === 'string' && ref.original_name.trim() !== '') {
        return `name:${ref.original_name.trim()}`;
    }
    return '';
}

function upsertSessionFile(byKey, ref) {
    if (!ref || typeof ref !== 'object') return;
    const key = sessionFileKey(ref);
    if (key === '') return;
    const prev = byKey.get(key);
    if (!prev) {
        byKey.set(key, { ...ref });
        return;
    }
    byKey.set(key, { ...prev, ...ref });
}

function fileRefFromA2aFilePart(part) {
    if (!part || typeof part !== 'object') return null;
    const meta = part.metadata && typeof part.metadata === 'object' ? part.metadata : null;
    const file = part.file && typeof part.file === 'object' ? part.file : null;
    const fileId = (
        (typeof part.file_id === 'string' && part.file_id.trim() !== '' ? part.file_id.trim() : '')
        || (meta && typeof meta.file_id === 'string' && meta.file_id.trim() !== '' ? meta.file_id.trim() : '')
        || (file && typeof file.file_id === 'string' && file.file_id.trim() !== '' ? file.file_id.trim() : '')
    );
    if (fileId === '') return null;
    const originalName = (
        (typeof part.filename === 'string' && part.filename.trim() !== '' ? part.filename.trim() : '')
        || (typeof part.original_name === 'string' && part.original_name.trim() !== '' ? part.original_name.trim() : '')
        || (file && typeof file.name === 'string' && file.name.trim() !== '' ? file.name.trim() : '')
        || fileId
    );
    const contentType = (
        (typeof part.mediaType === 'string' && part.mediaType.trim() !== '' ? part.mediaType.trim() : '')
        || (typeof part.content_type === 'string' && part.content_type.trim() !== '' ? part.content_type.trim() : '')
        || (file && typeof file.mimeType === 'string' && file.mimeType.trim() !== '' ? file.mimeType.trim() : '')
    );
    const url = (
        (typeof part.url === 'string' && part.url.trim() !== '' ? part.url.trim() : '')
        || (file && typeof file.uri === 'string' && file.uri.trim() !== '' ? file.uri.trim() : '')
    );
    const ref = { file_id: fileId, original_name: originalName };
    if (contentType !== '') ref.content_type = contentType;
    if (url !== '') ref.url = url;
    return ref;
}

function collectTaskSessionFiles(task, byKey) {
    for (const ref of conversationUserFiles(task)) {
        upsertSessionFile(byKey, ref);
    }
    const artifacts = Array.isArray(task.artifacts) ? task.artifacts : [];
    for (const artifact of artifacts) {
        if (!artifact || typeof artifact !== 'object') continue;
        for (const part of Array.isArray(artifact.parts) ? artifact.parts : []) {
            const ref = fileRefFromA2aFilePart(part);
            if (ref) upsertSessionFile(byKey, ref);
            const data = part && typeof part === 'object' ? part.data : null;
            if (data && typeof data === 'object' && Array.isArray(data.files)) {
                for (const item of data.files) upsertSessionFile(byKey, item);
            }
            if (data && typeof data === 'object' && Array.isArray(data.file_ids)) {
                for (const fileId of data.file_ids) {
                    if (typeof fileId !== 'string' || fileId.trim() === '') continue;
                    upsertSessionFile(byKey, { file_id: fileId.trim() });
                }
            }
        }
    }
    const history = Array.isArray(task.history) ? task.history : [];
    for (const message of history) {
        if (!message || typeof message !== 'object') continue;
        for (const part of Array.isArray(message.parts) ? message.parts : []) {
            const ref = fileRefFromA2aFilePart(part);
            if (ref) upsertSessionFile(byKey, ref);
        }
    }
}

/**
 * Unique FileRefs across conversation tasks (user attachments + A2A file parts).
 * Used by the session files panel in platform-flow-ui chrome top-actions.
 */
export function conversationSessionFiles(tasks) {
    if (!Array.isArray(tasks)) {
        throw new Error('flow-ui: conversationSessionFiles requires tasks array');
    }
    const byKey = new Map();
    for (const task of tasks) {
        if (!task || typeof task !== 'object') continue;
        collectTaskSessionFiles(task, byKey);
    }
    return Array.from(byKey.values());
}

/**
 * Submit causation ids carried by user_message artifacts (`metadata.mutation_id`).
 * The optimistic pending turn is consumed strictly by this identity.
 */
export function conversationUserMutationIds(task) {
    const ids = new Set();
    for (const artifact of userMessageArtifacts(task)) {
        const metadata = artifact.metadata;
        if (!metadata || typeof metadata !== 'object') continue;
        const mutationId = typeof metadata.mutation_id === 'string' && metadata.mutation_id.trim() !== ''
            ? metadata.mutation_id
            : (typeof metadata.mutationId === 'string' && metadata.mutationId.trim() !== ''
                ? metadata.mutationId
                : null);
        if (mutationId !== null) ids.add(mutationId);
    }
    return ids;
}

/**
 * Pending turn ids already materialized by a real Task projection.
 */
export function consumedPendingTurnIds(tasks, pendingTurns) {
    const pending = Array.isArray(pendingTurns) ? pendingTurns : [];
    if (pending.length === 0) return new Set();
    const pendingIds = new Set(pending.map((item) => item.id));
    const consumed = new Set();
    for (const task of Array.isArray(tasks) ? tasks : []) {
        if (!task || typeof task !== 'object') continue;
        for (const mutationId of conversationUserMutationIds(task)) {
            if (pendingIds.has(mutationId)) consumed.add(mutationId);
        }
    }
    return consumed;
}

function optimisticUserArtifact(item) {
    if (typeof item.id !== 'string' || item.id.trim() === '') {
        throw new Error('flow-ui: pending turn requires id');
    }
    if (typeof item.text !== 'string') {
        throw new Error('flow-ui: pending turn requires text');
    }
    const files = Array.isArray(item.files) ? item.files : [];
    const parts = [];
    if (item.text !== '') parts.push({ text: item.text });
    if (files.length) parts.push({ data: { files } });
    return {
        name: 'user_message',
        parts,
        metadata: { mutation_id: item.id },
    };
}

function makeOptimisticTask(item) {
    return {
        id: `optimistic:${item.id}`,
        status: { state: 'TASK_STATE_SUBMITTED' },
        history: [],
        artifacts: [optimisticUserArtifact(item)],
    };
}

function withOptimisticUser(task, item) {
    // Keep the real task id/status so a completed reply clears the typing bubble.
    const existing = Array.isArray(task.artifacts) ? task.artifacts : [];
    return {
        ...task,
        artifacts: [optimisticUserArtifact(item), ...existing],
    };
}

function taskHasUserTurn(task) {
    return conversationUserText(task) !== '' || conversationUserFiles(task).length > 0;
}

/**
 * Merge optimistic pending user turns with projected tasks for conversation feed.
 *
 * A pending entry drops as soon as a real task carries its `mutation_id`.
 * Until then it is paired with the in-flight (or orphan assistant-only) real
 * task so the user bubble never appears *after* the agent reply, and so
 * typing disappears once that real task is terminal.
 */
export function mergeConversationTasks(tasks, pendingTurns) {
    const real = conversationTimeline(tasks);
    const pending = Array.isArray(pendingTurns) ? pendingTurns : [];
    if (pending.length === 0) {
        return conversationTasks(tasks);
    }

    const consumed = consumedPendingTurnIds(tasks, pending);
    const pendingQueue = pending.filter((item) => !consumed.has(item.id));
    if (pendingQueue.length === 0) {
        return conversationTasks(tasks);
    }

    const result = [];
    for (let index = 0; index < real.length; index += 1) {
        const task = real[index];
        const hasUser = taskHasUserTurn(task);
        const isLastReal = index === real.length - 1;
        const nonTerminal = !isTerminalTaskState(task.status?.state);
        // Pair with the submit's real task: still running, or the latest
        // assistant-only projection that answered before user_message landed.
        const orphanAssistantReply = isLastReal && !hasUser && pendingQueue.length > 0;
        if (!hasUser && pendingQueue.length > 0 && (nonTerminal || orphanAssistantReply)) {
            result.push(withOptimisticUser(task, pendingQueue.shift()));
            continue;
        }
        result.push(task);
    }
    for (const item of pendingQueue) {
        result.push(makeOptimisticTask(item));
    }
    // Drop terminal shells that stayed empty after pairing drained the queue.
    return result.filter((task) => (
        taskHasUserTurn(task)
        || conversationTurnText(task) !== ''
        || !isTerminalTaskState(task.status?.state)
    ));
}

/**
 * Conversation turn text: streamed `response` artifact wins; otherwise A2A status.message.
 * Observability artifacts (node_complete_*, tool_result:*) are not conversation content.
 */
export function conversationTurnText(task) {
    if (!task || typeof task !== 'object') {
        throw new Error('flow-ui: conversationTurnText requires task object');
    }
    const responseArtifacts = (Array.isArray(task.artifacts) ? task.artifacts : [])
        .filter(isResponseArtifact);
    const fromArtifacts = responseArtifacts
        .map((artifact) => textFromParts(artifact.parts))
        .join('');
    if (fromArtifacts !== '') return fromArtifacts;
    const message = task.status?.message;
    if (message && typeof message === 'object' && !isUserRole(messageRole(message))) {
        return textFromParts(message.parts);
    }
    return '';
}

export function isTerminalTaskState(state) {
    return TERMINAL_TASK_STATES.has(state);
}

/**
 * Latest non-terminal Task — the turn the flow is answering right now.
 */
export function activeConversationTask(tasks) {
    if (!Array.isArray(tasks)) return null;
    for (let index = tasks.length - 1; index >= 0; index -= 1) {
        const task = tasks[index];
        if (!task || typeof task !== 'object') continue;
        if (!isTerminalTaskState(task.status?.state)) return task;
    }
    return null;
}

/**
 * Tasks visible in the conversation timeline: turns with content, plus
 * non-terminal tasks that are still waiting for the first chunk.
 */
export function conversationTimeline(tasks) {
    if (!Array.isArray(tasks)) {
        throw new Error('flow-ui: conversationTimeline requires tasks array');
    }
    return tasks.filter((task) => {
        if (!task || typeof task !== 'object') return false;
        if (!isTerminalTaskState(task.status?.state)) return true;
        return (
            conversationTurnText(task) !== ''
            || conversationUserText(task) !== ''
            || conversationUserFiles(task).length > 0
        );
    });
}

export function conversationTasks(tasks) {
    if (!Array.isArray(tasks)) {
        throw new Error('flow-ui: conversationTasks requires tasks array');
    }
    return tasks.filter((task) => (
        conversationTurnText(task) !== ''
        || conversationUserText(task) !== ''
        || conversationUserFiles(task).length > 0
    ));
}

export function hasConversationContent(tasks) {
    return conversationTasks(tasks).length > 0;
}

export function isOrdinaryConversationArtifact(artifact) {
    return isOrdinaryFeedArtifact(artifact);
}
