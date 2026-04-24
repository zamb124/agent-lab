/**
 * Восстанавливает сообщения слайса flows/chat из A2A ExecutionState.messages
 * (ответ GET /flows/api/v1/tasks/state) в ту же форму, что наполняется live-SSE.
 *
 * Reasoning: в messages обычно нет — reasoning из live идёт только потоком chunks в UI.
 * Если в metadata конкретного сообщения есть стабильное поле, оно переносится.
 */

import { isPlainObject } from './flows-resolvers.js';

/**
 * @param {unknown} rawMessages
 * @param {string | null} defaultTaskId
 * @returns {object[]}
 */
export function a2aStateMessagesToChatMessages(rawMessages, defaultTaskId) {
    if (!Array.isArray(rawMessages)) {
        throw new Error('a2aStateMessagesToChatMessages: array required');
    }
    const defTask =
        typeof defaultTaskId === 'string' && defaultTaskId.length > 0
            ? defaultTaskId
            : null;
    const out = [];
    /** @type {null | { content: string, toolCalls: object[], toolResults: object[], taskId: string, timestamp: string, id: string, reasoning: string, activity: string, mergeOpen: boolean }} */
    let buf = null;
    let idx = 0;

    const flushBuf = () => {
        if (!buf) {
            return;
        }
        out.push(_assistantRow(buf));
        buf = null;
    };

    for (const msg of rawMessages) {
        if (!isPlainObject(msg)) {
            throw new Error('a2aStateMessagesToChatMessages: message must be object');
        }
        const role = _parseRole(msg);
        const text = _partsText(msg);
        const meta = isPlainObject(msg.metadata) ? msg.metadata : {};
        const messageId = _messageId(msg, idx);
        const timestamp = _timestamp(msg);
        const taskId = _taskId(msg, defTask);
        const toolCalls = meta.tool_calls;
        const hasToolCalls = Array.isArray(toolCalls) && toolCalls.length > 0;
        const toolCallId = typeof meta.tool_call_id === 'string' ? meta.tool_call_id : '';
        const isSystem = meta.system === true;

        if (role === 'user') {
            flushBuf();
            out.push({
                id: messageId,
                role: 'user',
                content: text,
                timestamp,
                taskId,
                streaming: false,
            });
            idx += 1;
            continue;
        }

        if (isSystem) {
            flushBuf();
            out.push({
                id: messageId,
                role: 'system',
                content: text,
                timestamp,
                taskId,
                streaming: false,
            });
            idx += 1;
            continue;
        }

        if (role !== 'agent' && role !== 'assistant') {
            flushBuf();
            out.push({
                id: messageId,
                role: 'assistant',
                content: text,
                timestamp,
                taskId,
                streaming: false,
            });
            idx += 1;
            continue;
        }

        if (hasToolCalls) {
            flushBuf();
            const normalized = toolCalls.map((tc) => _normalizeToolCallForUi(tc));
            const reasoning = _reasoningFromMeta(meta);
            buf = {
                id: `assistant_${taskId || 't'}_${messageId}`,
                content: text,
                toolCalls: normalized,
                toolResults: [],
                taskId: taskId || defTask || '',
                timestamp,
                reasoning,
                activity: '',
                mergeOpen: true,
            };
            idx += 1;
            continue;
        }

        if (toolCallId.length > 0) {
            const resUi = {
                id: toolCallId,
                name: _resolveToolNameFromCalls(buf, toolCallId, ''),
                result: text,
            };
            if (buf && buf.toolCalls.length > 0) {
                buf.toolResults.push(resUi);
            } else {
                flushBuf();
                out.push(
                    _assistantRow({
                        id: `orphan_tr_${messageId}`,
                        content: '',
                        toolCalls: [],
                        toolResults: [resUi],
                        taskId: taskId || defTask || '',
                        timestamp,
                        reasoning: '',
                        activity: '',
                        mergeOpen: false,
                    }),
                );
            }
            idx += 1;
            continue;
        }

        if (buf && buf.mergeOpen) {
            buf.content = _joinContent(buf.content, text);
            flushBuf();
            buf = null;
        } else {
            flushBuf();
            out.push({
                id: messageId,
                role: 'assistant',
                content: text,
                timestamp,
                taskId,
                streaming: false,
                reasoning: _reasoningFromMeta(meta),
                activity: '',
                toolCalls: [],
                toolResults: [],
            });
        }
        idx += 1;
    }
    flushBuf();
    return out;
}

/**
 * @param {object} buf
 * @returns {object}
 */
function _assistantRow(buf) {
    return {
        id: buf.id,
        role: 'assistant',
        content: buf.content,
        timestamp: buf.timestamp,
        taskId: buf.taskId,
        streaming: false,
        reasoning: buf.reasoning,
        activity: buf.activity,
        toolCalls: buf.toolCalls,
        toolResults: buf.toolResults,
    };
}

/**
 * @param {object | null} buf
 * @param {string} toolCallId
 * @param {string} emptyName
 */
function _resolveToolNameFromCalls(buf, toolCallId, emptyName) {
    if (!buf || !Array.isArray(buf.toolCalls)) {
        return emptyName;
    }
    for (const tc of buf.toolCalls) {
        if (isPlainObject(tc) && tc.id === toolCallId) {
            if (typeof tc.name === 'string' && tc.name.length > 0) {
                return tc.name;
            }
        }
    }
    return emptyName;
}

/**
 * @param {string} a
 * @param {string} b
 */
function _joinContent(a, b) {
    const t1 = typeof a === 'string' ? a : '';
    const t2 = typeof b === 'string' ? b : '';
    if (t1.length === 0) {
        return t2;
    }
    if (t2.length === 0) {
        return t1;
    }
    return `${t1}\n\n${t2}`;
}

/**
 * @param {object} meta
 */
function _reasoningFromMeta(meta) {
    if (typeof meta.reasoning === 'string') {
        return meta.reasoning;
    }
    return '';
}

/**
 * @param {object} msg
 * @param {number} i
 */
function _messageId(msg, i) {
    if (typeof msg.messageId === 'string' && msg.messageId.length > 0) {
        return msg.messageId;
    }
    if (typeof msg.id === 'string' && msg.id.length > 0) {
        return msg.id;
    }
    return `msg-${i}`;
}

/**
 * @param {object} msg
 */
function _timestamp(msg) {
    if (typeof msg.timestamp === 'string' && msg.timestamp.length > 0) {
        return msg.timestamp;
    }
    return new Date().toISOString();
}

/**
 * @param {object} msg
 * @param {string | null} def
 */
function _taskId(msg, def) {
    if (typeof msg.taskId === 'string' && msg.taskId.length > 0) {
        return msg.taskId;
    }
    if (def !== null) {
        return def;
    }
    return '';
}

/**
 * @param {object} msg
 */
function _parseRole(msg) {
    const r = msg.role;
    if (typeof r === 'string') {
        return r.toLowerCase();
    }
    if (isPlainObject(r) && typeof r.value === 'string') {
        return r.value.toLowerCase();
    }
    return 'agent';
}

/**
 * @param {object} msg
 */
function _partsText(msg) {
    if (typeof msg.content === 'string' && msg.content.length > 0) {
        return msg.content;
    }
    if (!Array.isArray(msg.parts)) {
        return '';
    }
    const chunks = [];
    for (const p of msg.parts) {
        if (!isPlainObject(p)) {
            continue;
        }
        if (p.kind === 'text' && typeof p.text === 'string') {
            chunks.push(p.text);
        }
    }
    return chunks.join('');
}

/**
 * @param {object} tc
 * @returns {{ id: string, name: string, args: object }}
 */
function _normalizeToolCallForUi(tc) {
    if (!isPlainObject(tc)) {
        throw new Error('normalizeToolCall: object required');
    }
    if (isPlainObject(tc.function)) {
        const fn = tc.function;
        const name = typeof fn.name === 'string' ? fn.name : '';
        const idRaw = typeof tc.id === 'string' ? tc.id : name;
        const id = idRaw.length > 0 ? idRaw : name;
        if (id.length === 0) {
            throw new Error('normalizeToolCall: id required');
        }
        const args = _coerceToolArguments(fn.arguments);
        return { id, name, args };
    }
    const name = typeof tc.name === 'string' ? tc.name : '';
    const id = typeof tc.id === 'string' && tc.id.length > 0 ? tc.id : name;
    if (id.length === 0) {
        throw new Error('normalizeToolCall: id or name required');
    }
    const args = _coerceToolArguments(tc.arguments);
    return { id, name, args };
}

/**
 * @param {unknown} raw
 * @returns {object}
 */
function _coerceToolArguments(raw) {
    if (raw === null || raw === undefined) {
        return {};
    }
    if (isPlainObject(raw)) {
        return raw;
    }
    if (typeof raw === 'string') {
        if (raw.length === 0) {
            return {};
        }
        return JSON.parse(raw);
    }
    throw new Error('normalizeToolCall: arguments must be object or JSON string');
}
