/**
 * sync-direct-member-row — строка участника компании в DM-секции sidebar.
 *
 * Клик: ищет direct в списке; если есть — navigate и закрытие моб. сайдбара;
 * иначе create; после sync/channels/created с тем же peer — navigate.
 * Дубликаты direct на сервере не создаются (идемпотентный create).
 *
 * Отображает аватар (или цветные инициалы), имя, presence subtitle (online /
 * last seen) и пульсирующий зелёный dot online.
 */

import type { ResourceController, ControllerFor } from '@platform/lib/base/use-resource.js';
import { html, css } from 'lit';
import type {CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult} from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import type { PlatformEvent } from '@platform/lib/events/contract.js';
import { resolveDisplayName } from '../_helpers/sync-id-resolvers.js';
import { resolveAvatarImageSrc } from '@platform/lib/utils/placeholder-avatar.js';
import { initialsFromName, syncAvatarHueVar } from '../_helpers/sync-hue.js';
import { getPeerPresenceSubtitle, isOnline } from '../_helpers/sync-presence.js';
import '@platform/lib/components/platform-icon.js';
import { SYNC_CHANNELS_CREATED } from '../events/types.js';

export class SyncDirectMemberRow extends PlatformElement {
    static override properties: PropertyDeclarations = {
        member: { type: Object },
        _avatarImgFailed: { state: true },
    };
    declare member: Record<string, unknown> | null;
    declare _avatarImgFailed: unknown;

    static override styles: CSSResultGroup = css`
        :host {
            display: block;
            position: relative;
        }
        .row-inner {
            display: flex;
            align-items: center;
            gap: var(--space-2);
            padding: var(--space-1) var(--space-2);
            border-radius: var(--radius-sm);
            cursor: pointer;
            box-sizing: border-box;
        }
        .row-inner:hover {
            background: var(--glass-hover);
        }
        .avatar {
            width: 32px;
            height: 32px;
            border-radius: 50%;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-weight: 600;
            font-size: var(--text-xs);
            flex-shrink: 0;
            position: relative;
        }
        .avatar.pastel-initials {
            --sync-avatar-h: 0;
            background: hsl(var(--sync-avatar-h), var(--sync-pastel-avatar-s-bg), var(--sync-pastel-avatar-l-bg));
            color: hsl(var(--sync-avatar-h), var(--sync-pastel-avatar-s-fg), var(--sync-pastel-avatar-l-fg));
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

        @media (min-width: 768px) {
            :host-context(platform-service-sidebar[collapsed]) .row-inner {
                justify-content: center;
                width: 100%;
                max-width: 100%;
                margin: 0 0 var(--space-1) 0;
                padding: var(--space-2);
            }
            :host-context(platform-service-sidebar[collapsed]) .text {
                display: none;
            }
            :host-context(platform-service-sidebar[collapsed]) .avatar {
                width: 36px;
                height: 36px;
            }
        }
    `;
    private _channels: ControllerFor<'sync/channels'>;
    private _avatarMemberSig: string;
    private _pendingOpenDmPeerId: any;

    constructor() {
        super();
        this.member = null;
        this._avatarImgFailed = false;
        this._avatarMemberSig = '';
        this._pendingOpenDmPeerId = null;
        this._channels = this.useResource('sync/channels');
        this.useEvent(SYNC_CHANNELS_CREATED, (e) => this._onChannelsCreated(e));
        this.useEvent('sync/channels/create_failed', () => {
            this._pendingOpenDmPeerId = null;
        });
    }

    _closeSidebarMobile() {
        const shell = this.closest('platform-service-sidebar') as { closeMobile?: () => void } | null;
        if (shell && typeof shell.closeMobile === 'function') {
            shell.closeMobile();
        }
    }

    _onChannelsCreated(e: PlatformEvent) {
        if (this._pendingOpenDmPeerId === null) return;
        const p = e.payload as Record<string, unknown> | null;
        if (!p || typeof p !== 'object') return;
        const item = p.item as Record<string, any> | null | undefined;
        if (!item || typeof item !== 'object') return;
        if (item.type !== 'direct') return;
        const peer = item.peer;
        const peerId = peer && typeof peer.user_id === 'string' ? peer.user_id : '';
        if (peerId === '' || peerId !== this._pendingOpenDmPeerId) return;
        this._pendingOpenDmPeerId = null;
        const channelId = item.channel_id;
        if (typeof channelId !== 'string' || channelId === '') return;
        this.navigate('channel', { channelId });
        this._closeSidebarMobile();
    }

    override updated(changed: PropertyValues<this>): void {
        super.updated(changed);
        if (this.member && typeof this.member.user_id === 'string') {
            const au = typeof this.member.avatar_url === 'string' ? this.member.avatar_url : '';
            const sig = `${this.member.user_id}|${au}`;
            if (this._avatarMemberSig !== sig) {
                this._avatarMemberSig = sig;
                this._avatarImgFailed = false;
            }
        }
    }

    _onMemberAvatarError() {
        this._avatarImgFailed = true;
    }

    _findDirectChannel() {
        if (!this.member) return null;
        const member = this.member;
        return this._channels.items.find((c) => c.type === 'direct'
            && member !== null
            && (c.peer as Record<string, unknown> | undefined)?.user_id === member.user_id);
    }

    _onClick() {
        if (!this.member) return;
        const existing = this._findDirectChannel();
        if (existing) {
            this.navigate('channel', { channelId: typeof existing.channel_id === 'string' ? existing.channel_id : '' });
            this._closeSidebarMobile();
            return;
        }
        this._pendingOpenDmPeerId = this.member.user_id;
        this._channels.create({ type: 'direct', member_ids: [this.member.user_id] });
    }

    _renderAvatar() {
        const m = this.member;
        if (!m) return html``;
        const name = resolveDisplayName(m);
        const hueVar = syncAvatarHueVar(m.user_id);
        if (this._avatarImgFailed) {
            return html`<span class="avatar pastel-initials" style=${hueVar}>${initialsFromName(name)}</span>`;
        }
        const mUrl = typeof m.avatar_url === 'string' && m.avatar_url !== '' ? m.avatar_url : null;
        const resolved = resolveAvatarImageSrc({ avatarUrl: mUrl, seed: typeof m.user_id === 'string' ? m.user_id : '' });
        return html`<span class="avatar"><img src=${resolved.src} alt="" @error=${this._onMemberAvatarError} /></span>`;
    }

    override render(): TemplateResult {
        if (!this.member) return html``;
        const subtitle = getPeerPresenceSubtitle(this.member, (k: string, v?: Record<string, string | number> | null) => this.t(k, v));
        return html`
            <div class="row-inner" @click=${this._onClick}>
                <span style="position: relative;">
                    ${this._renderAvatar()}
                    ${isOnline(this.member)
                        ? html`<span class="presence-dot" title=${this.t('sidebar.row_online')}></span>`
                        : ''}
                </span>
                <div class="text">
                    <div class="name">${resolveDisplayName(this.member)}</div>
                    ${subtitle ? html`<div class="subtitle">${subtitle}</div>` : ''}
                </div>
            </div>
        `;
    }
}

customElements.define('sync-direct-member-row', SyncDirectMemberRow);
