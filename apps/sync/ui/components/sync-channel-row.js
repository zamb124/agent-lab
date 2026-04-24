/**
 * sync-channel-row — строка канала / DM в sidebar.
 *
 * Источники:
 *   useResource('sync/channels')      — выбранный канал, для подсветки.
 *   select syncPresence                — typing preview, online dot для DM.
 *   select syncCallUi.activeCallChannels — pill «Войти» (как баннер свёрнутого звонка).
 *
 * Действия: navigate('channel', { channelId }); иконка типа (user / users); шестерёнка:
 * группы — sync.channel_edit, личные — platform.user_info.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';
import { channelDisplayTitle } from './_helpers/sync-channel-display.js';
import { resolveAvatarImageSrc } from '@platform/lib/utils/placeholder-avatar.js';
import { syncChannelPlaceholderCollection } from '../_helpers/sync-channel-placeholder-collection.js';
import { initialsFromName, syncAvatarHueVar } from '../_helpers/sync-hue.js';
import { isOnline } from '../_helpers/sync-presence.js';
import { getTypingIndicatorLine } from '../_helpers/sync-typing.js';

export class SyncChannelRow extends PlatformElement {
    static properties = {
        channel: { type: Object },
        _avatarImgFailed: { state: true },
    };

    static styles = css`
        :host {
            display: flex;
            align-items: center;
            gap: var(--space-3);
            padding: var(--space-3);
            margin: 0;
            border-radius: var(--radius-xl);
            cursor: pointer;
            position: relative;
            box-sizing: border-box;
            background: var(--sync-channel-row-bg, var(--glass-solid-medium));
            border: 1px solid var(--sync-channel-row-border, var(--glass-border-subtle, var(--glass-border)));
            box-shadow: 0 1px 3px rgba(15, 23, 42, 0.08);
            transition: background var(--duration-fast), box-shadow var(--duration-fast), border-color var(--duration-fast);
        }
        :host(:hover) {
            background: var(--sync-channel-row-bg-hover, var(--glass-solid-strong));
            border-color: var(--sync-channel-row-border-hover, var(--accent));
            box-shadow: 0 2px 10px rgba(15, 23, 42, 0.1);
        }
        :host([data-selected]) {
            background: var(--accent);
            border-color: transparent;
            box-shadow: 0 4px 12px var(--accent-subtle, rgba(153, 166, 249, 0.18));
        }
        :host([data-selected]) .title,
        :host([data-selected]) .time,
        :host([data-selected]) .preview { color: var(--text-inverse, #fff); }
        :host([data-selected]) .preview.typing { color: var(--text-inverse, #fff); font-weight: var(--font-medium); }
        :host([data-mention]:not([data-selected])) .title { color: var(--accent); font-weight: var(--font-semibold); }

        .avatar {
            width: 48px;
            height: 48px;
            border-radius: 50%;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            color: var(--text-inverse, #fff);
            font-weight: var(--font-semibold);
            font-size: var(--text-sm);
            flex-shrink: 0;
            position: relative;
            overflow: hidden;
            background: var(--accent-subtle, rgba(99, 102, 241, 0.15));
            box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--text-primary) 10%, transparent);
        }
        :host([data-selected]) .avatar:not(.pastel-initials) {
            background: rgba(255, 255, 255, 0.22);
            box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.28);
        }
        .avatar.pastel-initials {
            --sync-avatar-h: 0;
            background: hsl(var(--sync-avatar-h), var(--sync-pastel-avatar-s-bg), var(--sync-pastel-avatar-l-bg));
            color: hsl(var(--sync-avatar-h), var(--sync-pastel-avatar-s-fg), var(--sync-pastel-avatar-l-fg));
            box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--text-primary) 8%, transparent);
        }
        :host([data-selected]) .avatar.pastel-initials {
            background: rgba(255, 255, 255, 0.28);
            color: var(--text-inverse, #fff);
        }
        .avatar img {
            width: 100%;
            height: 100%;
            object-fit: cover;
            border-radius: 50%;
        }
        .presence-dot {
            position: absolute;
            right: 0;
            bottom: 0;
            width: 14px;
            height: 14px;
            border-radius: 50%;
            background: var(--success, #22c55e);
            border: 2px solid var(--bg-elevated, var(--glass-solid));
        }
        :host([data-selected]) .presence-dot { border-color: var(--accent); }

        .text {
            flex: 1;
            min-width: 0;
            display: flex;
            flex-direction: column;
            gap: 2px;
        }
        .row-top {
            display: flex;
            align-items: baseline;
            gap: var(--space-2);
        }
        .title {
            flex: 1;
            min-width: 0;
            font-size: var(--text-base);
            font-weight: var(--font-semibold);
            color: var(--text-primary);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .time {
            font-size: var(--text-xs);
            color: var(--text-tertiary);
            white-space: nowrap;
            flex-shrink: 0;
        }
        .row-bottom {
            display: flex;
            align-items: center;
            gap: var(--space-2);
            min-width: 0;
        }
        .preview {
            flex: 1;
            min-width: 0;
            font-size: var(--text-sm);
            color: var(--text-secondary);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .preview.typing { color: var(--accent); font-style: italic; }

        .row-bottom-trail {
            display: inline-flex;
            align-items: center;
            gap: var(--space-2);
            flex-shrink: 0;
        }
        .kind-icon-wrap {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
            color: var(--text-tertiary);
            pointer-events: none;
        }
        .kind-icon-wrap--direct {
            color: color-mix(in srgb, var(--accent) 88%, var(--text-primary));
        }
        .kind-icon-wrap--group {
            color: var(--text-secondary);
        }
        :host([data-selected]) .kind-icon-wrap {
            color: rgba(255, 255, 255, 0.92);
        }

        .badges {
            display: inline-flex;
            align-items: center;
            gap: var(--space-1);
            flex-shrink: 0;
        }
        .badge {
            min-width: 20px;
            height: 20px;
            padding: 0 6px;
            border-radius: 999px;
            background: var(--accent);
            color: var(--text-inverse, #fff);
            font-size: var(--text-xs);
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-weight: var(--font-bold);
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
        }
        :host([data-selected]) .badge {
            background: var(--text-inverse, #fff);
            color: var(--accent);
        }
        .badge.mention { background: var(--color-error, #ef4444); }
        :host([data-selected]) .badge.mention { background: var(--text-inverse, #fff); color: var(--color-error, #ef4444); }

        .call-pill {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            padding: 3px 10px;
            border-radius: 999px;
            border: none;
            background: var(--accent-gradient, linear-gradient(135deg, #6366f1, #8b5cf6));
            color: var(--text-inverse, #fff);
            font-size: var(--text-xs);
            font-weight: var(--font-semibold);
            cursor: pointer;
            box-shadow: 0 1px 4px rgba(99, 102, 241, 0.22);
        }
        .call-pill:hover {
            filter: brightness(1.06);
        }
        .call-pill:focus-visible {
            outline: 2px solid rgba(99, 102, 241, 0.75);
            outline-offset: 2px;
        }
        :host([data-selected]) .call-pill {
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.12);
        }

        .gear {
            opacity: 0;
            transition: opacity var(--duration-fast);
            background: transparent;
            border: none;
            color: var(--text-secondary);
            padding: 4px;
            cursor: pointer;
            border-radius: var(--radius-sm);
        }
        :host(:hover) .gear { opacity: 1; }
        .gear:hover { background: var(--glass-hover); color: var(--text-primary); }
        :host([data-selected]) .gear { color: var(--text-inverse, #fff); }

        @media (min-width: 768px) {
            :host-context(platform-service-sidebar[collapsed]) {
                justify-content: center;
                width: 100%;
                max-width: 100%;
                margin: 0 0 var(--space-2) 0;
                padding: var(--space-2);
                gap: 0;
                box-sizing: border-box;
            }
            :host-context(platform-service-sidebar[collapsed]) .text {
                display: none;
            }
            :host-context(platform-service-sidebar[collapsed]) .avatar {
                width: 40px;
                height: 40px;
                font-size: var(--text-xs);
            }
            :host-context(platform-service-sidebar[collapsed]) .presence-dot {
                width: 12px;
                height: 12px;
            }
        }
    `;

    constructor() {
        super();
        this.channel = null;
        this._avatarImgFailed = false;
        this._avatarRowSig = '';
        this._presenceSel = this.select((s) => s.syncPresence);
        this._callUiSel = this.select((s) => s.syncCallUi);
        this._callUi = this.useSlice('sync/call_ui');
        this._modalsSel = this.select((s) => s.modals.stack);
        this._channelsSel = this.select((s) => s.syncChannels);
        this._authSel = this.select((s) => s.auth && s.auth.user);
        this._members = this.useResource('sync/company_members');
    }

    updated(changed) {
        super.updated(changed);
        if (this.channel) {
            const isDm = this.channel.type === 'direct' && this.channel.peer
                && typeof this.channel.peer.user_id === 'string';
            let sig;
            if (isDm) {
                const peer = this.channel.peer;
                const au = typeof peer.avatar_url === 'string' ? peer.avatar_url : '';
                sig = `dm:${peer.user_id}|${au}`;
            } else {
                const id = typeof this.channel.id === 'string' ? this.channel.id : '';
                const au = typeof this.channel.avatar_url === 'string' ? this.channel.avatar_url : '';
                sig = `ch:${id}|${au}`;
            }
            if (this._avatarRowSig !== sig) {
                this._avatarRowSig = sig;
                this._avatarImgFailed = false;
            }
        }
        const slice = this._channelsSel.value;
        const selected = slice && slice.selectedChannelId === (this.channel && this.channel.id);
        this.toggleAttribute('data-selected', Boolean(selected));
        const mention = !!(this.channel && typeof this.channel.mention_unread_count === 'number'
            && this.channel.mention_unread_count > 0);
        this.toggleAttribute('data-mention', mention);
    }

    _onRowAvatarError() {
        this._avatarImgFailed = true;
    }

    _onClick() {
        if (!this.channel) return;
        this.navigate('channel', { channelId: this.channel.id });
    }

    _onJoinCall(callInfo, e) {
        e.stopPropagation();
        if (!this.channel || !callInfo || typeof callInfo.call_id !== 'string' || callInfo.call_id === '') {
            return;
        }
        const stack = this._modalsSel.value;
        const list = Array.isArray(stack) ? stack : [];
        const hasOverlay = list.some(
            (m) => m.kind === 'sync.call_overlay'
                && m.props
                && typeof m.props.callId === 'string'
                && m.props.callId === callInfo.call_id,
        );
        this._callUi.expandOverlay(null);
        if (!hasOverlay) {
            const callType = typeof callInfo.call_type === 'string' && callInfo.call_type !== ''
                ? callInfo.call_type
                : 'video';
            this.openModal('sync.call_overlay', {
                callId: callInfo.call_id,
                channelId: this.channel.id,
                callType,
            });
        }
        this.navigate('channel', { channelId: this.channel.id });
    }

    _onGear(e) {
        e.stopPropagation();
        if (!this.channel) return;
        const ch = this.channel;
        const isDm = ch.type === 'direct' && ch.peer && typeof ch.peer.user_id === 'string' && ch.peer.user_id !== '';
        if (isDm) {
            this.openModal('platform.user_info', { userId: ch.peer.user_id });
            return;
        }
        if (typeof ch.id === 'string' && ch.id !== '') {
            this.openModal('sync.channel_edit', { channelId: ch.id });
        }
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
            const hueVar = syncAvatarHueVar(channel.peer.user_id);
            if (this._avatarImgFailed) {
                return html`<span class="avatar pastel-initials" style=${hueVar}>
                    ${initialsFromName(name)}
                    ${online ? html`<span class="presence-dot"></span>` : ''}
                </span>`;
            }
            const peerUrl = typeof channel.peer.avatar_url === 'string' && channel.peer.avatar_url !== ''
                ? channel.peer.avatar_url
                : null;
            const resolved = resolveAvatarImageSrc({ avatarUrl: peerUrl, seed: channel.peer.user_id });
            return html`<span class="avatar">
                <img src=${resolved.src} alt="" @error=${this._onRowAvatarError} />
                ${online ? html`<span class="presence-dot"></span>` : ''}
            </span>`;
        }
        const name = typeof channel.name === 'string' && channel.name !== '' ? channel.name : '#';
        const chId = typeof channel.id === 'string' ? channel.id : 'sync';
        const hueVar = syncAvatarHueVar(chId);
        if (this._avatarImgFailed) {
            return html`<span class="avatar pastel-initials" style=${hueVar}>${initialsFromName(name)}</span>`;
        }
        const chUrl = typeof channel.avatar_url === 'string' && channel.avatar_url !== ''
            ? channel.avatar_url
            : null;
        const resolved = resolveAvatarImageSrc({
            avatarUrl: chUrl,
            seed: chId,
            collection: syncChannelPlaceholderCollection(channel),
        });
        return html`<span class="avatar"><img src=${resolved.src} alt="" @error=${this._onRowAvatarError} /></span>`;
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
        const lastAtIso = typeof this.channel.last_message_at === 'string' ? this.channel.last_message_at : '';
        const timeLabel = lastAtIso !== '' ? this._formatTime(lastAtIso) : '';
        const isDm = this.channel.type === 'direct' && this.channel.peer
            && typeof this.channel.peer.user_id === 'string' && this.channel.peer.user_id !== '';
        const showGear = isDm || this.channel.type !== 'direct';
        const gearTitle = isDm
            ? this.t('chat_view.peer_profile_aria')
            : this.t('sidebar.channel_settings_aria');
        const isDirectType = this.channel.type === 'direct';
        const kindIconClass = isDirectType ? 'kind-icon-wrap kind-icon-wrap--direct' : 'kind-icon-wrap kind-icon-wrap--group';
        const kindAria = isDirectType ? this.t('sidebar.meta_direct') : this.t('sidebar.meta_group');
        const kindIconName = isDirectType ? 'user' : 'users';
        return html`
            ${this._renderAvatar()}
            <div class="text" @click=${this._onClick}>
                <div class="row-top">
                    <span class="title">${channelDisplayTitle(this.channel)}</span>
                    ${timeLabel !== '' ? html`<span class="time">${timeLabel}</span>` : ''}
                </div>
                <div class="row-bottom">
                    ${typingLine !== ''
                        ? html`<span class="preview typing">${typingLine}</span>`
                        : html`<span class="preview">${previewText}</span>`}
                    <div class="row-bottom-trail">
                        <span class=${kindIconClass} title=${kindAria} aria-label=${kindAria} role="img">
                            <platform-icon name=${kindIconName} size="14"></platform-icon>
                        </span>
                        <div class="badges">
                            ${activeCall ? html`
                                <button
                                    type="button"
                                    class="call-pill"
                                    @click=${(e) => this._onJoinCall(activeCall, e)}
                                    title=${this.t('sidebar.call_active_title')}
                                >
                                    <platform-icon name="phone" size="10"></platform-icon>
                                    ${this.t('sidebar.call_join')}
                                </button>
                            ` : ''}
                            ${mentions > 0 ? html`<span class="badge mention">@${mentions}</span>` : ''}
                            ${unread > 0 ? html`<span class="badge">${unread}</span>` : ''}
                            ${showGear ? html`
                                <button
                                    class="gear"
                                    @click=${this._onGear}
                                    title=${gearTitle}
                                    aria-label=${gearTitle}
                                >
                                    <platform-icon name="settings" size="14"></platform-icon>
                                </button>
                            ` : ''}
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    _formatTime(iso) {
        const dt = new Date(iso);
        if (Number.isNaN(dt.getTime())) return '';
        const now = new Date();
        const sameDay = dt.getFullYear() === now.getFullYear()
            && dt.getMonth() === now.getMonth()
            && dt.getDate() === now.getDate();
        if (sameDay) {
            return dt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        }
        const yesterday = new Date(now);
        yesterday.setDate(now.getDate() - 1);
        const wasYesterday = dt.getFullYear() === yesterday.getFullYear()
            && dt.getMonth() === yesterday.getMonth()
            && dt.getDate() === yesterday.getDate();
        if (wasYesterday) return this.t('sidebar.time_yesterday');
        const within7days = (now.getTime() - dt.getTime()) < 7 * 24 * 60 * 60 * 1000;
        if (within7days) {
            return dt.toLocaleDateString([], { weekday: 'short' });
        }
        return dt.toLocaleDateString([], { day: '2-digit', month: '2-digit' });
    }
}

customElements.define('sync-channel-row', SyncChannelRow);
