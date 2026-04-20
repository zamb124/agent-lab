/**
 * sync-pin-strip — горизонтальная полоска закреплённых сообщений канала.
 *
 * Источник: useResource('sync/channels').items.find(...).pinned_messages.
 * Источник индекса: useSlice('sync/chat_ui').pinnedNavigateIndex.
 *
 * Клик циклически листает закрепы; emit('jump-to-message', { messageId })
 * для родителя (sync-channel-page) — slot-композиция, не cross-app.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';

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
        this._chatUi = this.useSlice('sync/chat_ui');
    }

    _channel() {
        return this._channels.items.find((c) => c.id === this.channelId);
    }

    _onClick() {
        const channel = this._channel();
        if (!channel || !Array.isArray(channel.pinned_messages) || channel.pinned_messages.length === 0) return;
        const idx = (typeof this._chatUi.value.pinnedNavigateIndex === 'number'
            ? this._chatUi.value.pinnedNavigateIndex
            : 0);
        const next = (idx + 1) % channel.pinned_messages.length;
        const msg = channel.pinned_messages[next];
        this._chatUi.setPinnedIndex({ index: next });
        if (msg && typeof msg.message_id === 'string') {
            this.emit('jump-to-message', { messageId: msg.message_id });
        }
    }

    render() {
        const channel = this._channel();
        if (!channel) return html``;
        const pins = Array.isArray(channel.pinned_messages) ? channel.pinned_messages : [];
        if (pins.length === 0) return html``;
        const idx = typeof this._chatUi.value.pinnedNavigateIndex === 'number'
            ? this._chatUi.value.pinnedNavigateIndex
            : 0;
        const safeIdx = pins.length > 0 ? idx % pins.length : 0;
        const cur = pins[safeIdx];
        const preview = cur && typeof cur.preview === 'string' ? cur.preview : this.t('bubble.default_message');
        return html`
            <div class="row" @click=${this._onClick} title=${this.t('chat_view.pin_strip_title')}>
                <platform-icon name="pin" size="14" class="pin-icon"></platform-icon>
                <span class="preview">${preview}</span>
                <span class="counter">${safeIdx + 1}/${pins.length}</span>
            </div>
        `;
    }
}

customElements.define('sync-pin-strip', SyncPinStrip);
