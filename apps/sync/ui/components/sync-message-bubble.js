/**
 * sync-message-bubble — пузырь сообщения с полным набором функций.
 *
 * Поддерживаемые типы content:
 *   text/plain, code/block, file/image, mock/image, file/document,
 *   file/audio, file/video, call/boundary, call/transcript, git/reference,
 *   custom_tool_response.
 *
 * Группировка по отправителю (атрибут data-position: first|middle|last|single)
 * определяется родителем (sync-message-list). Аватар и имя показываются
 * только в position='first'|'single' и только для чужих сообщений.
 *
 * Контекстное меню: правая кнопка / long-press 450ms на touch — диспатчит
 * messagesResource.events.CONTEXT_MENU_REQUESTED. Сама модалка — отдельный
 * компонент `<sync-message-context-menu>`.
 *
 * Selection mode: chat_ui.selectionMode=true → показ чекбокса, клик
 * переключает выделение через chat_ui.toggleMessageSelection.
 *
 * Flash: messages.flashMessageId/flashSeq → анимация подсветки.
 * Deletion: chat_ui.deletingMessageIds.includes(message_id) → fade-out.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-user-chip.js';
import '@platform/lib/components/platform-audio-message-player.js';
import { parseMentionsToSegments } from '../_helpers/sync-mention-text.js';
import { hueFromString, initialsFromName } from '../_helpers/sync-hue.js';

const FILE_DOWNLOAD_BASE = '/sync/api/v1/files/download';
const LONG_PRESS_MS = 450;

const EMOJI_QUICK = ['👍', '❤️', '😂', '🔥', '🎉', '👏'];

function _formatBytes(n, t) {
    if (typeof n !== 'number' || n < 0) return '';
    if (n < 1024) return t('bubble.file_size_b', { n });
    if (n < 1024 * 1024) return t('bubble.file_size_kb', { n: (n / 1024).toFixed(1) });
    if (n < 1024 * 1024 * 1024) return t('bubble.file_size_mb', { n: (n / (1024 * 1024)).toFixed(1) });
    return t('bubble.file_size_gb', { n: (n / (1024 * 1024 * 1024)).toFixed(2) });
}

export class SyncMessageBubble extends PlatformElement {
    static properties = {
        message: { type: Object },
        myUserId: { type: String, attribute: 'my-user-id' },
        channelType: { type: String, attribute: 'channel-type' },
        position: { type: String, reflect: true, attribute: 'data-position' },
        members: { type: Array },
    };

    static styles = css`
        :host {
            display: block;
            margin: 1px 0;
            transition: opacity 200ms ease, transform 200ms ease;
        }
        :host([data-position="first"]) { margin-top: var(--space-2); }
        :host([data-position="single"]) { margin-top: var(--space-2); }
        :host([data-deleting]) { opacity: 0; transform: translateY(-4px); pointer-events: none; }
        .row {
            display: flex;
            gap: var(--space-2);
            align-items: flex-end;
        }
        :host([data-own]) .row { justify-content: flex-end; }
        .avatar-slot {
            width: 32px;
            flex-shrink: 0;
            display: flex;
            justify-content: center;
            align-items: flex-end;
        }
        .avatar {
            width: 32px;
            height: 32px;
            border-radius: 50%;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-weight: 600;
            font-size: var(--text-xs);
            cursor: pointer;
        }
        :host([data-own]) .avatar-slot { display: none; }
        :host(:not([data-show-avatar])) .avatar-slot .avatar { visibility: hidden; }
        .check {
            display: none;
            margin-right: var(--space-1);
        }
        :host([data-selection]) .check {
            display: inline-flex;
            align-items: center;
        }
        .check input {
            width: 16px;
            height: 16px;
            cursor: pointer;
        }
        .bubble {
            background: var(--glass-solid);
            border: 1px solid var(--glass-border);
            border-radius: 14px;
            padding: var(--space-2) var(--space-3);
            max-width: 70%;
            min-width: 0;
            position: relative;
            transition: background 150ms ease;
        }
        :host([data-own]) .bubble {
            background: var(--accent);
            color: white;
            border-color: transparent;
        }
        :host([data-position="first"]) .bubble { border-bottom-left-radius: 4px; }
        :host([data-position="middle"]) .bubble { border-radius: 14px 14px 14px 4px; }
        :host([data-position="last"]) .bubble { border-top-left-radius: 4px; }
        :host([data-own][data-position="first"]) .bubble { border-bottom-left-radius: 14px; border-bottom-right-radius: 4px; }
        :host([data-own][data-position="middle"]) .bubble { border-radius: 14px 14px 4px 14px; }
        :host([data-own][data-position="last"]) .bubble { border-top-right-radius: 4px; border-top-left-radius: 14px; }
        :host([data-flash]) .bubble {
            box-shadow: 0 0 0 3px var(--accent), 0 0 22px var(--accent);
            animation: flash-ring 1.4s ease-out;
        }
        @keyframes flash-ring {
            0% { box-shadow: 0 0 0 3px var(--accent), 0 0 22px var(--accent); }
            100% { box-shadow: 0 0 0 0 transparent; }
        }
        .sender {
            font-size: var(--text-xs);
            font-weight: 600;
            margin-bottom: var(--space-1);
            color: var(--text-secondary);
            cursor: pointer;
        }
        :host([data-own]) .sender { display: none; }
        .reply-quote {
            border-left: 3px solid var(--accent);
            padding: 2px var(--space-2);
            margin-bottom: var(--space-1);
            background: var(--glass-hover);
            border-radius: var(--radius-sm);
            font-size: var(--text-xs);
            color: var(--text-secondary);
            cursor: pointer;
        }
        :host([data-own]) .reply-quote { background: rgba(255,255,255,0.18); color: rgba(255,255,255,0.92); }
        .reply-quote .who { font-weight: 600; }
        .forwarded {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            font-size: var(--text-xs);
            color: var(--text-secondary);
            margin-bottom: var(--space-1);
        }
        :host([data-own]) .forwarded { color: rgba(255,255,255,0.85); }
        .body {
            white-space: pre-wrap;
            word-break: break-word;
            overflow-wrap: anywhere;
            font-size: var(--text-sm);
            line-height: 1.4;
        }
        .body a { color: inherit; text-decoration: underline; }
        .mention {
            background: rgba(99, 102, 241, 0.18);
            color: var(--accent);
            padding: 0 2px;
            border-radius: 3px;
            cursor: pointer;
        }
        :host([data-own]) .mention {
            background: rgba(255,255,255,0.22);
            color: white;
        }
        pre {
            background: var(--bg-secondary, #1e293b);
            color: #f8fafc;
            padding: var(--space-2);
            border-radius: var(--radius-sm);
            font-family: ui-monospace, monospace;
            font-size: var(--text-xs);
            overflow-x: auto;
            margin: 0;
        }
        .meta {
            display: flex;
            align-items: center;
            gap: var(--space-1);
            justify-content: flex-end;
            font-size: 11px;
            color: var(--text-secondary);
            margin-top: 2px;
        }
        :host([data-own]) .meta { color: rgba(255, 255, 255, 0.85); }
        .reactions {
            display: flex;
            flex-wrap: wrap;
            gap: var(--space-1);
            margin-top: var(--space-1);
        }
        .reaction {
            display: inline-flex;
            align-items: center;
            gap: 2px;
            padding: 2px 6px;
            border-radius: 12px;
            background: var(--glass-hover);
            color: var(--text-primary);
            cursor: pointer;
            font-size: var(--text-xs);
            border: 1px solid transparent;
        }
        :host([data-own]) .reaction { background: rgba(255,255,255,0.2); color: white; }
        .reaction.mine { border-color: var(--accent); }
        .file {
            display: flex;
            align-items: center;
            gap: var(--space-2);
            padding: var(--space-2);
            background: var(--glass-hover);
            border-radius: var(--radius-sm);
            min-width: 200px;
        }
        :host([data-own]) .file { background: rgba(255,255,255,0.18); }
        .file-info { flex: 1; min-width: 0; }
        .file-name {
            font-size: var(--text-sm);
            font-weight: 500;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .file-size {
            font-size: var(--text-xs);
            color: var(--text-secondary);
        }
        :host([data-own]) .file-size { color: rgba(255,255,255,0.85); }
        .image-wrap img {
            max-width: 320px;
            max-height: 360px;
            border-radius: var(--radius-sm);
            display: block;
            cursor: zoom-in;
        }
        video {
            max-width: 360px;
            border-radius: var(--radius-sm);
            background: black;
        }
        .call-boundary {
            display: inline-flex;
            align-items: center;
            gap: var(--space-2);
            font-size: var(--text-xs);
            color: var(--text-secondary);
            padding: var(--space-1) var(--space-3);
            background: var(--glass-hover);
            border-radius: 999px;
        }
        .call-join-btn {
            padding: 2px 10px;
            background: var(--accent);
            color: white;
            border: none;
            border-radius: 999px;
            cursor: pointer;
            font-size: var(--text-xs);
        }
        .transcript {
            display: flex;
            flex-direction: column;
            gap: var(--space-1);
            font-size: var(--text-xs);
            margin-top: var(--space-1);
        }
        .transcript .turn {
            display: grid;
            grid-template-columns: 24px 1fr;
            gap: var(--space-1);
        }
        .transcribe-btn {
            background: transparent;
            border: 1px solid var(--glass-border);
            color: var(--text-primary);
            padding: 2px 8px;
            border-radius: var(--radius-sm);
            cursor: pointer;
            font-size: var(--text-xs);
        }
        :host([data-own]) .transcribe-btn { color: white; border-color: rgba(255,255,255,0.6); }
        .quick-reactions {
            display: none;
            position: absolute;
            top: -28px;
            right: 8px;
            background: var(--glass-solid);
            border: 1px solid var(--glass-border);
            border-radius: 999px;
            padding: 2px 4px;
            gap: 2px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.18);
            z-index: 10;
        }
        .bubble:hover .quick-reactions { display: inline-flex; }
        .quick-reactions span {
            cursor: pointer;
            font-size: 16px;
            padding: 2px;
            border-radius: 50%;
            transition: transform 100ms ease;
        }
        .quick-reactions span:hover { transform: scale(1.25); background: var(--glass-hover); }
    `;

    constructor() {
        super();
        this.message = null;
        this.myUserId = '';
        this.channelType = '';
        this.position = 'single';
        this.members = [];
        this._messages = this.useOp('sync/messages');
        this._callAccept = this.useOp('sync/calls_accept');
        this._chatUi = this.useSlice('sync/chat_ui');
        this._messagesSlice = this.select((s) => s.syncMessages);
        this._channelsSel = this.select((s) => s.syncChannels);
        this._longPressTimer = null;
        this._longPressTriggered = false;
    }

    updated(changed) {
        super.updated?.(changed);
        if (changed.has('message') || changed.has('myUserId')) {
            const own = !!(this.message && this.message.sender && this.message.sender.user_id === this.myUserId);
            this.toggleAttribute('data-own', own);
            const showAvatar = !own && (this.position === 'first' || this.position === 'single');
            this.toggleAttribute('data-show-avatar', showAvatar);
        }
        const slice = this._chatUi.value;
        const selectionMode = !!(slice && slice.selectionMode === true);
        this.toggleAttribute('data-selection', selectionMode);
        const messageId = this.message && this.message.message_id;
        const flashId = this._messagesSlice.value && this._messagesSlice.value.flashMessageId;
        this.toggleAttribute('data-flash', !!(messageId && flashId === messageId));
        const deleting = !!(slice && Array.isArray(slice.deletingMessageIds)
            && messageId && slice.deletingMessageIds.includes(messageId));
        this.toggleAttribute('data-deleting', deleting);
    }

    _onPointerDown(e) {
        if (e.pointerType !== 'touch') return;
        this._longPressTriggered = false;
        this._longPressTimer = window.setTimeout(() => {
            this._longPressTriggered = true;
            this._showContextMenu(e.clientX, e.clientY);
        }, LONG_PRESS_MS);
    }

    _onPointerUp() {
        if (this._longPressTimer !== null) {
            window.clearTimeout(this._longPressTimer);
            this._longPressTimer = null;
        }
    }

    _onContextMenu(e) {
        e.preventDefault();
        this._showContextMenu(e.clientX, e.clientY);
    }

    _showContextMenu(x, y) {
        const messageId = this.message && this.message.message_id;
        if (typeof messageId !== 'string') return;
        this._messages.actions.showContextMenu({
            messageId,
            x: typeof x === 'number' ? x : 0,
            y: typeof y === 'number' ? y : 0,
        });
    }

    _onBubbleClick() {
        const slice = this._chatUi.value;
        if (!(slice && slice.selectionMode === true)) return;
        const messageId = this.message && this.message.message_id;
        if (typeof messageId !== 'string') return;
        this._chatUi.toggleMessageSelection({ messageId });
    }

    _onReplyQuoteClick() {
        const parent = this.message && this.message.parent_message_id;
        if (typeof parent !== 'string' || parent === '') return;
        this.emit('jump-to-message', { messageId: parent });
    }

    _onSenderClick() {
        const senderId = this.message && this.message.sender && this.message.sender.user_id;
        if (typeof senderId !== 'string' || senderId === '') return;
        this.openModal('platform.user_info', { userId: senderId });
    }

    _onMentionClick(userId) {
        if (typeof userId !== 'string' || userId === '') return;
        this.openModal('platform.user_info', { userId });
    }

    _onReaction(emoji) {
        if (!this.message || typeof emoji !== 'string' || emoji === '') return;
        this._messages.actions.react({
            channel_id: this.message.channel_id,
            message_id: this.message.message_id,
            emoji,
        });
    }

    _onTranscribeAudio() {
        if (!this.message) return;
        this._messages.actions.transcribeAudio({
            channel_id: this.message.channel_id,
            message_id: this.message.message_id,
        });
    }

    _onTranscribeVideo() {
        if (!this.message) return;
        this._messages.actions.transcribeVideo({
            channel_id: this.message.channel_id,
            message_id: this.message.message_id,
        });
    }

    _onTranscribeCall(callId) {
        if (typeof callId !== 'string' || callId === '') return;
        this._messages.actions.transcribeCall({
            channel_id: this.message.channel_id,
            message_id: this.message.message_id,
            call_id: callId,
        });
    }

    _onJoinCall(callId) {
        if (typeof callId !== 'string' || callId === '') return;
        this._callAccept.run({ call_id: callId });
    }

    _renderText(content) {
        const data = (content && content.data && typeof content.data === 'object') ? content.data : null;
        const text = data && (typeof data.text === 'string' ? data.text : (typeof data.body === 'string' ? data.body : ''));
        if (typeof text !== 'string' || text === '') return '';
        const segments = parseMentionsToSegments(text, this.members);
        return html`<div class="body">${segments.map((s) => s.kind === 'mention'
            ? html`<span class="mention" @click=${() => this._onMentionClick(s.userId)}>${s.value}</span>`
            : s.value)}</div>`;
    }

    _renderCodeBlock(content) {
        const data = (content && content.data && typeof content.data === 'object') ? content.data : null;
        const code = data && typeof data.code === 'string' ? data.code : '';
        const lang = data && typeof data.language === 'string' ? data.language : '';
        if (code === '') return '';
        return html`<pre><code data-lang=${lang}>${code}</code></pre>`;
    }

    _renderImage(content) {
        const data = (content && content.data && typeof content.data === 'object') ? content.data : null;
        if (!data) return '';
        let url = '';
        if (typeof data.url === 'string' && data.url !== '') url = data.url;
        else if (typeof data.file_id === 'string') url = `${FILE_DOWNLOAD_BASE}/${encodeURIComponent(data.file_id)}`;
        if (url === '') return '';
        return html`<div class="image-wrap"><img src=${url} alt="" loading="lazy" @click=${() => window.open(url, '_blank')} /></div>`;
    }

    _renderFile(content) {
        const data = (content && content.data && typeof content.data === 'object') ? content.data : null;
        const fileId = data ? data.file_id : null;
        if (typeof fileId !== 'string') return '';
        let name = '';
        if (data && typeof data.original_name === 'string' && data.original_name !== '') name = data.original_name;
        else if (data && typeof data.name === 'string' && data.name !== '') name = data.name;
        else name = this.t('bubble.file_fallback');
        const url = `${FILE_DOWNLOAD_BASE}/${encodeURIComponent(fileId)}`;
        const size = data && typeof data.size === 'number'
            ? _formatBytes(data.size, (k, v) => this.t(k, v))
            : '';
        return html`
            <div class="file">
                <platform-icon name="file" size="24"></platform-icon>
                <div class="file-info">
                    <div class="file-name">${name}</div>
                    ${size ? html`<div class="file-size">${size}</div>` : ''}
                </div>
                <a href=${url} download=${name} title=${this.t('bubble.download_title')}>
                    <platform-icon name="download" size="18"></platform-icon>
                </a>
            </div>
        `;
    }

    _renderAudio(content) {
        const data = (content && content.data && typeof content.data === 'object') ? content.data : null;
        const fileId = data ? data.file_id : null;
        if (typeof fileId !== 'string') return '';
        const url = `${FILE_DOWNLOAD_BASE}/${encodeURIComponent(fileId)}`;
        const status = data ? data.transcription_status : null;
        const transcript = data ? data.transcript : null;
        return html`
            <div class="file" style="flex-direction: column; align-items: stretch;">
                <platform-audio-message-player src=${url}></platform-audio-message-player>
                ${status === 'done' && typeof transcript === 'string' && transcript !== ''
                    ? html`<div class="body">${transcript}</div>` : ''}
                ${status !== 'done' && status !== 'processing'
                    ? html`<button class="transcribe-btn" @click=${this._onTranscribeAudio}>${this.t('message_bubble.action_transcribe')}</button>`
                    : ''}
                ${status === 'processing'
                    ? html`<span class="file-size">${this.t('message_bubble.transcribe_processing')}</span>` : ''}
            </div>
        `;
    }

    _renderVideo(content) {
        const data = (content && content.data && typeof content.data === 'object') ? content.data : null;
        const fileId = data ? data.file_id : null;
        if (typeof fileId !== 'string') return '';
        const url = `${FILE_DOWNLOAD_BASE}/${encodeURIComponent(fileId)}`;
        const status = data ? data.transcription_status : null;
        return html`
            <div class="file" style="flex-direction: column; align-items: stretch; padding: 0; background: transparent;">
                <video controls src=${url} preload="metadata"></video>
                ${status !== 'done' && status !== 'processing'
                    ? html`<button class="transcribe-btn" @click=${this._onTranscribeVideo}>${this.t('message_bubble.action_transcribe')}</button>`
                    : ''}
                ${status === 'processing'
                    ? html`<span class="file-size">${this.t('message_bubble.transcribe_processing')}</span>` : ''}
            </div>
        `;
    }

    _renderCallBoundary(content) {
        const data = (content && content.data && typeof content.data === 'object') ? content.data : null;
        const phase = data ? data.phase : null;
        const callId = data ? data.call_id : null;
        if (phase === 'started') {
            return html`
                <div class="call-boundary">
                    <platform-icon name="phone" size="14"></platform-icon>
                    ${this.t('bubble.call_boundary_started')}
                    ${typeof callId === 'string' ? html`
                        <button class="call-join-btn" @click=${() => this._onJoinCall(callId)} title=${this.t('bubble.call_boundary_join_title')}>
                            ${this.t('bubble.call_boundary_join')}
                        </button>
                        <button class="transcribe-btn" @click=${() => this._onTranscribeCall(callId)}>
                            ${this.t('bubble.transcribe_meeting')}
                        </button>
                    ` : ''}
                </div>
            `;
        }
        return html`
            <div class="call-boundary">
                <platform-icon name="phone-off" size="14"></platform-icon>
                ${this.t('bubble.call_boundary_ended')}
                ${typeof callId === 'string' ? html`
                    <button class="transcribe-btn" @click=${() => this._onTranscribeCall(callId)}>
                        ${this.t('bubble.transcribe_meeting')}
                    </button>
                ` : ''}
            </div>
        `;
    }

    _renderTranscript(content) {
        const data = (content && content.data && typeof content.data === 'object') ? content.data : null;
        const turns = data && Array.isArray(data.turns) ? data.turns : [];
        if (turns.length === 0) return html`<div class="body">${this.t('bubble.transcript_preview')}</div>`;
        return html`
            <div class="body">${this.t('bubble.transcript_preview')}</div>
            <div class="transcript">
                ${turns.map((turn) => {
                    const userId = typeof turn.user_id === 'string' ? turn.user_id : '';
                    return html`<div class="turn">
                        ${userId !== ''
                            ? html`<platform-user-chip user-id=${userId} size="sm" ?interactive=${true}></platform-user-chip>`
                            : html`<span></span>`}
                        <span>${typeof turn.text === 'string' ? turn.text : ''}</span>
                    </div>`;
                })}
            </div>
        `;
    }

    _renderGitRef(content) {
        const data = (content && content.data && typeof content.data === 'object') ? content.data : null;
        if (!data) return '';
        const label = typeof data.label === 'string' && data.label !== '' ? data.label : 'git';
        return html`<div class="file"><platform-icon name="git-branch" size="18"></platform-icon><div class="file-info"><div class="file-name">${label}</div></div></div>`;
    }

    _renderToolResponse(content) {
        const data = (content && content.data && typeof content.data === 'object') ? content.data : null;
        if (!data) return '';
        const text = typeof data.text === 'string' ? data.text : '';
        return html`<div class="file"><platform-icon name="zap" size="18"></platform-icon><div class="file-info"><div class="file-name">${text}</div></div></div>`;
    }

    _renderContent(content) {
        if (!content || typeof content.type !== 'string') return '';
        switch (content.type) {
            case 'text/plain':       return this._renderText(content);
            case 'code/block':       return this._renderCodeBlock(content);
            case 'mock/image':
            case 'file/image':       return this._renderImage(content);
            case 'file/audio':       return this._renderAudio(content);
            case 'file/video':       return this._renderVideo(content);
            case 'call/boundary':    return this._renderCallBoundary(content);
            case 'call/transcript':  return this._renderTranscript(content);
            case 'git/reference':    return this._renderGitRef(content);
            case 'custom_tool_response': return this._renderToolResponse(content);
            default:
                if (content.type.startsWith('file/')) return this._renderFile(content);
                return html`<div class="body">${this.t('bubble.default_message')}</div>`;
        }
    }

    _renderReplyQuote() {
        const parentId = this.message && this.message.parent_message_id;
        if (typeof parentId !== 'string' || parentId === '') return '';
        const channelId = this.message && this.message.channel_id;
        const channelsSlice = this._messagesSlice.value;
        const channelData = channelsSlice && channelsSlice.byChannelId
            ? channelsSlice.byChannelId[channelId]
            : null;
        const items = channelData && Array.isArray(channelData.items) ? channelData.items : [];
        const parent = items.find((m) => m.message_id === parentId);
        if (!parent) {
            return html`<div class="reply-quote" @click=${this._onReplyQuoteClick}>
                <span class="who">${this.t('bubble.default_message')}</span>
            </div>`;
        }
        let senderName = '';
        if (parent.sender && typeof parent.sender === 'object') {
            if (typeof parent.sender.display_name === 'string' && parent.sender.display_name !== '') {
                senderName = parent.sender.display_name;
            } else if (typeof parent.sender.user_id === 'string') {
                senderName = parent.sender.user_id;
            }
        }
        const previewContent = Array.isArray(parent.contents) ? parent.contents.find((c) => c.type === 'text/plain') : null;
        const previewText = previewContent && previewContent.data && typeof previewContent.data.text === 'string'
            ? previewContent.data.text.slice(0, 80)
            : this.t('bubble.default_message');
        return html`<div class="reply-quote" @click=${this._onReplyQuoteClick}>
            <span class="who">${senderName}</span>: ${previewText}
        </div>`;
    }

    _renderForwarded() {
        if (!this.message || this.message.forwarded_from === null || typeof this.message.forwarded_from !== 'object') return '';
        const label = typeof this.message.forwarded_from.label === 'string' ? this.message.forwarded_from.label : '';
        return html`<div class="forwarded">
            <platform-icon name="forward" size="12"></platform-icon>
            ${this.t('bubble.forwarded_from', { label })}
        </div>`;
    }

    _renderReactions() {
        const reactions = this.message && Array.isArray(this.message.reactions)
            ? this.message.reactions
            : [];
        if (reactions.length === 0) return '';
        return html`
            <div class="reactions">
                ${reactions.map((r) => html`
                    <span
                        class=${Array.isArray(r.user_ids) && r.user_ids.includes(this.myUserId) ? 'reaction mine' : 'reaction'}
                        @click=${() => this._onReaction(r.emoji)}
                    >${r.emoji} ${Array.isArray(r.user_ids) ? r.user_ids.length : 0}</span>
                `)}
            </div>
        `;
    }

    _renderStatus() {
        const status = this.message && this.message.status;
        if (typeof status !== 'string' || status === '') return '';
        const own = this.message.sender && this.message.sender.user_id === this.myUserId;
        if (!own) return '';
        const channelsSlice = this._channelsSel.value;
        const peerReadAt = channelsSlice && channelsSlice.peerReadAtByChannel
            ? channelsSlice.peerReadAtByChannel[this.message.channel_id]
            : null;
        const isRead = typeof peerReadAt === 'string' && typeof this.message.sent_at === 'string'
            && peerReadAt >= this.message.sent_at;
        if (this.message._pending) return html`<platform-icon name="clock" size="11"></platform-icon>`;
        if (isRead || status === 'read') return html`<platform-icon name="check-double" size="11"></platform-icon>`;
        if (status === 'delivered') return html`<platform-icon name="check" size="11"></platform-icon>`;
        return html`<platform-icon name="check" size="11"></platform-icon>`;
    }

    _renderMeta() {
        const sentAt = this.message && this.message.sent_at;
        const time = typeof sentAt === 'string'
            ? new Date(sentAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
            : '';
        const edited = this.message && this.message.edited_at
            ? html`<span>${this.t('bubble.edited_short')}</span>`
            : '';
        const pinned = this.message && this.message.is_pinned
            ? html`<platform-icon name="pin" size="11" title=${this.t('bubble.pinned_title')}></platform-icon>`
            : '';
        return html`<div class="meta">${pinned}${edited}<span>${time}</span>${this._renderStatus()}</div>`;
    }

    _renderAvatar() {
        const sender = this.message && this.message.sender;
        if (!sender || typeof sender.user_id !== 'string') return html`<span class="avatar"></span>`;
        const name = (typeof sender.display_name === 'string' && sender.display_name !== '')
            ? sender.display_name
            : sender.user_id;
        const hue = hueFromString(sender.user_id);
        if (typeof sender.avatar_url === 'string' && sender.avatar_url !== '') {
            return html`<img class="avatar" src=${sender.avatar_url} alt="" @click=${this._onSenderClick} />`;
        }
        return html`<span class="avatar" style=${`background: hsl(${hue}, 60%, 55%)`} @click=${this._onSenderClick}>${initialsFromName(name)}</span>`;
    }

    render() {
        if (!this.message) return html``;
        const sender = this.message.sender;
        const senderId = sender && sender.user_id;
        const isOwn = senderId === this.myUserId;
        const contents = Array.isArray(this.message.contents) ? this.message.contents : [];
        const onlyBoundary = contents.length === 1 && contents[0].type === 'call/boundary';
        if (onlyBoundary) {
            return html`<div class="row" style="justify-content: center;">${this._renderContent(contents[0])}</div>`;
        }
        const slice = this._chatUi.value;
        const selectionMode = slice && slice.selectionMode === true;
        const selected = slice && Array.isArray(slice.selectedMessageIds)
            && this.message.message_id
            && slice.selectedMessageIds.includes(this.message.message_id);
        const showSenderName = !isOwn && (this.position === 'first' || this.position === 'single');
        const senderName = sender && (typeof sender.display_name === 'string' && sender.display_name !== ''
            ? sender.display_name
            : sender.user_id);
        return html`
            <div class="row"
                 @contextmenu=${this._onContextMenu}
                 @pointerdown=${this._onPointerDown}
                 @pointerup=${this._onPointerUp}
                 @pointercancel=${this._onPointerUp}
                 @click=${this._onBubbleClick}
            >
                ${selectionMode ? html`<span class="check"><input type="checkbox" .checked=${!!selected} /></span>` : ''}
                ${!isOwn ? html`<div class="avatar-slot">${this._renderAvatar()}</div>` : ''}
                <div class="bubble">
                    ${showSenderName && senderName ? html`<div class="sender" @click=${this._onSenderClick}>${senderName}</div>` : ''}
                    ${this._renderForwarded()}
                    ${this._renderReplyQuote()}
                    ${contents.map((c) => this._renderContent(c))}
                    ${this._renderReactions()}
                    ${this._renderMeta()}
                    <span class="quick-reactions">
                        ${EMOJI_QUICK.map((e) => html`<span @click=${(ev) => { ev.stopPropagation(); this._onReaction(e); }}>${e}</span>`)}
                    </span>
                </div>
            </div>
        `;
    }
}

customElements.define('sync-message-bubble', SyncMessageBubble);
