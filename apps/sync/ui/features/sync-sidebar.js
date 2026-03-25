/**
 * SyncSidebar — боковая панель: spaces, channels, навигация
 * По образцу rag-sidebar + platform-sidebar.
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { sidebarStyles } from '@platform/lib/styles/shared/sidebar.styles.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { ServiceRegistry } from '@platform/lib/services/ServiceRegistry.js';
import { SyncStore } from '../store/sync.store.js';
import './sync-channel-row.js';
import './sync-space-row.js';
import './sync-direct-member-row.js';
import '@platform/lib/components/layout/platform-sidebar.js';
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
                transition: all var(--duration-fast);
            }

            .nav-row-wrap:hover {
                background: var(--glass-solid-subtle);
                border-color: var(--glass-border-subtle);
            }

            .nav-row-wrap.active {
                background: var(--accent-subtle);
                border-color: var(--accent);
            }

            .nav-row-wrap.active .row-gear {
                color: var(--accent);
            }

            .nav-row-wrap.active:hover {
                background: var(--accent-subtle);
                border-color: var(--accent);
            }

            .nav-row-wrap .row-gear {
                align-self: center;
                margin-right: var(--space-1);
            }

            .nav-row-wrap > sync-channel-row,
            .nav-row-wrap > sync-space-row {
                flex: 1;
                min-width: 0;
            }

            .nav-row-wrap > sync-channel-row[icon-only],
            .nav-row-wrap > sync-space-row[icon-only] {
                flex: 0 0 auto;
            }

            .section-scroll {
                max-height: 45vh;
                overflow-y: auto;
                padding-right: var(--space-1);
            }

            .loading-text {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                padding: var(--space-2) var(--space-3);
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

            platform-sidebar[collapsed] .sync-sidebar-footer-row {
                flex-direction: column;
                gap: 8px;
                align-items: center;
            }

            platform-sidebar[collapsed] .sync-sidebar-footer-row platform-user {
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

            :host([collapsed]) .sync-sidebar-inner .section-title,
            :host([collapsed]) .sync-sidebar-inner .chevron-rot,
            :host([collapsed]) .sync-sidebar-inner .direct-search,
            :host([collapsed]) .sync-sidebar-inner .section-empty,
            :host([collapsed]) .sync-sidebar-inner .loading-text,
            :host([collapsed]) .sync-sidebar-inner .add-btn {
                display: none !important;
            }

            :host([collapsed]) .sync-sidebar-inner .section-header--toggle {
                justify-content: center;
                padding-left: var(--space-2);
                padding-right: var(--space-2);
            }

            :host([collapsed]) .sync-sidebar-inner .nav-row-wrap {
                justify-content: center;
                margin-bottom: var(--space-1);
            }

            :host([collapsed]) .sync-sidebar-inner .row-gear {
                display: none !important;
            }

            :host([collapsed]) .sync-sidebar-inner .channels-section {
                border-top: none;
                padding-top: var(--space-2);
                margin-top: 0;
            }

            :host([collapsed]) .sync-sidebar-inner .section-scroll {
                max-height: none;
            }

            .call-indicator {
                display: flex;
                align-items: center;
                gap: var(--space-1);
                padding: 2px 6px;
                background: rgba(34,197,94,0.15);
                border: 1px solid rgba(34,197,94,0.3);
                border-radius: 100px;
                font-size: 11px;
                font-weight: 600;
                color: #22c55e;
                flex-shrink: 0;
                cursor: pointer;
                transition: background 0.15s;
            }
            .call-indicator:hover { background: rgba(34,197,94,0.25); }
            .call-dot {
                width: 6px; height: 6px;
                border-radius: 50%;
                background: #22c55e;
                animation: blink 1.5s ease infinite;
                flex-shrink: 0;
            }
            @keyframes blink {
                0%, 100% { opacity: 1; }
                50% { opacity: 0.3; }
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
    }

    connectedCallback() {
        super.connectedCallback();
        this._unsubscribe = SyncStore.subscribe(state => {
            this._spaces = state.spaces;
            this._channels = state.channels;
            this._companyMembers = state.companyMembers;
            this._chat = state.chat;
            this._sectionOpen = state.ui.sidebarSectionOpen;
            this._typingPeersByChannel = state.typingPeersByChannel ?? {};
        });
    }

    disconnectedCallback() {
        super.disconnectedCallback?.();
        this._unsubscribe?.();
    }

    _selectSpace(spaceId) {
        SyncStore.selectSpace(spaceId);
    }

    async _selectChannel(channel) {
        const syncApi = ServiceRegistry.get('syncApi');
        await SyncStore.selectChannelAndLoadMessages(syncApi, channel.space_id, channel.id);
        if (window.innerWidth < 768) {
            SyncStore.setMobileSidebarOpen(false);
        }
    }

    async _openDirectWithMember(member) {
        try {
            const syncApi = ServiceRegistry.get('syncApi');
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
        const { selectedSpaceId, selectedChannelId } = this._chat;
        const sec = this._sectionOpen || { direct: true, spaces: true, channels: true };
        const channelsForSpace = selectedSpaceId
            ? SyncStore.getChannelsForSpace(selectedSpaceId)
            : [];
        const memberRows = this._filteredCompanyMembers();

        return html`
            <platform-sidebar
                logo-src="/static/core/assets/service_logos/sync_logo.svg"
                logo-text="Sync Chat"
                ?collapsed=${this.collapsed}
                @collapse-change=${(e) => { this.collapsed = e.detail.collapsed; }}
                @mobile-change=${(e) => {
                    const o = e.detail?.open;
                    if (typeof o === 'boolean') {
                        SyncStore.setMobileSidebarOpen(o);
                    }
                }}
            >
                <div class="sync-sidebar-inner">
                    <div class="channels-section">
                        <div
                            class="section-header section-header--toggle"
                            @click=${() => SyncStore.setSidebarSectionOpen('direct', !sec.direct)}
                        >
                            <span class="chevron-rot ${sec.direct ? '' : 'is-closed'}">
                                <platform-icon name="chevron-down" size="14"></platform-icon>
                            </span>
                            <platform-icon name="user" size="16"></platform-icon>
                            <span class="section-title">Личные</span>
                        </div>
                        ${sec.direct ? html`
                            <input
                                type="search"
                                class="direct-search"
                                placeholder="Поиск по имени или id..."
                                aria-label="Поиск участников компании"
                                .value=${this._directSearch}
                                @input=${(e) => { this._directSearch = e.target.value; }}
                                @click=${(e) => e.stopPropagation()}
                            />
                            <div class="section-scroll">
                                ${this._companyMembers.loading
                                    ? html`<div class="loading-text">Загрузка...</div>`
                                    : ''}
                                ${!this._companyMembers.loading && memberRows.length === 0
                                    ? html`<div class="section-empty">Нет совпадений или других участников</div>`
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
                        <div
                            class="section-header section-header--toggle"
                            @click=${() => SyncStore.setSidebarSectionOpen('spaces', !sec.spaces)}
                        >
                            <span class="chevron-rot ${sec.spaces ? '' : 'is-closed'}">
                                <platform-icon name="chevron-down" size="14"></platform-icon>
                            </span>
                            <platform-icon name="folder" size="16"></platform-icon>
                            <span class="section-title">Пространства</span>
                            <button
                                type="button"
                                class="add-btn"
                                title="Создать пространство"
                                aria-label="Создать пространство"
                                @click=${(e) => {
                                    e.stopPropagation();
                                    SyncStore.openSpaceSettingsCreate();
                                }}
                            >+</button>
                        </div>
                        ${sec.spaces ? html`
                            <div class="section-scroll">
                                ${this._spaces.loading ? html`<div class="loading-text">Загрузка...</div>` : ''}
                                ${this._spaces.list.map(space => html`
                                    <div
                                        class="nav-row-wrap ${space.id === selectedSpaceId ? 'active' : ''}"
                                    >
                                        <sync-space-row
                                            .space=${space}
                                            .active=${space.id === selectedSpaceId}
                                            .iconOnly=${this.collapsed}
                                            @click=${() => this._selectSpace(space.id)}
                                        ></sync-space-row>
                                        <button
                                            type="button"
                                            class="row-gear"
                                            title="Настройки пространства"
                                            aria-label="Настройки пространства"
                                            @click=${(e) => {
                                                e.stopPropagation();
                                                SyncStore.openSpaceSettings(space.id);
                                            }}
                                        >
                                            <platform-icon name="settings" size="16"></platform-icon>
                                        </button>
                                    </div>
                                `)}
                            </div>
                        ` : ''}
                    </div>

                    <div class="channels-section">
                        <div
                            class="section-header section-header--toggle"
                            @click=${() => SyncStore.setSidebarSectionOpen('channels', !sec.channels)}
                        >
                            <span class="chevron-rot ${sec.channels ? '' : 'is-closed'}">
                                <platform-icon name="chevron-down" size="14"></platform-icon>
                            </span>
                            <platform-icon name="chat" size="16"></platform-icon>
                            <span class="section-title">Каналы</span>
                            ${typeof selectedSpaceId === 'string' && selectedSpaceId !== ''
        ? html`
                            <button
                                type="button"
                                class="add-btn"
                                title="Создать канал"
                                aria-label="Создать канал"
                                @click=${(e) => {
                                    e.stopPropagation();
                                    SyncStore.openChannelSettingsCreate();
                                }}
                            >+</button>
                            `
        : ''}
                        </div>
                        ${sec.channels ? html`
                            <div class="section-scroll">
                                ${this._channels.loading ? html`<div class="loading-text">Загрузка...</div>` : ''}
                                ${!selectedSpaceId && !this._channels.loading
                                    ? html`<div class="section-empty">Сначала выбери пространство в списке выше.</div>`
                                    : ''}
                                ${channelsForSpace.map((channel) => {
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
                                                class="call-indicator"
                                                title="Идёт звонок — войти"
                                                @click=${(e) => {
                                                    e.stopPropagation();
                                                    this.dispatchEvent(new CustomEvent('join-call-channel', {
                                                        bubbles: true, composed: true,
                                                        detail: { channelId: channel.id },
                                                    }));
                                                }}
                                            >
                                                <span class="call-dot"></span>
                                                Войти
                                            </button>
                                        ` : ''}
                                        ${showGear ? html`
                                            <button
                                                type="button"
                                                class="row-gear"
                                                title="Настройки канала"
                                                aria-label="Настройки канала"
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
                        ` : ''}
                    </div>
                </div>

                <div slot="footer" class="sync-sidebar-footer">
                    <div class="sync-sidebar-footer-row">
                        <platform-user block></platform-user>
                        <platform-notification-manager></platform-notification-manager>
                    </div>
                    <platform-deployment-version base-url="/sync" footer></platform-deployment-version>
                </div>
            </platform-sidebar>
        `;
    }
}

customElements.define('sync-sidebar', SyncSidebar);
