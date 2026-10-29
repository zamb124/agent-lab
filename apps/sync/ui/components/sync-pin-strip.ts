/**
 * sync-pin-strip — горизонтальная полоска закреплённых сообщений канала.
 *
 * Источник message_id: useResource('sync/channels') as ControllerFor<'sync/channels'>.items.find(...).pinned_message_ids.
 * Превью текста: сообщение из slice `sync/messages_store.byChannelId[channelId].items`,
 * иначе подпись по умолчанию.
 * Индекс навигации: useSlice('sync/chat_ui').pinnedNavigateIndex.
 *
 * Клик циклически листает закрепы; emit('jump-to-message', { messageId })
 * для родителя (sync-channel-page).
 */

import type { ResourceController, ControllerFor } from '@platform/lib/base/use-resource.js';
import { html, css } from 'lit';
import type {CSSResultGroup, PropertyDeclarations, TemplateResult} from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';

function pinnedIds(channel: Record<string, unknown> | undefined): string[] {
    if (!channel) return [];
    const pinned = channel.pinned_message_ids;
    if (!Array.isArray(pinned)) return [];
    const ids: string[] = [];
    for (const id of pinned) {
        if (typeof id === 'string' && id !== '') ids.push(id);
    }
    return ids;
}

function _textPreviewFromMessage(m: Record<string, any> | null | undefined) {
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
    static override properties: PropertyDeclarations = {
        channelId: { type: String },
    };
    declare channelId: string;

    static override styles: CSSResultGroup = css`
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
    private _channels: ControllerFor<'sync/channels'>;
    private _messagesStore: ControllerFor<'sync/messages_store'>;
    private _chatUi: ControllerFor<'sync/chat_ui'>;

    constructor() {
        super();
        this.channelId = '';
        this._channels = this.useResource('sync/channels');
        this._messagesStore = this.useSlice('sync/messages_store');
        this._chatUi = this.useSlice('sync/chat_ui');
    }

    _channel() {
        return this._channels.items.find((c: Record<string, unknown>) => c.channel_id === this.channelId);
    }

    _messageById(messageId: unknown) {
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
        const ids = pinnedIds(channel);
        if (!channel || ids.length === 0) return;
        const idx = (typeof this._chatUi.value?.pinnedNavigateIndex === 'number'
            ? this._chatUi.value.pinnedNavigateIndex
            : 0);
        const next = (idx + 1) % ids.length;
        const messageId = ids[next];
        this._chatUi.setPinnedIndex({ index: next });
        if (typeof messageId === 'string' && messageId !== '') {
            this.emit('jump-to-message', { messageId });
        }
    }

    override render(): TemplateResult {
        const channel = this._channel();
        if (!channel) return html``;
        const ids = pinnedIds(channel);
        if (ids.length === 0) return html``;
        const idx = typeof this._chatUi.value?.pinnedNavigateIndex === 'number'
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
