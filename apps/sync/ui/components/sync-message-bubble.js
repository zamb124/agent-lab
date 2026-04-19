/**
 * sync-message-bubble — пузырь одного сообщения.
 *
 * Поддерживает content-типы:
 *   - text/plain         — текст с упоминаниями (mentions) и edit-маркером
 *   - file/audio         — аудио-плеер + transcript + кнопка "Transcribe"
 *   - file/video         — видео-плеер + кнопка "Transcribe"
 *   - file/* (image/etc) — превью / иконка + download-link
 *   - call/boundary      — компактный пузырёк границы звонка (start/ended)
 *
 * Действия — через bus:
 *   - long-press / right-click → 'sync/messages/context_menu_requested'
 *   - клик по реакции → useOp 'sync/messages' .actions.react
 *   - кнопка "Войти" на call/boundary started → диспатч accept_requested
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-user-chip.js';

const FILE_DOWNLOAD_BASE = '/sync/api/v1/files/download';

export class SyncMessageBubble extends PlatformElement {
    static properties = {
        message: { type: Object },
        myUserId: { type: String, attribute: 'my-user-id' },
        channelType: { type: String, attribute: 'channel-type' },
    };

    static styles = css`
        :host {
            display: block;
            margin-bottom: var(--space-2);
        }
        .row {
            display: flex;
            gap: var(--space-2);
            align-items: flex-start;
        }
        :host([data-own]) .row { justify-content: flex-end; }
        .bubble {
            background: var(--glass-solid);
            border: 1px solid var(--glass-border);
            border-radius: var(--radius-md);
            padding: var(--space-2) var(--space-3);
            max-width: 70%;
            min-width: 0;
            position: relative;
        }
        :host([data-own]) .bubble {
            background: var(--accent);
            color: white;
            border-color: transparent;
        }
        .sender {
            font-size: var(--text-xs);
            font-weight: 600;
            margin-bottom: var(--space-1);
            color: var(--text-secondary);
        }
        :host([data-own]) .sender { display: none; }
        .body {
            white-space: pre-wrap;
            word-break: break-word;
            overflow-wrap: anywhere;
            font-size: var(--text-sm);
        }
        .meta {
            display: flex;
            align-items: center;
            gap: var(--space-1);
            justify-content: flex-end;
            font-size: var(--text-xs);
            color: var(--text-secondary);
            margin-top: var(--space-1);
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
            border-radius: var(--radius-sm);
            background: var(--glass-hover);
            color: var(--text-primary);
            cursor: pointer;
            font-size: var(--text-xs);
        }
        .reaction.mine { outline: 1px solid var(--accent); }
        .file {
            display: flex;
            align-items: center;
            gap: var(--space-2);
            padding: var(--space-2);
            background: var(--glass-hover);
            border-radius: var(--radius-sm);
        }
        .call-boundary {
            text-align: center;
            font-size: var(--text-xs);
            color: var(--text-secondary);
            padding: var(--space-2);
            border-top: 1px dashed var(--glass-border);
            border-bottom: 1px dashed var(--glass-border);
        }
        .call-join-btn {
            margin-left: var(--space-2);
            padding: 2px 8px;
            background: var(--accent);
            color: white;
            border: none;
            border-radius: var(--radius-sm);
            cursor: pointer;
        }
        button.transcribe {
            background: transparent;
            border: 1px solid var(--glass-border);
            color: var(--text-primary);
            padding: 2px 8px;
            border-radius: var(--radius-sm);
            cursor: pointer;
            font-size: var(--text-xs);
        }
    `;

    constructor() {
        super();
        this.message = null;
        this.myUserId = '';
        this.channelType = '';
        this._messages = this.useOp('sync/messages');
        this._callAccept = this.useOp('sync/calls_accept');
    }

    updated(changed) {
        super.updated?.(changed);
        if (changed.has('message') || changed.has('myUserId')) {
            const own = this.message && this.message.sender && this.message.sender.user_id === this.myUserId;
            this.toggleAttribute('data-own', Boolean(own));
        }
    }

    _onContextMenu(e) {
        e.preventDefault();
        const messageId = this.message && this.message.message_id;
        if (typeof messageId !== 'string') return;
        const x = typeof e.clientX === 'number' ? e.clientX : 0;
        const y = typeof e.clientY === 'number' ? e.clientY : 0;
        this._messages.actions.showContextMenu({ messageId, x, y });
    }

    _onReaction(emoji) {
        if (!this.message) return;
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

    _onJoinCall(callId) {
        if (typeof callId !== 'string' || callId === '') return;
        this._callAccept.run({ call_id: callId });
    }

    _renderText(content) {
        const text = content && content.data && content.data.text;
        if (typeof text !== 'string') return '';
        return html`<div class="body">${text}</div>`;
    }

    _renderAudio(content) {
        const fileId = content && content.data && content.data.file_id;
        if (typeof fileId !== 'string') return '';
        const url = `${FILE_DOWNLOAD_BASE}/${encodeURIComponent(fileId)}`;
        const status = content && content.data && content.data.transcription_status;
        const transcript = content && content.data && content.data.transcript;
        return html`
            <div class="file">
                <audio controls src=${url} style="max-width: 240px;"></audio>
                ${status === 'done' && transcript ? html`<div class="body">${transcript}</div>` : ''}
                ${status !== 'done' && status !== 'processing' ? html`
                    <button class="transcribe" @click=${this._onTranscribeAudio}>${this.t('message_bubble.action_transcribe')}</button>
                ` : ''}
                ${status === 'processing' ? html`<span class="meta">${this.t('message_bubble.transcribe_processing')}</span>` : ''}
            </div>
        `;
    }

    _renderVideo(content) {
        const fileId = content && content.data && content.data.file_id;
        if (typeof fileId !== 'string') return '';
        const url = `${FILE_DOWNLOAD_BASE}/${encodeURIComponent(fileId)}`;
        const status = content && content.data && content.data.transcription_status;
        return html`
            <div class="file" style="flex-direction: column; align-items: stretch;">
                <video controls src=${url} style="max-width: 360px; border-radius: var(--radius-sm);"></video>
                ${status !== 'done' && status !== 'processing' ? html`
                    <button class="transcribe" @click=${this._onTranscribeVideo}>${this.t('message_bubble.action_transcribe')}</button>
                ` : ''}
            </div>
        `;
    }

    _renderFile(content) {
        const data = (content && content.data && typeof content.data === 'object') ? content.data : null;
        const fileId = data ? data.file_id : null;
        if (typeof fileId !== 'string') return '';
        let name = '';
        if (data && typeof data.original_name === 'string' && data.original_name !== '') name = data.original_name;
        else if (data && typeof data.name === 'string' && data.name !== '') name = data.name;
        else name = this.t('message_bubble.attachment_default_name');
        const url = `${FILE_DOWNLOAD_BASE}/${encodeURIComponent(fileId)}`;
        return html`
            <div class="file">
                <platform-icon name="file" size="20"></platform-icon>
                <a href=${url} download=${name} style="color: inherit;">${name}</a>
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
                    ${this.t('message_bubble.call_started')}
                    <button class="call-join-btn" @click=${() => this._onJoinCall(callId)}>${this.t('message_bubble.action_join_call')}</button>
                </div>
            `;
        }
        return html`<div class="call-boundary">${this.t('message_bubble.call_ended')}</div>`;
    }

    _renderContent(content) {
        if (!content || typeof content.type !== 'string') return '';
        if (content.type === 'text/plain')   return this._renderText(content);
        if (content.type === 'file/audio')   return this._renderAudio(content);
        if (content.type === 'file/video')   return this._renderVideo(content);
        if (content.type.startsWith('file/')) return this._renderFile(content);
        if (content.type === 'call/boundary') return this._renderCallBoundary(content);
        return '';
    }

    _renderReactions() {
        const reactions = (this.message && Array.isArray(this.message.reactions))
            ? this.message.reactions
            : [];
        if (!Array.isArray(reactions) || reactions.length === 0) return '';
        return html`
            <div class="reactions">
                ${reactions.map((r) => html`
                    <span
                        class=${r.user_ids && r.user_ids.includes(this.myUserId) ? 'reaction mine' : 'reaction'}
                        @click=${() => this._onReaction(r.emoji)}
                    >${r.emoji} ${r.user_ids ? r.user_ids.length : 0}</span>
                `)}
            </div>
        `;
    }

    _renderStatus() {
        const status = this.message && this.message.status;
        if (!status) return '';
        const icon = status === 'read' ? 'check-double' : status === 'delivered' ? 'check' : 'clock';
        return html`<platform-icon name=${icon} size="12"></platform-icon>`;
    }

    _renderMeta() {
        const sentAt = this.message && this.message.sent_at;
        if (!sentAt) return this._renderStatus();
        const time = new Date(sentAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        const edited = this.message.edited_at ? html`<span>${this.t('message_bubble.edited')}</span>` : '';
        return html`<div class="meta">${edited}<span>${time}</span>${this._renderStatus()}</div>`;
    }

    render() {
        if (!this.message) return html``;
        const senderId = this.message.sender && this.message.sender.user_id;
        const isOwn = senderId === this.myUserId;
        const contents = Array.isArray(this.message.contents) ? this.message.contents : [];
        const onlyBoundary = contents.length === 1 && contents[0].type === 'call/boundary';
        if (onlyBoundary) {
            return html`<div class="row" style="justify-content: center;">${this._renderContent(contents[0])}</div>`;
        }
        return html`
            <div class="row" @contextmenu=${this._onContextMenu}>
                <div class="bubble">
                    ${!isOwn && senderId ? html`
                        <div class="sender">
                            <platform-user-chip user-id=${senderId} size="sm" ?interactive=${false}></platform-user-chip>
                        </div>
                    ` : ''}
                    ${contents.map((c) => this._renderContent(c))}
                    ${this._renderReactions()}
                    ${this._renderMeta()}
                </div>
            </div>
        `;
    }
}

customElements.define('sync-message-bubble', SyncMessageBubble);
