/**
 * sync-chat-header — шапка чата:
 *   - аватар канала (или DM-собеседник через platform-user-chip),
 *   - название + подзаголовок (typing / online / last seen / channel meta),
 *   - кнопки call / threads / more,
 *   - баннер активного звонка (свёрнутого) — открывает overlay.
 *
 * Источники: useResource('sync/channels'), select syncPresence, syncCallUi.
 * Действия: openModal('platform.user_info', ...), openModal('sync.channel_edit'),
 *           useOp('sync/calls_invite'), dispatch overlay_expanded.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-user-chip.js';
import { buildChatSubtitle, channelDisplayTitle } from './_helpers/sync-channel-display.js';
import { isOnline } from '../_helpers/sync-presence.js';
import { hueFromString, initialsFromName } from '../_helpers/sync-hue.js';
import { resolveDisplayName } from '../_helpers/sync-id-resolvers.js';

export class SyncChatHeader extends PlatformElement {
    static properties = {
        channelId: { type: String },
        _menuOpen: { state: true },
    };

    static styles = css`
        :host {
            display: flex;
            align-items: center;
            gap: var(--space-3);
            padding: var(--space-3) var(--space-6);
            border-bottom: 1px solid var(--glass-border);
            background: var(--glass-solid-soft, var(--glass-solid));
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            min-height: 72px;
            position: sticky;
            top: 0;
            z-index: 10;
        }
        :host([data-call-banner]) {
            background: var(--accent-gradient, linear-gradient(135deg, #6366f1, #8b5cf6));
            color: var(--text-inverse, #fff);
        }
        .menu-btn {
            display: none;
            background: transparent;
            border: none;
            color: var(--text-primary);
            padding: var(--space-2);
            margin-left: calc(var(--space-2) * -1);
            border-radius: var(--radius-full, 999px);
            cursor: pointer;
        }
        .menu-btn:hover { background: var(--glass-hover); }
        @media (max-width: 767px) {
            .menu-btn { display: inline-flex; }
        }
        .avatar {
            width: 44px;
            height: 44px;
            border-radius: 50%;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            color: var(--text-inverse, #fff);
            font-weight: var(--font-semibold);
            font-size: var(--text-sm);
            flex-shrink: 0;
            position: relative;
            box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
            cursor: pointer;
            transition: transform var(--duration-fast);
        }
        .avatar:hover { transform: scale(1.05); }
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
            width: 12px;
            height: 12px;
            border-radius: 50%;
            background: var(--success, #22c55e);
            border: 2px solid var(--bg-elevated, var(--glass-solid));
        }
        .text {
            display: flex;
            flex-direction: column;
            flex: 1;
            min-width: 0;
            gap: 2px;
        }
        .title {
            font-weight: var(--font-semibold);
            font-size: var(--text-base);
            color: var(--text-primary);
            line-height: 1.2;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .subtitle {
            font-size: var(--text-sm);
            color: var(--text-secondary);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .subtitle.online { color: var(--accent); font-weight: var(--font-medium); }
        :host([data-call-banner]) .title,
        :host([data-call-banner]) .subtitle { color: var(--text-inverse, #fff); }
        :host([data-call-banner]) .subtitle { color: rgba(255, 255, 255, 0.88); }

        .actions {
            display: inline-flex;
            align-items: center;
            gap: var(--space-1);
            position: relative;
        }
        .actions-divider {
            width: 1px;
            height: 24px;
            background: var(--glass-border);
            margin: 0 var(--space-1);
        }
        .icon-btn {
            background: transparent;
            border: none;
            color: var(--text-tertiary);
            padding: 10px;
            cursor: pointer;
            border-radius: var(--radius-full, 999px);
            display: inline-flex;
            align-items: center;
            justify-content: center;
            transition: background var(--duration-fast), color var(--duration-fast);
        }
        .icon-btn:hover { background: var(--glass-hover); color: var(--text-primary); }
        .icon-btn.accent:hover {
            background: var(--accent-subtle, rgba(153, 166, 249, 0.12));
            color: var(--accent);
        }
        :host([data-call-banner]) .icon-btn { color: var(--text-inverse, #fff); }
        :host([data-call-banner]) .icon-btn:hover { background: rgba(255, 255, 255, 0.16); color: var(--text-inverse, #fff); }
        .pulse {
            display: inline-block;
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: rgba(255,255,255,0.95);
            animation: pulse 1.6s ease-in-out infinite;
            margin-right: 6px;
            vertical-align: middle;
        }
        @keyframes pulse {
            0%, 100% { opacity: 0.4; transform: scale(0.85); }
            50% { opacity: 1; transform: scale(1); }
        }
        .menu-flyout {
            position: absolute;
            right: 0;
            top: 100%;
            margin-top: 4px;
            min-width: 200px;
            background: var(--glass-solid);
            border: 1px solid var(--glass-border);
            border-radius: var(--radius-md);
            box-shadow: 0 8px 24px rgba(0,0,0,0.18);
            padding: var(--space-1) 0;
            z-index: 30;
        }
        .menu-flyout button {
            display: flex;
            align-items: center;
            gap: var(--space-2);
            width: 100%;
            background: transparent;
            border: none;
            text-align: left;
            padding: var(--space-2) var(--space-3);
            color: var(--text-primary);
            cursor: pointer;
            font-size: var(--text-sm);
        }
        .menu-flyout button:hover { background: var(--glass-hover); }
        .menu-flyout .ws-row {
            padding: var(--space-2) var(--space-3);
            color: var(--text-secondary);
            font-size: var(--text-xs);
            display: flex;
            align-items: center;
            gap: var(--space-1);
            border-top: 1px solid var(--glass-border);
        }
        .ws-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: #94a3b8;
        }
        .ws-dot.connected { background: #22c55e; }
        .ws-dot.connecting { background: #eab308; }
    `;

    constructor() {
        super();
        this.channelId = '';
        this._menuOpen = false;
        this._channels = this.useResource('sync/channels', { autoload: true });
        this._members = this.useResource('sync/company_members');
        this._authSel = this.select((s) => s.auth && s.auth.user);
        this._presenceSel = this.select((s) => s.syncPresence);
        this._callUiSel = this.select((s) => s.syncCallUi);
        this._callUi = this.useSlice('sync/call_ui');
        this._wsSel = this.select((s) => s.network);
        this._callInvite = this.useOp('sync/calls_invite');
        this._callHangup = this.useOp('sync/calls_hangup');
        this._onDocClick = (e) => {
            if (!this._menuOpen) return;
            if (e.composedPath().some((n) => n === this)) return;
            this._menuOpen = false;
        };
    }

    connectedCallback() {
        super.connectedCallback();
        document.addEventListener('pointerdown', this._onDocClick);
    }

    disconnectedCallback() {
        document.removeEventListener('pointerdown', this._onDocClick);
        super.disconnectedCallback();
    }

    _channel() {
        return this._channels.items.find((c) => c.id === this.channelId);
    }

    _onMenuClick() {
        this.openSidebar();
    }

    async _onInviteCall() {
        if (!this.channelId) return;
        await this._callInvite.run({ channel_id: this.channelId });
        const result = this._callInvite.lastResult;
        if (!result || typeof result.call_id !== 'string') return;
        this._callUi.openOverlay({
            call_id: result.call_id,
            channel_id: typeof result.channel_id === 'string' ? result.channel_id : this.channelId,
            call_type: typeof result.call_type === 'string' ? result.call_type : 'video',
            livekit_room_name: typeof result.livekit_room_name === 'string' ? result.livekit_room_name : null,
            livekit_url: typeof result.livekit_url === 'string' ? result.livekit_url : null,
        });
        this.openModal('sync.call_overlay', {
            callId: result.call_id,
            channelId: typeof result.channel_id === 'string' ? result.channel_id : this.channelId,
        });
    }

    _onSettings() {
        if (!this.channelId) return;
        this.openModal('sync.channel_edit', { channelId: this.channelId });
    }

    _onMembers() {
        if (!this.channelId) return;
        this.openModal('sync.channel_members_add', { channelId: this.channelId });
    }

    _onMoreToggle() {
        this._menuOpen = !this._menuOpen;
    }

    _onExpandCall() {
        this._callUi.expandOverlay(null);
    }

    _onHangupCall(e) {
        e.stopPropagation();
        const callUi = this._callUiSel.value;
        if (!callUi || !callUi.activeCall || typeof callUi.activeCall.call_id !== 'string') return;
        if (typeof callUi.bannerHangupGuardUntil === 'number' && Date.now() < callUi.bannerHangupGuardUntil) {
            return;
        }
        this._callHangup.run({ call_id: callUi.activeCall.call_id });
    }

    _onPeerClick(channel) {
        if (!channel || !channel.peer || typeof channel.peer.user_id !== 'string') return;
        this.openModal('platform.user_info', { userId: channel.peer.user_id });
    }

    _renderAvatar(channel) {
        const isDm = channel.type === 'direct' && channel.peer && typeof channel.peer.user_id === 'string';
        if (isDm) {
            const presence = this._presenceSel.value;
            const presenceByUserId = presence && presence.presenceByUserId ? presence.presenceByUserId : null;
            const online = isOnline(presenceByUserId, channel.peer.user_id);
            const name = resolveDisplayName(channel.peer);
            const hue = hueFromString(channel.peer.user_id);
            return html`
                <span class="avatar" style=${`background: hsl(${hue}, 60%, 55%)`} @click=${() => this._onPeerClick(channel)}>
                    ${typeof channel.peer.avatar_url === 'string' && channel.peer.avatar_url !== ''
                        ? html`<img src=${channel.peer.avatar_url} alt="" />`
                        : initialsFromName(name)}
                    ${online ? html`<span class="presence-dot"></span>` : ''}
                </span>
            `;
        }
        const seed = typeof channel.id === 'string' ? channel.id : 'sync';
        const hue = hueFromString(seed);
        const name = typeof channel.name === 'string' && channel.name !== '' ? channel.name : '#';
        return html`
            <span class="avatar" style=${`background: hsl(${hue}, 60%, 55%)`}>
                ${typeof channel.avatar_url === 'string' && channel.avatar_url !== ''
                    ? html`<img src=${channel.avatar_url} alt="" />`
                    : initialsFromName(name)}
            </span>
        `;
    }

    render() {
        const channel = this._channel();
        if (!channel) {
            return html`<div class="text"><div class="title">${this.channelId}</div></div>`;
        }
        const presence = this._presenceSel.value;
        const typingByChannel = presence && presence.typingByChannel ? presence.typingByChannel : null;
        const presenceByUserId = presence && presence.presenceByUserId ? presence.presenceByUserId : null;
        const me = this._authSel.value;
        const myUserId = me && typeof me.user_id === 'string' ? me.user_id : '';
        const callUi = this._callUiSel.value;
        const title = channelDisplayTitle(channel);
        const subtitle = buildChatSubtitle({
            channel,
            typingByChannel,
            presenceByUserId,
            t: (k, vars) => this.t(k, vars),
            myUserId,
            members: this._members.items,
        });
        const isPeerOnline = channel.type === 'direct'
            && channel.peer && typeof channel.peer.user_id === 'string'
            && isOnline(presenceByUserId, channel.peer.user_id);
        const ac = callUi && callUi.activeCall ? callUi.activeCall : null;
        const chId = typeof this.channelId === 'string' ? this.channelId : '';
        const byChannelId = ac && typeof ac.channel_id === 'string' && ac.channel_id === chId;
        const byTracker = ac && chId !== ''
            && callUi.activeCallChannels
            && callUi.activeCallChannels[chId]
            && callUi.activeCallChannels[chId].call_id === ac.call_id;
        const callActiveHere = Boolean(ac && (byChannelId || byTracker));
        this.toggleAttribute('data-call-banner', callActiveHere && callUi && callUi.overlayMinimized);
        const ws = this._wsSel.value;
        const wsConnected = !!(ws && ws.connected === true);
        const wsConnecting = !!(ws && ws.connecting === true);
        return html`
            <button class="menu-btn" @click=${this._onMenuClick} title=${this.t('chat_header.menu')}>
                <platform-icon name="menu" size="20"></platform-icon>
            </button>
            ${callActiveHere && callUi.overlayMinimized ? html`
                <span class="pulse"></span>
            ` : this._renderAvatar(channel)}
            <div class="text" @click=${callActiveHere && callUi.overlayMinimized ? this._onExpandCall : null}>
                <div class="title">${callActiveHere && callUi.overlayMinimized ? this.t('chat_view.call_banner_title') : title}</div>
                ${callActiveHere && callUi.overlayMinimized
                    ? html`<div class="subtitle">${this.t('chat_view.call_banner_subtitle')}</div>`
                    : (subtitle
                        ? html`<div class="subtitle ${isPeerOnline ? 'online' : ''}">${subtitle}</div>`
                        : '')}
            </div>
            <div class="actions">
                ${callActiveHere && callUi.overlayMinimized ? html`
                    <button class="icon-btn" @click=${this._onHangupCall} title=${this.t('chat_view.call_banner_hangup_aria')}>
                        <platform-icon name="phone-off" size="18"></platform-icon>
                    </button>
                ` : html`
                    <button class="icon-btn accent" @click=${this._onInviteCall} ?disabled=${this._callInvite.busy} title=${this.t('chat_header.action_call')}>
                        <platform-icon name="phone" size="20"></platform-icon>
                    </button>
                    <button class="icon-btn accent" @click=${this._onInviteCall} ?disabled=${this._callInvite.busy} title=${this.t('chat_header.action_video_call')}>
                        <platform-icon name="video" size="20"></platform-icon>
                    </button>
                    <span class="actions-divider"></span>
                    <button class="icon-btn" @click=${this._onSettings} title=${this.t('chat_header.action_settings')}>
                        <platform-icon name="settings" size="20"></platform-icon>
                    </button>
                    <button class="icon-btn" @click=${this._onMoreToggle} title=${this.t('chat_view.more_title')}>
                        <platform-icon name="more-vertical" size="20"></platform-icon>
                    </button>
                    ${this._menuOpen ? html`
                        <div class="menu-flyout" @click=${(e) => e.stopPropagation()}>
                            <button @click=${() => { this._menuOpen = false; this._onMembers(); }}>
                                <platform-icon name="users" size="14"></platform-icon>
                                ${this.t('chat_header.action_members')}
                            </button>
                            <button @click=${() => { this._menuOpen = false; this._onSettings(); }}>
                                <platform-icon name="settings" size="14"></platform-icon>
                                ${this.t('chat_header.action_settings')}
                            </button>
                            <div class="ws-row">
                                <span class=${wsConnected ? 'ws-dot connected' : (wsConnecting ? 'ws-dot connecting' : 'ws-dot')}></span>
                                ${wsConnected
                                    ? this.t('chat_header.ws_status_connected')
                                    : (wsConnecting ? this.t('chat_header.ws_status_connecting') : this.t('chat_header.ws_status_disconnected'))}
                            </div>
                        </div>
                    ` : ''}
                `}
            </div>
        `;
    }
}

customElements.define('sync-chat-header', SyncChatHeader);
