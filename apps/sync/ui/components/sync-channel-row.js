/**
 * sync-channel-row — строка канала в sidebar.
 *
 * Источник presence: state.syncPresence (typing + presence).
 * Источник звонков:  state.syncCallUi.activeCallChannels.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';
import { channelDisplayTitle } from './_helpers/sync-channel-display.js';

export class SyncChannelRow extends PlatformElement {
    static properties = {
        channel: { type: Object },
    };

    static styles = css`
        :host {
            display: flex;
            align-items: center;
            gap: var(--space-2);
            padding: var(--space-2);
            border-radius: var(--radius-sm);
            cursor: pointer;
        }
        :host(:hover) { background: var(--glass-hover); }
        :host([data-selected]) { background: var(--glass-active, var(--glass-hover)); }
        .text {
            flex: 1;
            min-width: 0;
        }
        .title {
            font-size: var(--text-sm);
            font-weight: 500;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .preview {
            font-size: var(--text-xs);
            color: var(--text-secondary);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .badges {
            display: flex;
            align-items: center;
            gap: var(--space-1);
        }
        .badge {
            min-width: 18px;
            height: 18px;
            padding: 0 4px;
            border-radius: 9px;
            background: var(--accent);
            color: white;
            font-size: var(--text-xs);
            display: inline-flex;
            align-items: center;
            justify-content: center;
        }
        .mention { background: var(--color-danger, #ff6b6b); }
        .call-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: #4ade80;
        }
    `;

    constructor() {
        super();
        this.channel = null;
        this._presenceSel = this.select((s) => s.syncPresence);
        this._callUiSel = this.select((s) => s.syncCallUi);
        this._channelsSel = this.select((s) => s.syncChannels);
    }

    updated() {
        const slice = this._channelsSel.value;
        const selected = slice && slice.selectedChannelId === (this.channel && this.channel.id);
        this.toggleAttribute('data-selected', Boolean(selected));
    }

    _onClick() {
        if (!this.channel) return;
        this.navigate('channel', { channelId: this.channel.id });
    }

    _typingLine() {
        const presence = this._presenceSel.value;
        if (!presence || !this.channel) return null;
        const peers = presence.typingByChannel[this.channel.id];
        if (!peers || Object.keys(peers).length === 0) return null;
        return this.t('sidebar.row_typing');
    }

    render() {
        if (!this.channel) return html``;
        const callUi = this._callUiSel.value;
        const activeCallChannels = (callUi && callUi.activeCallChannels) ? callUi.activeCallChannels : null;
        const callIndicator = activeCallChannels ? activeCallChannels[this.channel.id] : null;
        const typing = this._typingLine();
        let preview = '';
        if (typeof typing === 'string' && typing !== '') preview = typing;
        else if (typeof this.channel.last_message_preview === 'string') preview = this.channel.last_message_preview;
        const unread = typeof this.channel.unread_count === 'number' ? this.channel.unread_count : 0;
        const mentions = typeof this.channel.mention_unread_count === 'number' ? this.channel.mention_unread_count : 0;
        return html`
            <div class="text" @click=${this._onClick}>
                <div class="title">${channelDisplayTitle(this.channel)}</div>
                ${preview ? html`<div class="preview">${preview}</div>` : ''}
            </div>
            <div class="badges">
                ${callIndicator ? html`<span class="call-dot" title=${this.t('sidebar.row_call_active')}></span>` : ''}
                ${mentions > 0 ? html`<span class="badge mention">@${mentions}</span>` : ''}
                ${unread > 0 ? html`<span class="badge">${unread}</span>` : ''}
            </div>
        `;
    }
}

customElements.define('sync-channel-row', SyncChannelRow);
