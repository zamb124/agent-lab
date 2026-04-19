/**
 * sync-message-list — список сообщений канала.
 *
 * Источник: slice 'syncMessages' (фабрика 'sync/messages').
 * Push-события 'sync/message/created' автоматически попадают в slice
 * через extraReducer messagesResource. Подписка на slice через
 * select() автоматически обновляет UI.
 *
 * Pending optimistic-сообщения (`pendingByLocalId`) отрисовываются
 * полупрозрачными в конце списка.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import './sync-message-bubble.js';

export class SyncMessageList extends PlatformElement {
    static properties = {
        channelId: { type: String },
        threadId: { type: String, attribute: 'thread-id' },
    };

    static styles = css`
        :host {
            display: block;
            height: 100%;
            overflow-y: auto;
            padding: var(--space-3);
        }
        .pending {
            opacity: 0.5;
        }
        .empty {
            text-align: center;
            color: var(--text-secondary);
            padding: var(--space-4);
        }
    `;

    constructor() {
        super();
        this.channelId = '';
        this.threadId = '';
        this._messagesSel = this.select((s) => s.syncMessages);
        this._authSel = this.select((s) => s.auth && s.auth.user);
    }

    scrollToBottom() {
        this.scrollTop = this.scrollHeight;
    }

    updated(changed) {
        super.updated?.(changed);
        if (changed.has('channelId')) {
            queueMicrotask(() => this.scrollToBottom());
        }
    }

    _filterByThread(items) {
        if (this.threadId) {
            return items.filter((m) => m.thread_id === this.threadId);
        }
        return items.filter((m) => !m.thread_id);
    }

    render() {
        const slice = this._messagesSel.value;
        const channelData = (slice && slice.byChannelId && slice.byChannelId[this.channelId])
            ? slice.byChannelId[this.channelId]
            : null;
        const items = (channelData && Array.isArray(channelData.items))
            ? this._filterByThread(channelData.items)
            : [];
        const pending = (channelData && channelData.pendingByLocalId)
            ? Object.values(channelData.pendingByLocalId)
            : [];
        const me = this._authSel.value;
        const myId = (me && typeof me.user_id === 'string') ? me.user_id : '';
        if (items.length === 0 && pending.length === 0) {
            return html`<div class="empty">${this.t('message_list.empty')}</div>`;
        }
        return html`
            ${items.map((m) => html`
                <sync-message-bubble .message=${m} my-user-id=${myId}></sync-message-bubble>
            `)}
            ${pending.map((m) => html`
                <div class="pending">
                    <sync-message-bubble .message=${m} my-user-id=${myId}></sync-message-bubble>
                </div>
            `)}
        `;
    }
}

customElements.define('sync-message-list', SyncMessageList);
