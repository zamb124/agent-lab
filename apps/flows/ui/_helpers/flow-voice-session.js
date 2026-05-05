/**
 * Сборка VoiceMediaSession + VoiceAgentBridge для flows-чата (страница чата, панель запуска).
 */
import { VoiceMediaSession } from '@platform/lib/voice/voice-media-session.js';
import { VoiceAgentBridge } from '@platform/lib/voice/voice-agent-bridge.js';
import { readTtsOutputEnabled } from '@platform/lib/voice/tts-output-pref.js';
import { resolveVoiceHttpOrigin } from '@platform/lib/voice/voice-http-origin.js';

/**
 * Нормализует локаль UI для query `language=` voice WebSocket (ISO 639-1 / префикс BCP-47).
 * @param {string} locale
 * @returns {string}
 */
export function normalizeFlowVoiceSttLanguage(locale) {
    if (typeof locale !== 'string') {
        throw new Error('normalizeFlowVoiceSttLanguage: locale must be string');
    }
    const trimmed = locale.trim();
    if (trimmed === '') {
        throw new Error('normalizeFlowVoiceSttLanguage: locale required');
    }
    const lower = trimmed.toLowerCase();
    const dash = lower.indexOf('-');
    const under = lower.indexOf('_');
    let cut = lower.length;
    if (dash >= 0) {
        cut = Math.min(cut, dash);
    }
    if (under >= 0) {
        cut = Math.min(cut, under);
    }
    const base = lower.slice(0, cut);
    if (base.length < 2) {
        throw new Error('normalizeFlowVoiceSttLanguage: invalid locale');
    }
    return base;
}

/**
 * HTTP-оригин голосового шлюза: тот же host, что у страницы, путь `/voice` (dev: WS-прокси
 * на `voice_service_url`, обычно :8015). Переопределение: meta `platform-voice-origin`.
 * @returns {string}
 */
export function resolveFlowVoiceHttpOrigin() {
    return resolveVoiceHttpOrigin();
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
 * @param {() => string|null|undefined} [p.getContextId] — перед каждым A2A message/stream (из слайса flows/chat).
 * @param {() => Promise<Record<string, unknown>|null|undefined>} [p.getStreamMetadata] — branch/metadata как у текстовой отправки.
 * @param {(text: string) => Promise<void>} [p.beforeA2aStream]
 * @param {(frame: object) => void} [p.onA2aStreamEvent] — SSE JSON-RPC для релея в `flows/chat`.
 * @param {(e: CustomEvent) => void} [p.onVad]
 * @param {(e: CustomEvent) => void} [p.onTtsState]
 * @param {(e: CustomEvent) => void} [p.onMediaError]
 * @param {() => void} [p.onClosed]
 * @param {string} [p.sttLanguage] — для query `language=` (STT), из `state.i18n.locale`
 * @param {() => boolean} [p.getTtsOutputEnabled] — по умолчанию `readTtsOutputEnabled` из localStorage
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

    /** @type {Record<string, string>} */
    const wsQuery = {};
    if (typeof p.sttLanguage === 'string' && p.sttLanguage.trim() !== '') {
        wsQuery.language = normalizeFlowVoiceSttLanguage(p.sttLanguage);
    }

    const mediaOpts = {
        baseUrl: wsBase,
        sessionId,
        companyId: p.companyId,
        autoRecord: true,
    };
    if (Object.keys(wsQuery).length > 0) {
        Object.assign(mediaOpts, { query: wsQuery });
    }
    const media = new VoiceMediaSession(mediaOpts);
    const getTts =
        typeof p.getTtsOutputEnabled === 'function' ? p.getTtsOutputEnabled : () => readTtsOutputEnabled();
    const bridge = new VoiceAgentBridge({
        mediaSession: media,
        a2aBaseUrl,
        flowId: p.flowId,
        branchId: branchNorm,
        credentials: 'include',
        initialContextId: p.initialContextId,
        getContextId: typeof p.getContextId === 'function' ? p.getContextId : undefined,
        getStreamMetadata: typeof p.getStreamMetadata === 'function' ? p.getStreamMetadata : undefined,
        beforeA2aStream: typeof p.beforeA2aStream === 'function' ? p.beforeA2aStream : undefined,
        onA2aStreamEvent: typeof p.onA2aStreamEvent === 'function' ? p.onA2aStreamEvent : undefined,
        getTtsOutputEnabled: getTts,
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
