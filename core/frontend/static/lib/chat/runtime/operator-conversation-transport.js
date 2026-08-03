/**
 * Транспорт встроенного чата HITL-задачи (operator_handoff) для `<platform-chat>`.
 *
 * Оператор видит тот же разговор сессии, что и пользователь.
 * Источник истины — durable `ExecutionState.messages` (REST snapshot).
 * Live — A2A `SubscribeToTask` на `a2a_task_id` (тот же Redis stream, что user chat).
 * Takeover ask: POST `/hitl/{id}/conversation/messages` (+ file_ids).
 * Single_reply Send: POST worktracker complete (resolution_text + resolution_files).
 */

import {
    a2aEndpointUrl,
    buildA2aSubscribeToTaskBody,
    consumeA2aStream,
} from './a2a-stream.js';
import { buildWorkItemFileCreateSpecJson } from '../../utils/file-create-spec.js';
import {
    isPlatformFileRef,
    uploadPlatformFile,
} from '../../utils/platform-file-upload.js';

/** origin+префикс flows без завершающего слэша; пустая строка — same-origin `/flows`. */
function _flowsRoot(baseUrl) {
    const trimmed = typeof baseUrl === 'string' ? baseUrl.trim().replace(/\/$/, '') : '';
    return trimmed !== '' ? trimmed : '/flows';
}

/**
 * ConversationTurn -> баббл chat-reducer. `agent` рисуется как `assistant`.
 * @param {object} turn
 */
export function turnToBubble(turn) {
    if (!turn || typeof turn !== 'object' || typeof turn.message_id !== 'string') {
        throw new Error('operator-transport: turn.message_id required');
    }
    const role = turn.role === 'agent' ? 'assistant' : String(turn.role || 'assistant');
    const fileIds = Array.isArray(turn.file_ids)
        ? turn.file_ids.filter((id) => typeof id === 'string' && id.length > 0)
        : [];
    return {
        id: turn.message_id,
        role,
        content: typeof turn.text === 'string' ? turn.text : '',
        timestamp: new Date().toISOString(),
        files: [],
        fileIds,
    };
}

function _randomIdempotencyKey() {
    if (globalThis.crypto && typeof globalThis.crypto.randomUUID === 'function') {
        return globalThis.crypto.randomUUID();
    }
    return `op-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

/**
 * @param {unknown} file
 * @returns {boolean}
 */
function _isBrowserFile(file) {
    return typeof File !== 'undefined' && file instanceof File;
}

export class OperatorConversationTransport {
    /**
     * @param {{
     *   workItemId: string,
     *   conversation: {
     *     session_id: string,
     *     context_id: string,
     *     flow_id: string,
     *     branch_id?: string,
     *     a2a_task_id?: string|null,
     *   },
     *   mode?: string,
     *   baseUrl?: string,
     *   credentials?: RequestCredentials,
     *   getHeaders?: () => Promise<Record<string, string>>,
     *   fetchImpl?: typeof fetch,
     * }} options
     */
    constructor(options) {
        if (!options || typeof options !== 'object') {
            throw new Error('OperatorConversationTransport: options required');
        }
        if (typeof options.workItemId !== 'string' || options.workItemId.trim() === '') {
            throw new Error('OperatorConversationTransport: workItemId required');
        }
        const conv = options.conversation;
        if (!conv || typeof conv !== 'object') {
            throw new Error('OperatorConversationTransport: conversation ref required');
        }
        if (typeof conv.context_id !== 'string' || conv.context_id.trim() === '') {
            throw new Error('OperatorConversationTransport: conversation.context_id required');
        }
        if (typeof conv.session_id !== 'string' || conv.session_id.trim() === '') {
            throw new Error('OperatorConversationTransport: conversation.session_id required');
        }
        if (typeof conv.flow_id !== 'string' || conv.flow_id.trim() === '') {
            throw new Error('OperatorConversationTransport: conversation.flow_id required');
        }
        const a2aTaskId = typeof conv.a2a_task_id === 'string' ? conv.a2a_task_id.trim() : '';
        if (a2aTaskId === '') {
            throw new Error('OperatorConversationTransport: conversation.a2a_task_id required');
        }
        const mode = typeof options.mode === 'string' && options.mode.length > 0
            ? options.mode
            : 'takeover';
        if (mode !== 'takeover' && mode !== 'single_reply') {
            throw new Error(`OperatorConversationTransport: unsupported mode ${JSON.stringify(mode)}`);
        }
        this._workItemId = options.workItemId.trim();
        this._conversation = conv;
        this._mode = mode;
        this._a2aTaskId = a2aTaskId;
        this._root = _flowsRoot(options.baseUrl);
        this._credentials = options.credentials || 'include';
        this._getHeaders = typeof options.getHeaders === 'function' ? options.getHeaders : async () => ({});
        this._fetch = typeof options.fetchImpl === 'function' ? options.fetchImpl : globalThis.fetch.bind(globalThis);
        /** @type {import('./chat-controller.js').ChatController|null} */
        this._controller = null;
        /** @type {Set<string>} */
        this._seen = new Set();
        /** @type {AbortController|null} */
        this._liveAbort = null;
    }

    attach(controller) {
        if (!controller || typeof controller.applyRuntimeVerb !== 'function') {
            throw new Error('OperatorConversationTransport.attach: controller required');
        }
        this._controller = controller;
    }

    async loadHistory() {
        if (this._controller === null) {
            throw new Error('OperatorConversationTransport.loadHistory: not attached');
        }
        const headers = await this._getHeaders();
        const url = `${this._root}/api/v1/hitl/${encodeURIComponent(this._workItemId)}/conversation`;
        const response = await this._fetch(url, {
            method: 'GET',
            headers: { Accept: 'application/json', ...headers },
            credentials: this._credentials,
        });
        if (!response.ok) {
            throw new Error(`operator-transport: snapshot HTTP ${response.status}`);
        }
        const snapshot = await response.json();
        const turns = Array.isArray(snapshot.turns) ? snapshot.turns : [];
        const messages = [];
        for (const turn of turns) {
            if (turn && typeof turn === 'object' && typeof turn.message_id === 'string') {
                this._seen.add(turn.message_id);
            }
            if (turn && turn.role === 'system') {
                continue;
            }
            messages.push(turnToBubble(turn));
        }
        this._controller.applyRuntimeVerb('session_loaded', {
            sessionId: this._conversation.session_id,
            flowId: this._conversation.flow_id,
            contextId: this._conversation.context_id,
            taskId: this._a2aTaskId,
            messages,
        });
        this._startLiveTail();
    }

    _startLiveTail() {
        this._stopLiveTail();
        if (this._controller === null) {
            return;
        }
        this._liveAbort = new AbortController();
        void this._runLiveTail(this._liveAbort);
    }

    _stopLiveTail() {
        if (this._liveAbort !== null) {
            this._liveAbort.abort();
            this._liveAbort = null;
        }
    }

    /**
     * @param {AbortController} abort
     */
    async _runLiveTail(abort) {
        const streamState = {
            contextId: this._conversation.context_id,
            taskId: this._a2aTaskId,
            taskPrimed: true,
        };
        const target = {
            baseUrl: this._root,
            flowId: this._conversation.flow_id,
        };
        try {
            while (!abort.signal.aborted) {
                let terminal = false;
                try {
                    const headers = await this._getHeaders();
                    await consumeA2aStream(
                        {
                            url: a2aEndpointUrl(target),
                            body: buildA2aSubscribeToTaskBody(this._a2aTaskId),
                            headers,
                            credentials: this._credentials,
                            signal: abort.signal,
                        },
                        (frame) => {
                            if (terminal || abort.signal.aborted || this._controller === null) {
                                return;
                            }
                            terminal = this._controller.relayA2aFrame(frame, streamState).terminal;
                        },
                    );
                } catch (err) {
                    if (err instanceof Error && err.name === 'AbortError') {
                        break;
                    }
                    await new Promise((resolve) => {
                        setTimeout(resolve, 800);
                    });
                    continue;
                }
                if (terminal || abort.signal.aborted) {
                    break;
                }
                await new Promise((resolve) => {
                    setTimeout(resolve, 400);
                });
            }
        } finally {
            if (this._liveAbort === abort) {
                this._liveAbort = null;
            }
        }
    }

    /** Единая точка приёма turn (снимок / эхо POST) с дедупом по message_id. */
    _ingestTurn(turn) {
        if (!turn || typeof turn !== 'object' || typeof turn.message_id !== 'string') {
            return;
        }
        if (this._seen.has(turn.message_id)) {
            return;
        }
        this._seen.add(turn.message_id);
        if (turn.role === 'system') {
            return;
        }
        if (this._controller === null) {
            return;
        }
        this._controller.applyRuntimeVerb('user_message_added', {
            contextId: this._conversation.context_id,
            message: turnToBubble(turn),
        });
    }

    /**
     * @param {unknown[]} files
     * @returns {Promise<Array<{
     *   file_id: string,
     *   original_name: string,
     *   content_type: string,
     *   file_size: number,
     *   url?: string|null,
     * }>>}
     */
    async _resolveFileRefs(files) {
        const list = Array.isArray(files) ? files : [];
        /** @type {Array<{ file_id: string, original_name: string, content_type: string, file_size: number, url?: string|null }>} */
        const refs = [];
        for (const file of list) {
            if (isPlatformFileRef(file)) {
                refs.push({
                    file_id: file.file_id,
                    original_name: file.original_name,
                    content_type: file.content_type,
                    file_size: file.file_size,
                    url: typeof file.url === 'string' ? file.url : null,
                });
                continue;
            }
            if (!_isBrowserFile(file)) {
                throw new Error('operator-transport: files must be File or FileRef');
            }
            refs.push(await this._uploadBrowserFile(file));
        }
        return refs;
    }

    /**
     * @param {File} file
     */
    async _uploadBrowserFile(file) {
        const headers = await this._getHeaders();
        const result = await uploadPlatformFile({
            file,
            spec: buildWorkItemFileCreateSpecJson({ workItemId: this._workItemId }),
            credentials: this._credentials,
            headers,
            fetchImpl: this._fetch,
        });
        if (!result || typeof result !== 'object' || typeof result.file_id !== 'string') {
            throw new Error('operator-transport: file upload result.file_id required');
        }
        return {
            file_id: result.file_id,
            original_name: typeof result.original_name === 'string' ? result.original_name : file.name,
            content_type: typeof result.content_type === 'string' ? result.content_type : (file.type || 'application/octet-stream'),
            file_size: typeof result.file_size === 'number' ? result.file_size : file.size,
            url: typeof result.url === 'string' ? result.url : null,
        };
    }

    /**
     * @param {{ message?: string, files?: unknown[] }} input
     */
    async send(input) {
        const message = input && typeof input.message === 'string' ? input.message.trim() : '';
        const fileRefs = await this._resolveFileRefs(input && Array.isArray(input.files) ? input.files : []);
        if (message === '' && fileRefs.length === 0) {
            return;
        }
        if (this._mode === 'single_reply') {
            await this._completeWithReply(message, fileRefs);
            return;
        }
        await this._sendAsk(message, fileRefs);
    }

    /**
     * @param {string} text
     * @param {Array<{ file_id: string, original_name: string, content_type: string, file_size: number, url?: string|null }>} fileRefs
     */
    async _sendAsk(text, fileRefs) {
        if (text === '' && fileRefs.length === 0) {
            throw new Error('operator-transport: ask requires text or files');
        }
        const headers = await this._getHeaders();
        const url = `${this._root}/api/v1/hitl/${encodeURIComponent(this._workItemId)}/conversation/messages`;
        const body = {
            text,
            idempotency_key: _randomIdempotencyKey(),
            file_ids: fileRefs.map((ref) => ref.file_id),
        };
        const response = await this._fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', Accept: 'application/json', ...headers },
            credentials: this._credentials,
            body: JSON.stringify(body),
        });
        if (!response.ok) {
            throw new Error(`operator-transport: send HTTP ${response.status}`);
        }
        const turn = await response.json();
        this._ingestTurn(turn);
    }

    /**
     * @param {string} text
     * @param {Array<{ file_id: string, original_name: string, content_type: string, file_size: number, url?: string|null }>} fileRefs
     */
    async _completeWithReply(text, fileRefs) {
        if (text === '' && fileRefs.length === 0) {
            throw new Error('operator-transport: single_reply complete requires text or files');
        }
        const headers = await this._getHeaders();
        const url = `/worktracker/api/v1/work-items/${encodeURIComponent(this._workItemId)}/complete`;
        const response = await this._fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', Accept: 'application/json', ...headers },
            credentials: this._credentials,
            body: JSON.stringify({
                resolution_text: text,
                resolution_files: fileRefs,
            }),
        });
        if (!response.ok) {
            throw new Error(`operator-transport: complete HTTP ${response.status}`);
        }
        // Optimistic bubble: resume/consumer может отдать operator_reply позже;
        // оператор сразу видит свой текст (дедуп в _operatorReply по content).
        if (this._controller !== null && text !== '') {
            this._controller.applyRuntimeVerb('operator_reply', {
                task_id: this._a2aTaskId,
                text,
            });
        }
        if (this._controller !== null && fileRefs.length > 0) {
            this._controller.applyRuntimeVerb('operator_files', {
                task_id: this._a2aTaskId,
                file_ids: fileRefs.map((ref) => ref.file_id),
            });
        }
    }

    async cancel() {
        /* HITL: отмена live tail — no-op для send; dispose останавливает SSE. */
    }

    dispose() {
        this._stopLiveTail();
    }
}
