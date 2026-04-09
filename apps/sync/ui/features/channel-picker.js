/**
 * ChannelPicker — сетка каналов для выбора когда канал не выбран
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { glassStyles } from '@platform/lib/styles/shared/glass.styles.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { SyncStore } from '../store/sync.store.js';
import '@platform/lib/components/platform-icon.js';
import './sync-channel-row.js';

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

            .adhoc-btn svg,
            .adhoc-btn platform-icon {
                flex-shrink: 0;
                color: var(--accent);
            }

            .adhoc-btn:hover svg,
            .adhoc-btn:hover platform-icon {
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
                padding: 0;
                border-radius: var(--radius-xl);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                text-align: left;
                transition: all var(--duration-normal);
                display: block;
                width: 100%;
                box-sizing: border-box;
                overflow: hidden;
            }

            .channel-card:hover {
                background: var(--glass-solid-medium);
                border-color: var(--glass-border-medium);
                box-shadow: var(--glass-shadow-subtle);
                transform: translateY(-2px);
            }

            .channel-card sync-channel-row {
                cursor: pointer;
                display: block;
                width: 100%;
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
        this._i18nUnsub = null;
    }

    connectedCallback() {
        super.connectedCallback();
        this._i18nUnsub = this.i18n.subscribe(() => this.requestUpdate());
        this._unsubscribe = SyncStore.subscribe(state => {
            this._channels = state.channels;
            this._chat = state.chat;
            this._sidebarSpaceFilterIds = state.ui.sidebarSpaceFilterIds ?? [];
        });
    }

    disconnectedCallback() {
        super.disconnectedCallback?.();
        this._i18nUnsub?.();
        this._i18nUnsub = null;
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
        const ts = (key, params) => this.i18n.t(key, params ?? {});
        const channels = SyncStore.getChannelsForPickerList();
        const loading = this._channels.loading;
        const hasFilter = Array.isArray(this._sidebarSpaceFilterIds) && this._sidebarSpaceFilterIds.length > 0;

        return html`
            <div class="hint">${ts('chat_view.title_pick_channel')}</div>
            <div class="adhoc-row">
                <button type="button" class="adhoc-btn" @click=${this._emitAdhocRequest}>
                    <platform-icon name="video-call" size="20" filled aria-hidden="true"></platform-icon>
                    ${ts('sidebar.create_sync_label')}
                </button>
                <div class="adhoc-hint">
                    ${ts('channel_picker.adhoc_description')}
                </div>
            </div>
            ${loading ? html`<div class="hint">${ts('sidebar.loading')}</div>` : ''}
            <div class="grid">
                ${channels.length === 0 && !loading
                    ? html`<div class="empty">${hasFilter
                        ? ts('sidebar.no_channels_filtered')
                        : ts('sidebar.no_channels_yet')}</div>`
                    : ''}
                ${channels.map((ch) => html`
                    <div class="channel-card">
                        <sync-channel-row
                            .channel=${ch}
                            .active=${false}
                            @click=${() => void this._pick(ch)}
                        ></sync-channel-row>
                    </div>
                `)}
            </div>
        `;
    }
}

customElements.define('channel-picker', ChannelPicker);
