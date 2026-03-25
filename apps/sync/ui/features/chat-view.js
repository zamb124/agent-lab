/**
 * ChatView — основной контейнер чата: хедер + список сообщений + composer
 */
import { html, css } from 'lit';
import { classMap } from 'lit/directives/class-map.js';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { glassStyles } from '@platform/lib/styles/shared/glass.styles.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { AppEvents } from '@platform/lib/utils/types.js';
import { SyncStore } from '../store/sync.store.js';
import './channel-picker.js';
import './message-list.js';
import './message-composer.js';
import './thread-drawer.js';
import './sync-channel-row.js';
import '../modals/channel-settings-modal.js';
import '@platform/lib/components/layout/platform-island.js';
import '@platform/lib/components/platform-icon.js';
import { modalShellStyles } from '@platform/lib/platform-element/styles.js';

export class ChatView extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        glassStyles,
        buttonStyles,
        modalShellStyles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                height: 100%;
                min-height: 0;
                overflow: hidden;
                box-sizing: border-box;
            }

            .chat-header {
                display: flex;
                flex-direction: column;
                align-items: stretch;
                gap: 0;
                padding: var(--space-2) var(--space-4);
                border-bottom: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                backdrop-filter: blur(var(--glass-blur-medium));
                flex-shrink: 0;
            }

            .header-body {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-3);
                min-width: 0;
                width: 100%;
            }

            .mobile-menu-btn {
                display: none;
            }

            @media (max-width: 767px) {
                .mobile-menu-btn {
                    display: flex;
                    width: 36px;
                    height: 36px;
                    align-items: center;
                    justify-content: center;
                    border-radius: var(--radius-lg);
                    background: var(--glass-solid-strong);
                    backdrop-filter: blur(var(--glass-blur-medium));
                    border: 1px solid var(--glass-border-medium);
                    color: var(--text-primary);
                    cursor: pointer;
                    flex-shrink: 0;
                    transition: all var(--duration-fast) var(--easing-default);
                    box-shadow: var(--glass-shadow-subtle);
                    padding: 0;
                }

                .mobile-menu-btn:hover {
                    background: var(--glass-solid-medium);
                }

                .mobile-menu-btn.hidden {
                    display: none;
                }

                .chat-header {
                    padding: var(--space-1) var(--space-2);
                }

                .header-channel-hit,
                .header-channel-static {
                    padding: var(--space-1) var(--space-2);
                }

                .header-entity-img,
                .header-entity-initials,
                .header-icon-fallback {
                    width: 32px;
                    height: 32px;
                }
            }

            .chat-header--compact .header-channel-static .header-channel-text,
            .chat-header--compact .header-channel-hit .header-channel-text {
                display: flex;
                flex-direction: column;
                align-items: stretch;
                justify-content: center;
                gap: 0;
                min-width: 0;
            }

            .chat-header--compact .header-title {
                min-width: 0;
                max-width: 100%;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            .chat-header--compact .header-subtitle {
                min-width: 0;
                max-width: 100%;
                margin-top: 1px;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            .header-channel-wrap {
                flex: 1 1 auto;
                min-width: 0;
                display: flex;
                align-items: center;
            }

            .header-leading {
                flex-shrink: 0;
                display: flex;
                align-items: center;
                justify-content: center;
            }

            .header-entity-img {
                width: 40px;
                height: 40px;
                border-radius: 50%;
                object-fit: cover;
                flex-shrink: 0;
            }

            .header-entity-initials {
                width: 40px;
                height: 40px;
                border-radius: 50%;
                flex-shrink: 0;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: #fff;
            }

            .header-icon-fallback {
                width: 40px;
                height: 40px;
                border-radius: var(--radius-lg);
                flex-shrink: 0;
                display: flex;
                align-items: center;
                justify-content: center;
                background: var(--glass-solid-medium);
                color: var(--accent);
                border: 1px solid var(--glass-border-subtle);
            }

            .header-channel-hit {
                width: 100%;
                flex: 1 1 auto;
                min-width: 0;
                display: flex;
                align-items: center;
                justify-content: flex-start;
                gap: var(--space-3);
                padding: var(--space-2) var(--space-3);
                margin: 0;
                border: none;
                border-radius: var(--radius-lg);
                background: transparent;
                cursor: pointer;
                font: inherit;
                color: inherit;
                text-align: left;
                -webkit-tap-highlight-color: transparent;
            }

            .header-channel-hit:hover {
                background: var(--glass-solid-medium);
            }

            .header-channel-hit:focus-visible {
                outline: 2px solid var(--accent);
                outline-offset: 2px;
            }

            .header-channel-text {
                min-width: 0;
                flex: 1 1 auto;
            }

            .header-settings-ic {
                flex-shrink: 0;
                color: var(--text-tertiary);
                opacity: 0.9;
            }

            .header-channel-hit:hover .header-settings-ic {
                color: var(--accent);
            }

            .header-channel-static {
                width: 100%;
                flex: 1 1 auto;
                min-width: 0;
                padding: var(--space-2) var(--space-3);
                display: flex;
                flex-direction: row;
                align-items: center;
                gap: var(--space-3);
            }

            .header-channel-static .header-channel-text {
                min-width: 0;
                flex: 1 1 auto;
                display: flex;
                flex-direction: column;
                justify-content: center;
            }

            .header-title {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }

            .header-subtitle {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-top: 2px;
            }

            .header-subtitle.is-typing {
                color: var(--accent);
            }

            .header-actions {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                flex-shrink: 0;
            }

            .header-more-wrap {
                position: relative;
            }

            .header-more-menu {
                position: absolute;
                top: calc(100% + var(--space-1));
                right: 0;
                min-width: 200px;
                padding: var(--space-2);
                border-radius: var(--radius-lg);
                border: 1px solid var(--glass-border-medium);
                background: var(--glass-solid-strong);
                backdrop-filter: blur(var(--glass-blur-medium));
                box-shadow: var(--glass-shadow-subtle);
                z-index: 80;
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }

            .header-more-menu-status {
                display: flex;
                align-items: center;
                justify-content: flex-start;
                padding: 0 var(--space-1);
            }

            .header-more-item {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                width: 100%;
                margin: 0;
                padding: var(--space-2) var(--space-3);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-solid-subtle);
                color: var(--text-primary);
                font: inherit;
                font-size: var(--text-xs);
                cursor: pointer;
                text-align: left;
                transition: background var(--duration-fast);
            }

            .header-more-item:hover:not(:disabled) {
                background: var(--glass-solid-medium);
            }

            .header-more-item:disabled {
                opacity: 0.4;
                cursor: not-allowed;
            }

            .icon-btn {
                background: transparent;
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                color: var(--text-secondary);
                cursor: pointer;
                padding: var(--space-2);
                transition: all var(--duration-fast);
                display: flex;
                align-items: center;
            }

            .icon-btn:hover {
                background: var(--glass-solid-subtle);
                color: var(--text-primary);
            }

            .icon-btn:disabled {
                opacity: 0.4;
                cursor: not-allowed;
            }

            .back-btn {
                background: transparent;
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                color: var(--text-secondary);
                cursor: pointer;
                padding: var(--space-2) var(--space-3);
                font-size: var(--text-xs);
                display: flex;
                align-items: center;
                gap: var(--space-2);
                transition: all var(--duration-fast);
            }

            .back-btn:hover {
                background: var(--glass-solid-subtle);
                color: var(--text-primary);
            }

            .content {
                flex: 1 1 auto;
                min-height: 0;
                overflow: hidden;
                display: flex;
                flex-direction: column;
            }

            .ws-badge {
                font-size: 10px;
                padding: 2px 8px;
                border-radius: var(--radius-full);
                border: 1px solid;
            }

            .ws-badge.open {
                background: rgba(16, 185, 129, 0.1);
                border-color: rgba(16, 185, 129, 0.4);
                color: rgb(16, 185, 129);
            }

            .ws-badge.connecting {
                background: rgba(245, 158, 11, 0.1);
                border-color: rgba(245, 158, 11, 0.4);
                color: rgb(245, 158, 11);
            }

            .ws-badge.closed {
                background: rgba(239, 68, 68, 0.1);
                border-color: rgba(239, 68, 68, 0.4);
                color: rgb(239, 68, 68);
            }

            .pin-strip {
                flex-shrink: 0;
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-4);
                border-bottom: 1px solid var(--glass-border-subtle);
                background: rgba(245, 158, 11, 0.08);
                cursor: pointer;
                font-size: var(--text-xs);
                color: var(--text-secondary);
            }

            .pin-strip:hover {
                background: rgba(245, 158, 11, 0.14);
            }

            .selection-bar {
                flex-shrink: 0;
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-3);
                padding: var(--space-2) var(--space-4);
                border-bottom: 1px solid rgba(244, 114, 182, 0.35);
                background: rgba(244, 114, 182, 0.14);
                font-size: var(--text-xs);
            }

            .selection-actions {
                display: flex;
                gap: var(--space-2);
            }

            .modal-overlay {
                position: fixed;
                inset: 0;
                z-index: 300;
                background: rgba(0, 0, 0, 0.45);
                display: flex;
                align-items: center;
                justify-content: center;
                padding: var(--space-4);
            }

            .modal-box {
                width: min(420px, 100%);
                border-radius: var(--radius-xl);
                border: 1px solid var(--glass-border-medium);
                background: var(--glass-solid-strong);
                padding: var(--space-4);
                max-height: 70vh;
                overflow: auto;
            }

            .modal-title {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                margin-bottom: var(--space-3);
            }

            .forward-channel-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
                max-height: min(48vh, 360px);
                overflow-y: auto;
                padding-right: var(--space-1);
                margin-bottom: var(--space-2);
            }
        `
    ];

    static properties = {
        _chat: { state: true },
        _channels: { state: true },
        _spaces: { state: true },
        _wsState: { state: true },
        _threadIds: { state: true },
        _ui: { state: true },
        _isMobile: { state: true },
        _typingSubtitle: { state: true },
        _peerPresenceByUserId: { state: true },
        _typingPeersByChannel: { state: true },
        _headerMoreOpen: { state: true },
    };

    constructor() {
        super();
        const s = SyncStore.state;
        this._chat = s.chat;
        this._channels = s.channels;
        this._spaces = s.spaces;
        this._wsState = s.ws.state;
        this._threadIds = [];
        this._ui = SyncStore.state.ui;
        this._isMobile = false;
        this._headerMoreOpen = false;
        this._resizeObserver = null;
        this._typingSubtitle = '';
        this._peerPresenceByUserId = s.peerPresenceByUserId ?? {};
        this._typingPeersByChannel = s.typingPeersByChannel ?? {};
        this._boundAuthChange = () => {
            this._syncTypingSubtitleFromStore();
        };
        this._boundDocPointerHeaderMore = this._onDocPointerDownHeaderMore.bind(this);
        this._boundWindowResize = () => this._checkMobileViewport();
    }

    connectedCallback() {
        super.connectedCallback();
        document.addEventListener('pointerdown', this._boundDocPointerHeaderMore, true);
        window.addEventListener('resize', this._boundWindowResize);
        this._checkMobileViewport();
        this._resizeObserver = new ResizeObserver(() => this._checkMobileViewport());
        this._resizeObserver.observe(document.body);
        window.addEventListener(AppEvents.AUTH_CHANGE, this._boundAuthChange);
        this._unsubscribe = SyncStore.subscribe(state => {
            this._chat = state.chat;
            this._channels = state.channels;
            this._spaces = state.spaces;
            this._wsState = state.ws.state;
            this._threadIds = SyncStore.getThreadIds();
            this._ui = state.ui;
            this._peerPresenceByUserId = state.peerPresenceByUserId ?? {};
            this._typingPeersByChannel = state.typingPeersByChannel ?? {};
            this._syncTypingSubtitleFromStore();
        });
        this._syncTypingSubtitleFromStore();
    }

    disconnectedCallback() {
        super.disconnectedCallback?.();
        document.removeEventListener('pointerdown', this._boundDocPointerHeaderMore, true);
        window.removeEventListener('resize', this._boundWindowResize);
        window.removeEventListener(AppEvents.AUTH_CHANGE, this._boundAuthChange);
        this._resizeObserver?.disconnect();
        this._resizeObserver = null;
        this._unsubscribe?.();
    }

    _syncTypingSubtitleFromStore() {
        const state = SyncStore.state;
        const sel = state.chat.selectedChannelId;
        const myId = this.auth?.user?.id;
        if (!sel || typeof myId !== 'string' || myId === '') {
            this._typingSubtitle = '';
            return;
        }
        this._typingSubtitle = SyncStore.getTypingIndicatorLine(
            sel,
            state.chat.focusedThreadId ?? null,
            myId,
        );
    }

    _checkMobileViewport() {
        this._isMobile = window.innerWidth <= 767;
    }

    updated(changedProperties) {
        super.updated(changedProperties);
        if (changedProperties.has('_isMobile') && !this._isMobile && this._headerMoreOpen) {
            this._headerMoreOpen = false;
        }
    }

    /**
     * @param {PointerEvent} e
     */
    _onDocPointerDownHeaderMore(e) {
        if (!this._headerMoreOpen) {
            return;
        }
        const wrap = this.renderRoot?.querySelector('.header-more-wrap');
        if (wrap && e.composedPath().includes(wrap)) {
            return;
        }
        this._headerMoreOpen = false;
    }

    /**
     * @param {Event} e
     */
    _toggleHeaderMoreMenu(e) {
        e.stopPropagation();
        this._headerMoreOpen = !this._headerMoreOpen;
    }

    _closeHeaderMoreMenu() {
        this._headerMoreOpen = false;
    }

    _openMobileSidebar() {
        window.dispatchEvent(new CustomEvent('platform-sidebar-open', {
            bubbles: true,
            composed: true,
        }));
    }

    _selectedChannel() {
        const { selectedChannelId } = this._chat;
        if (!selectedChannelId) return null;
        return this._channels.list.find(c => c.id === selectedChannelId) ?? null;
    }

    _getTitle() {
        const { focusedThreadId, selectedChannelId } = this._chat;
        if (focusedThreadId) return 'Тред';
        if (!selectedChannelId) return 'Выбери канал';
        const ch = this._selectedChannel();
        if (!ch) return selectedChannelId;
        if (SyncStore.isHiddenSyncChannelName(ch.name)) {
            return 'Встреча';
        }
        if (ch.type === 'direct' && ch.peer && typeof ch.peer.display_name === 'string') {
            return ch.peer.display_name;
        }
        return ch.name ?? selectedChannelId;
    }

    _getSubtitle() {
        const { focusedThreadId } = this._chat;
        const ch = this._selectedChannel();
        if (!ch) return '';
        const chLabel = ch.type === 'direct' && ch.peer?.display_name
            ? ch.peer.display_name
            : (ch.name ?? ch.id);
        if (focusedThreadId) return `Канал: ${chLabel} • thread_id: ${focusedThreadId}`;
        if (ch.type === 'direct' && ch.peer && typeof ch.peer.user_id === 'string' && ch.peer.user_id !== '') {
            return SyncStore.getPeerPresenceSubtitle(ch.peer.user_id);
        }
        return ch.type ?? '';
    }

    _hueFromString(value) {
        const s = typeof value === 'string' ? value : String(value ?? '');
        let h = 0;
        for (let i = 0; i < s.length; i++) {
            h = (h * 31 + s.charCodeAt(i)) >>> 0;
        }
        return h % 360;
    }

    _resolvedSpace(channel) {
        if (!channel?.space_id) {
            return null;
        }
        const sid = channel.space_id;
        return this._spaces.list.find(sp => sp.id === sid) ?? null;
    }

    /**
     * Слева в шапке: собеседник (direct), аватар канала/пространства или запасная иконка.
     */
    _headerLeadingGraphic(channel) {
        if (!channel) {
            return html``;
        }
        if (channel.type === 'direct' && channel.peer) {
            const p = channel.peer;
            if (typeof p.avatar_url === 'string' && p.avatar_url !== '') {
                return html`<img class="header-entity-img" src=${p.avatar_url} alt="" />`;
            }
            const label = typeof p.display_name === 'string' ? p.display_name : p.user_id;
            const initial = (label.trim().slice(0, 1) || '?').toUpperCase();
            const hue = this._hueFromString(p.user_id);
            return html`
                <span class="header-entity-initials" style=${`background:hsl(${hue} 48% 42%)`}>${initial}</span>
            `;
        }
        const chUrl = typeof channel.avatar_url === 'string' && channel.avatar_url !== ''
            ? channel.avatar_url
            : null;
        if (chUrl) {
            return html`<img class="header-entity-img" src=${chUrl} alt="" />`;
        }
        const space = this._resolvedSpace(channel);
        const spaceUrl = space && typeof space.avatar_url === 'string' && space.avatar_url !== ''
            ? space.avatar_url
            : null;
        if (spaceUrl) {
            return html`<img class="header-entity-img" src=${spaceUrl} alt="" />`;
        }
        if (channel.space_id && space) {
            return html`
                <div class="header-icon-fallback" aria-hidden="true">
                    <platform-icon name="folder" size="22"></platform-icon>
                </div>
            `;
        }
        const label = typeof channel.name === 'string' ? channel.name : channel.id;
        const initial = (label.trim().slice(0, 1) || '?').toUpperCase();
        const hue = this._hueFromString(channel.id);
        return html`
            <span class="header-entity-initials" style=${`background:hsl(${hue} 48% 42%)`}>${initial}</span>
        `;
    }

    _messageListEl() {
        return this.shadowRoot?.querySelector('message-list');
    }

    _onPinStripClick() {
        const ch = this._selectedChannel();
        const ids = ch?.pinned_message_ids;
        if (!Array.isArray(ids) || ids.length === 0) return;
        const i = this._chat.pinnedNavigateIndex % ids.length;
        const targetId = ids[i];
        SyncStore.setPinnedNavigateIndex((i + 1) % ids.length);
        this.updateComplete.then(() => {
            const ml = this._messageListEl();
            if (!ml) {
                throw new Error('message-list не найден.');
            }
            ml.scrollToMessageId(targetId);
            SyncStore.flashMessageHighlight(targetId);
        }).catch((err) => {
            const text = err instanceof Error ? err.message : String(err);
            this.error(text);
        });
    }

    async _deleteSelected() {
        const syncApi = this.services.get('syncApi');
        const channelId = this._chat.selectedChannelId;
        if (!channelId) throw new Error('Канал не выбран.');
        const ids = this._ui.selectedMessageIds;
        for (const mid of ids) {
            await syncApi.deleteMessage(channelId, mid);
        }
        SyncStore.clearMessageSelection();
        SyncStore.setSelectionMode(false);
        await SyncStore.loadMessages(syncApi, channelId);
    }

    async _forwardSelectedToChannel(toChannelId) {
        const syncApi = this.services.get('syncApi');
        const fromId = this._chat.selectedChannelId;
        if (!fromId) throw new Error('Канал не выбран.');
        const ids = this._ui.selectedMessageIds;
        for (const mid of ids) {
            await syncApi.forwardMessage(fromId, mid, toChannelId, null);
        }
        SyncStore.clearMessageSelection();
        SyncStore.setSelectionMode(false);
        SyncStore.setForwardModal(false, null);
        await SyncStore.loadMessages(syncApi, fromId);
    }

    _openChannelSettings() {
        const ch = this._selectedChannel();
        if (!ch || ch.type === 'direct' || this._chat.focusedThreadId) {
            return;
        }
        SyncStore.openChannelSettings(ch.id);
    }

    async _forwardModalPick(toChannelId) {
        const syncApi = this.services.get('syncApi');
        const fwd = this._ui.forwardMessage;
        const fromId = this._chat.selectedChannelId;
        if (!fwd?.id || !fromId) throw new Error('Нет сообщения для пересылки.');
        await syncApi.forwardMessage(fromId, fwd.id, toChannelId, null);
        SyncStore.setForwardModal(false, null);
        await SyncStore.loadMessages(syncApi, fromId);
    }

    _newMeetChannelName() {
        const raw = typeof crypto.randomUUID === 'function'
            ? crypto.randomUUID().replace(/-/g, '')
            : `${Date.now().toString(16)}${Math.random().toString(16).slice(2)}`;
        return `_meet_${raw.slice(0, 20)}`;
    }

    _startCallWithChannel(channelId) {
        if (typeof channelId !== 'string' || channelId === '') return;
        const ws = this.services.get('syncWs');
        if (!ws) return;
        const id = typeof crypto.randomUUID === 'function'
            ? crypto.randomUUID()
            : ([1e7]+-1e3+-4e3+-8e3+-1e11).replace(/[018]/g, c =>
                (c ^ (Math.random() * 16 >> c / 4)).toString(16));
        ws.sendJson({
            id,
            type: 'call.invite',
            payload: { channel_id: channelId, call_type: 'video' },
        });
    }

    _startCall() {
        const channelId = this._chat.selectedChannelId;
        if (!channelId) return;
        this._startCallWithChannel(channelId);
    }

    async _startAdHocCall() {
        const syncApi = this.services.get('syncApi');
        if (!syncApi) return;
        let spaceId = this._chat.selectedSpaceId;
        if (typeof spaceId !== 'string' || spaceId === '') {
            const first = this._spaces.list[0];
            if (!first?.id) {
                this.error('Создайте пространство в сайдбаре, чтобы начать встречу.');
                return;
            }
            spaceId = first.id;
        }
        const name = this._newMeetChannelName();
        try {
            const created = await syncApi.createChannel(spaceId, name);
            await SyncStore.loadChannels(syncApi);
            SyncStore.sanitizeChatSelectionAfterLoad();
            await SyncStore.selectChannelAndLoadMessages(syncApi, spaceId, created.id);
            this._startCallWithChannel(created.id);
        } catch (err) {
            const text = err instanceof Error ? err.message : String(err);
            this.error(text);
        }
    }

    render() {
        const { selectedChannelId, focusedThreadId } = this._chat;
        const selectedChannel = this._selectedChannel();
        const pins = selectedChannel?.pinned_message_ids;
        const pinCount = Array.isArray(pins) ? pins.length : 0;
        const selMode = this._ui.selectionMode;
        const selIds = this._ui.selectedMessageIds;
        const fwdOpen = this._ui.forwardModalOpen;
        const forwardDestinations = typeof selectedChannelId === 'string' && selectedChannelId !== ''
            ? SyncStore.getForwardDestinationChannels(selectedChannelId)
            : [];

        const showChannelSettings = Boolean(
            selectedChannel
            && selectedChannel.type !== 'direct'
            && !focusedThreadId
            && !SyncStore.isHiddenSyncChannelName(selectedChannel.name),
        );

        const channelSettingsCreate = this._ui.channelSettingsCreate;
        const settingsChannelId = this._ui.channelSettingsChannelId;
        const settingsChannel = typeof settingsChannelId === 'string' && settingsChannelId !== ''
            ? this._channels.list.find(c => c.id === settingsChannelId) ?? null
            : null;
        const createSpaceId = this._ui.channelSettingsCreateSpaceId;
        const channelCreateDraft = channelSettingsCreate
            ? {
                id: null,
                type: 'topic',
                space_id: typeof createSpaceId === 'string' && createSpaceId !== ''
                    ? createSpaceId
                    : null,
                name: '',
                avatar_url: null,
            }
            : null;
        const channelForModal = channelSettingsCreate ? channelCreateDraft : settingsChannel;
        const channelModalOpen = channelSettingsCreate || settingsChannel !== null;

        const typingLine = this._typingSubtitle;
        const subtitleFallback = this._getSubtitle();
        const headerSubtitleText = typingLine || subtitleFallback;
        const showHeaderSubtitle = typeof headerSubtitleText === 'string' && headerSubtitleText !== '';

        const headerLead = selectedChannel
            ? html`<div class="header-leading">${this._headerLeadingGraphic(selectedChannel)}</div>`
            : html``;

        const showMobileMenuBtn = this._isMobile && !this._ui.mobileSidebarOpen;
        const channelBlock = showChannelSettings ? html`
                    <button
                        type="button"
                        class="header-channel-hit"
                        title="Настройки канала"
                        @click=${this._openChannelSettings}
                    >
                        ${headerLead}
                        <div class="header-channel-text">
                            <div class="header-title">${this._getTitle()}</div>
                            ${showHeaderSubtitle ? html`
                                <div class="header-subtitle ${typingLine ? 'is-typing' : ''}">${headerSubtitleText}</div>
                            ` : ''}
                        </div>
                        <platform-icon class="header-settings-ic" name="settings" size="20"></platform-icon>
                    </button>
                ` : html`
                    <div class="header-channel-static">
                        ${headerLead}
                        <div class="header-channel-text">
                            <div class="header-title">${this._getTitle()}</div>
                            ${showHeaderSubtitle ? html`
                                <div class="header-subtitle ${typingLine ? 'is-typing' : ''}">${headerSubtitleText}</div>
                            ` : ''}
                        </div>
                    </div>
                `;

        return html`
            <div class=${classMap({ 'chat-header': true, 'chat-header--compact': this._isMobile })}>
                <div class="header-body">
                    <button
                        type="button"
                        class=${classMap({ 'mobile-menu-btn': true, hidden: !showMobileMenuBtn })}
                        title="Открыть меню"
                        aria-label="Открыть меню"
                        @click=${this._openMobileSidebar}
                    >
                        <platform-icon name="hamburger" size="20"></platform-icon>
                    </button>
                    <div class="header-channel-wrap">
                        ${channelBlock}
                    </div>
                    <div class="header-actions">
                        ${this._isMobile ? html`
                            <div class="header-more-wrap">
                                <button
                                    type="button"
                                    class="icon-btn header-more-trigger"
                                    title="Ещё"
                                    aria-label="Дополнительные действия"
                                    aria-expanded=${this._headerMoreOpen ? 'true' : 'false'}
                                    aria-haspopup="true"
                                    @click=${this._toggleHeaderMoreMenu}
                                >
                                    <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                                        <circle cx="5" cy="12" r="2"/>
                                        <circle cx="12" cy="12" r="2"/>
                                        <circle cx="19" cy="12" r="2"/>
                                    </svg>
                                </button>
                                ${this._headerMoreOpen ? html`
                                    <div class="header-more-menu" @pointerdown=${(e) => e.stopPropagation()}>
                                        <div class="header-more-menu-status">
                                            <span class="ws-badge ${this._wsState}">${this._wsState}</span>
                                        </div>
                                        ${selectedChannelId ? html`
                                            <button
                                                type="button"
                                                class="header-more-item"
                                                @click=${() => {
        this._closeHeaderMoreMenu();
        this._startCall();
    }}
                                            >
                                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                                                    <polygon points="23 7 16 12 23 17 23 7"/>
                                                    <rect x="1" y="5" width="15" height="14" rx="2" ry="2"/>
                                                </svg>
                                                <span>Звонок</span>
                                            </button>
                                        ` : html`
                                            <button
                                                type="button"
                                                class="header-more-item"
                                                @click=${async () => {
        this._closeHeaderMoreMenu();
        await this._startAdHocCall();
    }}
                                            >
                                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                                                    <polygon points="23 7 16 12 23 17 23 7"/>
                                                    <rect x="1" y="5" width="15" height="14" rx="2" ry="2"/>
                                                </svg>
                                                <span>Встреча в новом канале</span>
                                            </button>
                                        `}
                                        ${focusedThreadId ? html`
                                            <button
                                                type="button"
                                                class="header-more-item"
                                                @click=${() => {
        this._closeHeaderMoreMenu();
        SyncStore.setFocusedThread(null);
    }}
                                            >
                                                <platform-icon name="chevron-left" size="16"></platform-icon>
                                                <span>Назад</span>
                                            </button>
                                        ` : html`
                                            <button
                                                type="button"
                                                class="header-more-item"
                                                ?disabled=${!selectedChannelId}
                                                @click=${() => {
        this._closeHeaderMoreMenu();
        SyncStore.setThreadDrawerOpen(true);
    }}
                                            >
                                                <platform-icon name="list" size="16"></platform-icon>
                                                <span>Треды</span>
                                            </button>
                                        `}
                                    </div>
                                ` : ''}
                            </div>
                        ` : html`
                            <span class="ws-badge ${this._wsState}">${this._wsState}</span>

                            ${selectedChannelId ? html`
                            <button type="button" class="icon-btn" title="Звонок" @click=${this._startCall}>
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                    <polygon points="23 7 16 12 23 17 23 7"/>
                                    <rect x="1" y="5" width="15" height="14" rx="2" ry="2"/>
                                </svg>
                            </button>
                        ` : html`
                            <button type="button" class="icon-btn" title="Встреча в новом канале" @click=${this._startAdHocCall}>
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                    <polygon points="23 7 16 12 23 17 23 7"/>
                                    <rect x="1" y="5" width="15" height="14" rx="2" ry="2"/>
                                </svg>
                            </button>
                        `}

                            ${focusedThreadId ? html`
                            <button type="button" class="back-btn" @click=${() => SyncStore.setFocusedThread(null)}>
                                <platform-icon name="chevron-left" size="14"></platform-icon>
                                Назад
                            </button>
                        ` : html`
                            <button
                                type="button"
                                class="icon-btn"
                                title="Треды"
                                ?disabled=${!selectedChannelId}
                                @click=${() => SyncStore.setThreadDrawerOpen(true)}
                            >
                                <platform-icon name="list" size="16"></platform-icon>
                            </button>
                        `}
                        `}
                    </div>
                </div>
            </div>

            <div class="content">
                ${!selectedChannelId ? html`
                    <channel-picker></channel-picker>
                ` : html`
                    ${pinCount > 0 && !focusedThreadId ? html`
                        <div class="pin-strip" @click=${this._onPinStripClick} title="Перейти к закреплённому">
                            <platform-icon name="target" size="14"></platform-icon>
                            <span>Закреплённые сообщения (${pinCount}) — нажмите для перехода по кругу</span>
                        </div>
                    ` : ''}
                    ${selMode ? html`
                        <div class="selection-bar">
                            <span>Выбрано: ${selIds.length}</span>
                            <div class="selection-actions">
                                <button type="button" class="back-btn" @click=${() => {
        SyncStore.setSelectionMode(false);
    }}>Отмена</button>
                                <button
                                    type="button"
                                    class="back-btn"
                                    ?disabled=${selIds.length === 0}
                                    @click=${() => SyncStore.setForwardModal(true, null)}
                                >Переслать</button>
                                <button
                                    type="button"
                                    class="back-btn"
                                    ?disabled=${selIds.length === 0}
                                    @click=${this._deleteSelected}
                                >Удалить</button>
                            </div>
                        </div>
                    ` : ''}
                    <message-list .channelId=${selectedChannelId}></message-list>
                    <message-composer .channelId=${selectedChannelId}></message-composer>
                `}
            </div>

            ${fwdOpen ? html`
                <div class="modal-overlay" @click=${(e) => {
        if (e.target === e.currentTarget) SyncStore.setForwardModal(false, null);
    }}>
                    <div class="modal-box" @click=${(e) => e.stopPropagation()}>
                        <div class="modal-title">Куда переслать</div>
                        ${forwardDestinations.length === 0 ? html`<p class="header-subtitle">Нет других каналов.</p>` : ''}
                        <div class="forward-channel-list">
                            ${forwardDestinations.map(c => html`
                            <sync-channel-row
                                .channel=${c}
                                @click=${() => {
        const one = this._ui.forwardMessage;
        if (one?.id) {
            this._forwardModalPick(c.id);
        } else if (this._ui.selectedMessageIds.length > 0) {
            this._forwardSelectedToChannel(c.id);
        } else {
            SyncStore.setForwardModal(false, null);
        }
    }}
                            ></sync-channel-row>
                        `)}
                        </div>
                        <button type="button" class="back-btn" style="margin-top:var(--space-3)" @click=${() => SyncStore.setForwardModal(false, null)}>Закрыть</button>
                    </div>
                </div>
            ` : ''}

            <thread-drawer></thread-drawer>

            <channel-settings-modal
                .open=${channelModalOpen}
                .channel=${channelForModal}
                .createMode=${channelSettingsCreate}
                @close=${() => SyncStore.closeChannelSettings()}
            ></channel-settings-modal>
        `;
    }
}

customElements.define('chat-view', ChatView);
