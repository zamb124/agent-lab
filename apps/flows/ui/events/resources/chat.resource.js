/**
 * Flows Chat — отправка реплики через WS request-reply + push-события.
 *
 * Транспорт:
 *   - `flows/chat/send_requested` — `transport: 'ws'`, ack возвращает
 *     `{ task_id, context_id, flow_id, correlation_id }`. REST-зеркало:
 *     `POST /flows/api/v1/{flow_id}` (A2A JSON-RPC `message/stream`).
 *   - `flows/chat/cancel_requested` — `transport: 'ws'`. REST-зеркало:
 *     то же `POST` с `tasks/cancel`.
 *
 * Push-события `flows/chat/*` публикуются из бэкенда в
 * `apps/flows/src/services/chat_stream_publisher.py` через
 * `core.ui_events.publish_ui_event_to_user`. Слайс хранит сообщения по
 * `contextId` и накапливает чанки.
 */

import { createResourceCollection, createAsyncOp } from '@platform/lib/events/index.js';

const EMPTY_LIST = Object.freeze([]);
const EMPTY_OBJECT = Object.freeze({});

function _ensureContextBucket(state, contextId) {
    if (typeof contextId !== 'string' || contextId.length === 0) return state;
    if (state.messagesByContextId[contextId]) return state;
    return {
        ...state,
        messagesByContextId: {
            ...state.messagesByContextId,
            [contextId]: { messages: EMPTY_LIST, taskId: null },
        },
    };
}

function _findOrCreateAssistantMessage(messages, taskId) {
    if (!Array.isArray(messages)) return { messages: [], message: null };
    const idx = messages.findIndex(
        (m) => m && m.role === 'assistant' && m.taskId === taskId && m.streaming !== false,
    );
    if (idx >= 0) {
        return { messages, message: messages[idx], idx };
    }
    const message = {
        id: `assistant_${taskId}`,
        role: 'assistant',
        content: '',
        reasoning: '',
        toolCalls: [],
        toolResults: [],
        streaming: true,
        taskId,
        inputRequired: null,
        breakpoint: null,
        operatorReplies: [],
    };
    return { messages: [...messages, message], message, idx: messages.length };
}

function _replaceMessage(messages, idx, updater) {
    const current = messages[idx];
    const next = updater(current);
    if (next === current) return messages;
    return messages.map((m, i) => (i === idx ? next : m));
}

function _pushMessage(state, contextId, message) {
    const bucket = state.messagesByContextId[contextId];
    if (!bucket) return state;
    return {
        ...state,
        messagesByContextId: {
            ...state.messagesByContextId,
            [contextId]: { ...bucket, messages: [...bucket.messages, message] },
        },
    };
}

function _bucketByTaskId(state, taskId) {
    for (const [ctxId, bucket] of Object.entries(state.messagesByContextId)) {
        if (bucket.taskId === taskId) {
            return { contextId: ctxId, bucket };
        }
        const exists = bucket.messages.some((m) => m && m.taskId === taskId);
        if (exists) {
            return { contextId: ctxId, bucket };
        }
    }
    return null;
}

function _applyToBucketMessages(state, taskId, mutator) {
    const found = _bucketByTaskId(state, taskId);
    if (!found) return state;
    const { contextId, bucket } = found;
    const nextMessages = mutator(bucket.messages, taskId);
    if (nextMessages === bucket.messages) return state;
    return {
        ...state,
        messagesByContextId: {
            ...state.messagesByContextId,
            [contextId]: { ...bucket, messages: nextMessages },
        },
    };
}

function _appendChunk(field, text) {
    return (messages, taskId) => {
        if (typeof text !== 'string' || text.length === 0) return messages;
        const { messages: nextMsgs, idx } = _findOrCreateAssistantMessage(messages, taskId);
        return _replaceMessage(nextMsgs, idx, (m) => ({
            ...m,
            [field]: (m[field] || '') + text,
        }));
    };
}

function _setMessageFields(taskId, fields) {
    return (messages) => {
        const { messages: nextMsgs, idx } = _findOrCreateAssistantMessage(messages, taskId);
        return _replaceMessage(nextMsgs, idx, (m) => ({ ...m, ...fields }));
    };
}

export const chatSendOp = createAsyncOp({
    name: 'flows/chat_send',
    transport: 'ws',
    wsTimeoutMs: 30_000,
    restMirror: { method: 'POST', path: '/flows/api/v1/{flow_id}' },
    silent: true,
});

export const chatCancelOp = createAsyncOp({
    name: 'flows/chat_cancel',
    transport: 'ws',
    wsTimeoutMs: 5_000,
    restMirror: { method: 'POST', path: '/flows/api/v1/{flow_id}' },
    silent: true,
});

export const chatResource = createResourceCollection({
    name: 'flows/chat',
    baseUrl: '/flows/api/v1/sessions',
    idField: 'session_id',
    operations: ['list'],
    extraInitial: {
        messagesByContextId: EMPTY_OBJECT,
        currentContextId: null,
        currentFlowId: null,
        currentTaskId: null,
        streaming: false,
        sessionId: null,
    },
    extraEvents: {
        SESSION_INIT: 'session_init',
        SESSION_RESET: 'session_reset',
        USER_MESSAGE_ADDED: 'user_message_added',
        SESSION_LOADED: 'session_loaded',
    },
    actions: {
        initSession: 'session_init',
        resetSession: 'session_reset',
        addUserMessage: 'user_message_added',
        loadSession: 'session_loaded',
    },
    extraReducer: (state, event) => {
        const type = event.type;

        if (type === 'flows/chat/session_init') {
            const p = event.payload || {};
            const flowId = typeof p.flowId === 'string' ? p.flowId : null;
            const contextId = typeof p.contextId === 'string' && p.contextId.length > 0
                ? p.contextId
                : `${Date.now()}`;
            const next = _ensureContextBucket(state, contextId);
            return {
                ...next,
                currentContextId: contextId,
                currentFlowId: flowId,
                currentTaskId: null,
                streaming: false,
                sessionId: null,
            };
        }

        if (type === 'flows/chat/session_reset') {
            const contextId = `${Date.now()}`;
            return {
                ...state,
                messagesByContextId: {
                    ...state.messagesByContextId,
                    [contextId]: { messages: EMPTY_LIST, taskId: null },
                },
                currentContextId: contextId,
                currentTaskId: null,
                streaming: false,
                sessionId: null,
            };
        }

        if (type === 'flows/chat/session_loaded') {
            const p = event.payload || {};
            const sessionId = typeof p.sessionId === 'string' ? p.sessionId : null;
            const flowId = typeof p.flowId === 'string' ? p.flowId : state.currentFlowId;
            const messages = Array.isArray(p.messages) ? p.messages : [];
            const taskId = typeof p.taskId === 'string' ? p.taskId : null;
            const contextId = typeof p.contextId === 'string' && p.contextId.length > 0
                ? p.contextId
                : (sessionId && sessionId.includes(':') ? sessionId.split(':').slice(1).join(':') : sessionId || `${Date.now()}`);
            return {
                ...state,
                messagesByContextId: {
                    ...state.messagesByContextId,
                    [contextId]: { messages, taskId },
                },
                currentContextId: contextId,
                currentFlowId: flowId,
                currentTaskId: taskId,
                streaming: false,
                sessionId,
            };
        }

        if (type === 'flows/chat/user_message_added') {
            const p = event.payload || {};
            const contextId = typeof p.contextId === 'string' ? p.contextId : state.currentContextId;
            if (!contextId) return state;
            const message = p.message;
            if (!message || typeof message !== 'object') return state;
            const ensured = _ensureContextBucket(state, contextId);
            return _pushMessage(ensured, contextId, message);
        }

        // -------- ack from chatSendOp ----------
        if (type === 'flows/chat_send/succeeded') {
            const p = (event.payload && event.payload.result) || {};
            const taskId = typeof p.task_id === 'string' ? p.task_id : null;
            const contextId = typeof p.context_id === 'string'
                ? p.context_id
                : state.currentContextId;
            if (!taskId || !contextId) return state;
            const bucket = state.messagesByContextId[contextId];
            if (!bucket) return state;
            return {
                ...state,
                currentContextId: contextId,
                currentTaskId: taskId,
                streaming: true,
                messagesByContextId: {
                    ...state.messagesByContextId,
                    [contextId]: { ...bucket, taskId },
                },
            };
        }
        if (type === 'flows/chat_send/failed') {
            return { ...state, streaming: false };
        }

        // -------- push events from backend ----------
        if (type === 'flows/chat/task_started') {
            const taskId = event.payload && typeof event.payload.task_id === 'string'
                ? event.payload.task_id
                : null;
            if (!taskId) return state;
            return { ...state, currentTaskId: taskId, streaming: true };
        }

        if (type === 'flows/chat/content_chunk') {
            const p = event.payload || {};
            const taskId = typeof p.task_id === 'string' ? p.task_id : null;
            const text = typeof p.text === 'string' ? p.text : '';
            if (!taskId) return state;
            return _applyToBucketMessages(state, taskId, _appendChunk('content', text));
        }

        if (type === 'flows/chat/reasoning_chunk') {
            const p = event.payload || {};
            const taskId = typeof p.task_id === 'string' ? p.task_id : null;
            const text = typeof p.text === 'string' ? p.text : '';
            if (!taskId) return state;
            return _applyToBucketMessages(state, taskId, _appendChunk('reasoning', text));
        }

        if (type === 'flows/chat/operator_reply') {
            const p = event.payload || {};
            const taskId = typeof p.task_id === 'string' ? p.task_id : null;
            const text = typeof p.text === 'string' ? p.text : '';
            if (!taskId || !text) return state;
            return _applyToBucketMessages(state, taskId, (messages) => {
                const operatorMsg = {
                    id: `operator_${taskId}_${Date.now()}`,
                    role: 'operator',
                    content: text,
                    timestamp: new Date().toISOString(),
                    fileIds: [],
                };
                return [...messages, operatorMsg];
            });
        }

        if (type === 'flows/chat/operator_files') {
            const p = event.payload || {};
            const taskId = typeof p.task_id === 'string' ? p.task_id : null;
            const fileIds = Array.isArray(p.file_ids) ? p.file_ids : [];
            if (!taskId || fileIds.length === 0) return state;
            return _applyToBucketMessages(state, taskId, (messages) => {
                for (let i = messages.length - 1; i >= 0; i--) {
                    const m = messages[i];
                    if (m && m.role === 'operator') {
                        return _replaceMessage(messages, i, (cur) => ({
                            ...cur,
                            fileIds: [...(cur.fileIds || []), ...fileIds],
                        }));
                    }
                }
                return [
                    ...messages,
                    {
                        id: `operator_${taskId}_${Date.now()}`,
                        role: 'operator',
                        content: '',
                        timestamp: new Date().toISOString(),
                        fileIds,
                    },
                ];
            });
        }

        if (type === 'flows/chat/tool_calls') {
            const p = event.payload || {};
            const taskId = typeof p.task_id === 'string' ? p.task_id : null;
            const newCalls = Array.isArray(p.tool_calls) ? p.tool_calls : [];
            if (!taskId || newCalls.length === 0) return state;
            return _applyToBucketMessages(state, taskId, (messages) => {
                const { messages: nextMsgs, idx } = _findOrCreateAssistantMessage(messages, taskId);
                return _replaceMessage(nextMsgs, idx, (m) => {
                    const existing = Array.isArray(m.toolCalls) ? m.toolCalls : [];
                    const ids = new Set(existing.map((tc) => tc && tc.id));
                    const additions = newCalls.filter((tc) => tc && !ids.has(tc.id));
                    if (additions.length === 0) return m;
                    return { ...m, toolCalls: [...existing, ...additions] };
                });
            });
        }

        if (type === 'flows/chat/tool_result') {
            const p = event.payload || {};
            const taskId = typeof p.task_id === 'string' ? p.task_id : null;
            const tr = p.tool_result;
            if (!taskId || !tr || typeof tr !== 'object') return state;
            return _applyToBucketMessages(state, taskId, (messages) => {
                const { messages: nextMsgs, idx } = _findOrCreateAssistantMessage(messages, taskId);
                return _replaceMessage(nextMsgs, idx, (m) => {
                    const existing = Array.isArray(m.toolResults) ? m.toolResults : [];
                    if (existing.find((r) => r && r.id === tr.id)) return m;
                    return { ...m, toolResults: [...existing, tr] };
                });
            });
        }

        if (type === 'flows/chat/breakpoint') {
            const p = event.payload || {};
            const taskId = typeof p.task_id === 'string' ? p.task_id : null;
            const breakpoint = p.breakpoint;
            if (!taskId || !breakpoint) return state;
            const next = _applyToBucketMessages(
                state,
                taskId,
                _setMessageFields(taskId, { breakpoint, streaming: false }),
            );
            return { ...next, streaming: false };
        }

        if (type === 'flows/chat/input_required') {
            const p = event.payload || {};
            const taskId = typeof p.task_id === 'string' ? p.task_id : null;
            if (!taskId) return state;
            const inputRequired = {
                question: '',
                interruptKind: null,
                resultMetadata: p.result_metadata || {},
                messageMetadata: p.message_metadata || {},
                message: p.message || null,
            };
            const next = _applyToBucketMessages(
                state,
                taskId,
                _setMessageFields(taskId, { inputRequired, streaming: false }),
            );
            return { ...next, streaming: false };
        }

        if (type === 'flows/chat/completed') {
            const p = event.payload || {};
            const taskId = typeof p.task_id === 'string' ? p.task_id : null;
            const content = typeof p.content === 'string' ? p.content : '';
            if (!taskId) return state;
            const next = _applyToBucketMessages(state, taskId, (messages) => {
                const { messages: nextMsgs, idx } = _findOrCreateAssistantMessage(messages, taskId);
                return _replaceMessage(nextMsgs, idx, (m) => {
                    const updated = { ...m, streaming: false, inputRequired: null };
                    if (content && (!m.content || m.content.trim() === '')) {
                        updated.content = content;
                    }
                    return updated;
                });
            });
            return { ...next, streaming: false, currentTaskId: taskId };
        }

        if (type === 'flows/chat/failed') {
            const p = event.payload || {};
            const taskId = typeof p.task_id === 'string' ? p.task_id : null;
            const errorText = typeof p.error === 'string' ? p.error : 'error';
            if (!taskId) return { ...state, streaming: false };
            const next = _applyToBucketMessages(
                state,
                taskId,
                _setMessageFields(taskId, {
                    streaming: false,
                    inputRequired: null,
                    error: errorText,
                }),
            );
            return { ...next, streaming: false };
        }

        return state;
    },
});
