/**
 * Транспорт встроенного чата HITL-задачи (operator_handoff) для `<platform-chat>`.
 *
 * Оператор в карточке WorkItem видит технически тот же разговор сессии, что и
 * пользователь. Источник истины — durable-леджер flows (`ExecutionState.messages`),
 * проекция отдаётся REST-снимком, новые turns приходят push-событием
 * `flows/hitl_conversation/turn_appended` через `platform:ui_events` -> WS.
 *
 * Транспорт не рендерит и не редьюсит сам: он подаёт turns в общий chat-reducer
 * через публичный `controller.applyRuntimeVerb(...)`, поэтому бабблы, композер и
 * токены — ровно те же, что в чате flows/embed. Дедуп по `message_id` (и снимок,
 * и push, и эхо POST проходят через единый `_ingestTurn`).
 */

export const HITL_CONVERSATION_TURN_APPENDED = 'flows/hitl_conversation/turn_appended';

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
     *   conversation: { session_id: string, context_id: string, flow_id: string, branch_id?: string },
     *   baseUrl?: string,
     *   credentials?: RequestCredentials,
     *   getHeaders?: () => Promise<Record<string, string>>,
     *   bus: { subscribeType: (type: string, cb: (event: object) => void) => (() => void) },
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
        if (!conv || typeof conv !== 'object'
            || typeof conv.context_id !== 'string' || conv.context_id.trim() === ''
            || typeof conv.session_id !== 'string' || conv.session_id.trim() === ''
            || typeof conv.flow_id !== 'string' || conv.flow_id.trim() === '') {
            throw new Error('OperatorConversationTransport: conversation ref required');
        }
        if (!options.bus || typeof options.bus.subscribeType !== 'function') {
            throw new Error('OperatorConversationTransport: bus with subscribeType required');
        }
        this._workItemId = options.workItemId.trim();
        this._conversation = conv;
        this._root = _flowsRoot(options.baseUrl);
        this._credentials = options.credentials || 'include';
        this._getHeaders = typeof options.getHeaders === 'function' ? options.getHeaders : async () => ({});
        this._bus = options.bus;
        this._fetch = typeof options.fetchImpl === 'function' ? options.fetchImpl : globalThis.fetch.bind(globalThis);
        /** @type {import('./chat-controller.js').ChatController|null} */
        this._controller = null;
        /** @type {Set<string>} */
        this._seen = new Set();
        /** @type {(() => void)|null} */
        this._unsubscribe = null;
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
            taskId: null,
            messages,
        });
        this._subscribeRealtime();
    }

    _subscribeRealtime() {
        if (this._unsubscribe !== null) {
            return;
        }
        this._unsubscribe = this._bus.subscribeType(HITL_CONVERSATION_TURN_APPENDED, (event) => {
            const payload = event && typeof event === 'object' ? event.payload : null;
            if (!payload || typeof payload !== 'object') {
                return;
            }
            if (payload.work_item_id !== this._workItemId) {
                return;
            }
            this._ingestTurn(payload.turn);
        });
    }

    /** Единая точка приёма turn (снимок/push/эхо POST) с дедупом по message_id. */
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
        /* HITL takeover не имеет отменяемого стрима; отмена — no-op. */
    }

    dispose() {
        if (this._unsubscribe !== null) {
            this._unsubscribe();
            this._unsubscribe = null;
        }
    }
}
