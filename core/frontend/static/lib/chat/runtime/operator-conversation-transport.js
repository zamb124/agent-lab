/**
 * Транспорт встроенного чата HITL-задачи (operator_handoff) для `<platform-chat>`.
 *
 * Оператор видит тот же разговор сессии, что и пользователь.
 * Источник истины — durable `ExecutionState.messages` (REST snapshot).
 * Live — A2A `tasks/resubscribe` на `a2a_task_id` (тот же Redis stream, что user chat).
 * Ask (takeover): POST `/hitl/{id}/conversation/messages`.
 * Close: WorkItem complete (не этот транспорт).
 */

import {
    a2aEndpointUrl,
    buildA2aResubscribeBody,
    consumeA2aStream,
} from './a2a-stream.js';

/** origin+префикс flows без завершающего слэша; пустая строка — same-origin `/flows`. */
function _flowsRoot(baseUrl) {
    const trimmed = typeof baseUrl === 'string' ? baseUrl.trim().replace(/\/$/, '') : '';
    return trimmed !== '' ? trimmed : '/flows';
}

/** ConversationTurn -> баббл chat-reducer. `agent` рисуется как `assistant`. */
export function turnToBubble(turn) {
    if (!turn || typeof turn !== 'object' || typeof turn.message_id !== 'string') {
        throw new Error('operator-transport: turn.message_id required');
    }
    const role = turn.role === 'agent' ? 'assistant' : String(turn.role || 'assistant');
    return {
        id: turn.message_id,
        role,
        content: typeof turn.text === 'string' ? turn.text : '',
        timestamp: new Date().toISOString(),
        files: [],
    };
}

function _randomIdempotencyKey() {
    if (globalThis.crypto && typeof globalThis.crypto.randomUUID === 'function') {
        return globalThis.crypto.randomUUID();
    }
    return `op-${Date.now()}-${Math.random().toString(36).slice(2)}`;
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
        this._workItemId = options.workItemId.trim();
        this._conversation = conv;
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
                            body: buildA2aResubscribeBody(this._a2aTaskId),
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

    async send(input) {
        const message = input && typeof input.message === 'string' ? input.message.trim() : '';
        if (message === '') {
            return;
        }
        const headers = await this._getHeaders();
        const url = `${this._root}/api/v1/hitl/${encodeURIComponent(this._workItemId)}/conversation/messages`;
        const response = await this._fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', Accept: 'application/json', ...headers },
            credentials: this._credentials,
            body: JSON.stringify({ text: message, idempotency_key: _randomIdempotencyKey() }),
        });
        if (!response.ok) {
            throw new Error(`operator-transport: send HTTP ${response.status}`);
        }
        const turn = await response.json();
        this._ingestTurn(turn);
    }

    async cancel() {
        /* HITL takeover: отмена live tail — no-op для send; dispose останавливает SSE. */
    }

    dispose() {
        this._stopLiveTail();
    }
}
