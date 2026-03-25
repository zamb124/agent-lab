/**
 * ChannelPicker — сетка каналов для выбора когда канал не выбран
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { glassStyles } from '@platform/lib/styles/shared/glass.styles.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { SyncStore } from '../store/sync.store.js';

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

            .adhoc-row {
                margin-bottom: var(--space-6);
            }

            .adhoc-btn {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-3) var(--space-4);
                border-radius: var(--radius-xl);
                border: 1px solid var(--accent);
                background: var(--accent-subtle);
                color: var(--accent);
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                cursor: pointer;
                transition: background var(--duration-fast), color var(--duration-fast);
            }

            .adhoc-btn:hover {
                background: var(--accent);
                color: white;
            }

            .adhoc-btn svg {
                flex-shrink: 0;
                color: var(--accent);
            }

            .adhoc-btn:hover svg {
                color: white;
            }

            .adhoc-hint {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-top: var(--space-2);
                max-width: 36rem;
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

    _emitAdhocRequest() {
        this.emit('sync-request-adhoc-call');
    }

    render() {
        const channels = SyncStore.getChannelsForPickerList();
        const loading = this._channels.loading;
        const hasFilter = Array.isArray(this._sidebarSpaceFilterIds) && this._sidebarSpaceFilterIds.length > 0;

        return html`
            <div class="hint">Выбери канал</div>
            <div class="adhoc-row">
                <button type="button" class="adhoc-btn" @click=${this._emitAdhocRequest}>
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                        <polygon points="23 7 16 12 23 17 23 7"/>
                        <rect x="1" y="5" width="15" height="14" rx="2" ry="2"/>
                    </svg>
                    Создать Sync
                </button>
                <div class="adhoc-hint">
                    Создаётся служебный канал встречи и сразу запускается видеозвонок. Канал скрыт в списках.
                </div>
            </div>
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
