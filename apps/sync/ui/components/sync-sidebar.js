/**
 * sync-sidebar — навигация по пространствам, каналам, DM-участникам.
 *
 * Источники: useResource('sync/spaces'|'sync/channels'|'sync/company_members').
 * UI-actions: dispatch('sync/spaces/space_selected'|'sync/spaces/filter_toggled').
 *
 * Пространства — горизонтальные теги (multi-select filter).
 * Каналы — отфильтрованные по `sidebarSpaceFilterIds` (пустой массив = все).
 * DM — список участников компании; click открывает существующий direct-канал
 * или создаёт новый.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { resolveSpaceId } from '../_helpers/sync-id-resolvers.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import './sync-channel-row.js';
import './sync-direct-member-row.js';

export class SyncSidebar extends PlatformElement {
    static styles = css`
        :host {
            display: flex;
            flex-direction: column;
            width: 280px;
            height: 100vh;
            background: var(--glass-solid);
            border-right: 1px solid var(--glass-border);
            overflow: hidden;
        }
        .header {
            padding: var(--space-3);
            border-bottom: 1px solid var(--glass-border);
            display: flex;
            align-items: center;
            gap: var(--space-2);
        }
        .header h3 { margin: 0; font-size: var(--text-sm); flex: 1; font-weight: 600; }
        .filter-bar {
            display: flex;
            flex-wrap: wrap;
            gap: var(--space-1);
            padding: var(--space-2) var(--space-3);
            border-bottom: 1px solid var(--glass-border);
        }
        .tag {
            font-size: var(--text-xs);
            padding: 2px 8px;
            border-radius: var(--radius-sm);
            background: var(--glass-hover);
            color: var(--text-secondary);
            cursor: pointer;
        }
        .tag.active { background: var(--accent); color: white; }
        .scroll {
            flex: 1;
            overflow-y: auto;
            padding: var(--space-2) var(--space-3);
        }
        .section {
            margin-bottom: var(--space-3);
        }
        .section-title {
            font-size: var(--text-xs);
            text-transform: uppercase;
            color: var(--text-secondary);
            margin: var(--space-2) 0 var(--space-1);
            display: flex;
            align-items: center;
            gap: var(--space-1);
        }
        .section-title .add {
            margin-left: auto;
            cursor: pointer;
            color: var(--text-primary);
        }
    `;

    constructor() {
        super();
        this._spaces = this.useResource('sync/spaces', { autoload: true });
        this._channels = this.useResource('sync/channels', { autoload: true });
        this._members = this.useResource('sync/company_members', { autoload: true });
    }

    _toggleFilter(spaceId) {
        this.dispatch('sync/spaces/filter_toggled', { spaceId });
    }

    _onCreateSpace() {
        this.openModal('sync.space_create', null);
    }

    _onCreateChannel(spaceId) {
        this.openModal('sync.channel_create', { spaceId });
    }

    _onAdhocCall() {
        this.dispatch('sync/calls/adhoc_create_requested', null);
    }

    _resolveFilterIds() {
        const sliceSpaces = this._spaces.slice;
        if (!sliceSpaces || !Array.isArray(sliceSpaces.sidebarSpaceFilterIds)) return [];
        return sliceSpaces.sidebarSpaceFilterIds;
    }

    _filteredTopicChannels() {
        const filterIds = this._resolveFilterIds();
        const topics = this._channels.items.filter((c) => c.type !== 'direct');
        if (filterIds.length === 0) return topics;
        return topics.filter((c) => typeof c.space_id === 'string' && filterIds.includes(c.space_id));
    }

    _directChannels() {
        return this._channels.items.filter((c) => c.type === 'direct');
    }

    render() {
        const activeFilters = this._resolveFilterIds();
        const topics = this._filteredTopicChannels();
        const directs = this._directChannels();
        return html`
            <div class="header">
                <h3>${this.t('sidebar.title')}</h3>
                <platform-button @click=${this._onAdhocCall} variant="ghost" title=${this.t('sidebar.action_adhoc_call')}>
                    <platform-icon name="phone-plus" size="16"></platform-icon>
                </platform-button>
            </div>
            ${this._spaces.items.length > 0 ? html`
                <div class="filter-bar">
                    ${this._spaces.items.map((s) => {
                        const id = resolveSpaceId(s);
                        return html`<span
                            class=${activeFilters.includes(id) ? 'tag active' : 'tag'}
                            @click=${() => this._toggleFilter(id)}
                        >${s.name}</span>`;
                    })}
                </div>
            ` : ''}
            <div class="scroll">
                <div class="section">
                    <div class="section-title">
                        ${this.t('sidebar.section_channels')}
                        <span class="add" @click=${() => this._onCreateChannel(null)}>+</span>
                    </div>
                    ${topics.map((c) => html`<sync-channel-row .channel=${c}></sync-channel-row>`)}
                </div>
                <div class="section">
                    <div class="section-title">
                        ${this.t('sidebar.section_directs')}
                    </div>
                    ${directs.map((c) => html`<sync-channel-row .channel=${c}></sync-channel-row>`)}
                </div>
                <div class="section">
                    <div class="section-title">
                        ${this.t('sidebar.section_team')}
                    </div>
                    ${this._members.items.map((m) => html`<sync-direct-member-row .member=${m}></sync-direct-member-row>`)}
                </div>
                <div class="section">
                    <div class="section-title">
                        ${this.t('sidebar.section_spaces')}
                        <span class="add" @click=${this._onCreateSpace}>+</span>
                    </div>
                </div>
            </div>
        `;
    }
}

customElements.define('sync-sidebar', SyncSidebar);
