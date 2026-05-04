/**
 * VoiceMediaSession — универсальный media-клиент для `apps/voice` WS.
 *
 * Не знает про A2A, Flows, embed или чат-UI. Делает ровно три вещи:
 *
 *  1. Держит WS `/voice/api/ws/session/{id}` и автоматом отправляет
 *     PCM 16kHz mono 16-bit из микрофона (через `AudioWorklet`).
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

const PCM_CAPTURE_WORKLET_NAME = 'pcm-capture';

const PCM_CAPTURE_WORKLET_SOURCE = `
const OUT_SAMPLE_RATE = 16000;

function floatToInt16(sample) {
    const s = Math.max(-1, Math.min(1, sample));
    const v = s < 0 ? s * 0x8000 : s * 0x7fff;
    return v | 0;
}

class PCMCaptureProcessor extends AudioWorkletProcessor {
    constructor() {
        super();
        this._tail = new Float32Array(0);
        this._nextOutSampleIndex = 0;
    }

    process(inputs) {
        const input = inputs[0];
        if (!input || input.length === 0) {
            return true;
        }
        const channel = input[0];
        if (!channel || channel.length === 0) {
            return true;
        }
        const inRate = sampleRate;
        if (inRate <= 0) {
            return true;
        }
        const mergedLen = this._tail.length + channel.length;
        const merged = new Float32Array(mergedLen);
        merged.set(this._tail);
        merged.set(channel, this._tail.length);

        const ratio = inRate / OUT_SAMPLE_RATE;
        const pcmParts = [];

        while (true) {
            const inPos = this._nextOutSampleIndex * ratio;
            const i0 = Math.floor(inPos);
            const i1 = i0 + 1;
            if (i1 >= merged.length) {
                break;
            }
            const frac = inPos - i0;
            const s = merged[i0] * (1 - frac) + merged[i1] * frac;
            pcmParts.push(floatToInt16(s));
            this._nextOutSampleIndex += 1;
        }

        const keepFloat = Math.floor(this._nextOutSampleIndex * ratio);
        const keepFrom = keepFloat > 0 ? keepFloat - 1 : 0;
        if (keepFrom >= merged.length) {
            this._tail = new Float32Array(0);
        } else {
            this._tail = merged.subarray(keepFrom);
        }

        const totalLen = pcmParts.length;
        if (totalLen > 0) {
            const pcm = new Int16Array(totalLen);
            for (let i = 0; i < totalLen; i++) {
                pcm[i] = pcmParts[i];
            }
            this.port.postMessage(pcm.buffer, [pcm.buffer]);
        }
        return true;
    }
}
registerProcessor('${PCM_CAPTURE_WORKLET_NAME}', PCMCaptureProcessor);
`;

export const VOICE_CAPTURE_SAMPLE_RATE = 16000;

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
 */

export class VoiceMediaSession extends EventTarget {
    /**
     * @param {VoiceMediaSessionOptions} options
     */
    constructor(options) {
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
        /** @type {AudioWorkletNode|null} */
        this._captureNode = null;
        this._workletReady = false;
        this._recording = false;

        /** @type {AudioContext|null} */
        this._playbackCtx = null;
        this._playbackCursor = 0;

        this._closed = false;
        this._openPromise = null;
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
        const ws = new WebSocket(url);
        ws.binaryType = 'arraybuffer';
        this._ws = ws;

        await new Promise((resolve, reject) => {
            ws.addEventListener('open', () => resolve(), { once: true });
            ws.addEventListener('error', (e) => reject(e), { once: true });
        });

        ws.addEventListener('message', (event) => this._handleWsMessage(event));
        ws.addEventListener('close', (event) => this._handleWsClose(event));

        if (this._autoRecord) {
            try {
                await this.startRecording();
            } catch (err) {
                this._dispatch('error', {
                    code: 'voice/client/microphone_denied',
                    detail: err && err.message ? err.message : String(err),
                });
                throw err;
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
            throw new Error(
                'Микрофон: Chromium не отдаёт getUserMedia для HTTP на этом хосте (нет secure context) — это правило браузера, не «запрет dev» в платформе. ' +
                    `Откройте тот же путь через loopback, например: ${localhostUrl} , либо HTTPS / флаг Chrome «Insecure origins treated as secure» для dev.`,
            );
        }
        if (!hasGetUserMediaApi()) {
            throw new Error(
                'VoiceMediaSession: getUserMedia not available (нет navigator.mediaDevices; часто встроенный превью-браузер, нестандартный WebView или политика безопасности).',
            );
        }
        this._mediaStream = await getUserMediaCompat({
            audio: {
                channelCount: 1,
                sampleRate: VOICE_CAPTURE_SAMPLE_RATE,
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true,
            },
            video: false,
        });
        await this._initCaptureWorklet();
        this._recording = true;
    }

    async _initCaptureWorklet() {
        const Ctx = window.AudioContext || window.webkitAudioContext;
        if (typeof Ctx !== 'function') {
            throw new Error('VoiceMediaSession: AudioContext not available');
        }
        /** Реальный sampleRate часто 44100/48000 (браузер игнорирует hint); ресемплинг в worklet → 16kHz. */
        this._captureCtx = new Ctx();
        const blob = new Blob([PCM_CAPTURE_WORKLET_SOURCE], { type: 'application/javascript' });
        const url = URL.createObjectURL(blob);
        try {
            await this._captureCtx.audioWorklet.addModule(url);
        } finally {
            URL.revokeObjectURL(url);
        }
        const source = this._captureCtx.createMediaStreamSource(this._mediaStream);
        this._captureNode = new AudioWorkletNode(this._captureCtx, PCM_CAPTURE_WORKLET_NAME);
        this._captureNode.port.onmessage = (event) => {
            if (this._ws === null || this._ws.readyState !== WebSocket.OPEN) {
                return;
            }
            this._ws.send(event.data);
        };
        source.connect(this._captureNode);
        // Нельзя подключать к destination — тогда слышно себя через колонки.
        this._workletReady = true;
    }

    /**
     * Отправить клиентскую команду на озвучивание текста.
     * @param {string} text
     * @param {{final?: boolean}} [options]
     */
    speak(text, options) {
        if (typeof text !== 'string' || text === '') return;
        const payload = { type: 'speak', text };
        if (options && options.final === true) {
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
    }

    /**
     * @param {object} payload
     */
    _sendText(payload) {
        if (this._ws === null || this._ws.readyState !== WebSocket.OPEN) {
            return;
        }
        this._ws.send(JSON.stringify(payload));
    }

    /**
     * @param {MessageEvent} event
     */
    _handleWsMessage(event) {
        if (event.data instanceof ArrayBuffer) {
            this._playAudioChunk(event.data);
            return;
        }
        if (typeof event.data !== 'string') {
            return;
        }
        let payload;
        try {
            payload = JSON.parse(event.data);
        } catch {
            return;
        }
        if (!payload || typeof payload !== 'object') return;
        switch (payload.type) {
            case 'transcript':
                this._dispatch('transcript', {
                    text: typeof payload.text === 'string' ? payload.text : '',
                    final: payload.final === true,
                    language: typeof payload.language === 'string' ? payload.language : undefined,
                });
                break;
            case 'vad':
                if (payload.state === 'started' || payload.state === 'ended') {
                    this._dispatch('vad', { state: payload.state });
                }
                break;
            case 'tts_state':
                if (payload.state === 'playing' || payload.state === 'stopped') {
                    this._dispatch('ttsState', { state: payload.state });
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
    _handleWsClose(event) {
        this._dispatch('closed', {
            code: typeof event.code === 'number' ? event.code : 1006,
            reason: typeof event.reason === 'string' ? event.reason : '',
        });
        this._closed = true;
        this._teardownCapture();
    }

    _teardownCapture() {
        this._recording = false;
        if (this._captureNode) {
            try { this._captureNode.port.onmessage = null; } catch { /* noop */ }
            try { this._captureNode.disconnect(); } catch { /* noop */ }
            this._captureNode = null;
        }
        if (this._captureCtx) {
            try { this._captureCtx.close(); } catch { /* noop */ }
            this._captureCtx = null;
        }
        if (this._mediaStream) {
            for (const track of this._mediaStream.getTracks()) {
                try { track.stop(); } catch { /* noop */ }
            }
            this._mediaStream = null;
        }
    }

    _resetPlayback() {
        if (this._playbackCtx !== null) {
            try { this._playbackCtx.close(); } catch { /* noop */ }
            this._playbackCtx = null;
        }
        this._playbackCursor = 0;
    }

    /**
     * Воспроизвести чанк аудио от voice.
     * @param {ArrayBuffer} buffer
     */
    async _playAudioChunk(buffer) {
        const ctx = await this._ensurePlaybackContext();
        const mime = (this._mediaConfig.mime || '').toLowerCase();
        if (mime === 'audio/l16' || mime === 'audio/pcm') {
            this._playRawPcm(ctx, buffer);
            return;
        }
        // WAV / MP3 / OGG — декодируем через встроенный декодер.
        try {
            const audioBuffer = await ctx.decodeAudioData(buffer.slice(0));
            this._scheduleAudioBuffer(ctx, audioBuffer);
        } catch (err) {
            this._dispatch('error', {
                code: 'voice/client/decode_failed',
                detail: err && err.message ? err.message : String(err),
            });
        }
    }

    async _ensurePlaybackContext() {
        if (this._playbackCtx !== null && this._playbackCtx.state !== 'closed') {
            return this._playbackCtx;
        }
        const Ctx = window.AudioContext || window.webkitAudioContext;
        this._playbackCtx = new Ctx({ sampleRate: this._mediaConfig.sampleRate });
        if (this._playbackCtx.state === 'suspended') {
            try { await this._playbackCtx.resume(); } catch { /* noop */ }
        }
        this._playbackCursor = this._playbackCtx.currentTime;
        return this._playbackCtx;
    }

    /**
     * @param {AudioContext} ctx
     * @param {ArrayBuffer} buffer
     */
    _playRawPcm(ctx, buffer) {
        const int16 = new Int16Array(buffer);
        if (int16.length === 0) return;
        const float32 = new Float32Array(int16.length);
        for (let i = 0; i < int16.length; i++) {
            float32[i] = int16[i] / 0x8000;
        }
        const audioBuffer = ctx.createBuffer(1, float32.length, this._mediaConfig.sampleRate);
        audioBuffer.copyToChannel(float32, 0);
        this._scheduleAudioBuffer(ctx, audioBuffer);
    }

    /**
     * @param {AudioContext} ctx
     * @param {AudioBuffer} audioBuffer
     */
    _scheduleAudioBuffer(ctx, audioBuffer) {
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
    _dispatch(type, detail) {
        this.dispatchEvent(new CustomEvent(type, { detail }));
    }

    /**
     * Закрыть сессию: остановить запись, закрыть WS, освободить контексты.
     */
    close() {
        if (this._closed) return;
        this._closed = true;
        this._teardownCapture();
        this._resetPlayback();
        if (this._ws !== null) {
            try { this._ws.close(1000, 'client_close'); } catch { /* noop */ }
            this._ws = null;
        }
    }
}
