/**
 * Декларация публичной поверхности voice-media-session.js (пока модуль в JS).
 * Контракт: PCM capture → WS /voice/api/ws/session/{id} → события transcript/error.
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

export declare function isVoiceClientDebugEnabled(): boolean;

export declare const VOICE_CAPTURE_SAMPLE_RATE: number;
export declare const VOICE_OUTBOUND_FRAME_SAMPLES: number;

export declare function designFirLowpassHamming(numTaps: number, fcNorm: number): Float32Array;

export declare function applyFirToFloat(
    chunk: Float32Array,
    firTaps: Float32Array,
    firHistory: Float32Array,
): Float32Array;

export interface SpliceTailState {
    tail: Int16Array;
}

export declare function spliceIntoOutboundFrames(
    chunkBuffer: Int16Array,
    tailState: SpliceTailState,
): Int16Array[];

export interface ResamplerState {
    tail: Float32Array;
    nextOutSampleIndex: number;
    inputBase: number;
    firTaps?: Float32Array;
    firHistory?: Float32Array;
    firInputRate?: number;
}

export declare function resampleMonoToPcm16ArrayBuffer(
    channel: Float32Array,
    inRate: number,
    state: ResamplerState,
): ArrayBuffer;

export declare class VoiceMediaSession extends EventTarget {
    constructor(options: VoiceMediaSessionOptions);
    readonly isConnected: boolean;
    connect(): Promise<void>;
    startRecording(): Promise<void>;
    stopPlayback(): void;
    awaitRecordingFinalized(timeoutMs?: number): Promise<void>;
    close(): void;
    addEventListener(
        type: 'transcript' | 'error' | 'recordingFinalized' | string,
        listener: EventListenerOrEventListenerObject | null,
        options?: boolean | AddEventListenerOptions,
    ): void;
    removeEventListener(
        type: 'transcript' | 'error' | 'recordingFinalized' | string,
        listener: EventListenerOrEventListenerObject | null,
        options?: boolean | EventListenerOptions,
    ): void;
}
