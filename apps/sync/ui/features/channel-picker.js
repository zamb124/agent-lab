/**
 * ChannelPicker — сетка каналов для выбора когда канал не выбран
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { glassStyles } from '@platform/lib/styles/shared/glass.styles.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { SyncStore } from '../store/sync.store.js';
import '@platform/lib/components/platform-icon.js';

export class ChannelPicker extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        glassStyles,
        buttonStyles,
        css`
            :host {
                display: block;
                padding: var(--space-6);
                flex: 1;
            }

            .hint {
                font-size: var(--text-sm);
                color: var(--text-tertiary);
                margin-bottom: var(--space-4);
            }

            .grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
                gap: var(--space-3);
            }

            .channel-card {
                padding: var(--space-4);
                border-radius: var(--radius-xl);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                cursor: pointer;
                text-align: left;
                transition: all var(--duration-normal);
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }

            .channel-card:hover {
                background: var(--glass-solid-medium);
                border-color: var(--glass-border-medium);
                box-shadow: var(--glass-shadow-subtle);
                transform: translateY(-2px);
            }

            .channel-name {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            .channel-type {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }

            .empty {
                font-size: var(--text-sm);
                color: var(--text-tertiary);
            }
        `
    ];

    static properties = {
        _channels: { state: true },
        _chat: { state: true },
        _sidebarSpaceFilterIds: { state: true },
    };

    constructor() {
        super();
        const s = SyncStore.state;
        this._channels = s.channels;
        this._chat = s.chat;
        this._sidebarSpaceFilterIds = s.ui.sidebarSpaceFilterIds ?? [];
    }

    connectedCallback() {
        super.connectedCallback();
        this._unsubscribe = SyncStore.subscribe(state => {
            this._channels = state.channels;
            this._chat = state.chat;
            this._sidebarSpaceFilterIds = state.ui.sidebarSpaceFilterIds ?? [];
        });
    }

    disconnectedCallback() {
        super.disconnectedCallback?.();
        this._unsubscribe?.();
    }

    async _pick(channel) {
        const syncApi = this.services.get('syncApi');
        await SyncStore.selectChannelAndLoadMessages(syncApi, channel.space_id, channel.id);
    }

    render() {
        const channels = SyncStore.getChannelsForPickerList();
        const loading = this._channels.loading;
        const hasFilter = Array.isArray(this._sidebarSpaceFilterIds) && this._sidebarSpaceFilterIds.length > 0;

        return html`
            <div class="hint">Выбери канал</div>
            ${loading ? html`<div class="hint">Загрузка...</div>` : ''}
            <div class="grid">
                ${channels.length === 0 && !loading
                    ? html`<div class="empty">${hasFilter
                        ? 'Нет каналов в выбранных пространствах.'
                        : 'Каналов пока нет.'}</div>`
                    : ''}
                ${channels.map((ch) => {
                    const title = ch.type === 'direct' && ch.peer?.display_name
                        ? ch.peer.display_name
                        : (ch.name ?? ch.id);
                    return html`
                        <button class="channel-card" @click=${() => this._pick(ch)}>
                            <span class="channel-name">${title}</span>
                            <span class="channel-type">${SyncStore.channelRowMetaLabel(ch)}</span>
                        </button>
                    `;
                })}
            </div>
        `;
    }
}

customElements.define('channel-picker', ChannelPicker);
