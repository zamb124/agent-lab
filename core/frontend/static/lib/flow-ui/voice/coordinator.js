/**
 * Universal Flow UI voice session coordinator (duplex mic + stream TTS).
 * Owned by <platform-flow-ui>; catalog VoiceInput(mode=session) only toggles it.
 */

import { VoiceMediaSession } from '../../voice/voice-media-session.js';
import { VoiceAgentBridge } from '../../voice/voice-agent-bridge.js';
import { disposeVoiceMediaThenBridge } from '../../voice/dispose-voice-session.js';
import {
    feedStreamTtsFromA2aResult,
    setStreamTtsTarget,
    stopStreamTtsPlayback,
} from '../../voice/stream-tts-registry.js';
import { readTtsOutputEnabled } from '../../voice/tts-output-pref.js';
import { resolveVoiceHttpOriginFromFlowsBaseUrl } from '../../voice/voice-http-origin.js';
import { fetchFlowVoiceSessionQueryDict } from '../../voice/fetch-flow-voice-session-query.js';

/**
 * @param {object} host — platform-flow-ui instance
 * @returns {boolean}
 */
export function flowUIVoiceSessionReady(host) {
    const companyId = typeof host.companyId === 'string' ? host.companyId.trim() : '';
    if (companyId === '') {
        return false;
    }
    const voiceBase = resolveHostVoiceBaseUrl(host);
    if (voiceBase === '') {
        return false;
    }
    const flowId = typeof host.flowId === 'string' ? host.flowId.trim() : '';
    const embedId = typeof host.embedId === 'string' ? host.embedId.trim() : '';
    if (flowId === '' && embedId === '') {
        return false;
    }
    const baseUrl = typeof host.baseUrl === 'string' ? host.baseUrl.trim() : '';
    return baseUrl !== '';
}

/**
 * @param {object} host
 * @returns {string}
 */
function resolveHostVoiceBaseUrl(host) {
    if (typeof host.voiceBaseUrl === 'string' && host.voiceBaseUrl.trim() !== '') {
        return host.voiceBaseUrl.trim().replace(/\/$/, '');
    }
    const baseUrl = typeof host.baseUrl === 'string' ? host.baseUrl.trim() : '';
    if (baseUrl === '') {
        return '';
    }
    try {
        if (baseUrl.startsWith('/')) {
            if (typeof window === 'undefined' || !window.location) {
                return '';
            }
            return resolveVoiceHttpOriginFromFlowsBaseUrl(
                `${window.location.origin}${baseUrl}`,
            );
        }
        return resolveVoiceHttpOriginFromFlowsBaseUrl(baseUrl);
    } catch {
        return '';
    }
}

/**
 * @param {object} host
 * @returns {Promise<void>}
 */
export async function startFlowUIVoiceSession(host) {
    if (host._voiceMedia || host._voiceBridge) {
        return;
    }
    if (!flowUIVoiceSessionReady(host)) {
        throw new Error('flow-ui voice: session infrastructure is not ready');
    }
    stopStreamTtsPlayback();
    const voiceBase = resolveHostVoiceBaseUrl(host);
    const companyId = String(host.companyId).trim();
    const flowId = typeof host.flowId === 'string' ? host.flowId.trim() : '';
    const embedId = typeof host.embedId === 'string' ? host.embedId.trim() : '';
    const branchId = typeof host.branchId === 'string' && host.branchId.trim() !== ''
        ? host.branchId.trim()
        : 'default';
    const flowsRoot = String(host.baseUrl).replace(/\/$/, '');
    const credentials = host.credentials === 'omit' ? 'omit' : 'include';
    const getHeaders = async () => (
        typeof host.getRequestHeaders === 'function'
            ? host.getRequestHeaders()
            : {}
    );

    /** @type {Record<string, string>} */
    let query = {};
    if (flowId !== '') {
        query = await fetchFlowVoiceSessionQueryDict({
            flowsApiRoot: flowsRoot,
            flowId,
            branchId,
            credentials,
            getHeaders,
        });
    }

    const sessionId = `flow-ui-${crypto.randomUUID()}`;
    const media = new VoiceMediaSession({
        baseUrl: voiceBase,
        sessionId,
        companyId,
        query,
        autoRecord: true,
    });
    const bridge = new VoiceAgentBridge({
        mediaSession: media,
        a2aBaseUrl: flowsRoot,
        flowId: flowId !== '' ? flowId : undefined,
        embedId: embedId !== '' ? embedId : undefined,
        branchId,
        getHeaders,
        credentials,
        getContextId: () => host.contextId || host.controller?.contextId || null,
        onA2aStreamEvent: (frame) => {
            if (frame && typeof frame === 'object') {
                host.applyA2AFrame(frame);
                if (frame.result != null) {
                    feedStreamTtsFromA2aResult(frame.result);
                }
            }
        },
    });
    host._voiceMedia = media;
    host._voiceBridge = bridge;
    host.voiceSessionActive = true;
    setStreamTtsTarget(media, () => readTtsOutputEnabled());
    bridge.start();
    await media.connect();
    host.requestUpdate();
}

/**
 * @param {object} host
 * @returns {Promise<void>}
 */
export async function stopFlowUIVoiceSession(host) {
    const media = host._voiceMedia;
    const bridge = host._voiceBridge;
    host._voiceMedia = null;
    host._voiceBridge = null;
    host.voiceSessionActive = false;
    await disposeVoiceMediaThenBridge(media, bridge);
    host.requestUpdate();
}

/**
 * @param {object} host
 * @returns {Promise<void>}
 */
export async function toggleFlowUIVoiceSession(host) {
    if (host.voiceSessionActive === true) {
        await stopFlowUIVoiceSession(host);
        return;
    }
    await startFlowUIVoiceSession(host);
}
