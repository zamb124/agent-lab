/**
 * sync-channel-picker — сетка каналов когда канал не выбран.
 *
 * Источники: useResource('sync/channels'), useResource('sync/spaces').
 * Фильтрация по `state.syncSpaces.sidebarSpaceFilterIds` (multi-select tags).
 *
 * Действия:
 *   - клик плитки канала → this.navigate('channel', { channelId })
 *   - кнопка "Создать канал" → openModal('sync.channel_create', { spaceId })
 *   - кнопка "Создать встречу" → dispatch UI-event 'sync/calls/adhoc_create_requested'
 *     (на него подписан sync-shell-page и открывает sync.channel_create с
 *     предзаполненным именем встречи + auto-invite после создания)
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/glass-card.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import { channelDisplayTitle } from './_helpers/sync-channel-display.js';
import { resolveSpaceId } from '../_helpers/sync-id-resolvers.js';

export class SyncChannelPicker extends PlatformElement {
    static styles = css`
        :host {
            display: block;
            padding: var(--space-4);
            overflow-y: auto;
            height: 100%;
        }
        .header {
            display: flex;
            align-items: center;
            gap: var(--space-2);
            margin-bottom: var(--space-3);
        }
        h2 { margin: 0; font-size: var(--text-lg); flex: 1; }
        .filters {
            display: flex;
            flex-wrap: wrap;
            gap: var(--space-1);
            margin-bottom: var(--space-3);
        }
        .filter {
            padding: 4px 8px;
            border-radius: var(--radius-sm);
            background: var(--glass-hover);
            color: var(--text-secondary);
            cursor: pointer;
            font-size: var(--text-xs);
        }
        .filter.active { background: var(--accent); color: white; }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
            gap: var(--space-3);
        }
        .tile {
            cursor: pointer;
            padding: var(--space-3);
        }
        .tile h3 { margin: 0 0 var(--space-1); font-size: var(--text-base); }
        .tile p { margin: 0; color: var(--text-secondary); font-size: var(--text-xs); }
    `;

    constructor() {
        super();
        this._channels = this.useResource('sync/channels', { autoload: true });
        this._spaces = this.useResource('sync/spaces', { autoload: true });
    }

    _toggleFilter(spaceId) {
        this.dispatch('sync/spaces/filter_toggled', { spaceId });
    }

    _onCreateChannel() {
        const firstSpace = this._spaces.items.length > 0 ? this._spaces.items[0] : null;
        const spaceId = firstSpace ? resolveSpaceId(firstSpace) : null;
        this.openModal('sync.channel_create', { spaceId: spaceId === '' ? null : spaceId });
    }

    _onAdhocCall() {
        this.dispatch('sync/calls/adhoc_create_requested', null);
    }

    _resolveFilterIds() {
        const sliceSpaces = this._spaces.slice;
        if (!sliceSpaces || !Array.isArray(sliceSpaces.sidebarSpaceFilterIds)) return [];
        return sliceSpaces.sidebarSpaceFilterIds;
    }

    _filteredChannels() {
        const filterIds = this._resolveFilterIds();
        const all = this._channels.items.filter((c) => c.type !== 'direct');
        if (filterIds.length === 0) return all;
        return all.filter((c) => typeof c.space_id === 'string' && filterIds.includes(c.space_id));
    }

    render() {
        const activeFilters = this._resolveFilterIds();
        const filtered = this._filteredChannels();
        return html`
            <div class="header">
                <h2>${this.t('channel_picker.title')}</h2>
                <platform-button @click=${this._onAdhocCall}>${this.t('channel_picker.action_adhoc_call')}</platform-button>
                <platform-button @click=${this._onCreateChannel}>${this.t('channel_picker.action_create_channel')}</platform-button>
            </div>
            ${this._spaces.items.length > 0 ? html`
                <div class="filters">
                    ${this._spaces.items.map((s) => {
                        const id = resolveSpaceId(s);
                        const active = activeFilters.includes(id);
                        return html`<span class=${active ? 'filter active' : 'filter'} @click=${() => this._toggleFilter(id)}>${s.name}</span>`;
                    })}
                </div>
            ` : ''}
            ${filtered.length === 0 ? html`
                <p style="color: var(--text-secondary);">${this.t('channel_picker.empty')}</p>
            ` : html`
                <div class="grid">
                    ${filtered.map((c) => html`
                        <glass-card class="tile" @click=${() => this.navigate('channel', { channelId: c.id })}>
                            <h3>${channelDisplayTitle(c)}</h3>
                            <p>${typeof c.last_message_preview === 'string' ? c.last_message_preview : ''}</p>
                        </glass-card>
                    `)}
                </div>
            `}
        `;
    }
}

customElements.define('sync-channel-picker', SyncChannelPicker);
