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

/** Поверхность ``<platform-flow-ui>``, нужная голосовому координатору. */
export interface FlowUiVoiceHost {
    companyId: string;
    voiceBaseUrl: string;
    baseUrl: string;
    flowId: string;
    embedId: string;
    branchId: string;
    credentials: string;
    getRequestHeaders?: (() => Record<string, string> | Promise<Record<string, string>>) | null;
    voiceSessionActive: boolean;
    client: { contextId: string | null } | null;
    _voiceMedia: VoiceMediaSession | null;
    _voiceBridge: VoiceAgentBridge | null;
    applyA2AFrame(frame: unknown): void;
    requestUpdate(): void;
}

export function flowUIVoiceSessionReady(host: FlowUiVoiceHost): boolean {
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

function resolveHostVoiceBaseUrl(host: FlowUiVoiceHost): string {
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

export async function startFlowUIVoiceSession(host: FlowUiVoiceHost): Promise<void> {
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
        getContextId: () => (host.client ? host.client.contextId : null),
        onA2aStreamEvent: (frame: unknown) => {
            if (frame && typeof frame === 'object') {
                host.applyA2AFrame(frame);
                const result = (frame as Record<string, unknown>).result;
                if (result != null) {
                    feedStreamTtsFromA2aResult(result);
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

export async function stopFlowUIVoiceSession(host: FlowUiVoiceHost): Promise<void> {
    const media = host._voiceMedia;
    const bridge = host._voiceBridge;
    host._voiceMedia = null;
    host._voiceBridge = null;
    host.voiceSessionActive = false;
    await disposeVoiceMediaThenBridge(media, bridge);
    host.requestUpdate();
}

export async function toggleFlowUIVoiceSession(host: FlowUiVoiceHost): Promise<void> {
    if (host.voiceSessionActive === true) {
        await stopFlowUIVoiceSession(host);
        return;
    }
    await startFlowUIVoiceSession(host);
}
