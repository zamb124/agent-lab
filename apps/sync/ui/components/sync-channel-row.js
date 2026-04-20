/**
 * sync-channel-row — строка канала / DM в sidebar.
 *
 * Источники:
 *   useResource('sync/channels')      — выбранный канал, для подсветки.
 *   select syncPresence                — typing preview, online dot для DM.
 *   select syncCallUi.activeCallChannels — зелёный «Войти» pill при активном звонке.
 *
 * Действия: navigate('channel', { channelId }), openModal('sync.channel_edit')
 * на gear-иконке (hover).
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';
import { channelDisplayTitle } from './_helpers/sync-channel-display.js';
import { hueFromString, initialsFromName } from '../_helpers/sync-hue.js';
import { isOnline } from '../_helpers/sync-presence.js';
import { getTypingIndicatorLine } from '../_helpers/sync-typing.js';

export class SyncChannelRow extends PlatformElement {
    static properties = {
        channel: { type: Object },
    };

    static styles = css`
        :host {
            display: flex;
            align-items: center;
            gap: var(--space-2);
            padding: var(--space-1) var(--space-2);
            border-radius: var(--radius-sm);
            cursor: pointer;
            position: relative;
        }
        :host(:hover) { background: var(--glass-hover); }
        :host([data-selected]) { background: var(--glass-active, var(--glass-hover)); }
        :host([data-mention]) .title { color: var(--accent); font-weight: 600; }
        .avatar {
            width: 32px;
            height: 32px;
            border-radius: 50%;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-weight: 600;
            font-size: var(--text-xs);
            flex-shrink: 0;
            position: relative;
        }
        .avatar img {
            width: 100%;
            height: 100%;
            object-fit: cover;
            border-radius: 50%;
        }
        .presence-dot {
            position: absolute;
            right: -1px;
            bottom: -1px;
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: var(--success, #22c55e);
            border: 2px solid var(--glass-solid);
        }
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
        .preview.typing { color: var(--accent); font-style: italic; }
        .badges {
            display: flex;
            align-items: center;
            gap: var(--space-1);
            flex-shrink: 0;
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
            font-weight: 600;
        }
        .badge.mention { background: var(--error, #ef4444); }
        .call-pill {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            padding: 2px 8px;
            border-radius: 999px;
            background: #22c55e;
            color: white;
            font-size: 11px;
            font-weight: 600;
            cursor: pointer;
        }
        .gear {
            opacity: 0;
            transition: opacity 150ms ease;
            background: transparent;
            border: none;
            color: var(--text-secondary);
            padding: 2px;
            cursor: pointer;
        }
        :host(:hover) .gear { opacity: 1; }
    `;

    constructor() {
        super();
        this.channel = null;
        this._presenceSel = this.select((s) => s.syncPresence);
        this._callUiSel = this.select((s) => s.syncCallUi);
        this._channelsSel = this.select((s) => s.syncChannels);
        this._authSel = this.select((s) => s.auth && s.auth.user);
        this._members = this.useResource('sync/company_members');
    }

    updated() {
        const slice = this._channelsSel.value;
        const selected = slice && slice.selectedChannelId === (this.channel && this.channel.id);
        this.toggleAttribute('data-selected', Boolean(selected));
        const mention = !!(this.channel && typeof this.channel.mention_unread_count === 'number'
            && this.channel.mention_unread_count > 0);
        this.toggleAttribute('data-mention', mention);
    }

    _onClick() {
        if (!this.channel) return;
        this.navigate('channel', { channelId: this.channel.id });
    }

    _onJoinCall(callId, e) {
        e.stopPropagation();
        if (typeof callId !== 'string' || callId === '') return;
        this.navigate('channel', { channelId: this.channel.id });
    }

    _onGear(e) {
        e.stopPropagation();
        if (!this.channel) return;
        this.openModal('sync.channel_edit', { channelId: this.channel.id });
    }

    _renderAvatar() {
        const channel = this.channel;
        const isDm = channel.type === 'direct' && channel.peer && typeof channel.peer.user_id === 'string';
        if (isDm) {
            const presenceByUserId = this._presenceSel.value && this._presenceSel.value.presenceByUserId;
            const online = isOnline(presenceByUserId, channel.peer.user_id);
            const name = typeof channel.peer.display_name === 'string' && channel.peer.display_name !== ''
                ? channel.peer.display_name
                : channel.peer.user_id;
            const hue = hueFromString(channel.peer.user_id);
            return html`<span class="avatar" style=${`background: hsl(${hue}, 60%, 55%)`}>
                ${typeof channel.peer.avatar_url === 'string' && channel.peer.avatar_url !== ''
                    ? html`<img src=${channel.peer.avatar_url} alt="" />`
                    : initialsFromName(name)}
                ${online ? html`<span class="presence-dot"></span>` : ''}
            </span>`;
        }
        const name = typeof channel.name === 'string' && channel.name !== '' ? channel.name : '#';
        const hue = hueFromString(typeof channel.id === 'string' ? channel.id : 'sync');
        if (typeof channel.avatar_url === 'string' && channel.avatar_url !== '') {
            return html`<span class="avatar"><img src=${channel.avatar_url} alt="" /></span>`;
        }
        return html`<span class="avatar" style=${`background: hsl(${hue}, 60%, 55%)`}>${initialsFromName(name)}</span>`;
    }

    render() {
        if (!this.channel) return html``;
        const presence = this._presenceSel.value;
        const typingByChannel = presence && presence.typingByChannel ? presence.typingByChannel : null;
        const me = this._authSel.value;
        const myUserId = me && typeof me.user_id === 'string' ? me.user_id : '';
        const typingLine = getTypingIndicatorLine({
            typingByChannel,
            channelId: this.channel.id,
            threadId: null,
            myUserId,
            members: this._members.items,
            t: (k, v) => this.t(k, v),
        });
        const callUi = this._callUiSel.value;
        const activeCall = callUi && callUi.activeCallChannels && callUi.activeCallChannels[this.channel.id];
        const unread = typeof this.channel.unread_count === 'number' ? this.channel.unread_count : 0;
        const mentions = typeof this.channel.mention_unread_count === 'number' ? this.channel.mention_unread_count : 0;
        const previewText = typeof this.channel.last_message_preview === 'string' ? this.channel.last_message_preview : '';
        return html`
            ${this._renderAvatar()}
            <div class="text" @click=${this._onClick}>
                <div class="title">${channelDisplayTitle(this.channel)}</div>
                ${typingLine !== ''
                    ? html`<div class="preview typing">${typingLine}</div>`
                    : (previewText !== '' ? html`<div class="preview">${previewText}</div>` : '')}
            </div>
            <div class="badges">
                ${activeCall ? html`
                    <span class="call-pill" @click=${(e) => this._onJoinCall(activeCall.call_id, e)} title=${this.t('sidebar.call_active_title')}>
                        <platform-icon name="phone" size="10"></platform-icon>
                        ${this.t('sidebar.call_join')}
                    </span>
                ` : ''}
                ${mentions > 0 ? html`<span class="badge mention">@${mentions}</span>` : ''}
                ${unread > 0 ? html`<span class="badge">${unread}</span>` : ''}
                ${this.channel.type !== 'direct' ? html`
                    <button class="gear" @click=${this._onGear} title=${this.t('sidebar.channel_settings_aria')}>
                        <platform-icon name="settings" size="14"></platform-icon>
                    </button>
                ` : ''}
            </div>
        `;
    }
}

customElements.define('sync-channel-row', SyncChannelRow);
