/**
 * sync-chat-list — единый компонент списка чатов Sync.
 *
 * Содержит:
 *   - поиск + scope-переключатель (groups/direct);
 *   - действия: adhoc call (phone-plus), STT defaults (`sync.namespace_settings` → `default`);
 *   - секция «Чаты» (`sidebar.section_chats`) с кнопкой «+» (создание канала);
 *   - объединённый список каналов и DM-партнёров через `sync-channel-row` /
 *     `sync-direct-member-row` (типизация, time, last-message, typing badge —
 *     внутри строк).
 *
 * Namespace switcher отсутствует: Sync показывает все membership-каналы
 * компании. Новые каналы / adhoc → company workspace `default`.
 *
 * Используется:
 *   1. `<sync-sidebar>` (desktop / >=768px) — в слотах `header` / default
 *      `<platform-service-sidebar>`.
 *   2. `<sync-shell-page>` (mobile / <=767px) — как основной контент главной
 *      страницы `/sync`.
 *
 * Атрибут `mode`:
 *   - `'sidebar'` (default): компактные отступы под `<platform-service-sidebar>`.
 *   - `'page'`: полноэкранный мобильный режим.
 */

import type { OpController, ResourceController, ControllerFor } from '@platform/lib/base/use-resource.js';
import { html, css } from 'lit';
import type {CSSResultGroup, PropertyDeclarations, TemplateResult} from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import {
    sidebarNavItemStyles,
    sidebarSectionStyles,
} from '@platform/lib/styles/shared/sidebar.styles.js';
import { resolveDisplayName } from '../_helpers/sync-id-resolvers.js';
import '@platform/lib/components/platform-icon.js';
import './sync-channel-row.js';
import './sync-direct-member-row.js';

const DEFAULT_NAMESPACE = 'default';

export class SyncChatList extends PlatformElement {
    static i18nNamespace = 'sync';

    static override properties: PropertyDeclarations = {
        mode: { type: String, reflect: true },
    };
    declare mode: string;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        sidebarNavItemStyles,
        sidebarSectionStyles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                width: 100%;
                min-width: 0;
                box-sizing: border-box;
                --sidebar-nav-inline: var(--space-1);
            }

            :host([mode='sidebar']) {
                flex: 1;
                min-height: 0;
                overflow: hidden;
            }

            :host([mode='page']) {
                flex: 1;
                min-height: 0;
                height: 100%;
                overflow: hidden;
                --sidebar-nav-inline: var(--space-3);
            }

            .header {
                display: flex;
                flex-direction: column;
                width: 100%;
                box-sizing: border-box;
                gap: var(--space-2);
                background: transparent;
                padding-bottom: var(--space-2);
                margin-bottom: var(--space-2);
                flex-shrink: 0;
            }

            :host([mode='page']) .header {
                padding: var(--space-3) var(--space-4) var(--space-2);
                border-bottom: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.06));
            }

            .header-actions {
                display: flex;
                align-items: center;
                justify-content: flex-end;
                gap: var(--space-1);
                padding: 0 var(--space-1);
            }

            .header-action-btn {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 36px;
                height: 36px;
                padding: 0;
                border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.06));
                border-radius: var(--radius-full, 999px);
                background: var(--glass-tint-subtle, rgba(255, 255, 255, 0.04));
                color: var(--text-secondary);
                cursor: pointer;
                transition: background var(--duration-fast), color var(--duration-fast), border-color var(--duration-fast);
            }
            .header-action-btn:hover {
                color: var(--accent);
                border-color: var(--accent);
                background: var(--accent-subtle, rgba(153, 166, 249, 0.16));
            }
            .header-action-btn:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }

            .search-box {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-3) var(--space-4);
                min-height: var(--button-height, 44px);
                background: var(--glass-tint-subtle, rgba(255, 255, 255, 0.04));
                border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.06));
                border-radius: var(--radius-full, 999px);
                color: var(--text-secondary);
                box-sizing: border-box;
                transition: border-color var(--duration-fast), box-shadow var(--duration-fast);
            }
            .search-box:focus-within {
                border-color: var(--accent);
                color: var(--accent);
                box-shadow: 0 0 0 4px var(--accent-subtle, rgba(153, 166, 249, 0.16));
            }
            .search-box input[data-canon='search-as-you-type'] {
                flex: 1;
                min-width: 0;
                background: transparent;
                border: none;
                outline: none;
                color: var(--text-primary);
                font-size: var(--text-base);
                line-height: 1.35;
            }
            .search-box input::placeholder { color: var(--text-tertiary); }

            .search-scope {
                display: inline-flex;
                flex-shrink: 0;
                align-items: center;
                gap: 0;
                padding: 2px;
                margin-left: 2px;
                border-radius: var(--radius-full, 999px);
                background: color-mix(in srgb, var(--glass-hover) 65%, transparent);
            }
            .search-scope-btn {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 26px;
                height: 26px;
                padding: 0;
                border: none;
                border-radius: var(--radius-full, 999px);
                background: transparent;
                color: var(--text-tertiary);
                cursor: pointer;
                transition: background var(--duration-fast), color var(--duration-fast);
            }
            .search-scope-btn:hover { color: var(--text-secondary); background: var(--glass-hover); }
            .search-scope-btn.is-active {
                color: var(--accent);
                background: var(--glass-solid-soft, rgba(255, 255, 255, 0.1));
            }

            .body {
                flex: 1 1 auto;
                min-height: 0;
                width: 100%;
                box-sizing: border-box;
            }

            :host([mode='sidebar']) .body {
                display: flex;
                flex-direction: column;
                overflow: hidden;
            }

            :host([mode='sidebar']) .section {
                margin-bottom: 0;
            }

            :host([mode='sidebar']) .section-content {
                overflow-y: auto;
                overscroll-behavior: contain;
                -webkit-overflow-scrolling: touch;
                padding-bottom: var(--space-2);
            }

            :host([mode='page']) .body {
                overflow-y: auto;
                -webkit-overflow-scrolling: touch;
                padding: var(--space-2) var(--space-3) var(--space-6);
            }

            .empty-row {
                padding: var(--space-2) var(--space-3);
                color: var(--text-tertiary);
                font-size: var(--text-xs);
            }

            .section-subheader {
                padding: var(--space-3) var(--space-3) var(--space-1);
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                text-transform: uppercase;
                letter-spacing: 0.06em;
            }

            .section-content {
                gap: var(--space-1);
            }
        `,
    ];
    private _channels: ControllerFor<'sync/channels'>;
    private _members: ResourceController;
    private _chatUi: ControllerFor<'sync/chat_ui'>;
    private _callUi: ControllerFor<'sync/call_ui'>;
    private _adhoc: OpController;
    private _callInvite: OpController;

    constructor() {
        super();
        this.mode = 'sidebar';
        this._channels = this.useResource('sync/channels', { autoload: true });
        this._members = this.useResource('sync/company_members', { autoload: true });
        this._chatUi = this.useSlice('sync/chat_ui');
        this._callUi = this.useSlice('sync/call_ui');
        this._adhoc = this.useOp('sync/channel_create_adhoc_call');
        this._callInvite = this.useOp('sync/calls_invite');
    }

    _searchQuery() {
        const slice = this._chatUi.value;
        if (!slice || typeof slice.sidebarSearchQuery !== 'string') return '';
        return slice.sidebarSearchQuery.trim().toLowerCase();
    }

    _searchScope() {
        const slice = this._chatUi.value;
        const s = slice && typeof slice.sidebarSearchScope === 'string' ? slice.sidebarSearchScope : 'all';
        if (s === 'groups' || s === 'direct') return s;
        return 'all';
    }

    _channelMatchesScope(channel: Record<string, any>, scope: string) {
        if (scope === 'all') return true;
        if (scope === 'groups') return channel.type !== 'direct';
        if (scope === 'direct') return channel.type === 'direct';
        return true;
    }

    _channelMatchesSearch(channel: Record<string, any>, search: string) {
        if (search === '') return true;
        if (channel.type === 'direct') {
            const peerName = channel.peer && typeof channel.peer.display_name === 'string'
                ? channel.peer.display_name.toLowerCase()
                : '';
            return peerName.includes(search);
        }
        const title = typeof channel.name === 'string' ? channel.name.toLowerCase() : '';
        return title.includes(search);
    }

    _unifiedChats() {
        const search = this._searchQuery();
        const scope = this._searchScope();
        const filtered = this._channels.items.filter((c) => (
            this._channelMatchesSearch(c, search)
            && this._channelMatchesScope(c, scope)
        ));
        return filtered.slice().sort((a, b) => {
            const ta = typeof a.last_message_at === 'string' ? a.last_message_at : '';
            const tb = typeof b.last_message_at === 'string' ? b.last_message_at : '';
            if (ta === tb) return 0;
            return ta < tb ? 1 : -1;
        });
    }

    _membersWithoutDm() {
        if (this._searchScope() === 'groups') return [];
        const directs = this._channels.items.filter((c: Record<string, any>) => c.type === 'direct');
        const dmUserIds = new Set<string>();
        for (const dm of directs) {
            const peer = dm.peer as Record<string, unknown> | undefined;
            if (peer && typeof peer.user_id === 'string') dmUserIds.add(peer.user_id);
        }
        const search = this._searchQuery();
        let members = this._members.items.filter((m: Record<string, any>) => !dmUserIds.has(m.user_id));
        if (search !== '') {
            members = members.filter((m: Record<string, any>) => resolveDisplayName(m).toLowerCase().includes(search));
        }
        return members;
    }

    _onOpenNamespaceSettings() {
        this.openModal('sync.namespace_settings', { name: DEFAULT_NAMESPACE });
    }

    _onCreateChannel() {
        this.openModal('sync.channel_create', { namespace: DEFAULT_NAMESPACE });
    }

    /**
     * Создание канала-встречи + invite + open overlay — единый путь и из сайдбара,
     * и из мобильной главной страницы. Логика идентична кнопке «Позвонить» в шапке.
     */
    async _startAdhocCallSession(channelId: string) {
        if (typeof channelId !== 'string' || channelId === '') return;
        await this._callInvite.run({ channel_id: channelId });
        const inv = this._callInvite.lastResult as Record<string, unknown> | null;
        if (!inv || typeof inv.call_id !== 'string') return;
        this._callUi.openOverlay({
            call_id: inv.call_id,
            channel_id: typeof inv.channel_id === 'string' ? inv.channel_id : channelId,
            call_type: typeof inv.call_type === 'string' ? inv.call_type : 'video',
            livekit_room_name: typeof inv.livekit_room_name === 'string' ? inv.livekit_room_name : null,
            livekit_url: typeof inv.livekit_url === 'string' ? inv.livekit_url : null,
        });
        this.openModal('sync.call_overlay', {
            callId: inv.call_id,
            channelId: typeof inv.channel_id === 'string' ? inv.channel_id : channelId,
        });
    }

    async _onAdhocCall() {
        if (this._adhoc.busy || this._callInvite.busy) return;
        const now = new Date();
        const dateStr = now.toLocaleDateString();
        const timeStr = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        const name = this.t('chat_view.adhoc_meet_channel_name', { date: dateStr, time: timeStr });
        const result = await this._adhoc.run({
            name,
            type: 'group',
            namespace: DEFAULT_NAMESPACE,
        });
        const channelId = result && typeof (result as Record<string, unknown>).channel_id === 'string'
            ? (result as { channel_id: string }).channel_id
            : null;
        if (channelId === null) return;
        this.navigate('channel', { channelId });
        this.emit('adhoc-call-started', { channelId });
        await this._startAdhocCallSession(channelId);
    }

    _onSearchInput(e: Event) {
        const value = typeof (e.target as HTMLInputElement | null)?.value === 'string'
            ? (e.target as HTMLInputElement).value
            : '';
        this._chatUi.setSidebarSearch({ query: value });
    }

    _onSearchScopeToggle(e: Event, kind: string) {
        e.stopPropagation();
        const cur = this._searchScope();
        if (kind === 'groups') {
            const next = cur === 'groups' ? 'all' : 'groups';
            this._chatUi.setSidebarSearchScope({ scope: next });
            return;
        }
        if (kind === 'direct') {
            const next = cur === 'direct' ? 'all' : 'direct';
            this._chatUi.setSidebarSearchScope({ scope: next });
        }
    }

    renderHeader() {
        const search = this._chatUi.value && typeof this._chatUi.value.sidebarSearchQuery === 'string'
            ? this._chatUi.value.sidebarSearchQuery
            : '';
        const scope = this._searchScope();
        return html`
            <div class="header">
                <div class="header-actions">
                    <button
                        type="button"
                        class="header-action-btn"
                        @click=${this._onOpenNamespaceSettings}
                        title=${this.t('sidebar.sync_defaults_tooltip')}
                        aria-label=${this.t('sidebar.sync_defaults_aria')}
                    >
                        <platform-icon name="settings" size="16"></platform-icon>
                    </button>
                    <button
                        type="button"
                        class="header-action-btn"
                        @click=${this._onAdhocCall}
                        ?disabled=${this._adhoc.busy || this._callInvite.busy}
                        title=${this.t('sidebar.create_sync_title')}
                        aria-label=${this.t('sidebar.namespace_meeting_btn')}
                    >
                        <platform-icon name="phone-plus" size="16"></platform-icon>
                    </button>
                </div>
                <div class="search-box">
                    <platform-icon name="search" size="14"></platform-icon>
                    <input
                        class="sync-chat-list-search-input"
                        type="text"
                        data-canon="search-as-you-type"
                        .value=${search}
                        @input=${this._onSearchInput}
                        placeholder=${this.t('sidebar.direct_search_placeholder')}
                        aria-label=${this.t('sidebar.direct_search_aria')}
                    />
                    <div
                        class="search-scope"
                        role="group"
                        aria-label=${this.t('sidebar.search_scope_group_aria')}
                    >
                        <button
                            type="button"
                            class="search-scope-btn ${scope === 'groups' ? 'is-active' : ''}"
                            title=${this.t('sidebar.search_scope_groups_title')}
                            aria-label=${this.t('sidebar.search_scope_groups_title')}
                            aria-pressed=${scope === 'groups'}
                            @click=${(ev: Event) => this._onSearchScopeToggle(ev, 'groups')}
                        ><platform-icon name="users" size="12"></platform-icon></button>
                        <button
                            type="button"
                            class="search-scope-btn ${scope === 'direct' ? 'is-active' : ''}"
                            title=${this.t('sidebar.search_scope_direct_title')}
                            aria-label=${this.t('sidebar.search_scope_direct_title')}
                            aria-pressed=${scope === 'direct'}
                            @click=${(ev: Event) => this._onSearchScopeToggle(ev, 'direct')}
                        ><platform-icon name="user" size="12"></platform-icon></button>
                    </div>
                </div>
            </div>
        `;
    }

    renderChats() {
        const chats = this._unifiedChats();
        const members = this._membersWithoutDm();
        const empty = chats.length === 0 && members.length === 0;
        return html`
            <div class="body">
                <div class="section">
                    <div class="section-header">
                        <span class="section-title">${this.t('sidebar.section_chats')}</span>
                        <div class="section-actions">
                            <button
                                type="button"
                                class="section-action-btn"
                                @click=${this._onCreateChannel}
                                title=${this.t('sidebar.create_channel_title')}
                            >
                                <platform-icon name="plus" size="14"></platform-icon>
                            </button>
                        </div>
                    </div>
                    <div class="section-content">
                        ${chats.map((c) => html`<sync-channel-row .channel=${c}></sync-channel-row>`)}
                        ${members.length > 0 ? html`
                            <div class="section-subheader">${this.t('sidebar.subheader_start_dm')}</div>
                            ${members.map((m) => html`<sync-direct-member-row .member=${m}></sync-direct-member-row>`)}
                        ` : ''}
                        ${empty ? html`<div class="empty-row">${this.t('sidebar.no_chats_yet')}</div>` : ''}
                    </div>
                </div>
            </div>
        `;
    }

    override render(): TemplateResult {
        return html`
            ${this.renderHeader()}
            ${this.renderChats()}
        `;
    }
}

customElements.define('sync-chat-list', SyncChatList);
