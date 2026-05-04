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
import { createFlowVoiceSession, disposeFlowVoiceSession } from '../_helpers/flow-voice-session.js';
import '../components/chat/chat-input.js';
import '../components/chat/chat-messages.js';
import { asArray, asString, isPlainObject } from '../_helpers/flows-resolvers.js';
import { a2aStateMessagesToChatMessages } from '../_helpers/chat-session-messages.js';
import { resolveFlowsChatTaskId } from '../_helpers/resolve-flows-chat-task-id.js';

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
        this._activeCompanySel = this.select((s) => s.companies.active);
        this._voiceOn = false;
        this._voiceStatus = 'idle';
        /** @type {VoiceMediaSession|null} */
        this._voiceMedia = null;
        /** @type {VoiceAgentBridge|null} */
        this._voiceBridge = null;
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
    }

    disconnectedCallback() {
        if (this._voiceOn) {
            this._stopVoice();
        }
        if (this._chatMql && this._onChatMobileMql) {
            this._chatMql.removeEventListener('change', this._onChatMobileMql);
        }
        document.removeEventListener('pointerdown', this._onDocPointer);
        super.disconnectedCallback();
    }

    async _startVoice() {
        if (this._voiceOn) return;
        if (!this.flowId) return;
        const company = this._activeCompanySel.value;
        const companyId =
            company && typeof company === 'object' && typeof company.company_id === 'string'
                ? company.company_id
                : '';
        if (companyId === '') {
            this._voiceStatus = 'no_company';
            return;
        }
        const initialContextId = this._chat.state?.currentContextId || null;
        const { media, bridge } = createFlowVoiceSession({
            flowId: this.flowId,
            branchId: this.branchId,
            companyId,
            initialContextId,
            onVad: (e) => {
                this._voiceStatus = e.detail.state === 'started' ? 'listening' : 'idle';
            },
            onTtsState: (e) => {
                this._voiceStatus = e.detail.state === 'playing' ? 'speaking' : 'idle';
            },
            onMediaError: () => {
                this._voiceStatus = 'error';
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
            disposeFlowVoiceSession(media, bridge);
            this._voiceStatus = 'error';
            this.toast('flows:platform_chat.toast_voice_error', {
                type: 'error',
                vars: { detail: err && err.message ? err.message : String(err) },
            });
            return;
        }
        bridge.start();
        this._voiceMedia = media;
        this._voiceBridge = bridge;
        this._voiceOn = true;
        this._voiceStatus = 'idle';
    }

    _stopVoice() {
        disposeFlowVoiceSession(this._voiceMedia, this._voiceBridge);
        this._voiceMedia = null;
        this._voiceBridge = null;
        this._voiceOn = false;
        this._voiceStatus = 'idle';
    }

    _toggleVoice() {
        if (this._voiceOn) {
            this._stopVoice();
        } else {
            void this._startVoice();
        }
    }

    updated(changed) {
        if (super.updated) {
            super.updated(changed);
        }
        if ((changed.has('flowId') || changed.has('branchId')) && this._voiceOn) {
            this._stopVoice();
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

        await this._send.run({ flow_id: this.flowId, params });
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
        const state = this._chat.state;
        const taskId = state?.currentTaskId;
        if (!taskId) return;
        void this._cancel.run({ flow_id: this.flowId, task_id: taskId });
    }

    _onClear() {
        this._overflowOpen = false;
        this._chat.resetSession();
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
                    @show-tracing=${this._onChatShowTracing}
                ></chat-messages>
                <chat-input
                    ?show-voice=${hasFlow}
                    ?voice-active=${this._voiceOn}
                    voice-status=${this._voiceStatus}
                    ?streaming=${streaming}
                    @send=${this._onSendMessage}
                    @stop=${this._onStop}
                    @voice-toggle=${this._toggleVoice}
                ></chat-input>
            </div>
        `;
    }
}

customElements.define('chat-page', ChatPage);
