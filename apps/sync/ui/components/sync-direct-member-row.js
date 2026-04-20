/**
 * sync-direct-member-row — строка участника компании в DM-секции sidebar.
 *
 * Click: ищет direct-канал в state.syncChannels.items; если есть — navigate;
 * иначе создаёт через useResource('sync/channels').create({type:'direct', member_ids}).
 *
 * Отображает аватар (или цветные инициалы), имя, presence subtitle (online /
 * last seen) и пульсирующий зелёный dot online.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { resolveDisplayName } from '../_helpers/sync-id-resolvers.js';
import { hueFromString, initialsFromName } from '../_helpers/sync-hue.js';
import { getPeerPresenceSubtitle } from '../_helpers/sync-presence.js';
import '@platform/lib/components/platform-icon.js';

export class SyncDirectMemberRow extends PlatformElement {
    static properties = {
        member: { type: Object },
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
            animation: subtle-pulse 2s ease-in-out infinite;
        }
        @keyframes subtle-pulse {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.1); }
        }
        .text { flex: 1; min-width: 0; }
        .name {
            font-size: var(--text-sm);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .subtitle {
            font-size: var(--text-xs);
            color: var(--text-secondary);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
    `;

    constructor() {
        super();
        this.member = null;
        this._channels = this.useResource('sync/channels');
        this._presenceSel = this.select((s) => s.syncPresence);
    }

    _findDirectChannel() {
        if (!this.member) return null;
        return this._channels.items.find((c) => c.type === 'direct'
            && c.peer && c.peer.user_id === this.member.user_id);
    }

    _onClick() {
        if (!this.member) return;
        const existing = this._findDirectChannel();
        if (existing) {
            this.navigate('channel', { channelId: existing.id });
            return;
        }
        this._channels.create({ type: 'direct', member_ids: [this.member.user_id] });
    }

    _renderAvatar() {
        const m = this.member;
        const name = resolveDisplayName(m);
        if (typeof m.avatar_url === 'string' && m.avatar_url !== '') {
            return html`<span class="avatar"><img src=${m.avatar_url} alt="" /></span>`;
        }
        const hue = hueFromString(m.user_id);
        return html`<span class="avatar" style=${`background: hsl(${hue}, 60%, 55%)`}>${initialsFromName(name)}</span>`;
    }

    render() {
        if (!this.member) return html``;
        const presence = this._presenceSel.value;
        const presenceByUserId = presence && presence.presenceByUserId ? presence.presenceByUserId : null;
        const userPresence = presenceByUserId ? presenceByUserId[this.member.user_id] : null;
        const subtitle = getPeerPresenceSubtitle(presenceByUserId, this.member.user_id, (k, v) => this.t(k, v));
        return html`
            <span style="position: relative;">
                ${this._renderAvatar()}
                ${userPresence && userPresence.online
                    ? html`<span class="presence-dot" title=${this.t('sidebar.row_online')}></span>`
                    : ''}
            </span>
            <div class="text" @click=${this._onClick}>
                <div class="name">${resolveDisplayName(this.member)}</div>
                ${subtitle ? html`<div class="subtitle">${subtitle}</div>` : ''}
            </div>
        `;
    }
}

customElements.define('sync-direct-member-row', SyncDirectMemberRow);
