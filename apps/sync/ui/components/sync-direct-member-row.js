/**
 * sync-direct-member-row — строка участника компании в DM-секции sidebar.
 *
 * Click: ищет direct-канал в state.syncChannels.items; если есть — navigate;
 * иначе создаёт через useResource('sync/channels').create({type: 'direct',
 * member_ids: [user_id]}).
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { resolveDisplayName } from '../_helpers/sync-id-resolvers.js';
import '@platform/lib/components/platform-user-chip.js';

export class SyncDirectMemberRow extends PlatformElement {
    static properties = {
        member: { type: Object },
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
        .text { flex: 1; min-width: 0; }
        .name {
            font-size: var(--text-sm);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .presence-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: #4ade80;
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
        return this._channels.items.find((c) => {
            return c.type === 'direct' && c.peer && c.peer.user_id === this.member.user_id;
        });
    }

    _onClick() {
        if (!this.member) return;
        const existing = this._findDirectChannel();
        if (existing) {
            this.navigate('channel', { channelId: existing.id });
            return;
        }
        this._channels.create({
            type: 'direct',
            member_ids: [this.member.user_id],
        });
    }

    render() {
        if (!this.member) return html``;
        const presence = this._presenceSel.value;
        const presenceByUserId = (presence && presence.presenceByUserId) ? presence.presenceByUserId : null;
        const userPresence = presenceByUserId ? presenceByUserId[this.member.user_id] : null;
        return html`
            <platform-user-chip user-id=${this.member.user_id} size="sm" ?interactive=${false}></platform-user-chip>
            <div class="text" @click=${this._onClick}>
                <div class="name">${resolveDisplayName(this.member)}</div>
            </div>
            ${userPresence && userPresence.online
                ? html`<span class="presence-dot" title=${this.t('sidebar.row_online')}></span>`
                : ''}
        `;
    }
}

customElements.define('sync-direct-member-row', SyncDirectMemberRow);
