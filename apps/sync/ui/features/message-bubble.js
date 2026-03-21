/**
 * MessageBubble — отображение одного сообщения со всеми типами контента
 * Полный паритет с sync1 MessageBubble + MessageContentView
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { glassStyles } from '@platform/lib/styles/shared/glass.styles.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import '../modals/user-info-modal.js';

function formatMessageTime(iso) {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '';
    return d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
}

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

function initialsForAvatar(displayName) {
    const label = toShortUsername(displayName);
    if (label === 'Пользователь') return '?';
    const parts = label.split(/\s+/).filter(Boolean);
    if (parts.length >= 2) {
        const a = parts[0][0] ?? '';
        const b = parts[1][0] ?? '';
        return (a + b).toUpperCase();
    }
    const w = parts[0] ?? label;
    return w.slice(0, 2).toUpperCase();
}

function hueFromUserId(userId) {
    let h = 0;
    for (let i = 0; i < userId.length; i++) {
        h = (h * 31 + userId.charCodeAt(i)) >>> 0;
    }
    return h % 360;
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
                align-items: flex-end;
                gap: var(--space-2);
            }

            .bubble-row.own {
                justify-content: flex-end;
            }

            .bubble-row.other {
                justify-content: flex-start;
            }

            .avatar-slot {
                flex: 0 0 auto;
                width: 36px;
                height: 36px;
                border-radius: 50%;
                overflow: hidden;
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                box-shadow: 0 1px 2px rgba(0, 0, 0, 0.06);
            }

            .avatar-slot button {
                width: 100%;
                height: 100%;
                padding: 0;
                border: none;
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                background: transparent;
            }

            .avatar-img {
                width: 100%;
                height: 100%;
                object-fit: cover;
                display: block;
            }

            .avatar-initials {
                width: 100%;
                height: 100%;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 13px;
                font-weight: var(--font-semibold);
                color: #fff;
                letter-spacing: 0.02em;
                user-select: none;
            }

            .bubble {
                max-width: min(720px, 90%);
                border-radius: var(--radius-2xl);
                padding: var(--space-3) var(--space-4);
                border: 1px solid;
            }

            .bubble-row.other .bubble {
                max-width: min(720px, calc(90% - 44px));
            }

            .bubble.own {
                border-color: rgba(16, 185, 129, 0.35);
                background: rgba(16, 185, 129, 0.16);
            }

            .bubble.other {
                border-color: rgba(56, 189, 248, 0.28);
                background: rgba(147, 197, 253, 0.35);
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
                min-width: 0;
            }

            .bubble-body {
                display: flex;
                align-items: flex-end;
                gap: var(--space-2);
            }

            .bubble-contents {
                flex: 1 1 auto;
                min-width: 0;
            }

            .bubble-time {
                flex: 0 0 auto;
                align-self: flex-end;
                font-size: 11px;
                line-height: 1.25;
                letter-spacing: 0.02em;
                white-space: nowrap;
                padding-bottom: 1px;
            }

            .bubble.other .bubble-time {
                color: var(--text-tertiary);
            }

            .bubble.own .bubble-time {
                color: rgba(6, 95, 70, 0.8);
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

            .sender-own {
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-secondary);
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

            .bubble-contents .contents-inner {
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

            .bubble-time.status-pending {
                color: var(--text-tertiary);
            }

            .bubble-time.status-failed {
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

    _renderAvatarSlot() {
        const sender = this.msg.sender;
        if (!sender || typeof sender.id !== 'string') {
            throw new Error('Сообщение без отправителя.');
        }
        const shortName = toShortUsername(sender.display_name ?? '');
        const initials = initialsForAvatar(sender.display_name ?? '');
        const hue = hueFromUserId(sender.id);
        const initialsStyle = `background: hsl(${hue} 48% 42%);`;
        const face = sender.avatar_url
            ? html`
                <img class="avatar-img" src=${sender.avatar_url} alt=${shortName} />
            `
            : html`
                <span class="avatar-initials" style=${initialsStyle}>${initials}</span>
            `;

        return html`
            <div class="avatar-slot">
                <button type="button" @click=${() => { this._profileOpen = true; }} aria-label=${`Профиль: ${shortName}`}>
                    ${face}
                </button>
            </div>
        `;
    }

    _renderTimeMeta() {
        const { status, sent_at } = this.msg;
        if (status === 'pending') {
            return html`<span class="bubble-time status-pending">Отправка...</span>`;
        }
        if (status === 'failed') {
            return html`<span class="bubble-time status-failed">Ошибка</span>`;
        }
        return html`<span class="bubble-time">${formatMessageTime(sent_at)}</span>`;
    }

    render() {
        if (!this.msg) return html``;
        const { msg, isOwn, canFocusThread } = this;
        const sorted = [...(msg.contents ?? [])].sort((a, b) => a.order - b.order);

        return html`
            <div class="bubble-row ${isOwn ? 'own' : 'other'}">
                ${isOwn ? '' : this._renderAvatarSlot()}
                <div class="bubble ${isOwn ? 'own' : 'other'}">
                    <div class="bubble-header">
                        <div class="sender-info">
                            ${isOwn ? html`
                                <span class="sender-own">${toShortUsername(msg.sender?.display_name ?? '')}</span>
                            ` : html`
                                <button
                                    class="sender-btn"
                                    @click=${() => { this._profileOpen = true; }}
                                >
                                    ${toShortUsername(msg.sender?.display_name ?? '')}
                                </button>
                            `}
                        </div>
                        ${canFocusThread ? html`
                            <button class="thread-btn" @click=${this._focusThread}>Тред</button>
                        ` : ''}
                    </div>
                    <div class="bubble-body">
                        <div class="bubble-contents">
                            <div class="contents-inner">
                                ${sorted.map(c => renderContent(c))}
                            </div>
                        </div>
                        ${this._renderTimeMeta()}
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
