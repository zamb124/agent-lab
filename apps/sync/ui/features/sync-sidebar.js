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

            .section-title {
                flex: 1;
                min-width: 0;
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                text-transform: uppercase;
                letter-spacing: 0.08em;
                color: var(--text-tertiary);
                padding: 0;
                margin-bottom: 0;
            }

            .section-header {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: 0 var(--space-3);
                margin-bottom: var(--space-2);
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

            .space-filters-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
                padding: 0 var(--space-3);
                margin-bottom: var(--space-2);
                min-width: 0;
            }

            .space-filters-header .section-title {
                margin-bottom: 0;
            }

            .space-tags-scroll {
                display: flex;
                flex-direction: row;
                flex-wrap: nowrap;
                align-items: center;
                gap: var(--space-2);
                overflow-x: auto;
                overflow-y: hidden;
                padding: 0 var(--space-3) var(--space-3);
                margin: 0 0 var(--space-1);
                scrollbar-width: thin;
                -webkit-overflow-scrolling: touch;
            }

            .space-tags-scroll::-webkit-scrollbar {
                height: 6px;
            }

            .space-tags-scroll::-webkit-scrollbar-thumb {
                background: var(--glass-border-medium);
                border-radius: 3px;
            }

            .space-tags-empty {
                padding-left: var(--space-3);
                flex-shrink: 0;
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

            .section-header--static {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: 0 var(--space-3);
                margin-bottom: var(--space-2);
                cursor: default;
                user-select: none;
                box-sizing: border-box;
                width: 100%;
            }

            .section-header--static .section-title {
                flex: 1;
                min-width: 0;
            }

            .sync-sidebar-inner {
                display: flex;
                flex-direction: column;
                height: 100%;
                min-height: 0;
                overflow: hidden;
            }

            .channels-section:last-child {
                flex: 1 1 0;
                min-height: 0;
                display: flex;
                flex-direction: column;
                overflow: hidden;
            }

            .section-scroll--channels {
                flex: 1 1 0;
                min-height: 0;
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

            .section-scroll {
                max-height: 30vh;
                overflow-y: auto;
                padding-right: var(--space-1);
            }

            .loading-text {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                padding: var(--space-2) var(--space-3);
            }

            .sidebar-adhoc-row {
                padding: 0 var(--space-3) var(--space-3);
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

            .sidebar-adhoc-btn svg {
                flex-shrink: 0;
                color: var(--accent);
                transition: transform var(--duration-fast) var(--easing-default);
            }

            .sidebar-adhoc-btn:hover svg {
                transform: scale(1.08);
            }

            platform-service-sidebar[collapsed] .sidebar-adhoc-label {
                display: none;
            }

            platform-service-sidebar[collapsed] .sidebar-adhoc-btn {
                justify-content: center;
                padding: var(--space-2);
            }

            .channels-section {
                border-top: 1px solid var(--glass-border-subtle);
                padding-top: var(--space-3);
                margin-top: var(--space-2);
            }

            .section-header--toggle {
                cursor: pointer;
                user-select: none;
                width: 100%;
                box-sizing: border-box;
            }

            .chevron-rot {
                display: inline-flex;
                align-items: center;
                transition: transform var(--duration-fast);
                flex-shrink: 0;
            }

            .chevron-rot.is-closed {
                transform: rotate(-90deg);
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

            .sync-sidebar-footer-row platform-notification-manager {
                flex-shrink: 0;
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

            .direct-search {
                width: calc(100% - 2 * var(--space-3));
                box-sizing: border-box;
                margin: 0 var(--space-3) var(--space-2);
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-lg);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary);
                font-size: var(--text-xs);
                font-family: inherit;
                outline: none;
            }

            .direct-search:focus {
                border-color: var(--accent);
            }

            .direct-search::placeholder {
                color: var(--text-tertiary);
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

            platform-service-sidebar[collapsed] .sync-sidebar-inner .section-title,
            platform-service-sidebar[collapsed] .sync-sidebar-inner .chevron-rot,
            platform-service-sidebar[collapsed] .sync-sidebar-inner .direct-search,
            platform-service-sidebar[collapsed] .sync-sidebar-inner .section-empty,
            platform-service-sidebar[collapsed] .sync-sidebar-inner .loading-text,
            platform-service-sidebar[collapsed] .sync-sidebar-inner .add-btn {
                display: none !important;
            }

            platform-service-sidebar[collapsed] .sync-sidebar-inner .section-header--toggle {
                justify-content: center;
                padding-left: var(--space-2);
                padding-right: var(--space-2);
            }

            platform-service-sidebar[collapsed] .sync-sidebar-inner .space-filters-header,
            platform-service-sidebar[collapsed] .sync-sidebar-inner .space-tags-scroll {
                display: none !important;
            }

            platform-service-sidebar[collapsed] .sync-sidebar-inner .nav-row-wrap {
                justify-content: center;
                margin-bottom: var(--space-1);
            }

            platform-service-sidebar[collapsed] .sync-sidebar-inner .row-gear {
                display: none !important;
            }

            platform-service-sidebar[collapsed] .sync-sidebar-inner .channels-section {
                border-top: none;
                padding-top: var(--space-2);
                margin-top: 0;
            }

            platform-service-sidebar[collapsed] .sync-sidebar-inner .section-scroll {
                max-height: none;
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
                border: 1px solid rgba(22, 163, 74, 0.4);
                background: rgba(22, 163, 74, 0.08);
                color: #15803d;
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                flex-shrink: 0;
                cursor: pointer;
                font-family: inherit;
                transition: background var(--duration-fast), border-color var(--duration-fast), color var(--duration-fast);
            }

            .call-join-btn:hover {
                background: rgba(22, 163, 74, 0.14);
                border-color: rgba(21, 128, 61, 0.55);
                color: #166534;
            }

            .nav-row-wrap.active .call-join-btn {
                border-color: rgba(22, 163, 74, 0.55);
                background: rgba(22, 163, 74, 0.12);
                color: #14532d;
            }

            .call-join-btn svg {
                flex-shrink: 0;
                opacity: 0.9;
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
        _sectionOpen: { state: true },
        _directSearch: { state: true },
        _typingPeersByChannel: { state: true },
        _sidebarSpaceFilterIds: { state: true },
    };

    constructor() {
        super();
        this.collapsed = false;
        const s = SyncStore.state;
        this._spaces = s.spaces;
        this._channels = s.channels;
        this._companyMembers = s.companyMembers;
        this._chat = s.chat;
        this._sectionOpen = s.ui.sidebarSectionOpen;
        this._directSearch = '';
        this._typingPeersByChannel = s.typingPeersByChannel ?? {};
        this._sidebarSpaceFilterIds = s.ui.sidebarSpaceFilterIds ?? [];
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
            this._sectionOpen = state.ui.sidebarSectionOpen;
            this._typingPeersByChannel = state.typingPeersByChannel ?? {};
            this._sidebarSpaceFilterIds = state.ui.sidebarSpaceFilterIds ?? [];
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
        const syncApi = this.services.get('syncApi');
        await SyncStore.selectChannelAndLoadMessages(syncApi, channel.space_id, channel.id);
        if (window.innerWidth < 768) {
            SyncStore.setMobileSidebarOpen(false);
        }
    }

    async _openDirectWithMember(member) {
        try {
            const syncApi = this.services.get('syncApi');
            const existing = SyncStore.findDirectChannelForPeer(member.user_id);
            if (existing) {
                await this._selectChannel(existing);
                return;
            }
            const created = await syncApi.createDirectChannel(member.user_id);
            await SyncStore.loadChannels(syncApi);
            SyncStore.sanitizeChatSelectionAfterLoad();
            await SyncStore.selectChannelAndLoadMessages(syncApi, null, created.id);
            if (window.innerWidth < 768) {
                SyncStore.setMobileSidebarOpen(false);
            }
        } catch (err) {
            const text = err instanceof Error ? err.message : String(err);
            this.error(text);
        }
    }

    _filteredCompanyMembers() {
        const list = this._companyMembers.list;
        const q = this._directSearch.trim().toLowerCase();
        if (!q) {
            return list;
        }
        return list.filter((m) => {
            const name = typeof m.name === 'string' ? m.name.toLowerCase() : '';
            const id = typeof m.user_id === 'string' ? m.user_id.toLowerCase() : '';
            return name.includes(q) || id.includes(q);
        });
    }

    _isDirectRowActive(member, selectedChannelId) {
        const ch = SyncStore.findDirectChannelForPeer(member.user_id);
        return ch !== null && ch.id === selectedChannelId;
    }

    render() {
        const ts = (key, params) => this.i18n.t(key, params ?? {});
        const { selectedChannelId } = this._chat;
        const sec = this._sectionOpen || { direct: true, spaces: true, channels: true };
        const sidebarChannels = SyncStore.getChannelsForSidebarList();
        const filterIds = this._sidebarSpaceFilterIds;
        const hasActiveFilter = Array.isArray(filterIds) && filterIds.length > 0;
        const memberRows = this._filteredCompanyMembers();
        const spaceList = this._spaces.list;

        return html`
            <platform-service-sidebar
                logo-src="/static/core/assets/service_logos/sync_logo.svg"
                logo-text="Sync Chat"
                ?collapsed=${this.collapsed}
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
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                                <polygon points="23 7 16 12 23 17 23 7"/>
                                <rect x="1" y="5" width="15" height="14" rx="2" ry="2"/>
                            </svg>
                            <span class="sidebar-adhoc-label">${ts('sidebar.create_sync_label')}</span>
                        </button>
                    </div>
                    <div class="channels-section">
                        <div
                            class="section-header section-header--toggle"
                            @click=${() => SyncStore.setSidebarSectionOpen('direct', !sec.direct)}
                        >
                            <span class="chevron-rot ${sec.direct ? '' : 'is-closed'}">
                                <platform-icon name="chevron-down" size="14"></platform-icon>
                            </span>
                            <platform-icon name="user" size="16"></platform-icon>
                            <span class="section-title">${ts('sidebar.direct_section')}</span>
                        </div>
                        ${sec.direct ? html`
                            <input
                                type="search"
                                class="direct-search"
                                placeholder=${ts('sidebar.direct_search_placeholder')}
                                aria-label=${ts('sidebar.direct_search_aria')}
                                .value=${this._directSearch}
                                @input=${(e) => { this._directSearch = e.target.value; }}
                                @click=${(e) => e.stopPropagation()}
                            />
                            <div class="section-scroll">
                                ${this._companyMembers.loading
                                    ? html`<div class="loading-text">${ts('sidebar.loading')}</div>`
                                    : ''}
                                ${!this._companyMembers.loading && memberRows.length === 0
                                    ? html`<div class="section-empty">${ts('sidebar.direct_empty')}</div>`
                                    : ''}
                                ${memberRows.map((member) => html`
                                    <sync-direct-member-row
                                        .member=${member}
                                        .active=${this._isDirectRowActive(member, selectedChannelId)}
                                        .iconOnly=${this.collapsed}
                                        @click=${() => this._openDirectWithMember(member)}
                                    ></sync-direct-member-row>
                                `)}
                            </div>
                        ` : ''}
                    </div>

                    <div class="channels-section">
                        <div class="space-filters-header">
                            <span class="section-title">${ts('sidebar.spaces_section')}</span>
                            <button
                                type="button"
                                class="add-btn"
                                title=${ts('sidebar.create_space_title')}
                                aria-label=${ts('sidebar.create_space_aria')}
                                @click=${() => SyncStore.openSpaceSettingsCreate()}
                            >+</button>
                        </div>
                        <div class="space-tags-scroll">
                            ${this._spaces.loading ? html`<div class="loading-text">${ts('sidebar.loading')}</div>` : ''}
                            ${!this._spaces.loading && spaceList.length === 0
                                ? html`<div class="section-empty space-tags-empty">${ts('sidebar.spaces_empty')}</div>`
                                : ''}
                            ${spaceList.map((space) => html`
                                <div
                                    class="space-chip ${filterIds.includes(space.id) ? 'active' : ''}"
                                >
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
                    </div>

                    <div class="channels-section">
                        <div class="section-header section-header--static">
                            <platform-icon name="chat" size="16"></platform-icon>
                            <span class="section-title">${ts('sidebar.channels_section')}</span>
                            ${spaceList.length > 0
        ? html`
                            <button
                                type="button"
                                class="add-btn"
                                title=${ts('sidebar.create_channel_title')}
                                aria-label=${ts('sidebar.create_channel_aria')}
                                style="margin-left:auto"
                                @click=${() => this._openChannelCreate()}
                            >+</button>
                            `
        : ''}
                        </div>
                        <div class="section-scroll section-scroll--channels">
                            ${this._channels.loading ? html`<div class="loading-text">${ts('sidebar.loading')}</div>` : ''}
                            ${!this._channels.loading && spaceList.length === 0
                                ? html`<div class="section-empty">${ts('sidebar.create_space_first')}</div>`
                                : ''}
                            ${!this._channels.loading && spaceList.length > 0 && sidebarChannels.length === 0
                                ? html`<div class="section-empty">${hasActiveFilter
                                    ? ts('sidebar.no_channels_filtered')
                                    : ts('sidebar.no_channels_yet')}</div>`
                                : ''}
                            ${sidebarChannels.map((channel) => {
                                    const showGear = channel.type !== 'direct';
                                    return html`
                                    <div
                                        class="nav-row-wrap ${channel.id === selectedChannelId ? 'active' : ''}"
                                    >
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
                                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                                                    <polygon points="23 7 16 12 23 17 23 7"/>
                                                    <rect x="1" y="5" width="15" height="14" rx="2" ry="2"/>
                                                </svg>
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
                        </div>
                    </div>
                </div>

                <div slot="footer" class="sync-sidebar-footer">
                    <div class="sync-sidebar-footer-row">
                        <platform-user block></platform-user>
                        <platform-notification-manager></platform-notification-manager>
                    </div>
                    <platform-deployment-version base-url="/sync" footer></platform-deployment-version>
                </div>
            </platform-service-sidebar>
        `;
    }
}

customElements.define('sync-sidebar', SyncSidebar);
