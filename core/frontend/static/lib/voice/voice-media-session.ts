/**
 * VoiceMediaSession — универсальный media-клиент для `apps/voice` WS.
 *
 * Не знает про A2A, Flows, embed или чат-UI. Делает ровно три вещи:
 *
 *  1. Держит WS `/voice/api/ws/session/{id}` и отправляет PCM 16 kHz mono s16le
 *     через один граф **Web Audio** (`MediaStream` → **AudioWorklet** `voice-mic-capture` →
 *     при недоступном worklet — **ScriptProcessorNode**, иначе **AnalyserNode** + pump).
 *     Тот же порядок фиксируется **один раз** при `startRecording`; альтернативного тракта захвата
 *     во время сессии нет. Флаг **`_recording`** до сборки графа.
 *     Тихий oscillator; таймер **`~140 ms`** и **`onstatechange`** поднимают контекст из `suspended`/`interrupted`.
 *  2. Принимает от voice text-frames (`transcript`, `vad`, `tts_state`,
 *     `error`, `ping`, `media_config`) и диспатчит как DOM `CustomEvent`.
 *  3. Принимает от voice binary-кадры и воспроизводит их через
 *     `AudioContext` (raw PCM L16 или WAV).
 *
 * Мост A2A ↔ voice делает отдельный модуль `voice-agent-bridge.js`.
 * Для мобильного приложения свой native-клиент по тому же WS-контракту.
 *
 * Контракт WS-фреймов задокументирован в `.cursor/rules/voice.mdc` и
 * `apps/voice/services/voice_client_channel.py`.
 */

import { getUserMediaCompat, hasGetUserMediaApi } from '../utils/voice-recording.js';

declare global {
    interface Window {
        webkitAudioContext?: typeof AudioContext;
    }
}
import { devtoolsLog, isPlatformDevtoolsEnabled } from '../events/devtools.js';

function sampleAt(values: ArrayLike<number>, index: number): number {
    const value = values[index];
    if (value === undefined) {
        throw new Error(`voice sample ${index} missing`);
    }
    return value;
}

/**
 * Один JSON `speak` с текстом длиннее лимита часто рвётся на прокси/WebSocket (типично 64k–1M).
 * A2A SSE шлёт серию коротких апдейтов — там проблема не проявляется; один финальный длинный кадр — да.
 */
const VOICE_WS_SPEAK_TEXT_CHUNK_MAX = 6000;

/**
 * Hostname'ы dev-оригина, где пробуем mic/WebAudio при HTTP (isSecureContext=false):
 * поддомены lvh.me, localhost, 127.0.0.1. Иначе Chromium не отдаёт getUserMedia — см. startRecording.
 *
 * @param {string} hostname
 * @returns {boolean}
 */
function isDevVoiceInsecureHost(hostname: string): boolean {
    if (typeof hostname !== 'string' || hostname === '') {
        return false;
    }
    const h = hostname.toLowerCase();
    if (h === 'localhost' || h === '127.0.0.1' || h === 'lvh.me') {
        return true;
    }
    if (h.endsWith('.localhost')) {
        return true;
    }
    if (h.endsWith('.lvh.me')) {
        return true;
    }
    return false;
}

/** Диагностика сессии идёт через общий флаг `?platform_devtools=1`. */
function _voiceClientDebug(message: string, payload?: unknown): void {
    devtoolsLog('voice-media', message, payload);
}

export const VOICE_CAPTURE_SAMPLE_RATE = 16000;

/** `resume()` нужен только остановленному контексту: у закрытого он отклоняется. */
async function resumeIfNotRunning(ctx: AudioContext): Promise<void> {
    if (ctx.state === 'running' || ctx.state === 'closed') {
        return;
    }
    await ctx.resume();
}

/** WS-кадр uplink: PCM s16le mono, 320 сэмплов = 640 байт = 20 ms @ 16 kHz.
 *  Совпадает с серверным `_FRAME_DURATION_S = 0.02` в `apps/voice/workers/stt_worker.py`. */
export const VOICE_OUTBOUND_FRAME_SAMPLES = 320;

/** Длина FIR low-pass перед децимацией (нечётная, 31 даёт ~1.9 ms задержки
 *  при 16 kHz). Подавляет диапазон выше 7.5 kHz, чтобы при downsample 48→16 kHz
 *  не появлялись alias-шумы, искажающие распознавание STT (свистящие согласные). */
const VOICE_FIR_TAPS = 31;
/** Cutoff в Hz: 7.5 kHz < Nyquist 8 kHz (16 kHz / 2). */
const VOICE_FIR_CUTOFF_HZ = 7500;

/** Размер буфера ScriptProcessorNode (степень двойки в допустимом диапазоне). */
const MIC_SCRIPT_PROCESSOR_BUFFER_SIZE = 4096;
/** Интервал опроса AnalyserNode (если доступен только analyser-путь захвата). */
const MIC_CAPTURE_PUMP_MS = 20;
/** fftSize временной волны (AnalyserNode). */
const MIC_CAPTURE_FFT_SIZE = 2048;

/**
 * Спроектировать FIR low-pass (Hamming-windowed sinc) с DC gain = 1.
 *
 * @param {number} numTaps — нечётное, типично 31
 * @param {number} fcNorm — cutoff / sampleRate, диапазон (0, 0.5)
 * @returns {Float32Array}
 */
export function designFirLowpassHamming(numTaps: number, fcNorm: number): Float32Array {
    if (!Number.isInteger(numTaps) || numTaps <= 1 || numTaps % 2 === 0) {
        throw new Error('designFirLowpassHamming: numTaps должно быть нечётным >= 3');
    }
    if (!(fcNorm > 0) || !(fcNorm < 0.5)) {
        throw new Error('designFirLowpassHamming: fcNorm должно быть в (0, 0.5)');
    }
    const N = numTaps;
    const M = N - 1;
    const taps = new Float32Array(N);
    for (let n = 0; n < N; n++) {
        const m = n - M / 2;
        let h;
        if (m === 0) {
            h = 2 * fcNorm;
        } else {
            h = Math.sin(2 * Math.PI * fcNorm * m) / (Math.PI * m);
        }
        const w = 0.54 - 0.46 * Math.cos((2 * Math.PI * n) / M);
        taps[n] = h * w;
    }
    let sum = 0;
    for (let i = 0; i < N; i++) sum += sampleAt(taps, i);
    if (sum !== 0) {
        const inv = 1 / sum;
        for (let i = 0; i < N; i++) taps[i] = sampleAt(taps, i) * inv;
    }
    return taps;
}

/**
 * Применить FIR-фильтр к чанку Float32 семплов с непрерывной историей предыдущих
 * вызовов (для гладкости на границах батчей). `firHistory` обновляется in-place.
 *
 * @param {Float32Array} chunk
 * @param {Float32Array} firTaps
 * @param {Float32Array} firHistory — длина `firTaps.length - 1`
 * @returns {Float32Array} отфильтрованный чанк той же длины
 */
export function applyFirToFloat(chunk: Float32Array, firTaps: Float32Array, firHistory: Float32Array): Float32Array {
    const M = firTaps.length;
    if (firHistory.length !== M - 1) {
        throw new Error(
            `applyFirToFloat: firHistory.length=${firHistory.length} ожидалось ${M - 1}`,
        );
    }
    const N = chunk.length;
    const out = new Float32Array(N);
    const ext = new Float32Array(M - 1 + N);
    ext.set(firHistory);
    ext.set(chunk, M - 1);
    for (let i = 0; i < N; i++) {
        let acc = 0;
        const base = i + (M - 1);
        for (let k = 0; k < M; k++) {
            acc += sampleAt(firTaps, k) * sampleAt(ext, base - k);
        }
        out[i] = acc;
    }
    firHistory.set(ext.subarray(N));
    return out;
}

function floatSampleToInt16(sample: number): number {
    const s = Math.max(-1, Math.min(1, sample));
    const v = s < 0 ? s * 0x8000 : s * 0x7fff;
    return v | 0;
}

/**
 * @param {Float32Array} channel
 * @returns {ArrayBuffer}
 */
function floatMonoToPcm16ArrayBufferDirect(channel: Float32Array): ArrayBuffer {
    const pcm = new Int16Array(channel.length);
    for (let i = 0; i < channel.length; i++) {
        pcm[i] = floatSampleToInt16(sampleAt(channel, i));
    }
    return pcm.buffer;
}

/**
 * Накопить новый PCM-чанк к остатку и вернуть массив целых outbound-кадров
 * (`VOICE_OUTBOUND_FRAME_SAMPLES = 320` int16 → 640 байт = 20 ms @ 16 kHz),
 * сохранив остаток в `tailState.tail` для следующего вызова.
 *
 * Серверный `stt_worker` ожидает фреймы 20 ms (`_FRAME_DURATION_S`); большие
 * пакеты (например 256 ms батч worklet'а) ломают VAD-детекцию и приводят к
 * рассинхрону окна STT и фактической паузы пользователя.
 *
 * @param {ArrayBuffer} chunkBuffer — int16 PCM mono 16 kHz
 * @param {{ tail: Int16Array }} tailState
 * @returns {ArrayBuffer[]}
 */
export function spliceIntoOutboundFrames(chunkBuffer: ArrayBuffer, tailState: SpliceTailState): ArrayBuffer[] {
    if (!(chunkBuffer instanceof ArrayBuffer)) {
        throw new Error('spliceIntoOutboundFrames: chunkBuffer должен быть ArrayBuffer');
    }
    if (!(tailState.tail instanceof Int16Array)) {
        throw new Error('spliceIntoOutboundFrames: tailState.tail должен быть Int16Array');
    }
    const incoming = new Int16Array(chunkBuffer);
    if (incoming.length === 0 && tailState.tail.length === 0) {
        return [];
    }
    const total = tailState.tail.length + incoming.length;
    if (total < VOICE_OUTBOUND_FRAME_SAMPLES) {
        const merged = new Int16Array(total);
        merged.set(tailState.tail);
        merged.set(incoming, tailState.tail.length);
        tailState.tail = merged;
        return [];
    }
    const merged = new Int16Array(total);
    merged.set(tailState.tail);
    merged.set(incoming, tailState.tail.length);
    const fullFrames = Math.floor(total / VOICE_OUTBOUND_FRAME_SAMPLES);
    const frames: ArrayBuffer[] = [];
    for (let i = 0; i < fullFrames; i++) {
        const start = i * VOICE_OUTBOUND_FRAME_SAMPLES;
        const slice = merged.slice(start, start + VOICE_OUTBOUND_FRAME_SAMPLES);
        frames.push(slice.buffer);
    }
    const remaining = total - fullFrames * VOICE_OUTBOUND_FRAME_SAMPLES;
    if (remaining > 0) {
        tailState.tail = merged.slice(fullFrames * VOICE_OUTBOUND_FRAME_SAMPLES);
    } else {
        tailState.tail = new Int16Array(0);
    }
    return frames;
}

/**
 * Downsample входного потока (например 48→16 kHz) с линейной интерполяцией между сэмплами.
 *
 * Перед децимацией к каждому новому чанку применяется FIR low-pass
 * (`designFirLowpassHamming(31, 7500/inRate)`), чтобы подавить компоненты выше
 * 7.5 kHz и не получить alias-шумы после downsample. Состояние FIR (`firTaps`,
 * `firHistory`) хранится в `state` и пересчитывается, если меняется `inRate`.
 *
 * После каждого вызова `merged = tail concat filtered_chunk`, при этом `merged[0]`
 * соответствует входному сэмплу с глобальным индексом **`state.inputBase`**.
 * Выходной счётчик **`nextOutSampleIndex`** задаёт время в шкале частоты 16 kHz.
 *
 * Без **`inputBase`** индекс `floor(nextOutSampleIndex * ratio)` ошибочно читают как оффсет
 * в `merged`: после первого чанка `merged` короче очередной глобальной позиции — цикл даёт `totalLen===0`,
 * uplink PCM обрывается после первого пакета.
 *
 * @param {Float32Array} channel
 * @param {number} inRate
 * @param {{ tail: Float32Array, nextOutSampleIndex: number, inputBase: number,
 *          firTaps?: Float32Array, firHistory?: Float32Array, firInputRate?: number }} state
 * @returns {ArrayBuffer|null}
 */
export function resampleMonoToPcm16ArrayBuffer(channel: Float32Array, inRate: number, state: ResamplerState): ArrayBuffer | null {
    if (!channel || channel.length === 0) {
        return null;
    }
    if (!(inRate > 0)) {
        return null;
    }

    let working = channel;
    if (inRate > VOICE_CAPTURE_SAMPLE_RATE) {
        if (
            state.firTaps === undefined
            || state.firHistory === undefined
            || state.firInputRate !== inRate
        ) {
            const fcNorm = VOICE_FIR_CUTOFF_HZ / inRate;
            state.firTaps = designFirLowpassHamming(VOICE_FIR_TAPS, fcNorm);
            state.firHistory = new Float32Array(VOICE_FIR_TAPS - 1);
            state.firInputRate = inRate;
        }
        working = applyFirToFloat(channel, state.firTaps, state.firHistory);
    }

    const mergedLen = state.tail.length + working.length;
    const merged = new Float32Array(mergedLen);
    merged.set(state.tail);
    merged.set(working, state.tail.length);
    const ratio = inRate / VOICE_CAPTURE_SAMPLE_RATE;
    const pcmParts = [];
    while (true) {
        const inPosGlobal = state.nextOutSampleIndex * ratio;
        const fp = inPosGlobal - state.inputBase;
        const i0 = Math.floor(fp);
        const i1 = i0 + 1;
        if (i1 >= merged.length) {
            break;
        }
        const frac = fp - i0;
        const s = sampleAt(merged, i0) * (1 - frac) + sampleAt(merged, i1) * frac;
        pcmParts.push(floatSampleToInt16(s));
        state.nextOutSampleIndex += 1;
    }
    const keepFloat = Math.floor(state.nextOutSampleIndex * ratio);
    const keepTailGlobal = keepFloat > 0 ? keepFloat - 1 : 0;
    const sliceStart = keepTailGlobal - state.inputBase;
    if (sliceStart >= merged.length) {
        state.tail = new Float32Array(0);
        state.inputBase += merged.length;
    } else {
        const keepFromIdx = sliceStart <= 0 ? 0 : sliceStart;
        state.tail = merged.slice(keepFromIdx);
        if (keepFromIdx > 0) {
            state.inputBase = keepTailGlobal;
        }
    }
    const totalLen = pcmParts.length;
    if (totalLen === 0) {
        return null;
    }
    const pcm = new Int16Array(totalLen);
    for (let i = 0; i < totalLen; i++) {
        pcm[i] = sampleAt(pcmParts, i);
    }
    return pcm.buffer;
}

/**
 * @typedef {object} VoiceMediaSessionOptions
 * @property {string} baseUrl - ws origin + опциональный prefix без завершающего "/"; например "wss://host/voice"
 * @property {string} sessionId - уникальный id WS-сессии
 * @property {string} companyId - активная компания пользователя
 * @property {Object<string,string>} [query] - дополнительные query-параметры (stt_provider_name, tts_voice, language и т.д.)
 * @property {boolean} [autoRecord=true] - начать захват микрофона сразу после connect
 */

/**
 * @typedef {object} VoiceMediaSessionEventsMap
 * @property {{ text: string, final: boolean, language?: string }} transcript
 * @property {{ state: 'started'|'ended' }} vad
 * @property {{ state: 'playing'|'stopped' }} ttsState
 * @property {{ mime: string, sampleRate: number, channels: number }} mediaConfig
 * @property {{ code: string, detail: string }} error
 * @property {{ code: number, reason: string }} closed
 * @property {Record<string, never>} recordingФиналized — ответ сервера на ``end_recording`` (``finalize_done``)
 */

export interface VoiceMediaSessionOptions {
    baseUrl: string;
    sessionId: string;
    companyId: string;
    query?: Record<string, string>;
    autoRecord?: boolean;
}

export interface VoiceTranscriptDetail {
    final?: boolean;
    text?: string;
    [key: string]: unknown;
}

export interface SpliceTailState {
    tail: Int16Array;
}

export interface ResamplerState {
    tail: Float32Array;
    nextOutSampleIndex: number;
    inputBase: number;
    firTaps?: Float32Array;
    firHistory?: Float32Array;
    firInputRate?: number;
}

type VoiceUplinkPath = 'none' | 'ac_worklet' | 'ac_script' | 'ac_analyser';

export class VoiceMediaSession extends EventTarget {
    private _baseUrl: string;
    private _sessionId: string;
    private _companyId: string;
    private _extraQuery: Record<string, string>;
    private _autoRecord: boolean;
    private _ws: WebSocket | null;
    private _mediaConfig: { mime: string; sampleRate: number; channels: number };
    private _mediaStream: MediaStream | null;
    private _captureCtx: AudioContext | null;
    private _captureAnalyser: AnalyserNode | null;
    private _captureWorkletNode: AudioWorkletNode | null;
    private _captureScriptProcessor: ScriptProcessorNode | null;
    private _capturePumpTimer: ReturnType<typeof setTimeout> | null;
    private _mutedTrackDiagnosticTimer: ReturnType<typeof setTimeout> | null;
    private _captureResumeWatchdog: ReturnType<typeof setInterval> | null;
    private _captureVisibilityHandler: (() => void) | null;
    private _captureKeepAliveOsc: OscillatorNode | null;
    private _captureKeepAliveGain: GainNode | null;
    private _captureResamplerState: ResamplerState | null;
    /** Хранит остаток < 320 семплов между ресемплами для построения 20 ms-кадров. */
    private _outboundFrameTail: SpliceTailState;
    /** mute sink: тянуть граф к destination без эха на колонках */
    private _captureSinkGain: GainNode | null;
    private _recording: boolean;
    private _playbackCtx: AudioContext | null;
    private _playbackCursor: number;
    /** Очередь TTS binary: decode+schedule строго по порядку прихода WS-кадров (без гонок). */
    private _playbackQueue: Promise<void>;
    /** Число binary-кадров, ещё не завершивших `_playAudioChunkSequential` (беклог декода/планирования). */
    private _playbackChunksInFlight: number;
    private _closed: boolean;
    private _openPromise: Promise<void> | null;
    /** Очередь PCM до OPEN (CONNECTING); иначе pump шлёт, пока сокет не OPEN — теряются. */
    private _pcmOutboundQueue: ArrayBuffer[];
    private _pcmOutboundQueueCap: number;
    /** Очередь JSON (`speak`, `end_of_utterance`, …) до OPEN — иначе первые чанки TTS теряются. */
    private _textOutboundQueue: Record<string, unknown>[];
    private _textOutboundQueueCap: number;
    /** Живой путь uplink (только диагностика). */
    private _voiceUplinkPath: VoiceUplinkPath;
    private _pcmUplinkDebugCount: number;
    /** только при platform_devtools — сколько раз worklet прислал полный Float32-батч. */
    private _captureWorkletBatchRecv: number;
    /** platform_devtools — encode вернул не ArrayBuffer после worklet-батча. */
    private _pcmEncodeMissCount: number;
    private _wsJsonDebugSeq: number;
    private _wsInBinaryDebugSeq: number;

    constructor(options: VoiceMediaSessionOptions) {
        super();
        if (!options || typeof options !== 'object') {
            throw new Error('VoiceMediaSession: options required');
        }
        if (typeof options.baseUrl !== 'string' || options.baseUrl === '') {
            throw new Error('VoiceMediaSession: baseUrl required');
        }
        if (typeof options.sessionId !== 'string' || options.sessionId === '') {
            throw new Error('VoiceMediaSession: sessionId required');
        }
        if (typeof options.companyId !== 'string' || options.companyId === '') {
            throw new Error('VoiceMediaSession: companyId required');
        }
        this._baseUrl = options.baseUrl.replace(/\/$/, '');
        this._sessionId = options.sessionId;
        this._companyId = options.companyId;
        this._extraQuery = options.query && typeof options.query === 'object' ? { ...options.query } : {};
        this._autoRecord = options.autoRecord !== false;

        /** @type {WebSocket|null} */
        this._ws = null;
        this._mediaConfig = { mime: 'audio/L16', sampleRate: 16000, channels: 1 };
        this._mediaStream = null;
        /** @type {AudioContext|null} */
        this._captureCtx = null;
        /** @type {AnalyserNode|null} */
        this._captureAnalyser = null;
        /** @type {AudioWorkletNode|null} */
        this._captureWorkletNode = null;
        /** @type {ScriptProcessorNode|null} */
        this._captureScriptProcessor = null;
        /** @type {ReturnType<typeof setTimeout>|null} */
        this._capturePumpTimer = null;
        /** @type {ReturnType<typeof setTimeout>|null} */
        this._mutedTrackDiagnosticTimer = null;
        /** @type {ReturnType<typeof setInterval>|null} */
        this._captureResumeWatchdog = null;
        /** @type {(() => void)|null} */
        this._captureVisibilityHandler = null;
        /** @type {OscillatorNode|null} */
        this._captureKeepAliveOsc = null;
        /** @type {GainNode|null} */
        this._captureKeepAliveGain = null;
        /** @type {{ tail: Float32Array, nextOutSampleIndex: number, inputBase: number,
         *           firTaps?: Float32Array, firHistory?: Float32Array, firInputRate?: number }|null} */
        this._captureResamplerState = null;
        /** Хранит остаток < 320 семплов между ресемплами для построения 20 ms-кадров. */
        this._outboundFrameTail = { tail: new Int16Array(0) };
        /** @type {GainNode|null} — mute sink: тянуть граф к destination без эха на колонках */
        this._captureSinkGain = null;
        this._recording = false;

        /** @type {AudioContext|null} */
        this._playbackCtx = null;
        this._playbackCursor = 0;
        /** Очередь TTS binary: decode+schedule строго по порядку прихода WS-кадров (без гонок). */
        this._playbackQueue = Promise.resolve();
        /** Число binary-кадров, ещё не завершивших `_playAudioChunkSequential` (беклог декода/планирования). */
        this._playbackChunksInFlight = 0;

        this._closed = false;
        this._openPromise = null;
        /** Очередь PCM до OPEN (CONNECTING); иначе pump шлёт, пока сокет не OPEN — теряются. */
        this._pcmOutboundQueue = [];
        this._pcmOutboundQueueCap = 200;
        /** Очередь JSON (`speak`, `end_of_utterance`, …) до OPEN — иначе первые чанки TTS теряются. */
        this._textOutboundQueue = [];
        this._textOutboundQueueCap = 64;
        /** Живой путь uplink (только диагностика). */
        this._voiceUplinkPath = /** @type {'none'|'ac_worklet'|'ac_script'|'ac_analyser'} */ ('none');
        this._pcmUplinkDebugCount = 0;
        /** @type {number} только при platform_devtools — сколько раз worklet прислал полный Float32-батч. */
        this._captureWorkletBatchRecv = 0;
        /** @type {number} platform_devtools — encode вернул не ArrayBuffer после worklet-батча. */
        this._pcmEncodeMissCount = 0;
        this._wsJsonDebugSeq = 0;
        this._wsInBinaryDebugSeq = 0;
    }

    /** @returns {string} */
    get sessionId() { return this._sessionId; }

    /** @returns {boolean} */
    get isConnected() {
        return this._ws !== null && this._ws.readyState === WebSocket.OPEN;
    }

    /** @returns {boolean} */
    get isRecording() { return this._recording; }

    /**
     * @returns {Promise<void>}
     */
    async connect() {
        if (this._closed) {
            throw new Error('VoiceMediaSession: already closed');
        }
        if (this._openPromise) {
            return this._openPromise;
        }
        this._openPromise = this._doConnect();
        try {
            await this._openPromise;
        } catch (err) {
            this._openPromise = null;
            throw err;
        }
    }

    async _doConnect() {
        const url = this._buildWsUrl();
        _voiceClientDebug('ws_connecting', { session_id: this._sessionId, url });
        const ws = new WebSocket(url);
        ws.binaryType = 'arraybuffer';
        this._ws = ws;

        ws.addEventListener('message', (event) => this._handleWsMessage(event));
        ws.addEventListener('close', (event) => this._handleWsClose(event));
        ws.addEventListener('open', () => {
            this._flushPcmOutboundQueue();
            this._flushTextOutboundQueue();
        });

        const openPromise = new Promise((resolve, reject) => {
            ws.addEventListener('open', () => resolve(undefined), { once: true });
            ws.addEventListener(
                'error',
                () => {
                    reject(
                        new Error(
                            `voice/ws/connect_failed url=${url} ` +
                                '(проверьте сервис voice на :8015 и `make app`; в dev WS /voice проксируется с того же Host, первый сегмент пути `voice`).',
                        ),
                    );
                },
                { once: true },
            );
        });

        /** Сначала mic+AudioContext (ближе к user gesture), затем ждём OPEN. Иначе PCM приходит, пока сокет CONNECTING — кадры терялись. */
        if (this._autoRecord) {
            try {
                await this.startRecording();
            } catch (err) {
                const detail =
                    err instanceof Error
                        ? err.message
                        : typeof err === 'string'
                          ? err
                          : String(err);
                const isWsBrowserError = typeof Event !== 'undefined' && err instanceof Event;
                if (!isWsBrowserError) {
                    this._dispatch('error', {
                        code: 'voice/client/microphone_denied',
                        detail,
                    });
                }
                ws.close();
                this._ws = null;
                throw err;
            }
        }
        try {
            await openPromise;
        } catch (err) {
            const detail =
                err instanceof Error
                    ? err.message
                    : typeof err === 'string'
                      ? err
                      : String(err);
            const isWsBrowserError = typeof Event !== 'undefined' && err instanceof Event;
            if (!isWsBrowserError && this._autoRecord) {
                this._dispatch('error', {
                    code: 'voice/client/microphone_denied',
                    detail,
                });
            }
            throw err;
        }
        this._flushPcmOutboundQueue();
        this._flushTextOutboundQueue();
        _voiceClientDebug('ws_open', {
            session_id: this._sessionId,
            uplink_path: this._voiceUplinkPath,
            capture_ac_state:
                this._captureCtx !== null && typeof this._captureCtx.state === 'string'
                    ? this._captureCtx.state
                    : 'none',
        });
        if (this._autoRecord && this._captureCtx !== null && !this._closed) {
            await resumeIfNotRunning(this._captureCtx);
        }
    }

    _clearPcmOutboundQueue() {
        this._pcmOutboundQueue.length = 0;
    }

    _clearTextOutboundQueue() {
        this._textOutboundQueue.length = 0;
    }

    /**
     * Отправить накопленные JSON-команды после OPEN.
     */
    _flushTextOutboundQueue() {
        if (this._ws === null || this._ws.readyState !== WebSocket.OPEN) {
            return;
        }
        while (this._textOutboundQueue.length > 0) {
            const payload = this._textOutboundQueue.shift();
            try {
                this._ws.send(JSON.stringify(payload));
            } catch (err) {
                this._dispatch('error', {
                    code: 'voice/client/ws_send_failed',
                    detail: err instanceof Error ? err.message : String(err),
                });
                break;
            }
        }
    }

    /**
     * После фактической отправки PCM по WS (диагностика: `platform_devtools`).
     * @param {ArrayBuffer} buffer
     */
    _debugAfterPcmSent(buffer: ArrayBuffer): void {
        if (!isPlatformDevtoolsEnabled()) {
            return;
        }
        this._pcmUplinkDebugCount += 1;
        const n = this._pcmUplinkDebugCount;
        if (n !== 1 && n % 35 !== 0) {
            return;
        }
        const path = this._voiceUplinkPath;
        const bytes = buffer.byteLength;
        let rmsApprox = 0;
        if (bytes >= 2) {
            const dv = new DataView(buffer);
            const stride = Math.max(2, Math.floor(bytes / 600) * 2);
            let sumSq = 0;
            let cnt = 0;
            for (let o = 0; o <= bytes - 2; o += stride) {
                const s = dv.getInt16(o, true);
                sumSq += s * s;
                cnt += 1;
            }
            rmsApprox = cnt > 0 ? Math.round(Math.sqrt(sumSq / cnt)) : 0;
        }
        _voiceClientDebug('pcm_uplink_tick', {
            session_id: this._sessionId,
            chunk_seq: n,
            path,
            bytes,
            rms_i16_approx: rmsApprox,
        });
    }

    /**
     * Накопить ресемплированный/нативный PCM, разбить на 20 ms-кадры и отправить.
     * Куски короче 320 сэмплов (≈ окраинные части воркер-батча) аккумулируются
     * в `_outboundFrameTail` до ближайшего полного кадра.
     *
     * @param {ArrayBuffer} buffer
     */
    _sendPcmToWebSocket(buffer: ArrayBuffer): void {
        if (this._ws === null) {
            return;
        }
        const frames = spliceIntoOutboundFrames(buffer, this._outboundFrameTail);
        for (const frame of frames) {
            this._enqueueOrSendOutboundFrame(frame);
        }
    }

    /**
     * @param {ArrayBuffer} frame
     */
    _enqueueOrSendOutboundFrame(frame: ArrayBuffer): void {
        if (this._ws === null) {
            return;
        }
        if (this._ws.readyState === WebSocket.OPEN) {
            try {
                this._ws.send(frame);
                this._debugAfterPcmSent(frame);
            } catch (err) {
                this._dispatch('error', {
                    code: 'voice/client/ws_send_failed',
                    detail: err instanceof Error ? err.message : String(err),
                });
            }
            return;
        }
        if (this._ws.readyState === WebSocket.CONNECTING) {
            while (this._pcmOutboundQueue.length >= this._pcmOutboundQueueCap) {
                this._pcmOutboundQueue.shift();
            }
            this._pcmOutboundQueue.push(frame.slice(0));
            return;
        }
    }

    _flushPcmOutboundQueue() {
        if (this._ws === null || this._ws.readyState !== WebSocket.OPEN) {
            return;
        }
        while (this._pcmOutboundQueue.length > 0) {
            const b = this._pcmOutboundQueue.shift();
            if (b === undefined) {
                continue;
            }
            try {
                this._ws.send(b);
                this._debugAfterPcmSent(b);
            } catch (err) {
                this._dispatch('error', {
                    code: 'voice/client/ws_send_failed',
                    detail: err instanceof Error ? err.message : String(err),
                });
                break;
            }
        }
    }

    _buildWsUrl() {
        const params = new URLSearchParams({ company_id: this._companyId });
        for (const [k, v] of Object.entries(this._extraQuery)) {
            if (typeof v === 'string' && v !== '') {
                params.set(k, v);
            }
        }
        return `${this._baseUrl}/api/ws/session/${encodeURIComponent(this._sessionId)}?${params.toString()}`;
    }

    /**
     * Запустить захват микрофона (если не стартовал автоматически).
     * @returns {Promise<void>}
     */
    async startRecording() {
        if (this._recording) return;
        if (typeof window !== 'undefined' && window.isSecureContext === false) {
            const loc = window.location;
            const portPart = loc.port ? `:${loc.port}` : '';
            const localhostUrl = `http://127.0.0.1${portPart}${loc.pathname}${loc.search}`;
            if (!isDevVoiceInsecureHost(loc.hostname)) {
                throw new Error(
                    'Микрофон: Chromium не отдаёт getUserMedia для HTTP на этом хосте (нет secure context) — это правило браузера, не «запрет dev» в платформе. ' +
                        `Откройте тот же путь через loopback, например: ${localhostUrl} , либо HTTPS / флаг Chrome «Insecure origins treated as secure» для dev.`,
                );
            }
            // system.lvh.me и т.п.: isSecureContext=false, но в dev через lvh пробуем mic; если браузер всё же отказал — упадём в общий catch connect().
        }
        if (!hasGetUserMediaApi()) {
            throw new Error(
                'VoiceMediaSession: getUserMedia not available (нет navigator.mediaDevices; часто встроенный превью-браузер, нестандартный WebView или политика безопасности).',
            );
        }
        /** Эхоподавление, шумоподавление и AGC запрашиваются как `exact`: без AEC браузер оставляет
         *  duplex-tap, и аудио ответа TTS возвращается через микрофон — STT транскрибирует «свой»
         *  голос как запрос пользователя. Браузер без поддержки `exact` отказывает, отказ уходит
         *  в `voice/client/microphone_denied`. */
        const stream = await getUserMediaCompat({
            audio: {
                channelCount: { exact: 1 },
                sampleRate: { ideal: VOICE_CAPTURE_SAMPLE_RATE },
                echoCancellation: { exact: true },
                noiseSuppression: { exact: true },
                autoGainControl: { exact: true },
            },
            video: false,
        });
        _voiceClientDebug('mic_constraints_applied', { mode: 'exact' });
        this._mediaStream = stream;
        this._recording = true;
        try {
            await this._initMicCaptureGraph();
        } catch (err) {
            this._recording = false;
            this._teardownCapture();
            throw err;
        }
    }

    /**
     * PCM uplink через Web Audio (`MediaStream` → worklet / ScriptProcessor / Analyser — один раз при сборке).
     */
    async _initMicCaptureGraph() {
        if (this._mediaStream === null) {
            throw new Error('VoiceMediaSession: MediaStream required');
        }
        const tracks = this._mediaStream.getAudioTracks();
        const audioTrack =
            tracks.length > 0 && tracks[0]?.kind === 'audio' ? tracks[0] : null;
        if (audioTrack === null) {
            throw new Error('VoiceMediaSession: в MediaStream нет audio-дорожки');
        }

        this._captureResamplerState = {
            tail: new Float32Array(0),
            nextOutSampleIndex: 0,
            inputBase: 0,
        };
        this._outboundFrameTail = { tail: new Int16Array(0) };

        await this._initAudioContextMicCaptureFromMediaStream();
    }

    /**
     * Захват uplink через Web Audio (MediaStream → worklet / ScriptProcessor / Analyser).
     * @returns {Promise<void>}
     */
    async _initAudioContextMicCaptureFromMediaStream() {
        if (this._captureCtx !== null || this._mediaStream === null) {
            return;
        }
        const Ctx = window.AudioContext || window.webkitAudioContext;
        if (typeof Ctx !== 'function') {
            throw new Error('VoiceMediaSession: AudioContext not available');
        }
        /** Просим 16 kHz: тогда граф совпадает с частотой WS и ресемплер работает «1:1».
         *  Браузер, который выбрал другую частоту, не ошибка: ресемплер берёт `captureCtx.sampleRate`. */
        const captureCtx = new Ctx({
            latencyHint: 'interactive',
            sampleRate: VOICE_CAPTURE_SAMPLE_RATE,
        });
        _voiceClientDebug('capture_ctx_sample_rate', {
            requested: VOICE_CAPTURE_SAMPLE_RATE,
            actual: captureCtx.sampleRate,
        });
        this._captureCtx = captureCtx;

        const source = this._captureCtx.createMediaStreamSource(this._mediaStream);

        const sinkGain = this._captureCtx.createGain();
        sinkGain.gain.value = 0;
        sinkGain.connect(this._captureCtx.destination);
        this._captureSinkGain = sinkGain;

        const keepOsc = this._captureCtx.createOscillator();
        keepOsc.type = 'sine';
        keepOsc.frequency.value = 24;
        const keepGain = this._captureCtx.createGain();
        keepGain.gain.value = 5e-4;
        keepOsc.connect(keepGain);
        keepGain.connect(this._captureCtx.destination);
        keepOsc.start();
        this._captureKeepAliveOsc = keepOsc;
        this._captureKeepAliveGain = keepGain;

        const ctx = this._captureCtx;
        let usedMicWorklet = false;
        const hasAudioWorklet = typeof ctx.audioWorklet?.addModule === 'function';

        if (hasAudioWorklet) {
            // Worklet не входит в бандл: сборка кладёт его в embed-dist, который отдаётся по /static/core/lib.
            // Путь от origin бандла одинаково работает в SPA сервисов и во встраивании на чужой сайт.
            const workletUrl = new URL(
                '/static/core/lib/voice/worklets/voice-mic-capture.processor.js',
                import.meta.url,
            ).href;
            await ctx.audioWorklet.addModule(workletUrl);
            const wNode = new AudioWorkletNode(ctx, 'voice-mic-capture', {
                numberOfInputs: 1,
                numberOfOutputs: 1,
                channelCount: 1,
                outputChannelCount: [1],
            });
            this._captureWorkletNode = wNode;
            wNode.port.onmessage = (event) => {
                void this._handleMicWorkletFrameAsync(event.data);
            };
            source.connect(wNode);
            wNode.connect(sinkGain);
            usedMicWorklet = true;
        }

        if (!usedMicWorklet && typeof ctx.createScriptProcessor === 'function') {
            const processor = ctx.createScriptProcessor(MIC_SCRIPT_PROCESSOR_BUFFER_SIZE, 1, 1);
            this._captureScriptProcessor = processor;
            processor.onaudioprocess = (ev) => {
                this._onMicScriptProcess(ev);
            };
            source.connect(processor);
            processor.connect(sinkGain);
        } else if (!usedMicWorklet) {
            const analyser = ctx.createAnalyser();
            analyser.fftSize = MIC_CAPTURE_FFT_SIZE;
            analyser.smoothingTimeConstant = 0;
            this._captureAnalyser = analyser;
            source.connect(analyser);
            analyser.connect(sinkGain);
        }

        await this._ensureCaptureAudioContextRunning();

        this._captureCtx.onstatechange = () => {
            if (this._closed || !this._captureCtx) {
                return;
            }
            _voiceClientDebug('capture_ctx_state', {
                state: this._captureCtx.state,
                uplink_path: this._voiceUplinkPath,
            });
            const ctxRef = this._captureCtx;
            if (
                ctxRef !== null
                && (ctxRef.state === 'suspended' || ctxRef.state === 'interrupted')
            ) {
                this._resumeInBackground(ctxRef);
            }
        };

        if (typeof window !== 'undefined' && typeof window.setInterval === 'function') {
            if (this._captureResumeWatchdog !== null) {
                clearInterval(this._captureResumeWatchdog);
            }
            this._captureResumeWatchdog = setInterval(() => {
                if (this._closed || !this._recording || !this._captureCtx) {
                    return;
                }
                const c = this._captureCtx;
                if (c.state === 'closed') {
                    return;
                }
                this._resumeInBackground(c);
            }, 140);
        }

        const captureUsesAnalyserPump = !usedMicWorklet && this._captureScriptProcessor === null;
        if (captureUsesAnalyserPump) {
            this._voiceUplinkPath = 'ac_analyser';
        } else if (this._captureScriptProcessor !== null) {
            this._voiceUplinkPath = 'ac_script';
        } else {
            this._voiceUplinkPath = 'ac_worklet';
        }
        _voiceClientDebug('ac_capture_ready', {
            path: this._voiceUplinkPath,
            sample_rate: ctx.sampleRate,
            state: ctx.state,
        });
        if (captureUsesAnalyserPump) {
            this._startMicCapturePumpLoop();
        }

        this._scheduleMutedMicDiagnostics();

        if (typeof document !== 'undefined') {
            const onVis = () => {
                if (document.visibilityState !== 'visible') {
                    return;
                }
                if (!this._captureCtx || this._closed) {
                    return;
                }
                const ctxRef = this._captureCtx;
                if (
                    ctxRef !== null
                    && (ctxRef.state === 'suspended' || ctxRef.state === 'interrupted')
                ) {
                    this._resumeInBackground(ctxRef);
                }
            };
            this._captureVisibilityHandler = onVis;
            document.addEventListener('visibilitychange', onVis);
        }
    }

    /**
     * Обработка батча из AudioWorklet. `resume()` выполняется с await: иначе Chromium часто остаётся
     * в `suspended` после первого кванта, и `process()` перестаёт вызываться.
     * @param {unknown} data
     * @returns {Promise<void>}
     */
    async _handleMicWorkletFrameAsync(data: unknown): Promise<void> {
        if (this._closed || !this._captureResamplerState || !this._captureCtx) {
            return;
        }
        if (!(data instanceof Float32Array) || data.length === 0) {
            return;
        }
        if (isPlatformDevtoolsEnabled()) {
            this._captureWorkletBatchRecv += 1;
            const r = this._captureWorkletBatchRecv;
            if (r <= 8 || r % 25 === 0) {
                _voiceClientDebug('worklet_batch_recv', {
                    batch_n: r,
                    floats: data.length,
                    ctx_state_before: this._captureCtx.state,
                });
            }
        }
        try {
            const c = this._captureCtx;
            await resumeIfNotRunning(c);
            if (c.state !== 'running') {
                if (isPlatformDevtoolsEnabled()) {
                    _voiceClientDebug('worklet_capture_ctx_not_running', {
                        batch_n: this._captureWorkletBatchRecv,
                        state: c.state,
                    });
                }
                return;
            }
            const buf = this._encodeMonoFloatToOutboundPcm16(data, c.sampleRate);
            if (!(buf instanceof ArrayBuffer)) {
                if (isPlatformDevtoolsEnabled()) {
                    this._pcmEncodeMissCount += 1;
                    const m = this._pcmEncodeMissCount;
                    if (m <= 8 || m % 40 === 0) {
                        _voiceClientDebug('pcm_encode_skipped_after_worklet', {
                            miss_seq: m,
                            floats_in: data.length,
                            sr: c.sampleRate,
                        });
                    }
                }
                return;
            }
            this._sendPcmToWebSocket(buf);
        } catch (err) {
            this._dispatch('error', {
                code: 'voice/client/pcm_capture_failed',
                detail: err instanceof Error ? err.message : String(err),
            });
        }
    }

    /**
     * @param {AudioProcessingEvent} ev
     */
    _onMicScriptProcess(ev: AudioProcessingEvent): void {
        if (this._closed || !this._captureResamplerState || !this._captureCtx || !this._captureScriptProcessor) {
            return;
        }
        try {
            const c = this._captureCtx;
            if (c.state !== 'running') {
                void c.resume();
            }
            const output = ev.outputBuffer.getChannelData(0);
            output.fill(0);
            const input = ev.inputBuffer.getChannelData(0);
            const copy = new Float32Array(input.length);
            copy.set(input);
            const buf = this._encodeMonoFloatToOutboundPcm16(copy, this._captureCtx.sampleRate);
            if (buf instanceof ArrayBuffer) {
                this._sendPcmToWebSocket(buf);
            }
        } catch (err) {
            this._dispatch('error', {
                code: 'voice/client/pcm_capture_failed',
                detail: err instanceof Error ? err.message : String(err),
            });
        }
    }

    /**
     * @param {Float32Array} mono
     * @param {number} inRate
     * @returns {ArrayBuffer|null}
     */
    _encodeMonoFloatToOutboundPcm16(mono: Float32Array, inRate: number): ArrayBuffer | null {
        if (!this._captureResamplerState) {
            return null;
        }
        if (!(inRate > 0)) {
            return null;
        }
        const chunk = new Float32Array(mono.length);
        chunk.set(mono);
        if (inRate === VOICE_CAPTURE_SAMPLE_RATE) {
            return floatMonoToPcm16ArrayBufferDirect(chunk);
        }
        return resampleMonoToPcm16ArrayBuffer(chunk, inRate, this._captureResamplerState);
    }

    /** Если дорожка остаётся `muted`, сигнал до графа не доходит — показываем явную ошибку. */
    _scheduleMutedMicDiagnostics() {
        if (this._mediaStream === null) {
            return;
        }
        const tracks = this._mediaStream.getAudioTracks();
        const track = tracks.length > 0 ? tracks[0] : null;
        if (
            track === null
            || typeof track !== 'object'
            || typeof track.addEventListener !== 'function'
        ) {
            return;
        }
        this._mutedTrackDiagnosticTimer = setTimeout(() => {
            this._mutedTrackDiagnosticTimer = null;
            if (this._closed || !this._recording) {
                return;
            }
            if (track.muted === true) {
                this._dispatch('error', {
                    code: 'voice/client/mic_track_muted',
                    detail:
                        'Микрофон в состоянии muted: браузер не отдаёт аудиокадры. Проверьте разрешения сайта, системный ввод по умолчанию и конфликты с другими приложениями.',
                });
            }
        }, 1600);
    }

    _startMicCapturePumpLoop() {
        const run = async () => {
            if (this._closed) {
                this._capturePumpTimer = null;
                return;
            }
            try {
                await this._micCapturePumpOne();
            } catch (err) {
                this._dispatch('error', {
                    code: 'voice/client/pcm_capture_failed',
                    detail: err instanceof Error ? err.message : String(err),
                });
            }
            this._capturePumpTimer = setTimeout(() => {
                void run();
            }, MIC_CAPTURE_PUMP_MS);
        };
        this._capturePumpTimer = setTimeout(() => {
            void run();
        }, 0);
    }

    /**
     * `AudioContext.resume()` асинхронен: после `void resume()` нельзя сразу проверять `state`.
     * Иначе почти каждый тик выходим без send — в сокет уходит один «автоматический» кадр и тишина.
     * @returns {Promise<void>}
     */
    async _micCapturePumpOne() {
        if (this._closed) {
            return;
        }
        if (!this._captureAnalyser || !this._captureResamplerState || !this._captureCtx) {
            return;
        }
        const ctx = this._captureCtx;
        await resumeIfNotRunning(ctx);
        if (ctx.state !== 'running') {
            return;
        }
        const fft = this._captureAnalyser.fftSize;
        const wave = new Float32Array(fft);
        this._captureAnalyser.getFloatTimeDomainData(wave);
        const buf = this._encodeMonoFloatToOutboundPcm16(wave, ctx.sampleRate);
        if (buf instanceof ArrayBuffer) {
            this._sendPcmToWebSocket(buf);
        }
    }

    /**
     * Без состояния `running` PCM не отправляется.
     * @returns {Promise<void>}
     */
    async _ensureCaptureAudioContextRunning() {
        if (!this._captureCtx) {
            throw new Error('VoiceMediaSession: capture AudioContext missing');
        }
        if (this._captureCtx.state === 'suspended') {
            await this._captureCtx.resume();
        }
        if (this._captureCtx.state !== 'running') {
            throw new Error(
                `VoiceMediaSession: AudioContext не running (state=${this._captureCtx.state}); для микрофона часто нужен явный жест — нажмите кнопку включения голоса ещё раз или откройте страницу по http://127.0.0.1 вместо HTTP с кастомным хостом.`,
            );
        }
    }

    /**
     * Отправить клиентскую команду на озвучивание текста.
     * @param {string} text
     * @param {{final?: boolean}} [options]
     */
    speak(text: string, options?: { final?: boolean }): void {
        if (typeof text !== 'string' || text === '') return;
        const isFinal = options?.final === true;
        if (text.length <= VOICE_WS_SPEAK_TEXT_CHUNK_MAX) {
            this._sendSpeakCommand(text, isFinal);
            return;
        }
        const pieces: string[] = [];
        let start = 0;
        while (start < text.length) {
            let end = Math.min(start + VOICE_WS_SPEAK_TEXT_CHUNK_MAX, text.length);
            if (end < text.length) {
                const win = text.slice(start, end);
                let cutRel = -1;
                const minSepIdx = Math.floor(VOICE_WS_SPEAK_TEXT_CHUNK_MAX * 0.35);
                const seps = ['\n\n', '\n', '. ', '。', '! ', '? ', '; ', ', '];
                for (let s = 0; s < seps.length; s += 1) {
                    const sep = seps[s];
                    if (sep === undefined) {
                        throw new Error('voice speak separator missing');
                    }
                    const idx = win.lastIndexOf(sep);
                    if (idx >= minSepIdx) {
                        cutRel = Math.max(cutRel, idx + sep.length);
                    }
                }
                if (cutRel > 0) {
                    end = start + cutRel;
                }
            }
            const piece = text.slice(start, end);
            if (piece !== '') {
                pieces.push(piece);
            }
            start = end;
        }
        if (pieces.length === 0) {
            if (isFinal) {
                this.endUtterance();
            }
            return;
        }
        for (let i = 0; i < pieces.length; i += 1) {
            const last = i === pieces.length - 1;
            const piece = pieces[i];
            if (piece === undefined) {
                throw new Error('voice speak piece missing');
            }
            this._sendSpeakCommand(piece, isFinal && last);
        }
    }

    /**
     * @param {string} text
     * @param {boolean} isФинал
     */
    _sendSpeakCommand(text: string, isFinal: boolean): void {
        const payload: Record<string, unknown> = { type: 'speak', text };
        if (isFinal) {
            payload.final = true;
        }
        this._sendText(payload);
    }

    /**
     * Отметить конец реплики — flush чанкера на стороне voice.
     */
    endUtterance() {
        this._sendText({ type: 'end_of_utterance' });
    }

    /**
     * Остановить любое текущее воспроизведение (barge-in от клиента).
     */
    stopPlayback() {
        this._sendText({ type: 'stop_playback' });
        this._resetPlayback();
        this._nudgeCaptureResumeIfRecording();
    }

    /**
     * Есть ли ещё исходящий с клиента TTS в Web Audio (очередь декода/воспроизведения).
     * Нужен для client barge-in: сервер может прислать `tts_state: stopped` раньше, чем очередь на клиенте доиграет.
     * @returns {boolean}
     */
    hasScheduledTtsPlayback() {
        if (this._playbackChunksInFlight > 0) {
            return true;
        }
        if (this._playbackCtx === null || this._playbackCtx.state === 'closed') {
            return false;
        }
        return this._playbackCursor > this._playbackCtx.currentTime + 0.02;
    }

    /**
     * После TTS часть браузеров держит захват в suspended; единый вызов resume для duplex STT.
     * @returns {void}
     */
    _nudgeCaptureResumeIfRecording() {
        if (!this._recording || this._closed) {
            return;
        }
        const c = this._captureCtx;
        if (c === null || c.state === 'closed') {
            return;
        }
        if (c.state === 'running') {
            return;
        }
        this._resumeInBackground(c);
    }

    /**
     * @param {object} payload
     */
    _sendText(payload: Record<string, unknown>): void {
        if (this._ws === null) {
            return;
        }
        if (this._ws.readyState === WebSocket.OPEN) {
            try {
                this._ws.send(JSON.stringify(payload));
            } catch (err) {
                this._dispatch('error', {
                    code: 'voice/client/ws_send_failed',
                    detail: err instanceof Error ? err.message : String(err),
                });
            }
            return;
        }
        if (this._ws.readyState === WebSocket.CONNECTING) {
            while (this._textOutboundQueue.length >= this._textOutboundQueueCap) {
                this._textOutboundQueue.shift();
            }
            this._textOutboundQueue.push(payload);
        }
    }

    /**
     * @param {MessageEvent} event
     */
    _handleWsMessage(event: MessageEvent): void {
        if (event.data instanceof ArrayBuffer) {
            if (isPlatformDevtoolsEnabled()) {
                this._wsInBinaryDebugSeq += 1;
                if (this._wsInBinaryDebugSeq <= 12) {
                    _voiceClientDebug('ws_in_binary', {
                        seq: this._wsInBinaryDebugSeq,
                        bytes: event.data.byteLength,
                    });
                }
            }
            this._playAudioChunk(event.data);
            return;
        }
        if (typeof event.data !== 'string') {
            return;
        }
        let payload;
        try {
            payload = JSON.parse(event.data);
        } catch (err) {
            this._dispatchFailure('voice/client/ws_frame_invalid', err);
            return;
        }
        if (!payload || typeof payload !== 'object') return;
        if (isPlatformDevtoolsEnabled()) {
            const t = typeof payload.type === 'string' ? payload.type : '?';
            this._wsJsonDebugSeq += 1;
            if (this._wsJsonDebugSeq <= 60) {
                _voiceClientDebug('ws_in_json', { seq: this._wsJsonDebugSeq, type: t });
            }
        }
        switch (payload.type) {
            case 'transcript':
                this._dispatch('transcript', {
                    text: typeof payload.text === 'string' ? payload.text : '',
                    final: payload.final === true,
                    language: typeof payload.language === 'string' ? payload.language : undefined,
                    interrupted: payload.interrupted === true,
                });
                break;
            case 'finalize_done':
                this._dispatch('recordingFinalized', {});
                break;
            case 'vad':
                if (payload.state === 'started' || payload.state === 'ended') {
                    this._dispatch('vad', { state: payload.state });
                }
                break;
            case 'tts_state':
                if (payload.state === 'playing' || payload.state === 'stopped') {
                    this._dispatch('ttsState', { state: payload.state });
                    if (payload.state === 'stopped') {
                        this._nudgeCaptureResumeIfRecording();
                    }
                }
                break;
            case 'media_config':
                this._mediaConfig = {
                    mime: typeof payload.mime === 'string' ? payload.mime : this._mediaConfig.mime,
                    sampleRate: typeof payload.sample_rate === 'number' ? payload.sample_rate : this._mediaConfig.sampleRate,
                    channels: typeof payload.channels === 'number' ? payload.channels : this._mediaConfig.channels,
                };
                this._dispatch('mediaConfig', this._mediaConfig);
                break;
            case 'error':
                this._dispatch('error', {
                    code: typeof payload.code === 'string' ? payload.code : 'voice/unknown',
                    detail: typeof payload.detail === 'string' ? payload.detail : '',
                });
                break;
            case 'ping':
                break;
            default:
                break;
        }
    }

    /**
     * @param {CloseEvent} event
     */
    _handleWsClose(event: CloseEvent): void {
        const codeVal = typeof event.code === 'number' ? event.code : 1006;
        _voiceClientDebug('ws_closed', {
            session_id: this._sessionId,
            code: codeVal,
            reason: typeof event.reason === 'string' ? event.reason : '',
            pcm_uplink_chunks_logged: this._pcmUplinkDebugCount,
            uplink_path: this._voiceUplinkPath,
        });
        this._dispatch('closed', {
            code: codeVal,
            reason: typeof event.reason === 'string' ? event.reason : '',
        });
        this._closed = true;
        this._clearPcmOutboundQueue();
        this._clearTextOutboundQueue();
        this._ws = null;
        this._teardownCapture();
    }

    _teardownCapture() {
        this._recording = false;
        this._captureResamplerState = null;
        this._outboundFrameTail = { tail: new Int16Array(0) };
        if (typeof document !== 'undefined' && this._captureVisibilityHandler !== null) {
            document.removeEventListener('visibilitychange', this._captureVisibilityHandler);
            this._captureVisibilityHandler = null;
        }
        if (this._capturePumpTimer !== null) {
            clearTimeout(this._capturePumpTimer);
            this._capturePumpTimer = null;
        }
        if (this._mutedTrackDiagnosticTimer !== null) {
            clearTimeout(this._mutedTrackDiagnosticTimer);
            this._mutedTrackDiagnosticTimer = null;
        }
        if (this._captureResumeWatchdog !== null) {
            clearInterval(this._captureResumeWatchdog);
            this._captureResumeWatchdog = null;
        }
        if (this._captureCtx !== null) {
            this._captureCtx.onstatechange = null;
        }
        if (this._captureWorkletNode !== null) {
            this._captureWorkletNode.port.onmessage = null;
            this._captureWorkletNode.port.close();
            this._captureWorkletNode.disconnect();
            this._captureWorkletNode = null;
        }
        if (this._captureScriptProcessor) {
            this._captureScriptProcessor.onaudioprocess = null;
            this._captureScriptProcessor.disconnect();
            this._captureScriptProcessor = null;
        }
        if (this._captureKeepAliveOsc) {
            this._captureKeepAliveOsc.stop();
            this._captureKeepAliveOsc.disconnect();
            this._captureKeepAliveOsc = null;
        }
        if (this._captureKeepAliveGain) {
            this._captureKeepAliveGain.disconnect();
            this._captureKeepAliveGain = null;
        }
        if (this._captureAnalyser) {
            this._captureAnalyser.disconnect();
            this._captureAnalyser = null;
        }
        if (this._captureSinkGain) {
            this._captureSinkGain.disconnect();
            this._captureSinkGain = null;
        }
        if (this._captureCtx) {
            this._closeAudioContext(this._captureCtx);
            this._captureCtx = null;
        }
        if (this._mediaStream) {
            for (const track of this._mediaStream.getTracks()) {
                track.stop();
            }
            this._mediaStream = null;
        }
    }

    _resetPlayback() {
        this._playbackQueue = Promise.resolve();
        this._playbackChunksInFlight = 0;
        if (this._playbackCtx !== null) {
            this._closeAudioContext(this._playbackCtx);
            this._playbackCtx = null;
        }
        this._playbackCursor = 0;
    }

    /**
     * Воспроизвести чанк аудио от voice.
     * @param {ArrayBuffer} buffer
     */
    _playAudioChunk(buffer: ArrayBuffer): void {
        this._playbackChunksInFlight += 1;
        const run = () =>
            this._playAudioChunkSequential(buffer).finally(() => {
                this._playbackChunksInFlight -= 1;
            });
        this._playbackQueue = this._playbackQueue.then(run, run);
    }

    /**
     * @param {ArrayBuffer} buffer
     */
    async _playAudioChunkSequential(buffer: ArrayBuffer): Promise<void> {
        const ctx = await this._ensurePlaybackContext();
        const mime = this._mediaConfig.mime.toLowerCase();
        if (mime === 'audio/l16' || mime === 'audio/pcm') {
            await this._playRawPcm(ctx, buffer);
            return;
        }
        try {
            const audioBuffer = await ctx.decodeAudioData(buffer.slice(0));
            await this._scheduleAudioBuffer(ctx, audioBuffer);
        } catch (err) {
            this._dispatch('error', {
                code: 'voice/client/decode_failed',
                detail: err instanceof Error && err.message ? err.message : String(err),
            });
        }
    }

    async _ensurePlaybackContext() {
        if (this._playbackCtx !== null && this._playbackCtx.state !== 'closed') {
            await resumeIfNotRunning(this._playbackCtx);
            return this._playbackCtx;
        }
        const Ctx = window.AudioContext || window.webkitAudioContext;
        this._playbackCtx = new Ctx({ sampleRate: this._mediaConfig.sampleRate });
        await resumeIfNotRunning(this._playbackCtx);
        this._playbackCursor = this._playbackCtx.currentTime;
        return this._playbackCtx;
    }

    /**
     * Только из синхронного обработчика жеста (отправка сообщения, микрофон).
     * Иначе Chromium держит AudioContext в suspended — чанки TTS по WS ставятся в очередь без звука.
     */
    primePlaybackFromUserGesture() {
        if (this._closed) {
            return;
        }
        const Ctx = window.AudioContext || window.webkitAudioContext;
        if (this._playbackCtx === null || this._playbackCtx.state === 'closed') {
            this._playbackCtx = new Ctx({ sampleRate: this._mediaConfig.sampleRate });
            this._playbackCursor = this._playbackCtx.currentTime;
        }
        if (this._playbackCtx.state === 'suspended') {
            this._resumeInBackground(this._playbackCtx);
        }
    }

    /**
     * @param {AudioContext} ctx
     * @param {ArrayBuffer} buffer
     */
    async _playRawPcm(ctx: AudioContext, buffer: ArrayBuffer): Promise<void> {
        const int16 = new Int16Array(buffer);
        if (int16.length === 0) return;
        const float32 = new Float32Array(int16.length);
        for (let i = 0; i < int16.length; i++) {
            float32[i] = sampleAt(int16, i) / 0x8000;
        }
        const audioBuffer = ctx.createBuffer(1, float32.length, this._mediaConfig.sampleRate);
        audioBuffer.copyToChannel(float32, 0);
        await this._scheduleAudioBuffer(ctx, audioBuffer);
    }

    /**
     * @param {AudioContext} ctx
     * @param {AudioBuffer} audioBuffer
     */
    async _scheduleAudioBuffer(ctx: AudioContext, audioBuffer: AudioBuffer): Promise<void> {
        await resumeIfNotRunning(ctx);
        const source = ctx.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(ctx.destination);
        const startAt = Math.max(ctx.currentTime, this._playbackCursor);
        source.start(startAt);
        this._playbackCursor = startAt + audioBuffer.duration;
    }

    /**
     * @param {string} type
     * @param {object} detail
     */
    _dispatch(type: string, detail: Record<string, unknown>): void {
        this.dispatchEvent(new CustomEvent(type, { detail }));
    }

    _dispatchFailure(code: string, err: unknown): void {
        this._dispatch('error', { code, detail: err instanceof Error ? err.message : String(err) });
    }

    /** Возобновление без ожидания (обработчики состояния и жеста): отказ уходит событием `error`. */
    _resumeInBackground(ctx: AudioContext): void {
        resumeIfNotRunning(ctx).catch((err: unknown) => this._dispatchFailure('voice/client/audio_resume_failed', err));
    }

    _closeAudioContext(ctx: AudioContext): void {
        if (ctx.state === 'closed') {
            return;
        }
        ctx.close().catch((err: unknown) => this._dispatchFailure('voice/client/audio_close_failed', err));
    }

    /**
     * Запросить на сервере немедленный flush STT по текущему сегменту (WS ``end_recording``)
     * и дождаться ответа ``finalize_done`` или таймаута. Вызывать **до** bridge.stop() / close(),
     * пока клиент ещё принимает транскрипты.
     * @param {number} [timeoutMs]
     * @returns {Promise<void>}
     */
    awaitRecordingFinalized(timeoutMs = 5000): Promise<void> {
        if (this._closed || !this.isConnected) {
            return Promise.resolve();
        }
        return new Promise((resolve) => {
            let settled = false;
            let timer: ReturnType<typeof setTimeout> | null = null;
            const finish = () => {
                if (settled) {
                    return;
                }
                settled = true;
                if (timer !== null) {
                    clearTimeout(timer);
                }
                this.removeEventListener('recordingFinalized', onDone);
                resolve();
            };
            const onDone = () => finish();
            timer = setTimeout(finish, timeoutMs);
            this.addEventListener('recordingFinalized', onDone, { once: true });
            this._sendText({ type: 'end_recording' });
        });
    }

    /**
     * Закрыть сессию: остановить запись, закрыть WS, освободить контексты.
     */
    close() {
        if (this._closed) return;
        this._closed = true;
        this._clearPcmOutboundQueue();
        this._clearTextOutboundQueue();
        this._teardownCapture();
        this._resetPlayback();
        if (this._ws !== null) {
            this._ws.close(1000, 'client_close');
            this._ws = null;
        }
    }
}
