/**
 * Карточка пользователя: аватар, роли, общие каналы (сетка как в сайдбаре).
 */
import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { SyncStore } from '../store/sync.store.js';
import { hueFromString } from '../utils/sync-hue.js';
import '../features/sync-channel-row.js';

export class UserInfoModal extends PlatformModal {
    static properties = {
        ...PlatformModal.properties,
        /** UserBrief: user_id, display_name, avatar_url */
        profileUser: { type: Object },
        /** @deprecated используйте profileUser */
        sender: { type: Object },
        _sharedChannels: { state: true },
        _channelsLoading: { state: true },
        _channelsError: { state: true },
    };

    static styles = [
        PlatformModal.styles,
        buttonStyles,
        css`
            .profile-head {
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: var(--space-3);
                margin-bottom: var(--space-4);
            }

            .profile-avatar {
                width: 96px;
                height: 96px;
                border-radius: 50%;
                object-fit: cover;
                border: 2px solid var(--glass-border-subtle);
            }

            .profile-avatar-initials {
                width: 96px;
                height: 96px;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 32px;
                font-weight: var(--font-semibold);
                color: #fff;
                border: 2px solid var(--glass-border-subtle);
            }

            .profile-name {
                font-size: var(--text-lg);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                text-align: center;
            }

            .section-title {
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                text-transform: uppercase;
                letter-spacing: 0.06em;
                color: var(--text-tertiary);
                margin-bottom: var(--space-2);
            }

            .roles-row {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
                margin-bottom: var(--space-4);
            }

            .role-chip {
                font-size: var(--text-xs);
                padding: 4px 10px;
                border-radius: var(--radius-full);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                color: var(--text-secondary);
            }

            .channels-grid {
                display: grid;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                gap: var(--space-2);
                align-items: start;
            }

            @media (max-width: 700px) {
                .channels-grid {
                    grid-template-columns: repeat(2, minmax(0, 1fr));
                }
            }

            @media (max-width: 420px) {
                .channels-grid {
                    grid-template-columns: 1fr;
                }
            }

            .channel-cell {
                min-width: 0;
                cursor: pointer;
                border-radius: var(--radius-lg);
                transition: background var(--duration-fast);
            }

            .channel-cell:hover {
                background: var(--glass-solid-subtle);
            }

            .channel-cell:focus-visible {
                outline: 2px solid var(--accent);
                outline-offset: 2px;
            }

            .channels-empty,
            .channels-error {
                font-size: var(--text-sm);
                color: var(--text-tertiary);
                padding: var(--space-2) 0;
            }

            .channels-error {
                color: var(--error);
            }

            .body-wrap {
                max-height: min(60vh, 520px);
                overflow-y: auto;
                padding-right: var(--space-1);
            }
        `,
    ];

    constructor() {
        super();
        this.title = 'Профиль';
        this.size = 'xl';
        this.profileUser = null;
        this.sender = null;
        this._sharedChannels = [];
        this._channelsLoading = false;
        this._channelsError = null;
    }

    _effectiveUser() {
        return this.profileUser ?? this.sender;
    }

    _userId() {
        const u = this._effectiveUser();
        if (!u || typeof u.user_id !== 'string' || u.user_id === '') {
            throw new Error('Нет user_id для профиля.');
        }
        return u.user_id;
    }

    _displayName() {
        const u = this._effectiveUser();
        const n = u?.display_name;
        return typeof n === 'string' && n.trim() !== '' ? n.trim() : this._userId();
    }

    _rolesFromStore() {
        const uid = this._userId();
        const list = SyncStore.state.companyMembers?.list;
        if (!Array.isArray(list)) return [];
        const row = list.find(m => m.user_id === uid);
        const roles = row?.roles;
        return Array.isArray(roles) ? roles : [];
    }

    updated(changedProperties) {
        super.updated(changedProperties);
        if (!this.open || !this._effectiveUser()) {
            return;
        }
        if (
            changedProperties.has('open')
            || changedProperties.has('profileUser')
            || changedProperties.has('sender')
        ) {
            void this._loadSharedChannels();
        }
    }

    async _loadSharedChannels() {
        const syncApi = this.services.get('syncApi');
        if (!syncApi) {
            throw new Error('syncApi не зарегистрирован.');
        }
        this._channelsLoading = true;
        this._channelsError = null;
        this._sharedChannels = [];
        try {
            const uid = this._userId();
            const list = await syncApi.getSharedChannelsWithMember(uid);
            this._sharedChannels = Array.isArray(list) ? list : [];
        } catch (e) {
            const msg = e instanceof Error ? e.message : String(e);
            this._channelsError = msg;
            this._sharedChannels = [];
        } finally {
            this._channelsLoading = false;
        }
    }

    async _selectChannel(channel) {
        if (!channel?.id) {
            throw new Error('Некорректный канал.');
        }
        const syncApi = this.services.get('syncApi');
        if (!syncApi) {
            throw new Error('syncApi не зарегистрирован.');
        }
        await SyncStore.selectChannelAndLoadMessages(syncApi, channel.space_id ?? null, channel.id);
        this.close();
    }

    close() {
        super.close();
        this.emit('close');
    }

    renderHeader() {
        return 'Профиль';
    }

    renderBody() {
        const u = this._effectiveUser();
        if (!u) {
            return html``;
        }
        const name = this._displayName();
        const avatarUrl = typeof u.avatar_url === 'string' && u.avatar_url !== '' ? u.avatar_url : null;
        const initials = name.trim().slice(0, 2).toUpperCase() || '?';
        const hue = hueFromString(this._userId());
        const roles = this._rolesFromStore();
        const selectedId = SyncStore.state.chat?.selectedChannelId ?? null;

        return html`
            <div class="body-wrap">
                <div class="profile-head">
                    ${avatarUrl
                        ? html`<img class="profile-avatar" src=${avatarUrl} alt="" />`
                        : html`<span
                              class="profile-avatar-initials"
                              style=${`background:hsl(${hue} 48% 42%)`}
                          >${initials}</span>`}
                    <div class="profile-name">${name}</div>
                </div>
                ${roles.length > 0
                    ? html`
                        <div class="section-title">Роли</div>
                        <div class="roles-row">
                            ${roles.map(
                                r => html`<span class="role-chip">${r}</span>`
                            )}
                        </div>
                    `
                    : ''}
                <div class="section-title">Каналы вместе</div>
                ${this._channelsLoading
                    ? html`<div class="channels-empty">Загрузка…</div>`
                    : this._channelsError
                      ? html`<div class="channels-error">${this._channelsError}</div>`
                      : this._sharedChannels.length === 0
                        ? html`<div class="channels-empty">Нет общих каналов.</div>`
                        : html`
                            <div class="channels-grid">
                                ${this._sharedChannels.map(ch => html`
                                    <div
                                        class="channel-cell"
                                        role="button"
                                        tabindex="0"
                                        @click=${() => this._selectChannel(ch)}
                                        @keydown=${(e) => {
                                            if (e.key === 'Enter' || e.key === ' ') {
                                                e.preventDefault();
                                                this._selectChannel(ch);
                                            }
                                        }}
                                    >
                                        <sync-channel-row
                                            .channel=${ch}
                                            .active=${ch.id === selectedId}
                                        ></sync-channel-row>
                                    </div>
                                `)}
                            </div>
                        `}
            </div>
        `;
    }

    renderFooter() {
        return html``;
    }

    render() {
        if (!this.open || !this._effectiveUser()) {
            return html``;
        }
        return super.render();
    }
}

customElements.define('user-info-modal', UserInfoModal);
