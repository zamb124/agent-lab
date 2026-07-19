/**
 * flows/api_console_run — прогон A2A JSON-RPC запроса из консоли API редактора.
 *
 * Единственная фабрика A2A вне `<platform-chat>`: сам чат (send/cancel/reducer)
 * живёт в едином chat runtime `@platform/lib/chat/runtime/*` внутри компонента.
 * Консоль шлёт произвольный JSON-RPC body (`SendStreamingMessage` | `SendMessage` |
 * async submit + `GetTask` polling) и собирает полный request/response
 * exchange для отображения разработчику.
 *
 * Источник правды для бекенда — `_handle_streaming` в `apps/flows/src/api/a2a.py`.
 */

import { createAsyncOp, HttpError, httpRequest } from '@platform/lib/events/index.js';
import {
    extractA2aTextFromParts as _extractA2aTextFromParts,
    isA2aStreamBoundaryState as _isStreamBoundaryState,
    resolveA2aContextId as _resolveStreamContextId,
    resolveA2aTaskId as _resolveStreamTaskId,
    unwrapA2aStreamResult as _unwrapA2aStreamResult,
} from '@platform/lib/chat/a2a-chat-runtime.js';
import { consumeA2aStream } from '@platform/lib/chat/runtime/a2a-stream.js';

const EMPTY_LIST = Object.freeze([]);
const EMPTY_OBJECT = Object.freeze({});

function _dataPartText(part) {
    if (!part || typeof part !== 'object') {
        return '';
    }
    const data = part.data;
    if (!data || typeof data !== 'object') {
        return '';
    }
    const res = data.res;
    if (typeof res === 'string') {
        return res;
    }
    return '';
}

function _partsDataText(parts) {
    if (!Array.isArray(parts)) {
        return '';
    }
    return parts.map(_dataPartText).filter((text) => text.length > 0).join('');
}

function _appendConsoleResultText(target, text) {
    if (typeof text !== 'string' || text.length === 0) {
        return;
    }
    target.push(text);
}

function _collectConsoleFrame(frame, stream) {
    if (!frame || typeof frame !== 'object') {
        return;
    }
    if (frame.error) {
        throw _jsonRpcResponseError(frame);
    }
    stream.frames.push(frame);
    const result = frame.result;
    if (!result || typeof result !== 'object') {
        return;
    }

    const nextTaskId = _resolveStreamTaskId(result, stream.taskId);
    if (typeof nextTaskId === 'string' && nextTaskId.length > 0) {
        stream.taskId = nextTaskId;
    }
    const nextContextId = _resolveStreamContextId(result, stream.contextId);
    if (typeof nextContextId === 'string' && nextContextId.length > 0) {
        stream.contextId = nextContextId;
    }

    const unwrapped = _unwrapA2aStreamResult(result);
    if (!unwrapped) {
        return;
    }

    if (unwrapped.frameKind === 'artifactUpdate') {
        const artifact = unwrapped.event.artifact;
        if (artifact && typeof artifact === 'object') {
            const text = _extractA2aTextFromParts(artifact.parts);
            const dataText = _partsDataText(artifact.parts);
            const artifactName = typeof artifact.name === 'string' ? artifact.name : 'response';
            if (artifactName === 'reasoning') {
                _appendConsoleResultText(stream.reasoningChunks, text);
            } else {
                _appendConsoleResultText(stream.responseChunks, text);
                _appendConsoleResultText(stream.responseChunks, dataText);
            }
        }
    }

    if (unwrapped.frameKind === 'message') {
        _appendConsoleResultText(stream.responseChunks, _extractA2aTextFromParts(unwrapped.event.parts));
    }

    if (unwrapped.frameKind === 'statusUpdate' && unwrapped.event.status && typeof unwrapped.event.status === 'object') {
        const status = unwrapped.event.status;
        if (typeof status.state === 'string') {
            stream.terminalState = status.state;
        }
        if (stream.responseChunks.length === 0 && status.message && typeof status.message === 'object') {
            _appendConsoleResultText(
                stream.responseChunks,
                _extractA2aTextFromParts(status.message.parts),
            );
        }
        if (_isStreamBoundaryState(stream.terminalState)) {
            stream.terminal = true;
        }
    }
}

function _isConsoleObject(value) {
    return value && typeof value === 'object' && !Array.isArray(value);
}

function _jsonRpcResponseError(frame) {
    const err = _isConsoleObject(frame) ? frame.error : null;
    let errMsg = 'a2a response error';
    if (_isConsoleObject(err)) {
        if (typeof err.message === 'string' && err.message.length > 0) {
            errMsg = err.message;
        } else if (typeof err.code === 'string' && err.code.length > 0) {
            errMsg = err.code;
        }
    }
    return new HttpError(errMsg, 0, err);
}

function _consoleModeFromPayload(payload, body) {
    if (typeof payload.mode === 'string' && payload.mode.length > 0) {
        const mode = payload.mode.trim().toLowerCase();
        if (mode === 'stream' || mode === 'sync' || mode === 'async') {
            return mode;
        }
        throw new Error('flows/api_console_run: mode must be stream, sync or async');
    }
    if (_isConsoleObject(body) && body.method === 'SendStreamingMessage') {
        return 'stream';
    }
    if (_isConsoleObject(body) && body.method === 'SendMessage') {
        const params = _isConsoleObject(body.params) ? body.params : null;
        const configuration =
            params && _isConsoleObject(params.configuration) ? params.configuration : null;
        if (configuration && configuration.returnImmediately === true) {
            return 'async';
        }
        return 'sync';
    }
    throw new Error(
        'flows/api_console_run: body.method must be SendStreamingMessage or SendMessage',
    );
}

function _taskIdFromTask(task) {
    if (!_isConsoleObject(task)) {
        return null;
    }
    if (typeof task.id === 'string' && task.id.length > 0) {
        return task.id;
    }
    if (typeof task.taskId === 'string' && task.taskId.length > 0) {
        return task.taskId;
    }
    if (typeof task.task_id === 'string' && task.task_id.length > 0) {
        return task.task_id;
    }
    return null;
}

function _contextIdFromTask(task, fallbackContextId) {
    if (!_isConsoleObject(task)) {
        return fallbackContextId;
    }
    if (typeof task.contextId === 'string' && task.contextId.length > 0) {
        return task.contextId;
    }
    if (typeof task.context_id === 'string' && task.context_id.length > 0) {
        return task.context_id;
    }
    return fallbackContextId;
}

function _statusStateFromTask(task) {
    if (!_isConsoleObject(task)) {
        return null;
    }
    const status = _isConsoleObject(task.status) ? task.status : null;
    if (status && typeof status.state === 'string' && status.state.length > 0) {
        return status.state;
    }
    return null;
}

function _appendConsolePartsText(responseChunks, reasoningChunks, parts, name) {
    const text = _extractA2aTextFromParts(parts);
    const dataText = _partsDataText(parts);
    if (name === 'reasoning') {
        _appendConsoleResultText(reasoningChunks, text);
        _appendConsoleResultText(reasoningChunks, dataText);
        return;
    }
    _appendConsoleResultText(responseChunks, text);
    _appendConsoleResultText(responseChunks, dataText);
}

function _consoleTaskText(task) {
    const responseChunks = [];
    const reasoningChunks = [];
    if (_isConsoleObject(task) && Array.isArray(task.artifacts)) {
        for (const artifact of task.artifacts) {
            if (!_isConsoleObject(artifact)) {
                continue;
            }
            const name = typeof artifact.name === 'string' ? artifact.name : 'response';
            _appendConsolePartsText(responseChunks, reasoningChunks, artifact.parts, name);
        }
    }
    if (responseChunks.length === 0 && _isConsoleObject(task)) {
        const status = _isConsoleObject(task.status) ? task.status : null;
        const message = status && _isConsoleObject(status.message) ? status.message : null;
        if (message) {
            _appendConsolePartsText(responseChunks, reasoningChunks, message.parts, 'response');
        }
    }
    if (responseChunks.length === 0 && _isConsoleObject(task) && Array.isArray(task.parts)) {
        _appendConsolePartsText(responseChunks, reasoningChunks, task.parts, 'response');
    }
    return {
        response_text: responseChunks.join(''),
        reasoning_text: reasoningChunks.join(''),
    };
}

function _consoleResultFromJsonRpc(response, mode, fallbackContextId) {
    if (!_isConsoleObject(response)) {
        throw new Error('flows/api_console_run: JSON-RPC response object required');
    }
    if (response.error) {
        throw _jsonRpcResponseError(response);
    }
    const result = response.result;
    if (!_isConsoleObject(result)) {
        throw new Error('flows/api_console_run: JSON-RPC result Task required');
    }
    const text = _consoleTaskText(result);
    return {
        mode,
        task_id: _taskIdFromTask(result),
        context_id: _contextIdFromTask(result, fallbackContextId),
        terminal_state: _statusStateFromTask(result),
        response_text: text.response_text,
        reasoning_text: text.reasoning_text,
        frames: [response],
        raw: response,
    };
}

function _consoleSleep(ms) {
    return new Promise((resolve) => {
        setTimeout(resolve, ms);
    });
}

function _getTaskConsoleBody(taskId) {
    return {
        jsonrpc: '2.0',
        id: `get_${Date.now()}`,
        method: 'GetTask',
        params: { id: taskId, historyLength: 20 },
    };
}

function _consoleAcceptForMode(mode) {
    if (mode === 'stream') {
        return 'text/event-stream';
    }
    return 'application/json';
}

function _consoleRequestEnvelope(flowId, body, mode) {
    return {
        url: `/flows/api/v1/${encodeURIComponent(flowId)}`,
        method: 'POST',
        headers: {
            Accept: _consoleAcceptForMode(mode),
            'Content-Type': 'application/json',
            'A2A-Version': '1.0',
        },
        credentials: 'same-origin',
        body,
    };
}

function _consoleResponseEnvelope(envelope, bodyKind) {
    if (!_isConsoleObject(envelope)) {
        throw new Error('flows/api_console_run: HTTP response envelope required');
    }
    const headers = _isConsoleObject(envelope.headers) ? envelope.headers : EMPTY_OBJECT;
    return {
        status: typeof envelope.status === 'number' ? envelope.status : 0,
        status_text: typeof envelope.statusText === 'string' ? envelope.statusText : '',
        headers,
        content_type: typeof headers['content-type'] === 'string' ? headers['content-type'] : '',
        body_kind: bodyKind,
        raw_text: typeof envelope.raw === 'string' ? envelope.raw : '',
        body: envelope.body,
    };
}

function _consoleStreamEvents(frames) {
    if (!Array.isArray(frames)) {
        return EMPTY_LIST;
    }
    return frames.map((frame, index) => ({
        index,
        event: 'message',
        data: frame,
    }));
}

function _consoleResultWithExchange(result, request, response) {
    return {
        ...result,
        request,
        response,
    };
}

async function _pollConsoleAsyncTask(flowId, submittedResult) {
    const taskId = submittedResult.task_id;
    if (typeof taskId !== 'string' || taskId.length === 0) {
        return submittedResult;
    }
    const frames = [submittedResult.raw];
    const pollExchanges = [];
    let latest = submittedResult;
    for (let attempt = 0; attempt < 80; attempt += 1) {
        if (attempt > 0) {
            await _consoleSleep(500);
        }
        const pollBody = _getTaskConsoleBody(taskId);
        const pollRequest = _consoleRequestEnvelope(flowId, pollBody, 'sync');
        const pollEnvelope = await httpRequest({ ...pollRequest, returnMeta: true });
        const pollResponse = _consoleResponseEnvelope(pollEnvelope, 'json');
        const frame = pollEnvelope.body;
        pollExchanges.push({
            attempt: attempt + 1,
            request: pollRequest,
            response: pollResponse,
        });
        frames.push(frame);
        if (!_isConsoleObject(frame)) {
            continue;
        }
        if (frame.error) {
            throw _jsonRpcResponseError(frame);
        }
        if (!_isConsoleObject(frame.result)) {
            continue;
        }
        latest = _consoleResultWithExchange(
            _consoleResultFromJsonRpc(frame, 'async', submittedResult.context_id),
            submittedResult.request,
            submittedResult.response,
        );
        if (_isStreamBoundaryState(latest.terminal_state)) {
            return {
                ...latest,
                submitted_task: submittedResult.raw,
                poll_exchanges: pollExchanges,
                frames,
                raw: { submitted: submittedResult.raw, polls: frames.slice(1) },
            };
        }
    }
    return {
        ...latest,
        submitted_task: submittedResult.raw,
        poll_timeout: true,
        poll_exchanges: pollExchanges,
        frames,
        raw: { submitted: submittedResult.raw, polls: frames.slice(1) },
    };
}

export const apiConsoleRunOp = createAsyncOp({
    name: 'flows/api_console_run',
    transport: 'http',
    silent: true,
    restMirror: { method: 'POST', path: '/flows/api/v1/:flow_id' },
    request: async ({ payload }) => {
        if (!payload || typeof payload !== 'object') {
            throw new Error('flows/api_console_run: payload required');
        }
        const flowId = payload.flow_id;
        const body = payload.body;
        if (typeof flowId !== 'string' || flowId.length === 0) {
            throw new Error('flows/api_console_run: flow_id required');
        }
        if (!body || typeof body !== 'object') {
            throw new Error('flows/api_console_run: body required');
        }
        const mode = _consoleModeFromPayload(payload, body);
        const params = body.params;
        const message = params && typeof params === 'object' ? params.message : null;
        const contextId =
            message && typeof message.contextId === 'string' && message.contextId.length > 0
                ? message.contextId
                : null;
        if (mode !== 'stream') {
            const request = _consoleRequestEnvelope(flowId, body, mode);
            const envelope = await httpRequest({ ...request, returnMeta: true });
            const response = _consoleResponseEnvelope(envelope, 'json');
            const result = _consoleResultWithExchange(
                _consoleResultFromJsonRpc(envelope.body, mode, contextId),
                request,
                response,
            );
            if (mode === 'async') {
                return _pollConsoleAsyncTask(flowId, result);
            }
            return result;
        }
        const stream = {
            taskId: null,
            contextId,
            terminalState: null,
            terminal: false,
            responseChunks: [],
            reasoningChunks: [],
            frames: [],
        };
        const request = _consoleRequestEnvelope(flowId, body, mode);
        const envelope = await consumeA2aStream(
            {
                url: request.url,
                body,
                credentials: 'same-origin',
                captureRaw: true,
            },
            (frame) => {
                if (stream.terminal) {
                    return;
                }
                _collectConsoleFrame(frame, stream);
            },
        );
        const response = {
            ..._consoleResponseEnvelope(
                { status: envelope.status, statusText: envelope.statusText, headers: envelope.headers, raw: envelope.raw, body: null },
                'sse',
            ),
            body: stream.frames,
        };
        return {
            mode,
            task_id: stream.taskId,
            context_id: stream.contextId,
            terminal_state: stream.terminalState,
            response_text: stream.responseChunks.join(''),
            reasoning_text: stream.reasoningChunks.join(''),
            request,
            response,
            stream_events: _consoleStreamEvents(stream.frames),
            frames: stream.frames,
            raw: stream.frames,
        };
    },
});
