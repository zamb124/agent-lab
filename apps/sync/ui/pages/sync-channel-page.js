/**
 * sync-channel-page — главный экран чата (по `/sync/c/:channelId`).
 *
 * Состав: <sync-chat-header>, <sync-message-list>, <sync-message-composer>,
 * <sync-thread-drawer>, <sync-message-context-menu>.
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import '@platform/lib/components/glass-spinner.js';
import '../components/sync-chat-header.js';
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
        this.useEvent('sync/message/created', (event) => this._onMessageCreated(event));
    }

    updated(changed) {
        super.updated?.(changed);
        if (changed.has('channelId') && this.channelId) {
            this._messages.run({ channel_id: this.channelId, limit: 50 });
            this.dispatch('sync/channels/channel_selected', { channelId: this.channelId });
        }
    }

    _onMessageCreated(event) {
        const m = event && event.payload;
        if (!m || m.channel_id !== this.channelId) return;
        const list = this.renderRoot && this.renderRoot.querySelector('sync-message-list');
        if (list && typeof list.scrollToBottom === 'function') {
            list.scrollToBottom();
        }
    }

    render() {
        return html`
            <sync-chat-header .channelId=${this.channelId}></sync-chat-header>
            <div class="body">
                <div class="body-main">
                    <sync-message-list .channelId=${this.channelId}></sync-message-list>
                    <sync-message-composer .channelId=${this.channelId}></sync-message-composer>
                </div>
                <sync-thread-drawer .channelId=${this.channelId}></sync-thread-drawer>
            </div>
            <sync-message-context-menu .channelId=${this.channelId}></sync-message-context-menu>
        `;
    }
}

customElements.define('sync-channel-page', SyncChannelPage);
