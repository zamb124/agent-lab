/**
 * VoiceAgentBridge — тонкий мост между `VoiceMediaSession` (apps/voice WS)
 * и A2A SSE стримом (apps/flows).
 *
 * Сервисы `voice` и `flows` не знают друг про друга: универсальный
 * gateway в одном углу, логика агента в другом. Bridge живёт на
 * клиенте (или в мобильном приложении — тот же контракт) и делает:
 *
 *  - `voice → flows`: на каждое финальное распознавание
 *    (`transcript{final:true}`) отправляет `SendStreamingMessage` в A2A
 *    (`embed/{embed_id}` или `flow/{flow_id}`). Тело A2A сообщения —
 *    текст пользователя; `voice` в A2A не участвует. Нефинальный
 *    текст (`final:false`) копится последним куском; при `stop()` моста
 *    (выключение микрофона) без последующего финала тот же путь отправки
 *    вызывается один раз для коммита в чат. Если финальный transcript уже
 *    запустил `SendStreamingMessage`, пустой `stop()` после снятия эфира **не**
 *    вызывает `AbortController.abort` на этом fetch (иначе UI успевает показать
 *    сообщение пользователя из `beforeA2aStream`, а ответ гаснет).
 *  - Авто-TTS из ответа обрабатывается отдельно: потребитель SSE-кадров
 *    (фабрика flows A2A или `<platform-flow-ui>`) вызывает
 *    `feedStreamTtsFromA2aResult` (registry — `stream-tts-registry.js`, см. `voice.mdc`).
 *  - Barge-in: `vad` с непрерывной речью ≥ ~0,3 s (как порог на шлюзе)
 *    во время TTS **или** пока живёт A2A fetch (фаза SSE до первого TTS) →
 *    `voice.stopPlayback()`, `AbortController.abort`, при наличии `taskId` —
 *    `CancelTask`. Учитывается и локальная очередь Web Audio (`hasScheduledTtsPlayback`):
 *    сервер может прислать `tts_state: stopped` до конца воспроизведения буфера на клиенте. DOM `a2aAborted`: при оборванном SSE — из `catch (AbortError)`
 *    после установки `_pendingA2aAbortDetail`; если fetch уже закрыт (например, только TTS) —
 *    сразу из `_cancelCurrentTask`. Payload: `task_id`/`context_id` для сброса `flows/chat`.
 *  - `a2aSettled`: только если `finally` того же инвока `_sendUserMessage` (`_sendSeq`);
 *    иначе суперсессия вторым финальным STT не триггерит `finalize` embed по старому fetch.
 *
 * Инкапсуляция: bridge не знает ни про конкретный UI-компонент, ни
 * про state-store; он общается только через DOM-события
 * `VoiceMediaSession` и публичные DOM-события самого bridge
 * (`userMessage`, `bargeIn`, `a2aAborted`, `a2aSettled`, `error`) —
 * чтобы UI мог показывать live transcript/индикаторы без костылей
 * в модулях friend'ах.
 */

import {
    a2aEndpointUrl,
    a2aRequestHeaders,
    buildCancelTaskBody,
    buildSendMessageBody,
    buildUserMessage,
} from '../a2a/a2a-codec.js';
import { consumeA2AStream, unwrapA2aStreamResult } from '../a2a/a2a-stream.js';
import { devtoolsLog, isPlatformDevtoolsEnabled } from '../events/devtools.js';
import { isPlainRecord } from '../events/payload.js';

function customRecord(event: Event): Record<string, unknown> | null {
    if (!(event instanceof CustomEvent) || !isPlainRecord(event.detail)) return null;
    return event.detail;
}

function streamVariables(metadata: Record<string, unknown> | null): Record<string, unknown> | null {
    if (metadata === null || !('variables' in metadata)) return null;
    const variables = metadata.variables;
    if (variables === null) return null;
    if (!isPlainRecord(variables)) {
        throw new Error('voice-agent-bridge: stream metadata.variables must be an object');
    }
    return variables;
}

function bridgeErrorCode(err: unknown): string {
    if (isPlainRecord(err) && typeof err.code === 'string') return err.code;
    return 'voice/bridge/a2a_failed';
}

/** Минимальная длительность сегмента речи (VAD open) до client barge-in, мс — как `vad_speech_seconds < 0.3` в `BargeInController`. */
const CLIENT_BARGE_MIN_SPEECH_MS = 300;

import type { VoiceMediaSession } from './voice-media-session.js';

export interface VoiceAgentBridgeOptions {
    mediaSession: VoiceMediaSession;
    /** origin + префикс flows (`https://host/flows`), без завершающего "/" */
    a2aBaseUrl: string;
    /** id flow; альтернатива `embedId` */
    flowId?: string | undefined;
    /** id embed; альтернатива `flowId` */
    embedId?: string | undefined;
    branchId?: string | null;
    getHeaders?: () => Promise<Record<string, string>>;
    credentials?: RequestCredentials;
    initialContextId?: string | null;
    /** перед каждым SendStreamingMessage подставляется актуальный contextId из UI (например `<platform-flow-ui>`) */
    getContextId?: () => string | null | undefined;
    /** metadata для A2A (как у текстовой отправки: variables и т.д.) */
    getStreamMetadata?: () => Promise<Record<string, unknown> | null | undefined>;
    /** перед fetch (например добавить user/assistant пузыри в чат) */
    beforeA2aStream?: (text: string) => Promise<void>;
    /** каждый SSE-кадр для UI; потребитель вызывает релей/reducer и там же `feedStreamTtsFromA2aResult`. Сам `VoiceAgentBridge` авто-TTS не вызывает. */
    onA2aStreamEvent?: (event: object) => void;
}

export class VoiceAgentBridge extends EventTarget {
    private _media: VoiceMediaSession;
    private _a2aBaseUrl: string;
    private _flowId: string | undefined;
    private _embedId: string | undefined;
    private _branchId: string | null;
    private _getHeaders: () => Promise<Record<string, string>>;
    private _credentials: RequestCredentials;
    private _contextId: string | null;
    private _getContextId: (() => string | null | undefined) | null;
    private _getStreamMetadata: (() => Promise<Record<string, unknown> | null | undefined>) | null;
    private _beforeA2aStream: ((text: string) => Promise<void>) | null;
    private _onA2aStreamEvent: ((event: object) => void) | null;
    private _currentAbort: AbortController | null;
    private _currentTaskId: string | null;
    private _ttsActive: boolean;
    private _clientBargeTimer: ReturnType<typeof setTimeout> | null;
    private _vadSpeechSegmentOpen: boolean;
    /** Перед `abort` сохраняем метаданные; в `catch (AbortError)` шлём `a2aAborted` один раз. */
    private _pendingA2aAbortDetail: { task_id: string | null; context_id: string | null } | null;
    private _started: boolean;
    /** Инкремент на каждый `_sendUserMessage`; `a2aSettled` только если `finally` того же инвока (не суперсессия). */
    private _sendSeq: number;
    /** последний нефинальный STT-текст; при `stop()` без финала уходит в A2A один раз */
    private _pendingPartialTranscript: string;

    constructor(options: VoiceAgentBridgeOptions) {
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

        this._currentAbort = null;
        this._currentTaskId = null;
        this._ttsActive = false;
        this._clientBargeTimer = null;
        this._vadSpeechSegmentOpen = false;
        this._pendingA2aAbortDetail = null;
        this._started = false;
        this._sendSeq = 0;
        this._pendingPartialTranscript = '';

        this._onTranscript = this._onTranscript.bind(this);
        this._onVad = this._onVad.bind(this);
        this._onTtsState = this._onTtsState.bind(this);
        this._onVoiceDiagnostic = this._onVoiceDiagnostic.bind(this);
    }

    get contextId(): string | null { return this._contextId; }

    /**
     * Подписаться на события voice.
     */
    start(): void {
        if (this._started) return;
        this._started = true;
        this._media.addEventListener('transcript', this._onTranscript);
        this._media.addEventListener('vad', this._onVad);
        this._media.addEventListener('ttsState', this._onTtsState);
        this._media.addEventListener('diagnostic', this._onVoiceDiagnostic);
    }

    private _onVoiceDiagnostic(event: Event): void {
        if (!isPlatformDevtoolsEnabled()) {
            return;
        }
        const detail = customRecord(event);
        devtoolsLog('voice-agent-bridge', 'diagnostic', detail === null ? {} : detail);
    }

    /**
     * Отписаться от событий voice и при наличии — отправить последний partial.
     * Активный fetch `SendStreamingMessage`, уже запущенный после `transcript{final:true}`,
     * не отменять: отмена — через barge-in / `CancelTask`.
     */
    stop(): void {
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

    private _clearClientBargeDebounce(): void {
        if (this._clientBargeTimer !== null) {
            clearTimeout(this._clientBargeTimer);
            this._clientBargeTimer = null;
        }
        this._vadSpeechSegmentOpen = false;
    }

    private _isClientBargeInScope(): boolean {
        if (this._ttsActive === true || this._currentAbort !== null) {
            return true;
        }
        if (typeof this._media.hasScheduledTtsPlayback === 'function') {
            return this._media.hasScheduledTtsPlayback();
        }
        return false;
    }

    /**
     * Срабатывание после дебаунса по длительности речи (см. `CLIENT_BARGE_MIN_SPEECH_MS`).
     */
    private _executeClientBargeIn(): void {
        this._clientBargeTimer = null;
        if (!this._vadSpeechSegmentOpen) return;
        if (!this._isClientBargeInScope()) return;
        this._dispatch('bargeIn', {});
        this._media.stopPlayback();
        void this._cancelCurrentTask();
    }

    private _onTranscript(event: Event): void {
        const detail = customRecord(event);
        if (detail === null) return;
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

    private _onVad(event: Event): void {
        const detail = customRecord(event);
        if (detail === null || typeof detail.state !== 'string') return;
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

    private _onTtsState(event: Event): void {
        const detail = customRecord(event);
        if (detail === null) return;
        this._ttsActive = detail.state === 'playing';
    }

    private _abortCurrent(): void {
        if (this._currentAbort !== null) {
            this._currentAbort.abort();
        }
        this._currentAbort = null;
        this._currentTaskId = null;
    }

    private async _sendUserMessage(text: string): Promise<void> {
        if (this._getContextId) {
            const cid = this._getContextId();
            if (typeof cid === 'string' && cid.trim() !== '') {
                this._contextId = cid.trim();
            }
        }

        this._abortCurrent();
        const mySeq = ++this._sendSeq;
        const ac = new AbortController();
        this._currentAbort = ac;
        this._dispatch('userMessage', { text });

        const onEvent = (ev: unknown) => {
            const frame = ev as object;
            this._handleA2AEvent(frame);
            if (this._onA2aStreamEvent) {
                this._onA2aStreamEvent(frame);
            }
        };

        try {
            if (this._beforeA2aStream) {
                try {
                    await this._beforeA2aStream(text);
                } catch (prepErr) {
                    const e = new Error(prepErr instanceof Error && prepErr.message ? prepErr.message : String(prepErr));
                    throw Object.assign(e, { code: 'voice/bridge/ui_prepare_failed' });
                }
            }
            let metadata: Record<string, unknown> | null = null;
            if (this._getStreamMetadata) {
                try {
                    const raw = await this._getStreamMetadata();
                    if (raw && typeof raw === 'object') {
                        metadata = raw;
                    }
                } catch (metaErr) {
                    const e = new Error(metaErr instanceof Error && metaErr.message ? metaErr.message : String(metaErr));
                    throw Object.assign(e, { code: 'voice/bridge/metadata_failed' });
                }
            }
            const extraHeaders = await this._getHeaders();
            await consumeA2AStream(
                {
                    url: a2aEndpointUrl({
                        baseUrl: this._a2aBaseUrl,
                        flowId: this._flowId,
                        embedId: this._embedId,
                    }),
                    body: buildSendMessageBody(buildUserMessage({ contextId: this._contextId, text }), {
                        branchId: this._branchId ?? 'default',
                        variables: streamVariables(metadata),
                    }),
                    headers: extraHeaders,
                    credentials: this._credentials,
                    signal: ac.signal,
                },
                onEvent,
            );
        } catch (err) {
            if (err instanceof Error && err.name === 'AbortError') {
                if (this._pendingA2aAbortDetail) {
                    this._dispatch('a2aAborted', this._pendingA2aAbortDetail);
                    this._pendingA2aAbortDetail = null;
                }
            } else {
                const code = bridgeErrorCode(err);
                this._dispatch('error', {
                    code,
                    detail: err instanceof Error && err.message ? err.message : String(err),
                });
            }
        } finally {
            if (this._currentAbort === ac) {
                this._currentAbort = null;
            }
            this._pendingA2aAbortDetail = null;
            if (this._sendSeq === mySeq) {
                this._dispatch('a2aSettled', {});
            }
        }
    }

    private _handleA2AEvent(event: object): void {
        if (!isPlainRecord(event)) return;

        const result = event.result;
        if (!isPlainRecord(result)) return;

        const unwrapped = unwrapA2aStreamResult(result);
        if (!unwrapped) {
            return;
        }
        const payload = unwrapped.event;

        if (typeof payload.contextId === 'string' && payload.contextId !== '') {
            this._contextId = payload.contextId;
        }

        if (unwrapped.frameKind === 'task') {
            if (typeof payload.id === 'string' && payload.id !== '') {
                this._currentTaskId = payload.id;
            }
            return;
        }

        if (typeof payload.taskId === 'string' && payload.taskId !== '') {
            this._currentTaskId = payload.taskId;
        }
    }

    /**
     * Кнопка «Стоп» в UI: заглушить TTS и прервать активный A2A fetch + CancelTask.
     */
    userStopActiveTurn(): void {
        this._media.stopPlayback();
        void this._cancelCurrentTask();
    }

    private async _cancelCurrentTask(): Promise<void> {
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

        const url = a2aEndpointUrl({
            baseUrl: this._a2aBaseUrl,
            flowId: this._flowId,
            embedId: this._embedId,
        });

        const extraHeaders = await this._getHeaders();
        try {
            await fetch(url, {
                method: 'POST',
                credentials: this._credentials,
                headers: a2aRequestHeaders(extraHeaders),
                body: JSON.stringify(buildCancelTaskBody(taskId)),
            });
        } catch (err) {
            this._dispatch('error', {
                code: 'voice/bridge/cancel_failed',
                detail: err instanceof Error && err.message ? err.message : String(err),
            });
        }
    }

    private _dispatch(type: string, detail: object): void {
        this.dispatchEvent(new CustomEvent(type, { detail }));
    }
}
