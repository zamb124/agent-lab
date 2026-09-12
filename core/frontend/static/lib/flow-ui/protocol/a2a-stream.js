/**
 * A2A JSON-RPC and SSE transport for Flow UI plus frame helpers.
 * AbortSignal cancellation is fail-closed for callers, but must not leave
 * uncaught BodyStreamBuffer AbortError when dispose() cancels mid-read.
 */
import { a2aRequestHeaders } from './a2a-codec.js';
import { INTERRUPTED_TASK_STATES, TERMINAL_TASK_STATES } from './constants.js';

/**
 * ``result`` кадра SendStreamingMessage/SubscribeToTask → ``{frameKind, event}``.
 * Кадры: ``statusUpdate``, ``artifactUpdate``, ``task`` (snapshot), ``message``.
 */
export function unwrapA2aStreamResult(result) {
    if (!result || typeof result !== 'object') return null;
    for (const frameKind of ['statusUpdate', 'artifactUpdate', 'task', 'message']) {
        const event = result[frameKind];
        if (event && typeof event === 'object') return { frameKind, event };
    }
    if (typeof result.id === 'string' && result.status && typeof result.status === 'object') {
        return { frameKind: 'task', event: result };
    }
    return null;
}

export function resolveA2aTaskId(result, current = null) {
    const unwrapped = unwrapA2aStreamResult(result);
    if (!unwrapped) return current;
    const { frameKind, event } = unwrapped;
    const taskId = frameKind === 'task' ? event.id : event.taskId;
    return typeof taskId === 'string' && taskId !== '' ? taskId : current;
}

export function resolveA2aContextId(result, current = null) {
    const unwrapped = unwrapA2aStreamResult(result);
    if (!unwrapped) return current;
    const contextId = unwrapped.event.contextId;
    return typeof contextId === 'string' && contextId !== '' ? contextId : current;
}

export function isTerminalTaskState(state) {
    return TERMINAL_TASK_STATES.has(state);
}

export function isInterruptedTaskState(state) {
    return INTERRUPTED_TASK_STATES.has(state);
}

/** Task больше не стримит: завершён или ждёт ввода/авторизации. */
export function isSettledTaskState(state) {
    return isTerminalTaskState(state) || isInterruptedTaskState(state);
}

/**
 * @param {unknown} error
 * @returns {error is Error}
 */
export function flowUIIsAbortError(error) {
    if (error == null || typeof error !== 'object') return false;
    const name = /** @type {{ name?: unknown }} */ (error).name;
    return name === 'AbortError';
}

async function responseError(response) {
    let payload = null;
    try { payload = await response.json(); } catch { payload = null; }
    const detail = payload?.detail || payload?.error?.message || `HTTP ${response.status}`;
    const error = new Error(String(detail));
    error.status = response.status;
    error.payload = payload;
    return error;
}

/**
 * @param {AbortSignal | null | undefined} signal
 * @param {unknown} error
 */
function rethrowUnlessAbort(signal, error) {
    if (flowUIIsAbortError(error) || signal?.aborted === true) {
        if (flowUIIsAbortError(error)) throw error;
        throw new DOMException('Aborted', 'AbortError');
    }
    throw error;
}

export async function sendA2ARequest({ url, body, headers = {}, credentials = 'include', signal }) {
    const response = await fetch(url, {
        method: 'POST',
        headers: a2aRequestHeaders(headers),
        credentials,
        body: JSON.stringify(body),
        signal,
    });
    if (!response.ok) throw await responseError(response);
    let frame;
    try {
        frame = await response.json();
    } catch (error) {
        rethrowUnlessAbort(signal, error);
    }
    if (frame?.error) {
        const error = new Error(frame.error.message || 'A2A request failed');
        error.code = frame.error.code;
        error.payload = frame.error;
        throw error;
    }
    return frame;
}

export async function consumeA2AStream(
    { url, body, headers = {}, credentials = 'include', signal },
    onFrame,
) {
    if (typeof onFrame !== 'function') throw new Error('flow-ui: onFrame is required');
    const response = await fetch(url, {
        method: 'POST',
        headers: a2aRequestHeaders(headers, { stream: true }),
        credentials,
        body: JSON.stringify(body),
        signal,
    });
    if (!response.ok) throw await responseError(response);
    if (!(response.headers.get('content-type') || '').toLowerCase().includes('text/event-stream')) {
        throw new Error('flow-ui: expected A2A text/event-stream response');
    }
    if (!response.body) {
        throw new Error('flow-ui: A2A stream response body is missing');
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    try {
        while (true) {
            let chunk;
            try {
                chunk = await reader.read();
            } catch (error) {
                rethrowUnlessAbort(signal, error);
            }
            const { done, value } = chunk;
            buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
            const records = buffer.split(/\r?\n\r?\n/);
            buffer = records.pop() || '';
            for (const record of records) {
                for (const line of record.split(/\r?\n/)) {
                    if (!line.startsWith('data:')) continue;
                    const data = line.slice(5).trimStart();
                    if (data && data !== '[DONE]') onFrame(JSON.parse(data));
                }
            }
            if (done) break;
        }
    } finally {
        try {
            await reader.cancel();
        } catch {
            // Body already aborted by AbortSignal — ignore.
        }
    }
}
