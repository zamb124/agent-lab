/**
 * Регистрация активной `VoiceMediaSession` для авто-TTS из A2A-кадров (`feedStreamTtsFromA2aResult`).
 * Очищается при `disposeVoiceMediaThenBridge` / смене вкладки голоса.
 */

import { feedSpeakableTtsFromA2aResult } from './a2a-result-tts.js';

import type { VoiceMediaSession } from './voice-media-session.js';

export interface StreamTtsTarget {
    mediaSession: VoiceMediaSession;
    getTtsOutputEnabled: () => boolean;
}

let _target: StreamTtsTarget | null = null;

/**
 * @param {import('./voice-media-session.js').VoiceMediaSession} mediaSession
 * @param {() => boolean} getTtsOutputEnabled
 */
export function setStreamTtsTarget(mediaSession: VoiceMediaSession, getTtsOutputEnabled: () => boolean): void {
    if (!mediaSession) {
        throw new Error('setStreamTtsTarget: mediaSession required');
    }
    if (typeof getTtsOutputEnabled !== 'function') {
        throw new Error('setStreamTtsTarget: getTtsOutputEnabled required');
    }
    _target = { mediaSession, getTtsOutputEnabled };
}

export function clearStreamTtsTarget(): void {
    _target = null;
}

/**
 * Barge-in: остановить воспроизведение текущего ответа (WS downstream).
 * Вызывать при новом сообщении пользователя (текст/голос), чтобы единообразно
 * прерывать озвучку предыдущего ответа во всех чатах.
 */
export function stopStreamTtsPlayback(): void {
    if (_target === null) {
        return;
    }
    const media = _target.mediaSession;
    if (media && typeof media.stopPlayback === 'function') {
        media.stopPlayback();
    }
}

/** Синхронно из цепочки user gesture (отправка, микрофон). Иначе Chromium оставляет playback AudioContext в suspended. */
export function primeStreamTtsPlaybackFromUserGesture(): void {
    if (_target === null) {
        return;
    }
    if (!_target.getTtsOutputEnabled()) {
        return;
    }
    const media = _target.mediaSession;
    if (media && typeof media.primePlaybackFromUserGesture === 'function') {
        media.primePlaybackFromUserGesture();
    }
}

/**
 * @param {object | null | undefined} result — `frame.result` из A2A SSE.
 */
export function feedStreamTtsFromA2aResult(result: object | null | undefined): void {
    if (_target === null || result === null || typeof result !== 'object') {
        return;
    }
    feedSpeakableTtsFromA2aResult(
        _target.mediaSession,
        result,
        _target.getTtsOutputEnabled,
    );
}
