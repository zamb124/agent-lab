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
 * Контекстное меню: правая кнопка / long-press 450ms на touch — action
 * `showContextMenu` slice'а `sync/messages_store`. Сама модалка — отдельный
 * компонент `<sync-message-context-menu>`.
 *
 * Selection mode: chat_ui.selectionMode=true → показ чекбокса, клик
 * переключает выделение через chat_ui.toggleMessageSelection.
 *
 * Flash: syncMessagesStore.flashMessageId/flashSeq → анимация подсветки.
 * Deletion: chat_ui.deletingMessageIds.includes(message_id) → fade-out.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-user-chip.js';
import '@platform/lib/components/platform-audio-message-player.js';
import { parseMentionsToSegments } from '../_helpers/sync-mention-text.js';
import { resolveAvatarImageSrc } from '@platform/lib/utils/placeholder-avatar.js';
import { initialsFromName, syncAvatarHueVar } from '../_helpers/sync-hue.js';

const FILE_DOWNLOAD_BASE = '/sync/api/v1/files/download';
const LONG_PRESS_MS = 450;

const EMOJI_QUICK = ['👍','👎','❤️', '😂', '🔥', '🎉', '👏'];

/** API хранит плоский список { user_id, emoji, created_at }; для UI — одна пилюля на emoji. */
function _reactionsGroupedByEmoji(raw) {
    if (!Array.isArray(raw)) return [];
    const map = new Map();
    for (const r of raw) {
        if (!r || typeof r !== 'object') continue;
        const emoji = typeof r.emoji === 'string' ? r.emoji : '';
        if (emoji === '') continue;
        const uid = typeof r.user_id === 'string' ? r.user_id : '';
        let userIds = map.get(emoji);
        if (!userIds) {
            userIds = [];
            map.set(emoji, userIds);
        }
        if (uid !== '' && !userIds.includes(uid)) userIds.push(uid);
    }
    return [...map.entries()].map(([emoji, user_ids]) => ({ emoji, user_ids }));
}

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
        _senderAvatarFailed: { state: true },
    };

    static styles = css`
        :host {
            display: block;
            margin: 1px 0;
            min-width: 0;
            transition: opacity 200ms ease, transform 200ms ease;
        }
        :host([data-position="first"]) { margin-top: var(--space-2); }
        :host([data-position="single"]) { margin-top: var(--space-2); }
        :host([data-deleting]) { opacity: 0; transform: translateY(-4px); pointer-events: none; }
        .row {
            display: flex;
            gap: var(--space-2);
            align-items: flex-end;
            min-width: 0;
        }
        @media (max-width: 767px) {
            .row,
            .row * {
                -webkit-user-select: none;
                user-select: none;
                -webkit-touch-callout: none;
            }
        }
        :host([data-own]) .row { justify-content: flex-end; }
        .row.row-call-boundary {
            box-sizing: border-box;
            width: 100%;
            max-width: 100%;
            display: block;
            text-align: center;
        }
        .row.row-call-boundary > .call-boundary {
            text-align: start;
        }
        :host([data-only-call-boundary]) {
            display: block;
            width: 100%;
            max-width: 100%;
            box-sizing: border-box;
        }
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
            font-weight: 600;
            font-size: var(--text-xs);
            cursor: pointer;
        }
        .avatar.pastel-initials {
            --sync-avatar-h: 0;
            background: hsl(var(--sync-avatar-h), var(--sync-pastel-avatar-s-bg), var(--sync-pastel-avatar-l-bg));
            color: hsl(var(--sync-avatar-h), var(--sync-pastel-avatar-s-fg), var(--sync-pastel-avatar-l-fg));
        }
        .avatar img {
            width: 100%;
            height: 100%;
            object-fit: cover;
            border-radius: 50%;
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
            background: var(--glass-solid-soft, var(--glass-solid));
            border: 1px solid var(--glass-border-subtle, var(--glass-border));
            border-radius: var(--radius-2xl, 18px);
            padding: 10px var(--space-4);
            display: inline-flex;
            flex-direction: column;
            align-items: stretch;
            width: fit-content;
            max-width: 70%;
            min-width: 0;
            position: relative;
            overflow: visible;
            color: var(--text-primary);
            box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
            transition: background var(--duration-fast);
        }
        :host([data-own]) .bubble {
            background: var(--accent);
            color: var(--text-inverse, #fff);
            border-color: transparent;
            box-shadow: 0 2px 8px var(--accent-subtle, rgba(153, 166, 249, 0.18));
        }
        :host(:not([data-own])) .bubble { border-bottom-left-radius: 6px; }
        :host([data-own]) .bubble { border-bottom-right-radius: 6px; }
        :host(:not([data-own])[data-position="middle"]) .bubble,
        :host(:not([data-own])[data-position="first"]) .bubble {
            border-bottom-left-radius: 6px;
        }
        :host([data-own][data-position="middle"]) .bubble,
        :host([data-own][data-position="first"]) .bubble {
            border-bottom-right-radius: 6px;
        }
        :host([data-flash]) .bubble {
            box-shadow: 0 0 0 3px var(--accent), 0 0 22px var(--accent);
            animation: flash-ring 1.4s ease-out;
        }
        @keyframes flash-ring {
            0% { box-shadow: 0 0 0 3px var(--accent), 0 0 22px var(--accent); }
            100% { box-shadow: 0 0 0 0 transparent; }
        }
        .sender {
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 0.01em;
            margin-bottom: var(--space-1);
            color: var(--text-secondary);
            cursor: pointer;
        }
        :host([data-own]) .sender { display: none; }
        .reply-quote {
            border-left: 3px solid var(--accent);
            padding: 6px var(--space-3);
            margin-bottom: var(--space-2);
            background: color-mix(in srgb, var(--glass-solid-soft, var(--glass-solid)) 82%, var(--sync-reply-quote-bg-mix));
            border-radius: var(--radius-sm);
            font-size: var(--text-xs);
            color: var(--text-secondary);
            cursor: pointer;
        }
        :host([data-own]) .reply-quote {
            background: rgba(255, 255, 255, 0.24);
            color: rgba(255, 255, 255, 0.95);
        }
        .reply-quote .who { font-weight: 600; }
        .forwarded {
            display: flex;
            align-items: flex-start;
            gap: 6px;
            max-width: 100%;
            min-width: 0;
            box-sizing: border-box;
            font-size: var(--text-xs);
            color: var(--text-secondary);
            margin-bottom: var(--space-1);
        }
        .forwarded platform-icon {
            flex-shrink: 0;
            margin-top: 2px;
        }
        .forwarded-label {
            flex: 1;
            min-width: 0;
            overflow-wrap: anywhere;
            word-break: break-word;
            line-height: 1.35;
        }
        :host([data-own]) .forwarded { color: rgba(255,255,255,0.85); }
        .body {
            white-space: pre-wrap;
            word-break: break-word;
            overflow-wrap: anywhere;
            font-size: var(--text-base, 16px);
            line-height: 1.5;
        }
        .tail-row {
            display: flex;
            flex-direction: row;
            align-items: center;
            gap: var(--space-2);
            align-self: stretch;
            min-width: 0;
            margin-top: 4px;
            justify-content: space-between;
            flex-wrap: wrap;
        }
        .tail-row--meta-only {
            justify-content: flex-end;
        }
        .tail-row .meta {
            margin-top: 0;
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
            display: inline-flex;
            align-items: center;
            gap: 4px;
            justify-content: flex-end;
            font-size: 11px;
            line-height: 1.2;
            color: var(--text-tertiary);
            margin-top: 2px;
            opacity: 0.88;
        }
        :host([data-own]) .meta {
            color: rgba(255, 255, 255, 0.82);
            opacity: 0.95;
        }
        .status-failed {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 0;
            margin: 0;
            border: none;
            background: transparent;
            color: var(--color-error, #ef4444);
            cursor: pointer;
            line-height: 0;
        }
        .status-failed:hover { color: var(--color-error, #ef4444); opacity: 0.85; }
        .status-failed:focus-visible {
            outline: 2px solid var(--color-error, #ef4444);
            outline-offset: 2px;
            border-radius: 999px;
        }
        :host([data-own]) .status-failed { color: var(--color-error, #ef4444); }
        .reactions {
            display: flex;
            flex-wrap: wrap;
            gap: var(--space-1);
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
        .audio-attachment {
            display: block;
            align-self: flex-start;
            width: max-content;
            max-width: min(360px, 100%);
            min-width: 0;
            margin: 0;
            padding: 0;
        }
        :host([data-own]) .audio-attachment {
            align-self: flex-end;
        }
        .image-wrap {
            margin: -2px 0;
        }
        .image-wrap img {
            max-width: 320px;
            max-height: 360px;
            border-radius: var(--radius-lg, 12px);
            display: block;
            cursor: zoom-in;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
            transition: opacity var(--duration-fast);
        }
        .image-wrap img:hover { opacity: 0.95; }
        .video-attachment {
            display: inline-block;
            max-width: 320px;
            vertical-align: top;
        }
        .video-wrap {
            position: relative;
            display: block;
            border-radius: var(--radius-lg, 12px);
            overflow: hidden;
            background: #000;
        }
        .video-wrap video {
            max-width: 320px;
            width: 100%;
            vertical-align: bottom;
            border-radius: var(--radius-lg, 12px);
            background: black;
            display: block;
        }
        .video-overlay-actions {
            position: absolute;
            top: var(--space-2);
            left: var(--space-2);
            z-index: 2;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            pointer-events: auto;
        }
        .video-action {
            box-sizing: border-box;
            width: 32px;
            height: 32px;
            padding: 0;
            border: none;
            border-radius: var(--radius-md, 8px);
            background: rgba(0, 0, 0, 0.52);
            color: #fff;
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            text-decoration: none;
            backdrop-filter: blur(6px);
            -webkit-backdrop-filter: blur(6px);
            transition: background var(--duration-fast);
        }
        .video-action:hover:not([disabled]) {
            background: rgba(0, 0, 0, 0.68);
        }
        .video-action[disabled] {
            opacity: 0.75;
            cursor: default;
        }
        .video-action-a {
            font-size: var(--text-sm);
            font-weight: 800;
            line-height: 1;
            letter-spacing: -0.02em;
        }
        .video-action platform-icon {
            color: #fff;
        }
        .call-boundary {
            display: inline-flex;
            flex-wrap: wrap;
            align-items: center;
            justify-content: center;
            gap: var(--space-2);
            font-size: var(--text-xs);
            color: var(--text-secondary);
            padding: var(--space-1) var(--space-3);
            background: var(--glass-hover);
            border-radius: 999px;
            max-width: 100%;
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
        :host([data-own]) .bubble .transcribe-btn {
            color: var(--text-inverse, #fff);
            border-color: rgba(255, 255, 255, 0.6);
        }
        .call-boundary .transcribe-call-a-btn {
            box-sizing: border-box;
            min-width: 28px;
            min-height: 28px;
            padding: 2px 6px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
        }
        .call-boundary .transcribe-a-glyph {
            font-size: var(--text-sm);
            font-weight: 800;
            line-height: 1;
            letter-spacing: -0.02em;
            color: var(--text-primary);
        }
        .quick-reactions {
            display: none;
            position: absolute;
            top: -28px;
            right: 8px;
            left: auto;
            margin: 0;
            box-sizing: border-box;
            width: max-content;
            max-width: calc(100dvw - var(--platform-safe-left) - var(--platform-safe-right) - 16px);
            flex-wrap: nowrap;
            align-items: center;
            background: var(--glass-solid-strong);
            border: 1px solid var(--glass-border);
            border-radius: 999px;
            padding: 2px 6px;
            gap: 2px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.18);
            z-index: 10;
            pointer-events: none;
        }
        .bubble:hover .quick-reactions {
            display: inline-flex;
            pointer-events: auto;
        }
        .quick-reactions span {
            cursor: pointer;
            font-size: 16px;
            line-height: 1;
            padding: 2px;
            border-radius: 50%;
            flex-shrink: 0;
            transition: transform 100ms ease;
        }
        .quick-reactions span:hover { transform: scale(1.25); background: var(--glass-tint-medium); }
    `;

    constructor() {
        super();
        this.message = null;
        this.myUserId = '';
        this.channelType = '';
        this.position = 'single';
        this.members = [];
        this._store = this.useSlice('sync/messages_store');
        this._react = this.useOp('sync/messages_react');
        this._transcribeAudio = this.useOp('sync/messages_transcribe_audio');
        this._transcribeVideo = this.useOp('sync/messages_transcribe_video');
        this._transcribeCall = this.useOp('sync/messages_transcribe_call');
        this._callAccept = this.useOp('sync/calls_accept');
        this._chatUi = this.useSlice('sync/chat_ui');
        this._messagesStoreSel = this.select((s) => s.syncMessagesStore);
        this._channelsSel = this.select((s) => s.syncChannels);
        this._longPressTimer = null;
        this._longPressTriggered = false;
        this._senderAvatarFailed = false;
        this._senderAvatarSig = '';
        this._captureSelectStartMobile = (e) => {
            if (!window.matchMedia || !window.matchMedia('(max-width: 767px)').matches) return;
            e.preventDefault();
        };
    }

    connectedCallback() {
        super.connectedCallback();
        const sr = this.shadowRoot;
        if (sr) {
            sr.addEventListener('selectstart', this._captureSelectStartMobile, true);
        }
    }

    disconnectedCallback() {
        const sr = this.shadowRoot;
        if (sr) {
            sr.removeEventListener('selectstart', this._captureSelectStartMobile, true);
        }
        super.disconnectedCallback();
    }

    updated(changed) {
        super.updated?.(changed);
        if (changed.has('message') || changed.has('myUserId')) {
            const own = !!(this.message && this.message.sender && this.message.sender.user_id === this.myUserId);
            this.toggleAttribute('data-own', own);
            const onlyCallBoundary = this._isCallBoundaryOnlyRow(
                this.message && this.message.contents,
            );
            this.toggleAttribute('data-only-call-boundary', onlyCallBoundary);
            const showAvatar = !own && (this.position === 'first' || this.position === 'single');
            this.toggleAttribute('data-show-avatar', showAvatar);
            const sender = this.message && this.message.sender;
            if (sender && typeof sender.user_id === 'string') {
                const au = typeof sender.avatar_url === 'string' ? sender.avatar_url : '';
                const sig = `${sender.user_id}|${au}`;
                if (this._senderAvatarSig !== sig) {
                    this._senderAvatarSig = sig;
                    this._senderAvatarFailed = false;
                }
            }
        }
        const slice = this._chatUi.value;
        const selectionMode = !!(slice && slice.selectionMode === true);
        this.toggleAttribute('data-selection', selectionMode);
        const messageId = this.message && this.message.message_id;
        const flashId = this._messagesStoreSel.value && this._messagesStoreSel.value.flashMessageId;
        this.toggleAttribute('data-flash', !!(messageId && flashId === messageId));
        const deleting = !!(slice && Array.isArray(slice.deletingMessageIds)
            && messageId && slice.deletingMessageIds.includes(messageId));
        this.toggleAttribute('data-deleting', deleting);
    }

    _onPointerDown(e) {
        if (e.pointerType !== 'touch') return;
        this._clearTextSelection();
        this._longPressTriggered = false;
        this._longPressTimer = window.setTimeout(() => {
            this._longPressTriggered = true;
            this._clearTextSelection();
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
        this._store.showContextMenu({
            messageId,
            x: typeof x === 'number' ? x : 0,
            y: typeof y === 'number' ? y : 0,
        });
    }

    _clearTextSelection() {
        const sel = typeof window !== 'undefined' ? window.getSelection() : null;
        if (sel && typeof sel.removeAllRanges === 'function') {
            sel.removeAllRanges();
        }
    }

    _onBubbleClick(e) {
        if (this._longPressTriggered) {
            this._longPressTriggered = false;
            e.preventDefault();
            e.stopPropagation();
            return;
        }
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

    _onSenderAvatarError(e) {
        e.stopPropagation();
        this._senderAvatarFailed = true;
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
        this._react.run({
            channel_id: this.message.channel_id,
            message_id: this.message.message_id,
            emoji,
        });
    }

    _onTranscribeAudio() {
        if (!this.message) return;
        this._transcribeAudio.run({
            channel_id: this.message.channel_id,
            message_id: this.message.message_id,
        });
    }

    _onTranscribeVideo() {
        if (!this.message) return;
        this._transcribeVideo.run({
            channel_id: this.message.channel_id,
            message_id: this.message.message_id,
        });
    }

    _onTranscribeCall(callId) {
        if (typeof callId !== 'string' || callId === '') return;
        if (!this.message || typeof this.message.channel_id !== 'string') return;
        this._transcribeCall.run({
            channel_id: this.message.channel_id,
            call_id: callId,
        });
    }

    _onJoinCall(callId) {
        if (typeof callId !== 'string' || callId === '') return;
        this._callAccept.run({ call_id: callId });
    }

    _reactionsNonEmpty() {
        const raw = this.message && Array.isArray(this.message.reactions) ? this.message.reactions : [];
        return _reactionsGroupedByEmoji(raw).length > 0;
    }

    _renderTailRow() {
        const hasReactions = this._reactionsNonEmpty();
        if (!hasReactions) {
            return html`<div class="tail-row tail-row--meta-only">${this._renderMeta()}</div>`;
        }
        return html`
            <div class="tail-row">
                ${this._renderReactions()}
                ${this._renderMeta()}
            </div>
        `;
    }

    _renderText(content) {
        const data = (content && content.data && typeof content.data === 'object') ? content.data : null;
        const text = data && (typeof data.body === 'string' ? data.body : (typeof data.text === 'string' ? data.text : ''));
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
        const alt = (typeof data.alt_text === 'string' && data.alt_text !== '')
            ? data.alt_text
            : (typeof data.filename === 'string' ? data.filename : '');
        return html`<div class="image-wrap"><img src=${url} alt=${alt} loading="lazy" @click=${() => window.open(url, '_blank')} /></div>`;
    }

    _renderFile(content) {
        const data = (content && content.data && typeof content.data === 'object') ? content.data : null;
        const fileId = data ? data.file_id : null;
        if (typeof fileId !== 'string') return '';
        let name = '';
        if (data && typeof data.filename === 'string' && data.filename !== '') name = data.filename;
        else if (data && typeof data.original_name === 'string' && data.original_name !== '') name = data.original_name;
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
        const status = data && typeof data.transcription_status === 'string' ? data.transcription_status : 'idle';
        const durationMs = data && typeof data.duration_ms === 'number' ? data.duration_ms : 0;
        const hasWaveform = data && Array.isArray(data.waveform);
        const waveform = hasWaveform ? data.waveform : null;
        const transcriptionText = data && typeof data.transcription_text === 'string' ? data.transcription_text : '';
        const transcriptionError = data && typeof data.transcription_error === 'string' ? data.transcription_error : '';
        return html`
            <div class="audio-attachment">
                <platform-audio-message-player
                    src=${url}
                    duration-ms=${durationMs}
                    .waveform=${waveform}
                    transcription-status=${status}
                    .transcriptionText=${transcriptionText}
                    .transcriptionError=${transcriptionError}
                    @request-transcription=${this._onTranscribeAudio}
                ></platform-audio-message-player>
            </div>
        `;
    }

    _renderVideo(content) {
        const data = (content && content.data && typeof content.data === 'object') ? content.data : null;
        const fileId = data ? data.file_id : null;
        if (typeof fileId !== 'string') return '';
        const url = `${FILE_DOWNLOAD_BASE}/${encodeURIComponent(fileId)}`;
        const status = data ? data.transcription_status : null;
        let name = '';
        if (data && typeof data.filename === 'string' && data.filename !== '') {
            name = data.filename;
        } else {
            name = this.t('bubble.file_fallback');
        }
        const transcribeControl = status === 'processing'
            ? html`
                <button
                    type="button"
                    class="video-action"
                    disabled
                    title=${this.t('message_bubble.transcribe_processing')}
                ><span class="video-action-a" aria-hidden="true">...</span></button>
            `
            : status !== 'done'
                ? html`
                <button
                    type="button"
                    class="video-action"
                    title=${this.t('message_bubble.action_transcribe')}
                    @click=${(e) => {
                        e.stopPropagation();
                        this._onTranscribeVideo();
                    }}
                ><span class="video-action-a">A</span></button>
            `
                : '';
        return html`
            <div class="video-attachment">
                <div class="video-wrap">
                    <video controls src=${url} preload="metadata"></video>
                    <div class="video-overlay-actions">
                        ${transcribeControl}
                        <a
                            class="video-action"
                            href=${url}
                            download=${name}
                            title=${this.t('bubble.download_title')}
                            @click=${(e) => e.stopPropagation()}
                        ><platform-icon name="download" size="16"></platform-icon></a>
                    </div>
                </div>
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
                    ` : ''}
                </div>
            `;
        }
        const showTranscribe = data ? data.has_recording !== false : true;
        return html`
            <div class="call-boundary">
                <platform-icon name="phone-off" size="14"></platform-icon>
                ${this.t('bubble.call_boundary_ended')}
                ${typeof callId === 'string' && showTranscribe ? html`
                    <button
                        type="button"
                        class="transcribe-btn transcribe-call-a-btn"
                        title=${this.t('bubble.transcribe_meeting')}
                        aria-label=${this.t('bubble.transcribe_meeting')}
                        @click=${() => this._onTranscribeCall(callId)}
                    ><span class="transcribe-a-glyph" aria-hidden="true">A</span></button>
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
        const messagesSlice = this._messagesStoreSel.value;
        const channelData = messagesSlice && messagesSlice.byChannelId
            ? messagesSlice.byChannelId[channelId]
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
        const previewData = previewContent && previewContent.data;
        const previewBody = previewData && typeof previewData.body === 'string'
            ? previewData.body
            : (previewData && typeof previewData.text === 'string' ? previewData.text : '');
        const previewText = previewBody !== ''
            ? previewBody.slice(0, 80)
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
            <span class="forwarded-label">${this.t('bubble.forwarded_from', { label })}</span>
        </div>`;
    }

    _renderReactions() {
        const raw = this.message && Array.isArray(this.message.reactions)
            ? this.message.reactions
            : [];
        const reactions = _reactionsGroupedByEmoji(raw);
        if (reactions.length === 0) return '';
        return html`
            <div class="reactions">
                ${reactions.map((r) => html`
                    <span
                        class=${Array.isArray(r.user_ids) && r.user_ids.includes(this.myUserId) ? 'reaction mine' : 'reaction'}
                        @click=${() => this._onReaction(r.emoji)}
                    >${r.emoji} ${r.user_ids.length}</span>
                `)}
            </div>
        `;
    }

    _renderStatus() {
        const status = this.message && this.message.status;
        if (typeof status !== 'string' || status === '') return '';
        const own = this.message.sender && this.message.sender.user_id === this.myUserId;
        if (!own) return '';
        const errorText = typeof this.message._error === 'string' && this.message._error !== ''
            ? this.message._error
            : null;
        if (errorText !== null) {
            const tip = this.t('message_bubble.send_failed', { error: errorText });
            return html`<button
                class="status-failed"
                title=${tip}
                aria-label=${this.t('message_bubble.send_failed_action_resend')}
                @click=${this._onResendFailed}
            ><platform-icon name="alert-circle" size="13"></platform-icon></button>`;
        }
        const channelsSlice = this._channelsSel.value;
        const readMap = channelsSlice && channelsSlice.readByChannelUser
            ? channelsSlice.readByChannelUser[this.message.channel_id]
            : null;
        const sentAtMs = typeof this.message.sent_at === 'string'
            ? Date.parse(this.message.sent_at)
            : NaN;
        let isRead = false;
        if (readMap && typeof readMap === 'object' && !Number.isNaN(sentAtMs)) {
            for (const [readerId, readAt] of Object.entries(readMap)) {
                if (readerId === this.myUserId) continue;
                if (typeof readAt !== 'string') continue;
                const readAtMs = Date.parse(readAt);
                if (!Number.isNaN(readAtMs) && readAtMs >= sentAtMs) {
                    isRead = true;
                    break;
                }
            }
        }
        if (this.message._pending) return html`<platform-icon name="clock" size="11"></platform-icon>`;
        if (isRead || status === 'read') return html`<platform-icon name="check-double" size="11"></platform-icon>`;
        if (status === 'delivered') return html`<platform-icon name="check" size="11"></platform-icon>`;
        return html`<platform-icon name="check" size="11"></platform-icon>`;
    }

    _onResendFailed(e) {
        e.stopPropagation();
        if (!this.message) return;
        const channelId = this.message.channel_id;
        const localId = this.message.local_id;
        if (typeof channelId !== 'string' || typeof localId !== 'string') return;
        this._store.resendOptimistic({ channelId, localId });
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

    _stringContentType(c) {
        if (c == null || typeof c !== 'object') return null;
        const t = c.type;
        if (typeof t !== 'string') return null;
        const s = t.trim();
        return s === '' ? null : s;
    }

    /**
     * Блоки для решения, «только call/boundary» это или нет: пустые text/plain
     * (часто приезжают с бэка вторым slot) не считаем содержимым.
     */
    _relevantContentBlocks(raw) {
        if (!Array.isArray(raw)) return [];
        const out = [];
        for (const c of raw) {
            if (c == null || typeof c !== 'object') continue;
            const st = this._stringContentType(c);
            if (st == null) continue;
            if (st === 'text/plain') {
                const data = c.data;
                if (data && typeof data === 'object' && 'body' in data) {
                    const b = data.body;
                    if (b == null) continue;
                    if (typeof b === 'string' && b.trim() === '') continue;
                } else {
                    continue;
                }
            }
            out.push(c);
        }
        return out;
    }

    _isCallBoundaryOnlyRow(contents) {
        const rel = this._relevantContentBlocks(contents);
        return rel.length > 0 && rel.every((c) => this._stringContentType(c) === 'call/boundary');
    }

    _renderAvatar() {
        const sender = this.message && this.message.sender;
        if (!sender || typeof sender.user_id !== 'string') return html`<span class="avatar"></span>`;
        const name = (typeof sender.display_name === 'string' && sender.display_name !== '')
            ? sender.display_name
            : sender.user_id;
        const hueVar = syncAvatarHueVar(sender.user_id);
        if (this._senderAvatarFailed) {
            return html`<span class="avatar pastel-initials" style=${hueVar} @click=${this._onSenderClick}>${initialsFromName(name)}</span>`;
        }
        const sUrl = typeof sender.avatar_url === 'string' && sender.avatar_url !== ''
            ? sender.avatar_url
            : null;
        const resolved = resolveAvatarImageSrc({ avatarUrl: sUrl, seed: sender.user_id });
        return html`<span class="avatar" @click=${this._onSenderClick}>
            <img src=${resolved.src} alt="" @error=${this._onSenderAvatarError} />
        </span>`;
    }

    render() {
        if (!this.message) return html``;
        const sender = this.message.sender;
        const senderId = sender && sender.user_id;
        const isOwn = senderId === this.myUserId;
        const relevant = this._relevantContentBlocks(this.message.contents);
        const onlyCallBoundaryLayout =
            relevant.length > 0
            && relevant.every((c) => this._stringContentType(c) === 'call/boundary');
        if (onlyCallBoundaryLayout) {
            return html`
                <div class="row row-call-boundary">
                    ${relevant.map((c) => this._renderContent(c))}
                </div>
            `;
        }
        const contents = Array.isArray(this.message.contents) ? this.message.contents : [];
        const slice = this._chatUi.value;
        const selectionMode = slice && slice.selectionMode === true;
        const selected = slice && Array.isArray(slice.selectedMessageIds)
            && this.message.message_id
            && slice.selectedMessageIds.includes(this.message.message_id);
        const showSenderName = !isOwn && (this.position === 'first' || this.position === 'single');
        const senderName = sender && (typeof sender.display_name === 'string' && sender.display_name !== ''
            ? sender.display_name
            : sender.user_id);
        const bodyMain = html`${contents.map((c) => this._renderContent(c))}`;
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
                    ${bodyMain}
                    ${this._renderTailRow()}
                    <span class="quick-reactions">
                        ${EMOJI_QUICK.map((e) => html`<span @click=${(ev) => { ev.stopPropagation(); this._onReaction(e); }}>${e}</span>`)}
                    </span>
                </div>
            </div>
        `;
    }
}

customElements.define('sync-message-bubble', SyncMessageBubble);
