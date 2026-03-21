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
                align-items: center;
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
            }

            .nav-item-type {
                font-size: 10px;
                color: var(--text-tertiary);
                flex-shrink: 0;
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
        `
    ];

    static properties = {
        collapsed: { type: Boolean, reflect: true },
        _spaces: { state: true },
        _channels: { state: true },
        _chat: { state: true },
    };

    constructor() {
        super();
        this.collapsed = false;
        const s = SyncStore.state;
        this._spaces = s.spaces;
        this._channels = s.channels;
        this._chat = s.chat;
    }

    connectedCallback() {
        super.connectedCallback();
        this._unsubscribe = SyncStore.subscribe(state => {
            this._spaces = state.spaces;
            this._channels = state.channels;
            this._chat = state.chat;
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

    render() {
        const { selectedSpaceId, selectedChannelId } = this._chat;
        const channelsForSpace = SyncStore.getChannelsForSpace(selectedSpaceId);

        return html`
            <platform-sidebar
                logo-src="/static/core/assets/service_logos/sync_logo.svg"
                logo-text="Sync Chat"
                ?collapsed=${this.collapsed}
                @collapse-change=${(e) => { this.collapsed = e.detail.collapsed; }}
            >
                <div>
                    <div class="section-header">
                        <platform-icon name="folder" size="16"></platform-icon>
                        <span class="section-title">Пространства</span>
                        <button
                            type="button"
                            class="add-btn"
                            title="Создать пространство"
                            aria-label="Создать пространство"
                            @click=${() => SyncStore.setShowCreateSpace(true)}
                        >+</button>
                    </div>
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

                    <div class="channels-section">
                        <div class="section-header">
                            <platform-icon name="chat" size="16"></platform-icon>
                            <span class="section-title">Каналы</span>
                            <button
                                type="button"
                                class="add-btn"
                                title="Создать канал"
                                aria-label="Создать канал"
                                @click=${() => SyncStore.setShowCreateChannel(true)}
                            >+</button>
                        </div>
                        <div class="section-scroll">
                            ${this._channels.loading ? html`<div class="loading-text">Загрузка...</div>` : ''}
                            ${channelsForSpace.map(channel => html`
                                <button
                                    class="nav-item ${channel.id === selectedChannelId ? 'active' : ''}"
                                    @click=${() => this._selectChannel(channel)}
                                >
                                    <platform-icon name="chat" size="16"></platform-icon>
                                    <span class="nav-item-label">${channel.name ?? channel.id}</span>
                                    <span class="nav-item-type">${channel.type}</span>
                                </button>
                            `)}
                        </div>
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
