/**
 * sync-message-composer — поле ввода с поддержкой:
 *   - reply mode (subscribe 'sync/messages_store/reply_mode_set')
 *   - edit mode (subscribe 'sync/messages_store/edit_mode_set')
 *   - file upload (drag-and-drop, paste, кнопка)
 *   - voice recording (MediaRecorder)
 *   - mention autocomplete (popup при '@')
 *   - typing notify (debounce 1500ms)
 *   - length limit SYNC_MESSAGE_TEXT_MAX_CHARS
 *
 * Отправка/редактирование — отдельные `createAsyncOp` фабрики:
 * `useOp('sync/messages_send')`, `useOp('sync/messages_edit')`.
 * Локальный optimistic-state — slice `sync/messages_store`
 * (`useSlice('sync/messages_store').addOptimistic / failOptimistic / setReplyMode / setEditMode`).
 * Загрузка файла — `useOp('sync/file_upload')`.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';
import { SYNC_MESSAGE_TEXT_MAX_CHARS } from './_helpers/sync-limits.js';
import { resolveDisplayName } from '../_helpers/sync-id-resolvers.js';
import { getUserMediaCompat, hasGetUserMediaApi, pickVoiceMimeType } from '@platform/lib/utils/voice-recording.js';

const TYPING_DEBOUNCE_MS = 1500;

const VOICE_DRAFT_WAVE_HEIGHTS_PX = Object.freeze([
    12, 20, 14, 24, 16, 22, 10, 26, 18, 14, 20, 16, 22, 12, 24, 18,
]);

function formatVoiceDurationMs(ms) {
    const n = typeof ms === 'number' && ms > 0 ? ms : 0;
    const totalSec = Math.floor(n / 1000);
    const m = Math.floor(totalSec / 60);
    const s = totalSec % 60;
    return `${m}:${s.toString().padStart(2, '0')}`;
}

export class SyncMessageComposer extends PlatformElement {
    static properties = {
        channelId: { type: String },
        threadId: { type: String, attribute: 'thread-id' },
        _draft: { state: true },
        _attachments: { state: true },
        _recording: { state: true },
        _mentionQuery: { state: true },
        _emojiOpen: { state: true },
        _mentionIndex: { state: true },
    };

    static styles = css`
        :host {
            display: flex;
            flex-direction: column;
            padding: var(--space-4) var(--space-6) var(--space-4);
            gap: var(--space-2);
            background: var(--sync-composer-host-bg, var(--glass-solid-soft, var(--glass-solid)));
            backdrop-filter: blur(8px);
            -webkit-backdrop-filter: blur(8px);
            border-top: 1px solid var(--glass-border-subtle, var(--glass-border));
        }
        @media (max-width: 767px) {
            :host { padding: var(--space-3) var(--space-4); }
        }
        .mode-bar {
            display: flex;
            align-items: center;
            gap: var(--space-2);
            font-size: var(--text-xs);
            color: var(--text-secondary);
            padding: var(--space-2) var(--space-3);
            background: var(--glass-tint-subtle, var(--glass-hover));
            border-left: 3px solid var(--accent);
            border-radius: var(--radius-md);
        }
        .mode-bar .cancel {
            background: transparent;
            border: none;
            color: var(--text-secondary);
            cursor: pointer;
            margin-left: auto;
            padding: 4px;
            border-radius: var(--radius-sm);
            display: inline-flex;
            align-items: center;
            justify-content: center;
        }
        .mode-bar .cancel:hover { background: var(--glass-hover); color: var(--text-primary); }
        .pill {
            display: flex;
            align-items: center;
            gap: var(--space-1);
            padding: 6px 8px;
            background: var(--sync-composer-capsule-bg, var(--glass-tint-subtle, var(--glass-hover)));
            border: 1px solid var(--sync-composer-capsule-border, var(--glass-border-subtle, var(--glass-border)));
            border-radius: 24px;
            box-shadow: var(--sync-composer-capsule-shadow, none);
            transition: border-color var(--duration-fast), box-shadow var(--duration-fast);
        }
        .pill:focus-within {
            border-color: var(--accent);
            box-shadow: 0 0 0 4px var(--accent-subtle, rgba(153, 166, 249, 0.16)), var(--sync-composer-capsule-shadow, none);
        }
        /* Высота textarea подгоняется под одну строку (24px) и совпадает с
           высотой иконок 40px (height = 24 + 16 padding = 40). При вводе
           _autoResize() выставляет height по scrollHeight в пределах 3 строк
           (~88px). Дальше включается overflow-y. */
        textarea {
            flex: 1;
            min-width: 0;
            height: 24px;
            min-height: 24px;
            max-height: 88px;
            padding: 8px var(--space-2);
            margin: 0;
            border: none;
            background: transparent;
            color: var(--text-primary);
            font: inherit;
            font-size: var(--text-base, 15px);
            line-height: 1.4;
            resize: none;
            outline: none;
            overflow-y: hidden;
        }
        textarea::placeholder { color: var(--text-tertiary); }
        button.icon {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 10px;
            border-radius: var(--radius-full, 999px);
            background: transparent;
            color: var(--text-tertiary);
            border: none;
            cursor: pointer;
            transition: background var(--duration-fast), color var(--duration-fast);
            flex-shrink: 0;
        }
        button.icon:hover { background: var(--glass-hover); color: var(--accent); }
        button.icon.recording { color: var(--color-error, #ef4444); }
        button.send {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 12px;
            background: var(--accent);
            color: var(--text-inverse, #fff);
            border: none;
            border-radius: var(--radius-full, 999px);
            cursor: pointer;
            box-shadow: 0 2px 8px var(--accent-subtle, rgba(153, 166, 249, 0.32));
            transition: transform var(--duration-fast), box-shadow var(--duration-fast);
            flex-shrink: 0;
        }
        button.send:hover { transform: translateY(-1px); background: var(--accent-hover, var(--accent)); }
        button.send:active { transform: translateY(0); }
        button.send:disabled, button.icon:disabled { opacity: 0.5; cursor: not-allowed; transform: none; box-shadow: none; }
        button.send.recording {
            background: var(--color-error, #ef4444);
            box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.6);
            animation: rec-pulse 1.4s ease-in-out infinite;
        }
        @keyframes rec-pulse {
            0%   { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.55); }
            70%  { box-shadow: 0 0 0 10px rgba(239, 68, 68, 0); }
            100% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0); }
        }
        .attachments {
            display: flex;
            flex-wrap: wrap;
            gap: var(--space-1);
        }
        .att {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            background: var(--glass-tint-subtle, var(--glass-hover));
            padding: 4px 10px;
            border-radius: var(--radius-full, 999px);
            font-size: var(--text-xs);
            color: var(--text-secondary);
            cursor: pointer;
        }
        .voice-draft {
            display: flex;
            align-items: center;
            gap: var(--space-2);
            width: 100%;
            flex-basis: 100%;
            min-width: 0;
            padding: var(--space-2) var(--space-3);
            border-radius: var(--radius-lg);
            border: 1px solid var(--glass-border-subtle, var(--glass-border));
            background: var(--glass-tint-subtle, var(--glass-hover));
            box-sizing: border-box;
        }
        .voice-draft-mic {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
            width: 36px;
            height: 36px;
            border-radius: var(--radius-full, 999px);
            background: var(--accent-subtle, rgba(153, 166, 249, 0.2));
            color: var(--accent);
        }
        .voice-draft-waves {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 3px;
            flex: 1;
            min-width: 0;
            height: 32px;
        }
        .voice-draft-waves span {
            display: block;
            width: 3px;
            border-radius: 2px;
            background: var(--accent);
            opacity: 0.8;
            flex-shrink: 0;
        }
        .voice-draft-meta {
            display: flex;
            flex-direction: column;
            align-items: flex-end;
            gap: 2px;
            flex-shrink: 0;
        }
        .voice-draft-time {
            font-size: var(--text-xs);
            font-variant-numeric: tabular-nums;
            color: var(--text-secondary);
        }
        .voice-draft-remove {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 6px;
            margin: -4px -4px -4px 0;
            border: none;
            border-radius: var(--radius-full, 999px);
            background: transparent;
            color: var(--text-tertiary);
            cursor: pointer;
        }
        .voice-draft-remove:hover {
            background: var(--glass-hover);
            color: var(--text-primary);
        }
        .mention-popup {
            position: absolute;
            bottom: 100%;
            left: var(--space-6);
            background: var(--glass-solid);
            border: 1px solid var(--glass-border);
            border-radius: var(--radius-lg);
            min-width: 220px;
            max-height: 240px;
            overflow-y: auto;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.16);
            z-index: 10;
        }
        .mention-popup .item {
            padding: var(--space-2) var(--space-3);
            cursor: pointer;
        }
        .mention-popup .item:hover, .mention-popup .item.active { background: var(--glass-hover); }
        .emoji-anchor {
            position: relative;
            display: inline-flex;
            align-items: center;
            flex-shrink: 0;
        }
        .emoji-popup {
            position: absolute;
            right: 0;
            bottom: 100%;
            margin-bottom: 8px;
            background: var(--glass-solid-strong);
            border: 1px solid var(--glass-border);
            border-radius: var(--radius-lg);
            min-width: 240px;
            padding: var(--space-2);
            display: grid;
            grid-template-columns: repeat(6, 1fr);
            gap: 4px;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.16);
            z-index: 10;
            box-sizing: border-box;
            max-width: calc(100dvw - var(--platform-safe-left) - var(--platform-safe-right) - 16px);
        }
        .warn { color: var(--color-error, #ef4444); font-size: var(--text-xs); padding: 0 var(--space-3); }
    `;

    constructor() {
        super();
        this.channelId = '';
        this.threadId = '';
        this._draft = '';
        this._attachments = [];
        this._recording = false;
        this._mentionQuery = null;
        this._mediaRecorder = null;
        this._recordedChunks = [];
        this._recordStartedAt = null;
        this._typingTimer = null;
        this._emojiOpen = false;
        this._mentionIndex = 0;
        this._sendOp = this.useOp('sync/messages_send');
        this._editOp = this.useOp('sync/messages_edit');
        this._upload = this.useOp('sync/file_upload');
        this._typing = this.useOp('sync/channel_typing');
        this._members = this.useResource('sync/company_members', { autoload: true });
        this._store = this.useSlice('sync/messages_store');
        this._messagesStoreSel = this.select((s) => s.syncMessagesStore);
        this._authSel = this.select((s) => s.auth && s.auth.user);
        this.useEvent('sync/messages_store/reply_mode_set', (event) => this._onReplyMode(event));
        this.useEvent('sync/messages_store/edit_mode_set', (event) => this._onEditMode(event));
        this.useEvent('sync/messages_store/optimistic_resend_requested', (event) => this._onResendRequested(event));
    }

    async _onResendRequested(event) {
        const p = event && event.payload;
        if (!p || typeof p.channelId !== 'string' || typeof p.localId !== 'string') return;
        if (p.channelId !== this.channelId) return;
        const slice = this._messagesStoreSel.value;
        const channelData = slice && slice.byChannelId && slice.byChannelId[p.channelId];
        if (!channelData || typeof channelData.pendingByLocalId !== 'object') return;
        const pending = channelData.pendingByLocalId[p.localId];
        if (!pending || !Array.isArray(pending.contents)) return;
        const body = { contents: pending.contents, local_id: p.localId };
        if (typeof pending.thread_id === 'string') body.thread_id = pending.thread_id;
        if (typeof pending.parent_message_id === 'string') body.parent_message_id = pending.parent_message_id;
        try {
            await this._sendOp.run({ channel_id: p.channelId, body });
        } catch (err) {
            const errorMessage = err && typeof err.message === 'string' && err.message !== ''
                ? err.message
                : this.t('composer.send_failed_default');
            this._store.failOptimistic({
                channelId: p.channelId,
                localId: p.localId,
                message: errorMessage,
            });
        }
    }

    _onReplyMode(event) {
        const messageId = event && event.payload && event.payload.messageId;
        this.requestUpdate();
        if (typeof messageId === 'string' && messageId !== '') {
            this._focusTextarea({ selectAll: false });
        }
    }

    _onEditMode(event) {
        const messageId = event && event.payload && event.payload.messageId;
        if (typeof messageId !== 'string' || messageId === '') {
            this.requestUpdate();
            return;
        }
        const slice = this._messagesStoreSel.value;
        const channelData = slice && slice.byChannelId && slice.byChannelId[this.channelId];
        if (!channelData || !Array.isArray(channelData.items)) return;
        const message = channelData.items.find((m) => m.message_id === messageId);
        if (!message || !Array.isArray(message.contents)) return;
        const textBlock = message.contents.find((c) => c.type === 'text/plain');
        const data = textBlock && textBlock.data;
        const draft = data && typeof data.body === 'string'
            ? data.body
            : (data && typeof data.text === 'string' ? data.text : '');
        this._draft = draft;
        this.requestUpdate();
        this._focusTextarea({ selectAll: true });
    }

    _focusTextarea({ selectAll }) {
        this.updateComplete.then(() => {
            const ta = this.renderRoot && this.renderRoot.querySelector('textarea');
            if (!ta) return;
            this._autoResize(ta);
            ta.focus();
            if (selectAll) {
                const len = typeof ta.value === 'string' ? ta.value.length : 0;
                if (len > 0) ta.setSelectionRange(len, len);
            } else {
                const len = typeof ta.value === 'string' ? ta.value.length : 0;
                ta.setSelectionRange(len, len);
            }
        });
    }

    _autoResize(ta) {
        if (!ta) return;
        ta.style.height = 'auto';
        const max = parseFloat(getComputedStyle(ta).maxHeight) || 88;
        const next = Math.min(ta.scrollHeight, max);
        ta.style.height = `${next}px`;
        ta.style.overflowY = ta.scrollHeight > max ? 'auto' : 'hidden';
    }

    _onInput(e) {
        const text = e.target.value;
        this._draft = text;
        this._autoResize(e.target);
        this._maybeNotifyTyping();
        this._maybeMentionPopup(text, e.target);
    }

    _maybeNotifyTyping() {
        if (this._typingTimer) return;
        if (!this.channelId) return;
        this._typing.run({ channel_id: this.channelId, typing: true });
        this._typingTimer = setTimeout(() => { this._typingTimer = null; }, TYPING_DEBOUNCE_MS);
    }

    _maybeMentionPopup(text, textarea) {
        const cursor = textarea.selectionStart;
        const before = text.slice(0, cursor);
        const lastAt = before.lastIndexOf('@');
        if (lastAt < 0) {
            this._mentionQuery = null;
            return;
        }
        const query = before.slice(lastAt + 1);
        if (query.includes(' ') || query.includes('\n')) {
            this._mentionQuery = null;
            return;
        }
        this._mentionQuery = { query, atPos: lastAt };
    }

    _filteredMembers() {
        if (!this._mentionQuery) return [];
        const q = this._mentionQuery.query.toLowerCase();
        return this._members.items
            .filter((m) => resolveDisplayName(m).toLowerCase().includes(q))
            .slice(0, 8);
    }

    _onKeyDown(e) {
        const suggestions = this._filteredMembers();
        if (suggestions.length > 0) {
            if (e.key === 'ArrowDown') { e.preventDefault(); this._mentionIndex = (this._mentionIndex + 1) % suggestions.length; return; }
            if (e.key === 'ArrowUp')   { e.preventDefault(); this._mentionIndex = (this._mentionIndex - 1 + suggestions.length) % suggestions.length; return; }
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                const idx = Math.max(0, Math.min(this._mentionIndex, suggestions.length - 1));
                this._insertMention(suggestions[idx]);
                return;
            }
            if (e.key === 'Escape') { this._mentionQuery = null; return; }
        }
        if (e.key === 'Escape') {
            if (this._emojiOpen) { this._emojiOpen = false; return; }
            this._cancelMode();
            return;
        }
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            this._send();
        }
    }

    _onInsertEmoji(emoji) {
        this._draft = this._draft + emoji;
        this._emojiOpen = false;
    }

    _insertMention(member) {
        if (!this._mentionQuery) return;
        const before = this._draft.slice(0, this._mentionQuery.atPos);
        const after = this._draft.slice(this._mentionQuery.atPos + 1 + this._mentionQuery.query.length);
        const insert = `@${member.user_id} `;
        this._draft = `${before}${insert}${after}`;
        this._mentionQuery = null;
    }

    async _onPickFiles(e) {
        const fileList = e.target.files;
        const files = fileList ? Array.from(fileList) : [];
        for (const file of files) {
            await this._uploadFile(file);
        }
        e.target.value = '';
    }

    async _onPaste(e) {
        const itemList = e.clipboardData ? e.clipboardData.items : null;
        const items = itemList ? Array.from(itemList) : [];
        for (const item of items) {
            if (item.kind === 'file') {
                const file = item.getAsFile();
                if (file) await this._uploadFile(file);
            }
        }
    }

    async _onDrop(e) {
        e.preventDefault();
        const fileList = e.dataTransfer ? e.dataTransfer.files : null;
        const files = fileList ? Array.from(fileList) : [];
        for (const file of files) {
            await this._uploadFile(file);
        }
    }

    async _uploadFile(file, opts) {
        await this._upload.run({ file });
        const result = this._upload.lastResult;
        if (!result || typeof result.file_id !== 'string' || result.file_id === '') return;
        const meta = typeof opts === 'object' && opts !== null ? opts : null;
        const voiceMessage = meta !== null && meta.voiceMessage === true;
        let recordDurationMs = null;
        if (meta !== null && typeof meta.durationMsApprox === 'number' && meta.durationMsApprox > 0) {
            recordDurationMs = meta.durationMsApprox;
        }
        const mimeType = (typeof result.mime_type === 'string' && result.mime_type !== '')
            ? result.mime_type
            : (typeof result.mime === 'string' && result.mime !== '' ? result.mime : file.type);
        const filename = (typeof result.filename === 'string' && result.filename !== '')
            ? result.filename
            : (typeof result.original_name === 'string' && result.original_name !== '' ? result.original_name : file.name);
        const size = typeof result.size === 'number' ? result.size : file.size;
        const entry = { file_id: result.file_id, filename, mime_type: mimeType, size };
        if (typeof result.duration_ms === 'number') {
            entry.duration_ms = result.duration_ms;
        } else if (recordDurationMs !== null) {
            entry.duration_ms = recordDurationMs;
        }
        if (typeof result.url === 'string' && result.url !== '') entry.url = result.url;
        if (voiceMessage) entry.voiceMessage = true;
        this._attachments = [...this._attachments, entry];
    }

    _removeAttachment(idx) {
        this._attachments = this._attachments.filter((_, i) => i !== idx);
    }

    async _toggleRecording() {
        if (this._recording) {
            if (this._mediaRecorder) this._mediaRecorder.stop();
            return;
        }
        if (!hasGetUserMediaApi()) {
            this.toast('composer.voice_insecure_context', { type: 'error' });
            return;
        }
        if (typeof window.MediaRecorder === 'undefined') {
            this.toast('composer.voice_unsupported', { type: 'error' });
            return;
        }
        let stream;
        try {
            stream = await getUserMediaCompat({ audio: true });
        } catch (err) {
            const code = err && typeof err.name === 'string' ? err.name : '';
            const i18nKey = code === 'NotAllowedError' || code === 'SecurityError'
                ? 'composer.voice_permission_denied'
                : (code === 'NotFoundError' ? 'composer.voice_no_microphone' : 'composer.voice_failed');
            this.toast(i18nKey, { type: 'error' });
            return;
        }
        const chosen = pickVoiceMimeType() || 'audio/webm';
        const recorder = chosen ? new MediaRecorder(stream, { mimeType: chosen }) : new MediaRecorder(stream);
        this._recordedChunks = [];
        this._mediaRecorder = recorder;
        recorder.ondataavailable = (ev) => { if (ev.data.size > 0) this._recordedChunks.push(ev.data); };
        recorder.onstop = async () => {
            const endedAt = Date.now();
            const startedAt = typeof this._recordStartedAt === 'number' ? this._recordStartedAt : endedAt;
            this._recordStartedAt = null;
            const durationMsApprox = Math.max(0, endedAt - startedAt);
            stream.getTracks().forEach((t) => t.stop());
            this._recording = false;
            const blob = new Blob(this._recordedChunks, { type: chosen });
            const ext = chosen.includes('mp4') ? 'm4a' : 'webm';
            const file = new File([blob], `voice-${Date.now()}.${ext}`, { type: blob.type });
            await this._uploadFile(file, { voiceMessage: true, durationMsApprox });
        };
        this._recordStartedAt = Date.now();
        recorder.start();
        this._recording = true;
    }

    _replyMessage() {
        const slice = this._messagesStoreSel.value;
        const replyId = slice && slice.replyToMessageId;
        if (typeof replyId !== 'string' || replyId === '') return null;
        const channelData = slice && slice.byChannelId && slice.byChannelId[this.channelId];
        if (!channelData || !Array.isArray(channelData.items)) return null;
        const found = channelData.items.find((m) => m.message_id === replyId);
        return found ? found : null;
    }

    _editMessageId() {
        const slice = this._messagesStoreSel.value;
        if (!slice || typeof slice.editMessageId !== 'string') return null;
        return slice.editMessageId;
    }

    _cancelMode() {
        this._store.setReplyMode({ messageId: null });
        this._store.setEditMode({ messageId: null });
        this._draft = '';
        this.updateComplete.then(() => {
            const ta = this.renderRoot && this.renderRoot.querySelector('textarea');
            this._autoResize(ta);
        });
    }

    async _send() {
        const text = this._draft.trim();
        if (text.length === 0 && this._attachments.length === 0) return;
        if (text.length > SYNC_MESSAGE_TEXT_MAX_CHARS) return;
        if (!this.channelId) return;

        const editId = this._editMessageId();
        if (editId) {
            await this._editOp.run({
                channel_id: this.channelId,
                message_id: editId,
                body: { contents: [{ type: 'text/plain', data: { body: text }, order: 0 }] },
            });
            this._cancelMode();
            return;
        }

        const contents = [];
        if (text.length > 0) {
            contents.push({ type: 'text/plain', data: { body: text }, order: 0 });
        }
        for (const att of this._attachments) {
            const mt = typeof att.mime_type === 'string' ? att.mime_type : '';
            const isAudio = mt.startsWith('audio/');
            const isVideo = mt.startsWith('video/');
            const isImage = mt.startsWith('image/');
            const blockType = isAudio ? 'file/audio'
                : isVideo ? 'file/video'
                : isImage ? 'file/image'
                : 'file/document';
            const data = {
                file_id: att.file_id,
                filename: att.filename,
                mime_type: mt,
                size: att.size,
            };
            if (isAudio) {
                data.duration_ms = typeof att.duration_ms === 'number' ? att.duration_ms : 0;
            }
            if (isVideo && typeof att.duration_ms === 'number') {
                data.duration_ms = att.duration_ms;
            }
            contents.push({ type: blockType, data, order: contents.length });
        }

        const reply = this._replyMessage();
        const localId = `local_${Date.now().toString(36)}_${Math.floor(Math.random() * 0xffffff).toString(36)}`;
        const body = { contents, local_id: localId };
        if (this.threadId) body.thread_id = this.threadId;
        if (reply) body.parent_message_id = reply.message_id;

        const me = this._authSel.value;
        const optimisticItem = {
            local_id: localId,
            message_id: localId,
            channel_id: this.channelId,
            contents,
            sender: me ? { user_id: me.user_id, display_name: me.name } : null,
            sent_at: new Date().toISOString(),
            status: 'sending',
        };
        if (this.threadId) optimisticItem.thread_id = this.threadId;
        if (reply) optimisticItem.parent_message_id = reply.message_id;
        this._store.addOptimistic({
            channelId: this.channelId,
            item: optimisticItem,
        });

        try {
            await this._sendOp.run({ channel_id: this.channelId, body });
        } catch (err) {
            const errorMessage = err && typeof err.message === 'string' && err.message !== ''
                ? err.message
                : this.t('composer.send_failed_default');
            this._store.failOptimistic({
                channelId: this.channelId,
                localId,
                message: errorMessage,
            });
        }

        this._draft = '';
        this._attachments = [];
        if (reply) this._store.setReplyMode({ messageId: null });
        this.updateComplete.then(() => {
            const ta = this.renderRoot && this.renderRoot.querySelector('textarea');
            this._autoResize(ta);
        });
    }

    render() {
        const reply = this._replyMessage();
        const editing = this._editMessageId();
        const overLimit = this._draft.length > SYNC_MESSAGE_TEXT_MAX_CHARS;
        const memberSuggestions = this._filteredMembers();
        const emojis = ['👍', '❤️', '😂', '🎉', '🔥', '👏', '😮', '😢', '🙏', '🤔', '💯', '🚀', '✨', '🌟', '💡', '✅', '⚡', '🎯'];
        return html`
            ${reply ? html`
                <div class="mode-bar">
                    <span>${this.t('composer.reply_to', { name: resolveDisplayName(reply.sender) })}</span>
                    <button class="cancel" @click=${this._cancelMode} title=${this.t('composer.cancel')}>
                        <platform-icon name="close" size="14"></platform-icon>
                    </button>
                </div>
            ` : ''}
            ${editing ? html`
                <div class="mode-bar">
                    <span>${this.t('composer.editing')}</span>
                    <button class="cancel" @click=${this._cancelMode} title=${this.t('composer.cancel')}>
                        <platform-icon name="close" size="14"></platform-icon>
                    </button>
                </div>
            ` : ''}
            ${this._attachments.length > 0 ? html`
                <div class="attachments">
                    ${this._attachments.map((att, i) => {
                        const mt = typeof att.mime_type === 'string' ? att.mime_type : '';
                        const isVoiceDraft = att.voiceMessage === true && mt.startsWith('audio/');
                        if (isVoiceDraft) {
                            const dur = typeof att.duration_ms === 'number' ? att.duration_ms : 0;
                            return html`
                                <div class="voice-draft" role="group" aria-label=${this.t('composer.voice_draft_label')}>
                                    <span class="voice-draft-mic" aria-hidden="true">
                                        <platform-icon name="mic" size="18"></platform-icon>
                                    </span>
                                    <div class="voice-draft-waves" aria-hidden="true">
                                        ${VOICE_DRAFT_WAVE_HEIGHTS_PX.map((h) => html`<span style="height:${h}px"></span>`)}
                                    </div>
                                    <div class="voice-draft-meta">
                                        <span class="voice-draft-time">${formatVoiceDurationMs(dur)}</span>
                                        <button
                                            type="button"
                                            class="voice-draft-remove"
                                            title=${this.t('composer.remove_attachment')}
                                            aria-label=${this.t('composer.remove_attachment')}
                                            @click=${() => this._removeAttachment(i)}
                                        >
                                            <platform-icon name="close" size="14"></platform-icon>
                                        </button>
                                    </div>
                                </div>
                            `;
                        }
                        return html`
                            <span class="att" @click=${() => this._removeAttachment(i)}>
                                ${att.filename || att.name || ''}
                                <platform-icon name="close" size="12"></platform-icon>
                            </span>
                        `;
                    })}
                </div>
            ` : ''}
            <div class="pill" style="position: relative;" @drop=${this._onDrop} @dragover=${(e) => e.preventDefault()}>
                ${memberSuggestions.length > 0 ? html`
                    <div class="mention-popup">
                        ${memberSuggestions.map((m, i) => html`
                            <div class="item ${i === Math.max(0, Math.min(this._mentionIndex, memberSuggestions.length - 1)) ? 'active' : ''}" @click=${() => this._insertMention(m)}>${resolveDisplayName(m)}</div>
                        `)}
                    </div>
                ` : ''}
                <input type="file" accept="image/*,video/*" multiple style="display: none;" id="photopick" @change=${this._onPickFiles} />
                <input type="file" multiple style="display: none;" id="filepick" @change=${this._onPickFiles} />
                <button class="icon" title=${this.t('composer.attach_photo_video')} @click=${() => this.renderRoot.getElementById('photopick').click()}>
                    <platform-icon name="image" size="22"></platform-icon>
                </button>
                <button class="icon" title=${this.t('composer.attach_file')} @click=${() => this.renderRoot.getElementById('filepick').click()}>
                    <platform-icon name="paperclip" size="22"></platform-icon>
                </button>
                <textarea
                    rows="1"
                    .value=${this._draft}
                    @input=${this._onInput}
                    @keydown=${this._onKeyDown}
                    @paste=${this._onPaste}
                    placeholder=${this.t('composer.placeholder')}
                ></textarea>
                <span class="emoji-anchor">
                    ${this._emojiOpen ? html`
                        <div class="emoji-popup">
                            ${emojis.map((e) => html`
                                <span style="cursor: pointer; font-size: 18px; padding: 4px; text-align: center; border-radius: var(--radius-sm);" @click=${() => this._onInsertEmoji(e)}>${e}</span>
                            `)}
                        </div>
                    ` : ''}
                    <button class="icon" title=${this.t('composer.emoji_title')} @click=${() => { this._emojiOpen = !this._emojiOpen; }}>
                        <platform-icon name="smile" size="22"></platform-icon>
                    </button>
                </span>
                ${(() => {
                    const hasContent = this._draft.trim().length > 0 || this._attachments.length > 0;
                    if (this._recording) {
                        return html`<button
                            class="send recording"
                            @click=${this._toggleRecording}
                            title=${this.t('composer.action_voice_stop')}
                            aria-label=${this.t('composer.action_voice_stop')}
                        ><platform-icon name="stop" size="20"></platform-icon></button>`;
                    }
                    if (hasContent) {
                        return html`<button
                            class="send"
                            @click=${this._send}
                            ?disabled=${overLimit}
                            title=${this.t('composer.action_send')}
                            aria-label=${this.t('composer.action_send')}
                        ><platform-icon name="send" size="20"></platform-icon></button>`;
                    }
                    return html`<button
                        class="send"
                        @click=${this._toggleRecording}
                        title=${this.t('composer.action_voice')}
                        aria-label=${this.t('composer.action_voice')}
                    ><platform-icon name="mic" size="20"></platform-icon></button>`;
                })()}
            </div>
            ${overLimit ? html`<div class="warn">${this.t('composer.over_limit', { max: SYNC_MESSAGE_TEXT_MAX_CHARS })}</div>` : ''}
        `;
    }
}

customElements.define('sync-message-composer', SyncMessageComposer);
