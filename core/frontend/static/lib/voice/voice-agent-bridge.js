/**
 * VoiceAgentBridge — тонкий мост между `VoiceMediaSession` (apps/voice WS)
 * и A2A SSE стримом (apps/flows).
 *
 * Сервисы `voice` и `flows` не знают друг про друга: универсальный
 * gateway в одном углу, логика агента в другом. Bridge живёт на
 * клиенте (или в мобильном приложении — тот же контракт) и делает:
 *
 *  - `voice → flows`: на каждое финальное распознавание
 *    (`transcript{final:true}`) отправляет `message/stream` в A2A
 *    (`embed/{embed_id}` или `flow/{flow_id}`). Тело A2A сообщения —
 *    текст пользователя; `voice` в A2A не участвует. Нефинальный
 *    текст (`final:false`) копится последним куском; при `stop()` моста
 *    (выключение микрофона) без последующего финала тот же путь отправки
 *    вызывается один раз для коммита в чат. Если финальный transcript уже
 *    запустил `message/stream`, пустой `stop()` после снятия эфира **не**
 *    вызывает `AbortController.abort` на этом fetch (иначе UI успевает показать
 *    сообщение пользователя из `beforeA2aStream`, а ответ гаснет).
 *  - Авто-TTS из ответа обрабатывается отдельно: после `_dispatchA2aEvent` в
 *    `apps/flows/ui/events/resources/chat.resource.js` и в embed
 *    `_handleEvent` вызывается `feedStreamTtsFromA2aResult` (registry —
 *    `stream-tts-registry.js`, см. `voice.mdc`).
 *  - Barge-in: `vad` с непрерывной речью ≥ ~0,3 s (как порог на шлюзе)
 *    во время TTS **или** пока живёт A2A fetch (фаза SSE до первого TTS) →
 *    `voice.stopPlayback()`, `AbortController.abort`, при наличии `taskId` —
 *    `tasks/cancel`. DOM `a2aAborted`: при оборванном SSE — из `catch (AbortError)`
 *    после установки `_pendingA2aAbortDetail`; если fetch уже закрыт (например, только TTS) —
 *    сразу из `_cancelCurrentTask`. Payload: `task_id`/`context_id` для сброса `flows/chat`.
 *
 * Инкапсуляция: bridge не знает ни про конкретный UI-компонент, ни
 * про state-store; он общается только через DOM-события
 * `VoiceMediaSession` и публичные DOM-события самого bridge
 * (`userMessage`, `bargeIn`, `a2aAborted`, `a2aSettled`, `error`) —
 * чтобы UI мог показывать live transcript/индикаторы без костылей
 * в модулях friend'ах.
 */

import { streamEmbedA2A } from '../embed-chat/embed-a2a-stream.js';
import { isVoiceClientDebugEnabled } from './voice-media-session.js';

/** Минимальная длительность сегмента речи (VAD open) до client barge-in, мс — как `vad_speech_seconds < 0.3` в `BargeInController`. */
const CLIENT_BARGE_MIN_SPEECH_MS = 300;

/**
 * @typedef {object} VoiceAgentBridgeOptions
 * @property {import('./voice-media-session.js').VoiceMediaSession} mediaSession
 * @property {string} a2aBaseUrl - origin + префикс flows (`https://host/flows`), без завершающего "/"
 * @property {string} [flowId] - id flow; альтернатива `embedId`
 * @property {string} [embedId] - id embed; альтернатива `flowId`
 * @property {string|null} [branchId]
 * @property {() => Promise<Record<string,string>>} [getHeaders]
 * @property {RequestCredentials} [credentials='omit']
 * @property {string|null} [initialContextId]
 * @property {() => string|null|undefined} [getContextId] — перед каждым message/stream подставляется актуальный contextId из UI (например embed-chat).
 * @property {() => Promise<Record<string, unknown>|null|undefined>} [getStreamMetadata] — metadata для A2A (как у текстовой отправки: variables и т.д.).
 * @property {(text: string) => Promise<void>} [beforeA2aStream] — перед fetch (например добавить user/assistant пузыри в чат).
 * @property {(event: object) => void} [onA2aStreamEvent] — каждый SSE-кадр для UI; потребитель вызывает релей/reducer и там же `feedStreamTtsFromA2aResult` (flows: `relayA2aVoiceStreamRpcFrame`, embed: `platform-embed-chat._handleEvent`). Сам `VoiceAgentBridge` авто-TTS не вызывает.
 */

export class VoiceAgentBridge extends EventTarget {
    /**
     * @param {VoiceAgentBridgeOptions} options
     */
    constructor(options) {
        super();
        if (!options || typeof options !== 'object') {
            throw new Error('VoiceAgentBridge: options required');
        }
        if (!options.mediaSession) {
            throw new Error('VoiceAgentBridge: mediaSession required');
        }
        if (typeof options.a2aBaseUrl !== 'string' || options.a2aBaseUrl === '') {
            throw new Error('VoiceAgentBridge: a2aBaseUrl required');
        }
        if (!options.flowId && !options.embedId) {
            throw new Error('VoiceAgentBridge: flowId or embedId required');
        }
        this._media = options.mediaSession;
        this._a2aBaseUrl = options.a2aBaseUrl.replace(/\/$/, '');
        this._flowId = typeof options.flowId === 'string' ? options.flowId : undefined;
        this._embedId = typeof options.embedId === 'string' ? options.embedId : undefined;
        this._branchId = options.branchId != null ? options.branchId : null;
        this._getHeaders = typeof options.getHeaders === 'function' ? options.getHeaders : async () => ({});
        this._credentials = options.credentials === 'include' ? 'include' : 'omit';
        this._contextId = typeof options.initialContextId === 'string' ? options.initialContextId : null;
        this._getContextId = typeof options.getContextId === 'function' ? options.getContextId : null;
        this._getStreamMetadata =
            typeof options.getStreamMetadata === 'function' ? options.getStreamMetadata : null;
        this._beforeA2aStream = typeof options.beforeA2aStream === 'function' ? options.beforeA2aStream : null;
        this._onA2aStreamEvent =
            typeof options.onA2aStreamEvent === 'function' ? options.onA2aStreamEvent : null;

        /** @type {AbortController|null} */
        this._currentAbort = null;
        /** @type {string|null} */
        this._currentTaskId = null;
        /** @type {boolean} */
        this._ttsActive = false;
        /** @type {ReturnType<typeof setTimeout>|null} */
        this._clientBargeTimer = null;
        /** @type {boolean} */
        this._vadSpeechSegmentOpen = false;
        /**
         * Перед `abort` сохраняем метаданные; в `catch (AbortError)` шлём `a2aAborted` один раз.
         * @type {{ task_id: string | null; context_id: string | null } | null}
         */
        this._pendingA2aAbortDetail = null;
        this._started = false;

        /** @type {string} — последний нефинальный STT-текст; при `stop()` без финала уходит в A2A один раз */
        this._pendingPartialTranscript = '';

        this._onTranscript = this._onTranscript.bind(this);
        this._onVad = this._onVad.bind(this);
        this._onTtsState = this._onTtsState.bind(this);
        this._onVoiceDiagnostic = this._onVoiceDiagnostic.bind(this);
    }

    /** @returns {string|null} */
    get contextId() { return this._contextId; }

    /**
     * Подписаться на события voice.
     */
    start() {
        if (this._started) return;
        this._started = true;
        this._media.addEventListener('transcript', this._onTranscript);
        this._media.addEventListener('vad', this._onVad);
        this._media.addEventListener('ttsState', this._onTtsState);
        this._media.addEventListener('diagnostic', this._onVoiceDiagnostic);
    }

    /**
     * @param {Event} event
     */
    _onVoiceDiagnostic(event) {
        if (!isVoiceClientDebugEnabled()) {
            return;
        }
        const ev = /** @type {CustomEvent<Record<string, unknown>>} */ (event);
        const detail =
            ev.detail !== null && typeof ev.detail === 'object' ? ev.detail : {};
        console.info('[voice-agent-bridge]', 'diagnostic', detail);
    }

    /**
     * Отписаться от событий voice и при наличии — отправить последний partial.
     * Активный fetch `message/stream`, уже запущенный после `transcript{final:true}`,
     * не отменять: отмена — через barge-in / `tasks/cancel`.
     */
    stop() {
        if (!this._started) return;
        const flushOnStop =
            typeof this._pendingPartialTranscript === 'string'
                ? this._pendingPartialTranscript.trim()
                : '';
        this._pendingPartialTranscript = '';

        this._started = false;
        this._media.removeEventListener('transcript', this._onTranscript);
        this._media.removeEventListener('vad', this._onVad);
        this._media.removeEventListener('ttsState', this._onTtsState);
        this._media.removeEventListener('diagnostic', this._onVoiceDiagnostic);
        this._clearClientBargeDebounce();
        if (flushOnStop !== '') {
            if (this._currentAbort !== null) {
                const tid = this._currentTaskId;
                this._pendingA2aAbortDetail = {
                    task_id: typeof tid === 'string' && tid !== '' ? tid : null,
                    context_id:
                        typeof this._contextId === 'string' && this._contextId !== ''
                            ? this._contextId
                            : null,
                };
            }
            void this._sendUserMessage(flushOnStop);
            return;
        }
    }

    _clearClientBargeDebounce() {
        if (this._clientBargeTimer !== null) {
            clearTimeout(this._clientBargeTimer);
            this._clientBargeTimer = null;
        }
        this._vadSpeechSegmentOpen = false;
    }

    /**
     * @returns {boolean}
     */
    _isClientBargeInScope() {
        return this._ttsActive === true || this._currentAbort !== null;
    }

    /**
     * Срабатывание после дебаунса по длительности речи (см. `CLIENT_BARGE_MIN_SPEECH_MS`).
     */
    _executeClientBargeIn() {
        this._clientBargeTimer = null;
        if (!this._vadSpeechSegmentOpen) return;
        if (!this._isClientBargeInScope()) return;
        this._dispatch('bargeIn', {});
        this._media.stopPlayback();
        void this._cancelCurrentTask();
    }

    /**
     * @param {Event} event
     */
    _onTranscript(event) {
        const detail =
            /** @type {CustomEvent<{text:string, final:boolean, interrupted?:boolean}>} */ (event).detail;
        if (!detail) return;
        const text = typeof detail.text === 'string' ? detail.text.trim() : '';
        if (detail.final === true) {
            this._pendingPartialTranscript = '';
            if (text === '') return;
            void this._sendUserMessage(text);
            return;
        }
        if (text !== '') {
            this._pendingPartialTranscript = text;
        }
    }

    /**
     * @param {Event} event
     */
    _onVad(event) {
        const detail = /** @type {CustomEvent<{state:'started'|'ended'}>} */ (event).detail;
        if (!detail || typeof detail.state !== 'string') return;
        if (detail.state === 'ended') {
            this._clearClientBargeDebounce();
            return;
        }
        if (detail.state !== 'started') return;
        if (!this._isClientBargeInScope()) return;
        this._clearClientBargeDebounce();
        this._vadSpeechSegmentOpen = true;
        this._clientBargeTimer = setTimeout(() => {
            this._executeClientBargeIn();
        }, CLIENT_BARGE_MIN_SPEECH_MS);
    }

    /**
     * @param {Event} event
     */
    _onTtsState(event) {
        const detail = /** @type {CustomEvent<{state:'playing'|'stopped'}>} */ (event).detail;
        if (!detail) return;
        this._ttsActive = detail.state === 'playing';
    }

    _abortCurrent() {
        if (this._currentAbort !== null) {
            try { this._currentAbort.abort(); } catch { /* noop */ }
        }
        this._currentAbort = null;
        this._currentTaskId = null;
    }

    /**
     * @param {string} text
     */
    async _sendUserMessage(text) {
        if (this._getContextId) {
            const cid = this._getContextId();
            if (typeof cid === 'string' && cid.trim() !== '') {
                this._contextId = cid.trim();
            }
        }

        this._abortCurrent();
        const ac = new AbortController();
        this._currentAbort = ac;
        this._dispatch('userMessage', { text });

        const onEvent = (ev) => {
            this._handleA2AEvent(ev);
            if (this._onA2aStreamEvent) {
                try {
                    this._onA2aStreamEvent(ev);
                } catch (relayErr) {
                    console.error('[voice-agent-bridge] onA2aStreamEvent', relayErr);
                }
            }
        };

        try {
            if (this._beforeA2aStream) {
                try {
                    await this._beforeA2aStream(text);
                } catch (prepErr) {
                    const e = new Error(prepErr && prepErr.message ? prepErr.message : String(prepErr));
                    throw Object.assign(e, { code: 'voice/bridge/ui_prepare_failed' });
                }
            }
            let metadata = null;
            if (this._getStreamMetadata) {
                try {
                    const raw = await this._getStreamMetadata();
                    if (raw && typeof raw === 'object') {
                        metadata = raw;
                    }
                } catch (metaErr) {
                    const e = new Error(metaErr && metaErr.message ? metaErr.message : String(metaErr));
                    throw Object.assign(e, { code: 'voice/bridge/metadata_failed' });
                }
            }
            await streamEmbedA2A(
                {
                    baseUrl: this._a2aBaseUrl,
                    flowId: this._flowId,
                    embedId: this._embedId,
                    message: text,
                    contextId: this._contextId,
                    branchId: this._branchId,
                    metadata,
                    getHeaders: this._getHeaders,
                    credentials: this._credentials,
                    signal: ac.signal,
                },
                onEvent,
            );
        } catch (err) {
            if (err && err.name === 'AbortError') {
                if (this._pendingA2aAbortDetail) {
                    this._dispatch('a2aAborted', this._pendingA2aAbortDetail);
                    this._pendingA2aAbortDetail = null;
                }
            } else {
                const code =
                    err && typeof err.code === 'string'
                        ? err.code
                        : 'voice/bridge/a2a_failed';
                this._dispatch('error', {
                    code,
                    detail: err && err.message ? err.message : String(err),
                });
            }
        } finally {
            if (this._currentAbort === ac) {
                this._currentAbort = null;
            }
            this._pendingA2aAbortDetail = null;
            this._dispatch('a2aSettled', {});
        }
    }

    /**
     * @param {object} event A2A SSE-событие.
     */
    _handleA2AEvent(event) {
        if (!event || typeof event !== 'object') return;

        const result = event.result;
        if (!result || typeof result !== 'object') return;

        if (typeof result.contextId === 'string' && result.contextId !== '') {
            this._contextId = result.contextId;
        }

        const kind = typeof result.kind === 'string' ? result.kind : '';

        if (kind === 'task') {
            if (typeof result.id === 'string' && result.id !== '') {
                this._currentTaskId = result.id;
            }
            return;
        }

        if (kind === 'artifact-update') {
            if (typeof result.taskId === 'string' && result.taskId !== '') {
                this._currentTaskId = result.taskId;
            }
            return;
        }

        if (kind === 'status-update') {
            if (typeof result.taskId === 'string' && result.taskId !== '') {
                this._currentTaskId = result.taskId;
            }
        }
    }

    /**
     * Кнопка «Стоп» в UI: заглушить TTS и прервать активный A2A fetch + tasks/cancel.
     */
    userStopActiveTurn() {
        this._media.stopPlayback();
        void this._cancelCurrentTask();
    }

    async _cancelCurrentTask() {
        const taskId = this._currentTaskId;
        const detail = {
            task_id: typeof taskId === 'string' && taskId !== '' ? taskId : null,
            context_id:
                typeof this._contextId === 'string' && this._contextId !== '' ? this._contextId : null,
        };
        const hadIncomingFetch = this._currentAbort !== null;
        if (hadIncomingFetch) {
            this._pendingA2aAbortDetail = detail;
        }
        this._abortCurrent();
        if (!hadIncomingFetch) {
            this._dispatch('a2aAborted', detail);
        }
        if (typeof taskId !== 'string' || taskId === '') return;

        const url = this._embedId
            ? `${this._a2aBaseUrl}/api/v1/embed/${encodeURIComponent(this._embedId)}`
            : `${this._a2aBaseUrl}/api/v1/${encodeURIComponent(this._flowId)}`;

        const extraHeaders = await this._getHeaders();
        try {
            await fetch(url, {
                method: 'POST',
                credentials: this._credentials,
                headers: {
                    'Content-Type': 'application/json',
                    ...extraHeaders,
                },
                body: JSON.stringify({
                    jsonrpc: '2.0',
                    id: String(Date.now()),
                    method: 'tasks/cancel',
                    params: { id: taskId },
                }),
            });
        } catch (err) {
            this._dispatch('error', {
                code: 'voice/bridge/cancel_failed',
                detail: err && err.message ? err.message : String(err),
            });
        }
    }

    /**
     * @param {string} type
     * @param {object} detail
     */
    _dispatch(type, detail) {
        this.dispatchEvent(new CustomEvent(type, { detail }));
    }
}
