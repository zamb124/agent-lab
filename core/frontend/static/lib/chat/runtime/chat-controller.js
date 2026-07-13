/**
 * Standalone-оркестрация единого чат-компонента.
 *
 * `ChatController` держит chat runtime state (chat-state.js) и ведёт полный
 * lifecycle send/cancel/voice-relay поверх одного SSE-клиента (a2a-stream.js)
 * без EventBus — режим `<platform-chat>` на внешнем сайте (embed) и в любом
 * контексте без фабрики `flows/chat`. Внутри PlatformApp тот же reducer
 * применяется фабрикой `flows/chat` — состояние и семантика идентичны.
 *
 * `TtsOnlyStreamLifecycle` — единый lifecycle WS-сессии «только озвучка»
 * (VoiceMediaSession без микрофона) для всех поверхностей чата.
 */

import {
    isA2aTerminalState,
    mapA2aResultToChatRuntimeEvents,
    resolveA2aContextId,
} from '../a2a-chat-runtime.js';
import {
    a2aEndpointUrl,
    buildA2aCancelBody,
    buildA2aMessageStreamBody,
    consumeA2aStream,
} from './a2a-stream.js';
import {
    applyChatRuntimeEvent,
    buildRunTraceEntry,
    createInitialChatRuntimeState,
    STREAM_INCOMPLETE_I18N_KEY,
} from './chat-state.js';
import {
    feedStreamTtsFromA2aResult,
    stopStreamTtsPlayback,
    setStreamTtsTarget,
    clearStreamTtsTarget,
} from '../../voice/stream-tts-registry.js';
import { VoiceMediaSession } from '../../voice/voice-media-session.js';

export class ChatController {
    /**
     * @param {{
     *   target: { baseUrl?: string, flowId?: string, embedId?: string, branchId?: string|null },
     *   getHeaders?: () => Promise<Record<string, string>>,
     *   credentials?: RequestCredentials,
     *   onChange: (state: object) => void,
     *   onUiEvent?: (uiEvent: object, meta: { taskId: string|null, contextId: string|null }) => void,
     *   onRunEvent?: (type: string, payload: object) => void,
     *   transport?: {
     *     attach?: (controller: ChatController) => void,
     *     loadHistory?: () => Promise<void>,
     *     send: (input: object) => Promise<void>,
     *     cancel?: () => Promise<void>,
     *     dispose?: () => void,
     *   } | null,
     * }} options
     *   transport — необязательный не-A2A транспорт (например operator_handoff в
     *   карточке WorkItem): при наличии send/cancel/history делегируются в него,
     *   а он подаёт turns в reducer через публичный applyRuntimeVerb. A2A-путь
     *   (flows/embed/landing) при отсутствии transport не меняется.
     */
    constructor(options) {
        if (!options || typeof options !== 'object') {
            throw new Error('ChatController: options required');
        }
        if (!options.target || typeof options.target !== 'object') {
            throw new Error('ChatController: options.target required');
        }
        if (typeof options.onChange !== 'function') {
            throw new Error('ChatController: options.onChange required');
        }
        this._target = options.target;
        this._getHeaders = typeof options.getHeaders === 'function' ? options.getHeaders : async () => ({});
        this._credentials = options.credentials || 'include';
        this._onChange = options.onChange;
        this._onUiEvent = typeof options.onUiEvent === 'function' ? options.onUiEvent : null;
        this._onRunEvent = typeof options.onRunEvent === 'function' ? options.onRunEvent : null;
        this._transport = options.transport && typeof options.transport === 'object' ? options.transport : null;
        if (this._transport !== null && typeof this._transport.send !== 'function') {
            throw new Error('ChatController: options.transport.send required');
        }
        /** @type {object} */
        this._state = createInitialChatRuntimeState();
        /** @type {AbortController|null} */
        this._streamAbort = null;
        this._sending = false;
        this._cancelBusy = false;
        if (this._transport !== null && typeof this._transport.attach === 'function') {
            this._transport.attach(this);
        }
    }

    get hasTransport() {
        return this._transport !== null;
    }

    /** Загрузить историю (только для не-A2A транспорта); A2A использует loadSession хоста. */
    async loadHistory() {
        if (this._transport === null || typeof this._transport.loadHistory !== 'function') {
            return;
        }
        await this._transport.loadHistory();
    }

    /** Освободить ресурсы транспорта (подписки на шину и т.п.). */
    dispose() {
        if (this._transport !== null && typeof this._transport.dispose === 'function') {
            this._transport.dispose();
        }
    }

    get state() {
        return this._state;
    }

    get sending() {
        return this._sending;
    }

    get cancelBusy() {
        return this._cancelBusy;
    }

    /** Обновить цель (например смена flow/branch в хосте) — вне активного стрима. */
    setTarget(target) {
        if (!target || typeof target !== 'object') {
            throw new Error('ChatController: target object required');
        }
        this._target = target;
    }

    /**
     * Задать не-A2A транспорт после конструирования (хост узнаёт work-item/policy
     * из атрибутов уже после constructor). Идемпотентно по ссылке.
     */
    setTransport(transport) {
        if (!transport || typeof transport !== 'object' || typeof transport.send !== 'function') {
            throw new Error('ChatController.setTransport: transport with send required');
        }
        if (this._transport === transport) {
            return;
        }
        this._transport = transport;
        if (typeof transport.attach === 'function') {
            transport.attach(this);
        }
    }

    /** Обновить режим credentials (cookie include/omit) — хост узнаёт его после конструирования. */
    setCredentials(credentials) {
        if (credentials !== 'include' && credentials !== 'omit' && credentials !== 'same-origin') {
            throw new Error('ChatController: invalid credentials mode');
        }
        this._credentials = credentials;
    }

    /** Применить runtime-verb к состоянию и уведомить хост (voice relay, session load). */
    applyRuntimeVerb(verb, payload) {
        const next = applyChatRuntimeEvent(this._state, verb, payload);
        if (next !== this._state) {
            this._state = next;
            this._onChange(this._state);
        }
    }

    initSession(payload) {
        this.applyRuntimeVerb('session_init', payload || {});
    }

    newChat() {
        if (this._streamAbort !== null) {
            this._streamAbort.abort();
        }
        stopStreamTtsPlayback();
        this.applyRuntimeVerb('session_reset', {});
    }

    addUserMessage(contextId, message) {
        this.applyRuntimeVerb('user_message_added', { contextId, message });
    }

    _appendTrace(contextId, taskId, fields) {
        if (typeof contextId !== 'string' || contextId.length === 0) {
            return;
        }
        this.applyRuntimeVerb('trace_append', {
            context_id: contextId,
            entry: buildRunTraceEntry(taskId, fields),
        });
    }

    /**
     * Один кадр JSON-RPC A2A → reducer + TTS + ui_event проброс хосту.
     * Используется и SSE-стримом send(), и voice-bridge relay.
     *
     * @param {object} frame
     * @param {{ contextId: string|null, taskId: string|null, taskPrimed: boolean }} streamState
     * @returns {{ terminal: boolean }}
     */
    relayA2aFrame(frame, streamState) {
        if (!frame || typeof frame !== 'object') {
            return { terminal: false };
        }
        if (frame.error) {
            const err = frame.error;
            let errorMessage = 'a2a stream error';
            if (err && typeof err === 'object') {
                if (typeof err.message === 'string' && err.message.length > 0) {
                    errorMessage = err.message;
                } else if (typeof err.code === 'string' && err.code.length > 0) {
                    errorMessage = err.code;
                }
            }
            const error = new Error(errorMessage);
            error.name = 'A2aStreamError';
            throw error;
        }
        const result = frame.result;
        if (!result || typeof result !== 'object') {
            return { terminal: false };
        }
        const mapped = mapA2aResultToChatRuntimeEvents(result, {
            contextId: streamState.contextId,
            currentTaskId: streamState.taskId,
            taskPrimed: streamState.taskPrimed,
        });
        streamState.taskPrimed = mapped.taskPrimed;
        if (mapped.nextTaskId) {
            streamState.taskId = mapped.nextTaskId;
        }
        const resolvedContextId = resolveA2aContextId(result, streamState.contextId);
        if (typeof resolvedContextId === 'string' && resolvedContextId.length > 0) {
            streamState.contextId = resolvedContextId;
        }
        for (const runEvent of mapped.runEvents) {
            if (this._onRunEvent) {
                this._onRunEvent(runEvent.type, runEvent.payload);
            }
        }
        for (const trace of mapped.traceEntries) {
            this._appendTrace(trace.context_id, trace.task_id, trace.fields);
        }
        for (const event of mapped.events) {
            if (event.type === 'ui_event') {
                if (this._onUiEvent) {
                    const uiEvent = event.payload && typeof event.payload === 'object' ? event.payload.event : null;
                    if (uiEvent && typeof uiEvent === 'object') {
                        this._onUiEvent(uiEvent, {
                            taskId: streamState.taskId,
                            contextId: streamState.contextId,
                        });
                    }
                }
                continue;
            }
            this.applyRuntimeVerb(event.type, event.payload);
        }
        feedStreamTtsFromA2aResult(result);

        let stateValue = null;
        if (result.kind === 'status-update' && result.status && typeof result.status.state === 'string') {
            stateValue = result.status.state;
        } else if (result.kind === 'artifact-update' && result.artifact && typeof result.artifact.state === 'string') {
            stateValue = result.artifact.state;
        }
        return { terminal: mapped.terminal || isA2aTerminalState(stateValue, result.final === true) };
    }

    /**
     * Отправка пользовательского сообщения: user bubble + полный SSE lifecycle.
     *
     * @param {{ message: string, files?: Array<object>, metadata?: object|null,
     *   userMessage?: object|null }} input
     *   userMessage — готовый bubble (например с files meta); null — собирается из message.
     */
    async send(input) {
        if (!input || typeof input !== 'object') {
            throw new Error('ChatController.send: input required');
        }
        if (this._sending) {
            throw new Error('ChatController.send: stream already active');
        }
        if (this._transport !== null) {
            this._sending = true;
            this._onChange(this._state);
            try {
                await this._transport.send(input);
            } finally {
                this._sending = false;
                this._onChange(this._state);
            }
            return;
        }
        const message = typeof input.message === 'string' ? input.message : '';
        const files = Array.isArray(input.files) ? input.files : [];
        if (message.trim() === '' && files.length === 0) {
            return;
        }
        stopStreamTtsPlayback();

        let contextId = this._state.currentContextId;
        if (typeof contextId !== 'string' || contextId.length === 0) {
            this.initSession({});
            contextId = this._state.currentContextId;
        }

        const userMessage = input.userMessage && typeof input.userMessage === 'object'
            ? input.userMessage
            : {
                id: `user_${Date.now()}`,
                role: 'user',
                content: message,
                timestamp: new Date().toISOString(),
                files: [],
            };
        this.addUserMessage(contextId, userMessage);

        const body = buildA2aMessageStreamBody({
            message,
            contextId,
            branchId: this._target.branchId != null ? this._target.branchId : null,
            files,
            metadata: input.metadata || null,
        });

        const streamState = { contextId, taskId: null, taskPrimed: false };
        this._sending = true;
        this._streamAbort = new AbortController();
        this._onChange(this._state);
        if (this._onRunEvent) {
            this._onRunEvent('flows/run/flow_started', {});
        }
        let terminal = false;
        try {
            const headers = await this._getHeaders();
            await consumeA2aStream(
                {
                    url: a2aEndpointUrl(this._target),
                    body,
                    headers,
                    credentials: this._credentials,
                    signal: this._streamAbort.signal,
                },
                (frame) => {
                    if (terminal) {
                        return;
                    }
                    terminal = this.relayA2aFrame(frame, streamState).terminal;
                },
            );
            this.applyRuntimeVerb('send_succeeded', {
                task_id: streamState.taskId,
                context_id: streamState.contextId,
            });
            if (!terminal && typeof streamState.taskId === 'string' && streamState.taskId.length > 0) {
                this.applyRuntimeVerb('failed', {
                    task_id: streamState.taskId,
                    context_id: streamState.contextId,
                    error_i18n_key: STREAM_INCOMPLETE_I18N_KEY,
                });
            }
        } catch (err) {
            if (err instanceof Error && err.name === 'AbortError') {
                this.applyRuntimeVerb('a2a_interrupted', {
                    task_id: streamState.taskId,
                    context_id: streamState.contextId,
                });
            } else {
                const errorText = err instanceof Error ? err.message : String(err);
                if (typeof streamState.taskId === 'string' && streamState.taskId.length > 0) {
                    this.applyRuntimeVerb('failed', {
                        task_id: streamState.taskId,
                        context_id: streamState.contextId,
                        error: errorText,
                    });
                } else {
                    this.applyRuntimeVerb('send_failed', {});
                }
                throw err;
            }
        } finally {
            this._streamAbort = null;
            this._sending = false;
            if (this._onRunEvent) {
                this._onRunEvent('flows/run/flow_done', {});
            }
            this._onChange(this._state);
        }
    }

    /**
     * Resume после breakpoint: пустой turn без user bubble, тот же contextId/taskId на backend.
     *
     * @param {{ metadata?: object|null }} input
     */
    async sendResume(input) {
        if (!input || typeof input !== 'object') {
            throw new Error('ChatController.sendResume: input required');
        }
        if (this._sending) {
            throw new Error('ChatController.sendResume: stream already active');
        }
        stopStreamTtsPlayback();

        const contextId = this._state.currentContextId;
        if (typeof contextId !== 'string' || contextId.length === 0) {
            throw new Error('ChatController.sendResume: contextId required');
        }

        const body = buildA2aMessageStreamBody({
            message: '',
            contextId,
            branchId: this._target.branchId != null ? this._target.branchId : null,
            files: [],
            metadata: input.metadata || null,
        });

        const streamState = { contextId, taskId: null, taskPrimed: false };
        this._sending = true;
        this._streamAbort = new AbortController();
        this._onChange(this._state);
        if (this._onRunEvent) {
            this._onRunEvent('flows/run/flow_started', {});
        }
        let terminal = false;
        try {
            const headers = await this._getHeaders();
            await consumeA2aStream(
                {
                    url: a2aEndpointUrl(this._target),
                    body,
                    headers,
                    credentials: this._credentials,
                    signal: this._streamAbort.signal,
                },
                (frame) => {
                    if (terminal) {
                        return;
                    }
                    terminal = this.relayA2aFrame(frame, streamState).terminal;
                },
            );
            this.applyRuntimeVerb('send_succeeded', {
                task_id: streamState.taskId,
                context_id: streamState.contextId,
            });
            if (!terminal && typeof streamState.taskId === 'string' && streamState.taskId.length > 0) {
                this.applyRuntimeVerb('failed', {
                    task_id: streamState.taskId,
                    context_id: streamState.contextId,
                    error_i18n_key: STREAM_INCOMPLETE_I18N_KEY,
                });
            }
        } catch (err) {
            if (err instanceof Error && err.name === 'AbortError') {
                this.applyRuntimeVerb('a2a_interrupted', {
                    task_id: streamState.taskId,
                    context_id: streamState.contextId,
                });
            } else {
                const errorText = err instanceof Error ? err.message : String(err);
                if (typeof streamState.taskId === 'string' && streamState.taskId.length > 0) {
                    this.applyRuntimeVerb('failed', {
                        task_id: streamState.taskId,
                        context_id: streamState.contextId,
                        error: errorText,
                    });
                } else {
                    this.applyRuntimeVerb('send_failed', {});
                }
                throw err;
            }
        } finally {
            this._streamAbort = null;
            this._sending = false;
            if (this._onRunEvent) {
                this._onRunEvent('flows/run/flow_done', {});
            }
            this._onChange(this._state);
        }
    }

    /** Отмена активного выполнения: abort SSE + JSON-RPC tasks/cancel. */
    async cancel() {
        if (this._cancelBusy) {
            return;
        }
        if (this._transport !== null) {
            if (typeof this._transport.cancel === 'function') {
                await this._transport.cancel();
            }
            return;
        }
        stopStreamTtsPlayback();
        if (this._streamAbort !== null) {
            this._streamAbort.abort();
        }
        const taskId = this._state.currentTaskId;
        if (typeof taskId !== 'string' || taskId === '') {
            return;
        }
        this._cancelBusy = true;
        this._onChange(this._state);
        try {
            const headers = await this._getHeaders();
            await fetch(a2aEndpointUrl(this._target), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', ...headers },
                credentials: this._credentials,
                body: JSON.stringify(buildA2aCancelBody(taskId)),
            });
        } catch {
            /* стрим уже оборван на клиенте */
        } finally {
            this._cancelBusy = false;
            this._onChange(this._state);
        }
    }
}

/**
 * WS-сессия «только озвучка» (TTS без микрофона) — единый lifecycle для всех
 * поверхностей чата: prime по жесту пользователя, фоновый ensure, dispose.
 * Хост задаёт контекст через колбэки; ошибки уходят в onError.
 */
export class TtsOnlyStreamLifecycle {
    /**
     * @param {{
     *   isAllowed: () => boolean,
     *   getWsBase: () => string,
     *   getCompanyId: () => string,
     *   getWsQuery: () => Promise<Record<string, string>>,
     *   readTtsEnabled: () => boolean,
     *   onError: (err: unknown) => void,
     * }} options
     */
    constructor(options) {
        if (!options || typeof options !== 'object') {
            throw new Error('TtsOnlyStreamLifecycle: options required');
        }
        for (const fn of ['isAllowed', 'getWsBase', 'getCompanyId', 'getWsQuery', 'readTtsEnabled', 'onError']) {
            if (typeof options[fn] !== 'function') {
                throw new Error(`TtsOnlyStreamLifecycle: options.${fn} required`);
            }
        }
        this._opts = options;
        /** @type {InstanceType<typeof VoiceMediaSession>|null} */
        this._media = null;
        this._starting = false;
    }

    get media() {
        return this._media;
    }

    dispose() {
        const media = this._media;
        this._media = null;
        this._starting = false;
        clearStreamTtsTarget();
        if (media) {
            try {
                media.close();
            } catch {
                /* noop */
            }
        }
    }

    /** Жест отправки: prime playback + WS connect в фоне. */
    primeFromUserGesture() {
        if (!this._opts.isAllowed()) {
            return;
        }
        if (this._media !== null && this._media.isConnected) {
            this._media.primePlaybackFromUserGesture();
            setStreamTtsTarget(this._media, this._opts.readTtsEnabled);
            return;
        }
        if (this._starting) {
            const media = this._media;
            if (media && typeof media.primePlaybackFromUserGesture === 'function') {
                media.primePlaybackFromUserGesture();
            }
            if (media) {
                setStreamTtsTarget(media, this._opts.readTtsEnabled);
            }
            return;
        }
        void this._start(true);
    }

    /** Фоновое подключение без жеста (переоткрытие панели, смена pref). */
    async ensure() {
        if (!this._opts.isAllowed()) {
            this.dispose();
            return;
        }
        if (this._media !== null && this._media.isConnected) {
            setStreamTtsTarget(this._media, this._opts.readTtsEnabled);
            return;
        }
        if (this._starting) {
            return;
        }
        await this._start(false);
    }

    /**
     * Пока WS коннектится, `feedStreamTtsFromA2aResult` без цели; ждём до maxMs.
     */
    async awaitReady(maxMs = 2500) {
        const t0 = Date.now();
        while (Date.now() - t0 < maxMs) {
            if (!this._opts.isAllowed()) {
                return;
            }
            if (!this._starting && this._media !== null && this._media.isConnected) {
                return;
            }
            await new Promise((resolve) => setTimeout(resolve, 40));
        }
    }

    async _start(fromGesture) {
        this.dispose();
        this._starting = true;
        /** @type {InstanceType<typeof VoiceMediaSession>|null} */
        let media = null;
        try {
            const wsBase = this._opts.getWsBase().replace(/\/$/, '').replace(/^http/, 'ws');
            if (wsBase === '') {
                return;
            }
            const companyId = this._opts.getCompanyId();
            if (typeof companyId !== 'string' || companyId.trim() === '') {
                return;
            }
            const wsQuery = await this._opts.getWsQuery();
            const sessionId = `tts_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
            const mediaOpts = {
                baseUrl: wsBase,
                sessionId,
                companyId: companyId.trim(),
                autoRecord: false,
            };
            if (wsQuery && Object.keys(wsQuery).length > 0) {
                Object.assign(mediaOpts, { query: wsQuery });
            }
            media = new VoiceMediaSession(mediaOpts);
            media.addEventListener('error', (event) => {
                this._opts.onError(event.detail);
            });
            media.addEventListener('closed', () => {
                if (this._media === media) {
                    this._media = null;
                    clearStreamTtsTarget();
                }
            });
            this._media = media;
            if (fromGesture) {
                media.primePlaybackFromUserGesture();
            }
            setStreamTtsTarget(media, this._opts.readTtsEnabled);
            await media.connect();
            if (this._media !== media) {
                try {
                    media.close();
                } catch {
                    /* noop */
                }
                return;
            }
            if (!this._opts.isAllowed()) {
                this._media = null;
                clearStreamTtsTarget();
                try {
                    media.close();
                } catch {
                    /* noop */
                }
                return;
            }
            setStreamTtsTarget(media, this._opts.readTtsEnabled);
        } catch (err) {
            if (this._media === media) {
                this._media = null;
            }
            clearStreamTtsTarget();
            if (media !== null) {
                try {
                    media.close();
                } catch {
                    /* noop */
                }
            }
            this._opts.onError(err);
        } finally {
            this._starting = false;
        }
    }
}
