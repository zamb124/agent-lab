/**
 * Flows Chat — стриминг A2A через SSE.
 *
 * Транспорт:
 *   - `flows/chat_send` — `transport: 'http'`, внутри `request` шлёт
 *     `POST /flows/api/v1/{flow_id}` с JSON-RPC `message/stream`,
 *     читает SSE-ответ и для каждого A2A-фрейма диспатчит локальное
 *     событие `flows/chat/<verb>` (ниже маппинг). Резолвит при
 *     терминальном `state in ('completed','failed','input-required')`
 *     или после исчерпания стрима.
 *   - `flows/chat_cancel` — `transport: 'http'`, тот же эндпоинт с
 *     JSON-RPC `tasks/cancel`.
 *
 * Источник правды для бекенда — `_handle_streaming` в
 * `apps/flows/src/api/a2a.py`. Reducer слайса (`extraReducer` ниже)
 * хранит сообщения по `contextId` и накапливает чанки.
 */

import { createResourceCollection, createAsyncOp, HttpError, httpRequest, httpStream } from '@platform/lib/events/index.js';

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
            [field]: (typeof m[field] === 'string' ? m[field] : '') + text,
        }));
    };
}

function _setMessageFields(taskId, fields) {
    return (messages) => {
        const { messages: nextMsgs, idx } = _findOrCreateAssistantMessage(messages, taskId);
        return _replaceMessage(nextMsgs, idx, (m) => ({ ...m, ...fields }));
    };
}

function _extractTextFromParts(parts) {
    if (!Array.isArray(parts)) return '';
    return parts
        .filter((p) => p && p.kind === 'text' && typeof p.text === 'string' && p.text.length > 0)
        .map((p) => p.text)
        .join('');
}

function _resolveTaskId(result, fallback) {
    if (result && typeof result === 'object') {
        if (typeof result.taskId === 'string') return result.taskId;
        if (typeof result.task_id === 'string') return result.task_id;
        const status = result.status;
        if (status && typeof status === 'object') {
            if (typeof status.taskId === 'string') return status.taskId;
            if (typeof status.task_id === 'string') return status.task_id;
        }
    }
    return fallback;
}

function _isTerminalState(state, final) {
    if (state === 'completed' || state === 'finished' || state === 'failed' || state === 'error') {
        return true;
    }
    if ((state === 'input-required' || state === 'input_required') && final) {
        return true;
    }
    return false;
}

/**
 * Маппинг A2A-фрейма (`result` из JSON-RPC) в локальные события
 * `flows/chat/<verb>`. Возвращает `task_id` фрейма, если он там есть,
 * иначе — переданный `currentTaskId`.
 */
function _dispatchA2aEvent(ctx, contextId, currentTaskId, result, causationId) {
    if (!result || typeof result !== 'object') return currentTaskId;

    if (result.kind === 'task' || (typeof result.id === 'string' && !result.kind)) {
        const taskId = _resolveTaskId(result, currentTaskId);
        if (taskId && taskId !== currentTaskId) {
            ctx.dispatch(
                'flows/chat/task_started',
                { task_id: taskId, context_id: contextId },
                { causation_id: causationId, source: 'http' },
            );
        }
        return taskId;
    }

    if (result.kind === 'message') {
        const message = result;
        const taskId = _resolveTaskId(message, currentTaskId);
        _dispatchMessageMetadata(ctx, taskId, message, causationId);
        return taskId;
    }

    if (result.kind === 'artifact-update') {
        const taskId = _resolveTaskId(result, currentTaskId);
        const artifact = result.artifact;
        const final = result.final === true;

        if (artifact && Array.isArray(artifact.parts)) {
            const text = _extractTextFromParts(artifact.parts);
            if (text) {
                if (artifact.name === 'reasoning') {
                    ctx.dispatch(
                        'flows/chat/reasoning_chunk',
                        { task_id: taskId, text },
                        { causation_id: causationId, source: 'http' },
                    );
                } else if (artifact.name === 'operator_reply') {
                    ctx.dispatch(
                        'flows/chat/operator_reply',
                        { task_id: taskId, text },
                        { causation_id: causationId, source: 'http' },
                    );
                } else if (artifact.name !== 'operator_files') {
                    ctx.dispatch(
                        'flows/chat/content_chunk',
                        { task_id: taskId, text },
                        { causation_id: causationId, source: 'http' },
                    );
                }
            }

            if (artifact.name === 'operator_files') {
                const dataPart = artifact.parts.find(
                    (p) => p && p.data && Array.isArray(p.data.file_ids),
                );
                if (dataPart) {
                    ctx.dispatch(
                        'flows/chat/operator_files',
                        { task_id: taskId, file_ids: dataPart.data.file_ids },
                        { causation_id: causationId, source: 'http' },
                    );
                }
            }
        }

        const message = artifact && artifact.message ? artifact.message : null;
        if (message) {
            _dispatchMessageMetadata(ctx, taskId, message, causationId);
            const text = _extractTextFromParts(message.parts);
            if (text) {
                ctx.dispatch(
                    'flows/chat/content_chunk',
                    { task_id: taskId, text },
                    { causation_id: causationId, source: 'http' },
                );
            }
        }

        const state = artifact ? artifact.state : null;
        if (final) {
            _dispatchTerminal(ctx, contextId, taskId, state, message, result.metadata, causationId);
        }
        return taskId;
    }

    if (result.kind === 'status-update') {
        const status = result.status;
        if (!status) return currentTaskId;
        const taskId = _resolveTaskId(result, currentTaskId);
        const message = status.message;
        const state = status.state;
        const final = result.final === true;
        const metadata = _resolveStatusMetadata(result, message);

        if (message) {
            _dispatchMessageMetadata(ctx, taskId, message, causationId);
        }

        if (state === 'input-required' || state === 'input_required') {
            const handoffContinue = metadata && metadata.platform_handoff_continue === true;
            const oauthContinue = metadata && metadata.platform_oauth_continue === true;
            if (final || handoffContinue || oauthContinue) {
                _dispatchInputRequired(ctx, contextId, taskId, message, metadata, causationId);
            }
            return taskId;
        }

        if (final || state === 'completed' || state === 'finished' || state === 'failed' || state === 'error') {
            _dispatchTerminal(ctx, contextId, taskId, state, message, metadata, causationId);
        }
        return taskId;
    }

    return currentTaskId;
}

function _resolveStatusMetadata(result, message) {
    if (result && typeof result === 'object' && result.metadata && typeof result.metadata === 'object') {
        return result.metadata;
    }
    if (message && typeof message === 'object' && message.metadata && typeof message.metadata === 'object') {
        return message.metadata;
    }
    return {};
}

function _dispatchMessageMetadata(ctx, taskId, message, causationId) {
    if (!taskId || !message || typeof message !== 'object') return;
    const metadata = message.metadata;
    if (!metadata || typeof metadata !== 'object') return;
    if (Array.isArray(metadata.tool_calls) && metadata.tool_calls.length > 0) {
        ctx.dispatch(
            'flows/chat/tool_calls',
            { task_id: taskId, tool_calls: metadata.tool_calls },
            { causation_id: causationId, source: 'http' },
        );
    }
    if (metadata.tool_result && typeof metadata.tool_result === 'object') {
        ctx.dispatch(
            'flows/chat/tool_result',
            { task_id: taskId, tool_result: metadata.tool_result },
            { causation_id: causationId, source: 'http' },
        );
    }
}

function _dispatchInputRequired(ctx, contextId, taskId, message, metadata, causationId) {
    if (!taskId) return;
    const meta = metadata;
    if (meta.breakpoint) {
        ctx.dispatch(
            'flows/chat/breakpoint',
            {
                task_id: taskId,
                context_id: contextId,
                breakpoint: {
                    node_id: meta.breakpoint.node_id,
                    state: meta.breakpoint.state,
                    step: meta.breakpoint.step,
                    data: meta.breakpoint.data,
                },
            },
            { causation_id: causationId, source: 'http' },
        );
        return;
    }
    ctx.dispatch(
        'flows/chat/input_required',
        {
            task_id: taskId,
            context_id: contextId,
            result_metadata: meta,
            message_metadata: message && message.metadata ? message.metadata : {},
            message: typeof message === 'object' && message !== null ? message : null,
        },
        { causation_id: causationId, source: 'http' },
    );
}

function _dispatchTerminal(ctx, contextId, taskId, state, message, metadata, causationId) {
    if (!taskId) return;
    if (state === 'completed' || state === 'finished') {
        const text = message ? _extractTextFromParts(message.parts) : '';
        ctx.dispatch(
            'flows/chat/completed',
            { task_id: taskId, context_id: contextId, content: text },
            { causation_id: causationId, source: 'http' },
        );
        return;
    }
    if (state === 'failed' || state === 'error') {
        const text = message ? _extractTextFromParts(message.parts) : '';
        ctx.dispatch(
            'flows/chat/failed',
            { task_id: taskId, context_id: contextId, error: text.length > 0 ? text : 'error' },
            { causation_id: causationId, source: 'http' },
        );
        return;
    }
    if (state === 'input-required' || state === 'input_required') {
        _dispatchInputRequired(ctx, contextId, taskId, message, metadata, causationId);
    }
}

/**
 * Стримит SSE-ответ A2A: для каждого `data: <json>` парсит JSON-RPC и
 * прогоняет `result` через `_dispatchA2aEvent`. Возвращает
 * `{ task_id, context_id }` после первого терминального state или
 * исчерпания стрима.
 */
async function _consumeA2aStream(req, ctx, contextId, causationId) {
    let taskId = null;
    let terminal = false;
    await httpStream(req, (frame) => {
        if (terminal) return;
        if (!frame || typeof frame !== 'object') return;
        if (frame.error) {
            const err = frame.error;
            let errMsg = 'a2a stream error';
            if (err && typeof err === 'object') {
                if (typeof err.message === 'string' && err.message.length > 0) errMsg = err.message;
                else if (typeof err.code === 'string' && err.code.length > 0) errMsg = err.code;
            }
            throw new HttpError(errMsg, 0, frame.error);
        }
        const result = frame.result;
        if (!result) return;
        const nextTaskId = _dispatchA2aEvent(ctx, contextId, taskId, result, causationId);
        if (nextTaskId) taskId = nextTaskId;
        let stateValue = null;
        if (result.kind === 'status-update' && result.status && typeof result.status.state === 'string') {
            stateValue = result.status.state;
        } else if (result.kind === 'artifact-update' && result.artifact && typeof result.artifact.state === 'string') {
            stateValue = result.artifact.state;
        }
        if (_isTerminalState(stateValue, result.final === true)) {
            terminal = true;
        }
    });
    return { task_id: taskId, context_id: contextId };
}

export const chatSendOp = createAsyncOp({
    name: 'flows/chat_send',
    transport: 'http',
    silent: true,
    // A2A JSON-RPC endpoint per-flow (см. apps/flows/src/api/a2a.py — мапит
    // POST /flows/api/v1/{flow_id} в обработчик A2A-методов message/stream и
    // tasks/cancel). UI шлёт SSE-стрим, поэтому _consumeA2aStream вместо
    // httpRequest, но REST-зеркало одно и то же.
    restMirror: { method: 'POST', path: '/flows/api/v1/:flow_id' },
    request: async ({ payload, ctx, event }) => {
        if (!payload || typeof payload !== 'object') {
            throw new Error('flows/chat_send: payload required');
        }
        const flowId = payload.flow_id;
        const params = payload.params;
        if (typeof flowId !== 'string' || !flowId) {
            throw new Error('flows/chat_send: flow_id required');
        }
        if (!params || typeof params !== 'object' || !params.message) {
            throw new Error('flows/chat_send: params.message required');
        }
        const contextId =
            typeof params.message.contextId === 'string' && params.message.contextId.length > 0
                ? params.message.contextId
                : null;
        const body = {
            jsonrpc: '2.0',
            id: `${Date.now()}`,
            method: 'message/stream',
            params,
        };
        return _consumeA2aStream(
            {
                url: `/flows/api/v1/${encodeURIComponent(flowId)}`,
                method: 'POST',
                headers: { Accept: 'text/event-stream' },
                credentials: 'same-origin',
                body,
            },
            ctx,
            contextId,
            event && event.id,
        );
    },
});

export const chatCancelOp = createAsyncOp({
    name: 'flows/chat_cancel',
    transport: 'http',
    silent: true,
    // Тот же A2A endpoint per-flow: tasks/cancel JSON-RPC method.
    restMirror: { method: 'POST', path: '/flows/api/v1/:flow_id' },
    request: async ({ payload }) => {
        if (!payload || typeof payload !== 'object') {
            throw new Error('flows/chat_cancel: payload required');
        }
        const flowId = payload.flow_id;
        const taskId = payload.task_id;
        if (typeof flowId !== 'string' || !flowId) {
            throw new Error('flows/chat_cancel: flow_id required');
        }
        if (typeof taskId !== 'string' || !taskId) {
            throw new Error('flows/chat_cancel: task_id required');
        }
        const body = {
            jsonrpc: '2.0',
            id: `${Date.now()}`,
            method: 'tasks/cancel',
            params: { id: taskId },
        };
        return httpRequest({
            url: `/flows/api/v1/${encodeURIComponent(flowId)}`,
            method: 'POST',
            credentials: 'same-origin',
            body,
        });
    },
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
            const p = event.payload;
            if (!p || typeof p !== 'object') return state;
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
            const p = event.payload;
            if (!p || typeof p !== 'object') return state;
            const sessionId = typeof p.sessionId === 'string' ? p.sessionId : null;
            const flowId = typeof p.flowId === 'string' ? p.flowId : state.currentFlowId;
            const messages = Array.isArray(p.messages) ? p.messages : [];
            const taskId = typeof p.taskId === 'string' ? p.taskId : null;
            let contextId;
            if (typeof p.contextId === 'string' && p.contextId.length > 0) {
                contextId = p.contextId;
            } else if (typeof sessionId === 'string' && sessionId.includes(':')) {
                contextId = sessionId.split(':').slice(1).join(':');
            } else if (typeof sessionId === 'string' && sessionId.length > 0) {
                contextId = sessionId;
            } else {
                contextId = `${Date.now()}`;
            }
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
            const p = event.payload;
            if (!p || typeof p !== 'object') return state;
            const contextId = typeof p.contextId === 'string' ? p.contextId : state.currentContextId;
            if (!contextId) return state;
            const message = p.message;
            if (!message || typeof message !== 'object') return state;
            const ensured = _ensureContextBucket(state, contextId);
            return _pushMessage(ensured, contextId, message);
        }

        if (type === 'flows/chat_send/succeeded') {
            const result = event.payload && typeof event.payload === 'object' ? event.payload.result : null;
            const p = result && typeof result === 'object' ? result : null;
            if (!p) return { ...state, streaming: true };
            const taskId = typeof p.task_id === 'string' ? p.task_id : null;
            const contextId = typeof p.context_id === 'string'
                ? p.context_id
                : state.currentContextId;
            // chat_send ack означает что бэк принял запрос — стрим chunks/artifacts
            // ещё впереди, поэтому streaming: true до terminal-события.
            const next = { ...state, streaming: true };
            if (!taskId || !contextId) return next;
            const bucket = next.messagesByContextId[contextId];
            if (!bucket) return next;
            return {
                ...next,
                currentContextId: contextId,
                currentTaskId: taskId,
                messagesByContextId: {
                    ...next.messagesByContextId,
                    [contextId]: { ...bucket, taskId },
                },
            };
        }
        if (type === 'flows/chat_send/failed') {
            return { ...state, streaming: false };
        }

        if (type === 'flows/chat/task_started') {
            const p = event.payload;
            if (!p || typeof p !== 'object') return state;
            const taskId = typeof p.task_id === 'string' ? p.task_id : null;
            const contextId = typeof p.context_id === 'string'
                ? p.context_id
                : state.currentContextId;
            if (!taskId) return state;
            let next = state;
            if (contextId) {
                next = _ensureContextBucket(next, contextId);
                const bucket = next.messagesByContextId[contextId];
                if (bucket) {
                    next = {
                        ...next,
                        currentContextId: contextId,
                        messagesByContextId: {
                            ...next.messagesByContextId,
                            [contextId]: { ...bucket, taskId },
                        },
                    };
                }
            }
            return { ...next, currentTaskId: taskId, streaming: true };
        }

        if (type === 'flows/chat/content_chunk') {
            const p = event.payload;
            if (!p || typeof p !== 'object') return state;
            const taskId = typeof p.task_id === 'string' ? p.task_id : null;
            const text = typeof p.text === 'string' ? p.text : '';
            if (!taskId) return state;
            return _applyToBucketMessages(state, taskId, _appendChunk('content', text));
        }

        if (type === 'flows/chat/reasoning_chunk') {
            const p = event.payload;
            if (!p || typeof p !== 'object') return state;
            const taskId = typeof p.task_id === 'string' ? p.task_id : null;
            const text = typeof p.text === 'string' ? p.text : '';
            if (!taskId) return state;
            return _applyToBucketMessages(state, taskId, _appendChunk('reasoning', text));
        }

        if (type === 'flows/chat/operator_reply') {
            const p = event.payload;
            if (!p || typeof p !== 'object') return state;
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
            const p = event.payload;
            if (!p || typeof p !== 'object') return state;
            const taskId = typeof p.task_id === 'string' ? p.task_id : null;
            const fileIds = Array.isArray(p.file_ids) ? p.file_ids : [];
            if (!taskId || fileIds.length === 0) return state;
            return _applyToBucketMessages(state, taskId, (messages) => {
                for (let i = messages.length - 1; i >= 0; i--) {
                    const m = messages[i];
                    if (m && m.role === 'operator') {
                        return _replaceMessage(messages, i, (cur) => ({
                            ...cur,
                            fileIds: [...(Array.isArray(cur.fileIds) ? cur.fileIds : []), ...fileIds],
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
            const p = event.payload;
            if (!p || typeof p !== 'object') return state;
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
            const p = event.payload;
            if (!p || typeof p !== 'object') return state;
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
            const p = event.payload;
            if (!p || typeof p !== 'object') return state;
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
            const p = event.payload;
            if (!p || typeof p !== 'object') return state;
            const taskId = typeof p.task_id === 'string' ? p.task_id : null;
            if (!taskId) return state;
            const inputRequired = {
                question: '',
                interruptKind: null,
                resultMetadata: p.result_metadata && typeof p.result_metadata === 'object' ? p.result_metadata : {},
                messageMetadata: p.message_metadata && typeof p.message_metadata === 'object' ? p.message_metadata : {},
                message: p.message && typeof p.message === 'object' ? p.message : null,
            };
            const next = _applyToBucketMessages(
                state,
                taskId,
                _setMessageFields(taskId, { inputRequired, streaming: false }),
            );
            return { ...next, streaming: false };
        }

        if (type === 'flows/chat/completed') {
            const p = event.payload;
            if (!p || typeof p !== 'object') return state;
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
            const p = event.payload;
            if (!p || typeof p !== 'object') return state;
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
