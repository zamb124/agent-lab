/**
 * sync-channel-picker — главный экран Sync (когда канал не выбран): сетка
 * крупных карточек каналов и горизонтальная панель действий.
 *
 * Источники:
 *   useResource('sync/channels') as ControllerFor<'sync/channels'> — все каналы компании (membership).
 *
 * Действия:
 *   - клик по карточке канала → navigate('channel', { channelId })
 * Создание канала / встречи — в сайдбаре (`sync-sidebar`).
 *
 * Namespace switcher отсутствует: показываются все non-direct каналы
 * без фильтра по `state.ui.namespace`.
 *
 * Стили: только токены платформы (--accent-gradient, --glass-tint-*,
 * --border-*, --text-*, --radius-*); никаких хардкод-цветов.
 */

import type { ResourceController, ControllerFor } from '@platform/lib/base/use-resource.js';
import { html, css } from 'lit';
import type {CSSResultGroup, PropertyDeclarations, TemplateResult} from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/glass-card.js';
import './sync-chat-header.js';
import { resolveAvatarImageSrc } from '@platform/lib/utils/placeholder-avatar.js';
import { channelDisplayTitle } from './_helpers/sync-channel-display.js';
import { syncChannelPlaceholderCollection } from '../_helpers/sync-channel-placeholder-collection.js';
import { initialsFromName, syncAvatarHueVar } from '../_helpers/sync-hue.js';

export class SyncChannelPicker extends PlatformElement {
    static i18nNamespace = 'sync';

    static override properties: PropertyDeclarations = {
        _tileAvatarFailed: { state: true },
    };
    declare _tileAvatarFailed: unknown;

    static override styles: CSSResultGroup = css`
        :host {
            display: flex;
            flex-direction: column;
            flex: 1;
            min-height: 0;
            height: 100%;
            box-sizing: border-box;
            overflow: hidden;
        }
        .body {
            flex: 1;
            min-height: 0;
            overflow-y: auto;
            padding: var(--space-6);
            box-sizing: border-box;
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
    private _channels: ControllerFor<'sync/channels'>;

    constructor() {
        super();
        this._tileAvatarFailed = Object.freeze({});
        this._channels = this.useResource('sync/channels', { autoload: true });
    }

    _groupChannels() {
        return this._channels.items.filter((c: Record<string, unknown>) => c.type !== 'direct');
    }

    _onTileAvatarError(channelId: unknown) {
        if (typeof channelId !== 'string' || channelId === '') return;
        this._tileAvatarFailed = Object.freeze({ ...(this._tileAvatarFailed as Record<string, unknown>), [channelId]: true });
    }

    _renderTileAvatar(channel: Record<string, any>) {
        const seed = typeof channel.channel_id === 'string' && channel.channel_id !== '' ? channel.channel_id : 'sync';
        const hueVar = syncAvatarHueVar(seed);
        const name = typeof channel.name === 'string' && channel.name !== '' ? channel.name : '#';
        const cid = typeof channel.channel_id === 'string' ? channel.channel_id : '';
        if (cid !== '' && (this._tileAvatarFailed as Record<string, unknown>)[cid] === true) {
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

    override render(): TemplateResult {
        const channels = this._groupChannels();
        return html`
            <sync-chat-header
                header-mode="list"
                .listTitle=${this.t('channel_picker.title')}
                .listSubtitle=${this.t('channel_picker.subtitle_all_chats')}
            ></sync-chat-header>
            <div class="body">
                ${channels.length === 0 ? html`
                    <div class="empty">${this.t('channel_picker.empty')}</div>
                ` : html`
                    <div class="grid">
                        ${channels.map((c) => html`
                            <glass-card class="tile" @click=${() => this.navigate('channel', { channelId: typeof c.channel_id === 'string' ? c.channel_id : '' })}>
                                <div class="tile-head">
                                    ${this._renderTileAvatar(c)}
                                    <h3 class="tile-title">${channelDisplayTitle(c)}</h3>
                                </div>
                                <p class="tile-preview">${typeof c.last_message_preview === 'string' ? c.last_message_preview : ''}</p>
                            </glass-card>
                        `)}
                    </div>
                `}
            </div>
        `;
    }
}

customElements.define('sync-channel-picker', SyncChannelPicker);
