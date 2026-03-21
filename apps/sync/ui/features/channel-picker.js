/**
 * ChannelPicker — сетка каналов для выбора когда канал не выбран
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { glassStyles } from '@platform/lib/styles/shared/glass.styles.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { SyncStore } from '../store/sync.store.js';
import { ServiceRegistry } from '@platform/lib/services/ServiceRegistry.js';
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
    };

    constructor() {
        super();
        const s = SyncStore.state;
        this._channels = s.channels;
        this._chat = s.chat;
    }

    connectedCallback() {
        super.connectedCallback();
        this._unsubscribe = SyncStore.subscribe(state => {
            this._channels = state.channels;
            this._chat = state.chat;
        });
    }

    disconnectedCallback() {
        super.disconnectedCallback?.();
        this._unsubscribe?.();
    }

    async _pick(channel) {
        SyncStore.selectChannel(channel.space_id, channel.id);
        const syncApi = ServiceRegistry.get('syncApi');
        await SyncStore.loadMessages(syncApi, channel.id);
    }

    render() {
        const channels = SyncStore.getChannelsForSpace(this._chat.selectedSpaceId);
        const loading = this._channels.loading;

        return html`
            <div class="hint">Выбери канал</div>
            ${loading ? html`<div class="hint">Загрузка...</div>` : ''}
            <div class="grid">
                ${channels.length === 0 && !loading ? html`<div class="empty">Каналов пока нет.</div>` : ''}
                ${channels.map(ch => html`
                    <button class="channel-card" @click=${() => this._pick(ch)}>
                        <span class="channel-name">${ch.name ?? ch.id}</span>
                        <span class="channel-type">${ch.type}</span>
                    </button>
                `)}
            </div>
        `;
    }
}

customElements.define('channel-picker', ChannelPicker);
