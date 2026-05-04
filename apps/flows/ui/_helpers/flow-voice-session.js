/**
 * Сборка VoiceMediaSession + VoiceAgentBridge для flows-чата (страница чата, панель запуска).
 */
import { VoiceMediaSession } from '@platform/lib/voice/voice-media-session.js';
import { VoiceAgentBridge } from '@platform/lib/voice/voice-agent-bridge.js';

/**
 * HTTP-оригин голосового шлюза: тот же host, что у страницы, путь `/voice` (dev: WS-прокси
 * на `voice_service_url`, обычно :8015). Переопределение: meta `platform-voice-origin`.
 * @returns {string}
 */
export function resolveFlowVoiceHttpOrigin() {
    if (typeof document !== 'undefined') {
        const el = document.querySelector('meta[name="platform-voice-origin"]');
        if (el) {
            const raw = el.getAttribute('content');
            if (typeof raw === 'string') {
                const trimmed = raw.trim();
                if (trimmed !== '') {
                    return trimmed.replace(/\/$/, '');
                }
            }
        }
    }
    if (typeof window !== 'undefined' && window.location) {
        return `${window.location.protocol}//${window.location.host}/voice`;
    }
    return '';
}

/**
 * Сообщение для toast при ошибке WebSocket: у `error` на сокете часто нет текста.
 * @param {unknown} err
 * @param {(key: string) => string} tFlows — `this.t` при `static i18nNamespace = 'flows'` или эквивалент
 * @returns {string}
 */
export function formatFlowVoiceConnectErrorDetail(err, tFlows) {
    if (err instanceof Error && err.message.trim() !== '') {
        return err.message;
    }
    let asStr = '';
    if (typeof err === 'string') {
        asStr = err;
    } else if (err !== null && err !== undefined) {
        asStr = String(err);
    }
    if (asStr !== '' && asStr !== '[object Event]') {
        return asStr;
    }
    return tFlows('platform_chat.toast_voice_ws_hint');
}

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
    const voiceBaseUrl = resolveFlowVoiceHttpOrigin();
    const pageOrigin =
        typeof window !== 'undefined' && window.location
            ? `${window.location.protocol}//${window.location.host}`
            : '';
    const a2aBaseUrl = `${pageOrigin}/flows`;
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
