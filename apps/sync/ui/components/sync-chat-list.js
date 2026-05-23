/**
 * sync-chat-list — единый компонент списка чатов Sync.
 *
 * Содержит:
 *   - действие «создать митинг» (adhoc call) — кнопка в строке селектора пространства;
 *   - селектор платформенного namespace + поиск + scope-переключатель (groups/direct);
 *   - секция «Чаты» (`sidebar.section_chats`) с кнопкой «+» (создание канала);
 *   - объединённый список каналов и DM-партнёров через `sync-channel-row` /
 *     `sync-direct-member-row` (типизация, time, last-message, typing badge —
 *     внутри строк).
 *
 * Используется:
 *   1. `<sync-sidebar>` (desktop / >=768px) — в слотах `header` / default
 *      `<platform-service-sidebar>`.
 *   2. `<sync-shell-page>` (mobile / <=767px) — как основной контент главной
 *      страницы `/sync`, чтобы мобильный пользователь получал ровно тот же
 *      UX, что и в боковой панели десктопа (поиск, typing, settings и т.п.).
 *
 * Атрибут `mode`:
 *   - `'sidebar'` (default): компактные отступы под `<platform-service-sidebar>`,
 *     заголовок секции «Чаты» с тёмным фоном (sidebarSectionStyles).
 *   - `'page'`: полноэкранный мобильный режим — отступы крупнее, шапка
 *     поднимается над списком, нет лимитов на ширину; работает в паре с
 *     платформенным top-bar'ом и нижней навигацией (mobile shell 2026).
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import {
    sidebarNavItemStyles,
    sidebarSectionStyles,
} from '@platform/lib/styles/shared/sidebar.styles.js';
import {
    setPlatformNamespaceSelection,
    getPlatformNamespaceSidebarSelection,
} from '@platform/lib/utils/platform-namespace.js';
import { resolveDisplayName } from '../_helpers/sync-id-resolvers.js';
import '@platform/lib/components/layout/platform-sidebar-namespace-select.js';
import '@platform/lib/components/platform-icon.js';
import './sync-channel-row.js';
import './sync-direct-member-row.js';

export class SyncChatList extends PlatformElement {
    static i18nNamespace = 'sync';

    static properties = {
        mode: { type: String, reflect: true },
    };

    static styles = [
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
                background: var(--glass-tint-subtle, rgba(255, 255, 255, 0.02));
                backdrop-filter: blur(var(--glass-blur-medium));
                -webkit-backdrop-filter: blur(var(--glass-blur-medium));
                padding-bottom: var(--space-2);
                margin-bottom: var(--space-2);
                flex-shrink: 0;
            }

            /* sidebar-режим: контейнер прокрутки — .sidebar-nav снаружи, header'у
               нужно «прилипать» к верху списка как раньше делала .sidebar-header. */
            :host([mode='sidebar']) .header {
                position: sticky;
                top: 0;
                z-index: 2;
            }

            /* page-режим: внутренний body имеет свой overflow, header — обычный
               flex-child, который занимает фиксированную высоту сверху. */
            :host([mode='page']) .header {
                padding: var(--space-3) var(--space-4) var(--space-2);
                border-bottom: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.06));
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

    constructor() {
        super();
        this.mode = 'sidebar';
        this._namespaces = this.useResource('sync/namespaces', { autoload: true });
        this._channels = this.useResource('sync/channels', { autoload: true });
        this._members = this.useResource('sync/company_members', { autoload: true });
        this._chatUi = this.useSlice('sync/chat_ui');
        this._callUi = this.useSlice('sync/call_ui');
        this._adhoc = this.useOp('sync/channel_create_adhoc_call');
        this._callInvite = this.useOp('sync/calls_invite');
        this._authSel = this.select((s) => s.auth && s.auth.user ? s.auth.user : null);
        this._uiNsSel = this.select((s) => s.ui.namespace);
    }

    _activeNamespace() {
        const user = this._authSel.value;
        if (!user || typeof user.company_id !== 'string' || user.company_id === '') return 'all';
        return getPlatformNamespaceSidebarSelection(user.company_id);
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

    _channelMatchesScope(channel, scope) {
        if (scope === 'all') return true;
        if (scope === 'groups') return channel.type !== 'direct';
        if (scope === 'direct') return channel.type === 'direct';
        return true;
    }

    _channelMatchesSearch(channel, search) {
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

    _channelMatchesNamespace(channel, activeNs) {
        if (activeNs === 'all') return true;
        if (channel.type === 'direct') return false;
        return typeof channel.namespace === 'string' && channel.namespace === activeNs;
    }

    _unifiedChats() {
        const activeNs = this._activeNamespace();
        const search = this._searchQuery();
        const scope = this._searchScope();
        const filtered = this._channels.items.filter((c) => (
            this._channelMatchesNamespace(c, activeNs)
            && this._channelMatchesSearch(c, search)
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
        if (this._activeNamespace() !== 'all') return [];
        const directs = this._channels.items.filter((c) => c.type === 'direct');
        const dmUserIds = new Set();
        for (const dm of directs) {
            if (dm.peer && typeof dm.peer.user_id === 'string') dmUserIds.add(dm.peer.user_id);
        }
        const search = this._searchQuery();
        let members = this._members.items.filter((m) => !dmUserIds.has(m.user_id));
        if (search !== '') {
            members = members.filter((m) => resolveDisplayName(m).toLowerCase().includes(search));
        }
        return members;
    }

    _activeNamespaceItem() {
        const activeNs = this._activeNamespace();
        if (activeNs === 'all') return null;
        return this._namespaces.items.find((ns) => ns.name === activeNs) || null;
    }

    _namespaceEnumHeaderConfig() {
        const items = this._namespaces.items;
        if (!Array.isArray(items)) {
            throw new Error('SyncChatList._namespaceEnumHeaderConfig: items must be an array');
        }
        const values = [{ value: '', label: this.t('sidebar.all_namespaces') }];
        for (const ns of items) {
            if (!ns || typeof ns.name !== 'string' || ns.name.length === 0) {
                throw new Error('SyncChatList._namespaceEnumHeaderConfig: invalid namespace item');
            }
            values.push({ value: ns.name, label: ns.name });
        }
        return { values };
    }

    _onNamespaceChange(e) {
        const user = this._authSel.value;
        if (!user || typeof user.company_id !== 'string' || user.company_id === '') {
            throw new Error('SyncChatList: cannot change namespace without active company_id');
        }
        const raw = e.detail && typeof e.detail.value === 'string' ? e.detail.value : '';
        setPlatformNamespaceSelection(user.company_id, raw === '' ? null : raw);
    }

    _onEditActiveNamespace() {
        const ns = this._activeNamespaceItem();
        if (!ns) return;
        this.openModal('sync.namespace_settings', { name: ns.name });
    }

    _onCreateChannel() {
        const ns = this._activeNamespaceItem();
        const namespace = ns ? ns.name : null;
        this.openModal('sync.channel_create', { namespace });
    }

    /**
     * Создание канала-встречи + invite + open overlay — единый путь и из сайдбара,
     * и из мобильной главной страницы. Логика идентична кнопке «Позвонить» в шапке.
     */
    async _startAdhocCallSession(channelId) {
        if (typeof channelId !== 'string' || channelId === '') return;
        await this._callInvite.run({ channel_id: channelId });
        const inv = this._callInvite.lastResult;
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
        const ns = this._activeNamespaceItem();
        const payload = { name, type: 'group' };
        if (ns !== null) payload.namespace = ns.name;
        const result = await this._adhoc.run(payload);
        const channelId = result && typeof result.channel_id === 'string' ? result.channel_id : null;
        if (channelId === null) return;
        this.navigate('channel', { channelId });
        this.emit('adhoc-call-started', { channelId });
        await this._startAdhocCallSession(channelId);
    }

    _onSearchInput(e) {
        const value = typeof e.target.value === 'string' ? e.target.value : '';
        this._chatUi.setSidebarSearch({ query: value });
    }

    _onSearchScopeToggle(e, kind) {
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
        const activeNs = this._activeNamespace();
        const selectValue = activeNs === 'all' ? '' : activeNs;
        const search = this._chatUi.value && typeof this._chatUi.value.sidebarSearchQuery === 'string'
            ? this._chatUi.value.sidebarSearchQuery
            : '';
        const scope = this._searchScope();
        return html`
            <div class="header">
                <platform-sidebar-namespace-select
                    .label=${this.t('sidebar.namespace_label')}
                    .value=${selectValue}
                    .config=${this._namespaceEnumHeaderConfig()}
                    ?show-edit=${selectValue !== '' && this._activeNamespaceItem() !== null}
                    ?show-add=${false}
                    edit-icon="settings"
                    edit-title=${this.t('sidebar.edit_namespace_tooltip')}
                    @change=${this._onNamespaceChange}
                    @edit-request=${this._onEditActiveNamespace}
                >
                    <button
                        type="button"
                        slot="trailing"
                        class="platform-namespace-trailing-action-btn"
                        @click=${this._onAdhocCall}
                        ?disabled=${this._adhoc.busy || this._callInvite.busy}
                        title=${this.t('sidebar.create_sync_title')}
                        aria-label=${this.t('sidebar.namespace_meeting_btn')}
                    >
                        <platform-icon name="phone-plus" size="16"></platform-icon>
                    </button>
                </platform-sidebar-namespace-select>
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
                            @click=${(ev) => this._onSearchScopeToggle(ev, 'groups')}
                        ><platform-icon name="users" size="12"></platform-icon></button>
                        <button
                            type="button"
                            class="search-scope-btn ${scope === 'direct' ? 'is-active' : ''}"
                            title=${this.t('sidebar.search_scope_direct_title')}
                            aria-label=${this.t('sidebar.search_scope_direct_title')}
                            aria-pressed=${scope === 'direct'}
                            @click=${(ev) => this._onSearchScopeToggle(ev, 'direct')}
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
        const activeNs = this._activeNamespace();
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
                        ${empty ? html`<div class="empty-row">${
                            activeNs !== 'all'
                                ? this.t('sidebar.no_channels_in_namespace')
                                : this.t('sidebar.no_chats_yet')
                        }</div>` : ''}
                    </div>
                </div>
            </div>
        `;
    }

    render() {
        return html`
            ${this.renderHeader()}
            ${this.renderChats()}
        `;
    }
}

customElements.define('sync-chat-list', SyncChatList);
