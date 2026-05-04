/**
 * VoiceMediaSession — универсальный media-клиент для `apps/voice` WS.
 *
 * Не знает про A2A, Flows, embed или чат-UI. Делает ровно три вещи:
 *
 *  1. Держит WS `/voice/api/ws/session/{id}` и автоматом отправляет
 *     PCM 16kHz mono 16-bit из микрофона через `ScriptProcessorNode` (общий путь для
 *     всех Origin: захват через AudioWorklet в ряде Chromium даёт только нули uplink).
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

/**
 * Hostname'ы dev-оригина, где пробуем mic/WebAudio при HTTP (isSecureContext=false):
 * поддомены lvh.me, localhost, 127.0.0.1. Иначе Chromium не отдаёт getUserMedia — см. startRecording.
 *
 * @param {string} hostname
 * @returns {boolean}
 */
function isDevVoiceInsecureHost(hostname) {
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

export const VOICE_CAPTURE_SAMPLE_RATE = 16000;

function floatSampleToInt16(sample) {
    const s = Math.max(-1, Math.min(1, sample));
    const v = s < 0 ? s * 0x8000 : s * 0x7fff;
    return v | 0;
}

/**
 * @param {AudioBuffer} ib
 * @returns {Float32Array|null}
 */
function monoFloat32FromAudioBuffer(ib) {
    const frameLen = ib.length;
    const nCh = ib.numberOfChannels;
    if (frameLen === 0 || nCh === 0) {
        return null;
    }
    const mono = new Float32Array(frameLen);
    let contributors = 0;
    for (let c = 0; c < nCh; c++) {
        const data = ib.getChannelData(c);
        if (!data || data.length < frameLen) {
            continue;
        }
        contributors += 1;
        for (let i = 0; i < frameLen; i++) {
            mono[i] += data[i];
        }
    }
    if (contributors === 0) {
        return null;
    }
    if (contributors > 1) {
        const inv = 1 / contributors;
        for (let i = 0; i < frameLen; i++) {
            mono[i] *= inv;
        }
    }
    return mono;
}

/**
 * @param {Float32Array} channel
 * @param {number} inRate
 * @param {{ tail: Float32Array, nextOutSampleIndex: number }} state
 * @returns {ArrayBuffer|null}
 */
function resampleMonoToPcm16ArrayBuffer(channel, inRate, state) {
    if (!channel || channel.length === 0) {
        return null;
    }
    if (!(inRate > 0)) {
        return null;
    }
    const mergedLen = state.tail.length + channel.length;
    const merged = new Float32Array(mergedLen);
    merged.set(state.tail);
    merged.set(channel, state.tail.length);
    const ratio = inRate / VOICE_CAPTURE_SAMPLE_RATE;
    const pcmParts = [];
    while (true) {
        const inPos = state.nextOutSampleIndex * ratio;
        const i0 = Math.floor(inPos);
        const i1 = i0 + 1;
        if (i1 >= merged.length) {
            break;
        }
        const frac = inPos - i0;
        const s = merged[i0] * (1 - frac) + merged[i1] * frac;
        pcmParts.push(floatSampleToInt16(s));
        state.nextOutSampleIndex += 1;
    }
    const keepFloat = Math.floor(state.nextOutSampleIndex * ratio);
    const keepFrom = keepFloat > 0 ? keepFloat - 1 : 0;
    if (keepFrom >= merged.length) {
        state.tail = new Float32Array(0);
    } else {
        state.tail = merged.subarray(keepFrom);
    }
    const totalLen = pcmParts.length;
    if (totalLen === 0) {
        return null;
    }
    const pcm = new Int16Array(totalLen);
    for (let i = 0; i < totalLen; i++) {
        pcm[i] = pcmParts[i];
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
        /** @type {ScriptProcessorNode|null} */
        this._scriptProcessor = null;
        /** @type {{ tail: Float32Array, nextOutSampleIndex: number }|null} */
        this._captureResamplerState = null;
        /** @type {GainNode|null} — mute sink: тянуть граф к destination без эха на колонках */
        this._captureSinkGain = null;
        this._recording = false;

        /** @type {AudioContext|null} */
        this._playbackCtx = null;
        this._playbackCursor = 0;

        this._closed = false;
        this._openPromise = null;
        /** Очередь PCM до OPEN (CONNECTING); иначе process() шлёт, onmessage делает return — байты не уходят. */
        this._pcmOutboundQueue = [];
        this._pcmOutboundQueueCap = 200;
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

        ws.addEventListener('message', (event) => this._handleWsMessage(event));
        ws.addEventListener('close', (event) => this._handleWsClose(event));
        ws.addEventListener('open', () => {
            this._flushPcmOutboundQueue();
        });

        const openPromise = new Promise((resolve, reject) => {
            ws.addEventListener('open', () => resolve(undefined), { once: true });
            ws.addEventListener('error', (e) => reject(e), { once: true });
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
                try { ws.close(); } catch { /* noop */ }
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
    }

    _clearPcmOutboundQueue() {
        this._pcmOutboundQueue.length = 0;
    }

    /**
     * @param {ArrayBuffer} buffer
     */
    _sendPcmToWebSocket(buffer) {
        if (this._ws === null) {
            return;
        }
        if (this._ws.readyState === WebSocket.OPEN) {
            try {
                this._ws.send(buffer);
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
            this._pcmOutboundQueue.push(buffer.slice(0));
            return;
        }
    }

    _flushPcmOutboundQueue() {
        if (this._ws === null || this._ws.readyState !== WebSocket.OPEN) {
            return;
        }
        while (this._pcmOutboundQueue.length > 0) {
            const b = this._pcmOutboundQueue.shift();
            try {
                this._ws.send(b);
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
        this._mediaStream = await getUserMediaCompat({ audio: true, video: false });
        await this._initCaptureScriptProcessor();
        this._recording = true;
    }

    /**
     * PCM uplink только через ScriptProcessorNode: канал ScriptProcessor задаётся по
     * `MediaStreamAudioSourceNode.channelCount` (учёт stereo); без running AudioContext процесс не вызывается.
     */
    async _initCaptureScriptProcessor() {
        const Ctx = window.AudioContext || window.webkitAudioContext;
        if (typeof Ctx !== 'function') {
            throw new Error('VoiceMediaSession: AudioContext not available');
        }
        this._captureCtx = new Ctx({ latencyHint: 'interactive' });
        this._captureResamplerState = { tail: new Float32Array(0), nextOutSampleIndex: 0 };

        const source = this._captureCtx.createMediaStreamSource(this._mediaStream);
        /** @type {number} */
        let inputChannels = 2;
        const srcCh = source.channelCount;
        if (typeof srcCh === 'number' && Number.isFinite(srcCh) && srcCh >= 1) {
            /** Минимум 2: часть браузеров отдаёт «моно», но дорожки фактически стерео, речь только во втором канале. */
            inputChannels = Math.min(32, Math.max(2, Math.floor(srcCh)));
        }

        const processor = this._captureCtx.createScriptProcessor(4096, inputChannels, 1);
        this._scriptProcessor = processor;
        processor.onaudioprocess = (e) => {
            const mono = monoFloat32FromAudioBuffer(e.inputBuffer);
            if (!mono || !this._captureResamplerState) {
                return;
            }
            const inRate = this._captureCtx.sampleRate;
            const buf = resampleMonoToPcm16ArrayBuffer(mono, inRate, this._captureResamplerState);
            if (buf instanceof ArrayBuffer) {
                this._sendPcmToWebSocket(buf);
            }
        };

        source.connect(processor);

        const sinkGain = this._captureCtx.createGain();
        sinkGain.gain.value = 0;
        processor.connect(sinkGain);
        sinkGain.connect(this._captureCtx.destination);
        this._captureSinkGain = sinkGain;

        await this._ensureCaptureAudioContextRunning();
    }

    /**
     * Без состояния `running` браузер не вызывает onaudioprocess — uplink будет пустым.
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
        this._clearPcmOutboundQueue();
        this._ws = null;
        this._teardownCapture();
    }

    _teardownCapture() {
        this._recording = false;
        this._captureResamplerState = null;
        if (this._captureSinkGain) {
            try { this._captureSinkGain.disconnect(); } catch { /* noop */ }
            this._captureSinkGain = null;
        }
        if (this._scriptProcessor) {
            try { this._scriptProcessor.onaudioprocess = null; } catch { /* noop */ }
            try { this._scriptProcessor.disconnect(); } catch { /* noop */ }
            this._scriptProcessor = null;
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
        this._clearPcmOutboundQueue();
        this._teardownCapture();
        this._resetPlayback();
        if (this._ws !== null) {
            try { this._ws.close(1000, 'client_close'); } catch { /* noop */ }
            this._ws = null;
        }
    }
}
