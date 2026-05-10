/**
 * Сборка VoiceMediaSession + VoiceAgentBridge для flows-чата (страница чата, панель запуска).
 */
import { VoiceMediaSession } from '@platform/lib/voice/voice-media-session.js';
import { VoiceAgentBridge } from '@platform/lib/voice/voice-agent-bridge.js';
import { disposeVoiceMediaThenBridge } from '@platform/lib/voice/dispose-voice-session.js';
import { resolveVoiceHttpOrigin } from '@platform/lib/voice/voice-http-origin.js';
import { normalizeVoiceLocaleForWs } from '@platform/lib/voice/normalize-voice-locale.js';
import {
    fetchFlowVoiceSessionQueryDict,
    normalizeBranchIdForFlowVoiceSessionQuery,
} from '@platform/lib/voice/fetch-flow-voice-session-query.js';

/**
 * Дополнительные заголовки для fetch к voice / A2A (как `getAuthToken` в embed): по умолчанию {}.
 * При встраивании с Bearer переопределите тот же контракт там, где создаёте сессию и Play.
 * @returns {Promise<Record<string, string>>}
 */
export async function flowsVoiceAuxiliaryHttpHeadersStub() {
    return {};
}

export { normalizeVoiceLocaleForWs as normalizeFlowVoiceSttLanguage };

/**
 * `base` и пустое значение — базовый граф (`branch_id=default` на API), не ключ `FlowConfig.branches`.
 * @param {string|null|undefined} branchId
 * @returns {string}
 */
export function branchIdForFlowVoiceSessionQuery(branchId) {
    return normalizeBranchIdForFlowVoiceSessionQuery(branchId, undefined);
}

/**
 * Query-параметры Voice WS: полный набор из `voice-session-query` (STT/TTS/VAD/language),
 * как отдаёт flows API после мержа профиля речи; без обрезки до голоса.
 * @param {object} p
 * @param {string} p.flowId
 * @param {string|null|undefined} p.branchId
 * @returns {Promise<Record<string, string>>}
 */
export async function fetchFlowVoiceWsQuery({ flowId, branchId }) {
    if (typeof flowId !== 'string' || flowId.length === 0) {
        throw new Error('fetchFlowVoiceWsQuery: flow_id required');
    }
    return fetchFlowVoiceSessionQueryDict({
        flowsApiRoot: '/flows',
        flowId,
        branchId,
        credentials: 'include',
        getHeaders: async () => ({}),
    });
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
 * @param {(frame: object) => void} [p.onA2aStreamEvent] — SSE JSON-RPC для релея в `flows/chat`; после `_dispatchA2aEvent` вызывается `feedStreamTtsFromA2aResult`.
 * @param {(e: CustomEvent) => void} [p.onVad]
 * @param {(e: CustomEvent) => void} [p.onTtsState]
 * @param {(e: CustomEvent) => void} [p.onMediaError]
 * @param {() => void} [p.onClosed]
 * @param {string} [p.sttLanguage] — для query `language=` (STT), из `state.i18n.locale`
 * @param {Record<string, string>} [p.voiceWsQuery] — готовые query с сервера (flow speech); мерж после language
 * @param {() => Promise<Record<string, string>>} [p.getVoiceWsQuery] — async загрузка query (приоритет над voiceWsQuery)
 * @param {() => Promise<Record<string, string>>} [p.getHeaders] — как embed `getAuthToken` для A2A `message/stream`
 * @returns {FlowVoiceSessionHandles}
 */
export async function createFlowVoiceSession(p) {
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
        wsQuery.language = normalizeVoiceLocaleForWs(p.sttLanguage);
    }
    let serverQuery = {};
    if (typeof p.getVoiceWsQuery === 'function') {
        const loaded = await p.getVoiceWsQuery();
        if (loaded && typeof loaded === 'object') {
            serverQuery = loaded;
        }
    } else if (p.voiceWsQuery && typeof p.voiceWsQuery === 'object') {
        serverQuery = p.voiceWsQuery;
    }
    Object.assign(wsQuery, serverQuery);
    if (typeof p.sttLanguage === 'string' && p.sttLanguage.trim() !== '') {
        wsQuery.language = normalizeVoiceLocaleForWs(p.sttLanguage);
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
    const getHeaders =
        typeof p.getHeaders === 'function' ? p.getHeaders : flowsVoiceAuxiliaryHttpHeadersStub;
    const bridge = new VoiceAgentBridge({
        mediaSession: media,
        a2aBaseUrl,
        flowId: p.flowId,
        branchId: branchNorm,
        credentials: 'include',
        getHeaders,
        initialContextId: p.initialContextId,
        getContextId: typeof p.getContextId === 'function' ? p.getContextId : undefined,
        getStreamMetadata: typeof p.getStreamMetadata === 'function' ? p.getStreamMetadata : undefined,
        beforeA2aStream: typeof p.beforeA2aStream === 'function' ? p.beforeA2aStream : undefined,
        onA2aStreamEvent: typeof p.onA2aStreamEvent === 'function' ? p.onA2aStreamEvent : undefined,
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
 * @returns {Promise<void>}
 */
export async function disposeFlowVoiceSession(media, bridge) {
    await disposeVoiceMediaThenBridge(media, bridge);
}
