/**
 * ChatView — основной контейнер чата: хедер + список сообщений + composer
 */
import { html, css } from 'lit';
import { classMap } from 'lit/directives/class-map.js';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { glassStyles } from '@platform/lib/styles/shared/glass.styles.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { AppEvents } from '@platform/lib/utils/types.js';
import { createAvatarRetry } from '@platform/lib/utils/avatar-retry.js';
import { SyncStore } from '../store/sync.store.js';
import { hueFromString } from '../utils/sync-hue.js';
import { mentionDisplayLabel } from '../utils/sync-mention-text.js';
import '../modals/user-info-modal.js';
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

            @media (max-width: 767px) {
                :host {
                    padding-left: 0;
                    padding-right: 0;
                }
            }

            .chat-header {
                position: relative;
                z-index: 120;
                display: flex;
                flex-direction: column;
                align-items: stretch;
                gap: 0;
                padding: var(--space-2) var(--space-4);
                border-bottom: 1px solid var(--glass-border-medium);
                background: var(--glass-solid-subtle);
                backdrop-filter: blur(var(--sync-header-blur));
                -webkit-backdrop-filter: blur(var(--sync-header-blur));
                box-shadow: var(--glass-shadow-subtle);
                flex-shrink: 0;
            }

            .header-body {
                display: flex;
                align-items: center;
                justify-content: flex-start;
                gap: var(--space-3);
                min-width: 0;
                width: 100%;
            }

            .header-main-tray {
                flex: 1 1 0;
                min-width: 0;
                display: flex;
                align-items: center;
                gap: var(--space-2);
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
                    padding: max(var(--space-1), env(safe-area-inset-top, 0px)) var(--space-2)
                        var(--space-1);
                }

                .header-channel-hit,
                .header-channel-static {
                    padding: var(--space-1) var(--space-2);
                }

                .header-entity-img,
                .header-entity-initials,
                .header-peer-hit {
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
                flex: 1 1 0;
                min-width: 0;
                display: flex;
                align-items: center;
            }

            .header-call-banner--integrated {
                flex: 1 1 0;
                min-width: 0;
                box-sizing: border-box;
                display: flex;
                flex-direction: row;
                align-items: center;
                gap: var(--space-2);
                padding: 8px 10px 8px 12px;
                border-radius: var(--radius-lg);
                border: 1px solid rgba(255, 255, 255, 0.22);
                background: var(--accent-gradient);
                box-shadow:
                    0 4px 18px rgba(153, 166, 249, 0.32),
                    inset 0 1px 0 rgba(255, 255, 255, 0.2);
                color: rgba(255, 255, 255, 0.98);
            }

            :host-context([data-theme="light"]) .header-call-banner--integrated {
                border-color: rgba(255, 255, 255, 0.35);
                box-shadow:
                    0 4px 16px rgba(153, 166, 249, 0.22),
                    inset 0 1px 0 rgba(255, 255, 255, 0.35);
            }

            @media (min-width: 768px) {
                .header-call-banner--integrated {
                    border-radius: var(--radius-lg);
                }
            }

            @media (max-width: 767px) {
                .header-call-banner--integrated {
                    border-radius: var(--radius-lg) 0 0 var(--radius-lg);
                    padding-right: max(10px, env(safe-area-inset-right, 0px));
                }
            }

            .header-call-banner-hit {
                flex: 1 1 0;
                min-width: 0;
                display: flex;
                flex-direction: row;
                align-items: center;
                gap: 12px;
                padding: 0;
                margin: 0;
                border: none;
                background: transparent;
                color: inherit;
                font: inherit;
                text-align: left;
                cursor: pointer;
                -webkit-tap-highlight-color: transparent;
                position: relative;
                z-index: 0;
            }

            .header-call-banner-hit:hover {
                filter: brightness(1.06);
            }

            .header-call-banner-hit:focus-visible {
                outline: 2px solid rgba(255, 255, 255, 0.85);
                outline-offset: 2px;
                border-radius: var(--radius-md);
            }

            .header-call-banner-toolbar {
                display: flex;
                flex-shrink: 0;
                align-items: center;
                gap: 6px;
                position: relative;
                z-index: 2;
            }

            .header-call-banner-ws.ws-badge.open {
                background: rgba(255, 255, 255, 0.18);
                border-color: rgba(255, 255, 255, 0.45);
                color: #fff;
            }

            .header-call-banner-ws.ws-badge.connecting {
                background: rgba(253, 224, 71, 0.22);
                border-color: rgba(253, 224, 71, 0.5);
                color: #fffbeb;
            }

            .header-call-banner-ws.ws-badge.closed {
                background: rgba(248, 113, 113, 0.28);
                border-color: rgba(252, 165, 165, 0.5);
                color: #fff;
            }

            .header-call-banner-icon-btn {
                display: inline-flex;
                width: 38px;
                height: 38px;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-md);
                border: 1px solid rgba(255, 255, 255, 0.35);
                background: rgba(255, 255, 255, 0.12);
                color: #fff;
                cursor: pointer;
                padding: 0;
                box-sizing: border-box;
                transition: background var(--duration-fast), border-color var(--duration-fast);
            }

            .header-call-banner-icon-btn:hover {
                background: rgba(255, 255, 255, 0.2);
                border-color: rgba(255, 255, 255, 0.5);
            }

            .header-call-banner-icon-btn:focus-visible {
                outline: 2px solid #fff;
                outline-offset: 2px;
            }

            .header-call-banner-pulse {
                width: 10px;
                height: 10px;
                border-radius: 50%;
                flex-shrink: 0;
                background: #fff;
                animation: header-call-banner-pulse 1.5s ease-in-out infinite;
            }

            @keyframes header-call-banner-pulse {
                0%, 100% {
                    opacity: 1;
                    transform: scale(1);
                    box-shadow: 0 0 0 0 rgba(255, 255, 255, 0.4);
                }
                50% {
                    opacity: 0.88;
                    transform: scale(0.9);
                    box-shadow: 0 0 0 6px rgba(255, 255, 255, 0);
                }
            }

            .header-call-banner-text {
                flex: 1 1 auto;
                min-width: 0;
                display: flex;
                flex-direction: column;
                gap: 2px;
            }

            .header-call-banner-title {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                letter-spacing: 0.01em;
            }

            .header-call-banner-sub {
                font-size: var(--text-xs);
                opacity: 0.92;
            }

            .header-call-banner-hangup {
                flex-shrink: 0;
                width: 40px;
                height: 40px;
                border-radius: var(--radius-full);
                border: none;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                cursor: pointer;
                background: rgba(220, 38, 38, 0.92);
                color: #fff;
                box-shadow: 0 2px 10px rgba(220, 38, 38, 0.35);
                transition: transform var(--duration-fast) var(--easing-default), background var(--duration-fast) var(--easing-default);
                position: relative;
                z-index: 3;
            }

            .header-call-banner-hangup:hover {
                background: rgba(185, 28, 28, 0.98);
                transform: scale(1.04);
            }

            .header-call-banner-hangup:focus-visible {
                outline: 2px solid #fff;
                outline-offset: 2px;
            }

            .header-body--call-banner {
                align-items: stretch;
            }

            @media (max-width: 767px) {
                .chat-header.chat-header--call-banner {
                    padding-top: max(var(--space-1), env(safe-area-inset-top, 0px));
                    padding-bottom: var(--space-1);
                    padding-left: var(--space-2);
                    padding-right: 0;
                }
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

            .header-peer-hit {
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 0;
                margin: 0;
                border: none;
                background: transparent;
                cursor: pointer;
                border-radius: 50%;
                flex-shrink: 0;
            }

            .header-peer-hit:focus-visible {
                outline: 2px solid var(--accent);
                outline-offset: 2px;
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
                display: flex;
                align-items: center;
                gap: var(--space-1);
            }

            .header-subtitle.is-typing {
                color: var(--accent);
            }

            .header-online-dot {
                width: 7px;
                height: 7px;
                border-radius: 50%;
                background: var(--success);
                flex-shrink: 0;
                animation: header-online-pulse 2.5s ease-in-out infinite;
            }

            @keyframes header-online-pulse {
                0%, 100% { opacity: 0.75; transform: scale(1); }
                50% { opacity: 1; transform: scale(1.3); }
            }

            .header-actions {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                flex-shrink: 0;
            }

            .header-more-wrap {
                position: relative;
                isolation: isolate;
            }

            .header-more-menu {
                position: absolute;
                top: calc(100% + var(--space-1));
                right: 0;
                min-width: 200px;
                padding: var(--space-2);
                border-radius: var(--radius-lg);
                border: 1px solid var(--glass-border-strong);
                background: #1e2a47 !important;
                background-color: #1e2a47 !important;
                background-image: none !important;
                backdrop-filter: none !important;
                -webkit-backdrop-filter: none !important;
                opacity: 1;
                box-shadow: var(--glass-shadow-strong);
                z-index: 80;
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                isolation: isolate;
                overflow: hidden;
            }

            .header-more-menu::before {
                content: '';
                position: absolute;
                inset: 0;
                background: #1e2a47;
                z-index: -1;
                pointer-events: none;
            }

            :host-context([data-theme="light"]) .header-more-menu {
                background: #ffffff !important;
                background-color: #ffffff !important;
            }

            :host-context([data-theme="light"]) .header-more-menu::before {
                background: #ffffff;
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
                position: relative;
                z-index: 1;
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
                background: rgba(153, 166, 249, 0.1);
                border-color: rgba(153, 166, 249, 0.4);
                color: var(--success);
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

            @media (max-width: 767px) {
                .header-more-menu {
                    background: var(--bg-surface, #1e2a47);
                }
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
        _headerProfileOpen: { state: true },
        _headerProfileUser: { state: true },
    };

    constructor() {
        super();
        this._headerAvatarRetry = createAvatarRetry(() => this.requestUpdate());
        const s = SyncStore.state;
        this._chat = s.chat;
        this._channels = s.channels;
        this._spaces = s.spaces;
        this._wsState = s.ws.state;
        this._threadIds = [];
        this._ui = SyncStore.state.ui;
        this._isMobile = false;
        this._headerMoreOpen = false;
        this._headerProfileOpen = false;
        this._headerProfileUser = null;
        this._resizeObserver = null;
        this._typingSubtitle = '';
        this._peerPresenceByUserId = s.peerPresenceByUserId ?? {};
        this._typingPeersByChannel = s.typingPeersByChannel ?? {};
        this._boundAuthChange = () => {
            this._syncTypingSubtitleFromStore();
        };
        this._boundDocPointerHeaderMore = this._onDocPointerDownHeaderMore.bind(this);
        this._boundWindowResize = () => this._checkMobileViewport();
        this._boundWindowAdhoc = () => void this._startAdHocCall();
        this._i18nUnsub = null;
    }

    connectedCallback() {
        super.connectedCallback();
        this._i18nUnsub = this.i18n.subscribe(() => this.requestUpdate());
        document.addEventListener('pointerdown', this._boundDocPointerHeaderMore, true);
        window.addEventListener('resize', this._boundWindowResize);
        this._checkMobileViewport();
        this._resizeObserver = new ResizeObserver(() => this._checkMobileViewport());
        this._resizeObserver.observe(document.body);
        window.addEventListener(AppEvents.AUTH_CHANGE, this._boundAuthChange);
        window.addEventListener('sync-request-adhoc-call', this._boundWindowAdhoc);
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
        this._i18nUnsub?.();
        this._i18nUnsub = null;
        this._headerAvatarRetry.cancel();
        document.removeEventListener('pointerdown', this._boundDocPointerHeaderMore, true);
        window.removeEventListener('resize', this._boundWindowResize);
        window.removeEventListener(AppEvents.AUTH_CHANGE, this._boundAuthChange);
        window.removeEventListener('sync-request-adhoc-call', this._boundWindowAdhoc);
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
        if (focusedThreadId) return this.i18n.t('chat_view.title_thread', {});
        if (!selectedChannelId) return this.i18n.t('chat_view.title_pick_channel', {});
        const ch = this._selectedChannel();
        if (!ch) return selectedChannelId;
        if (SyncStore.isHiddenSyncChannelName(ch.name)) {
            return this.i18n.t('chat_view.title_meeting', {});
        }
        if (ch.type === 'direct' && ch.peer && typeof ch.peer.display_name === 'string') {
            return ch.peer.display_name;
        }
        return ch.name ?? selectedChannelId;
    }

    _isPeerOnline() {
        const ch = this._selectedChannel();
        if (!ch || ch.type !== 'direct' || !ch.peer?.user_id) return false;
        const row = (this._peerPresenceByUserId ?? {})[ch.peer.user_id];
        return !!(row && row.online);
    }

    _getSubtitle() {
        const { focusedThreadId } = this._chat;
        const ch = this._selectedChannel();
        if (!ch) return '';
        const chLabel = ch.type === 'direct' && ch.peer?.display_name
            ? ch.peer.display_name
            : (ch.name ?? ch.id);
        if (focusedThreadId) {
            return this.i18n.t('chat_view.thread_subtitle', { channel: chLabel, thread_id: focusedThreadId });
        }
        if (ch.type === 'direct' && ch.peer && typeof ch.peer.user_id === 'string' && ch.peer.user_id !== '') {
            return SyncStore.getPeerPresenceSubtitle(ch.peer.user_id);
        }
        return ch.type ?? '';
    }

    /**
     * Слева в шапке: как в sync-channel-row — только аватар канала (или peer в DM), иначе инициалы.
     */
    _headerLeadingGraphic(channel) {
        const ts = (key, params) => this.i18n.t(key, params ?? {});
        if (!channel) {
            return html``;
        }
        const originalUrl = channel.type === 'direct' && channel.peer
            ? (typeof channel.peer.avatar_url === 'string' && channel.peer.avatar_url !== '' ? channel.peer.avatar_url : null)
            : (typeof channel.avatar_url === 'string' && channel.avatar_url !== '' ? channel.avatar_url : null);
        const src = this._headerAvatarRetry.currentSrc(originalUrl);

        if (channel.type === 'direct' && channel.peer) {
            const p = channel.peer;
            const label = SyncStore.channelDisplayTitle(channel);
            const initial = (label.trim().slice(0, 1) || '?').toUpperCase();
            const hue = hueFromString(p.user_id);
            const inner = src
                ? html`<img class="header-entity-img" src=${src} alt=""
                    @load=${() => this._headerAvatarRetry.onLoad()}
                    @error=${() => this._headerAvatarRetry.onError(originalUrl)} />`
                : html`
                    <span class="header-entity-initials" style=${`background:hsl(${hue} 48% 42%)`}>${initial}</span>
                `;
            return html`
                <button
                    type="button"
                    class="header-peer-hit"
                    title=${ts('chat_view.peer_profile_title')}
                    aria-label=${ts('chat_view.peer_profile_aria')}
                    @click=${(e) => {
                        e.stopPropagation();
                        this._openHeaderPeerProfile(p);
                    }}
                >
                    ${inner}
                </button>
            `;
        }
        if (src) {
            return html`<img class="header-entity-img" src=${src} alt=""
                @load=${() => this._headerAvatarRetry.onLoad()}
                @error=${() => this._headerAvatarRetry.onError(originalUrl)} />`;
        }
        const title = SyncStore.channelDisplayTitle(channel);
        const initial = (title.trim().slice(0, 1) || '?').toUpperCase();
        const hue = hueFromString(channel.id);
        return html`
            <span class="header-entity-initials" style=${`background:hsl(${hue} 48% 42%)`}>${initial}</span>
        `;
    }

    _openHeaderPeerProfile(peer) {
        if (!peer || typeof peer.user_id !== 'string' || peer.user_id === '') {
            throw new Error(this.i18n.t('chat_view.err_peer_user_id', {}));
        }
        const members = SyncStore.state.companyMembers?.list ?? [];
        const cm = members.find(m => m.user_id === peer.user_id);
        this._headerProfileUser = {
            user_id: peer.user_id,
            display_name: typeof cm?.name === 'string' && cm.name.trim() !== ''
                ? cm.name.trim()
                : (typeof peer.display_name === 'string' && peer.display_name.trim() !== ''
                    ? peer.display_name.trim()
                    : mentionDisplayLabel(peer.user_id, members)),
            avatar_url: typeof cm?.avatar_url === 'string' && cm.avatar_url !== ''
                ? cm.avatar_url
                : (typeof peer.avatar_url === 'string' && peer.avatar_url !== '' ? peer.avatar_url : null),
        };
        this._headerProfileOpen = true;
    }

    _onHeaderProfileClose() {
        this._headerProfileOpen = false;
        this._headerProfileUser = null;
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
        this.updateComplete.then(async () => {
            const ml = this._messageListEl();
            if (!ml) {
                throw new Error(this.i18n.t('chat_view.err_message_list', {}));
            }
            await ml.scrollToMessageId(targetId);
            SyncStore.flashMessageHighlight(targetId);
        }).catch((err) => {
            const text = err instanceof Error ? err.message : String(err);
            this.error(text);
        });
    }

    async _deleteSelected() {
        const syncApi = this.services.get('syncApi');
        const channelId = this._chat.selectedChannelId;
        if (!channelId) throw new Error(this.i18n.t('chat_view.err_channel_not_selected', {}));
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
        if (!fromId) throw new Error(this.i18n.t('chat_view.err_channel_not_selected', {}));
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
        if (!fwd?.id || !fromId) throw new Error(this.i18n.t('chat_view.err_no_forward_message', {}));
        await syncApi.forwardMessage(fromId, fwd.id, toChannelId, null);
        SyncStore.setForwardModal(false, null);
        await SyncStore.loadMessages(syncApi, fromId);
    }

    _newMeetChannelName() {
        const locale = this.i18n.getCurrentLocale();
        const intlLocale = locale === 'ru' ? 'ru-RU' : 'en-US';
        const now = new Date();
        const dateStr = new Intl.DateTimeFormat(intlLocale, {
            year: 'numeric',
            month: 'short',
            day: 'numeric',
        }).format(now);
        const timeStr = new Intl.DateTimeFormat(intlLocale, {
            hour: 'numeric',
            minute: '2-digit',
        }).format(now);
        return this.i18n.t('chat_view.adhoc_meet_channel_name', { date: dateStr, time: timeStr });
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
                this.error(this.i18n.t('chat_view.create_space_for_meeting', {}));
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

    _callBannerActive() {
        const o = this._ui.activeCallOverlay;
        if (!o || o.minimized !== true) {
            return false;
        }
        if (typeof o.channel_id !== 'string' || o.channel_id === '') {
            return false;
        }
        const sel = this._chat.selectedChannelId;
        if (typeof sel !== 'string' || sel === '') {
            return false;
        }
        return SyncStore.normalizeSyncChannelId(sel) === SyncStore.normalizeSyncChannelId(o.channel_id);
    }

    _expandCallFromBanner(e) {
        if (e.target.closest('.header-call-banner-toolbar')) {
            return;
        }
        window.dispatchEvent(new CustomEvent('sync-call-overlay-expand', { bubbles: true }));
    }

    _hangupCallFromBanner(e) {
        e.stopPropagation();
        const o = this._ui.activeCallOverlay;
        if (typeof o?.call_id !== 'string' || o.call_id === '') {
            throw new Error(this.i18n.t('chat_view.err_call_banner_call_id', {}));
        }
        window.dispatchEvent(new CustomEvent('sync-call-banner-hangup', {
            bubbles: true,
            detail: { call_id: o.call_id },
        }));
    }

    _onCallBannerKeydown(e) {
        if (e.key !== 'Enter' && e.key !== ' ') {
            return;
        }
        e.preventDefault();
        this._expandCallFromBanner(e);
    }

    render() {
        const ts = (key, params) => this.i18n.t(key, params ?? {});
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
        const peerOnline = !typingLine && this._isPeerOnline();

        const callBanner = this._callBannerActive();

        const headerLead = selectedChannel
            ? html`<div class="header-leading">${this._headerLeadingGraphic(selectedChannel)}</div>`
            : html``;

        const showMobileMenuBtn = this._isMobile && !this._ui.mobileSidebarOpen;
        const channelBlock = showChannelSettings ? html`
                    <button
                        type="button"
                        class="header-channel-hit"
                        title=${ts('chat_view.channel_settings_title')}
                        @click=${this._openChannelSettings}
                    >
                        ${headerLead}
                        <div class="header-channel-text">
                            <div class="header-title">${this._getTitle()}</div>
                            ${showHeaderSubtitle ? html`
                                <div class="header-subtitle ${typingLine ? 'is-typing' : ''}">
                                    ${peerOnline ? html`<span class="header-online-dot" aria-hidden="true"></span>` : ''}
                                    <span>${headerSubtitleText}</span>
                                </div>
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
                                <div class="header-subtitle ${typingLine ? 'is-typing' : ''}">
                                    ${peerOnline ? html`<span class="header-online-dot" aria-hidden="true"></span>` : ''}
                                    <span>${headerSubtitleText}</span>
                                </div>
                            ` : ''}
                        </div>
                    </div>
                `;

        const mobileMenuBtn = html`
                    <button
                        type="button"
                        class=${classMap({ 'mobile-menu-btn': true, hidden: !showMobileMenuBtn })}
                        title=${ts('chat_view.open_menu_title')}
                        aria-label=${ts('chat_view.open_menu_aria')}
                        @click=${this._openMobileSidebar}
                    >
                        <platform-icon name="hamburger" size="20"></platform-icon>
                    </button>
                `;

        const callBannerBody = html`
                    ${mobileMenuBtn}
                    <div class="header-call-banner--integrated">
                        <button
                            type="button"
                            class="header-call-banner-hit"
                            title=${ts('chat_view.call_banner_subtitle')}
                            @click=${this._expandCallFromBanner}
                            @keydown=${this._onCallBannerKeydown}
                        >
                            <span class="header-call-banner-pulse" aria-hidden="true"></span>
                            <div class="header-call-banner-text">
                                <div class="header-call-banner-title">${ts('chat_view.call_banner_title')}</div>
                                <div class="header-call-banner-sub">${ts('chat_view.call_banner_subtitle')}</div>
                            </div>
                        </button>
                        <div class="header-call-banner-toolbar">
                            <span class="ws-badge ${this._wsState} header-call-banner-ws">${this._wsState}</span>
                            ${focusedThreadId ? html`
                                <button
                                    type="button"
                                    class="header-call-banner-icon-btn"
                                    title=${ts('chat_view.back')}
                                    aria-label=${ts('chat_view.back')}
                                    @click=${() => SyncStore.setFocusedThread(null)}
                                >
                                    <platform-icon name="chevron-left" size="18"></platform-icon>
                                </button>
                            ` : html`
                                <button
                                    type="button"
                                    class="header-call-banner-icon-btn"
                                    title=${ts('chat_view.threads_title')}
                                    aria-label=${ts('chat_view.threads_title')}
                                    ?disabled=${!selectedChannelId}
                                    @click=${() => SyncStore.setThreadDrawerOpen(true)}
                                >
                                    <platform-icon name="list" size="18"></platform-icon>
                                </button>
                            `}
                            ${this._isMobile ? html`
                                <div class="header-more-wrap">
                                    <button
                                        type="button"
                                        class="header-call-banner-icon-btn header-more-trigger"
                                        title=${ts('chat_view.more_title')}
                                        aria-label=${ts('chat_view.more_aria')}
                                        aria-expanded=${this._headerMoreOpen ? 'true' : 'false'}
                                        aria-haspopup="true"
                                        @click=${this._toggleHeaderMoreMenu}
                                    >
                                        <platform-icon name="more-vert" size="18" filled aria-hidden="true"></platform-icon>
                                    </button>
                                    ${this._headerMoreOpen ? html`
                                        <div class="header-more-menu" @pointerdown=${(e) => e.stopPropagation()}>
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
                                                    <span>${ts('chat_view.back')}</span>
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
                                                    <span>${ts('chat_view.threads')}</span>
                                                </button>
                                            `}
                                        </div>
                                    ` : ''}
                                </div>
                            ` : ''}
                            <button
                                type="button"
                                class="header-call-banner-hangup"
                                title=${ts('call_overlay.hangup_title')}
                                aria-label=${ts('chat_view.call_banner_hangup_aria')}
                                @click=${this._hangupCallFromBanner}
                            >
                                <platform-icon name="phone-ended" size="20" filled aria-hidden="true"></platform-icon>
                            </button>
                        </div>
                    </div>
                `;

        return html`
            <div class=${classMap({
        'chat-header': true,
        'chat-header--compact': this._isMobile,
        'chat-header--call-banner': callBanner,
    })}>
                <div class=${classMap({
        'header-body': true,
        'header-body--call-banner': callBanner,
    })}>
                    ${callBanner ? callBannerBody : html`
                    ${mobileMenuBtn}
                    <div class="header-main-tray">
                        <div class="header-channel-wrap">
                            ${channelBlock}
                        </div>
                        <div class="header-actions">
                        ${this._isMobile ? html`
                            <div class="header-more-wrap">
                                <button
                                    type="button"
                                    class="icon-btn header-more-trigger"
                                    title=${ts('chat_view.more_title')}
                                    aria-label=${ts('chat_view.more_aria')}
                                    aria-expanded=${this._headerMoreOpen ? 'true' : 'false'}
                                    aria-haspopup="true"
                                    @click=${this._toggleHeaderMoreMenu}
                                >
                                    <platform-icon name="more-vert" size="18" filled aria-hidden="true"></platform-icon>
                                </button>
                                ${this._headerMoreOpen ? html`
                                    <div class="header-more-menu" @pointerdown=${(e) => e.stopPropagation()}>
                                        <div class="header-more-menu-status">
                                            <span class="ws-badge ${this._wsState}">${this._wsState}</span>
                                        </div>
                                        ${selectedChannelId && !callBanner ? html`
                                            <button
                                                type="button"
                                                class="header-more-item"
                                                @click=${() => {
        this._closeHeaderMoreMenu();
        this._startCall();
    }}
                                            >
                                                <platform-icon name="video-call" size="16" filled aria-hidden="true"></platform-icon>
                                                <span>${ts('chat_view.call')}</span>
                                            </button>
                                        ` : ''}
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
                                                <span>${ts('chat_view.back')}</span>
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
                                                <span>${ts('chat_view.threads')}</span>
                                            </button>
                                        `}
                                    </div>
                                ` : ''}
                            </div>
                        ` : html`
                            <span class="ws-badge ${this._wsState}">${this._wsState}</span>

                            ${selectedChannelId && !callBanner ? html`
                            <button type="button" class="icon-btn" title=${ts('chat_view.call_in_channel_title')} aria-label=${ts('chat_view.call_in_channel_aria')} @click=${this._startCall}>
                                <platform-icon name="video-call" size="16" filled aria-hidden="true"></platform-icon>
                            </button>
                        ` : ''}

                            ${focusedThreadId ? html`
                            <button type="button" class="back-btn" @click=${() => SyncStore.setFocusedThread(null)}>
                                <platform-icon name="chevron-left" size="14"></platform-icon>
                                ${ts('chat_view.back')}
                            </button>
                        ` : html`
                            <button
                                type="button"
                                class="icon-btn"
                                title=${ts('chat_view.threads_title')}
                                ?disabled=${!selectedChannelId}
                                @click=${() => SyncStore.setThreadDrawerOpen(true)}
                            >
                                <platform-icon name="list" size="16"></platform-icon>
                            </button>
                        `}
                        `}
                        </div>
                    </div>
                    `}
                </div>
            </div>

            <div class="content">
                ${!selectedChannelId ? html`
                    <channel-picker @sync-request-adhoc-call=${() => void this._startAdHocCall()}></channel-picker>
                ` : html`
                    ${pinCount > 0 && !focusedThreadId ? html`
                        <div class="pin-strip" @click=${this._onPinStripClick} title=${ts('chat_view.pin_strip_title')}>
                            <platform-icon name="target" size="14"></platform-icon>
                            <span>${ts('chat_view.pinned_messages', { count: pinCount })}</span>
                        </div>
                    ` : ''}
                    ${selMode ? html`
                        <div class="selection-bar">
                            <span>${ts('chat_view.selected_count', { count: selIds.length })}</span>
                            <div class="selection-actions">
                                <button type="button" class="back-btn" @click=${() => {
        SyncStore.setSelectionMode(false);
    }}>${ts('chat_view.cancel')}</button>
                                <button
                                    type="button"
                                    class="back-btn"
                                    ?disabled=${selIds.length === 0}
                                    @click=${() => SyncStore.setForwardModal(true, null)}
                                >${ts('chat_view.forward')}</button>
                                <button
                                    type="button"
                                    class="back-btn"
                                    ?disabled=${selIds.length === 0}
                                    @click=${this._deleteSelected}
                                >${ts('chat_view.delete')}</button>
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
                        <div class="modal-title">${ts('chat_view.forward_modal_title')}</div>
                        ${forwardDestinations.length === 0 ? html`<p class="header-subtitle">${ts('chat_view.no_other_channels')}</p>` : ''}
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
                        <button type="button" class="back-btn" style="margin-top:var(--space-3)" @click=${() => SyncStore.setForwardModal(false, null)}>${ts('close')}</button>
                    </div>
                </div>
            ` : ''}

            <thread-drawer></thread-drawer>

            ${this._headerProfileOpen && this._headerProfileUser
                ? html`
                <user-info-modal
                    .open=${true}
                    .profileUser=${this._headerProfileUser}
                    @close=${this._onHeaderProfileClose}
                ></user-info-modal>
            `
                : ''}

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
