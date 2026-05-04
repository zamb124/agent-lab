/**
 * Сборка VoiceMediaSession + VoiceAgentBridge для flows-чата (страница чата, панель запуска).
 */
import { VoiceMediaSession } from '@platform/lib/voice/voice-media-session.js';
import { VoiceAgentBridge } from '@platform/lib/voice/voice-agent-bridge.js';

/**
 * @typedef {object} FlowVoiceSessionHandles
 * @property {InstanceType<typeof VoiceMediaSession>} media
 * @property {InstanceType<typeof VoiceAgentBridge>} bridge
 */

/**
 * @param {object} p
 * @param {string} p.flowId
 * @param {string|null|undefined} p.branchId
 * @param {string} p.companyId
 * @param {string|null} p.initialContextId
 * @param {(e: CustomEvent) => void} [p.onVad]
 * @param {(e: CustomEvent) => void} [p.onTtsState]
 * @param {(e: CustomEvent) => void} [p.onMediaError]
 * @param {() => void} [p.onClosed]
 * @returns {FlowVoiceSessionHandles}
 */
export function createFlowVoiceSession(p) {
    const origin =
        typeof window !== 'undefined' && window.location
            ? `${window.location.protocol}//${window.location.host}`
            : '';
    const voiceBaseUrl = `${origin}/voice`;
    const a2aBaseUrl = `${origin}/flows`;
    const wsBase = voiceBaseUrl.replace(/^http/, 'ws');
    const sessionId = `voice_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
    const branchNorm = p.branchId && p.branchId !== 'base' ? p.branchId : null;

    const media = new VoiceMediaSession({
        baseUrl: wsBase,
        sessionId,
        companyId: p.companyId,
        autoRecord: true,
    });
    const bridge = new VoiceAgentBridge({
        mediaSession: media,
        a2aBaseUrl,
        flowId: p.flowId,
        branchId: branchNorm,
        credentials: 'include',
        initialContextId: p.initialContextId,
    });

    if (typeof p.onVad === 'function') {
        media.addEventListener('vad', p.onVad);
    }
    if (typeof p.onTtsState === 'function') {
        media.addEventListener('ttsState', p.onTtsState);
    }
    if (typeof p.onMediaError === 'function') {
        media.addEventListener('error', p.onMediaError);
    }
    if (typeof p.onClosed === 'function') {
        media.addEventListener('closed', p.onClosed);
    }

    return { media, bridge };
}

/**
 * @param {InstanceType<typeof VoiceMediaSession>|null} media
 * @param {InstanceType<typeof VoiceAgentBridge>|null} bridge
 */
export function disposeFlowVoiceSession(media, bridge) {
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
