/**
 * sync-chat-header — шапка чата и единая шапка экранов Sync:
 *   - `header-mode="channel"` (по умолчанию): аватар, заголовок, подзаголовок, звонок/настройки/⋯
 *     На ширине ≤767px в строке действий только кнопка звонка; видео, участники,
 *     настройки и статус WebSocket — под меню ⋯.
 *   - `header-mode="list"`: тот же ряд (меню, иконка, title/subtitle), без действий канала — список каналов, встречи, настройки
 *   - баннер активного звонка (свёрнутого) — открывает overlay.
 *
 * Источники: useResource('sync/channels'), useResource('sync/company_members'),
 *            select syncPresence (typing), syncCallUi.
 * Действия: openModal('platform.user_info', ...), openModal('sync.channel_edit'),
 *           useOp('sync/calls_invite'), dispatch overlay_expanded.
 */

import type { SyncCallUiSlice, SyncPresenceSlice } from '../events/sync.types.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';
import type { OpController, ResourceController, ControllerFor } from '@platform/lib/base/use-resource.js';
import { html, css } from 'lit';
import type {CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult} from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';
import type { AuthUser } from '@platform/lib/events/reducers/auth.js';
import type { NetworkState } from '@platform/lib/events/reducers/network.js';
import type { ChannelRead } from '@platform/lib/events/wire/sync.gen.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-user-chip.js';
import '@platform/lib/components/platform-spinner.js';
import '@platform/lib/components/platform-empty-state.js';
import { buildChatSubtitle, channelDisplayTitle } from './_helpers/sync-channel-display.js';
import { isOnline, findCompanyMember } from '../_helpers/sync-presence.js';
import { resolveAvatarImageSrc } from '@platform/lib/utils/placeholder-avatar.js';
import { initialsFromName, syncAvatarHueVar } from '../_helpers/sync-hue.js';
import { resolveDisplayName } from '../_helpers/sync-id-resolvers.js';
import { syncChannelPlaceholderCollection } from '../_helpers/sync-channel-placeholder-collection.js';
import { mobileStickyHeaderSyncChatHostStyles } from '@platform/lib/styles/shared/mobile-sticky-header.styles.js';

function isSyncPresenceSlice(value: unknown): value is SyncPresenceSlice {
    return isPlainRecord(value);
}

function isSyncCallUiSlice(value: unknown): value is SyncCallUiSlice {
    return isPlainRecord(value);
}

export class SyncChatHeader extends PlatformElement {
    static override properties: PropertyDeclarations = {
        /**
         * `channel` — шапка диалога (телефон, настройки, …).
         * `list` — те же отступы и меню, без действий канала: список каналов, встречи, настройки.
         */
        headerMode: { type: String, reflect: true, attribute: 'header-mode' },
        listTitle: { type: String, attribute: 'list-title' },
        listSubtitle: { type: String, attribute: 'list-subtitle' },
        channelId: { type: String },
        _menuOpen: { state: true },
        _headerAvatarFailed: { state: true },
        /** Узкий экран: в строке только звонок, остальные действия — под ⋯ */
        _headerMobile: { state: true },
    };
    declare headerMode: string;
    declare listTitle: string;
    declare listSubtitle: string;
    declare channelId: string;
    declare _menuOpen: boolean;
    declare _headerAvatarFailed: boolean;
    declare _headerMobile: boolean;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        css`
        :host {
            display: flex;
            align-items: center;
            gap: var(--space-3);
            padding: var(--space-3) var(--space-6);
            border-bottom: 1px solid var(--glass-border-medium);
            background: var(--glass-solid-subtle);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            min-height: 72px;
            flex-shrink: 0;
            position: relative;
            z-index: 10;
        }
        :host([data-call-banner]) {
            background: var(--accent-gradient);
            color: var(--text-inverse);
        }
        /* Mobile shell 2026: гамбургер удалён, back-кнопка только на мобиле для channel-маршрута */
        .back-btn {
            display: none;
            background: transparent;
            border: none;
            color: var(--text-primary);
            padding: var(--space-2);
            margin-left: calc(var(--space-2) * -1);
            border-radius: var(--radius-full);
            cursor: pointer;
        }
        .back-btn:hover { background: var(--glass-tint-medium); }
        @media (max-width: 767px) {
            .back-btn { display: inline-flex; }
        }
        .avatar {
            width: 44px;
            height: 44px;
            border-radius: 50%;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            color: var(--text-inverse);
            font-weight: var(--font-semibold);
            font-size: var(--text-sm);
            flex-shrink: 0;
            position: relative;
            overflow: hidden;
            background: var(--accent-subtle);
            box-shadow: 0 1px 4px var(--glass-shadow-subtle), inset 0 0 0 1px color-mix(in srgb, var(--text-primary) 8%, transparent);
            cursor: pointer;
            transition: transform var(--motion-duration-micro);
        }
        .avatar.pastel-initials {
            --sync-avatar-h: 0;
            background: hsl(var(--sync-avatar-h), var(--sync-pastel-avatar-s-bg), var(--sync-pastel-avatar-l-bg));
            color: hsl(var(--sync-avatar-h), var(--sync-pastel-avatar-s-fg), var(--sync-pastel-avatar-l-fg));
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
            background: var(--success);
            border: 2px solid var(--bg-elevated);
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
        :host([data-call-banner]) .subtitle { color: var(--text-inverse); }
        :host([data-call-banner]) .subtitle { color: var(--text-on-accent); }
        :host([data-call-banner]) .avatar:not(.pastel-initials) {
            background: color-mix(in srgb, var(--text-on-accent) 22%, transparent);
            box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--text-on-accent) 28%, transparent);
        }
        :host([data-call-banner]) .avatar.pastel-initials {
            background: color-mix(in srgb, var(--text-on-accent) 24%, transparent);
            color: var(--text-inverse);
        }

        .actions {
            display: inline-flex;
            align-items: center;
            gap: var(--space-1);
            position: relative;
        }
        .actions-divider {
            width: 1px;
            height: 24px;
            background: var(--glass-border-medium);
            margin: 0 var(--space-1);
        }
        .icon-btn {
            background: color-mix(in srgb, var(--glass-tint-medium) 35%, transparent);
            border: none;
            color: var(--text-tertiary);
            padding: 10px;
            cursor: pointer;
            border-radius: var(--radius-full);
            display: inline-flex;
            align-items: center;
            justify-content: center;
            transition: background var(--motion-duration-micro), color var(--motion-duration-micro);
        }
        .icon-btn:hover { background: var(--glass-tint-medium); color: var(--text-primary); }
        .icon-btn:focus-visible {
            outline: 2px solid var(--accent);
            outline-offset: 2px;
        }
        .icon-btn.accent:hover {
            background: var(--accent-subtle);
            color: var(--accent);
        }
        :host([data-call-banner]) .icon-btn {
            color: var(--text-inverse);
            background: color-mix(in srgb, var(--text-on-accent) 12%, transparent);
        }
        :host([data-call-banner]) .icon-btn:hover {
            background: color-mix(in srgb, var(--text-on-accent) 22%, transparent);
            color: var(--text-inverse);
        }
        .pulse {
            display: inline-block;
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: var(--glass-tint-strong);
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
            background: var(--glass-solid-medium);
            border: 1px solid var(--glass-border-medium);
            border-radius: var(--radius-md);
            box-shadow: 0 8px 24px var(--glass-shadow-medium);
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
        .menu-flyout button:hover { background: var(--glass-tint-medium); }
        .menu-flyout .ws-row {
            padding: var(--space-2) var(--space-3);
            color: var(--text-secondary);
            font-size: var(--text-xs);
            display: flex;
            align-items: center;
            gap: var(--space-1);
            border-top: 1px solid var(--glass-border-medium);
        }
        .ws-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: var(--text-tertiary);
        }
        .ws-dot.connected { background: var(--success); }
        .ws-dot.connecting { background: var(--warning); }
        .avatar.list-mark {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            color: var(--accent);
            cursor: default;
        }
        .avatar.list-mark platform-icon {
            display: block;
        }
        .overflow-anchor {
            position: relative;
            flex-shrink: 0;
        }
    `,
        mobileStickyHeaderSyncChatHostStyles,
    ];
    private _channels: ControllerFor<'sync/channels'>;
    private _members: ResourceController;
    private _authSel: SelectController<AuthUser | null>;
    private _presenceSel: SelectController<SyncPresenceSlice | undefined>;
    private _callUiSel: SelectController<SyncCallUiSlice | undefined>;
    private _callUi: ControllerFor<'sync/call_ui'>;
    private _wsSel: SelectController<NetworkState>;
    private _callInvite: OpController;
    private _callHangup: OpController;
    private _headerAvatarSig: string;
    private _headerMql: MediaQueryList | null;
    private _onDocClick: (e: Event) => void;
    private _onHeaderMqlChange: () => void;

    constructor() {
        super();
        this.headerMode = 'channel';
        this.listTitle = '';
        this.listSubtitle = '';
        this.channelId = '';
        this._menuOpen = false;
        this._headerMobile =
            typeof window !== 'undefined'
            && typeof window.matchMedia === 'function'
            && window.matchMedia('(max-width: 767px)').matches;
        this._headerAvatarFailed = false;
        this._headerAvatarSig = '';
        this._channels = this.useResource('sync/channels', { autoload: true });
        this._members = this.useResource('sync/company_members');
        this._authSel = this.select((s) => s.auth.user);
        this._presenceSel = this.select((s) => isSyncPresenceSlice(s.syncPresence) ? s.syncPresence : undefined);
        this._callUiSel = this.select((s) => isSyncCallUiSlice(s.syncCallUi) ? s.syncCallUi : undefined);
        this._callUi = this.useSlice('sync/call_ui');
        this._wsSel = this.select((s) => s.network);
        this._callInvite = this.useOp('sync/calls_invite');
        this._callHangup = this.useOp('sync/calls_hangup');
        this._onDocClick = (e: Event) => {
            if (!this._menuOpen) return;
            if (e.composedPath().some((n: EventTarget) => n === this)) return;
            this._menuOpen = false;
        };
        this._onHeaderMqlChange = () => {
            const next =
                typeof window !== 'undefined'
                && typeof window.matchMedia === 'function'
                && window.matchMedia('(max-width: 767px)').matches;
            if (next !== this._headerMobile) {
                this._headerMobile = next;
                if (!next) {
                    this._menuOpen = false;
                }
                this.requestUpdate();
            }
        };
        /** @type {MediaQueryList | null} */
        this._headerMql = null;
    }

    override connectedCallback(): void {
        super.connectedCallback();
        this.useDomEvent(document, 'pointerdown', this._onDocClick);
        if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
            this._headerMql = window.matchMedia('(max-width: 767px)');
            this._headerMql.addEventListener('change', this._onHeaderMqlChange);
            const next = this._headerMql.matches;
            if (next !== this._headerMobile) {
                this._headerMobile = next;
            }
        }
    }

    override disconnectedCallback(): void {
        if (this._headerMql) {
            this._headerMql.removeEventListener('change', this._onHeaderMqlChange);
            this._headerMql = null;
        }
        super.disconnectedCallback();
    }

    override updated(changed: PropertyValues<this>): void {
        super.updated?.(changed);
        const channel = this._channel();
        if (channel) {
            const peer = channel.peer;
            let sig;
            if (channel.type === 'direct' && peer) {
                const au = typeof peer.avatar_url === 'string' ? peer.avatar_url : '';
                sig = `dm:${peer.user_id}|${au}`;
            } else {
                const id = typeof channel.channel_id === 'string' ? channel.channel_id : '';
                const au = typeof channel.avatar_url === 'string' ? channel.avatar_url : '';
                const coll = syncChannelPlaceholderCollection(channel);
                sig = `ch:${id}|${au}|${coll}`;
            }
            if (this._headerAvatarSig !== sig) {
                this._headerAvatarSig = sig;
                this._headerAvatarFailed = false;
            }
        }
    }

    _channel(): ChannelRead | undefined {
        return this._channels.items.find((c) => c.channel_id === this.channelId);
    }

    _onBackClick() {
        if (typeof history !== 'undefined' && history.length > 1) {
            history.back();
            return;
        }
        this.navigate('shell', {});
    }

    _renderListChrome(title: string, subtitle: string) {
        if (typeof title !== 'string' || title === '') {
            throw new Error('sync-chat-header: list chrome title required');
        }
        const sub = typeof subtitle === 'string' && subtitle !== '' ? subtitle : '';
        return html`
            <span class="avatar list-mark" aria-hidden="true">
                <platform-icon name="chat" size="22"></platform-icon>
            </span>
            <div class="text">
                <div class="title">${title}</div>
                ${sub !== '' ? html`<div class="subtitle">${sub}</div>` : ''}
            </div>
            <div class="actions"></div>
        `;
    }

    async _onInviteCall() {
        if (!this.channelId) return;
        await this._callInvite.run({ channel_id: this.channelId });
        const result = this._callInvite.lastResult;
        if (!isPlainRecord(result)) return;
        const callId = result.call_id;
        if (typeof callId !== 'string') return;
        const channelId = result.channel_id;
        const callType = result.call_type;
        const roomName = result.livekit_room_name;
        const livekitUrl = result.livekit_url;
        const resolvedChannelId = typeof channelId === 'string' ? channelId : this.channelId;
        this._callUi.openOverlay({
            call_id: callId,
            channel_id: resolvedChannelId,
            call_type: typeof callType === 'string' ? callType : 'video',
            livekit_room_name: typeof roomName === 'string' ? roomName : null,
            livekit_url: typeof livekitUrl === 'string' ? livekitUrl : null,
        });
        this.openModal('sync.call_overlay', {
            callId,
            channelId: resolvedChannelId,
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

    _onHangupCall(e: Event) {
        e.stopPropagation();
        const callUi = this._callUiSel.value;
        if (!callUi || !callUi.activeCall || typeof callUi.activeCall.call_id !== 'string') return;
        if (typeof callUi.bannerHangupGuardUntil === 'number' && Date.now() < callUi.bannerHangupGuardUntil) {
            return;
        }
        this._callHangup.run({ call_id: callUi.activeCall.call_id });
    }

    _onPeerClick(channel: ChannelRead | null) {
        if (channel === null || !channel.peer) return;
        const userId = channel.peer.user_id;
        if (typeof userId !== 'string') return;
        this.openModal('platform.user_info', { userId });
    }

    _onHeaderAvatarError() {
        this._headerAvatarFailed = true;
    }

    _renderAvatar(channel: ChannelRead) {
        const peer = channel.peer;
        if (channel.type === 'direct' && peer) {
            const member = findCompanyMember(this._members.items, peer.user_id);
            const online = isOnline(member);
            const name = resolveDisplayName(peer);
            const hueVar = syncAvatarHueVar(peer.user_id);
            if (this._headerAvatarFailed) {
                return html`
                    <span class="avatar pastel-initials" style=${hueVar} @click=${() => this._onPeerClick(channel)}>
                        ${initialsFromName(name)}
                        ${online ? html`<span class="presence-dot"></span>` : ''}
                    </span>
                `;
            }
            const peerUrl = typeof peer.avatar_url === 'string' && peer.avatar_url !== ''
                ? peer.avatar_url
                : null;
            const resolved = resolveAvatarImageSrc({ avatarUrl: peerUrl, seed: peer.user_id });
            return html`
                <span class="avatar" @click=${() => this._onPeerClick(channel)}>
                    <img src=${resolved.src} alt="" @error=${this._onHeaderAvatarError} />
                    ${online ? html`<span class="presence-dot"></span>` : ''}
                </span>
            `;
        }
        const seed = typeof channel.channel_id === 'string' ? channel.channel_id : 'sync';
        const hueVar = syncAvatarHueVar(seed);
        const name = typeof channel.name === 'string' && channel.name !== '' ? channel.name : '#';
        if (this._headerAvatarFailed) {
            return html`
                <span class="avatar pastel-initials" style=${hueVar}>
                    ${initialsFromName(name)}
                </span>
            `;
        }
        const chUrl = typeof channel.avatar_url === 'string' && channel.avatar_url !== ''
            ? channel.avatar_url
            : null;
        const resolved = resolveAvatarImageSrc({
            avatarUrl: chUrl,
            seed,
            collection: syncChannelPlaceholderCollection(channel),
        });
        return html`
            <span class="avatar">
                <img src=${resolved.src} alt="" @error=${this._onHeaderAvatarError} />
            </span>
        `;
    }

    override render(): TemplateResult {
        if (this.headerMode === 'list') {
            if (typeof this.listTitle !== 'string' || this.listTitle === '') {
                throw new Error('sync-chat-header: list mode requires listTitle');
            }
            const st =
                typeof this.listSubtitle === 'string' && this.listSubtitle !== '' ? this.listSubtitle : '';
            return this._renderListChrome(this.listTitle, st);
        }
        const channel = this._channel();
        if (!channel) {
            return html`
                <span class="avatar list-mark" aria-hidden="true">
                    <platform-icon name="chat" size="22"></platform-icon>
                </span>
                <div class="text">
                    <platform-empty-state loading></platform-empty-state>
                </div>
                <div class="actions"></div>
            `;
        }
        const presence = this._presenceSel.value;
        const typingByChannel = presence && presence.typingByChannel ? presence.typingByChannel : null;
        const me = this._authSel.value;
        const myUserId = me && typeof me.user_id === 'string' ? me.user_id : '';
        const callUi = this._callUiSel.value;
        const title = channelDisplayTitle(channel);
        const subtitle = buildChatSubtitle({
            channel,
            typingByChannel,
            t: (k, vars) => this.t(k, vars),
            myUserId,
            members: this._members.items,
        });
        const peerUserId = channel.peer?.user_id;
        const isPeerOnline = channel.type === 'direct'
            && peerUserId !== undefined
            && isOnline(findCompanyMember(this._members.items, peerUserId));
        const ac = callUi !== undefined && callUi.activeCall ? callUi.activeCall : null;
        const chId = typeof this.channelId === 'string' ? this.channelId : '';
        const byChannelId = ac !== null && typeof ac.channel_id === 'string' && ac.channel_id === chId;
        const trackerEntry = callUi !== undefined && chId !== '' ? callUi.activeCallChannels[chId] : undefined;
        const byTracker = ac !== null && trackerEntry !== undefined && trackerEntry.call_id === ac.call_id;
        const callActiveHere = ac !== null && callUi !== undefined && (byChannelId || byTracker);
        this.toggleAttribute('data-call-banner', callActiveHere && callUi.overlayMinimized);
        const network = this._wsSel.value;
        const wsConnected = network.ws.status === 'open';
        const wsConnecting = network.ws.status === 'connecting';
        return html`
            <button class="back-btn" @click=${this._onBackClick} title=${this.t('chat_header.back')}>
                <platform-icon name="arrow-left" size="20"></platform-icon>
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
                    <button class="icon-btn" @click=${this._onHangupCall} title=${this.t('chat_view.call_banner_hangup_aria')} aria-label=${this.t('chat_view.call_banner_hangup_aria')}>
                        <platform-icon name="phone-off" size="18"></platform-icon>
                    </button>
                ` : this._headerMobile ? html`
                    <button class="icon-btn accent" @click=${this._onInviteCall} ?disabled=${this._callInvite.busy} title=${this.t('chat_header.action_call')} aria-label=${this.t('chat_header.action_call')}>
                        <platform-icon name="phone" size="20"></platform-icon>
                    </button>
                    <div class="overflow-anchor">
                        <button
                            type="button"
                            class="icon-btn"
                            aria-expanded=${String(this._menuOpen)}
                            aria-haspopup="true"
                            @click=${this._onMoreToggle}
                            title=${this.t('chat_view.more_title')}
                            aria-label=${this.t('chat_view.more_title')}
                        >
                            <platform-icon name="more-vertical" size="20"></platform-icon>
                        </button>
                        ${this._menuOpen ? html`
                            <div class="menu-flyout" @click=${(e: Event) => e.stopPropagation()}>
                                <button type="button" @click=${() => { this._menuOpen = false; void this._onInviteCall(); }}>
                                    <platform-icon name="video" size="14"></platform-icon>
                                    ${this.t('chat_header.action_video_call')}
                                </button>
                                <button type="button" @click=${() => { this._menuOpen = false; this._onMembers(); }}>
                                    <platform-icon name="users" size="14"></platform-icon>
                                    ${this.t('chat_header.action_members')}
                                </button>
                                <button type="button" @click=${() => { this._menuOpen = false; this._onSettings(); }}>
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
                    </div>
                ` : html`
                    <button class="icon-btn accent" @click=${this._onInviteCall} ?disabled=${this._callInvite.busy} title=${this.t('chat_header.action_call')} aria-label=${this.t('chat_header.action_call')}>
                        <platform-icon name="phone" size="20"></platform-icon>
                    </button>
                    <button class="icon-btn accent" @click=${this._onInviteCall} ?disabled=${this._callInvite.busy} title=${this.t('chat_header.action_video_call')} aria-label=${this.t('chat_header.action_video_call')}>
                        <platform-icon name="video" size="20"></platform-icon>
                    </button>
                    <span class="actions-divider"></span>
                    <button class="icon-btn" @click=${this._onSettings} title=${this.t('chat_header.action_settings')} aria-label=${this.t('chat_header.action_settings')}>
                        <platform-icon name="settings" size="20"></platform-icon>
                    </button>
                    <button type="button" class="icon-btn" @click=${this._onMoreToggle} title=${this.t('chat_view.more_title')} aria-label=${this.t('chat_view.more_title')}>
                        <platform-icon name="more-vertical" size="20"></platform-icon>
                    </button>
                    ${this._menuOpen ? html`
                        <div class="menu-flyout" @click=${(e: Event) => e.stopPropagation()}>
                            <button type="button" @click=${() => { this._menuOpen = false; this._onMembers(); }}>
                                <platform-icon name="users" size="14"></platform-icon>
                                ${this.t('chat_header.action_members')}
                            </button>
                            <button type="button" @click=${() => { this._menuOpen = false; this._onSettings(); }}>
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
