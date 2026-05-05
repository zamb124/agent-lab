import { clearStreamTtsTarget } from './stream-tts-registry.js';

/**
 * Унифицированное завершение сессии (media + VoiceAgentBridge):
 * пока WS открыт — server-side flush STT (``end_recording`` → ``finalize_done``), затем
 * ``bridge.stop()``: нефинальный partial уходит в одно ``message/stream``; ответ на уже
 *   запущенный запрос после финального transcript **не** обрывается (отмена только barge-in /
 *   ``tasks/cancel``), затем ``media.close()``.
 *
 * @param {import('./voice-media-session.js').VoiceMediaSession|null} media
 * @param {import('./voice-agent-bridge.js').VoiceAgentBridge|null} bridge
 * @param {{ finalizeTimeoutMs?: number }} [opts]
 * @returns {Promise<void>}
 */
export async function disposeVoiceMediaThenBridge(media, bridge, opts = {}) {
    clearStreamTtsTarget();
    const finalizeTimeoutMs =
        typeof opts.finalizeTimeoutMs === 'number' && opts.finalizeTimeoutMs > 0
            ? opts.finalizeTimeoutMs
            : 8000;
    try {
        if (
            media &&
            media.isConnected === true &&
            typeof media.awaitRecordingFinalized === 'function'
        ) {
            await media.awaitRecordingFinalized(finalizeTimeoutMs);
        }
    } catch {
        /* noop */
    }
    if (bridge) {
        try {
            bridge.stop();
        } catch {
            /* noop */
        }
    }
    if (media) {
        try {
            media.close();
        } catch {
            /* noop */
        }
    }
}
