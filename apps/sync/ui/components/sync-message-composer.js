/**
 * sync-message-composer — поле ввода с поддержкой:
 *   - reply mode (subscribe 'sync/messages/reply_mode_set')
 *   - edit mode (subscribe 'sync/messages/edit_mode_set')
 *   - file upload (drag-and-drop, paste, кнопка)
 *   - voice recording (MediaRecorder)
 *   - mention autocomplete (popup при '@')
 *   - typing notify (debounce 1500ms)
 *   - length limit SYNC_MESSAGE_TEXT_MAX_CHARS
 *
 * Все мутации — useOp('sync/messages').actions.send|edit (+ useOp('sync/file_upload')).
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';
import { SYNC_MESSAGE_TEXT_MAX_CHARS } from './_helpers/sync-limits.js';
import { resolveDisplayName } from '../_helpers/sync-id-resolvers.js';

const TYPING_DEBOUNCE_MS = 1500;

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
            border-top: 1px solid var(--glass-border);
            padding: var(--space-2) var(--space-3);
            gap: var(--space-1);
            background: var(--glass-solid);
        }
        .mode-bar {
            display: flex;
            align-items: center;
            gap: var(--space-2);
            font-size: var(--text-xs);
            color: var(--text-secondary);
            padding: var(--space-1) var(--space-2);
            background: var(--glass-hover);
            border-radius: var(--radius-sm);
        }
        .mode-bar .cancel {
            background: transparent;
            border: none;
            color: var(--text-primary);
            cursor: pointer;
            margin-left: auto;
        }
        .row {
            display: flex;
            gap: var(--space-2);
            align-items: flex-end;
        }
        textarea {
            flex: 1;
            min-height: 36px;
            max-height: 200px;
            padding: var(--space-2);
            border-radius: var(--radius-md);
            border: 1px solid var(--glass-border);
            background: var(--glass-solid);
            color: var(--text-primary);
            font: inherit;
            font-size: var(--text-sm);
            resize: vertical;
            outline: none;
        }
        button {
            padding: var(--space-2);
            border-radius: var(--radius-md);
            background: transparent;
            color: var(--text-primary);
            border: 1px solid var(--glass-border);
            cursor: pointer;
        }
        button.send {
            background: var(--accent);
            color: white;
            border-color: transparent;
            padding: var(--space-2) var(--space-4);
        }
        button:disabled { opacity: 0.5; cursor: not-allowed; }
        .attachments {
            display: flex;
            flex-wrap: wrap;
            gap: var(--space-1);
        }
        .att {
            background: var(--glass-hover);
            padding: 2px 6px;
            border-radius: var(--radius-sm);
            font-size: var(--text-xs);
        }
        .mention-popup {
            position: absolute;
            bottom: 100%;
            left: var(--space-3);
            background: var(--glass-solid);
            border: 1px solid var(--glass-border);
            border-radius: var(--radius-md);
            min-width: 180px;
            max-height: 200px;
            overflow-y: auto;
            z-index: 10;
        }
        .mention-popup .item {
            padding: var(--space-2);
            cursor: pointer;
        }
        .mention-popup .item:hover { background: var(--glass-hover); }
        .warn { color: var(--color-danger, #ff6b6b); font-size: var(--text-xs); }
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
        this._typingTimer = null;
        this._emojiOpen = false;
        this._mentionIndex = 0;
        this._messages = this.useOp('sync/messages');
        this._upload = this.useOp('sync/file_upload');
        this._typing = this.useOp('sync/channel_typing');
        this._members = this.useResource('sync/company_members', { autoload: true });
        this._messagesSel = this.select((s) => s.syncMessages);
        this._authSel = this.select((s) => s.auth && s.auth.user);
        this.useEvent('sync/messages/reply_mode_set', () => this.requestUpdate());
        this.useEvent('sync/messages/edit_mode_set', (event) => this._onEditMode(event));
    }

    _onEditMode(event) {
        const messageId = event && event.payload && event.payload.messageId;
        if (typeof messageId !== 'string') return;
        const slice = this._messagesSel.value;
        const channelData = slice && slice.byChannelId && slice.byChannelId[this.channelId];
        if (!channelData || !Array.isArray(channelData.items)) return;
        const message = channelData.items.find((m) => m.message_id === messageId);
        if (!message || !Array.isArray(message.contents)) return;
        const textBlock = message.contents.find((c) => c.type === 'text/plain');
        const draft = (textBlock && textBlock.data && typeof textBlock.data.text === 'string')
            ? textBlock.data.text
            : '';
        this._draft = draft;
        this.requestUpdate();
    }

    _onInput(e) {
        const text = e.target.value;
        this._draft = text;
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

    async _uploadFile(file) {
        await this._upload.run({ file });
        const result = this._upload.lastResult;
        if (!result || typeof result.file_id !== 'string' || result.file_id === '') return;
        let mime = file.type;
        if (typeof result.mime === 'string' && result.mime !== '') mime = result.mime;
        let name = file.name;
        if (typeof result.original_name === 'string' && result.original_name !== '') name = result.original_name;
        const entry = { file_id: result.file_id, mime, name };
        if (typeof result.url === 'string' && result.url !== '') entry.url = result.url;
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
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const mimeOptions = ['audio/mp4', 'audio/webm;codecs=opus', 'audio/webm'];
        const supported = mimeOptions.find((mt) => MediaRecorder.isTypeSupported(mt));
        const chosen = typeof supported === 'string' ? supported : 'audio/webm';
        const recorder = supported ? new MediaRecorder(stream, { mimeType: chosen }) : new MediaRecorder(stream);
        this._recordedChunks = [];
        this._mediaRecorder = recorder;
        recorder.ondataavailable = (ev) => { if (ev.data.size > 0) this._recordedChunks.push(ev.data); };
        recorder.onstop = async () => {
            stream.getTracks().forEach((t) => t.stop());
            this._recording = false;
            const blob = new Blob(this._recordedChunks, { type: chosen });
            const ext = chosen.includes('mp4') ? 'm4a' : 'webm';
            const file = new File([blob], `voice-${Date.now()}.${ext}`, { type: blob.type });
            await this._uploadFile(file);
        };
        recorder.start();
        this._recording = true;
    }

    _replyMessage() {
        const slice = this._messagesSel.value;
        const replyId = slice && slice.replyToMessageId;
        if (typeof replyId !== 'string' || replyId === '') return null;
        const channelData = slice && slice.byChannelId && slice.byChannelId[this.channelId];
        if (!channelData || !Array.isArray(channelData.items)) return null;
        const found = channelData.items.find((m) => m.message_id === replyId);
        return found ? found : null;
    }

    _editMessageId() {
        const slice = this._messagesSel.value;
        if (!slice || typeof slice.editMessageId !== 'string') return null;
        return slice.editMessageId;
    }

    _cancelMode() {
        this.dispatch('sync/messages/reply_mode_set', { messageId: null });
        this.dispatch('sync/messages/edit_mode_set', { messageId: null });
        this._draft = '';
    }

    async _send() {
        const text = this._draft.trim();
        if (text.length === 0 && this._attachments.length === 0) return;
        if (text.length > SYNC_MESSAGE_TEXT_MAX_CHARS) return;
        if (!this.channelId) return;

        const editId = this._editMessageId();
        if (editId) {
            this._messages.actions.edit({
                channel_id: this.channelId,
                message_id: editId,
                body: { contents: [{ type: 'text/plain', data: { text } }] },
            });
            this._cancelMode();
            return;
        }

        const contents = [];
        if (text.length > 0) contents.push({ type: 'text/plain', data: { text } });
        for (const att of this._attachments) {
            const baseType = att.mime && att.mime.startsWith('audio/') ? 'file/audio'
                : att.mime && att.mime.startsWith('video/') ? 'file/video'
                : 'file/attachment';
            contents.push({
                type: baseType,
                data: { file_id: att.file_id, mime: att.mime, original_name: att.name, url: att.url },
            });
        }

        const reply = this._replyMessage();
        const localId = `local_${Date.now().toString(36)}_${Math.floor(Math.random() * 0xffffff).toString(36)}`;
        const body = { contents, local_id: localId };
        if (this.threadId) body.thread_id = this.threadId;
        if (reply) body.parent_message_id = reply.message_id;

        const me = this._authSel.value;
        this.dispatch('sync/messages/optimistic_added', {
            channelId: this.channelId,
            item: {
                local_id: localId,
                message_id: localId,
                channel_id: this.channelId,
                contents,
                sender: me ? { user_id: me.user_id, display_name: me.name } : null,
                sent_at: new Date().toISOString(),
                status: 'sending',
            },
        });

        try {
            await this._messages.actions.send({ channel_id: this.channelId, body });
        } catch (err) {
            const errorMessage = err && typeof err.message === 'string' && err.message !== ''
                ? err.message
                : this.t('composer.send_failed_default');
            this.dispatch('sync/messages/optimistic_failed', {
                channelId: this.channelId,
                localId,
                message: errorMessage,
            });
        }

        this._draft = '';
        this._attachments = [];
        if (reply) this.dispatch('sync/messages/reply_mode_set', { messageId: null });
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
                    <button class="cancel" @click=${this._cancelMode}>${this.t('composer.cancel')}</button>
                </div>
            ` : ''}
            ${editing ? html`
                <div class="mode-bar">
                    <span>${this.t('composer.editing')}</span>
                    <button class="cancel" @click=${this._cancelMode}>${this.t('composer.cancel')}</button>
                </div>
            ` : ''}
            ${this._attachments.length > 0 ? html`
                <div class="attachments">
                    ${this._attachments.map((att, i) => html`
                        <span class="att" @click=${() => this._removeAttachment(i)}>
                            ${att.name} ✕
                        </span>
                    `)}
                </div>
            ` : ''}
            <div class="row" style="position: relative;" @drop=${this._onDrop} @dragover=${(e) => e.preventDefault()}>
                ${memberSuggestions.length > 0 ? html`
                    <div class="mention-popup">
                        ${memberSuggestions.map((m, i) => html`
                            <div class="item" style=${i === Math.max(0, Math.min(this._mentionIndex, memberSuggestions.length - 1)) ? 'background: var(--glass-hover);' : ''} @click=${() => this._insertMention(m)}>${resolveDisplayName(m)}</div>
                        `)}
                    </div>
                ` : ''}
                ${this._emojiOpen ? html`
                    <div class="mention-popup" style="bottom: 100%; left: 80px; min-width: 240px; padding: var(--space-2); display: grid; grid-template-columns: repeat(6, 1fr); gap: 4px;">
                        ${emojis.map((e) => html`
                            <span style="cursor: pointer; font-size: 18px; padding: 4px; text-align: center; border-radius: var(--radius-sm);" @click=${() => this._onInsertEmoji(e)}>${e}</span>
                        `)}
                    </div>
                ` : ''}
                <input type="file" accept="image/*,video/*" multiple style="display: none;" id="photopick" @change=${this._onPickFiles} />
                <input type="file" multiple style="display: none;" id="filepick" @change=${this._onPickFiles} />
                <button title=${this.t('composer.attach_photo_video')} @click=${() => this.renderRoot.getElementById('photopick').click()}>
                    <platform-icon name="image" size="18"></platform-icon>
                </button>
                <button title=${this.t('composer.attach_file')} @click=${() => this.renderRoot.getElementById('filepick').click()}>
                    <platform-icon name="paperclip" size="18"></platform-icon>
                </button>
                <button title=${this.t('composer.emoji_title')} @click=${() => { this._emojiOpen = !this._emojiOpen; }}>
                    <platform-icon name="smile" size="18"></platform-icon>
                </button>
                <button title=${this.t('composer.action_voice')} @click=${this._toggleRecording}>
                    <platform-icon name=${this._recording ? 'square' : 'mic'} size="18"></platform-icon>
                </button>
                <textarea
                    .value=${this._draft}
                    @input=${this._onInput}
                    @keydown=${this._onKeyDown}
                    @paste=${this._onPaste}
                    placeholder=${this.t('composer.placeholder')}
                ></textarea>
                <button class="send" @click=${this._send} ?disabled=${overLimit || (this._draft.trim().length === 0 && this._attachments.length === 0)}>
                    ${this.t('composer.action_send')}
                </button>
            </div>
            ${overLimit ? html`<div class="warn">${this.t('composer.over_limit', { max: SYNC_MESSAGE_TEXT_MAX_CHARS })}</div>` : ''}
        `;
    }
}

customElements.define('sync-message-composer', SyncMessageComposer);
