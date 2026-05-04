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

/**
 * Query-фрагменты из `location.search` и из `location.hash` (после `?`), если SPA
 * держит параметры в hash.
 *
 * @returns {string[]}
 */
function voiceClientUrlQuerySlices() {
    if (typeof window === 'undefined') {
        return [];
    }
    /** @type {string[]} */
    const out = [];
    const search = window.location.search;
    if (typeof search === 'string' && search.length > 0) {
        out.push(search);
    }
    const hash = window.location.hash;
    if (typeof hash === 'string' && hash.includes('?')) {
        const i = hash.indexOf('?');
        out.push(hash.slice(i));
    }
    return out;
}

/**
 * Диагностика в консоли: **`?voice_debug=1`** или **`?voice_debug=true`** в URL
 * (в т.ч. в части hash после `?`), либо **`sessionStorage.setItem('voice_debug','1')`**,
 * затем перезагрузите вкладку. Сообщения `[voice-media]` после **`connect()`** —
 * включите голосовой ввод (микрофон на чате flows).
 *
 * @returns {boolean}
 */
export function isVoiceClientDebugEnabled() {
    if (typeof window === 'undefined') {
        return false;
    }
    try {
        for (const qs of voiceClientUrlQuerySlices()) {
            if (/[?&]voice_debug=(?:1|true)(?:&|$)/i.test(qs)) {
                return true;
            }
        }
        if (typeof window.sessionStorage?.getItem === 'function') {
            const v = window.sessionStorage.getItem('voice_debug');
            if (v === '1' || (typeof v === 'string' && v.toLowerCase() === 'true')) {
                return true;
            }
        }
    } catch {
        /* storage / доступ к location */
    }
    return false;
}

/**
 * @param {string} message
 * @param {Record<string, unknown>} [payload]
 */
function _voiceClientDebug(message, payload) {
    if (!isVoiceClientDebugEnabled()) {
        return;
    }
    if (payload !== undefined) {
        console.info('[voice-media]', message, payload);
        return;
    }
    console.info('[voice-media]', message);
}

/**
 * Одноразовое сообщение при загрузке модуля: иначе кажется, что флаг не работает
 * (WS/PCM-логи идут только после `connect()` / кнопки микрофона).
 */
function _scheduleVoiceDebugBootstrapNotice() {
    if (typeof window === 'undefined') {
        return;
    }
    const run = () => {
        if (!isVoiceClientDebugEnabled()) {
            return;
        }
        console.info('[voice-media]', 'voice_debug_active', {
            query_slices: voiceClientUrlQuerySlices(),
            next: 'Включите голосовой ввод на чате (микрофон); затем появятся ws_connecting, ws_open, pcm_uplink_tick, …',
        });
    };
    if (typeof queueMicrotask === 'function') {
        queueMicrotask(run);
    } else {
        window.setTimeout(run, 0);
    }
}
_scheduleVoiceDebugBootstrapNotice();

export const VOICE_CAPTURE_SAMPLE_RATE = 16000;

/** Размер буфера ScriptProcessorNode (степень двойки в допустимом диапазоне). */
const MIC_SCRIPT_PROCESSOR_BUFFER_SIZE = 4096;
/** Интервал опроса AnalyserNode (если доступен только analyser-путь захвата). */
const MIC_CAPTURE_PUMP_MS = 20;
/** fftSize временной волны (AnalyserNode). */
const MIC_CAPTURE_FFT_SIZE = 2048;

function floatSampleToInt16(sample) {
    const s = Math.max(-1, Math.min(1, sample));
    const v = s < 0 ? s * 0x8000 : s * 0x7fff;
    return v | 0;
}

/**
 * @param {Float32Array} channel
 * @returns {ArrayBuffer}
 */
function floatMonoToPcm16ArrayBufferDirect(channel) {
    const pcm = new Int16Array(channel.length);
    for (let i = 0; i < channel.length; i++) {
        pcm[i] = floatSampleToInt16(channel[i]);
    }
    return pcm.buffer;
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
        state.tail = merged.slice(keepFrom);
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
        /** Очередь PCM до OPEN (CONNECTING); иначе pump шлёт, пока сокет не OPEN — теряются. */
        this._pcmOutboundQueue = [];
        this._pcmOutboundQueueCap = 200;
        /** Живой путь uplink (только диагностика). */
        this._voiceUplinkPath = /** @type {'none'|'ac_worklet'|'ac_script'|'ac_analyser'} */ ('none');
        this._pcmUplinkDebugCount = 0;
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
        _voiceClientDebug('ws_open', {
            session_id: this._sessionId,
            uplink_path: this._voiceUplinkPath,
            capture_ac_state:
                this._captureCtx !== null && typeof this._captureCtx.state === 'string'
                    ? this._captureCtx.state
                    : 'none',
        });
        if (this._autoRecord && this._captureCtx !== null && !this._closed) {
            try {
                await this._captureCtx.resume();
            } catch {
                /* второй resume после OPEN: не рвём сессию, см. pump */
            }
        }
    }

    _clearPcmOutboundQueue() {
        this._pcmOutboundQueue.length = 0;
    }

    /**
     * После фактической отправки PCM по WS (диагностика: `voice_debug`).
     * @param {ArrayBuffer} buffer
     */
    _debugAfterPcmSent(buffer) {
        if (!isVoiceClientDebugEnabled()) {
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
     * @param {ArrayBuffer} buffer
     */
    _sendPcmToWebSocket(buffer) {
        if (this._ws === null) {
            return;
        }
        if (this._ws.readyState === WebSocket.OPEN) {
            try {
                this._ws.send(buffer);
                this._debugAfterPcmSent(buffer);
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
        let stream;
        try {
            stream = await getUserMediaCompat({
                audio: {
                    channelCount: { ideal: 1 },
                    echoCancellation: { ideal: true },
                    noiseSuppression: { ideal: true },
                    autoGainControl: { ideal: true },
                },
                video: false,
            });
        } catch {
            stream = await getUserMediaCompat({ audio: true, video: false });
        }
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
        const tracks = this._mediaStream.getAudioTracks();
        const audioTrack =
            tracks.length > 0 && tracks[0].kind === 'audio' ? tracks[0] : null;
        if (audioTrack === null) {
            throw new Error('VoiceMediaSession: в MediaStream нет audio-дорожки');
        }

        this._captureResamplerState = { tail: new Float32Array(0), nextOutSampleIndex: 0 };

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
        this._captureCtx = new Ctx({ latencyHint: 'interactive' });

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
        /** @type {boolean} */
        let usedMicWorklet = false;
        const hasAudioWorklet = typeof ctx.audioWorklet?.addModule === 'function';

        if (hasAudioWorklet) {
            try {
                const workletUrl = new URL(
                    './worklets/voice-mic-capture.processor.js',
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
                    this._onMicWorkletFrame(event.data);
                };
                source.connect(wNode);
                wNode.connect(sinkGain);
                usedMicWorklet = true;
            } catch {
                this._captureWorkletNode = null;
                usedMicWorklet = false;
            }
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
            if (
                this._captureCtx.state === 'suspended'
                || this._captureCtx.state === 'interrupted'
            ) {
                void this._captureCtx.resume().catch(() => {});
            }
        };

        if (typeof window !== 'undefined' && typeof window.setInterval === 'function') {
            if (this._captureResumeWatchdog !== null) {
                window.clearInterval(this._captureResumeWatchdog);
            }
            this._captureResumeWatchdog = window.setInterval(() => {
                if (this._closed || !this._recording || !this._captureCtx) {
                    return;
                }
                const c = this._captureCtx;
                if (c.state === 'closed') {
                    return;
                }
                if (c.state !== 'running') {
                    void c.resume().catch(() => {});
                }
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
                if (
                    this._captureCtx.state === 'suspended'
                    || this._captureCtx.state === 'interrupted'
                ) {
                    void (async () => {
                        try {
                            await this._captureCtx.resume();
                        } catch {
                            /* noop */
                        }
                    })();
                }
            };
            this._captureVisibilityHandler = onVis;
            document.addEventListener('visibilitychange', onVis);
        }
    }

    /**
     * @param {unknown} data — Float32Array с батчем сэмплов из AudioWorklet (transferable).
     */
    _onMicWorkletFrame(data) {
        if (this._closed || !this._captureResamplerState || !this._captureCtx) {
            return;
        }
        if (!(data instanceof Float32Array) || data.length === 0) {
            return;
        }
        try {
            const c = this._captureCtx;
            if (c.state !== 'running') {
                void c.resume();
            }
            const buf = this._encodeMonoFloatToOutboundPcm16(data, this._captureCtx.sampleRate);
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
     * @param {AudioProcessingEvent} ev
     */
    _onMicScriptProcess(ev) {
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
    _encodeMonoFloatToOutboundPcm16(mono, inRate) {
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
        this._mutedTrackDiagnosticTimer = window.setTimeout(() => {
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
            this._capturePumpTimer = window.setTimeout(() => {
                void run();
            }, MIC_CAPTURE_PUMP_MS);
        };
        this._capturePumpTimer = window.setTimeout(() => {
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
        if (ctx.state !== 'running') {
            try {
                await ctx.resume();
            } catch {
                /* noop */
            }
        }
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
            if (isVoiceClientDebugEnabled()) {
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
        } catch {
            return;
        }
        if (!payload || typeof payload !== 'object') return;
        if (isVoiceClientDebugEnabled()) {
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
        this._ws = null;
        this._teardownCapture();
    }

    _teardownCapture() {
        this._recording = false;
        this._captureResamplerState = null;
        if (typeof document !== 'undefined' && this._captureVisibilityHandler !== null) {
            document.removeEventListener('visibilitychange', this._captureVisibilityHandler);
            this._captureVisibilityHandler = null;
        }
        if (this._capturePumpTimer !== null) {
            window.clearTimeout(this._capturePumpTimer);
            this._capturePumpTimer = null;
        }
        if (this._mutedTrackDiagnosticTimer !== null) {
            window.clearTimeout(this._mutedTrackDiagnosticTimer);
            this._mutedTrackDiagnosticTimer = null;
        }
        if (this._captureResumeWatchdog !== null) {
            window.clearInterval(this._captureResumeWatchdog);
            this._captureResumeWatchdog = null;
        }
        if (this._captureCtx !== null) {
            this._captureCtx.onstatechange = null;
        }
        if (this._captureWorkletNode !== null) {
            try {
                this._captureWorkletNode.port.onmessage = null;
                this._captureWorkletNode.port.close();
            } catch {
                /* noop */
            }
            try {
                this._captureWorkletNode.disconnect();
            } catch {
                /* noop */
            }
            this._captureWorkletNode = null;
        }
        if (this._captureScriptProcessor) {
            try {
                this._captureScriptProcessor.onaudioprocess = null;
                this._captureScriptProcessor.disconnect();
            } catch {
                /* noop */
            }
            this._captureScriptProcessor = null;
        }
        if (this._captureKeepAliveOsc) {
            try { this._captureKeepAliveOsc.stop(); } catch { /* noop */ }
            try { this._captureKeepAliveOsc.disconnect(); } catch { /* noop */ }
            this._captureKeepAliveOsc = null;
        }
        if (this._captureKeepAliveGain) {
            try { this._captureKeepAliveGain.disconnect(); } catch { /* noop */ }
            this._captureKeepAliveGain = null;
        }
        if (this._captureAnalyser) {
            try { this._captureAnalyser.disconnect(); } catch { /* noop */ }
            this._captureAnalyser = null;
        }
        if (this._captureSinkGain) {
            try { this._captureSinkGain.disconnect(); } catch { /* noop */ }
            this._captureSinkGain = null;
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
