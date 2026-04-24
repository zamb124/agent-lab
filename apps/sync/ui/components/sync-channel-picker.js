/**
 * sync-channel-picker — главный экран Sync (когда канал не выбран): сетка
 * крупных карточек каналов и горизонтальная панель действий.
 *
 * Источники:
 *   useResource('sync/channels')   — все каналы.
 *   useResource('sync/namespaces') — список платформенных namespace.
 *
 * Действия:
 *   - клик по карточке канала → navigate('channel', { channelId })
 * Создание канала / встречи — в сайдбаре (`sync-sidebar`).
 *
 * Активный namespace — `getPlatformNamespaceSidebarSelection(company_id)`
 * (тот же глобальный селект, что и в CRM); фильтрация — по
 * `channel.namespace`.
 *
 * Стили: только токены платформы (--accent-gradient, --glass-tint-*,
 * --border-*, --text-*, --radius-*); никаких хардкод-цветов.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { getPlatformNamespaceSidebarSelection } from '@platform/lib/utils/platform-namespace.js';
import '@platform/lib/components/glass-card.js';
import { resolveAvatarImageSrc } from '@platform/lib/utils/placeholder-avatar.js';
import { channelDisplayTitle } from './_helpers/sync-channel-display.js';
import { syncChannelPlaceholderCollection } from '../_helpers/sync-channel-placeholder-collection.js';
import { initialsFromName, syncAvatarHueVar } from '../_helpers/sync-hue.js';

export class SyncChannelPicker extends PlatformElement {
    static properties = {
        _tileAvatarFailed: { state: true },
    };

    static styles = css`
        :host {
            display: block;
            padding: var(--space-6);
            overflow-y: auto;
            height: 100%;
            box-sizing: border-box;
        }
        .header {
            margin-bottom: var(--space-5);
        }
        h2 {
            margin: 0;
            font-size: var(--text-2xl);
            font-weight: var(--font-bold);
            color: var(--text-primary);
        }
        .filters {
            display: flex;
            flex-wrap: wrap;
            gap: var(--space-2);
            margin-bottom: var(--space-5);
        }
        .filter {
            padding: 6px var(--space-3);
            border-radius: var(--radius-full);
            background: var(--glass-tint-subtle, rgba(255, 255, 255, 0.04));
            border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.06));
            color: var(--text-secondary);
            cursor: pointer;
            font-size: var(--text-sm);
            font-weight: var(--font-medium);
            user-select: none;
            transition: all var(--duration-fast) var(--easing-default);
        }
        .filter:hover {
            background: var(--glass-tint-medium, rgba(255, 255, 255, 0.08));
            color: var(--text-primary);
        }
        .filter.active {
            background: var(--accent-subtle, rgba(153, 166, 249, 0.18));
            border-color: var(--accent);
            color: var(--accent);
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
            gap: var(--space-4);
        }
        .tile {
            cursor: pointer;
            padding: var(--space-4);
            display: flex;
            flex-direction: column;
            gap: var(--space-2);
            transition: transform var(--duration-fast) var(--easing-default),
                        box-shadow var(--duration-fast) var(--easing-default);
        }
        .tile:hover {
            transform: translateY(-2px);
        }
        .tile-head {
            display: flex;
            align-items: center;
            gap: var(--space-3);
        }
        .tile-avatar {
            width: 40px;
            height: 40px;
            border-radius: var(--radius-md);
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-weight: var(--font-semibold);
            font-size: var(--text-sm);
            flex-shrink: 0;
            overflow: hidden;
            background: var(--accent-subtle, rgba(99, 102, 241, 0.12));
        }
        .tile-avatar.pastel-initials {
            --sync-avatar-h: 0;
            background: hsl(var(--sync-avatar-h), var(--sync-pastel-avatar-s-bg), var(--sync-pastel-avatar-l-bg));
            color: hsl(var(--sync-avatar-h), var(--sync-pastel-avatar-s-fg), var(--sync-pastel-avatar-l-fg));
        }
        .tile-title {
            margin: 0;
            font-size: var(--text-base);
            font-weight: var(--font-semibold);
            color: var(--text-primary);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            flex: 1;
            min-width: 0;
        }
        .tile-preview {
            margin: 0;
            color: var(--text-secondary);
            font-size: var(--text-sm);
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
            min-height: 40px;
        }
        .empty {
            color: var(--text-tertiary);
            font-size: var(--text-base);
            padding: var(--space-6);
            text-align: center;
        }
    `;

    constructor() {
        super();
        this._tileAvatarFailed = Object.freeze({});
        this._channels = this.useResource('sync/channels', { autoload: true });
        this._namespaces = this.useResource('sync/namespaces', { autoload: true });
        this._authSel = this.select((s) => s.auth && s.auth.user ? s.auth.user : null);
        this._uiNsSel = this.select((s) => s.ui.namespace);
    }

    _activeNamespace() {
        const user = this._authSel.value;
        if (!user || typeof user.company_id !== 'string' || user.company_id === '') return 'all';
        return getPlatformNamespaceSidebarSelection(user.company_id);
    }

    _activeNamespaceItem() {
        const activeNs = this._activeNamespace();
        if (activeNs === 'all') return null;
        return this._namespaces.items.find((ns) => ns.name === activeNs) || null;
    }

    _filteredChannels() {
        const activeNs = this._activeNamespace();
        const all = this._channels.items.filter((c) => c.type !== 'direct');
        if (activeNs === 'all') return all;
        return all.filter((c) => typeof c.namespace === 'string' && c.namespace === activeNs);
    }

    _onTileAvatarError(channelId) {
        if (typeof channelId !== 'string' || channelId === '') return;
        this._tileAvatarFailed = Object.freeze({ ...this._tileAvatarFailed, [channelId]: true });
    }

    _renderTileAvatar(channel) {
        const seed = typeof channel.id === 'string' && channel.id !== '' ? channel.id : 'sync';
        const hueVar = syncAvatarHueVar(seed);
        const name = typeof channel.name === 'string' && channel.name !== '' ? channel.name : '#';
        const cid = typeof channel.id === 'string' ? channel.id : '';
        if (cid !== '' && this._tileAvatarFailed[cid] === true) {
            return html`<span class="tile-avatar pastel-initials" style=${hueVar}>${initialsFromName(name)}</span>`;
        }
        const chUrl = typeof channel.avatar_url === 'string' && channel.avatar_url !== ''
            ? channel.avatar_url
            : null;
        const resolved = resolveAvatarImageSrc({
            avatarUrl: chUrl,
            seed,
            collection: syncChannelPlaceholderCollection(channel),
        });
        return html`<span class="tile-avatar">
            <img
                src=${resolved.src}
                alt=""
                style="width:100%;height:100%;border-radius:inherit;object-fit:cover;"
                @error=${() => this._onTileAvatarError(cid)}
            />
        </span>`;
    }

    render() {
        const filtered = this._filteredChannels();
        const activeNs = this._activeNamespace();
        const activeNsItem = this._activeNamespaceItem();
        const headerTitle = activeNsItem
            ? activeNsItem.name
            : this.t('channel_picker.title');
        return html`
            <div class="header">
                <h2>${headerTitle}</h2>
            </div>
            <div class="filters">
                ${activeNs === 'all'
                    ? html`<span class="filter active">${this.t('sidebar.all_namespaces')}</span>`
                    : html`<span class="filter active">${activeNs}</span>`}
            </div>
            ${filtered.length === 0 ? html`
                <div class="empty">${this.t('channel_picker.empty')}</div>
            ` : html`
                <div class="grid">
                    ${filtered.map((c) => html`
                        <glass-card class="tile" @click=${() => this.navigate('channel', { channelId: c.id })}>
                            <div class="tile-head">
                                ${this._renderTileAvatar(c)}
                                <h3 class="tile-title">${channelDisplayTitle(c)}</h3>
                            </div>
                            <p class="tile-preview">${typeof c.last_message_preview === 'string' ? c.last_message_preview : ''}</p>
                        </glass-card>
                    `)}
                </div>
            `}
        `;
    }
}

customElements.define('sync-channel-picker', SyncChannelPicker);
