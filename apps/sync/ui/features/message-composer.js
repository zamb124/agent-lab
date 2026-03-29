/**
 * MessageComposer — ввод и отправка сообщений (текст, изображение, эмодзи)
 * Полный паритет с sync1 Composer.
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { formStyles } from '@platform/lib/styles/shared/form.styles.js';
import { AppEvents } from '@platform/lib/utils/types.js';
import { SyncStore } from '../store/sync.store.js';
import { senderUserId } from '../utils/sender.js';
import { SYNC_MESSAGE_TEXT_MAX_CHARS } from '../constants/sync-limits.js';
import { extractMentionedUserIdsFromPlainText } from '../utils/sync-mention-text.js';

const EMOJIS = ['😀', '😅', '😉', '😍', '🤝', '🔥', '✅', '💡', '🧠', '🚀', '📌', '🧩', '⚠️', '❌', '👍', '👀'];

function extractPlainTextFromMsg(msg) {
    const contents = msg?.contents ?? [];
    const parts = [];
    for (const c of contents) {
        if (c.type === 'text/plain' && typeof c.data?.body === 'string') {
            parts.push(c.data.body);
        }
    }
    return parts.join('\n').trim();
}

function toShortUsernameForReply(displayName) {
    const raw = (displayName || '').trim();
    if (raw === '') return 'Пользователь';
    const parts = raw.split(/\s+/).filter(p => p.trim() !== '');
    const nonEmail = parts.filter(p => !p.includes('@'));
    if (nonEmail.length > 0) return nonEmail.join(' ');
    const first = parts[0] ?? raw;
    if (first.includes('@')) return first.split('@')[0] || first;
    return raw;
}

function randomUuidV4() {
    const c = globalThis.crypto;
    if (c && typeof c.randomUUID === 'function') {
        return c.randomUUID();
    }
    if (c && typeof c.getRandomValues === 'function') {
        const buf = new Uint8Array(16);
        c.getRandomValues(buf);
        buf[6] = (buf[6] & 0x0f) | 0x40;
        buf[8] = (buf[8] & 0x3f) | 0x80;
        const hex = Array.from(buf, (byte) => byte.toString(16).padStart(2, '0')).join('');
        return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
    }
    throw new Error('Web Crypto API недоступен: нельзя сгенерировать идентификатор команды.');
}

export class MessageComposer extends PlatformElement {
    static properties = {
        channelId: { type: String },
        _text: { state: true },
        _emojiOpen: { state: true },
        _attachMenuOpen: { state: true },
        _pendingAttachments: { state: true },
        _uploading: { state: true },
        _focusedThreadId: { state: true },
        _replyToMessage: { state: true },
        _editMessage: { state: true },
        _editSourceId: { state: true },
        _isMobile: { state: true },
        _isRecording: { state: true },
        _recordingSeconds: { state: true },
        _isRecordHoldActive: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        buttonStyles,
        formStyles,
        css`
            :host {
                display: block;
                flex-shrink: 0;
            }

            .composer {
                border-top: 1px solid var(--glass-border-subtle);
                padding: var(--space-3);
            }

            @media (max-width: 767px) {
                .composer {
                    padding: var(--space-2) var(--space-2) max(var(--space-2), env(safe-area-inset-bottom, 0px));
                }
            }

            .row {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                position: relative;
            }

            .icon-btn {
                width: 44px;
                height: 44px;
                border-radius: var(--radius-lg);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-secondary);
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                transition: all var(--duration-fast);
                flex-shrink: 0;
            }

            .icon-btn:hover {
                background: var(--glass-solid-medium);
                color: var(--text-primary);
            }

            .icon-btn.record-hold-active {
                transform: scale(1.12);
            }

            .icon-btn.send {
                background: var(--accent-subtle);
                border-color: var(--accent);
                color: var(--accent);
            }

            .icon-btn.send:hover {
                background: var(--accent);
                color: white;
            }

            .textarea {
                flex: 1;
                min-width: 0;
                min-height: 44px;
                max-height: 200px;
                resize: none;
                padding: var(--space-3);
                border-radius: var(--radius-lg);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary);
                font-size: var(--text-sm);
                font-family: inherit;
                outline: none;
                overflow-wrap: anywhere;
                transition: border-color var(--duration-fast);
            }

            .textarea:focus {
                border-color: var(--accent);
            }

            .attach-popup {
                position: absolute;
                bottom: calc(100% + 8px);
                left: 0;
                min-width: 180px;
                border-radius: var(--radius-xl);
                border: 1px solid var(--glass-border-medium);
                background: var(--glass-solid-strong);
                backdrop-filter: blur(var(--glass-blur-strong));
                padding: var(--space-1);
                box-shadow: var(--glass-shadow-strong);
                z-index: 50;
                display: flex;
                flex-direction: column;
                gap: 2px;
            }

            .attach-item {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                border: none;
                background: transparent;
                color: var(--text-primary);
                font-size: var(--text-sm);
                font-family: inherit;
                cursor: pointer;
                border-radius: var(--radius-md);
                text-align: left;
                transition: background var(--duration-fast);
                user-select: none;
            }

            .attach-item:hover {
                background: var(--glass-solid-medium);
            }

            .attach-item input[type="file"] {
                display: none;
            }

            .emoji-popup {
                position: absolute;
                bottom: calc(100% + 8px);
                right: 44px;
                width: min(288px, calc(100vw - var(--space-4)));
                box-sizing: border-box;
                border-radius: var(--radius-xl);
                border: 1px solid var(--glass-border-medium);
                background: var(--glass-solid-strong);
                backdrop-filter: blur(var(--glass-blur-strong));
                padding: var(--space-2);
                box-shadow: var(--glass-shadow-strong);
                z-index: 50;
            }

            .emoji-grid {
                display: grid;
                grid-template-columns: repeat(8, minmax(0, 1fr));
                gap: var(--space-1);
                width: 100%;
            }

            .emoji-btn {
                box-sizing: border-box;
                display: flex;
                align-items: center;
                justify-content: center;
                min-width: 0;
                width: 100%;
                aspect-ratio: 1;
                background: transparent;
                border: none;
                border-radius: var(--radius-md);
                cursor: pointer;
                font-size: 18px;
                padding: 4px;
                transition: background var(--duration-fast);
                line-height: 1;
            }

            .emoji-btn:hover {
                background: var(--glass-solid-medium);
            }

            .thread-hint {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-top: var(--space-2);
            }

            .draft-bar {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                margin-bottom: var(--space-2);
                border-radius: var(--radius-lg);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                font-size: var(--text-xs);
                color: var(--text-secondary);
            }

            .draft-bar .snippet {
                flex: 1;
                min-width: 0;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            .draft-bar button {
                flex-shrink: 0;
                border: none;
                background: transparent;
                color: var(--accent);
                cursor: pointer;
                font-size: var(--text-xs);
            }

            .draft-bar.reply-draft--parent-own {
                align-items: flex-start;
                border-left: 4px solid rgb(5, 150, 105);
                background: rgba(16, 185, 129, 0.26);
                border-color: rgba(16, 185, 129, 0.35);
            }

            .draft-bar.reply-draft--parent-other {
                align-items: flex-start;
                border-left: 4px solid rgb(2, 132, 199);
                background: rgba(147, 197, 253, 0.52);
                border-color: rgba(56, 189, 248, 0.4);
            }

            .reply-draft-body {
                flex: 1;
                min-width: 0;
            }

            .reply-draft-author {
                display: block;
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                margin-bottom: 2px;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            .reply-draft--parent-own .reply-draft-author {
                color: rgb(4, 120, 87);
            }

            .reply-draft--parent-other .reply-draft-author {
                color: rgb(3, 105, 161);
            }

            .reply-draft-text {
                display: block;
                font-size: var(--text-xs);
                color: var(--text-primary);
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            .attachments-strip {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
                padding: var(--space-2) 0;
            }

            .attachment-thumb-wrap {
                position: relative;
                flex-shrink: 0;
            }

            .attachment-thumb {
                width: 72px;
                height: 72px;
                border-radius: var(--radius-lg);
                object-fit: cover;
                border: 1px solid var(--glass-border-subtle);
                display: block;
            }

            .attachment-thumb-doc {
                width: 72px;
                height: 72px;
                border-radius: var(--radius-lg);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                gap: 4px;
                color: var(--text-secondary);
            }

            .attachment-thumb-doc-name {
                font-size: 9px;
                color: var(--text-tertiary);
                max-width: 60px;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                text-align: center;
            }

            .attachment-remove {
                position: absolute;
                top: -6px;
                right: -6px;
                width: 18px;
                height: 18px;
                border-radius: 50%;
                background: var(--error, #ef4444);
                color: white;
                border: none;
                cursor: pointer;
                font-size: 11px;
                display: flex;
                align-items: center;
                justify-content: center;
                line-height: 1;
                padding: 0;
            }

            .uploading-hint {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                padding: var(--space-1) 0;
            }

            .recording-hint {
                display: inline-flex;
                align-items: center;
                gap: 8px;
                font-size: var(--text-sm);
                color: #f87171;
                font-weight: var(--font-semibold);
                padding: var(--space-1) 0;
            }

            .recording-hint-dot {
                width: 9px;
                height: 9px;
                border-radius: 50%;
                background: #ef4444;
                box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.8);
                animation: recording-dot-pulse 1.2s ease-in-out infinite;
                flex-shrink: 0;
            }

            .recording-hint-time {
                font-weight: var(--font-bold);
                letter-spacing: 0.02em;
            }

            @keyframes recording-dot-pulse {
                0% {
                    opacity: 1;
                    box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.8);
                }
                70% {
                    opacity: 0.45;
                    box-shadow: 0 0 0 8px rgba(239, 68, 68, 0);
                }
                100% {
                    opacity: 1;
                    box-shadow: 0 0 0 0 rgba(239, 68, 68, 0);
                }
            }

            .icon-btn.mic {
                background: rgba(239, 68, 68, 0.12);
                border-color: rgba(239, 68, 68, 0.4);
                color: rgb(185, 28, 28);
            }

            .icon-btn.mic.recording {
                background: rgba(239, 68, 68, 0.22);
                color: rgb(153, 27, 27);
                animation: rec-pulse 0.9s ease-in-out infinite alternate;
            }

            .icon-btn.send.recording {
                animation: rec-pulse 0.9s ease-in-out infinite alternate;
            }

            @keyframes rec-pulse {
                from {
                    box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.22);
                }
                to {
                    box-shadow: 0 0 0 6px rgba(239, 68, 68, 0.08);
                }
            }

            .mention-popup {
                position: absolute;
                bottom: calc(100% + 8px);
                left: 44px;
                right: 88px;
                max-height: 220px;
                overflow-y: auto;
                border-radius: var(--radius-xl);
                border: 1px solid var(--glass-border-medium);
                background: var(--glass-solid-strong);
                backdrop-filter: blur(var(--glass-blur-strong));
                padding: var(--space-1);
                box-shadow: var(--glass-shadow-strong);
                z-index: 55;
            }

            .mention-item {
                display: block;
                width: 100%;
                padding: var(--space-2) var(--space-3);
                border: none;
                border-radius: var(--radius-md);
                background: transparent;
                color: var(--text-primary);
                font-size: var(--text-sm);
                font-family: inherit;
                text-align: left;
                cursor: pointer;
                transition: background var(--duration-fast);
            }

            .mention-item:hover,
            .mention-item.is-active {
                background: var(--glass-solid-medium);
            }

            .mention-item-id {
                display: block;
                font-size: 10px;
                color: var(--text-tertiary);
                margin-top: 2px;
            }
        `
    ];

    constructor() {
        super();
        this.channelId = null;
        this._text = '';
        this._emojiOpen = false;
        this._attachMenuOpen = false;
        this._pendingAttachments = [];
        this._uploading = false;
        this._focusedThreadId = null;
        this._replyToMessage = null;
        this._editMessage = null;
        this._editSourceId = null;
        this._typingDebounceTimer = null;
        this._lastTypingContext = null;
        this._mentionOpen = false;
        this._mentionFilter = '';
        this._mentionAnchor = 0;
        this._mentionCaret = 0;
        this._mentionIndex = 0;
        this._channelMembers = null;
        this._membersChannelId = null;
        this._mentionLoading = false;
        /** user_id выбранные из попапа (не обязательно в формате UUID в тексте). */
        this._mentionPickUserIds = [];
        this._isMobile = false;
        this._isRecording = false;
        this._recordingSeconds = 0;
        this._isRecordHoldActive = false;
        this._recordingStartAt = 0;
        this._recordingChunks = [];
        this._mediaRecorder = null;
        this._recordingMimeType = '';
        this._recordingTickTimer = null;
        this._recordingStream = null;
        this._sendHoldTimer = null;
        this._sendHoldPointerId = null;
        this._sendHoldTriggered = false;
        this._boundWindowResize = () => this._updateMobileFlag();
    }

    connectedCallback() {
        super.connectedCallback();
        window.addEventListener('resize', this._boundWindowResize);
        this._updateMobileFlag();
        this._unsubscribe = SyncStore.subscribe(state => {
            this._focusedThreadId = state.chat.focusedThreadId;
            const reply = state.chat.replyToMessage;
            const edit = state.chat.editMessage;
            this._replyToMessage = reply;
            this._editMessage = edit;
            const eid = edit?.id ?? null;
            if (eid !== this._editSourceId) {
                this._editSourceId = eid;
                if (edit && eid) {
                    const t = extractPlainTextFromMsg(edit);
                    this._text = t;
                }
            }
        });
    }

    disconnectedCallback() {
        super.disconnectedCallback?.();
        window.removeEventListener('resize', this._boundWindowResize);
        clearTimeout(this._typingDebounceTimer);
        this._typingDebounceTimer = null;
        const ctx = this._lastTypingContext;
        if (ctx) {
            this._emitTypingWs(false, ctx.channelId, ctx.threadId);
        }
        this._unsubscribe?.();
        this._clearSendHoldTimer();
        this._clearRecordingTick();
        this._stopCaptureTracks();
    }

    updated(changedProperties) {
        super.updated(changedProperties);
        if (changedProperties.has('channelId')) {
            this._membersChannelId = null;
            this._channelMembers = null;
            this._mentionOpen = false;
            this._mentionPickUserIds = [];
        }
        if (changedProperties.has('channelId') || changedProperties.has('_focusedThreadId')) {
            const ctx = this._lastTypingContext;
            if (ctx) {
                this._emitTypingWs(false, ctx.channelId, ctx.threadId);
            }
        }
        if (!changedProperties.has('_replyToMessage')) return;
        const prev = changedProperties.get('_replyToMessage');
        const cur = this._replyToMessage;
        if (!cur || this._editMessage) return;
        if (prev?.id === cur.id) return;
        queueMicrotask(() => this._focusTextarea());
    }

    _focusTextarea() {
        const ta = this.shadowRoot?.querySelector('textarea.textarea');
        if (!ta) return;
        ta.focus();
        const len = ta.value.length;
        try {
            ta.setSelectionRange(len, len);
        } catch {
            /* ignore */
        }
    }

    _companyMemberName(userId) {
        if (typeof userId !== 'string' || userId === '') return userId;
        const list = SyncStore.state.companyMembers?.list;
        if (!Array.isArray(list)) return userId;
        const cm = list.find(c => c.user_id === userId);
        if (typeof cm?.name === 'string' && cm.name.trim() !== '') return cm.name.trim();
        return userId;
    }

    async _ensureChannelMembers() {
        if (!this.channelId) return;
        if (this._membersChannelId === this.channelId && Array.isArray(this._channelMembers)) return;
        const syncApi = this.services.get('syncApi');
        if (!syncApi) throw new Error('syncApi не зарегистрирован.');
        this._mentionLoading = true;
        this.requestUpdate();
        const list = await syncApi.getChannelMembers(this.channelId);
        if (!Array.isArray(list)) {
            throw new Error('getChannelMembers: ожидается массив.');
        }
        this._channelMembers = list;
        this._membersChannelId = this.channelId;
        this._mentionLoading = false;
        this.requestUpdate();
    }

    _mentionRowsFiltered() {
        const myId = this.auth?.user?.id;
        const raw = this._channelMembers;
        if (!Array.isArray(raw)) return [];
        let rows = raw
            .filter(m => m && typeof m.user_id === 'string' && m.user_id !== '' && m.user_id !== myId)
            .map(m => ({
                user_id: m.user_id,
                label: this._companyMemberName(m.user_id),
            }));
        const q = (this._mentionFilter || '').trim().toLowerCase();
        if (q !== '') {
            rows = rows.filter(
                r =>
                    r.label.toLowerCase().includes(q) ||
                    r.user_id.toLowerCase().includes(q)
            );
        }
        return rows;
    }

    _syncMentionUiFromCaret(text, caret) {
        const before = text.slice(0, caret);
        const at = before.lastIndexOf('@');
        if (at < 0) {
            this._mentionOpen = false;
            return;
        }
        const afterAt = before.slice(at + 1);
        if (/[\s\n]/.test(afterAt)) {
            this._mentionOpen = false;
            return;
        }
        this._mentionOpen = true;
        this._mentionAnchor = at;
        this._mentionCaret = caret;
        this._mentionFilter = afterAt;
        this._mentionIndex = 0;
        this._emojiOpen = false;
        this._attachMenuOpen = false;
        void this._ensureChannelMembers();
    }

    _pickMention(userId) {
        if (typeof userId !== 'string' || userId === '') {
            throw new Error('pickMention: userId обязателен.');
        }
        const text = this._text;
        const anchor = this._mentionAnchor;
        const caret = this._mentionCaret;
        const before = text.slice(0, anchor);
        const after = text.slice(caret);
        const insert = `@${userId} `;
        let next = before + insert + after;
        if (next.length > SYNC_MESSAGE_TEXT_MAX_CHARS) {
            window.dispatchEvent(
                new CustomEvent(AppEvents.TOAST_SHOW, {
                    detail: {
                        type: 'warning',
                        message: `Не больше ${SYNC_MESSAGE_TEXT_MAX_CHARS} символов в сообщении (как в Telegram).`,
                        duration: 4000,
                    },
                })
            );
            next = next.slice(0, SYNC_MESSAGE_TEXT_MAX_CHARS);
        }
        this._text = next;
        if (!this._mentionPickUserIds.includes(userId)) {
            this._mentionPickUserIds.push(userId);
        }
        this._mentionOpen = false;
        this._scheduleTypingPing();
        this.requestUpdate();
        const pos = Math.min(before.length + insert.length, next.length);
        queueMicrotask(() => {
            const ta = this.shadowRoot?.querySelector('textarea.textarea');
            if (!ta) return;
            ta.focus();
            try {
                ta.setSelectionRange(pos, pos);
            } catch {
                /* ignore */
            }
        });
    }

    _onTextInput(e) {
        const raw = e.target.value;
        const caret =
            typeof e.target.selectionStart === 'number' ? e.target.selectionStart : raw.length;
        if (raw.length > SYNC_MESSAGE_TEXT_MAX_CHARS) {
            const clipped = raw.slice(0, SYNC_MESSAGE_TEXT_MAX_CHARS);
            e.target.value = clipped;
            this._text = clipped;
            window.dispatchEvent(
                new CustomEvent(AppEvents.TOAST_SHOW, {
                    detail: {
                        type: 'warning',
                        message: `Не больше ${SYNC_MESSAGE_TEXT_MAX_CHARS} символов в сообщении (как в Telegram).`,
                        duration: 4000,
                    },
                })
            );
            this._syncMentionUiFromCaret(clipped, clipped.length);
            return;
        }
        this._text = raw;
        this._syncMentionUiFromCaret(raw, caret);
        this._scheduleTypingPing();
    }

    _emitTypingWs(typing, channelId, threadId) {
        const ws = this.services.get('syncWs');
        if (!ws || ws.state !== 'open') {
            if (!typing) {
                this._lastTypingContext = null;
            }
            return;
        }
        if (!channelId) {
            if (!typing) {
                this._lastTypingContext = null;
            }
            return;
        }
        const tid = threadId === undefined || threadId === null ? null : threadId;
        ws.sendJson({
            id: randomUuidV4(),
            type: 'channels.typing',
            payload: { channel_id: channelId, thread_id: tid, typing },
        });
        if (typing) {
            this._lastTypingContext = { channelId, threadId: tid };
        } else {
            this._lastTypingContext = null;
        }
    }

    _scheduleTypingPing() {
        clearTimeout(this._typingDebounceTimer);
        if (!this.channelId) {
            return;
        }
        const t = this._text.trim();
        if (t === '') {
            const ctx = this._lastTypingContext;
            if (ctx) {
                this._emitTypingWs(false, ctx.channelId, ctx.threadId);
            }
            return;
        }
        this._typingDebounceTimer = setTimeout(() => {
            this._typingDebounceTimer = null;
            if (!this.channelId || this._text.trim() === '') {
                return;
            }
            const tid = this._focusedThreadId ?? null;
            this._emitTypingWs(true, this.channelId, tid);
        }, 450);
    }

    _flushTypingNotTyping() {
        clearTimeout(this._typingDebounceTimer);
        this._typingDebounceTimer = null;
        const ctx = this._lastTypingContext;
        if (ctx) {
            this._emitTypingWs(false, ctx.channelId, ctx.threadId);
        }
    }

    _onTextareaBlur() {
        this._flushTypingNotTyping();
    }

    async _sendText() {
        const text = this._text.trim();
        const hasPending = this._pendingAttachments.length > 0;

        if (!this.channelId) return;
        if (!text && !hasPending) return;

        this._flushTypingNotTyping();

        if (text.length > SYNC_MESSAGE_TEXT_MAX_CHARS) {
            window.dispatchEvent(
                new CustomEvent(AppEvents.TOAST_SHOW, {
                    detail: {
                        type: 'error',
                        message: `Сообщение не длиннее ${SYNC_MESSAGE_TEXT_MAX_CHARS} символов.`,
                        duration: 5000,
                    },
                })
            );
            return;
        }

        if (hasPending) {
            await this._sendWithAttachments(text);
            return;
        }

        const syncApi = this.services.get('syncApi');
        const edit = this._editMessage;
        if (edit?.id) {
            const contents = [{ type: 'text/plain', data: { body: text }, order: 0 }];
            await syncApi.editMessage(this.channelId, edit.id, { contents });
            SyncStore.clearEditMessage();
            this._text = '';
            await SyncStore.loadMessages(syncApi, this.channelId);
            return;
        }

        const ws = this.services.get('syncWs');
        if (!ws) throw new Error('WebSocket не подключен.');

        const commandId = randomUuidV4();
        const auth = this.auth;
        const userId = auth?.user?.id;
        if (!userId) throw new Error('Не удалось определить user_id.');
        const displayName =
            typeof auth?.user?.name === 'string' && auth.user.name.trim() !== ''
                ? auth.user.name.trim()
                : 'Вы';

        const parentId = this._replyToMessage?.id ?? null;
        const fromUuid = extractMentionedUserIdsFromPlainText(text);
        const fromPicks = this._mentionPickUserIds.filter(uid => text.includes(`@${uid}`));
        const mentionedUserIds = [...new Set([...fromUuid, ...fromPicks])];
        const messageCreate = {
            thread_id: this._focusedThreadId,
            parent_message_id: parentId,
            contents: [{ type: 'text/plain', data: { body: text }, order: 0 }],
            ...(mentionedUserIds.length > 0 ? { mentioned_user_ids: mentionedUserIds } : {}),
        };

        const pending = {
            id: `pending:${commandId}`,
            channel_id: this.channelId,
            thread_id: this._focusedThreadId,
            parent_message_id: parentId,
            sender: { user_id: userId, id: userId, display_name: displayName, avatar_url: null },
            status: 'pending',
            sent_at: new Date().toISOString(),
            edited_at: null,
            contents: messageCreate.contents,
        };

        this._text = '';
        SyncStore.clearReplyToMessage();
        SyncStore.addPending(commandId, pending);

        try {
            ws.sendJson({
                id: commandId,
                type: 'messages.send',
                payload: { channel_id: this.channelId, body: messageCreate },
            });
        } catch (e) {
            SyncStore.failPending(commandId);
            throw e;
        }
        this._mentionPickUserIds = [];
    }

    async _sendWithAttachments(text) {
        if (!this.channelId) throw new Error('Выбери канал.');
        this._uploading = true;

        const syncApi = this.services.get('syncApi');
        const snapshot = this._pendingAttachments.slice();

        const uploads = await Promise.all(snapshot.map(a => syncApi.uploadFile(a.file)));

        snapshot.forEach(a => { if (a.localUrl) URL.revokeObjectURL(a.localUrl); });

        const fileBlocks = uploads.map((res, idx) => {
            if (!res?.file_id) throw new Error(`Некорректный ответ загрузки файла #${idx + 1}.`);
            return {
                type: snapshot[idx].contentType,
                data: {
                    file_id: res.file_id,
                    filename: res.original_name,
                    mime_type: res.content_type,
                    size: res.file_size,
                },
                order: idx,
            };
        });

        const contents = [];
        if (text) {
            contents.push({ type: 'text/plain', data: { body: text }, order: 0 });
            fileBlocks.forEach((b, i) => { b.order = i + 1; });
        }
        contents.push(...fileBlocks);

        const parentId = this._replyToMessage?.id ?? null;
        const fromUuid = extractMentionedUserIdsFromPlainText(text);
        const fromPicks = this._mentionPickUserIds.filter(uid => text.includes(`@${uid}`));
        const mentionedUserIds = [...new Set([...fromUuid, ...fromPicks])];
        const messageCreate = {
            thread_id: this._focusedThreadId,
            parent_message_id: parentId,
            contents,
            ...(mentionedUserIds.length > 0 ? { mentioned_user_ids: mentionedUserIds } : {}),
        };

        this._text = '';
        this._pendingAttachments = [];
        this._uploading = false;
        SyncStore.clearReplyToMessage();
        await syncApi.sendMessage(this.channelId, messageCreate);
        this._mentionPickUserIds = [];
        await SyncStore.loadMessages(syncApi, this.channelId);
    }

    _pickAttachments(contentType, e) {
        const files = Array.from(e.target.files || []);
        if (files.length === 0) return;
        e.target.value = '';
        this._attachMenuOpen = false;

        const staged = files.map(file => ({
            file,
            contentType,
            localUrl: file.type.startsWith('image/') ? URL.createObjectURL(file) : null,
        }));
        this._pendingAttachments = [...this._pendingAttachments, ...staged];
    }

    _removeAttachment(idx) {
        const next = [...this._pendingAttachments];
        const removed = next.splice(idx, 1)[0];
        if (removed?.localUrl) URL.revokeObjectURL(removed.localUrl);
        this._pendingAttachments = next;
    }

    _insertEmoji(em) {
        if (!em.trim()) throw new Error('emoji обязателен.');
        let next = this._text + em;
        if (next.length > SYNC_MESSAGE_TEXT_MAX_CHARS) {
            window.dispatchEvent(
                new CustomEvent(AppEvents.TOAST_SHOW, {
                    detail: {
                        type: 'warning',
                        message: `Не больше ${SYNC_MESSAGE_TEXT_MAX_CHARS} символов в сообщении (как в Telegram).`,
                        duration: 4000,
                    },
                })
            );
            next = next.slice(0, SYNC_MESSAGE_TEXT_MAX_CHARS);
        }
        this._text = next;
        this._emojiOpen = false;
        this._scheduleTypingPing();
    }

    _onKeyDown(e) {
        const rows = this._mentionRowsFiltered();
        if (this._mentionOpen) {
            if (e.key === 'Escape') {
                e.preventDefault();
                this._mentionOpen = false;
                this.requestUpdate();
                return;
            }
            if (rows.length > 0) {
                if (e.key === 'ArrowDown') {
                    e.preventDefault();
                    this._mentionIndex = Math.min(this._mentionIndex + 1, rows.length - 1);
                    this.requestUpdate();
                    return;
                }
                if (e.key === 'ArrowUp') {
                    e.preventDefault();
                    this._mentionIndex = Math.max(this._mentionIndex - 1, 0);
                    this.requestUpdate();
                    return;
                }
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    const row = rows[this._mentionIndex];
                    if (row) this._pickMention(row.user_id);
                    return;
                }
            }
        }
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            this._sendText();
        }
    }

    _replySnippet() {
        const m = this._replyToMessage;
        if (!m) return '';
        const t = extractPlainTextFromMsg(m).slice(0, 160);
        return t || 'Сообщение';
    }

    _replyQuotedParentIsOwn() {
        const m = this._replyToMessage;
        const myId = this.auth?.user?.id;
        const sid = senderUserId(m?.sender);
        return typeof myId === 'string' && typeof sid === 'string' && myId === sid;
    }

    _replyAuthorLabel() {
        const m = this._replyToMessage;
        return toShortUsernameForReply(m?.sender?.display_name ?? '');
    }

    _renderAttachmentsStrip() {
        if (this._pendingAttachments.length === 0) return '';
        return html`
            <div class="attachments-strip">
                ${this._pendingAttachments.map((a, idx) => html`
                    <div class="attachment-thumb-wrap">
                        ${a.localUrl ? html`
                            <img class="attachment-thumb" src=${a.localUrl} alt=${a.file.name}>
                        ` : html`
                            <div class="attachment-thumb-doc">
                                <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
                                    <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6z" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
                                    <path d="M14 2v6h6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
                                </svg>
                                <span class="attachment-thumb-doc-name">${a.file.name}</span>
                            </div>
                        `}
                        <button class="attachment-remove" title="Удалить" @click=${() => this._removeAttachment(idx)}>×</button>
                    </div>
                `)}
                ${this._uploading ? html`<span class="uploading-hint">Отправка...</span>` : ''}
            </div>
        `;
    }

    _updateMobileFlag() {
        this._isMobile = window.innerWidth <= 767;
    }

    _clearSendHoldTimer() {
        if (this._sendHoldTimer !== null) {
            clearTimeout(this._sendHoldTimer);
            this._sendHoldTimer = null;
        }
    }

    _clearRecordingTick() {
        if (this._recordingTickTimer !== null) {
            clearInterval(this._recordingTickTimer);
            this._recordingTickTimer = null;
        }
    }

    _stopCaptureTracks() {
        if (!this._recordingStream) {
            return;
        }
        this._recordingStream.getTracks().forEach((track) => track.stop());
        this._recordingStream = null;
    }

    _canStartHoldRecording() {
        if (typeof this.channelId !== 'string' || this.channelId === '') {
            return false;
        }
        if (this._uploading || this._isRecording) {
            return false;
        }
        if (this._pendingAttachments.length > 0) {
            return false;
        }
        return this._text.trim() === '';
    }

    _pickMediaRecorderMimeType() {
        const variants = [
            'audio/webm;codecs=opus',
            'audio/webm',
            'audio/ogg;codecs=opus',
            'audio/mp4',
        ];
        for (const variant of variants) {
            if (MediaRecorder.isTypeSupported(variant)) {
                return variant;
            }
        }
        return '';
    }

    _formatRecordingSeconds() {
        const total = Math.max(0, Math.floor(this._recordingSeconds));
        const mins = Math.floor(total / 60);
        const secs = total % 60;
        return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
    }

    _showRecordingError(message) {
        const text = typeof message === 'string' && message.trim() !== ''
            ? message
            : 'Не удалось запустить запись аудио.';
        window.dispatchEvent(
            new CustomEvent(AppEvents.TOAST_SHOW, {
                detail: {
                    type: 'error',
                    message: text,
                    duration: 5000,
                },
            })
        );
    }

    async _safeStartRecording() {
        try {
            await this._startRecording();
        } catch (err) {
            this._sendHoldTriggered = false;
            const message = err instanceof Error ? err.message : String(err);
            this._showRecordingError(message);
        }
    }

    async _startRecording() {
        if (!this._canStartHoldRecording()) {
            return;
        }
        const hostname = window.location.hostname.toLowerCase();
        const isLocalLvhMe = hostname === 'lvh.me' || hostname.endsWith('.lvh.me');
        const canUseGetUserMedia = Boolean(
            navigator.mediaDevices && typeof navigator.mediaDevices.getUserMedia === 'function'
        );
        if (!window.isSecureContext && !isLocalLvhMe) {
            throw new Error('Запись доступна только в HTTPS или localhost.');
        }
        if (!canUseGetUserMedia) {
            if (isLocalLvhMe && window.location.protocol === 'http:') {
                throw new Error(
                    'Для http://*.lvh.me браузер блокирует доступ к микрофону. '
                    + 'Используй HTTPS или добавь origin в chrome://flags/#unsafely-treat-insecure-origin-as-secure.'
                );
            }
            throw new Error('Браузер не поддерживает запись с микрофона.');
        }
        this._recordingChunks = [];
        this._recordingStartAt = Date.now();
        this._recordingSeconds = 0;
        this._recordingStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const mimeType = this._pickMediaRecorderMimeType();
        this._recordingMimeType = mimeType !== '' ? mimeType : 'audio/webm';
        this._mediaRecorder = mimeType !== ''
            ? new MediaRecorder(this._recordingStream, { mimeType })
            : new MediaRecorder(this._recordingStream);
        this._mediaRecorder.ondataavailable = (event) => {
            if (event.data && event.data.size > 0) {
                this._recordingChunks.push(event.data);
            }
        };
        this._mediaRecorder.onstop = () => {
            const durationMs = Date.now() - this._recordingStartAt;
            const blob = new Blob(this._recordingChunks, { type: this._recordingMimeType });
            this._recordingChunks = [];
            this._isRecording = false;
            this._recordingSeconds = 0;
            this._clearRecordingTick();
            this._stopCaptureTracks();
            this._mediaRecorder = null;
            void this._sendRecordedAudio(blob, durationMs).catch((err) => {
                const message = err instanceof Error ? err.message : String(err);
                this._showRecordingError(message);
            });
        };
        this._mediaRecorder.start();
        this._isRecording = true;
        this._recordingTickTimer = setInterval(() => {
            this._recordingSeconds = Math.floor((Date.now() - this._recordingStartAt) / 1000);
        }, 250);
    }

    async _stopRecording() {
        if (!this._mediaRecorder) {
            return;
        }
        if (this._mediaRecorder.state === 'inactive') {
            return;
        }
        this._mediaRecorder.stop();
    }

    async _sendRecordedAudio(blob, durationMs) {
        if (!(blob instanceof Blob) || blob.size === 0) {
            throw new Error('Записанное аудио пустое.');
        }
        if (durationMs < 250) {
            return;
        }
        if (typeof this.channelId !== 'string' || this.channelId === '') {
            throw new Error('Канал не выбран.');
        }
        const mimeType = blob.type || this._recordingMimeType;
        if (mimeType === '') {
            throw new Error('mime_type аудио не определен.');
        }
        this._uploading = true;
        const syncApi = this.services.get('syncApi');
        try {
            const ext = mimeType.includes('ogg') ? 'ogg' : 'webm';
            const file = new File([blob], `voice-${Date.now()}.${ext}`, { type: mimeType });
            const uploaded = await syncApi.uploadFile(file);
            if (!uploaded || typeof uploaded.file_id !== 'string' || uploaded.file_id === '') {
                throw new Error('Некорректный ответ загрузки аудио.');
            }
            const parentId = this._replyToMessage?.id ?? null;
            const contents = [
                {
                    type: 'file/audio',
                    data: {
                        file_id: uploaded.file_id,
                        filename: uploaded.original_name,
                        mime_type: uploaded.content_type,
                        size: uploaded.file_size,
                        duration_ms: durationMs,
                        waveform: null,
                        transcription_status: 'idle',
                        transcription_text: null,
                        transcription_error: null,
                    },
                    order: 0,
                },
            ];
            await syncApi.sendMessage(this.channelId, {
                thread_id: this._focusedThreadId,
                parent_message_id: parentId,
                contents,
            });
            SyncStore.clearReplyToMessage();
            await SyncStore.loadMessages(syncApi, this.channelId);
        } finally {
            this._uploading = false;
        }
    }

    _onMicPointerDown(e) {
        if (this._isMobile) {
            return;
        }
        e.preventDefault();
        this._isRecordHoldActive = true;
        void this._safeStartRecording();
    }

    _onMicPointerUp(e) {
        if (this._isMobile) {
            return;
        }
        e.preventDefault();
        this._isRecordHoldActive = false;
        void this._stopRecording();
    }

    _onSendPointerDown(e) {
        if (!this._isMobile || !this._canStartHoldRecording()) {
            return;
        }
        this._sendHoldPointerId = e.pointerId;
        this._isRecordHoldActive = true;
        this._clearSendHoldTimer();
        this._sendHoldTimer = setTimeout(() => {
            this._sendHoldTriggered = true;
            void this._safeStartRecording();
        }, 180);
    }

    _onSendPointerUp(e) {
        if (!this._isMobile || this._sendHoldPointerId !== e.pointerId) {
            return;
        }
        this._clearSendHoldTimer();
        this._sendHoldPointerId = null;
        this._isRecordHoldActive = false;
        if (this._isRecording) {
            e.preventDefault();
            void this._stopRecording();
        }
    }

    _onSendPointerCancel(e) {
        if (!this._isMobile || this._sendHoldPointerId !== e.pointerId) {
            return;
        }
        this._clearSendHoldTimer();
        this._sendHoldPointerId = null;
        this._isRecordHoldActive = false;
        if (this._isRecording) {
            void this._stopRecording();
        }
    }

    _onSendClick(e) {
        if (this._isMobile && this._isRecording) {
            e.preventDefault();
            this._sendHoldTriggered = false;
            this._clearSendHoldTimer();
            this._sendHoldPointerId = null;
            this._isRecordHoldActive = false;
            void this._stopRecording();
            return;
        }
        if (this._sendHoldTriggered) {
            e.preventDefault();
            this._sendHoldTriggered = false;
            return;
        }
        void this._sendText();
    }

    render() {
        const mentionRows = this._mentionOpen ? this._mentionRowsFiltered() : [];
        return html`
            <div class="composer">
                ${this._editMessage ? html`
                    <div class="draft-bar">
                        <span>Редактирование сообщения</span>
                        <button type="button" @click=${() => SyncStore.clearEditMessage()}>Отмена</button>
                    </div>
                ` : ''}
                ${this._replyToMessage && !this._editMessage ? html`
                    <div class="draft-bar reply-draft ${this._replyQuotedParentIsOwn() ? 'reply-draft--parent-own' : 'reply-draft--parent-other'}">
                        <div class="reply-draft-body">
                            <span class="reply-draft-author">${this._replyAuthorLabel()}</span>
                            <span class="reply-draft-text">${this._replySnippet()}</span>
                        </div>
                        <button type="button" @click=${() => SyncStore.clearReplyToMessage()}>Отмена</button>
                    </div>
                ` : ''}
                ${this._renderAttachmentsStrip()}
                ${this._isRecording ? html`
                    <div class="recording-hint">
                        <span class="recording-hint-dot"></span>
                        <span>Запись</span>
                        <span class="recording-hint-time">${this._formatRecordingSeconds()}</span>
                    </div>
                ` : ''}
                <div class="row">
                    <button class="icon-btn" title="Прикрепить файл" @click=${() => { this._attachMenuOpen = !this._attachMenuOpen; this._emojiOpen = false; }}>
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                            <path d="M12.5 6.5L6.4 12.6a4 4 0 105.7 5.7l7.1-7.1a6 6 0 10-8.5-8.5l-7.1 7.1" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
                        </svg>
                    </button>

                    <textarea
                        class="textarea"
                        rows="1"
                        placeholder="Сообщение..."
                        .value=${this._text}
                        @input=${this._onTextInput}
                        @blur=${this._onTextareaBlur}
                        @keydown=${this._onKeyDown}
                    ></textarea>

                    <button
                        class="icon-btn"
                        title="Эмодзи"
                        @click=${() => { this._emojiOpen = !this._emojiOpen; this._attachMenuOpen = false; }}
                    >
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                            <path d="M12 22a10 10 0 110-20 10 10 0 010 20z" stroke="currentColor" stroke-width="1.8"/>
                            <path d="M8.5 10.2h.01M15.5 10.2h.01" stroke="currentColor" stroke-width="2.6" stroke-linecap="round"/>
                            <path d="M8.2 14.2c1.1 1.3 2.4 2 3.8 2s2.7-.7 3.8-2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
                        </svg>
                    </button>

                    ${!this._isMobile ? html`
                        <button
                            class="icon-btn mic ${this._isRecording ? 'recording' : ''} ${this._isRecordHoldActive ? 'record-hold-active' : ''}"
                            title="Зажмите для записи"
                            @pointerdown=${this._onMicPointerDown}
                            @pointerup=${this._onMicPointerUp}
                            @pointercancel=${this._onMicPointerUp}
                            @pointerleave=${this._onMicPointerUp}
                        >
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                                <rect x="9" y="3" width="6" height="12" rx="3" stroke="currentColor" stroke-width="1.8"></rect>
                                <path d="M5 11a7 7 0 0014 0M12 18v3M9 21h6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"></path>
                            </svg>
                        </button>
                    ` : ''}

                    <button
                        class="icon-btn send ${this._isMobile && this._isRecording ? 'recording' : ''} ${this._isMobile && this._isRecordHoldActive ? 'record-hold-active' : ''}"
                        title=${this._isMobile && this._isRecording ? 'Остановить запись' : 'Отправить'}
                        @click=${this._onSendClick}
                        @pointerdown=${this._onSendPointerDown}
                        @pointerup=${this._onSendPointerUp}
                        @pointercancel=${this._onSendPointerCancel}
                    >
                        ${this._isMobile && this._isRecording ? html`
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                                <rect x="7" y="7" width="10" height="10" rx="2.2" fill="currentColor"></rect>
                            </svg>
                        ` : html`
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                                <path d="M21.2 3.6L10.1 14.7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
                                <path d="M21.2 3.6l-7.2 19.2-3.3-7.7-7.7-3.3 18.2-8.2z" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
                            </svg>
                        `}
                    </button>

                    ${this._attachMenuOpen ? html`
                        <div class="attach-popup">
                            <label class="attach-item">
                                <input type="file" accept="image/*,video/*" multiple @change=${e => this._pickAttachments('file/image', e)}>
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                                    <rect x="3" y="3" width="18" height="18" rx="3" stroke="currentColor" stroke-width="1.8"/>
                                    <circle cx="8.5" cy="8.5" r="1.5" stroke="currentColor" stroke-width="1.5"/>
                                    <path d="M3 16l5-5 4 4 3-3 6 6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
                                </svg>
                                Фото или видео
                            </label>
                            <label class="attach-item">
                                <input type="file" accept="*/*" multiple @change=${e => this._pickAttachments('file/document', e)}>
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                                    <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6z" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
                                    <path d="M14 2v6h6M9 13h6M9 17h4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
                                </svg>
                                Файл
                            </label>
                        </div>
                    ` : ''}
                    ${this._emojiOpen ? html`
                        <div class="emoji-popup">
                            <div class="emoji-grid">
                                ${EMOJIS.map(em => html`
                                    <button class="emoji-btn" @click=${() => this._insertEmoji(em)}>${em}</button>
                                `)}
                            </div>
                        </div>
                    ` : ''}
                    ${this._mentionOpen ? html`
                        <div class="mention-popup" role="listbox">
                            ${this._mentionLoading
                                ? html`<div class="mention-item" tabindex="-1">Загрузка…</div>`
                                : ''}
                            ${!this._mentionLoading && mentionRows.length === 0
                                ? html`<div class="mention-item" tabindex="-1">Нет совпадений</div>`
                                : ''}
                            ${mentionRows.map(
                                (r, i) => html`
                                    <button
                                        type="button"
                                        class="mention-item ${i === this._mentionIndex ? 'is-active' : ''}"
                                        role="option"
                                        @click=${() => this._pickMention(r.user_id)}
                                    >
                                        ${r.label}
                                        <span class="mention-item-id">${r.user_id}</span>
                                    </button>
                                `
                            )}
                        </div>
                    ` : ''}
                </div>

                ${this._focusedThreadId ? html`
                    <div class="thread-hint">Фокус на тред: новые сообщения уйдут в выбранный thread_id.</div>
                ` : ''}
            </div>
        `;
    }
}

customElements.define('message-composer', MessageComposer);
