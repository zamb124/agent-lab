/**
 * Pure reducer единого чат-компонента платформы.
 *
 * Состояние чата (messages/files/run-trace по contextId) меняется ТОЛЬКО здесь:
 * `<platform-chat>` применяет reducer через ChatController во всех режимах
 * (SPA, editor test, embed). Без DOM, без EventBus, без fetch, без импортов app.
 */

import { inputRequiredFieldsFromA2a } from '../a2a-chat-runtime.js';

const EMPTY_LIST = Object.freeze([]);
const EMPTY_OBJECT = Object.freeze({});

/** Ключ i18n `flows.chat_message.*` при обрыве SSE без терминального status-update. */
export const STREAM_INCOMPLETE_I18N_KEY = 'stream_incomplete';

let _traceSeq = 0;

/** Trace-запись run trace: id/ts генерируются здесь, append — событием `trace_append`. */
export function buildRunTraceEntry(taskId, fields) {
    if (!fields || typeof fields !== 'object') {
        throw new Error('chat-state: trace fields required');
    }
    const kind = fields.kind;
    if (typeof kind !== 'string' || kind.length === 0) {
        throw new Error('chat-state: trace kind required');
    }
    _traceSeq += 1;
    const entry = {
        id: `tr_${_traceSeq}`,
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
    return Object.freeze(entry);
}

/** Начальное состояние chat runtime (ChatController). */
export function createInitialChatRuntimeState() {
    return {
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
    };
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
 *   Пока стрим не закончен, `send_succeeded` ещё не записал taskId в bucket;
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

function _stampTerminalTimestamp(message, patch) {
    const next = { ...message, ...patch };
    if (patch.streaming !== false) {
        return next;
    }
    const existing = typeof message.timestamp === 'string' ? message.timestamp : '';
    if (existing.length === 0) {
        next.timestamp = new Date().toISOString();
    }
    return next;
}

function _setMessageFields(taskId, fields) {
    return (messages) => {
        const { messages: nextMsgs, idx } = _findOrCreateAssistantMessage(messages, taskId);
        return _replaceMessage(nextMsgs, idx, (m) => _stampTerminalTimestamp(m, fields));
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

function _sessionInit(state, p) {
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

function _sessionReset(state) {
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

function _sessionLoaded(state, p) {
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

function _traceAppend(state, p) {
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

function _userMessageAdded(state, p) {
    if (!p || typeof p !== 'object') return state;
    const contextId = typeof p.contextId === 'string' ? p.contextId : state.currentContextId;
    if (!contextId) return state;
    const message = p.message;
    if (!message || typeof message !== 'object') return state;
    const ensured = _ensureContextBucket(state, contextId);
    const bucket = ensured.messagesByContextId && ensured.messagesByContextId[contextId];
    const existing = bucket && Array.isArray(bucket.messages) ? bucket.messages : [];
    const last = existing.length > 0 ? existing[existing.length - 1] : null;
    const newContent = typeof message.content === 'string' ? message.content : '';
    if (
        last
        && last.role === 'user'
        && typeof last.content === 'string'
        && last.content === newContent
        && newContent !== ''
    ) {
        return state;
    }
    return {
        ..._pushMessage(ensured, contextId, message),
        filesByContextId: {
            ..._filesByContextMap(ensured.filesByContextId),
            [contextId]: _upsertFiles(ensured.filesByContextId?.[contextId], message.files),
        },
    };
}

function _filesUpdated(state, p) {
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

function _sendSucceeded(state, result) {
    const p = result && typeof result === 'object' ? result : null;
    // Отправитель ждёт полный SSE; к этому моменту terminal-события уже применены — streaming: false.
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

function _a2aInterrupted(state, payload) {
    const p = payload && typeof payload === 'object' ? payload : {};
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

function _taskStarted(state, p) {
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

function _streamPing(state, p) {
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

function _activity(state, p) {
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

function _chunk(state, p, field) {
    if (!p || typeof p !== 'object') return state;
    const taskId = typeof p.task_id === 'string' ? p.task_id : null;
    const text = typeof p.text === 'string' ? p.text : '';
    if (!taskId) return state;
    return _applyToBucketMessages(state, taskId, _appendChunk(field, text));
}

function _operatorReply(state, p) {
    if (!p || typeof p !== 'object') return state;
    const taskId = typeof p.task_id === 'string' ? p.task_id : null;
    const text = typeof p.text === 'string' ? p.text : '';
    if (!taskId || !text) return state;
    return _applyToBucketMessages(state, taskId, (messages) => {
        const last = messages.length > 0 ? messages[messages.length - 1] : null;
        if (
            last
            && last.role === 'operator'
            && typeof last.content === 'string'
            && last.content === text
        ) {
            return messages;
        }
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

function _operatorFiles(state, p) {
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

function _toolCalls(state, p) {
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

function _toolResult(state, p) {
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

function _browserPreviewEvent(state, p) {
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

function _filesEvent(state, p) {
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

function _breakpoint(state, p) {
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

function _inputRequired(state, p) {
    if (!p || typeof p !== 'object') return state;
    const taskId = typeof p.task_id === 'string' ? p.task_id : null;
    if (!taskId) return state;
    const ctxHint = typeof p.context_id === 'string' ? p.context_id : null;
    const msg = p.message && typeof p.message === 'object' ? p.message : null;
    const rmeta = p.result_metadata && typeof p.result_metadata === 'object' ? p.result_metadata : {};
    const mmeta = p.message_metadata && typeof p.message_metadata === 'object' ? p.message_metadata : {};
    const extracted = inputRequiredFieldsFromA2a(msg, rmeta);
    const inputRequired = {
        question: extracted.question,
        interruptKind: extracted.interruptKind,
        resultMetadata: rmeta,
        messageMetadata: mmeta,
        message: msg,
    };
    if (typeof extracted.workItemId === 'string' && extracted.workItemId.length > 0) {
        inputRequired.workItemId = extracted.workItemId;
    }
    if (typeof extracted.operatorTaskTitle === 'string' && extracted.operatorTaskTitle.length > 0) {
        inputRequired.operatorTaskTitle = extracted.operatorTaskTitle;
    }
    if (typeof extracted.handoffMode === 'string' && extracted.handoffMode.length > 0) {
        inputRequired.handoffMode = extracted.handoffMode;
    }
    if (typeof extracted.operatorAssigneeQueue === 'string' && extracted.operatorAssigneeQueue.length > 0) {
        inputRequired.operatorAssigneeQueue = extracted.operatorAssigneeQueue;
    }
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

function _completed(state, p) {
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
                const updated = _stampTerminalTimestamp(m, {
                    streaming: false,
                    inputRequired: null,
                    activity: '',
                    error: '',
                    errorI18nKey: null,
                });
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

function _failed(state, p) {
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
                const base = _stampTerminalTimestamp(m, {
                    streaming: false,
                    inputRequired: null,
                    activity: '',
                });
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

function _handoffInitiated(state, p) {
    if (!p || typeof p !== 'object') return state;
    const taskId = typeof p.task_id === 'string' ? p.task_id : null;
    if (!taskId) return state;
    const ctxHint = typeof p.context_id === 'string' ? p.context_id : null;
    const handoff = {
        status: 'active',
        targetFlowId: typeof p.target_flow_id === 'string' ? p.target_flow_id : '',
        targetFlowName: typeof p.target_flow_name === 'string'
            ? p.target_flow_name
            : (typeof p.target_flow_id === 'string' ? p.target_flow_id : ''),
        depth: typeof p.depth === 'number' ? p.depth : 0,
        reason: typeof p.handoff_reason === 'string' ? p.handoff_reason : '',
        traceId: typeof p.trace_id === 'string' ? p.trace_id : '',
    };
    return _pushMessage(
        _applyToBucketMessages(state, taskId,
            _setMessageFields(taskId, { handoff, streaming: false, activity: '' }),
            ctxHint
        ),
        state.currentContextId,
        { id: `handoff_${taskId}_${handoff.targetFlowId}`, role: 'handoff', ...handoff },
    );
}

function _handbackCompleted(state, p) {
    if (!p || typeof p !== 'object') return state;
    const taskId = typeof p.task_id === 'string' ? p.task_id : null;
    if (!taskId) return state;
    const ctxHint = typeof p.context_id === 'string' ? p.context_id : null;
    const handback = {
        id: `handback_${taskId}`,
        role: 'handback',
        childFlowName: typeof p.child_flow_name === 'string' ? p.child_flow_name : '',
        parentFlowName: typeof p.parent_flow_name === 'string' ? p.parent_flow_name : '',
        response: typeof p.response === 'string' ? p.response : '',
        depth: typeof p.handoff_depth === 'number' ? p.handoff_depth : 0,
        traceId: typeof p.trace_id === 'string' ? p.trace_id : '',
    };
    const next = _applyToBucketMessages(state, taskId, (messages) => {
        const updated = messages.map((message) => {
            if (message.role !== 'assistant' || !message.handoff) {
                return message;
            }
            return {
                ...message,
                handoff: { ...message.handoff, status: 'returned' },
            };
        });
        return [...updated, handback];
    }, ctxHint);
    return { ...next, streaming: false };
}

/**
 * Применить одно chat-runtime событие к состоянию.
 *
 * @param {object} state — chat runtime state (см. createInitialChatRuntimeState)
 * @param {string} verb — короткий verb события без префикса (`task_started`, `content_chunk`, ...)
 * @param {unknown} payload
 * @returns {object} новое состояние (или прежний объект, если событие не про chat)
 */
export function applyChatRuntimeEvent(state, verb, payload) {
    switch (verb) {
        case 'session_init':
            return _sessionInit(state, payload);
        case 'session_reset':
            return _sessionReset(state);
        case 'session_loaded':
            return _sessionLoaded(state, payload);
        case 'trace_append':
            return _traceAppend(state, payload);
        case 'user_message_added':
            return _userMessageAdded(state, payload);
        case 'files_updated':
            return _filesUpdated(state, payload);
        case 'send_succeeded':
            return _sendSucceeded(state, payload);
        case 'send_failed':
            return { ...state, streaming: false };
        case 'a2a_interrupted':
            return _a2aInterrupted(state, payload);
        case 'task_started':
            return _taskStarted(state, payload);
        case 'stream_ping':
            return _streamPing(state, payload);
        case 'activity':
            return _activity(state, payload);
        case 'content_chunk':
            return _chunk(state, payload, 'content');
        case 'reasoning_chunk':
            return _chunk(state, payload, 'reasoning');
        case 'operator_reply':
            return _operatorReply(state, payload);
        case 'operator_files':
            return _operatorFiles(state, payload);
        case 'tool_calls':
            return _toolCalls(state, payload);
        case 'tool_result':
            return _toolResult(state, payload);
        case 'browser_preview_event':
            return _browserPreviewEvent(state, payload);
        case 'files_event':
            return _filesEvent(state, payload);
        case 'breakpoint':
            return _breakpoint(state, payload);
        case 'input_required':
            return _inputRequired(state, payload);
        case 'completed':
            return _completed(state, payload);
        case 'failed':
            return _failed(state, payload);
        case 'handoff_initiated':
            return _handoffInitiated(state, payload);
        case 'handback_completed':
            return _handbackCompleted(state, payload);
        default:
            return state;
    }
}
