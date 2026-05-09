/**
 * SyncSidebar — навигация Sync на каноничной оболочке `platform-service-sidebar`.
 *
 * Активное «пространство» выбирается тем же глобальным селектом
 * платформенного namespace, что и в CRM (`setPlatformNamespaceSelection` /
 * `getPlatformNamespaceSidebarSelection`). Источник списка namespace —
 * фабрика `sync/namespaces` (autoload через `useResource`), напрямую
 * читает `core/db/repositories/namespace_repository.py` через
 * `GET /sync/api/v1/namespaces`. При выборе конкретного namespace список
 * каналов фильтруется по `channel.namespace`; при «Все» — видны все
 * каналы и DM-участники.
 *
 * Создание namespace — в CRM (`crm.namespace`-modal); sync редактирует
 * только `Namespace.sync_settings` через карандаш на выбранном namespace
 * (`sync.namespace_settings`).
 *
 * Slots `<platform-service-sidebar>`:
 *   - header: ad-hoc встреча, namespace selector, поиск.
 *   - default (nav): единая секция «Чаты» — каналы + DM-участники.
 *   - footer: <platform-user block>.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import {
    sidebarStyles,
    sidebarNavItemStyles,
    sidebarSectionStyles,
} from '@platform/lib/styles/shared/sidebar.styles.js';
import { readShellSidebarCollapsed } from '@platform/lib/utils/shell-sidebar-preference.js';
import {
    setPlatformNamespaceSelection,
    getPlatformNamespaceSidebarSelection,
} from '@platform/lib/utils/platform-namespace.js';
import { resolveDisplayName } from '../_helpers/sync-id-resolvers.js';
import '@platform/lib/components/layout/platform-service-sidebar.js';
import '@platform/lib/components/layout/platform-sidebar-namespace-select.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-user.js';
import '@platform/lib/components/platform-notification-manager.js';
import './sync-channel-row.js';
import './sync-direct-member-row.js';

export class SyncSidebar extends PlatformElement {
    static i18nNamespace = 'sync';

    static properties = {
        collapsed: { type: Boolean, reflect: true },
        mobileOpen: { type: Boolean, reflect: true, attribute: 'mobile-open' },
    };

    static styles = [
        PlatformElement.styles,
        sidebarStyles,
        sidebarNavItemStyles,
        sidebarSectionStyles,
        css`
            :host {
                display: block;
                height: 100%;
                --sidebar-nav-inline: var(--space-1);
            }

            platform-service-sidebar {
                --sidebar-logo-text-weight: 700;
                --sidebar-logo-text-gradient: var(--accent-gradient);
                --sidebar-logo-text-clip: text;
                --sidebar-logo-text-fill: transparent;
            }

            .sync-sidebar-header-inner {
                display: flex;
                flex-direction: column;
                width: 100%;
                min-width: 0;
                box-sizing: border-box;
            }

            .header-adhoc {
                display: flex;
                flex-direction: column;
                width: 100%;
                box-sizing: border-box;
                margin-bottom: var(--space-2);
            }

            .header-area {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                width: 100%;
                box-sizing: border-box;
            }

            .adhoc-btn {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                gap: var(--space-2);
                width: 100%;
                padding: var(--space-3) var(--space-4);
                border: none;
                border-radius: var(--radius-full, 999px);
                background: var(--accent);
                color: var(--text-inverse);
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                cursor: pointer;
                box-sizing: border-box;
                transition: transform var(--duration-fast), box-shadow var(--duration-fast), background var(--duration-fast);
                box-shadow: 0 2px 8px var(--accent-subtle, rgba(153, 166, 249, 0.18));
            }
            .adhoc-btn:hover { background: var(--accent-hover, var(--accent)); }
            .adhoc-btn:hover { transform: translateY(-1px); }
            .adhoc-btn:active { transform: translateY(0); }
            .adhoc-btn:disabled { opacity: 0.6; cursor: wait; transform: none; box-shadow: none; }

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
            .search-box input[data-canon="search-as-you-type"] {
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
            .search-scope-btn:hover {
                color: var(--text-secondary);
                background: var(--glass-hover);
            }
            .search-scope-btn.is-active {
                color: var(--accent);
                background: var(--glass-solid-soft, rgba(255, 255, 255, 0.1));
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

            .user-section {
                display: flex;
                flex-direction: column;
                gap: 0;
                width: 100%;
                min-width: 0;
                padding: var(--space-3) var(--sidebar-nav-inline) 0;
                margin-top: 0;
                box-sizing: border-box;
            }

            platform-service-sidebar[collapsed] platform-sidebar-namespace-select,
            platform-service-sidebar[collapsed] .search-box,
            platform-service-sidebar[collapsed] .section-header,
            platform-service-sidebar[collapsed] .section-subheader { display: none; }
            platform-service-sidebar[collapsed] .sync-sidebar-header-inner .header-adhoc {
                align-items: center;
                margin-bottom: var(--space-3);
            }
            platform-service-sidebar[collapsed] .adhoc-btn {
                width: auto;
                min-width: 40px;
                min-height: 40px;
                padding: var(--space-2);
            }
            platform-service-sidebar[collapsed] .adhoc-btn span { display: none; }
        `,
    ];

    constructor() {
        super();
        this.collapsed = readShellSidebarCollapsed();
        this.mobileOpen = false;
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
            throw new Error('SyncSidebar._namespaceEnumHeaderConfig: items must be an array');
        }
        const values = [{ value: '', label: this.t('sidebar.all_namespaces') }];
        for (const ns of items) {
            if (!ns || typeof ns.name !== 'string' || ns.name.length === 0) {
                throw new Error('SyncSidebar._namespaceEnumHeaderConfig: invalid namespace item');
            }
            values.push({ value: ns.name, label: ns.name });
        }
        return { values };
    }

    _onNamespaceChange(e) {
        const user = this._authSel.value;
        if (!user || typeof user.company_id !== 'string' || user.company_id === '') {
            throw new Error('SyncSidebar: cannot change namespace without active company_id');
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
     * После создания канала митинга — тот же путь, что «Позвонить» в шапке чата:
     * invite (LiveKit room + участники), затем overlay с подключением.
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
        const channelId = result && typeof result.id === 'string' ? result.id : null;
        if (channelId === null) return;
        this.navigate('channel', { channelId });
        this.renderRoot?.querySelector('platform-service-sidebar')?.closeMobile?.();
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

    _renderHeaderArea() {
        const activeNs = this._activeNamespace();
        const selectValue = activeNs === 'all' ? '' : activeNs;
        const search = this._chatUi.value && typeof this._chatUi.value.sidebarSearchQuery === 'string'
            ? this._chatUi.value.sidebarSearchQuery
            : '';
        const scope = this._searchScope();
        return html`
            <div class="sync-sidebar-header-inner">
                <div class="header-adhoc">
                    <button
                        class="adhoc-btn"
                        @click=${this._onAdhocCall}
                        ?disabled=${this._adhoc.busy || this._callInvite.busy}
                        title=${this.t('sidebar.create_sync_title')}
                    >
                        <platform-icon name="phone-plus" size="16"></platform-icon>
                        <span>${this.t('sidebar.action_adhoc_call')}</span>
                    </button>
                </div>
                <div class="header-area">
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
                    ></platform-sidebar-namespace-select>
                    <div class="search-box">
                        <platform-icon name="search" size="14"></platform-icon>
                        <input
                            class="sync-sidebar-search-input"
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
            </div>
        `;
    }

    _renderChatsSection() {
        const chats = this._unifiedChats();
        const members = this._membersWithoutDm();
        const empty = chats.length === 0 && members.length === 0;
        const activeNs = this._activeNamespace();
        return html`
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
        `;
    }

    render() {
        return html`
            <platform-service-sidebar
                logo-src="/static/core/assets/service_logos/sync_logo.svg"
                logo-text="Sync"
                ?logo-opens-services=${true}
                ?collapsed=${this.collapsed}
                ?mobile-open=${this.mobileOpen}
                @collapse-change=${(e) => { this.collapsed = e.detail.collapsed; }}
                @mobile-change=${(e) => { this.mobileOpen = e.detail.open; }}
            >
                <div slot="header">${this._renderHeaderArea()}</div>
                ${this._renderChatsSection()}
                <div slot="footer" class="user-section">
                    <platform-user block>
                        <platform-notification-manager slot="user-toolbar"></platform-notification-manager>
                    </platform-user>
                </div>
            </platform-service-sidebar>
        `;
    }
}

customElements.define('sync-sidebar', SyncSidebar);
