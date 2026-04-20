/**
 * sync-channel-page — главный экран чата (по `/sync/c/:channelId`).
 *
 * Состав: <sync-chat-header>, <sync-pin-strip>, <sync-selection-bar>,
 * <sync-message-list>, <sync-message-composer>, <sync-thread-drawer>,
 * <sync-message-context-menu>.
 *
 * Mount-логика: при смене channelId — useOp('sync/messages').run({ channel_id })
 * + dispatch channels/channel_selected + mark_read для обнуления unread.
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import '@platform/lib/components/glass-spinner.js';
import '../components/sync-chat-header.js';
import '../components/sync-pin-strip.js';
import '../components/sync-selection-bar.js';
import '../components/sync-message-list.js';
import '../components/sync-message-composer.js';
import '../components/sync-message-context-menu.js';
import '../components/sync-thread-drawer.js';

export class SyncChannelPage extends PlatformPage {
    static properties = {
        channelId: { type: String },
    };

    static styles = css`
        :host {
            display: flex;
            flex-direction: column;
            height: 100%;
            min-height: 0;
            position: relative;
        }
        .body {
            flex: 1;
            min-height: 0;
            overflow: hidden;
            display: flex;
        }
        .body-main {
            flex: 1;
            min-height: 0;
            overflow: hidden;
            display: flex;
            flex-direction: column;
        }
    `;

    constructor() {
        super();
        this.channelId = '';
        this._channels = this.useResource('sync/channels', { autoload: true });
        this._messages = this.useOp('sync/messages');
        this._markRead = this.useOp('sync/channel_mark_read');
        this._authSel = this.select((s) => s.auth && s.auth.user);
        this._lastLoadedChannel = '';
        this.useEvent('sync/message/created', (event) => this._onMessageCreated(event));
    }

    updated(changed) {
        super.updated?.(changed);
        if (this.channelId && this._lastLoadedChannel !== this.channelId) {
            this._lastLoadedChannel = this.channelId;
            this._messages.run({ channel_id: this.channelId, limit: 50 });
            this.dispatch('sync/channels/channel_selected', { channelId: this.channelId });
            this._markRead.run({ channel_id: this.channelId });
        }
    }

    _onMessageCreated(event) {
        const m = event && event.payload;
        if (!m || m.channel_id !== this.channelId) return;
        this._markRead.run({ channel_id: this.channelId });
    }

    _resolveMyUserId() {
        const me = this._authSel.value;
        if (!me || typeof me.user_id !== 'string') return '';
        return me.user_id;
    }

    _channel() {
        return this._channels.items.find((c) => c.id === this.channelId);
    }

    render() {
        const channel = this._channel();
        const channelType = channel && typeof channel.type === 'string' ? channel.type : '';
        const myUserId = this._resolveMyUserId();
        return html`
            <sync-chat-header .channelId=${this.channelId}></sync-chat-header>
            <sync-pin-strip .channelId=${this.channelId}></sync-pin-strip>
            <sync-selection-bar .channelId=${this.channelId}></sync-selection-bar>
            <div class="body">
                <div class="body-main">
                    <sync-message-list
                        .channelId=${this.channelId}
                        my-user-id=${myUserId}
                        channel-type=${channelType}
                    ></sync-message-list>
                    <sync-message-composer .channelId=${this.channelId}></sync-message-composer>
                </div>
                <sync-thread-drawer .channelId=${this.channelId}></sync-thread-drawer>
            </div>
            <sync-message-context-menu .channelId=${this.channelId}></sync-message-context-menu>
        `;
    }
}

customElements.define('sync-channel-page', SyncChannelPage);
