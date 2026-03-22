/**
 * MessageBubble — отображение одного сообщения со всеми типами контента
 * Полный паритет с sync1 MessageBubble + MessageContentView
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { glassStyles } from '@platform/lib/styles/shared/glass.styles.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { copyTextToClipboard } from '@platform/lib/utils/clipboard.js';
import { ServiceRegistry } from '@platform/lib/services/ServiceRegistry.js';
import { SyncStore } from '../store/sync.store.js';
import '../modals/user-info-modal.js';
import './message-context-menu.js';
import '@platform/lib/components/platform-icon.js';

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

function extractPlainText(msg) {
    const contents = msg?.contents ?? [];
    const parts = [];
    for (const c of contents) {
        if (c.type === 'text/plain' && typeof c.data?.body === 'string') {
            parts.push(c.data.body);
        }
    }
    return parts.join('\n').trim();
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
        channelId: { type: String },
        pinnedMessageIds: { type: Array },
        selectionMode: { type: Boolean },
        selected: { type: Boolean },
        flashActive: { type: Boolean },
        deleting: { type: Boolean },
        _profileOpen: { state: true },
        _menuOpen: { state: true },
        _menuX: { state: true },
        _menuY: { state: true },
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

            .bubble-row.flash-target .bubble {
                animation: bubble-flash-ring 2.6s ease-out;
            }

            @keyframes bubble-flash-ring {
                0% {
                    box-shadow: 0 0 0 0 rgba(56, 189, 248, 0.45);
                }
                35% {
                    box-shadow: 0 0 0 4px rgba(56, 189, 248, 0.22);
                }
                100% {
                    box-shadow: 0 0 0 0 transparent;
                }
            }

            .bubble-row--destroying {
                pointer-events: none;
            }

            .bubble-row--destroying .bubble {
                animation: message-destroy-bubble 0.58s cubic-bezier(0.4, 0, 0.2, 1) forwards;
                will-change: transform, opacity, filter;
            }

            .bubble-row--destroying .avatar-slot {
                animation: message-destroy-avatar 0.58s cubic-bezier(0.4, 0, 0.2, 1) forwards;
                will-change: transform, opacity, filter;
            }

            .bubble-row--destroying .select-wrap {
                opacity: 0;
                transition: opacity 0.15s ease;
            }

            @keyframes message-destroy-bubble {
                0% {
                    opacity: 1;
                    transform: translateY(0) scale(1) rotate(0deg);
                    filter: blur(0) brightness(1);
                }
                22% {
                    opacity: 0.94;
                    transform: translateY(2px) scale(0.985) rotate(-0.4deg);
                    filter: blur(0.5px) brightness(1.02);
                }
                100% {
                    opacity: 0;
                    transform: translateY(18px) scale(0.74) rotate(1.4deg);
                    filter: blur(14px) brightness(1.45);
                }
            }

            @keyframes message-destroy-avatar {
                0% {
                    opacity: 1;
                    transform: scale(1);
                    filter: blur(0);
                }
                100% {
                    opacity: 0;
                    transform: scale(0.82);
                    filter: blur(10px);
                }
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
                position: relative;
                min-width: 0;
                max-width: min(720px, 90%);
                border-radius: var(--radius-2xl);
                padding: var(--space-2) var(--space-3);
                border: 1px solid;
            }

            .bubble--forwarded .bubble-header {
                padding-left: 18px;
            }

            .forwarded-corner {
                position: absolute;
                left: 8px;
                top: 8px;
                z-index: 1;
                display: flex;
                align-items: center;
                justify-content: center;
                color: var(--text-tertiary);
                opacity: 0.92;
                line-height: 1;
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
                gap: var(--space-2);
                margin-bottom: var(--space-1);
            }

            .bubble-header-end {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                flex-shrink: 0;
            }

            .pin-mark {
                display: flex;
                align-items: center;
                justify-content: center;
                color: var(--text-tertiary);
                opacity: 0.9;
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
                gap: var(--space-1);
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
                gap: var(--space-1);
            }

            .msg-text {
                font-size: var(--text-base);
                color: var(--text-primary);
                white-space: pre-wrap;
                overflow-wrap: anywhere;
                word-break: normal;
                line-height: 1.45;
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

            .reply-quote {
                display: block;
                width: 100%;
                margin: 0 0 var(--space-1) 0;
                padding: var(--space-1) var(--space-2);
                border: none;
                border-radius: var(--radius-md);
                text-align: left;
                cursor: pointer;
                font: inherit;
                max-width: 100%;
                box-sizing: border-box;
                border-left: 4px solid var(--text-tertiary);
                background: var(--glass-solid-subtle);
            }

            .reply-quote--parent-own {
                border-left-color: rgb(5, 150, 105);
                background: rgba(16, 185, 129, 0.26);
            }

            .reply-quote--parent-other {
                border-left-color: rgb(2, 132, 199);
                background: rgba(147, 197, 253, 0.52);
            }

            .reply-quote--unknown {
                border-left-color: var(--text-tertiary);
                background: var(--glass-solid-subtle);
            }

            .reply-quote:hover {
                filter: brightness(0.97);
            }

            .reply-quote:focus-visible {
                outline: 2px solid var(--accent);
                outline-offset: 1px;
            }

            .reply-quote__author {
                display: block;
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                margin-bottom: 1px;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            .reply-quote--parent-own .reply-quote__author {
                color: rgb(4, 120, 87);
            }

            .reply-quote--parent-other .reply-quote__author {
                color: rgb(3, 105, 161);
            }

            .reply-quote--unknown .reply-quote__author {
                color: var(--text-secondary);
            }

            .reply-quote__text {
                display: block;
                font-size: var(--text-xs);
                color: var(--text-primary);
                line-height: 1.35;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            .edited-badge {
                font-size: 10px;
                color: var(--text-tertiary);
            }

            .reactions-row {
                display: flex;
                flex-wrap: wrap;
                gap: 4px;
                margin-top: var(--space-1);
            }

            .reaction-chip {
                font-size: 13px;
                padding: 2px 6px;
                border-radius: var(--radius-full);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
            }

            .select-wrap {
                flex-shrink: 0;
                align-self: flex-start;
                padding-top: 4px;
            }

            .select-cb {
                width: 18px;
                height: 18px;
            }
        `
    ];

    constructor() {
        super();
        this.msg = null;
        this.isOwn = false;
        this.canFocusThread = false;
        this.channelId = null;
        this.pinnedMessageIds = [];
        this.selectionMode = false;
        this.selected = false;
        this.flashActive = false;
        this.deleting = false;
        this._profileOpen = false;
        this._menuOpen = false;
        this._menuX = 0;
        this._menuY = 0;
    }

    _focusThread() {
        if (this.msg?.thread_id) {
            this.emit('focus-thread', { threadId: this.msg.thread_id });
        }
    }

    _renderAvatarSlot() {
        const sender = this.msg.sender;
        if (!sender || typeof sender.user_id !== 'string') {
            throw new Error('Сообщение без отправителя.');
        }
        const shortName = toShortUsername(sender.display_name ?? '');
        const initials = initialsForAvatar(sender.display_name ?? '');
        const hue = hueFromUserId(sender.user_id);
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

    _onContextMenu(e) {
        e.preventDefault();
        this._menuX = e.clientX;
        this._menuY = e.clientY;
        this._menuOpen = true;
    }

    async _onMenuAction(e) {
        this._menuOpen = false;
        const { kind, emoji } = e.detail;
        const syncApi = ServiceRegistry.get('syncApi');
        const { msg, channelId } = this;
        if (!msg?.id) throw new Error('Нет сообщения.');
        if (!channelId) throw new Error('Нет channelId.');

        if (kind === 'reply') {
            SyncStore.setReplyToMessage(msg);
            return;
        }
        if (kind === 'copy') {
            const text = extractPlainText(msg);
            if (text === '') throw new Error('Нет текста для копирования.');
            await copyTextToClipboard(text);
            return;
        }
        if (kind === 'translate') {
            const text = extractPlainText(msg);
            const q = text === '' ? '' : `&q=${encodeURIComponent(text)}`;
            globalThis.open(`https://translate.google.com/?sl=auto&tl=ru${q}`, '_blank');
            return;
        }
        if (kind === 'edit') {
            SyncStore.setEditMessage(msg);
            return;
        }
        if (kind === 'pin') {
            const pinned = this.pinnedMessageIds ?? [];
            const isPinned = pinned.includes(msg.id);
            await syncApi.pinMessage(channelId, msg.id, isPinned ? 'remove' : 'add');
            return;
        }
        if (kind === 'forward') {
            SyncStore.setForwardModal(true, msg);
            return;
        }
        if (kind === 'select') {
            SyncStore.setSelectionMode(true);
            SyncStore.toggleMessageSelection(msg.id);
            return;
        }
        if (kind === 'delete') {
            await syncApi.deleteMessage(channelId, msg.id);
            return;
        }
        if (kind === 'react') {
            if (typeof emoji !== 'string' || emoji.trim() === '') {
                throw new Error('emoji обязателен.');
            }
            await syncApi.reactMessage(channelId, msg.id, emoji);
        }
    }

    _isPinned() {
        const id = this.msg?.id;
        const pins = this.pinnedMessageIds;
        if (!id || !Array.isArray(pins)) return false;
        return pins.includes(id);
    }

    _forwardedMeta() {
        const f = this.msg?.forwarded_from;
        if (!f || typeof f.channel_id !== 'string' || f.channel_id === '') {
            return null;
        }
        const nm = typeof f.channel_name === 'string' ? f.channel_name.trim() : '';
        const label = nm !== '' ? nm : f.channel_id;
        return { tip: `Переслано из «${label}»` };
    }

    _onReplyPreviewClick(e) {
        e.stopPropagation();
        e.preventDefault();
        const pid = this.msg?.parent_message_id;
        if (typeof pid !== 'string' || pid === '') {
            throw new Error('parent_message_id обязателен.');
        }
        this.emit('scroll-to-message', { messageId: pid });
    }

    _parentPreview() {
        const pid = this.msg?.parent_message_id;
        if (!pid) return null;
        const all = SyncStore.getDisplayMessages();
        const p = all.find(m => m.id === pid);
        const myId = ServiceRegistry.auth?.user?.id;
        const parentIsOwn =
            typeof myId === 'string' &&
            p &&
            typeof p.sender?.id === 'string' &&
            p.sender.user_id === myId;
        const quoteClass = !p
            ? 'reply-quote--unknown'
            : parentIsOwn
              ? 'reply-quote--parent-own'
              : 'reply-quote--parent-other';
        const who = p ? toShortUsername(p.sender?.display_name ?? '') : 'Сообщение';
        const snippetRaw = p ? extractPlainText(p).slice(0, 160) : '';
        const snippet = snippetRaw !== '' ? snippetRaw : 'Сообщение';

        return html`
            <button type="button" class="reply-quote ${quoteClass}" @click=${this._onReplyPreviewClick}>
                <span class="reply-quote__author">${who}</span>
                <span class="reply-quote__text">${snippet}</span>
            </button>
        `;
    }

    _reactionsLine() {
        const rx = this.msg?.reactions;
        if (!Array.isArray(rx) || rx.length === 0) return null;
        const groups = new Map();
        for (const r of rx) {
            if (!r?.emoji) continue;
            const n = (groups.get(r.emoji) ?? 0) + 1;
            groups.set(r.emoji, n);
        }
        const chips = [...groups.entries()].map(([em, n]) => html`
            <span class="reaction-chip">${em}${n > 1 ? ` ${n}` : ''}</span>
        `);
        return html`<div class="reactions-row">${chips}</div>`;
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
        const { msg, isOwn, canFocusThread, flashActive, deleting } = this;
        const sorted = [...(msg.contents ?? [])].sort((a, b) => a.order - b.order);
        const fwdMeta = this._forwardedMeta();
        const hasEdited = Boolean(msg.edited_at);
        const hasHeaderEnd = this._isPinned() || canFocusThread;
        const showBubbleHeader = !isOwn || hasEdited || hasHeaderEnd;

        return html`
            <div
                class="bubble-row ${isOwn ? 'own' : 'other'} ${flashActive ? 'flash-target' : ''} ${deleting ? 'bubble-row--destroying' : ''}"
                data-message-id=${msg.id}
                @contextmenu=${this._onContextMenu}
            >
                ${this.selectionMode ? html`
                    <div class="select-wrap">
                        <input
                            type="checkbox"
                            class="select-cb"
                            .checked=${this.selected}
                            @change=${() => SyncStore.toggleMessageSelection(msg.id)}
                        />
                    </div>
                ` : ''}
                ${isOwn ? '' : this._renderAvatarSlot()}
                <div class="bubble ${isOwn ? 'own' : 'other'} ${fwdMeta ? 'bubble--forwarded' : ''}">
                    ${fwdMeta ? html`
                        <span class="forwarded-corner" title=${fwdMeta.tip}>
                            <platform-icon name="share" size="12"></platform-icon>
                        </span>
                    ` : ''}
                    ${showBubbleHeader ? html`
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
                                ${hasEdited ? html`<span class="edited-badge">изм.</span>` : ''}
                            </div>
                            ${hasHeaderEnd ? html`
                                <div class="bubble-header-end">
                                    ${this._isPinned() ? html`
                                        <span class="pin-mark" title="Закреплено">
                                            <platform-icon name="target" size="12"></platform-icon>
                                        </span>
                                    ` : ''}
                                    ${canFocusThread ? html`
                                        <button class="thread-btn" @click=${this._focusThread}>Тред</button>
                                    ` : ''}
                                </div>
                            ` : ''}
                        </div>
                    ` : ''}
                    ${this._parentPreview()}
                    <div class="bubble-body">
                        <div class="bubble-contents">
                            <div class="contents-inner">
                                ${sorted.map(c => renderContent(c))}
                            </div>
                        </div>
                        ${this._renderTimeMeta()}
                    </div>
                    ${this._reactionsLine()}
                </div>
            </div>

            ${this._menuOpen ? html`
                <message-context-menu
                    .open=${true}
                    .anchorX=${this._menuX}
                    .anchorY=${this._menuY}
                    .isOwn=${isOwn}
                    .selectionMode=${this.selectionMode}
                    @menu-action=${this._onMenuAction}
                    @close=${() => { this._menuOpen = false; }}
                ></message-context-menu>
            ` : ''}

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
