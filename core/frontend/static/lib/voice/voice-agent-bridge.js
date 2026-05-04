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
 *    текст пользователя; `voice` в A2A не участвует.
 *  - `flows → voice`: читает SSE, для каждого
 *    `TaskArtifactUpdateEvent` с speakable-артефактом
 *    (см. `speakable.js`) вызывает `voice.speak(text,...)`. На
 *    `TaskStatusUpdateEvent{final:true}` — `voice.endUtterance()`.
 *  - Barge-in: `vad{state:"started"}` во время TTS → отменяет
 *    текущий A2A fetch (`AbortController.abort`) и шлёт
 *    `voice.stopPlayback()`. Если в A2A задача уже получила
 *    `taskId`, отправляется ещё и `tasks/cancel` на тот же URL.
 *
 * Инкапсуляция: bridge не знает ни про конкретный UI-компонент, ни
 * про state-store; он общается только через DOM-события
 * `VoiceMediaSession` и публичные DOM-события самого bridge
 * (`userMessage`, `agentText`, `taskFinal`, `bargeIn`, `error`) —
 * чтобы UI мог показывать live transcript/индикаторы без костылей
 * в модулях friend'ах.
 */

import { streamEmbedA2A } from '../embed-chat/embed-a2a-stream.js';
import { extractSpeakableText } from './speakable.js';

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

        /** @type {AbortController|null} */
        this._currentAbort = null;
        /** @type {string|null} */
        this._currentTaskId = null;
        /** @type {boolean} */
        this._ttsActive = false;
        this._started = false;

        this._onTranscript = this._onTranscript.bind(this);
        this._onVad = this._onVad.bind(this);
        this._onTtsState = this._onTtsState.bind(this);
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
    }

    /**
     * Отписаться и отменить текущий A2A-стрим.
     */
    stop() {
        if (!this._started) return;
        this._started = false;
        this._media.removeEventListener('transcript', this._onTranscript);
        this._media.removeEventListener('vad', this._onVad);
        this._media.removeEventListener('ttsState', this._onTtsState);
        this._abortCurrent();
    }

    /**
     * @param {Event} event
     */
    _onTranscript(event) {
        const detail = /** @type {CustomEvent<{text:string, final:boolean}>} */ (event).detail;
        if (!detail || detail.final !== true) return;
        const text = typeof detail.text === 'string' ? detail.text.trim() : '';
        if (text === '') return;
        this._dispatch('userMessage', { text });
        this._sendUserMessage(text);
    }

    /**
     * @param {Event} event
     */
    _onVad(event) {
        const detail = /** @type {CustomEvent<{state:'started'|'ended'}>} */ (event).detail;
        if (!detail) return;
        if (detail.state !== 'started') return;
        if (!this._ttsActive) return;
        this._dispatch('bargeIn', {});
        this._media.stopPlayback();
        this._cancelCurrentTask();
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
        this._abortCurrent();
        const ac = new AbortController();
        this._currentAbort = ac;
        const onEvent = (ev) => this._handleA2AEvent(ev);
        try {
            await streamEmbedA2A(
                {
                    baseUrl: this._a2aBaseUrl,
                    flowId: this._flowId,
                    embedId: this._embedId,
                    message: text,
                    contextId: this._contextId,
                    branchId: this._branchId,
                    getHeaders: this._getHeaders,
                    credentials: this._credentials,
                    signal: ac.signal,
                },
                onEvent,
            );
        } catch (err) {
            if (err && err.name === 'AbortError') {
                return;
            }
            this._dispatch('error', {
                code: 'voice/bridge/a2a_failed',
                detail: err && err.message ? err.message : String(err),
            });
        } finally {
            if (this._currentAbort === ac) {
                this._currentAbort = null;
            }
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
            const text = extractSpeakableText(result);
            if (text === null) return;
            this._dispatch('agentText', {
                text,
                last: result.lastChunk === true,
            });
            this._media.speak(text, { final: result.lastChunk === true });
            return;
        }

        if (kind === 'status-update') {
            if (typeof result.taskId === 'string' && result.taskId !== '') {
                this._currentTaskId = result.taskId;
            }
            if (result.final === true) {
                this._dispatch('taskFinal', {});
                this._media.endUtterance();
            }
        }
    }

    async _cancelCurrentTask() {
        const taskId = this._currentTaskId;
        this._abortCurrent();
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
