/**
 * ChatPage — чат с flow.
 *
 * Транспорт: команда отправки `flows/chat/send_requested` идёт через WS
 * (`useOp('flows/chat_send')`); ответ от воркера — push-события `flows/chat/*`,
 * которые слайс `flows/chat` (см. `events/resources/chat.resource.js`)
 * раскладывает в `messagesByContextId[contextId]`.
 *
 * Никаких прямых SSE/`fetch`/`postStream` — всё через шину.
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import '../components/chat/chat-input.js';
import '../components/chat/chat-messages.js';

export class ChatPage extends PlatformPage {
    static properties = {
        flowId: { type: String, attribute: 'flow-id' },
        skillId: { type: String, attribute: 'skill-id' },
        sessionId: { type: String, attribute: 'session-id' },
    };

    static styles = [
        PlatformPage.styles,
        css`
            :host {
                flex: 1;
                min-width: 0;
                min-height: 0;
                display: flex;
                flex-direction: column;
                background: var(--glass-solid-subtle);
                border-radius: var(--radius-lg);
                border: 1px solid var(--border-subtle);
                margin: var(--space-3);
                overflow: hidden;
            }
            .chat-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: var(--space-4) var(--space-6);
                border-bottom: 1px solid var(--border-subtle);
                background: var(--glass-tint-subtle);
            }
            .chat-title {
                display: flex;
                flex-direction: column;
                gap: 2px;
                min-width: 0;
            }
            .chat-flow-name {
                font-size: var(--text-lg);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }
            .chat-skill {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
            .chat-actions {
                display: flex;
                align-items: center;
                gap: var(--space-2);
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
        this.skillId = 'base';
        this.sessionId = '';
        this._chat = this.useResource('flows/chat');
        this._send = this.useOp('flows/chat_send');
        this._cancel = this.useOp('flows/chat_cancel');
        this._sessionState = this.useOp('flows/session_state');
        this._flows = this.useResource('flows/flows');
    }

    connectedCallback() {
        super.connectedCallback();
        this._initOrLoadSession();
    }

    updated(changed) {
        if (super.updated) super.updated(changed);
        if (changed.has('flowId') || changed.has('sessionId') || changed.has('skillId')) {
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
        const messages = (result?.messages || []).map((msg, idx) => {
            const role = typeof msg.role === 'string'
                ? msg.role.toLowerCase()
                : (msg.role?.value || 'assistant');
            let content = msg.content || '';
            if (!content && Array.isArray(msg.parts)) {
                content = msg.parts
                    .filter((p) => p && (p.kind === 'text' || p.text))
                    .map((p) => p.text || '')
                    .join('');
            }
            return {
                id: msg.messageId || msg.id || `msg-${idx}`,
                role: role === 'user' ? 'user' : 'assistant',
                content,
                timestamp: msg.timestamp || new Date().toISOString(),
                taskId: msg.taskId || result?.task_id || null,
                streaming: false,
            };
        });
        this._chat.loadSession({
            sessionId,
            flowId: this.flowId,
            messages,
            taskId: result?.task_id || null,
        });
    }

    _currentMessages() {
        const state = this._chat.state;
        const ctx = state?.currentContextId;
        if (!ctx) return [];
        const bucket = state?.messagesByContextId?.[ctx];
        return bucket?.messages || [];
    }

    _currentFlow() {
        const items = this._flows.items || [];
        return items.find((f) => f && f.flow_id === this.flowId) || null;
    }

    async _onSendMessage(e) {
        const detail = e.detail || {};
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
        if (this.skillId && this.skillId !== 'base') metadata.skill = this.skillId;

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
                        mimeType: file.type || 'application/octet-stream',
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
        this._chat.resetSession();
    }

    _openEditor() {
        if (!this.flowId) return;
        if (this.skillId && this.skillId !== 'base') {
            this.navigate('flow_editor_skill', { flowId: this.flowId, skillId: this.skillId });
        } else {
            this.navigate('flow_editor', { flowId: this.flowId });
        }
    }

    _openSessions() {
        this.openModal('flows.sessions', { flowId: this.flowId });
    }

    _openTracing() {
        const state = this._chat.state;
        const ctxId = state?.currentContextId;
        if (!ctxId || !this.flowId) return;
        this.openModal('flows.tracing', { sessionId: `${this.flowId}:${ctxId}` });
    }

    _openState() {
        const state = this._chat.state;
        const ctxId = state?.currentContextId;
        if (!ctxId || !this.flowId) return;
        this.openModal('flows.state', { sessionId: `${this.flowId}:${ctxId}` });
    }

    render() {
        const flow = this._currentFlow();
        const flowName = flow?.name || this.flowId || this.t('platform_chat.no_flow');
        const messages = this._currentMessages();
        const streaming = Boolean(this._chat.state?.streaming);

        return html`
            <div class="chat-header">
                <div class="chat-title">
                    <span class="chat-flow-name">${flowName}</span>
                    <span class="chat-skill">${this.skillId === 'base' ? this.t('platform_chat.base_skill') : this.skillId}</span>
                </div>
                <div class="chat-actions">
                    <button type="button" class="action-btn" title=${this.t('platform_chat.btn_sessions')} @click=${this._openSessions}>
                        <platform-icon name="history" size="16"></platform-icon>
                    </button>
                    <button type="button" class="action-btn" title=${this.t('platform_chat.btn_traces')} @click=${this._openTracing}>
                        <platform-icon name="activity" size="16"></platform-icon>
                    </button>
                    <button type="button" class="action-btn" title=${this.t('platform_chat.btn_editor')} @click=${this._openEditor}>
                        <platform-icon name="edit" size="16"></platform-icon>
                    </button>
                    <button type="button" class="action-btn" title=${this.t('platform_chat.btn_clear')} @click=${this._onClear}>
                        <platform-icon name="trash" size="16"></platform-icon>
                    </button>
                </div>
            </div>
            <div class="chat-body">
                <chat-messages .messages=${messages}></chat-messages>
                <chat-input
                    ?streaming=${streaming}
                    @send-message=${this._onSendMessage}
                    @stop-stream=${this._onStop}
                ></chat-input>
            </div>
        `;
    }
}

customElements.define('chat-page', ChatPage);
