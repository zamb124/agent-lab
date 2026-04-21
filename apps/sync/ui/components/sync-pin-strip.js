/**
 * sync-pin-strip — горизонтальная полоска закреплённых сообщений канала.
 *
 * Источник id: useResource('sync/channels').items.find(...).pinned_message_ids.
 * Превью текста: сообщение из slice `sync/messages_store.byChannelId[channelId].items`,
 * иначе подпись по умолчанию.
 * Индекс навигации: useSlice('sync/chat_ui').pinnedNavigateIndex.
 *
 * Клик циклически листает закрепы; emit('jump-to-message', { messageId })
 * для родителя (sync-channel-page).
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';

function _textPreviewFromMessage(m) {
    if (!m || typeof m !== 'object') return '';
    const contents = Array.isArray(m.contents) ? m.contents : [];
    const block = contents.find((c) => c && c.type === 'text/plain');
    const data = block && block.data && typeof block.data === 'object' ? block.data : null;
    if (!data) return '';
    const body = typeof data.body === 'string' ? data.body : '';
    const text = typeof data.text === 'string' ? data.text : '';
    const raw = body !== '' ? body : text;
    if (typeof raw !== 'string' || raw === '') return '';
    return raw.length > 120 ? `${raw.slice(0, 120)}…` : raw;
}

export class SyncPinStrip extends PlatformElement {
    static properties = {
        channelId: { type: String },
    };

    static styles = css`
        :host {
            display: block;
            border-bottom: 1px solid var(--glass-border);
            background: var(--glass-hover);
        }
        .row {
            display: flex;
            align-items: center;
            gap: var(--space-2);
            padding: var(--space-1) var(--space-3);
            cursor: pointer;
            font-size: var(--text-xs);
            color: var(--text-secondary);
        }
        .row:hover { background: var(--glass-active, var(--glass-hover)); color: var(--text-primary); }
        .pin-icon {
            color: var(--accent);
            flex-shrink: 0;
        }
        .preview {
            flex: 1;
            min-width: 0;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            color: var(--text-primary);
        }
        .counter {
            color: var(--text-secondary);
            font-weight: 500;
        }
    `;

    constructor() {
        super();
        this.channelId = '';
        this._channels = this.useResource('sync/channels');
        this._messagesStore = this.useSlice('sync/messages_store');
        this._chatUi = this.useSlice('sync/chat_ui');
    }

    _channel() {
        return this._channels.items.find((c) => c.id === this.channelId);
    }

    _messageById(messageId) {
        const slice = this._messagesStore.value;
        if (!slice || !slice.byChannelId || typeof this.channelId !== 'string' || this.channelId === '') {
            return null;
        }
        const data = slice.byChannelId[this.channelId];
        if (!data || !Array.isArray(data.items)) return null;
        const found = data.items.find((m) => m && m.message_id === messageId);
        return found === undefined ? null : found;
    }

    _onClick() {
        const channel = this._channel();
        const ids = channel && Array.isArray(channel.pinned_message_ids)
            ? channel.pinned_message_ids.filter((id) => typeof id === 'string' && id !== '')
            : [];
        if (!channel || ids.length === 0) return;
        const idx = (typeof this._chatUi.value.pinnedNavigateIndex === 'number'
            ? this._chatUi.value.pinnedNavigateIndex
            : 0);
        const next = (idx + 1) % ids.length;
        const messageId = ids[next];
        this._chatUi.setPinnedIndex({ index: next });
        if (typeof messageId === 'string' && messageId !== '') {
            this.emit('jump-to-message', { messageId });
        }
    }

    render() {
        const channel = this._channel();
        if (!channel) return html``;
        const ids = Array.isArray(channel.pinned_message_ids)
            ? channel.pinned_message_ids.filter((id) => typeof id === 'string' && id !== '')
            : [];
        if (ids.length === 0) return html``;
        const idx = typeof this._chatUi.value.pinnedNavigateIndex === 'number'
            ? this._chatUi.value.pinnedNavigateIndex
            : 0;
        const safeIdx = ids.length > 0 ? idx % ids.length : 0;
        const curId = ids[safeIdx];
        const fromList = this._messageById(curId);
        const fromText = _textPreviewFromMessage(fromList);
        const preview = fromText !== ''
            ? fromText
            : this.t('bubble.default_message');
        return html`
            <div class="row" @click=${this._onClick} title=${this.t('chat_view.pin_strip_title')}>
                <platform-icon name="pin" size="14" class="pin-icon"></platform-icon>
                <span class="preview">${preview}</span>
                <span class="counter">${safeIdx + 1}/${ids.length}</span>
            </div>
        `;
    }
}

customElements.define('sync-pin-strip', SyncPinStrip);
