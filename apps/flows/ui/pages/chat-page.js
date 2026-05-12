/**
 * ChatPage — чат с flow.
 *
 * Транспорт: `useOp('flows/chat_send')` запускает `POST /flows/api/v1/{flow_id}`
 * с JSON-RPC `message/stream` по SSE A2A (см. `events/resources/chat.resource.js`).
 * Каждый A2A-фрейм маппится в локальное событие `flows/chat/<verb>`, которое
 * слайс `flows/chat` раскладывает в `messagesByContextId[contextId]`.
 */

import { html, css, nothing } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/layout/page-header.js';
import { dispatchEmbedChatWindowToggle } from '@platform/lib/embed-chat/embed-chat-window-toggle.js';
import {
    createFlowVoiceSession,
    disposeFlowVoiceSession,
    fetchFlowVoiceWsQuery,
    flowsVoiceAuxiliaryHttpHeadersStub,
    formatFlowVoiceConnectErrorDetail,
    normalizeFlowVoiceSttLanguage,
    resolveFlowVoiceHttpOrigin,
} from '../_helpers/flow-voice-session.js';
import '../modals/flows-preview-share-modal.js';
import '../components/chat/chat-input.js';
import '../components/chat/chat-messages.js';
import { asArray, asString, isPlainObject, authActiveCompanyId } from '../_helpers/flows-resolvers.js';
import { a2aStateMessagesToChatMessages } from '../_helpers/chat-session-messages.js';
import { relayA2aVoiceStreamRpcFrame } from '../_helpers/relay-voice-a2a-to-chat.js';
import { resolveFlowsChatTaskId } from '../_helpers/resolve-flows-chat-task-id.js';
import {
    readTtsOutputEnabled,
    toggleTtsOutputEnabled,
    TTS_OUTPUT_CHANGED_EVENT,
    TTS_OUTPUT_STORAGE_KEY,
} from '@platform/lib/voice/tts-output-pref.js';
import { VoiceMediaSession } from '@platform/lib/voice/voice-media-session.js';
import {
    clearStreamTtsTarget,
    primeStreamTtsPlaybackFromUserGesture,
    setStreamTtsTarget,
    stopStreamTtsPlayback,
} from '@platform/lib/voice/stream-tts-registry.js';

export class ChatPage extends PlatformPage {
    static properties = {
        flowId: { type: String, attribute: 'flow-id' },
        branchId: { type: String, attribute: 'branch-id' },
        sessionId: { type: String, attribute: 'session-id' },
        _isMobile: { state: true },
        _overflowOpen: { state: true },
        _voiceOn: { state: true },
        _voiceStatus: { state: true },
    };

    static styles = [
        PlatformPage.styles,
        css`
            :host {
                flex: 1;
                min-width: 0;
                min-height: 0;
                height: 100%;
                display: flex;
                flex-direction: column;
                overflow: hidden;
                background: transparent;
                box-sizing: border-box;
            }
            .chat-branch-hint {
                flex-shrink: 0;
                padding: 0 var(--space-4) var(--space-2);
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
            .flow-chat-header-actions {
                position: relative;
                display: flex;
                align-items: center;
                gap: var(--space-2);
            }
            .flow-chat-overflow-anchor {
                position: relative;
                z-index: 50;
            }
            .action-btn {
                width: 36px;
                height: 36px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-lg);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--border-subtle);
                color: var(--text-secondary);
                cursor: pointer;
            }
            .action-btn:hover {
                background: var(--glass-solid-medium);
                color: var(--text-primary);
            }
            .action-btn-menu {
                width: 100%;
                min-height: 40px;
                display: flex;
                align-items: center;
                gap: var(--space-2);
                background: transparent;
                border: none;
                text-align: left;
                padding: var(--space-2) var(--space-3);
                color: var(--text-primary);
                cursor: pointer;
                font-size: var(--text-sm);
            }
            .action-btn-menu:hover {
                background: var(--glass-hover, color-mix(in srgb, var(--glass-hover) 35%, transparent));
            }
            .menu-flyout {
                position: absolute;
                right: 0;
                top: 100%;
                margin-top: 4px;
                min-width: 220px;
                background: var(--glass-solid-strong);
                border: 1px solid var(--glass-border, var(--border-subtle));
                border-radius: var(--radius-md);
                box-shadow: 0 8px 24px rgba(0, 0, 0, 0.18);
                padding: var(--space-1) 0;
                z-index: 40;
            }
            .chat-body {
                flex: 1;
                min-height: 0;
                display: flex;
                flex-direction: column;
                overflow: hidden;
            }
            chat-messages {
                flex: 1;
                min-height: 0;
                overflow: auto;
            }
        `,
    ];

    constructor() {
        super();
        this.flowId = '';
        this.branchId = 'base';
        this.sessionId = '';
        this._isMobile =
            typeof window !== 'undefined' &&
            typeof window.matchMedia === 'function' &&
            window.matchMedia('(max-width: 767px)').matches;
        this._overflowOpen = false;
        this._chatMql = null;
        this._onChatMobileMql = null;
        this._onDocPointer = (e) => {
            if (!this._overflowOpen) {
                return;
            }
            const path = e.composedPath();
            for (const n of path) {
                if (n === this) {
                    break;
                }
                if (n == null || typeof n !== 'object' || !('classList' in n) || !n.classList) {
                    continue;
                }
                if (n.classList.contains('flow-chat-header-actions')) {
                    return;
                }
            }
            this._overflowOpen = false;
        };
        this._chat = this.useResource('flows/chat');
        this._send = this.useOp('flows/chat_send');
        this._cancel = this.useOp('flows/chat_cancel');
        this._sessionState = this.useOp('flows/session_state');
        this._flows = this.useResource('flows/flows');
        this._activeCompanySel = this.select((s) => authActiveCompanyId(s));
        this._localeSel = this.select((s) => s.i18n.locale);
        this._voiceOn = false;
        this._voiceStatus = 'idle';
        /** @type {VoiceMediaSession|null} */
        this._voiceMedia = null;
        /** @type {VoiceAgentBridge|null} */
        this._voiceBridge = null;
        /** @type {(() => void) | null} */
        this._voiceA2aSettledHandler = null;
        /** @type {((e: Event) => void) | null} */
        this._voiceA2aAbortedHandler = null;
        /** @type {(() => void) | null} */
        this._onTtsOutputPref = null;
        /** @type {((e: StorageEvent) => void) | null} */
        this._onTtsOutputStorage = null;
        /** @type {InstanceType<typeof VoiceMediaSession> | null} */
        this._ttsOnlyMedia = null;
        this._ttsOnlyStreamStarting = false;
    }

    connectedCallback() {
        super.connectedCallback();
        this._initOrLoadSession();
        if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
            return;
        }
        this._chatMql = window.matchMedia('(max-width: 767px)');
        this._onChatMobileMql = () => {
            const next = this._chatMql.matches;
            if (next !== this._isMobile) {
                this._isMobile = next;
            }
        };
        this._chatMql.addEventListener('change', this._onChatMobileMql);
        const next = this._chatMql.matches;
        if (next !== this._isMobile) {
            this._isMobile = next;
        }
        document.addEventListener('pointerdown', this._onDocPointer);
        this.useEvent('flows/chat/compose_edit', (ev) => {
            const p = ev.payload && typeof ev.payload === 'object' ? ev.payload : null;
            const text = p && typeof p.text === 'string' ? p.text : '';
            if (text === '') {
                return;
            }
            const input = this.renderRoot?.querySelector('chat-input');
            if (!input || typeof input.setDraft !== 'function') {
                throw new Error('chat-page: chat-input.setDraft is not available');
            }
            input.setDraft(text);
        });
        this._onTtsOutputPref = () => {
            if (!readTtsOutputEnabled()) {
                this._disposeTtsOnlyStream();
            }
            this.requestUpdate();
        };
        if (typeof window !== 'undefined') {
            window.addEventListener(TTS_OUTPUT_CHANGED_EVENT, this._onTtsOutputPref);
            this._onTtsOutputStorage = (e) => {
                if (e.storageArea === window.localStorage && e.key === TTS_OUTPUT_STORAGE_KEY) {
                    if (!readTtsOutputEnabled()) {
                        this._disposeTtsOnlyStream();
                    }
                    this.requestUpdate();
                }
            };
            window.addEventListener('storage', this._onTtsOutputStorage);
        }
    }

    disconnectedCallback() {
        this._disposeTtsOnlyStream();
        if (this._voiceOn) {
            void this._stopVoice();
        }
        if (this._chatMql && this._onChatMobileMql) {
            this._chatMql.removeEventListener('change', this._onChatMobileMql);
        }
        document.removeEventListener('pointerdown', this._onDocPointer);
        if (typeof window !== 'undefined' && this._onTtsOutputPref) {
            window.removeEventListener(TTS_OUTPUT_CHANGED_EVENT, this._onTtsOutputPref);
            this._onTtsOutputPref = null;
        }
        if (typeof window !== 'undefined' && this._onTtsOutputStorage) {
            window.removeEventListener('storage', this._onTtsOutputStorage);
            this._onTtsOutputStorage = null;
        }
        super.disconnectedCallback();
    }

    _disposeTtsOnlyStream() {
        const m = this._ttsOnlyMedia;
        this._ttsOnlyMedia = null;
        this._ttsOnlyStreamStarting = false;
        clearStreamTtsTarget();
        if (m) {
            try {
                m.close();
            } catch {
                /* noop */
            }
        }
    }

    /**
     * Жест отправки: WS только для TTS (`speak`), без микрофона — цель `feedStreamTtsFromA2aResult`.
     */
    _primeChatTtsOnlyStreamFromUserGesture() {
        if (!readTtsOutputEnabled() || this._voiceOn) {
            return;
        }
        const companyId = asString(this._activeCompanySel.value);
        if (companyId === '' || !this.flowId) {
            return;
        }
        const localeRaw = asString(this._localeSel.value);
        if (this._ttsOnlyMedia !== null && this._ttsOnlyMedia.isConnected) {
            this._ttsOnlyMedia.primePlaybackFromUserGesture();
            setStreamTtsTarget(this._ttsOnlyMedia, readTtsOutputEnabled);
            return;
        }
        if (this._ttsOnlyStreamStarting) {
            const m = this._ttsOnlyMedia;
            if (m && typeof m.primePlaybackFromUserGesture === 'function') {
                m.primePlaybackFromUserGesture();
            }
            if (m) {
                setStreamTtsTarget(m, readTtsOutputEnabled);
            }
            return;
        }
        this._disposeTtsOnlyStream();
        this._ttsOnlyStreamStarting = true;
        const voiceBaseUrl = resolveFlowVoiceHttpOrigin();
        const wsBase = voiceBaseUrl.replace(/^http/, 'ws');
        const sessionId = `tts_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;

        void (async () => {
            /** @type {InstanceType<typeof VoiceMediaSession>|null} */
            let media = null;
            try {
                const serverQuery = await fetchFlowVoiceWsQuery({
                    flowId: this.flowId,
                    branchId: this.branchId,
                });
                /** @type {Record<string, string>} */
                const wsQuery = { ...serverQuery };
                if (localeRaw.trim() !== '') {
                    try {
                        wsQuery.language = normalizeFlowVoiceSttLanguage(localeRaw);
                    } catch {
                        /* noop */
                    }
                }
                const mediaOpts = {
                    baseUrl: wsBase,
                    sessionId,
                    companyId,
                    autoRecord: false,
                };
                if (Object.keys(wsQuery).length > 0) {
                    Object.assign(mediaOpts, { query: wsQuery });
                }
                media = new VoiceMediaSession(mediaOpts);
                media.addEventListener('error', (ev) => {
                    const d = ev.detail && typeof ev.detail === 'object' ? ev.detail : {};
                    const msg =
                        typeof d.detail === 'string' && d.detail.trim() !== ''
                            ? d.detail
                            : typeof d.code === 'string'
                              ? d.code
                              : this.t('platform_chat.toast_voice_ws_hint');
                    this.toast('flows:platform_chat.toast_voice_error', {
                        type: 'error',
                        vars: { detail: msg },
                    });
                });
                media.addEventListener('closed', () => {
                    if (this._ttsOnlyMedia === media) {
                        this._ttsOnlyMedia = null;
                        clearStreamTtsTarget();
                    }
                });
                this._ttsOnlyMedia = media;
                media.primePlaybackFromUserGesture();
                setStreamTtsTarget(media, readTtsOutputEnabled);
                await media.connect();
                if (this._ttsOnlyMedia !== media) {
                    try {
                        media.close();
                    } catch {
                        /* noop */
                    }
                    return;
                }
                if (this._voiceOn || !readTtsOutputEnabled()) {
                    this._ttsOnlyMedia = null;
                    clearStreamTtsTarget();
                    try {
                        media.close();
                    } catch {
                        /* noop */
                    }
                    return;
                }
                setStreamTtsTarget(media, readTtsOutputEnabled);
            } catch (err) {
                if (this._ttsOnlyMedia === media) {
                    this._ttsOnlyMedia = null;
                }
                clearStreamTtsTarget();
                if (media !== null) {
                    try {
                        media.close();
                    } catch {
                        /* noop */
                    }
                }
                this.toast('flows:platform_chat.toast_voice_error', {
                    type: 'error',
                    vars: {
                        detail: formatFlowVoiceConnectErrorDetail(err, (key) => this.t(key)),
                    },
                });
            } finally {
                this._ttsOnlyStreamStarting = false;
            }
        })();
    }

    async _startVoice() {
        if (this._voiceOn) return;
        this._disposeTtsOnlyStream();
        if (!this.flowId) return;
        const companyId = asString(this._activeCompanySel.value);
        if (companyId === '') {
            this._voiceStatus = 'no_company';
            this.toast('flows:platform_chat.toast_voice_no_company', { type: 'warning' });
            return;
        }
        const chatCtx = this._chat.state?.currentContextId;
        if (typeof chatCtx !== 'string' || chatCtx.length === 0) {
            this._chat.initSession({ flowId: this.flowId });
        }
        const initialContextId = this._chat.state?.currentContextId || null;
        const localeRaw = asString(this._localeSel.value);
        const sttLanguage = normalizeFlowVoiceSttLanguage(localeRaw);
        /** @type {{ contextId: string|null, taskId: string|null, taskPrimed: boolean }} */
        const voiceStreamRelayState = {
            contextId: null,
            taskId: null,
            taskPrimed: false,
        };
        const { media, bridge } = await createFlowVoiceSession({
            flowId: this.flowId,
            branchId: this.branchId,
            companyId,
            sttLanguage,
            initialContextId,
            getVoiceWsQuery: async () => {
                return fetchFlowVoiceWsQuery({
                    flowId: this.flowId,
                    branchId: this.branchId,
                });
            },
            getContextId: () => {
                const cid = this._chat.state?.currentContextId;
                return typeof cid === 'string' && cid.length > 0 ? cid : null;
            },
            beforeA2aStream: async (text) => {
                stopStreamTtsPlayback();
                const ctx = this._chat.state?.currentContextId;
                if (typeof ctx !== 'string' || ctx.length === 0) {
                    throw new Error('flows chat voice: отсутствует currentContextId');
                }
                voiceStreamRelayState.contextId = ctx;
                voiceStreamRelayState.taskId = null;
                voiceStreamRelayState.taskPrimed = false;
                const trimmed = typeof text === 'string' ? text.trim() : '';
                if (trimmed.length === 0) {
                    throw new Error('flows chat voice: пустой транскрипт');
                }
                const userMessage = {
                    id: `user_${Date.now()}`,
                    role: 'user',
                    content: trimmed,
                    timestamp: new Date().toISOString(),
                    files: [],
                };
                this._chat.addUserMessage({ contextId: ctx, message: userMessage });
                this.dispatch('flows/run/flow_started', {}, { source: 'http' });
            },
            onA2aStreamEvent: (frame) => {
                relayA2aVoiceStreamRpcFrame(
                    {
                        dispatch: (t, p, m) => {
                            this.dispatch(t, p, m);
                        },
                    },
                    voiceStreamRelayState,
                    frame,
                    null,
                );
            },
            onVad: (e) => {
                this._voiceStatus = e.detail.state === 'started' ? 'listening' : 'idle';
            },
            onTtsState: (e) => {
                this._voiceStatus = e.detail.state === 'playing' ? 'speaking' : 'idle';
            },
            onMediaError: (e) => {
                this._voiceStatus = 'error';
                const d = isPlainObject(e.detail) ? e.detail : {};
                const msg =
                    typeof d.detail === 'string' && d.detail.trim() !== ''
                        ? d.detail
                        : typeof d.code === 'string'
                          ? d.code
                          : this.t('platform_chat.toast_voice_ws_hint');
                this.toast('flows:platform_chat.toast_voice_error', {
                    type: 'error',
                    vars: { detail: msg },
                });
            },
            onClosed: () => {
                this._voiceMedia = null;
                this._voiceBridge = null;
                this._voiceOn = false;
                this._voiceStatus = 'closed';
            },
        });

        try {
            await media.connect();
        } catch (err) {
            await disposeFlowVoiceSession(media, bridge);
            this._voiceStatus = 'error';
            this.toast('flows:platform_chat.toast_voice_error', {
                type: 'error',
                vars: {
                    detail: formatFlowVoiceConnectErrorDetail(err, (key) => this.t(key)),
                },
            });
            return;
        }
        const onVoiceA2aSettled = () => {
            this.dispatch('flows/run/flow_done', {}, { source: 'http' });
        };
        const onVoiceA2aAborted = (ev) => {
            const ce = /** @type {CustomEvent<Record<string, unknown>>} */ (ev);
            const d =
                ce.detail !== null && typeof ce.detail === 'object'
                    ? /** @type {Record<string, unknown>} */ (ce.detail)
                    : null;
            const task_id =
                d && typeof d.task_id === 'string' ? d.task_id : null;
            const context_id =
                d && typeof d.context_id === 'string' ? d.context_id : null;
            this.dispatch('flows/chat/a2a_interrupted', { task_id, context_id }, { source: 'local' });
        };
        this._voiceA2aSettledHandler = onVoiceA2aSettled;
        this._voiceA2aAbortedHandler = onVoiceA2aAborted;
        bridge.addEventListener('a2aSettled', onVoiceA2aSettled);
        bridge.addEventListener('a2aAborted', onVoiceA2aAborted);
        bridge.start();
        setStreamTtsTarget(media, readTtsOutputEnabled);
        this._voiceMedia = media;
        this._voiceBridge = bridge;
        this._voiceOn = true;
        this._voiceStatus = 'idle';
    }

    async _stopVoice() {
        if (this._voiceBridge && this._voiceA2aSettledHandler) {
            this._voiceBridge.removeEventListener('a2aSettled', this._voiceA2aSettledHandler);
            this._voiceA2aSettledHandler = null;
        }
        if (this._voiceBridge && this._voiceA2aAbortedHandler) {
            this._voiceBridge.removeEventListener('a2aAborted', this._voiceA2aAbortedHandler);
            this._voiceA2aAbortedHandler = null;
        }
        await disposeFlowVoiceSession(this._voiceMedia, this._voiceBridge);
        this._voiceMedia = null;
        this._voiceBridge = null;
        this._voiceOn = false;
        this._voiceStatus = 'idle';
    }

    _toggleVoice() {
        if (this._voiceOn) {
            void this._stopVoice();
        } else {
            void this._startVoice();
        }
    }

    _onTtsOutputToggle() {
        toggleTtsOutputEnabled();
        if (!readTtsOutputEnabled()) {
            this._disposeTtsOnlyStream();
        }
        this.requestUpdate();
    }

    updated(changed) {
        if (super.updated) {
            super.updated(changed);
        }
        if ((changed.has('flowId') || changed.has('branchId')) && this._voiceOn) {
            void this._stopVoice();
        }
        if (
            (changed.has('flowId') || changed.has('branchId')) &&
            !this._voiceOn
        ) {
            this._disposeTtsOnlyStream();
        }
        if (changed.has('flowId') || changed.has('sessionId') || changed.has('branchId')) {
            this._initOrLoadSession();
        }
    }

    _initOrLoadSession() {
        if (typeof this.flowId !== 'string' || this.flowId.length === 0) return;
        if (this.sessionId && this.sessionId.length > 0) {
            void this._restoreSessionFromUrl(this.sessionId);
            return;
        }
        this._chat.initSession({ flowId: this.flowId });
    }

    async _restoreSessionFromUrl(sessionId) {
        const result = await this._sessionState.run({ session_id: sessionId });
        const rawMessages = isPlainObject(result) && Array.isArray(result.messages) ? result.messages : [];
        const resultTaskId = isPlainObject(result) && typeof result.task_id === 'string' ? result.task_id : null;
        const messages = a2aStateMessagesToChatMessages(rawMessages, resultTaskId);
        this._chat.loadSession({
            sessionId,
            flowId: this.flowId,
            messages,
            taskId: resultTaskId,
        });
    }

    _currentMessages() {
        const state = this._chat.state;
        const ctx = state?.currentContextId;
        if (!ctx) return [];
        const buckets = isPlainObject(state) && isPlainObject(state.messagesByContextId)
            ? state.messagesByContextId
            : null;
        const bucket = buckets !== null && isPlainObject(buckets[ctx]) ? buckets[ctx] : null;
        return bucket !== null && Array.isArray(bucket.messages) ? bucket.messages : [];
    }

    _currentRunTrace() {
        const state = this._chat.state;
        if (!isPlainObject(state)) {
            return [];
        }
        const ctx = typeof state.currentContextId === 'string' ? state.currentContextId : null;
        if (!ctx) {
            return [];
        }
        const by = state.runTraceByContextId;
        if (!isPlainObject(by)) {
            return [];
        }
        const list = by[ctx];
        return Array.isArray(list) ? list : [];
    }

    _currentFlow() {
        const items = asArray(this._flows.items);
        const found = items.find((f) => f && f.flow_id === this.flowId);
        return found ? found : null;
    }

    async _onSendMessage(e) {
        const detail = isPlainObject(e.detail) ? e.detail : {};
        const text = typeof detail.message === 'string' ? detail.message : '';
        const files = Array.isArray(detail.files) ? detail.files : [];
        if (!text && files.length === 0) return;

        const state = this._chat.state;
        const contextId = state?.currentContextId;
        if (!contextId) return;

        stopStreamTtsPlayback();

        const fileParts = await Promise.all(files.map((file) => this._fileToPart(file)));

        const userMessage = {
            id: `user_${Date.now()}`,
            role: 'user',
            content: text,
            timestamp: new Date().toISOString(),
            files: files.map((f) => ({ name: f.name, size: f.size, type: f.type })),
        };
        this._chat.addUserMessage({ contextId, message: userMessage });

        const a2aMessage = {
            messageId: `${Date.now()}_${Math.random().toString(36).slice(2, 11)}`,
            role: 'user',
            parts: [
                { kind: 'text', text },
                ...fileParts,
            ],
            contextId,
        };

        const metadata = {};
        if (this.branchId && this.branchId !== 'base') metadata.branch = this.branchId;

        const params = { message: a2aMessage };
        if (Object.keys(metadata).length > 0) params.metadata = metadata;

        if (readTtsOutputEnabled() && !this._voiceOn) {
            primeStreamTtsPlaybackFromUserGesture();
            this._primeChatTtsOnlyStreamFromUserGesture();
            await this._awaitChatTtsOnlyReady();
        }

        await this._send.run({ flow_id: this.flowId, params });
    }

    /**
     * Пока tts-only WS коннектится, `feedStreamTtsFromA2aResult` без цели; ждём перед SSE.
     */
    async _awaitChatTtsOnlyReady() {
        const t0 = Date.now();
        const maxMs = 2500;
        while (Date.now() - t0 < maxMs) {
            if (this._voiceOn || !readTtsOutputEnabled()) {
                return;
            }
            if (!this._ttsOnlyStreamStarting && this._ttsOnlyMedia !== null && this._ttsOnlyMedia.isConnected) {
                return;
            }
            await new Promise((r) => setTimeout(r, 40));
        }
    }

    async _fileToPart(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => {
                const result = reader.result;
                const base64 = typeof result === 'string' ? result.split(',')[1] : '';
                resolve({
                    kind: 'file',
                    file: {
                        name: file.name,
                        mimeType: typeof file.type === 'string' && file.type.length > 0 ? file.type : 'application/octet-stream',
                        bytes: base64,
                    },
                });
            };
            reader.onerror = reject;
            reader.readAsDataURL(file);
        });
    }

    _onStop() {
        if (this._cancel.busy) return;
        const state = this._chat.state;
        const taskId = state?.currentTaskId;
        if (!taskId) return;
        void this._cancel.run({ flow_id: this.flowId, task_id: taskId });
    }

    _onClear() {
        this._overflowOpen = false;
        this._disposeTtsOnlyStream();
        this._chat.resetSession();
    }

    _onFlowsChatBack() {
        this.navigate('list', {});
    }

    _openEditor() {
        this._overflowOpen = false;
        if (!this.flowId) return;
        if (this.branchId && this.branchId !== 'base') {
            this.navigate('flow_editor_branch', { flowId: this.flowId, branchId: this.branchId });
        } else {
            this.navigate('flow_editor', { flowId: this.flowId });
        }
    }

    _openTriggers() {
        this._overflowOpen = false;
        if (typeof this.flowId !== 'string' || this.flowId.length === 0) {
            return;
        }
        this.openModal('flows.triggers', { flowId: this.flowId });
    }

    _openTracingModalFromDetail(detail) {
        this._overflowOpen = false;
        const state = this._chat.state;
        const ctxId = state?.currentContextId;
        if (!ctxId || !this.flowId) {
            return;
        }
        const sessionId = `${this.flowId}:${ctxId}`;
        const taskId =
            detail && typeof detail === 'object' && typeof detail.taskId === 'string' && detail.taskId.length > 0
                ? detail.taskId
                : '';
        const props = { sessionId };
        if (taskId.length > 0) {
            props.taskId = taskId;
        }
        this.openModal('flows.tracing', props);
    }

    _openTracing() {
        this._openTracingModalFromDetail(null);
    }

    _onChatShowTracing(e) {
        this._openTracingModalFromDetail(e.detail);
    }

    _openLogs() {
        this._overflowOpen = false;
        const state = this._chat.state;
        const ctxId = state?.currentContextId;
        if (!ctxId || !this.flowId) {
            return;
        }
        const sessionId = `${this.flowId}:${ctxId}`;
        const taskId = resolveFlowsChatTaskId(this._chat.state);
        const props = { sessionId };
        if (taskId.length > 0) {
            props.taskId = taskId;
        }
        this.openModal('flows.logs', props);
    }

    _openLara() {
        this._overflowOpen = false;
        dispatchEmbedChatWindowToggle('flows-lara-open', { open: true });
    }

    _openPreviewShare() {
        this._overflowOpen = false;
        if (typeof this.flowId !== 'string' || this.flowId.length === 0) {
            return;
        }
        const raw =
            typeof this.branchId === 'string' && this.branchId.trim() !== '' ? this.branchId.trim() : 'base';
        const bid = raw === 'base' ? 'default' : raw;
        this.openModal('flows.preview_share', { flowId: this.flowId, branchId: bid });
    }

    _toggleOverflow(e) {
        e.stopPropagation();
        this._overflowOpen = !this._overflowOpen;
    }

    _renderDesktopActions(hasFlow) {
        return html`
            <button
                type="button"
                class="action-btn"
                title=${this.t('editor_header.lara')}
                aria-label=${this.t('editor_header.lara')}
                @click=${this._openLara}
            >
                <platform-icon name="ai" size="16"></platform-icon>
            </button>
            ${hasFlow
                ? html`
                    <button
                        type="button"
                        class="action-btn"
                        title=${this.t('editor_header.share_preview')}
                        aria-label=${this.t('editor_header.share_preview')}
                        @click=${this._openPreviewShare}
                    >
                        <platform-icon name="share" size="16"></platform-icon>
                    </button>
                `
                : nothing}
            ${hasFlow
                ? html`
                    <button
                        type="button"
                        class="action-btn"
                        title=${this.t('flows_sidebar.footer_triggers')}
                        aria-label=${this.t('flows_sidebar.footer_triggers')}
                        @click=${this._openTriggers}
                    >
                        <platform-icon name="zap" size="16"></platform-icon>
                    </button>
                `
                : nothing}
            <button
                type="button"
                class="action-btn"
                title=${this.t('platform_chat.btn_traces')}
                aria-label=${this.t('platform_chat.btn_traces')}
                @click=${this._openTracing}
            >
                <platform-icon name="chart" size="16"></platform-icon>
            </button>
            <button
                type="button"
                class="action-btn"
                title=${this.t('platform_chat.btn_logs')}
                aria-label=${this.t('platform_chat.btn_logs')}
                @click=${this._openLogs}
            >
                <platform-icon name="file-text" size="16"></platform-icon>
            </button>
            <button
                type="button"
                class="action-btn"
                title=${this.t('platform_chat.btn_editor')}
                aria-label=${this.t('platform_chat.btn_editor')}
                @click=${this._openEditor}
            >
                <platform-icon name="edit" size="16"></platform-icon>
            </button>
            <button
                type="button"
                class="action-btn"
                title=${this.t('platform_chat.btn_clear')}
                aria-label=${this.t('platform_chat.btn_clear')}
                @click=${this._onClear}
            >
                <platform-icon name="trash" size="16"></platform-icon>
            </button>
        `;
    }

    _renderMobileActions(hasFlow) {
        return html`
            <div class="flow-chat-header-actions" @click=${(e) => e.stopPropagation()}>
                <button
                    type="button"
                    class="action-btn"
                    title=${this.t('editor_header.lara')}
                    aria-label=${this.t('editor_header.lara')}
                    @click=${this._openLara}
                >
                    <platform-icon name="ai" size="16"></platform-icon>
                </button>
                <div class="flow-chat-overflow-anchor">
                    <button
                        type="button"
                        class="action-btn"
                        title=${this.t('platform_chat.overflow_aria')}
                        aria-label=${this.t('platform_chat.overflow_aria')}
                        aria-expanded=${this._overflowOpen ? 'true' : 'false'}
                        @click=${this._toggleOverflow}
                    >
                        <platform-icon name="more-vertical" size="20"></platform-icon>
                    </button>
                    ${this._overflowOpen
                        ? html`
                            <div class="menu-flyout" @click=${(e) => e.stopPropagation()}>
                                ${hasFlow
                                    ? html`
                                        <button type="button" class="action-btn-menu" @click=${this._openPreviewShare}>
                                            <platform-icon name="share" size="16"></platform-icon>
                                            ${this.t('editor_header.share_preview')}
                                        </button>
                                    `
                                    : nothing}
                                ${hasFlow
                                    ? html`
                                        <button type="button" class="action-btn-menu" @click=${this._openTriggers}>
                                            <platform-icon name="zap" size="16"></platform-icon>
                                            ${this.t('flows_sidebar.footer_triggers')}
                                        </button>
                                    `
                                    : nothing}
                                <button type="button" class="action-btn-menu" @click=${this._openTracing}>
                                    <platform-icon name="chart" size="16"></platform-icon>
                                    ${this.t('platform_chat.btn_traces')}
                                </button>
                                <button type="button" class="action-btn-menu" @click=${this._openLogs}>
                                    <platform-icon name="file-text" size="16"></platform-icon>
                                    ${this.t('platform_chat.btn_logs')}
                                </button>
                                <button type="button" class="action-btn-menu" @click=${this._openEditor}>
                                    <platform-icon name="edit" size="16"></platform-icon>
                                    ${this.t('platform_chat.btn_editor')}
                                </button>
                                <button type="button" class="action-btn-menu" @click=${this._onClear}>
                                    <platform-icon name="trash" size="16"></platform-icon>
                                    ${this.t('platform_chat.btn_clear')}
                                </button>
                            </div>
                        `
                        : nothing}
                </div>
            </div>
        `;
    }

    render() {
        const flow = this._currentFlow();
        let flowName;
        if (flow && typeof flow.name === 'string' && flow.name.length > 0) {
            flowName = flow.name;
        } else if (typeof this.flowId === 'string' && this.flowId.length > 0) {
            flowName = this.flowId;
        } else {
            flowName = this.t('platform_chat.no_flow');
        }
        const branchLabel = this.branchId === 'base' ? this.t('platform_chat.base_branch') : this.branchId;
        const hasFlow = typeof this.flowId === 'string' && this.flowId.length > 0;
        const messages = this._currentMessages();
        const runTrace = this._currentRunTrace();
        const streaming = Boolean(this._chat.state?.streaming);
        const currentTaskId = asString(this._chat.state?.currentTaskId);

        return html`
            <page-header
                title=${flowName}
                subtitle=${branchLabel}
                actions-overflow="visible"
            >
                ${this._isMobile
                    ? html`
                          <button
                              type="button"
                              slot="leading"
                              class="page-header-leading-btn"
                              title=${this.t('platform_chat.title_back_to_flows_list')}
                              aria-label=${this.t('platform_chat.title_back_to_flows_list')}
                              @click=${this._onFlowsChatBack}
                          >
                              <platform-icon name="arrow-left" size="20"></platform-icon>
                          </button>
                      `
                    : nothing}
                <div slot="actions">
                    ${this._isMobile
                        ? this._renderMobileActions(hasFlow)
                        : html`<div class="flow-chat-header-actions">${this._renderDesktopActions(hasFlow)}</div>`}
                </div>
            </page-header>
            ${this._isMobile ? html`<div class="chat-branch-hint">${branchLabel}</div>` : nothing}
            <div class="chat-body">
                <chat-messages
                    .messages=${messages}
                    .runTrace=${runTrace}
                    .currentTaskId=${currentTaskId}
                    .voicePlayGetHeaders=${flowsVoiceAuxiliaryHttpHeadersStub}
                    @show-tracing=${this._onChatShowTracing}
                ></chat-messages>
                <chat-input
                    ?show-voice=${hasFlow}
                    ?voice-active=${this._voiceOn}
                    voice-status=${this._voiceStatus}
                    ?tts-output-enabled=${readTtsOutputEnabled()}
                    ?streaming=${streaming}
                    .cancelBusy=${this._cancel.busy}
                    @send=${this._onSendMessage}
                    @stop=${this._onStop}
                    @voice-toggle=${this._toggleVoice}
                    @tts-output-toggle=${this._onTtsOutputToggle}
                ></chat-input>
            </div>
        `;
    }
}

customElements.define('chat-page', ChatPage);
