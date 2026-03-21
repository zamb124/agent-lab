/**
 * SyncSidebar — боковая панель: spaces, channels, навигация
 * По образцу rag-sidebar + platform-sidebar.
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { sidebarStyles, sidebarNavItemStyles } from '@platform/lib/styles/shared/sidebar.styles.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { ServiceRegistry } from '@platform/lib/services/ServiceRegistry.js';
import { SyncStore } from '../store/sync.store.js';
import '@platform/lib/components/layout/platform-sidebar.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-user.js';

export class SyncSidebar extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        sidebarStyles,
        sidebarNavItemStyles,
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

            .nav-item {
                display: flex;
                align-items: flex-start;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-lg);
                cursor: pointer;
                background: transparent;
                border: 1px solid transparent;
                color: var(--text-secondary);
                font-size: var(--text-sm);
                width: 100%;
                text-align: left;
                transition: all var(--duration-fast);
                margin-bottom: var(--space-1);
            }

            .nav-item:hover {
                background: var(--glass-solid-subtle);
                border-color: var(--glass-border-subtle);
                color: var(--text-primary);
            }

            .nav-item.active {
                background: var(--accent-subtle);
                border-color: var(--accent);
                color: var(--accent);
                font-weight: var(--font-semibold);
            }

            .nav-item-label {
                flex: 1;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                min-width: 0;
            }

            .nav-item-type {
                font-size: 10px;
                color: var(--text-tertiary);
                flex-shrink: 0;
            }

            .nav-item-inner {
                flex: 1;
                min-width: 0;
                display: flex;
                flex-direction: column;
                gap: 2px;
            }

            .nav-item-title-row {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                min-width: 0;
            }

            .nav-item-preview {
                font-size: 11px;
                color: var(--text-tertiary);
                line-height: 1.3;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }

            .nav-item-unread {
                font-size: 11px;
                font-weight: var(--font-semibold);
                color: #fff;
                background: var(--accent);
                border-radius: var(--radius-full);
                min-width: 18px;
                padding: 1px 6px;
                text-align: center;
                flex-shrink: 0;
                margin-left: auto;
                align-self: flex-start;
            }

            .nav-item-count {
                font-size: 11px;
                color: var(--text-tertiary);
                background: var(--glass-solid-subtle);
                border-radius: var(--radius-full);
                padding: 1px 6px;
                flex-shrink: 0;
                margin-left: auto;
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

            .lists-toolbar {
                display: flex;
                flex-wrap: wrap;
                gap: 6px;
                padding: 0 var(--space-3) var(--space-2);
            }

            .toolbar-btn {
                font-size: 10px;
                font-weight: var(--font-medium);
                padding: 4px 8px;
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-tertiary);
                cursor: pointer;
            }

            .toolbar-btn:hover {
                color: var(--text-secondary);
                border-color: var(--glass-border-medium);
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

            .peer-avatar {
                width: 28px;
                height: 28px;
                border-radius: 50%;
                flex-shrink: 0;
                object-fit: cover;
            }

            .peer-avatar-initials {
                width: 28px;
                height: 28px;
                border-radius: 50%;
                flex-shrink: 0;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 11px;
                font-weight: var(--font-semibold);
                color: #fff;
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
        `
    ];

    static properties = {
        collapsed: { type: Boolean, reflect: true },
        _spaces: { state: true },
        _channels: { state: true },
        _companyMembers: { state: true },
        _chat: { state: true },
        _sectionOpen: { state: true },
        _directSearch: { state: true },
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
    }

    connectedCallback() {
        super.connectedCallback();
        this._unsubscribe = SyncStore.subscribe(state => {
            this._spaces = state.spaces;
            this._channels = state.channels;
            this._companyMembers = state.companyMembers;
            this._chat = state.chat;
            this._sectionOpen = state.ui.sidebarSectionOpen;
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

    _hueFromUserId(userId) {
        let h = 0;
        for (let i = 0; i < userId.length; i++) {
            h = (h * 31 + userId.charCodeAt(i)) >>> 0;
        }
        return h % 360;
    }

    _memberAvatar(member) {
        if (member.avatar_url) {
            return html`<img class="peer-avatar" src=${member.avatar_url} alt="" />`;
        }
        const label = typeof member.name === 'string' ? member.name : member.user_id;
        const initial = (label.trim().slice(0, 1) || '?').toUpperCase();
        const hue = this._hueFromUserId(member.user_id);
        return html`
            <span class="peer-avatar-initials" style=${`background:hsl(${hue} 48% 42%)`}>${initial}</span>
        `;
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

    _channelRowMeta(channel) {
        if (!channel) {
            return { preview: '', unread: 0 };
        }
        const preview = typeof channel.last_message_preview === 'string' ? channel.last_message_preview : '';
        const unread = typeof channel.unread_count === 'number' ? channel.unread_count : 0;
        return { preview, unread };
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
            >
                <div>
                    <div class="lists-toolbar">
                        <button
                            type="button"
                            class="toolbar-btn"
                            title="Свернуть списки пространств, каналов и личных чатов"
                            @click=${() => SyncStore.collapseAllSidebarSections()}
                        >Свернуть всё</button>
                        <button
                            type="button"
                            class="toolbar-btn"
                            title="Развернуть все секции"
                            @click=${() => SyncStore.expandAllSidebarSections()}
                        >Развернуть всё</button>
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
                                ${memberRows.map((member) => {
                                    const dmCh = SyncStore.findDirectChannelForPeer(member.user_id);
                                    const rowMeta = this._channelRowMeta(dmCh);
                                    return html`
                                    <button
                                        type="button"
                                        class="nav-item ${this._isDirectRowActive(member, selectedChannelId) ? 'active' : ''}"
                                        @click=${() => this._openDirectWithMember(member)}
                                    >
                                        ${this._memberAvatar(member)}
                                        <div class="nav-item-inner">
                                            <div class="nav-item-title-row">
                                                <span class="nav-item-label">${member.name}</span>
                                            </div>
                                            ${rowMeta.preview
                                                ? html`<span class="nav-item-preview">${rowMeta.preview}</span>`
                                                : ''}
                                        </div>
                                        ${rowMeta.unread > 0
                                            ? html`<span class="nav-item-unread">${rowMeta.unread}</span>`
                                            : ''}
                                    </button>
                                `;
                                })}
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
                                    SyncStore.setShowCreateSpace(true);
                                }}
                            >+</button>
                        </div>
                        ${sec.spaces ? html`
                            <div class="section-scroll">
                                ${this._spaces.loading ? html`<div class="loading-text">Загрузка...</div>` : ''}
                                ${this._spaces.list.map(space => html`
                                    <button
                                        class="nav-item ${space.id === selectedSpaceId ? 'active' : ''}"
                                        @click=${() => this._selectSpace(space.id)}
                                    >
                                        <platform-icon name="folder" size="16"></platform-icon>
                                        <span class="nav-item-label">${space.name}</span>
                                    </button>
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
                            <button
                                type="button"
                                class="add-btn"
                                title="Создать канал"
                                aria-label="Создать канал"
                                @click=${(e) => {
                                    e.stopPropagation();
                                    SyncStore.setShowCreateChannel(true);
                                }}
                            >+</button>
                        </div>
                        ${sec.channels ? html`
                            <div class="section-scroll">
                                ${this._channels.loading ? html`<div class="loading-text">Загрузка...</div>` : ''}
                                ${!selectedSpaceId && !this._channels.loading
                                    ? html`<div class="section-empty">Выбери пространство</div>`
                                    : ''}
                                ${channelsForSpace.map((channel) => {
                                    const rowMeta = this._channelRowMeta(channel);
                                    return html`
                                    <button
                                        class="nav-item ${channel.id === selectedChannelId ? 'active' : ''}"
                                        @click=${() => this._selectChannel(channel)}
                                    >
                                        <platform-icon name="chat" size="16"></platform-icon>
                                        <div class="nav-item-inner">
                                            <div class="nav-item-title-row">
                                                <span class="nav-item-label">${channel.name ?? channel.id}</span>
                                                <span class="nav-item-type">${channel.type}</span>
                                            </div>
                                            ${rowMeta.preview
                                                ? html`<span class="nav-item-preview">${rowMeta.preview}</span>`
                                                : ''}
                                        </div>
                                        ${rowMeta.unread > 0
                                            ? html`<span class="nav-item-unread">${rowMeta.unread}</span>`
                                            : ''}
                                    </button>
                                `;
                                })}
                            </div>
                        ` : ''}
                    </div>
                </div>

                <div slot="footer">
                    <platform-user block></platform-user>
                </div>
            </platform-sidebar>
        `;
    }
}

customElements.define('sync-sidebar', SyncSidebar);
