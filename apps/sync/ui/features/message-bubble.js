/**
 * MessageBubble — отображение одного сообщения со всеми типами контента
 * Полный паритет с sync1 MessageBubble + MessageContentView
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { glassStyles } from '@platform/lib/styles/shared/glass.styles.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import '../modals/user-info-modal.js';

function toShortUsername(displayName) {
    const raw = (displayName || '').trim();
    if (raw === '') return 'Пользователь';
    const parts = raw.split(/\s+/).filter(p => p.trim() !== '');
    const nonEmail = parts.filter(p => !p.includes('@'));
    if (nonEmail.length > 0) return nonEmail.join(' ');
    const first = parts[0] ?? raw;
    if (first.includes('@')) return first.split('@')[0] || first;
    return raw;
}

function renderContent(content) {
    if (content.type === 'text/plain') {
        const body = content.data?.body;
        if (typeof body !== 'string') throw new Error('Некорректный text/plain контент.');
        return html`<div class="msg-text">${body}</div>`;
    }
    if (content.type === 'code/block') {
        const { language, source } = content.data ?? {};
        if (typeof language !== 'string' || typeof source !== 'string') {
            throw new Error('Некорректный code/block контент.');
        }
        return html`
            <div class="code-block">
                <div class="code-lang">${language}</div>
                <pre class="code-source"><code>${source}</code></pre>
            </div>
        `;
    }
    if (content.type === 'mock/image') {
        const fileId = content.data?.file_id;
        if (typeof fileId !== 'string') throw new Error('Некорректный mock/image контент.');
        return html`<div class="content-ref">Изображение: ${fileId}</div>`;
    }
    if (content.type === 'git/reference') {
        const gitRefId = content.data?.git_ref_id;
        if (typeof gitRefId !== 'string') throw new Error('Некорректный git/reference контент.');
        return html`<div class="content-ref">Git: ${gitRefId}</div>`;
    }
    if (content.type === 'custom_tool_response') {
        const toolName = content.data?.tool_name;
        if (typeof toolName !== 'string') throw new Error('Некорректный custom_tool_response контент.');
        return html`<div class="content-ref">Tool: ${toolName}</div>`;
    }
    throw new Error(`Неподдерживаемый тип контента: ${content.type}`);
}

export class MessageBubble extends PlatformElement {
    static properties = {
        msg: { type: Object },
        isOwn: { type: Boolean },
        canFocusThread: { type: Boolean },
        _profileOpen: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        glassStyles,
        buttonStyles,
        css`
            :host {
                display: block;
            }

            .bubble-row {
                display: flex;
            }

            .bubble-row.own {
                justify-content: flex-end;
            }

            .bubble-row.other {
                justify-content: flex-start;
            }

            .bubble {
                max-width: min(720px, 90%);
                border-radius: var(--radius-2xl);
                padding: var(--space-3) var(--space-4);
                border: 1px solid;
            }

            .bubble.own {
                border-color: rgba(56, 189, 248, 0.2);
                background: rgba(14, 165, 233, 0.12);
            }

            .bubble.other {
                border-color: var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
            }

            .bubble-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-3);
                margin-bottom: var(--space-2);
            }

            .sender-info {
                display: flex;
                align-items: center;
                gap: var(--space-2);
            }

            .sender-btn {
                background: transparent;
                border: none;
                color: var(--text-primary);
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                cursor: pointer;
                padding: 0;
                text-decoration: none;
            }

            .sender-btn:hover {
                text-decoration: underline;
                text-underline-offset: 4px;
            }

            .timestamp {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }

            .thread-btn {
                background: transparent;
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                color: var(--text-secondary);
                font-size: var(--text-xs);
                cursor: pointer;
                padding: 2px 8px;
                transition: all var(--duration-fast);
                flex-shrink: 0;
            }

            .thread-btn:hover {
                background: var(--glass-solid-subtle);
                color: var(--text-primary);
            }

            .contents {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }

            .msg-text {
                font-size: var(--text-base);
                color: var(--text-primary);
                white-space: pre-wrap;
                line-height: 1.6;
            }

            .code-block {
                border-radius: var(--radius-lg);
                border: 1px solid var(--glass-border-subtle);
                background: rgba(0, 0, 0, 0.3);
                padding: var(--space-3);
                backdrop-filter: blur(var(--glass-blur-medium));
            }

            .code-lang {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-bottom: var(--space-2);
            }

            .code-source {
                font-size: var(--text-xs);
                color: var(--text-secondary);
                overflow: auto;
                margin: 0;
            }

            .content-ref {
                font-size: var(--text-sm);
                color: var(--text-secondary);
            }

            .status-pending {
                color: var(--text-tertiary);
            }

            .status-failed {
                color: var(--error);
            }
        `
    ];

    constructor() {
        super();
        this.msg = null;
        this.isOwn = false;
        this.canFocusThread = false;
        this._profileOpen = false;
    }

    _focusThread() {
        if (this.msg?.thread_id) {
            this.emit('focus-thread', { threadId: this.msg.thread_id });
        }
    }

    _renderTimestamp() {
        const { status, sent_at } = this.msg;
        if (status === 'pending') return html`<span class="timestamp status-pending">Отправка...</span>`;
        if (status === 'failed') return html`<span class="timestamp status-failed">Ошибка</span>`;
        return html`<span class="timestamp">${new Date(sent_at).toLocaleString()}</span>`;
    }

    render() {
        if (!this.msg) return html``;
        const { msg, isOwn, canFocusThread } = this;
        const sorted = [...(msg.contents ?? [])].sort((a, b) => a.order - b.order);

        return html`
            <div class="bubble-row ${isOwn ? 'own' : 'other'}">
                <div class="bubble ${isOwn ? 'own' : 'other'}">
                    <div class="bubble-header">
                        <div class="sender-info">
                            ${!isOwn ? html`
                                <button
                                    class="sender-btn"
                                    @click=${() => { this._profileOpen = true; }}
                                >
                                    ${toShortUsername(msg.sender?.display_name ?? '')}
                                </button>
                            ` : ''}
                            ${this._renderTimestamp()}
                        </div>
                        ${canFocusThread ? html`
                            <button class="thread-btn" @click=${this._focusThread}>Тред</button>
                        ` : ''}
                    </div>
                    <div class="contents">
                        ${sorted.map(c => renderContent(c))}
                    </div>
                </div>
            </div>

            ${!isOwn ? html`
                <user-info-modal
                    .open=${this._profileOpen}
                    .sender=${msg.sender}
                    @close=${() => { this._profileOpen = false; }}
                ></user-info-modal>
            ` : ''}
        `;
    }
}

customElements.define('message-bubble', MessageBubble);
