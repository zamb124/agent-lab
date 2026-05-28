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
import {
    inputRequiredFieldsFromA2a as _inputRequiredFieldsFromPayload,
    isA2aTerminalState as _isTerminalState,
    mapA2aResultToChatRuntimeEvents,
    resolveA2aContextId as _resolveStreamContextId,
} from '@platform/lib/flows-chat/a2a-chat-runtime.js';
import {
    feedStreamTtsFromA2aResult,
    stopStreamTtsPlayback,
} from '@platform/lib/voice/stream-tts-registry.js';

const EMPTY_LIST = Object.freeze([]);
const EMPTY_OBJECT = Object.freeze({});

/** Ключ i18n `flows.chat_message.*` при обрыве SSE без терминального status-update. */
const STREAM_INCOMPLETE_I18N_KEY = 'stream_incomplete';

let _traceSeq = 0;

function _nextTraceId() {
    _traceSeq += 1;
    return `tr_${_traceSeq}`;
}

function _stringOrEmpty(value) {
    return typeof value === 'string' ? value : '';
}

function _stringOrPrevious(value, previous) {
    return typeof value === 'string' ? value : _stringOrEmpty(previous);
}

function _nonEmptyStringOrPrevious(value, previous) {
    if (typeof value === 'string' && value.length > 0) {
        return value;
    }
    return _stringOrEmpty(previous);
}

function _filesByContextMap(value) {
    if (value && typeof value === 'object' && !Array.isArray(value)) {
        return value;
    }
    return EMPTY_OBJECT;
}

/** @param {{ dispatch: Function }} ctx */
function _appendRunTrace(ctx, contextId, taskId, fields, causationId) {
    if (typeof contextId !== 'string' || contextId.length === 0) {
        return;
    }
    if (!fields || typeof fields !== 'object') {
        throw new Error('flows/chat: trace fields required');
    }
    const kind = fields.kind;
    if (typeof kind !== 'string' || kind.length === 0) {
        throw new Error('flows/chat: trace kind required');
    }
    const entry = {
        id: _nextTraceId(),
        ts: Date.now(),
        kind,
    };
    if (typeof taskId === 'string' && taskId.length > 0) {
        entry.task_id = taskId;
    }
    const keys = Object.keys(fields);
    for (let i = 0; i < keys.length; i += 1) {
        const key = keys[i];
        if (key === 'kind') {
            continue;
        }
        entry[key] = fields[key];
    }
    ctx.dispatch(
        'flows/chat/trace_append',
        { context_id: contextId, entry: Object.freeze(entry) },
        { causation_id: causationId, source: 'http' },
    );
}

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

/** Активный bubble ассистента для `taskId`.
 * Resume после interrupt/breakpoint сохраняет тот же backend `taskId`, поэтому
 * внутри одного task может быть несколько assistant-bubble. Live-события всегда
 * пишутся в последний bubble этого task; повторный terminal frame для завершённого
 * хода не создаёт дубль.
 */
function _findOrCreateAssistantMessage(messages, taskId) {
    if (!Array.isArray(messages)) return { messages: [], message: null };
    let idx = -1;
    for (let i = messages.length - 1; i >= 0; i -= 1) {
        const m = messages[i];
        if (m && m.role === 'assistant' && m.taskId === taskId) {
            idx = i;
            break;
        }
    }
    if (idx >= 0) {
        return { messages, message: messages[idx], idx };
    }
    const message = _newAssistantMessage(taskId, `assistant_${taskId}`);
    return { messages: [...messages, message], message, idx: messages.length };
}

function _newAssistantMessage(taskId, id) {
    return {
        id,
        role: 'assistant',
        content: '',
        reasoning: '',
        activity: '',
        error: '',
        errorI18nKey: null,
        toolCalls: [],
        toolResults: [],
        browserPreviews: [],
        files: [],
        streaming: true,
        taskId,
        inputRequired: null,
        breakpoint: null,
        operatorReplies: [],
    };
}

function _assistantMessageIdForAppend(messages, taskId) {
    if (!Array.isArray(messages)) {
        return `assistant_${taskId}`;
    }
    let count = 0;
    for (const m of messages) {
        if (m && m.role === 'assistant' && m.taskId === taskId) {
            count += 1;
        }
    }
    if (count === 0) {
        return `assistant_${taskId}`;
    }
    return `assistant_${taskId}_${count + 1}`;
}

function _hasResumeBoundary(message) {
    if (!message || message.role !== 'assistant') {
        return false;
    }
    return message.inputRequired != null || message.breakpoint != null;
}

function _ensurePlaceholderAssistant(messages, taskId) {
    if (!Array.isArray(messages) || typeof taskId !== 'string' || taskId.length === 0) {
        return messages;
    }
    let lastIdx = -1;
    for (let i = messages.length - 1; i >= 0; i -= 1) {
        const m = messages[i];
        if (m && m.role === 'assistant' && m.taskId === taskId) {
            lastIdx = i;
            break;
        }
    }
    if (lastIdx < 0) {
        const { messages: withAssistant } = _findOrCreateAssistantMessage(messages, taskId);
        return withAssistant;
    }
    if (!_hasResumeBoundary(messages[lastIdx])) {
        return messages;
    }
    return [
        ...messages,
        _newAssistantMessage(taskId, _assistantMessageIdForAppend(messages, taskId)),
    ];
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

/**
 * @param {string | null | undefined} fallbackContextId — из payload A2A (context_id).
 *   Пока стрим не закончен, `flows/chat_send/succeeded` ещё не записал taskId в bucket;
 *   тогда ищем корзину по context_id или по state.currentContextId при streaming.
 */
function _applyToBucketMessages(state, taskId, mutator, fallbackContextId) {
    let found = _bucketByTaskId(state, taskId);
    if (!found) {
        let hint =
            typeof fallbackContextId === 'string' && fallbackContextId.length > 0
                ? fallbackContextId
                : null;
        if (!hint && state.streaming && typeof state.currentContextId === 'string') {
            hint = state.currentContextId;
        }
        if (hint && state.messagesByContextId[hint]) {
            found = { contextId: hint, bucket: state.messagesByContextId[hint] };
        }
    }
    if (!found) return state;
    const { contextId, bucket } = found;
    const nextMessages = mutator(bucket.messages, taskId);
    if (nextMessages === bucket.messages) return state;
    const mergedTaskId = bucket.taskId != null ? bucket.taskId : taskId;
    return {
        ...state,
        messagesByContextId: {
            ...state.messagesByContextId,
            [contextId]: { ...bucket, taskId: mergedTaskId, messages: nextMessages },
        },
    };
}

/**
 * Закрывает «висящий» ассистентский streaming, если HTTP вернулся без
 * терминального A2A-события (например, обрыв до диспатча failed).
 */
function _sweepOrphanStreamingInContext(state, contextId) {
    if (typeof contextId !== 'string' || contextId.length === 0) {
        return state;
    }
    const bucket = state.messagesByContextId[contextId];
    if (!bucket || !Array.isArray(bucket.messages)) {
        return state;
    }
    let changed = false;
    const nextMessages = bucket.messages.map((m) => {
        if (m && m.role === 'assistant' && m.streaming === true) {
            changed = true;
            return {
                ...m,
                streaming: false,
                error: '',
                errorI18nKey: STREAM_INCOMPLETE_I18N_KEY,
                activity: '',
            };
        }
        return m;
    });
    if (!changed) {
        return state;
    }
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

function _browserPreviewSessionId(payload) {
    if (!payload || typeof payload !== 'object') return '';
    const sid = typeof payload.browser_session_id === 'string'
        ? payload.browser_session_id
        : typeof payload.session_id === 'string'
          ? payload.session_id
          : '';
    return sid.trim();
}

function _browserPreviewStatus(eventType, payload) {
    if (eventType.endsWith('.session_closed')) return 'closed';
    if (eventType.endsWith('.tool_failed')) return 'failed';
    if (payload && payload.status === 'failed') return 'failed';
    if (eventType.endsWith('.tool_started')) return 'running';
    return 'live';
}

function _upsertBrowserPreview(list, event) {
    if (!event || typeof event !== 'object') return list;
    const payload = event.payload && typeof event.payload === 'object' ? event.payload : {};
    const sessionId = _browserPreviewSessionId(payload);
    if (sessionId.length === 0) return list;
    const existing = Array.isArray(list) ? list : [];
    const idx = existing.findIndex((item) => item && item.sessionId === sessionId);
    const prev = idx >= 0 ? existing[idx] : {};
    const toolCallId =
        typeof payload.parent_tool_call_id === 'string' && payload.parent_tool_call_id.length > 0
            ? payload.parent_tool_call_id
            : typeof payload.tool_call_id === 'string'
              ? payload.tool_call_id
              : '';
    const next = {
        ...prev,
        sessionId,
        browserSessionId: sessionId,
        toolCallId: _nonEmptyStringOrPrevious(toolCallId, prev.toolCallId),
        parentToolCallId: _nonEmptyStringOrPrevious(toolCallId, prev.parentToolCallId),
        topLevelToolName:
            typeof payload.top_level_tool_name === 'string'
                ? payload.top_level_tool_name
                : _stringOrEmpty(prev.topLevelToolName),
        browserToolName:
            typeof payload.browser_tool_name === 'string'
                ? payload.browser_tool_name
                : _stringOrEmpty(prev.browserToolName),
        status: _browserPreviewStatus(event.type, payload),
        viewerUrl:
            typeof payload.viewer_url === 'string' && payload.viewer_url.length > 0
                ? payload.viewer_url
                : _stringOrEmpty(prev.viewerUrl),
        screenshotUrl:
            typeof payload.screenshot_url === 'string' && payload.screenshot_url.length > 0
                ? payload.screenshot_url
                : _stringOrEmpty(prev.screenshotUrl),
        currentUrl:
            typeof payload.final_url === 'string' && payload.final_url.length > 0
                ? payload.final_url
                : typeof payload.url === 'string' && payload.url.length > 0
                  ? payload.url
                  : _stringOrEmpty(prev.currentUrl),
        lastEventType: _stringOrPrevious(event.type, prev.lastEventType),
        updatedAt:
            typeof event.timestamp === 'string' && event.timestamp.length > 0
                ? event.timestamp
                : new Date().toISOString(),
    };
    if (idx < 0) {
        return [...existing, next];
    }
    return existing.map((item, i) => (i === idx ? next : item));
}

function _normalizeFileItem(item) {
    if (!item || typeof item !== 'object' || Array.isArray(item)) return null;
    const fileId = typeof item.file_id === 'string' ? item.file_id : '';
    const originalName = typeof item.original_name === 'string' ? item.original_name : '';
    const url = typeof item.url === 'string' ? item.url : '';
    const contentType = typeof item.content_type === 'string' ? item.content_type : '';
    const fileSize = typeof item.file_size === 'number' ? item.file_size : null;
    if (!fileId && !url) return null;
    if (originalName.length === 0) return null;
    if (contentType.length === 0) return null;
    if (fileSize === null) return null;
    const { name, path, mime_type, type, size, ...rest } = item;
    return {
        ...rest,
        file_id: fileId,
        original_name: originalName,
        url,
        content_type: contentType,
        file_size: fileSize,
    };
}

function _upsertFiles(list, incoming) {
    const existing = Array.isArray(list) ? list : [];
    const files = Array.isArray(incoming) ? incoming.map(_normalizeFileItem).filter(Boolean) : [];
    if (files.length === 0) return existing;
    let next = existing.slice();
    for (const file of files) {
        const fid = typeof file.file_id === 'string' ? file.file_id : '';
        const idx = fid
            ? next.findIndex((item) => item && item.file_id === fid)
            : next.findIndex((item) => item && item.url === file.url);
        if (idx >= 0) {
            next[idx] = { ...next[idx], ...file };
        } else {
            next.push(file);
        }
    }
    return next;
}

function _dispatchRuntimeEvents(ctx, mapped, causationId) {
    const meta = { causation_id: causationId, source: 'http' };
    for (const runEvent of mapped.runEvents) {
        ctx.dispatch(runEvent.type, runEvent.payload, meta);
    }
    for (const trace of mapped.traceEntries) {
        _appendRunTrace(ctx, trace.context_id, trace.task_id, trace.fields, causationId);
    }
    for (const event of mapped.events) {
        if (event.type === 'ui_event') {
            continue;
        }
        ctx.dispatch(`flows/chat/${event.type}`, event.payload, meta);
    }
}

/**
 * Редьюсер чата и авто-TTS из одного кадра A2A (HTTP `chat_send` и `relayA2aVoiceStreamRpcFrame`).
 */
function _dispatchA2aEventAndMaybeFeedStreamTts(ctx, contextId, currentTaskId, result, causationId, streamState) {
    const mapped = mapA2aResultToChatRuntimeEvents(result, {
        contextId,
        currentTaskId,
        taskPrimed: streamState && streamState.taskPrimed === true,
    });
    _dispatchRuntimeEvents(ctx, mapped, causationId);
    feedStreamTtsFromA2aResult(result);
    return mapped;
}

/**
 * Стримит SSE-ответ A2A: для каждого `data: <json>` парсит JSON-RPC и
 * прогоняет `result` через `_dispatchA2aEventAndMaybeFeedStreamTts` (редьюсер +
 * `feedStreamTtsFromA2aResult`). Возвращает
 * `{ task_id, context_id }` после первого терминального state или
 * исчерпания стрима.
 *
 * Первый фрейм с `taskId` и `contextId` (часто `artifact-update`, без
 * отдельного `kind: task`) диспатчит `flows/chat/task_started`, иначе
 * `streaming` в слайсе остаётся false и `reasoning_chunk` / `content_chunk`
 * не сопоставляются с корзиной.
 */
async function _consumeA2aStream(req, ctx, contextId, causationId) {
    let taskId = null;
    let terminal = false;
    let streamTaskPrimed = false;
    const meta = { causation_id: causationId, source: 'http' };
    ctx.dispatch('flows/run/flow_started', {}, meta);
    try {
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
            const mapped = _dispatchA2aEventAndMaybeFeedStreamTts(
                ctx,
                contextId,
                taskId,
                result,
                causationId,
                { taskPrimed: streamTaskPrimed },
            );
            streamTaskPrimed = mapped.taskPrimed;
            if (mapped.nextTaskId) taskId = mapped.nextTaskId;
            let stateValue = null;
            if (result.kind === 'status-update' && result.status && typeof result.status.state === 'string') {
                stateValue = result.status.state;
            } else if (result.kind === 'artifact-update' && result.artifact && typeof result.artifact.state === 'string') {
                stateValue = result.artifact.state;
            }
            if (mapped.terminal || _isTerminalState(stateValue, result.final === true)) {
                terminal = true;
            }
        });
    } finally {
        ctx.dispatch('flows/run/flow_done', {}, meta);
    }
    if (!terminal) {
        const effectiveCid =
            typeof contextId === 'string' && contextId.length > 0 ? contextId : null;
        if (typeof taskId === 'string' && taskId.length > 0) {
            ctx.dispatch(
                'flows/chat/failed',
                {
                    task_id: taskId,
                    context_id: effectiveCid,
                    error_i18n_key: STREAM_INCOMPLETE_I18N_KEY,
                },
                meta,
            );
        }
    }
    return { task_id: taskId, context_id: contextId };
}

/**
 * Прокидывает кадр SSE (JSON-RPC из `data:`) голосового `message/stream` в тот же reducer,
 * что и `flows/chat_send`, без второго HTTP-запроса; затем `feedStreamTtsFromA2aResult`.
 * Состояние стрима мутабельное между кадрами (`streamState`).
 *
 * @param {{ dispatch: Function }} ctx
 * @param {{ contextId: string|null, taskId: string|null, taskPrimed: boolean }} streamState
 * @param {object} rpcFrame
 * @param {string|null} causationId
 */
export function relayA2aVoiceStreamRpcFrame(ctx, streamState, rpcFrame, causationId) {
    if (!ctx || typeof ctx.dispatch !== 'function') {
        throw new Error('relayA2aVoiceStreamRpcFrame: ctx.dispatch required');
    }
    if (!streamState || typeof streamState !== 'object') {
        throw new Error('relayA2aVoiceStreamRpcFrame: streamState required');
    }
    if (!rpcFrame || typeof rpcFrame !== 'object') return;
    const metaBase =
        causationId != null && typeof causationId === 'string' && causationId.length > 0
            ? { causation_id: causationId, source: 'http' }
            : { source: 'http' };

    if (rpcFrame.error) {
        const err = rpcFrame.error;
        let errMsg = 'a2a stream error';
        if (err && typeof err === 'object') {
            if (typeof err.message === 'string' && err.message.length > 0) {
                errMsg = err.message;
            } else if (typeof err.code === 'string' && err.code.length > 0) {
                errMsg = err.code;
            }
        }
        const tid =
            typeof streamState.taskId === 'string' && streamState.taskId.length > 0
                ? streamState.taskId
                : null;
        const cid =
            typeof streamState.contextId === 'string' && streamState.contextId.length > 0
                ? streamState.contextId
                : null;
        if (tid) {
            ctx.dispatch(
                'flows/chat/failed',
                { task_id: tid, context_id: cid, error: errMsg },
                metaBase,
            );
        }
        return;
    }

    const result = rpcFrame.result;
    if (!result || typeof result !== 'object') return;

    const mapped = _dispatchA2aEventAndMaybeFeedStreamTts(
        ctx,
        streamState.contextId,
        streamState.taskId,
        result,
        causationId,
        streamState,
    );
    streamState.taskPrimed = mapped.taskPrimed;
    if (mapped.nextTaskId) {
        streamState.taskId = mapped.nextTaskId;
    }
    const resolvedCid = _resolveStreamContextId(result, streamState.contextId);
    if (typeof resolvedCid === 'string' && resolvedCid.length > 0) {
        streamState.contextId = resolvedCid;
    }
}

export const chatSendOp = createAsyncOp({
    name: 'flows/chat_send',
    transport: 'http',
    silent: true,
    // A2A JSON-RPC endpoint на flow (см. apps/flows/src/api/a2a.py — мапит
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
        stopStreamTtsPlayback();
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
    // Тот же A2A endpoint на flow: tasks/cancel JSON-RPC method.
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
    baseUrl: '/flows/api/v1/sessions/',
    idField: 'session_id',
    operations: ['list'],
    extraInitial: {
        messagesByContextId: EMPTY_OBJECT,
        filesByContextId: EMPTY_OBJECT,
        runTraceByContextId: EMPTY_OBJECT,
        currentContextId: null,
        currentFlowId: null,
        currentTaskId: null,
        streaming: false,
        sessionId: null,
        lastStreamPingAt: null,
        streamPingByContextId: EMPTY_OBJECT,
    },
    extraEvents: {
        SESSION_INIT: 'session_init',
        SESSION_RESET: 'session_reset',
        USER_MESSAGE_ADDED: 'user_message_added',
        FILES_UPDATED: 'files_updated',
        SESSION_LOADED: 'session_loaded',
        A2A_INTERRUPTED: 'a2a_interrupted',
    },
    actions: {
        initSession: 'session_init',
        resetSession: 'session_reset',
        addUserMessage: 'user_message_added',
        updateFiles: 'files_updated',
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
                runTraceByContextId: {
                    ...next.runTraceByContextId,
                    [contextId]: EMPTY_LIST,
                },
                filesByContextId: {
                    ..._filesByContextMap(next.filesByContextId),
                    [contextId]: EMPTY_LIST,
                },
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
                runTraceByContextId: {
                    ...state.runTraceByContextId,
                    [contextId]: EMPTY_LIST,
                },
                filesByContextId: {
                    ..._filesByContextMap(state.filesByContextId),
                    [contextId]: EMPTY_LIST,
                },
            };
        }

        if (type === 'flows/chat/session_loaded') {
            const p = event.payload;
            if (!p || typeof p !== 'object') return state;
            const sessionId = typeof p.sessionId === 'string' ? p.sessionId : null;
            const flowId = typeof p.flowId === 'string' ? p.flowId : state.currentFlowId;
            const messages = Array.isArray(p.messages) ? p.messages : [];
            const files = Array.isArray(p.files) ? _upsertFiles([], p.files) : [];
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
                runTraceByContextId: {
                    ...state.runTraceByContextId,
                    [contextId]: EMPTY_LIST,
                },
                filesByContextId: {
                    ..._filesByContextMap(state.filesByContextId),
                    [contextId]: files,
                },
            };
        }

        if (type === 'flows/chat/trace_append') {
            const p = event.payload;
            if (!p || typeof p !== 'object') return state;
            const contextId = typeof p.context_id === 'string' ? p.context_id : null;
            const entry = p.entry;
            if (!contextId || contextId.length === 0) return state;
            if (!entry || typeof entry !== 'object') return state;
            if (typeof entry.id !== 'string' || entry.id.length === 0) return state;
            if (typeof entry.kind !== 'string' || entry.kind.length === 0) return state;
            if (typeof entry.ts !== 'number') return state;
            const prev = state.runTraceByContextId[contextId];
            const list = Array.isArray(prev) ? prev : [];
            const nextList = Object.freeze([...list, Object.freeze({ ...entry })]);
            return {
                ...state,
                runTraceByContextId: {
                    ...state.runTraceByContextId,
                    [contextId]: nextList,
                },
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
            return {
                ..._pushMessage(ensured, contextId, message),
                filesByContextId: {
                    ..._filesByContextMap(ensured.filesByContextId),
                    [contextId]: _upsertFiles(ensured.filesByContextId?.[contextId], message.files),
                },
            };
        }

        if (type === 'flows/chat/files_updated') {
            const p = event.payload;
            if (!p || typeof p !== 'object') return state;
            const contextId = typeof p.contextId === 'string' && p.contextId.length > 0
                ? p.contextId
                : state.currentContextId;
            const files = Array.isArray(p.files) ? p.files : [];
            if (typeof contextId !== 'string' || contextId.length === 0 || files.length === 0) {
                return state;
            }
            return {
                ...state,
                filesByContextId: {
                    ..._filesByContextMap(state.filesByContextId),
                    [contextId]: _upsertFiles(state.filesByContextId?.[contextId], files),
                },
            };
        }

        if (type === 'flows/chat_send/succeeded') {
            const result = event.payload && typeof event.payload === 'object' ? event.payload.result : null;
            const p = result && typeof result === 'object' ? result : null;
            // request() ждёт полный SSE; к этому моменту terminal-события уже в bus — streaming: false.
            if (!p) {
                return { ...state, streaming: false };
            }
            const taskId = typeof p.task_id === 'string' ? p.task_id : null;
            const contextId = typeof p.context_id === 'string'
                ? p.context_id
                : state.currentContextId;
            const next = { ...state, streaming: false };
            if (!contextId) {
                return next;
            }
            if (!taskId) {
                return _sweepOrphanStreamingInContext(next, contextId);
            }
            const bucket = next.messagesByContextId[contextId];
            if (!bucket) {
                return _sweepOrphanStreamingInContext(next, contextId);
            }
            return _sweepOrphanStreamingInContext(
                {
                    ...next,
                    currentContextId: contextId,
                    currentTaskId: taskId,
                    messagesByContextId: {
                        ...next.messagesByContextId,
                        [contextId]: { ...bucket, taskId },
                    },
                },
                contextId,
            );
        }
        if (type === 'flows/chat_send/failed') {
            return { ...state, streaming: false };
        }

        if (type === 'flows/chat/a2a_interrupted') {
            const p = event.payload && typeof event.payload === 'object' ? event.payload : {};
            const interruptedTaskId = typeof p.task_id === 'string' ? p.task_id : null;
            let contextId = null;
            if (typeof p.context_id === 'string' && p.context_id.length > 0) {
                contextId = p.context_id;
            } else if (typeof state.currentContextId === 'string' && state.currentContextId.length > 0) {
                contextId = state.currentContextId;
            }
            let next = { ...state, streaming: false };
            if (
                interruptedTaskId
                && typeof state.currentTaskId === 'string'
                && state.currentTaskId === interruptedTaskId
            ) {
                next = { ...next, currentTaskId: null };
            }
            if (typeof contextId === 'string' && contextId.length > 0) {
                next = _sweepOrphanStreamingInContext(next, contextId);
            }
            return next;
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
            const tracePatch =
                typeof contextId === 'string' && contextId.length > 0
                    ? { ...next.runTraceByContextId, [contextId]: EMPTY_LIST }
                    : next.runTraceByContextId;
            let withTask = { ...next, currentTaskId: taskId, streaming: true, runTraceByContextId: tracePatch };
            if (typeof contextId === 'string' && contextId.length > 0) {
                withTask = _applyToBucketMessages(
                    withTask,
                    taskId,
                    (messages) => _ensurePlaceholderAssistant(messages, taskId),
                    contextId,
                );
            }
            return withTask;
        }

        if (type === 'flows/chat/stream_ping') {
            const p = event.payload;
            if (!p || typeof p !== 'object') return state;
            const taskId = typeof p.task_id === 'string' ? p.task_id : null;
            const contextId = typeof p.context_id === 'string' && p.context_id.length > 0
                ? p.context_id
                : state.currentContextId;
            const receivedAt = typeof p.received_at === 'number' ? p.received_at : Date.now();
            const sentAt = typeof p.sent_at === 'string' ? p.sent_at : '';
            const sequence = typeof p.sequence === 'number' ? p.sequence : null;
            if (typeof contextId !== 'string' || contextId.length === 0) {
                return {
                    ...state,
                    lastStreamPingAt: receivedAt,
                };
            }
            return {
                ...state,
                lastStreamPingAt: receivedAt,
                streamPingByContextId: {
                    ...state.streamPingByContextId,
                    [contextId]: {
                        taskId,
                        sentAt,
                        receivedAt,
                        sequence,
                    },
                },
            };
        }

        if (type === 'flows/chat/activity') {
            const p = event.payload;
            if (!p || typeof p !== 'object') return state;
            const taskId = typeof p.task_id === 'string' ? p.task_id : null;
            const text = typeof p.text === 'string' ? p.text : '';
            if (!taskId) return state;
            return _applyToBucketMessages(
                state,
                taskId,
                (messages) => {
                    const { messages: nextMsgs, idx } = _findOrCreateAssistantMessage(messages, taskId);
                    return _replaceMessage(nextMsgs, idx, (m) => ({ ...m, activity: text }));
                },
            );
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

        if (type === 'flows/chat/browser_preview_event') {
            const p = event.payload;
            if (!p || typeof p !== 'object') return state;
            const taskId = typeof p.task_id === 'string' ? p.task_id : null;
            const contextId = typeof p.context_id === 'string' ? p.context_id : null;
            const browserEvent = p.event;
            if (!taskId || !browserEvent || typeof browserEvent !== 'object') return state;
            return _applyToBucketMessages(
                state,
                taskId,
                (messages) => {
                    const { messages: nextMsgs, idx } = _findOrCreateAssistantMessage(messages, taskId);
                    return _replaceMessage(nextMsgs, idx, (m) => ({
                        ...m,
                        browserPreviews: _upsertBrowserPreview(m.browserPreviews, browserEvent),
                    }));
                },
                contextId,
            );
        }

        if (type === 'flows/chat/files_event') {
            const p = event.payload;
            if (!p || typeof p !== 'object') return state;
            const taskId = typeof p.task_id === 'string' ? p.task_id : null;
            const contextId = typeof p.context_id === 'string' ? p.context_id : null;
            const filesEvent = p.event;
            if (!taskId || !filesEvent || typeof filesEvent !== 'object') return state;
            const payload = filesEvent.payload && typeof filesEvent.payload === 'object' ? filesEvent.payload : {};
            const files = Array.isArray(payload.files) ? payload.files : [];
            if (files.length === 0) return state;
            const withMessage = _applyToBucketMessages(
                state,
                taskId,
                (messages) => {
                    const { messages: nextMsgs, idx } = _findOrCreateAssistantMessage(messages, taskId);
                    return _replaceMessage(nextMsgs, idx, (m) => ({
                        ...m,
                        files: _upsertFiles(m.files, files),
                    }));
                },
                contextId,
            );
            const cid = contextId || state.currentContextId;
            if (typeof cid !== 'string' || cid.length === 0) {
                return withMessage;
            }
            return {
                ...withMessage,
                filesByContextId: {
                    ..._filesByContextMap(withMessage.filesByContextId),
                    [cid]: _upsertFiles(withMessage.filesByContextId?.[cid], files),
                },
            };
        }

        if (type === 'flows/chat/breakpoint') {
            const p = event.payload;
            if (!p || typeof p !== 'object') return state;
            const taskId = typeof p.task_id === 'string' ? p.task_id : null;
            const breakpoint = p.breakpoint;
            const ctxHint = typeof p.context_id === 'string' ? p.context_id : null;
            if (!taskId || !breakpoint) return state;
            const next = _applyToBucketMessages(
                state,
                taskId,
                _setMessageFields(taskId, {
                    breakpoint,
                    streaming: false,
                    activity: '',
                    error: '',
                    errorI18nKey: null,
                }),
                ctxHint,
            );
            return { ...next, streaming: false };
        }

        if (type === 'flows/chat/input_required') {
            const p = event.payload;
            if (!p || typeof p !== 'object') return state;
            const taskId = typeof p.task_id === 'string' ? p.task_id : null;
            if (!taskId) return state;
            const ctxHint = typeof p.context_id === 'string' ? p.context_id : null;
            const msg = p.message && typeof p.message === 'object' ? p.message : null;
            const rmeta = p.result_metadata && typeof p.result_metadata === 'object' ? p.result_metadata : {};
            const mmeta = p.message_metadata && typeof p.message_metadata === 'object' ? p.message_metadata : {};
            const extracted = _inputRequiredFieldsFromPayload(msg, rmeta);
            const inputRequired = {
                question: extracted.question,
                interruptKind: extracted.interruptKind,
                resultMetadata: rmeta,
                messageMetadata: mmeta,
                message: msg,
            };
            if (extracted.authUrl.length > 0) {
                inputRequired.authUrl = extracted.authUrl;
            }
            const next = _applyToBucketMessages(
                state,
                taskId,
                _setMessageFields(taskId, {
                    inputRequired,
                    streaming: false,
                    activity: '',
                    error: '',
                    errorI18nKey: null,
                }),
                ctxHint,
            );
            return { ...next, streaming: false };
        }

        if (type === 'flows/chat/completed') {
            const p = event.payload;
            if (!p || typeof p !== 'object') return state;
            const taskId = typeof p.task_id === 'string' ? p.task_id : null;
            const content = typeof p.content === 'string' ? p.content : '';
            const ctxHint = typeof p.context_id === 'string' ? p.context_id : null;
            if (!taskId) return state;
            const next = _applyToBucketMessages(
                state,
                taskId,
                (messages) => {
                    const { messages: nextMsgs, idx } = _findOrCreateAssistantMessage(messages, taskId);
                    return _replaceMessage(nextMsgs, idx, (m) => {
                        const updated = {
                            ...m,
                            streaming: false,
                            inputRequired: null,
                            activity: '',
                            error: '',
                            errorI18nKey: null,
                        };
                        if (content && (!m.content || m.content.trim() === '')) {
                            updated.content = content;
                        }
                        return updated;
                    });
                },
                ctxHint,
            );
            return { ...next, streaming: false, currentTaskId: taskId };
        }

        if (type === 'flows/chat/failed') {
            const p = event.payload;
            if (!p || typeof p !== 'object') return state;
            const taskId = typeof p.task_id === 'string' ? p.task_id : null;
            const hasI18n = typeof p.error_i18n_key === 'string' && p.error_i18n_key.length > 0;
            const errFromPayload = typeof p.error === 'string' ? p.error : null;
            const errorText = hasI18n ? '' : (errFromPayload !== null ? errFromPayload : 'error');
            const ctxHint = typeof p.context_id === 'string' ? p.context_id : null;
            if (!taskId) return { ...state, streaming: false };
            const i18nKey = hasI18n ? p.error_i18n_key : null;
            const next = _applyToBucketMessages(
                state,
                taskId,
                (messages) => {
                    const { messages: nextMsgs, idx } = _findOrCreateAssistantMessage(messages, taskId);
                    return _replaceMessage(nextMsgs, idx, (m) => {
                        const base = { ...m, streaming: false, inputRequired: null, activity: '' };
                        if (i18nKey !== null) {
                            return { ...base, error: '', errorI18nKey: i18nKey };
                        }
                        return { ...base, error: errorText, errorI18nKey: null };
                    });
                },
                ctxHint,
            );
            return { ...next, streaming: false };
        }

        return state;
    },
});
