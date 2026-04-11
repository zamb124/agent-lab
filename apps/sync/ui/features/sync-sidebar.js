/**
 * SyncSidebar — spaces, channels; оболочка platform-service-sidebar.
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { sidebarStyles } from '@platform/lib/styles/shared/sidebar.styles.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { SyncStore } from '../store/sync.store.js';
import './sync-channel-row.js';
import './sync-direct-member-row.js';
import { readShellSidebarCollapsed } from '@platform/lib/utils/shell-sidebar-preference.js';
import '@platform/lib/components/layout/platform-service-sidebar.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-user.js';
import '@platform/lib/components/platform-notification-manager.js';

export class SyncSidebar extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        sidebarStyles,
        buttonStyles,
        css`
            :host {
                display: block;
                height: 100%;
            }

            .add-btn {
                margin-left: auto;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                min-width: 28px;
                height: 28px;
                padding: 0;
                background: transparent;
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                color: var(--text-tertiary);
                cursor: pointer;
                font-size: var(--text-lg);
                line-height: 1;
                transition: all var(--duration-fast);
            }

            .add-btn:hover {
                background: var(--glass-solid-subtle);
                color: var(--text-secondary);
            }

            .spaces-row {
                display: flex;
                flex-direction: row;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                border-top: 1px solid var(--glass-border-subtle);
                flex-shrink: 0;
                min-width: 0;
            }

            .spaces-row-label {
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                text-transform: uppercase;
                letter-spacing: 0.08em;
                color: var(--text-tertiary);
                flex-shrink: 0;
                white-space: nowrap;
            }

            .spaces-chips-scroll {
                display: flex;
                flex-direction: row;
                flex-wrap: nowrap;
                align-items: center;
                gap: var(--space-2);
                overflow-x: auto;
                overflow-y: hidden;
                flex: 1;
                min-width: 0;
                scrollbar-width: none;
                -webkit-overflow-scrolling: touch;
            }

            .spaces-chips-scroll::-webkit-scrollbar {
                display: none;
            }

            .spaces-filter-btn {
                display: none;
                flex-shrink: 0;
                align-items: center;
                justify-content: center;
                width: 28px;
                height: 28px;
                padding: 0;
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: transparent;
                color: var(--text-tertiary);
                cursor: pointer;
                transition: all var(--duration-fast);
            }

            .spaces-filter-btn.has-filter {
                border-color: var(--accent);
                color: var(--accent);
                background: var(--sync-active-row-bg);
            }

            .spaces-filter-btn:hover {
                background: var(--glass-solid-subtle);
                color: var(--text-secondary);
            }

            @media (max-width: 767px) {
                .spaces-filter-btn {
                    display: inline-flex;
                }

                .space-chip-gear {
                    display: none !important;
                }
            }

            .space-chip {
                display: inline-flex;
                flex-direction: row;
                align-items: center;
                flex-shrink: 0;
                max-width: min(200px, 85vw);
                border-radius: var(--radius-full);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                transition: border-color var(--duration-fast), background var(--duration-fast);
            }

            .space-chip.active {
                border-color: var(--accent);
                background: var(--sync-active-row-bg);
                box-shadow: var(--glass-inner-glow-subtle);
            }

            .space-chip-main {
                flex: 1;
                min-width: 0;
                padding: 6px 4px 6px 10px;
                border: none;
                background: transparent;
                cursor: pointer;
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
                color: var(--text-primary);
                text-align: left;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            .space-chip-gear {
                flex-shrink: 0;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 22px;
                height: 22px;
                margin: 2px 4px 2px 0;
                padding: 0;
                border: none;
                border-radius: var(--radius-md);
                background: transparent;
                color: var(--text-tertiary);
                cursor: pointer;
                transition: color var(--duration-fast), background var(--duration-fast);
            }

            .space-chip-gear:hover {
                background: var(--glass-solid-medium);
                color: var(--accent);
            }

            .space-chip.active .space-chip-gear {
                color: var(--accent);
            }

            .unified-channels-header {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: 0 var(--space-3) var(--space-2);
                flex-shrink: 0;
            }

            .channels-search {
                flex: 1;
                min-width: 0;
                padding: 5px var(--space-2);
                border-radius: var(--radius-lg);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary);
                font-size: var(--text-xs);
                font-family: inherit;
                outline: none;
            }

            .channels-search:focus {
                border-color: var(--accent);
            }

            .channels-search::placeholder {
                color: var(--text-tertiary);
            }

            .sync-sidebar-inner {
                display: flex;
                flex-direction: column;
                height: 100%;
                min-height: 0;
                overflow: hidden;
            }

            .channels-section--unified {
                flex: 1 1 0;
                min-height: 0;
                display: flex;
                flex-direction: column;
                overflow: hidden;
                border-top: 1px solid var(--glass-border-subtle);
                padding-top: var(--space-2);
            }

            .section-scroll--channels {
                flex: 1 1 0;
                min-height: 0;
                overflow-y: auto;
                padding-right: var(--space-1);
            }

            .nav-row-wrap {
                display: flex;
                align-items: stretch;
                gap: 0;
                margin-bottom: var(--space-1);
                width: 100%;
                min-width: 0;
                box-sizing: border-box;
                border-radius: var(--radius-lg);
                border: 1px solid transparent;
                background: transparent;
                transition: all var(--duration-normal) var(--easing-default);
            }

            .nav-row-wrap:hover {
                background: var(--glass-solid-subtle);
                border-color: var(--glass-border-subtle);
                box-shadow: var(--glass-inner-glow-subtle);
            }

            .nav-row-wrap.active {
                background: var(--sync-active-row-bg);
                border-color: var(--accent);
                box-shadow: var(--glass-inner-glow-subtle);
            }

            .nav-row-wrap.active .row-gear {
                color: var(--accent);
            }

            .nav-row-wrap.active:hover {
                background: var(--sync-active-row-bg);
                border-color: var(--accent);
            }

            .nav-row-wrap .row-gear {
                align-self: center;
                margin-right: var(--space-1);
            }

            .nav-row-wrap > sync-channel-row {
                flex: 1;
                min-width: 0;
            }

            .nav-row-wrap > sync-channel-row[icon-only] {
                flex: 0 0 auto;
            }

            .spaces-overlay {
                position: fixed;
                inset: 0;
                z-index: 9999;
                background: rgba(0, 0, 0, 0.35);
                display: flex;
                align-items: flex-end;
                animation: overlay-in var(--duration-fast) ease;
            }

            @keyframes overlay-in {
                from { opacity: 0; }
                to { opacity: 1; }
            }

            .spaces-sheet {
                width: 100%;
                max-height: 70dvh;
                border-radius: 16px 16px 0 0;
                background: var(--bg-surface, var(--glass-solid-medium, #fff));
                overflow-y: auto;
                -webkit-overflow-scrolling: touch;
                box-shadow: 0 -4px 24px rgba(0, 0, 0, 0.15);
                animation: sheet-in var(--duration-normal) var(--easing-default);
            }

            @keyframes sheet-in {
                from { transform: translateY(100%); }
                to { transform: translateY(0); }
            }

            .spaces-modal-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: var(--space-4) var(--space-4) var(--space-3);
                border-bottom: 1px solid var(--glass-border-subtle);
                position: sticky;
                top: 0;
                background: var(--bg-surface, #ffffff);
                z-index: 1;
            }

            .spaces-modal-title {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }

            .spaces-modal-done {
                padding: var(--space-1) var(--space-3);
                border: none;
                border-radius: var(--radius-md);
                background: var(--accent);
                color: #fff;
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                cursor: pointer;
                font-family: inherit;
            }

            .spaces-modal-list {
                padding: var(--space-2) 0;
            }

            .spaces-modal-item {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                padding: var(--space-3) var(--space-4);
                cursor: pointer;
            }

            .spaces-modal-item:active {
                background: var(--glass-solid-subtle);
            }

            .spaces-modal-item-name {
                flex: 1;
                min-width: 0;
                font-size: var(--text-sm);
                color: var(--text-primary);
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            .spaces-modal-item-check {
                flex-shrink: 0;
                width: 20px;
                height: 20px;
                border-radius: 50%;
                border: 2px solid var(--glass-border-medium);
                background: transparent;
                display: flex;
                align-items: center;
                justify-content: center;
                transition: all var(--duration-fast);
            }

            .spaces-modal-item-check.checked {
                background: var(--accent);
                border-color: var(--accent);
            }

            .spaces-modal-item-gear {
                flex-shrink: 0;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 32px;
                height: 32px;
                border: none;
                border-radius: var(--radius-md);
                background: transparent;
                color: var(--text-tertiary);
                cursor: pointer;
                transition: color var(--duration-fast), background var(--duration-fast);
            }

            .spaces-modal-item-gear:hover {
                background: var(--glass-solid-medium);
                color: var(--accent);
            }

            .loading-text {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                padding: var(--space-2) var(--space-3);
            }

            .sidebar-adhoc-row {
                padding: 0 0 var(--space-3);
            }

            .sidebar-adhoc-btn {
                display: flex;
                align-items: center;
                justify-content: flex-start;
                gap: var(--space-2);
                width: 100%;
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-lg);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary);
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                cursor: pointer;
                transition: background var(--duration-fast), border-color var(--duration-fast);
            }

            .sidebar-adhoc-btn:hover {
                background: var(--sync-active-row-bg);
                border-color: var(--accent);
                color: var(--accent);
                box-shadow: var(--glass-inner-glow-subtle);
            }

            .sidebar-adhoc-btn svg,
            .sidebar-adhoc-btn platform-icon {
                flex-shrink: 0;
                color: var(--accent);
                transition: transform var(--duration-fast) var(--easing-default);
            }

            .sidebar-adhoc-btn:hover svg,
            .sidebar-adhoc-btn:hover platform-icon {
                transform: scale(1.08);
            }

            platform-service-sidebar[collapsed] .sidebar-adhoc-label {
                display: none;
            }

            platform-service-sidebar[collapsed] .sidebar-adhoc-btn {
                justify-content: center;
                padding: var(--space-2);
            }

            .sync-sidebar-footer {
                display: flex;
                flex-direction: column;
                align-items: stretch;
                gap: 6px;
                width: 100%;
                min-width: 0;
                box-sizing: border-box;
            }

            .sync-sidebar-footer-row {
                display: flex;
                flex-direction: row;
                align-items: center;
                gap: 6px;
                width: 100%;
                min-width: 0;
                box-sizing: border-box;
            }

            .sync-sidebar-footer-row platform-user {
                flex: 1;
                min-width: 0;
            }

            platform-service-sidebar[collapsed] .sync-sidebar-footer-row {
                flex-direction: column;
                gap: 8px;
                align-items: center;
            }

            platform-service-sidebar[collapsed] .sync-sidebar-footer-row platform-user {
                flex: 0 0 auto;
                width: 100%;
            }

            .section-empty {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                padding: 0 var(--space-3) var(--space-2);
            }

            .row-gear {
                flex-shrink: 0;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 28px;
                height: 28px;
                padding: 0;
                border: none;
                border-radius: var(--radius-md);
                background: transparent;
                color: var(--text-tertiary);
                cursor: pointer;
                transition: color var(--duration-fast), background var(--duration-fast);
            }

            .row-gear:hover {
                background: var(--glass-solid-subtle);
                color: var(--accent);
            }

            platform-service-sidebar[collapsed] .sync-sidebar-inner .section-empty,
            platform-service-sidebar[collapsed] .sync-sidebar-inner .loading-text,
            platform-service-sidebar[collapsed] .sync-sidebar-inner .add-btn {
                display: none !important;
            }

            platform-service-sidebar[collapsed] .sidebar-adhoc-row {
                padding: 0 var(--space-2) var(--space-2);
            }

            platform-service-sidebar[collapsed] .sync-sidebar-inner .spaces-row {
                display: none !important;
            }

            platform-service-sidebar[collapsed] .sync-sidebar-inner .unified-channels-header {
                display: none !important;
            }

            platform-service-sidebar[collapsed] .sync-sidebar-inner .channels-search {
                display: none !important;
            }

            platform-service-sidebar[collapsed] .sync-sidebar-inner .nav-row-wrap {
                justify-content: center;
                margin-bottom: var(--space-1);
            }

            platform-service-sidebar[collapsed] .sync-sidebar-inner .row-gear {
                display: none !important;
            }

            platform-service-sidebar[collapsed] .sync-sidebar-inner .channels-section--unified {
                border-top: none;
                padding-top: var(--space-2);
            }

            .call-join-btn {
                align-self: center;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                gap: 6px;
                height: 30px;
                padding: 0 12px;
                margin-right: var(--space-1);
                box-sizing: border-box;
                border-radius: var(--radius-md);
                border: 1px solid var(--success-border);
                background: var(--success-bg);
                color: var(--success);
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                flex-shrink: 0;
                cursor: pointer;
                font-family: inherit;
                transition: background var(--duration-fast), border-color var(--duration-fast), color var(--duration-fast);
            }

            .call-join-btn:hover {
                background: rgba(16, 185, 129, 0.2);
                border-color: var(--success);
                color: var(--success);
            }

            .nav-row-wrap.active .call-join-btn {
                border-color: var(--success);
                background: rgba(16, 185, 129, 0.16);
                color: var(--success);
            }

            .call-join-btn platform-icon {
                flex-shrink: 0;
            }
        `
    ];

    static properties = {
        collapsed: { type: Boolean, reflect: true },
        activeCallChannels: { type: Object },
        _spaces: { state: true },
        _channels: { state: true },
        _companyMembers: { state: true },
        _chat: { state: true },
        _sidebarSpaceFilterIds: { state: true },
        _channelSearch: { state: true },
        _spacesModalOpen: { state: true },
        _mobileSidebarOpen: { state: true },
    };

    constructor() {
        super();
        this.collapsed = readShellSidebarCollapsed();
        const s = SyncStore.state;
        this._spaces = s.spaces;
        this._channels = s.channels;
        this._companyMembers = s.companyMembers;
        this._chat = s.chat;
        this._sidebarSpaceFilterIds = s.ui.sidebarSpaceFilterIds ?? [];
        this._channelSearch = '';
        this._spacesModalOpen = false;
        this._mobileSidebarOpen = s.ui.mobileSidebarOpen ?? false;
        this._i18nUnsub = null;
    }

    connectedCallback() {
        super.connectedCallback();
        this._i18nUnsub = this.i18n.subscribe(() => this.requestUpdate());
        this._unsubscribe = SyncStore.subscribe(state => {
            this._spaces = state.spaces;
            this._channels = state.channels;
            this._companyMembers = state.companyMembers;
            this._chat = state.chat;
            this._sidebarSpaceFilterIds = state.ui.sidebarSpaceFilterIds ?? [];
            this._mobileSidebarOpen = state.ui.mobileSidebarOpen ?? false;
        });
    }

    disconnectedCallback() {
        super.disconnectedCallback?.();
        this._i18nUnsub?.();
        this._i18nUnsub = null;
        this._unsubscribe?.();
    }

    _openChannelCreate() {
        try {
            SyncStore.openChannelSettingsCreate();
        } catch (err) {
            const text = err instanceof Error ? err.message : String(err);
            this.error(text);
        }
    }

    _requestAdhocCall() {
        window.dispatchEvent(new CustomEvent('sync-request-adhoc-call', { bubbles: true }));
        if (window.innerWidth < 768) {
            SyncStore.setMobileSidebarOpen(false);
        }
    }

    async _selectChannel(channel) {
        if (window.innerWidth < 768) {
            SyncStore.setMobileSidebarOpen(false);
        }
        const syncApi = this.services.get('syncApi');
        await SyncStore.selectChannelAndLoadMessages(syncApi, channel.space_id, channel.id);
    }

    async _openDirectWithMember(member) {
        if (window.innerWidth < 768) {
            SyncStore.setMobileSidebarOpen(false);
        }
        try {
            const syncApi = this.services.get('syncApi');
            const existing = SyncStore.findDirectChannelForPeer(member.user_id);
            if (existing) {
                await SyncStore.selectChannelAndLoadMessages(syncApi, null, existing.id);
                return;
            }
            const created = await syncApi.createDirectChannel(member.user_id);
            await SyncStore.loadChannels(syncApi);
            SyncStore.sanitizeChatSelectionAfterLoad();
            await SyncStore.selectChannelAndLoadMessages(syncApi, null, created.id);
        } catch (err) {
            const text = err instanceof Error ? err.message : String(err);
            this.error(text);
        }
    }

    _openSpacesModal() {
        this._spacesModalOpen = true;
    }

    _closeSpacesModal() {
        this._spacesModalOpen = false;
    }

    render() {
        const ts = (key, params) => this.i18n.t(key, params ?? {});
        const { selectedChannelId } = this._chat;
        const filterIds = this._sidebarSpaceFilterIds;
        const hasActiveFilter = Array.isArray(filterIds) && filterIds.length > 0;
        const spaceList = this._spaces.list;
        const q = this._channelSearch.trim().toLowerCase();

        const allChannels = SyncStore.getUnifiedSidebarChannelList();
        const filteredChannels = q
            ? allChannels.filter(c => {
                const title = (SyncStore.channelDisplayTitle(c) ?? '').toLowerCase();
                return title.includes(q);
            })
            : allChannels;

        const existingPeerIds = new Set(
            allChannels
                .filter(c => c.type === 'direct' && c.peer?.user_id)
                .map(c => c.peer.user_id),
        );
        const allMembers = this._companyMembers?.list ?? [];
        const membersWithoutDm = allMembers.filter(m => !existingPeerIds.has(m.user_id));
        const filteredMembersWithoutDm = q
            ? membersWithoutDm.filter(m => {
                const name = (typeof m.name === 'string' ? m.name : '').toLowerCase();
                const id = (typeof m.user_id === 'string' ? m.user_id : '').toLowerCase();
                return name.includes(q) || id.includes(q);
            })
            : membersWithoutDm;

        return html`
            <platform-service-sidebar
                logo-src="/static/core/assets/service_logos/sync_logo.svg"
                logo-text="Sync Chat"
                ?collapsed=${this.collapsed}
                ?mobile-open=${this._mobileSidebarOpen}
                @collapse-change=${(e) => {
                    this.collapsed = e.detail.collapsed;
                }}
                @mobile-change=${(e) => {
                    const o = e.detail?.open;
                    if (typeof o === 'boolean') {
                        SyncStore.setMobileSidebarOpen(o);
                    }
                }}
            >
                <div class="sync-sidebar-inner">
                    <div class="sidebar-adhoc-row">
                        <button
                            type="button"
                            class="sidebar-adhoc-btn"
                            title=${ts('sidebar.create_sync_title')}
                            @click=${this._requestAdhocCall}
                        >
                            <platform-icon name="video-call" size="20" filled aria-hidden="true"></platform-icon>
                            <span class="sidebar-adhoc-label">${ts('sidebar.create_sync_label')}</span>
                        </button>
                    </div>

                    <div class="spaces-row">
                        <span class="spaces-row-label">${ts('sidebar.spaces_section')}</span>
                        <div class="spaces-chips-scroll">
                            ${this._spaces.loading ? html`<div class="loading-text">${ts('sidebar.loading')}</div>` : ''}
                            ${spaceList.map((space) => html`
                                <div class="space-chip ${filterIds.includes(space.id) ? 'active' : ''}">
                                    <button
                                        type="button"
                                        class="space-chip-main"
                                        @click=${() => SyncStore.toggleSidebarSpaceFilter(space.id)}
                                    >${space.name}</button>
                                    <button
                                        type="button"
                                        class="space-chip-gear"
                                        title=${ts('sidebar.space_settings_title')}
                                        aria-label=${ts('sidebar.space_settings_aria')}
                                        @click=${(e) => {
                                            e.stopPropagation();
                                            SyncStore.openSpaceSettings(space.id);
                                        }}
                                    >
                                        <platform-icon name="settings" size="12"></platform-icon>
                                    </button>
                                </div>
                            `)}
                        </div>
                        <button
                            type="button"
                            class="spaces-filter-btn ${hasActiveFilter ? 'has-filter' : ''}"
                            title=${ts('sidebar.spaces_section')}
                            aria-label=${ts('sidebar.spaces_section')}
                            @click=${this._openSpacesModal}
                        >
                            <platform-icon name="filter" size="14"></platform-icon>
                        </button>
                        <button
                            type="button"
                            class="add-btn"
                            title=${ts('sidebar.create_space_title')}
                            aria-label=${ts('sidebar.create_space_aria')}
                            @click=${() => SyncStore.openSpaceSettingsCreate()}
                        >+</button>
                    </div>

                    <div class="channels-section--unified">
                        <div class="unified-channels-header">
                            <input
                                type="search"
                                class="channels-search"
                                placeholder=${ts('sidebar.direct_search_placeholder')}
                                aria-label=${ts('sidebar.direct_search_aria')}
                                .value=${this._channelSearch}
                                @input=${(e) => { this._channelSearch = e.target.value; }}
                            />
                            ${spaceList.length > 0 ? html`
                                <button
                                    type="button"
                                    class="add-btn"
                                    title=${ts('sidebar.create_channel_title')}
                                    aria-label=${ts('sidebar.create_channel_aria')}
                                    @click=${() => this._openChannelCreate()}
                                >+</button>
                            ` : ''}
                        </div>
                        <div class="section-scroll--channels">
                            ${this._channels.loading ? html`<div class="loading-text">${ts('sidebar.loading')}</div>` : ''}
                            ${!this._channels.loading && spaceList.length === 0
                                ? html`<div class="section-empty">${ts('sidebar.create_space_first')}</div>`
                                : ''}
                            ${!this._channels.loading && spaceList.length > 0 && filteredChannels.length === 0 && filteredMembersWithoutDm.length === 0
                                ? html`<div class="section-empty">${hasActiveFilter || q
                                    ? ts('sidebar.no_channels_filtered')
                                    : ts('sidebar.no_channels_yet')}</div>`
                                : ''}
                            ${filteredChannels.map((channel) => {
                                const showGear = channel.type !== 'direct';
                                return html`
                                    <div class="nav-row-wrap ${channel.id === selectedChannelId ? 'active' : ''}">
                                        <sync-channel-row
                                            in-nav-wrap
                                            .channel=${channel}
                                            .active=${channel.id === selectedChannelId}
                                            .iconOnly=${this.collapsed}
                                            @click=${() => this._selectChannel(channel)}
                                        ></sync-channel-row>
                                        ${this.activeCallChannels?.[channel.id] ? html`
                                            <button
                                                type="button"
                                                class="call-join-btn"
                                                title=${ts('sidebar.call_active_title')}
                                                @click=${(e) => {
                                                    e.stopPropagation();
                                                    this.dispatchEvent(new CustomEvent('join-call-channel', {
                                                        bubbles: true, composed: true,
                                                        detail: { channelId: channel.id },
                                                    }));
                                                }}
                                            >
                                                <platform-icon name="video-call" size="14" filled aria-hidden="true"></platform-icon>
                                                ${ts('sidebar.call_join')}
                                            </button>
                                        ` : ''}
                                        ${showGear ? html`
                                            <button
                                                type="button"
                                                class="row-gear"
                                                title=${ts('sidebar.channel_settings_title')}
                                                aria-label=${ts('sidebar.channel_settings_aria')}
                                                @click=${(e) => {
                                                    e.stopPropagation();
                                                    SyncStore.openChannelSettings(channel.id);
                                                }}
                                            >
                                                <platform-icon name="settings" size="16"></platform-icon>
                                            </button>
                                        ` : ''}
                                    </div>
                                `;
                            })}
                            ${filteredMembersWithoutDm.map((member) => html`
                                <sync-direct-member-row
                                    .member=${member}
                                    .active=${false}
                                    .iconOnly=${this.collapsed}
                                    @click=${() => this._openDirectWithMember(member)}
                                ></sync-direct-member-row>
                            `)}
                        </div>
                    </div>
                </div>

                <div slot="footer" class="sync-sidebar-footer">
                    <div class="sync-sidebar-footer-row">
                        <platform-user block>
                            <platform-notification-manager slot="user-toolbar"></platform-notification-manager>
                        </platform-user>
                    </div>
                    <platform-deployment-version base-url="/sync" footer></platform-deployment-version>
                </div>
            </platform-service-sidebar>

            ${this._spacesModalOpen ? html`
                <div class="spaces-overlay" @click=${this._closeSpacesModal}>
                    <div class="spaces-sheet" @click=${(e) => e.stopPropagation()}>
                        <div class="spaces-modal-header">
                            <span class="spaces-modal-title">${ts('sidebar.spaces_section')}</span>
                            <button
                                type="button"
                                class="spaces-modal-done"
                                @click=${this._closeSpacesModal}
                            >${ts('sidebar.spaces_modal_done')}</button>
                        </div>
                        <div class="spaces-modal-list">
                            ${spaceList.map((space) => html`
                                <div class="spaces-modal-item" @click=${() => SyncStore.toggleSidebarSpaceFilter(space.id)}>
                                    <div class="spaces-modal-item-check ${filterIds.includes(space.id) ? 'checked' : ''}">
                                        ${filterIds.includes(space.id) ? html`
                                            <platform-icon name="check" size="12" style="color:#fff"></platform-icon>
                                        ` : ''}
                                    </div>
                                    <span class="spaces-modal-item-name">${space.name}</span>
                                    <button
                                        type="button"
                                        class="spaces-modal-item-gear"
                                        title=${ts('sidebar.space_settings_title')}
                                        aria-label=${ts('sidebar.space_settings_aria')}
                                        @click=${(e) => {
                                            e.stopPropagation();
                                            this._closeSpacesModal();
                                            SyncStore.openSpaceSettings(space.id);
                                        }}
                                    >
                                        <platform-icon name="settings" size="16"></platform-icon>
                                    </button>
                                </div>
                            `)}
                        </div>
                    </div>
                </div>
            ` : ''}
        `;
    }
}

customElements.define('sync-sidebar', SyncSidebar);
