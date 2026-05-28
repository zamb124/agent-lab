/**
 * platform-user-info-modal — единая модалка профиля платформы.
 *
 * modalKind: 'platform.user_info'
 *
 * Открывается одинаково на собственного и чужого юзера; режим определяется
 * сравнением `userId` с текущим `state.auth.user.raw.user_id`.
 *
 * Источник данных:
 *   - Собственный юзер: state.auth.user (поля name/first_name/last_name/bio/
 *     emails/avatar_url/ui_preferences.language).
 *   - Чужой юзер: state.team.members. Если члены ещё не подгружены — модалка
 *     диспатчит TEAM_EVENTS.MEMBERS_LOAD_REQUESTED.
 *
 * Режим Own (isOwn === true):
 *   - Форма с полями first_name, last_name, name (обяз.), email (read-only),
 *     bio, language (ru/en).
 *   - Отправка → dispatch('auth/profile/update_requested', { updates }).
 *   - Toast platform:user_info_modal.toast_profile_saved.
 *   - Футер: Save (primary), Logout (danger), Cancel.
 *
 * Режим Other (isOwn === false), member найден:
 *   - Карточка: avatar, name, email, роли, joined_at.
 *   - Если у текущего auth.user.raw.roles есть 'owner'/'admin' в активной
 *     компании — инлайн-секция «Роли»: чекбоксы owner/admin/developer/viewer.
 *     Чекбокс owner блокируется, если у member.roles есть 'owner' (защита
 *     владельца компании).
 *   - Сохранение ролей → useResource('frontend/team_members').update(userId, { roles }).
 *   - Футер: Save roles (если admin и роли изменены), Message in Sync,
 *     Открыть в Team, Close.
 *   - Копирование user id: иконка в шапке слева от Save.
 *
 * Режим Other (member не найден):
 *   - Карточка только для чтения с user_chip.unknown.
 *   - Footer: Close (копирование id — иконка в шапке).
 *
 * Cross-app переходы — через window.location.href (общего routes-реестра
 * между сервисами нет; см. platform-user.js — тот же приём).
 *
 * i18n namespace: 'platform'.
 */

import { html, css } from 'lit';
import { PlatformFormModal } from './glass-form-modal.js';
import { registerModalKind } from '../utils/modal-registry.js';
import { TEAM_EVENTS } from '../events/reducers/team.js';
import { hasFactory } from '../events/factory-registry.js';

import { CoreEvents } from '../events/contract.js';
import { resolveAvatarImageSrc } from '../utils/placeholder-avatar.js';
import './platform-button.js';
import './platform-icon.js';

const TEAM_MEMBERS_RESOURCE_NAME = 'frontend/team_members';
const SYNC_SHARED_CHANNELS_OP_NAME = 'sync/shared_channels';
const AVAILABLE_ROLES = Object.freeze(['owner', 'admin', 'developer', 'viewer']);

export class PlatformUserInfoModal extends PlatformFormModal {
    static modalKind = 'platform.user_info';
    static i18nNamespace = 'platform';

    static properties = {
        ...PlatformFormModal.properties,
        userId: { type: String, attribute: 'user-id' },
        _roles: { state: true },
        _rolesDirty: { state: true },
        _avatarLgFallback: { state: true },
        _sharedChannels: { state: true },
        _sharedChannelsLoading: { state: true },
        _sharedChannelsError: { state: true },
    };

    static styles = [
        ...PlatformFormModal.styles,
        css`
            .user-card {
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: var(--space-3, 12px);
                padding: var(--space-2, 8px) 0 var(--space-4, 16px);
            }

            .avatar-lg {
                width: 96px;
                height: 96px;
                border-radius: 50%;
                background: var(--accent-subtle, rgba(99, 102, 241, 0.18));
                color: var(--accent, #6366f1);
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 36px;
                font-weight: var(--font-semibold, 600);
                overflow: hidden;
                flex-shrink: 0;
            }

            .avatar-lg img {
                width: 100%;
                height: 100%;
                object-fit: cover;
                border-radius: 50%;
            }

            .name {
                font-size: var(--text-xl, 20px);
                font-weight: var(--font-semibold, 600);
                color: var(--text-primary);
                text-align: center;
            }

            .email {
                font-size: var(--text-sm, 14px);
                color: var(--text-secondary, rgba(255, 255, 255, 0.65));
                text-align: center;
                word-break: break-all;
            }

            .meta {
                width: 100%;
                display: grid;
                grid-template-columns: max-content 1fr;
                gap: var(--space-2, 8px) var(--space-3, 12px);
                margin-top: var(--space-2, 8px);
            }

            .meta-label {
                color: var(--text-tertiary, rgba(255, 255, 255, 0.5));
                font-size: var(--text-xs, 12px);
                text-transform: uppercase;
                letter-spacing: 0.04em;
                align-self: center;
            }

            .meta-value {
                color: var(--text-primary);
                font-size: var(--text-sm, 14px);
            }

            .role-chips {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2, 8px);
            }

            .role-chip {
                padding: 2px 10px;
                border-radius: var(--radius-full, 999px);
                background: var(--glass-tint-medium, rgba(255, 255, 255, 0.08));
                color: var(--text-primary);
                font-size: var(--text-xs, 12px);
                font-weight: var(--font-medium, 500);
            }

            .actions {
                display: flex;
                flex-direction: row;
                flex-wrap: wrap;
                align-items: center;
                gap: var(--space-2, 8px);
                width: 100%;
            }

            .actions platform-button {
                flex: 0 0 auto;
            }

            .actions .spacer {
                flex: 1 1 auto;
            }

            .actions .save-row {
                flex: 0 0 100%;
                display: flex;
            }

            .empty {
                padding: var(--space-4, 16px);
                color: var(--text-tertiary);
                font-size: var(--text-sm, 14px);
                text-align: center;
            }

            .roles-section {
                margin-top: var(--space-4, 16px);
                padding-top: var(--space-4, 16px);
                border-top: 1px solid var(--glass-border-subtle);
            }

            .roles-section-title {
                font-size: var(--text-sm, 14px);
                font-weight: var(--font-semibold, 600);
                color: var(--text-primary);
                margin-bottom: var(--space-2, 8px);
            }

            .roles-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-2, 8px);
            }

            .role-row {
                display: flex;
                align-items: center;
                gap: var(--space-3, 12px);
                padding: var(--space-2, 8px) var(--space-3, 12px);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                cursor: pointer;
                color: var(--text-primary);
                font-size: var(--text-sm);
            }

            .role-row.checked {
                background: var(--glass-solid-medium);
                border-color: var(--accent);
            }

            .role-row.disabled {
                opacity: 0.6;
                cursor: not-allowed;
            }

            .role-name {
                font-weight: var(--font-medium);
            }

            .role-hint {
                margin-left: auto;
                color: var(--text-tertiary);
                font-size: var(--text-xs);
            }

            .channels-section {
                margin-top: var(--space-4, 16px);
                padding-top: var(--space-4, 16px);
                border-top: 1px solid var(--glass-border-subtle);
            }

            .channels-section-title {
                font-size: var(--text-sm, 14px);
                font-weight: var(--font-semibold, 600);
                color: var(--text-primary);
                margin-bottom: var(--space-2, 8px);
            }

            .channels-grid {
                display: flex;
                flex-direction: column;
                gap: var(--space-2, 8px);
            }

            .channel-cell {
                display: block;
                width: 100%;
                padding: 0;
                border: 0;
                background: transparent;
                color: inherit;
                text-align: inherit;
                cursor: pointer;
            }

            .channel-cell sync-channel-row {
                pointer-events: none;
            }

            .channels-empty {
                padding: var(--space-3, 12px);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                color: var(--text-tertiary);
                font-size: var(--text-sm, 14px);
                background: var(--glass-solid-subtle);
            }
        `,
    ];

    constructor() {
        super();
        this.userId = '';
        this._roles = new Set();
        this._rolesDirty = false;
        this._avatarLgFallback = 0;
        this._avatarLgSig = '';
        this._sharedChannels = [];
        this._sharedChannelsLoading = false;
        this._sharedChannelsError = '';
        this._sharedChannelsPeerId = '';
        this._sharedChannelsOp = null;
        this._teamSel = this.select((s) => s.team);
        this._authSel = this.select((s) => s.auth);
        this._localeSel = this.select((s) => s.i18n.locale);
        this._loadDispatched = false;
        // Редактирование ролей живёт в фабрике сервиса frontend
        // (`frontend/team_members`). В сервисах без админ-панели команд
        // (office, rag, ...) фабрика не зарегистрирована — секция ролей
        // в модалке скрывается, а резолвить контроллер мы будем лениво
        // при сохранении ролей у админа.
        this._members = null;
    }

    _ensureTeamMembersResource() {
        if (this._members) return this._members;
        if (!hasFactory(TEAM_MEMBERS_RESOURCE_NAME)) return null;
        this._members = this.useResource(TEAM_MEMBERS_RESOURCE_NAME);
        return this._members;
    }

    _ensureSharedChannelsOp() {
        if (this._sharedChannelsOp) return this._sharedChannelsOp;
        if (!hasFactory(SYNC_SHARED_CHANNELS_OP_NAME)) return null;
        this._sharedChannelsOp = this.useOp(SYNC_SHARED_CHANNELS_OP_NAME);
        return this._sharedChannelsOp;
    }

    updated(changed) {
        super.updated(changed);
        const auth = this._authSel.value;
        const team = this._teamSel.value;
        if (
            !this._loadDispatched
            && auth.status === 'authenticated'
            && team.members.length === 0
            && team.loading === false
        ) {
            this._loadDispatched = true;
            this.dispatch(TEAM_EVENTS.MEMBERS_LOAD_REQUESTED, null);
        }
        if (changed.has('userId') && this.userId) {
            this._rolesDirty = false;
            this._avatarLgFallback = 0;
            this._avatarLgSig = '';
            this._sharedChannels = [];
            this._sharedChannelsLoading = false;
            this._sharedChannelsError = '';
            this._sharedChannelsPeerId = '';
            const resolved = this._resolveUser();
            if (resolved && !resolved.isOwn && resolved.user) {
                this._roles = new Set(resolved.user.roles);
            } else if (resolved && !resolved.isOwn && !resolved.user) {
                this._roles = new Set();
            }
        } else if (!this._rolesDirty) {
            const resolved = this._resolveUser();
            if (resolved && !resolved.isOwn && resolved.user) {
                const incoming = new Set(resolved.user.roles);
                if (incoming.size !== this._roles.size
                    || Array.from(incoming).some((r) => !this._roles.has(r))) {
                    this._roles = incoming;
                }
            }
        }
        const resolvedAvatar = this._resolveUser();
        if (resolvedAvatar && resolvedAvatar.user) {
            const u = resolvedAvatar.user;
            const au = typeof u.avatar_url === 'string' ? u.avatar_url : '';
            const sig = `${u.user_id}|${au}`;
            if (this._avatarLgSig !== sig) {
                this._avatarLgSig = sig;
                this._avatarLgFallback = 0;
            }
        }
        this._maybeLoadSharedChannels(resolvedAvatar);
    }

    _maybeLoadSharedChannels(resolved) {
        if (!resolved || resolved.isOwn || !resolved.user) return;
        const peerId = typeof resolved.user.user_id === 'string' ? resolved.user.user_id : '';
        if (peerId === '') return;
        if (this._sharedChannelsPeerId === peerId || this._sharedChannelsLoading) return;
        const op = this._ensureSharedChannelsOp();
        if (!op) return;
        this._sharedChannelsPeerId = peerId;
        this._sharedChannels = [];
        this._sharedChannelsError = '';
        this._sharedChannelsLoading = true;
        this._loadSharedChannels(peerId, op);
    }

    async _loadSharedChannels(peerId, op) {
        try {
            const result = await op.run({ peer_user_id: peerId });
            if (this.userId !== peerId || this._sharedChannelsPeerId !== peerId) return;
            const source = result && typeof result === 'object' ? result : op.lastResult;
            const items = source && Array.isArray(source.items)
                ? source.items
                : (Array.isArray(source) ? source : []);
            this._sharedChannels = items.filter((channel) => (
                channel
                && typeof channel === 'object'
                && typeof channel.channel_id === 'string'
                && channel.channel_id !== ''
            ));
        } catch (err) {
            if (this.userId === peerId && this._sharedChannelsPeerId === peerId) {
                this._sharedChannels = [];
                this._sharedChannelsError = err && typeof err.message === 'string'
                    ? err.message
                    : 'failed';
            }
        } finally {
            if (this.userId === peerId && this._sharedChannelsPeerId === peerId) {
                this._sharedChannelsLoading = false;
            }
        }
    }

    _resolveUser() {
        const userId = this.userId;
        if (typeof userId !== 'string' || userId.length === 0) {
            return null;
        }
        const auth = this._authSel.value;
        const currentUser = auth.user;
        const currentId = currentUser
            ? ((currentUser.raw && currentUser.raw.user_id) || currentUser.id)
            : null;
        if (currentUser && currentId === userId) {
            const raw = currentUser.raw || {};
            return {
                isOwn: true,
                source: 'auth',
                user: {
                    user_id: userId,
                    name: currentUser.name || raw.name || this.t('user_chip.you'),
                    first_name: raw.first_name || '',
                    last_name: raw.last_name || '',
                    bio: raw.bio || '',
                    email: Array.isArray(raw.emails) && raw.emails.length > 0 ? raw.emails[0] : null,
                    avatar_url: typeof raw.avatar_url === 'string' && raw.avatar_url.length > 0 ? raw.avatar_url : null,
                    roles: Array.isArray(raw.roles) ? raw.roles : [],
                    joined_at: raw.created_at || null,
                    language: (raw.ui_preferences && raw.ui_preferences.language)
                        ? raw.ui_preferences.language
                        : this._localeSel.value,
                    ui_preferences: raw.ui_preferences || {},
                },
            };
        }
        const team = this._teamSel.value;
        const member = team.members.find((m) => m.user_id === userId);
        if (member) {
            return {
                isOwn: false,
                source: 'team',
                user: {
                    user_id: member.user_id,
                    name: member.name,
                    email: member.email,
                    avatar_url: member.avatar_url,
                    roles: Array.isArray(member.roles) ? member.roles : [],
                    joined_at: member.joined_at || null,
                },
            };
        }
        return { isOwn: false, source: 'unknown', user: null };
    }

    _onAvatarLgError() {
        const resolved = this._resolveUser();
        if (!resolved || !resolved.user) return;
        const u = resolved.user;
        const hadUrl = typeof u.avatar_url === 'string' && u.avatar_url.length > 0;
        if (this._avatarLgFallback === 0 && hadUrl) {
            this._avatarLgFallback = 1;
        } else {
            this._avatarLgFallback = 2;
        }
    }

    _renderAvatarLg(user) {
        if (this._avatarLgFallback >= 2) {
            return html`<div class="avatar-lg">${(user.name || '?').trim().charAt(0).toUpperCase()}</div>`;
        }
        const hadUrl = typeof user.avatar_url === 'string' && user.avatar_url.length > 0;
        const resolved = resolveAvatarImageSrc({
            avatarUrl: this._avatarLgFallback === 0 && hadUrl ? user.avatar_url : null,
            seed: user.user_id,
        });
        return html`<div class="avatar-lg"><img src=${resolved.src} alt=${user.name} @error=${this._onAvatarLgError} /></div>`;
    }

    _canEditRoles() {
        if (!hasFactory(TEAM_MEMBERS_RESOURCE_NAME)) return false;
        const auth = this._authSel.value;
        const raw = auth.user && auth.user.raw;
        if (!raw || !Array.isArray(raw.roles)) return false;
        return raw.roles.includes('owner') || raw.roles.includes('admin');
    }

    _isMemberOwner(memberRoles) {
        return Array.isArray(memberRoles) && memberRoles.includes('owner');
    }

    _roleLabel(role) {
        if (role === 'owner')     return this.t('user_info_modal.role_owner');
        if (role === 'admin')     return this.t('user_info_modal.role_admin');
        if (role === 'developer') return this.t('user_info_modal.role_developer');
        if (role === 'viewer')    return this.t('user_info_modal.role_viewer');
        return role;
    }

    _formatJoinedAt(value) {
        if (!value) return null;
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return null;
        const locale = this._localeSel.value === 'ru' ? 'ru-RU' : 'en-US';
        return new Intl.DateTimeFormat(locale, {
            year: 'numeric',
            month: 'long',
            day: 'numeric',
        }).format(date);
    }

    renderHeader() {
        return this.t('user_info_modal.header');
    }

    renderBody() {
        const resolved = this._resolveUser();
        if (!resolved) {
            return html`<div class="empty">${this.t('user_chip.unknown')}</div>`;
        }
        if (resolved.isOwn) {
            return this._renderOwnForm(resolved.user);
        }
        if (!resolved.user) {
            return html`<div class="empty">${this.t('user_chip.unknown')}</div>`;
        }
        return this._renderOtherCard(resolved.user);
    }

    _renderOwnForm(user) {
        return html`
            <div class="user-card">
                ${this._renderAvatarLg(user)}
                <div class="name">${user.name}</div>
                ${user.email ? html`<div class="email">${user.email}</div>` : null}
            </div>
            <form @submit=${this._onSubmit} @input=${() => { this.isDirty = true; }}>
                <div class="form-group">
                    <label for="first_name" class="form-label">
                        ${this.t('user_info_modal.field_first_name')}
                    </label>
                    <input
                        type="text"
                        id="first_name"
                        name="first_name"
                        class="form-input"
                        .value=${user.first_name}
                        maxlength="100"
                    />
                    ${this.renderFieldError('first_name')}
                </div>
                <div class="form-group">
                    <label for="last_name" class="form-label">
                        ${this.t('user_info_modal.field_last_name')}
                    </label>
                    <input
                        type="text"
                        id="last_name"
                        name="last_name"
                        class="form-input"
                        .value=${user.last_name}
                        maxlength="100"
                    />
                    ${this.renderFieldError('last_name')}
                </div>
                <div class="form-group">
                    <label for="name" class="form-label">
                        ${this.t('user_info_modal.field_name')}
                    </label>
                    <input
                        type="text"
                        id="name"
                        name="name"
                        class="form-input"
                        .value=${user.name}
                        maxlength="100"
                        required
                    />
                    ${this.renderFieldError('name')}
                </div>
                <div class="form-group">
                    <label for="email" class="form-label">
                        ${this.t('user_info_modal.field_email')}
                    </label>
                    <input
                        type="email"
                        id="email"
                        class="form-input"
                        .value=${user.email || ''}
                        disabled
                    />
                    <small class="form-help">${this.t('user_info_modal.field_email_locked')}</small>
                </div>
                <div class="form-group">
                    <label for="bio" class="form-label">
                        ${this.t('user_info_modal.field_bio')}
                    </label>
                    <textarea
                        id="bio"
                        name="bio"
                        class="form-textarea"
                        rows="4"
                        maxlength="4000"
                        .value=${user.bio}
                    ></textarea>
                    ${this.renderFieldError('bio')}
                </div>
                <div class="form-group">
                    <label for="language" class="form-label">
                        ${this.t('user_info_modal.field_language')}
                    </label>
                    <select id="language" name="language" class="form-select">
                        <option value="ru" ?selected=${user.language === 'ru'}>
                            ${this.t('user_info_modal.lang_ru')}
                        </option>
                        <option value="en" ?selected=${user.language === 'en'}>
                            ${this.t('user_info_modal.lang_en')}
                        </option>
                    </select>
                </div>
            </form>
        `;
    }

    _renderOtherCard(user) {
        const joined = this._formatJoinedAt(user.joined_at);
        const showRolesEditor = this._canEditRoles();
        return html`
            <div class="user-card">
                ${this._renderAvatarLg(user)}
                <div class="name">${user.name}</div>
                ${user.email ? html`<div class="email">${user.email}</div>` : null}
                <div class="meta">
                    ${user.roles.length > 0
                        ? html`
                            <div class="meta-label">${this.t('user_info_modal.roles_label')}</div>
                            <div class="meta-value">
                                <div class="role-chips">
                                    ${user.roles.map((role) => html`
                                        <span class="role-chip">${this._roleLabel(role)}</span>
                                    `)}
                                </div>
                            </div>
                        `
                        : null}
                    ${joined
                        ? html`
                            <div class="meta-label">${this.t('user_info_modal.joined_at')}</div>
                            <div class="meta-value">${joined}</div>
                        `
                        : null}
                </div>
            </div>
            ${this._renderSharedChannels()}
            ${showRolesEditor ? this._renderRolesEditor(user) : null}
        `;
    }

    _renderSharedChannels() {
        if (!hasFactory(SYNC_SHARED_CHANNELS_OP_NAME)) return null;
        return html`
            <div class="channels-section">
                <div class="channels-section-title">${this.t('user_info_modal.shared_channels')}</div>
                ${this._sharedChannelsLoading
                    ? html`<div class="channels-empty">${this.t('user_info_modal.shared_channels_loading')}</div>`
                    : this._sharedChannelsError !== ''
                        ? html`<div class="channels-empty">${this.t('user_info_modal.shared_channels_error')}</div>`
                        : this._sharedChannels.length === 0
                            ? html`<div class="channels-empty">${this.t('user_info_modal.shared_channels_empty')}</div>`
                            : html`
                                <div class="channels-grid">
                                    ${this._sharedChannels.map((channel) => html`
                                        <button
                                            type="button"
                                            class="channel-cell"
                                            @click=${() => this._openSharedChannel(channel)}
                                        >
                                            <sync-channel-row .channel=${channel} .pickMode=${true}></sync-channel-row>
                                        </button>
                                    `)}
                                </div>
                            `}
            </div>
        `;
    }

    _renderRolesEditor(user) {
        const memberIsOwner = this._isMemberOwner(user.roles);
        return html`
            <div class="roles-section">
                <div class="roles-section-title">${this.t('user_info_modal.section_roles')}</div>
                <div class="roles-list">
                    ${AVAILABLE_ROLES.map((role) => {
                        const checked = this._roles.has(role);
                        const lockOwner = role === 'owner' && memberIsOwner;
                        return html`
                            <label class="role-row ${checked ? 'checked' : ''} ${lockOwner ? 'disabled' : ''}">
                                <input
                                    type="checkbox"
                                    .checked=${checked}
                                    ?disabled=${lockOwner}
                                    @change=${() => this._toggleRole(role)}
                                />
                                <span class="role-name">${this._roleLabel(role)}</span>
                                ${lockOwner
                                    ? html`<span class="role-hint">${this.t('user_info_modal.role_owner_locked')}</span>`
                                    : null}
                            </label>
                        `;
                    })}
                </div>
                ${this.renderFieldError('roles')}
            </div>
        `;
    }

    _toggleRole(role) {
        const resolved = this._resolveUser();
        if (!resolved || !resolved.user) return;
        if (role === 'owner' && this._isMemberOwner(resolved.user.roles)) return;
        const next = new Set(this._roles);
        if (next.has(role)) next.delete(role); else next.add(role);
        this._roles = next;
        this._rolesDirty = true;
    }

    _saveRoles() {
        const resolved = this._resolveUser();
        if (!resolved || resolved.isOwn || !resolved.user) return;
        if (this._roles.size === 0) {
            this.formErrors = { roles: this.t('user_info_modal.error_role_required') };
            return;
        }
        const members = this._ensureTeamMembersResource();
        if (!members) {
            throw new Error(
                'platform-user-info-modal: frontend/team_members factory required to update roles',
            );
        }
        this.formErrors = {};
        members.update(resolved.user.user_id, { roles: Array.from(this._roles) });
        this._rolesDirty = false;
        this.close();
    }

    validateForm() {
        const errors = {};
        const data = this.getFormData();
        if (!data.name || data.name.trim().length === 0) {
            errors.name = this.t('user_info_modal.error_name_required');
        }
        return errors;
    }

    handleSubmit(data) {
        const resolved = this._resolveUser();
        if (!resolved || !resolved.isOwn) return;
        const updates = {
            name: data.name.trim(),
            first_name: data.first_name && data.first_name.trim() ? data.first_name.trim() : null,
            last_name: data.last_name && data.last_name.trim() ? data.last_name.trim() : null,
            bio: data.bio && data.bio.trim() ? data.bio.trim() : null,
            ui_preferences: {
                ...resolved.user.ui_preferences,
                language: data.language,
            },
        };
        this.dispatch('auth/profile/update_requested', { updates });
        this.toast('user_info_modal.toast_profile_saved', { type: 'success' });
        this.closeAfterSave();
    }

    _logout() {
        this.dispatch(CoreEvents.AUTH_LOGOUT_REQUESTED, null);
        super.close();
    }

    _openSync() {
        if (typeof this.userId !== 'string' || this.userId.length === 0) return;
        window.location.href = `/sync?direct=${encodeURIComponent(this.userId)}`;
    }

    _openTeamPage() {
        if (typeof this.userId !== 'string' || this.userId.length === 0) return;
        window.location.href = `/frontend/team?focus=${encodeURIComponent(this.userId)}`;
    }

    _openSharedChannel(channel) {
        if (!channel || typeof channel.channel_id !== 'string' || channel.channel_id === '') return;
        super.close();
        this.navigate('channel', { channelId: channel.channel_id });
    }

    _copyId() {
        if (typeof this.userId !== 'string' || this.userId.length === 0) return;
        this.copyToClipboard(this.userId, {
            success_i18n_key: 'platform:user_info_modal.toast_copied',
            error_i18n_key: 'platform:user_info_modal.toast_copy_failed',
        });
    }

    renderHeaderActions() {
        if (typeof this.userId !== 'string' || this.userId.length === 0) {
            return html``;
        }
        const copyTitle = this.t('user_info_modal.action_copy_id');
        return html`
            <button
                type="button"
                class="header-btn"
                title=${copyTitle}
                aria-label=${copyTitle}
                @click=${() => this._copyId()}
            >
                <platform-icon name="copy" size="16"></platform-icon>
            </button>
        `;
    }

    renderFooter() {
        const resolved = this._resolveUser();
        if (!resolved) {
            return html`
                <div class="actions">
                    <platform-button variant="secondary" @click=${() => this.close()}>
                        ${this.t('user_info_modal.action_cancel')}
                    </platform-button>
                </div>
            `;
        }
        if (resolved.isOwn) {
            return html`
                <div class="actions">
                    <platform-button
                        variant="primary"
                        ?disabled=${this.loading}
                        @click=${() => this._performSave()}
                    >
                        ${this.t('user_info_modal.action_save')}
                    </platform-button>
                    <platform-button variant="secondary" @click=${() => this.close()}>
                        ${this.t('user_info_modal.action_cancel')}
                    </platform-button>
                    <span class="spacer"></span>
                    <platform-button variant="ghost" @click=${() => this._logout()}>
                        ${this.t('user_info_modal.action_logout')}
                    </platform-button>
                </div>
            `;
        }
        if (!resolved.user) {
            return html`
                <div class="actions">
                    <platform-button variant="secondary" @click=${() => this.close()}>
                        ${this.t('user_info_modal.action_cancel')}
                    </platform-button>
                </div>
            `;
        }
        const showSave = this._canEditRoles() && this._rolesDirty;
        return html`
            <div class="actions ${showSave ? 'with-save' : ''}">
                ${showSave ? html`
                    <div class="save-row">
                        <platform-button
                            variant="primary"
                            ?disabled=${this._roles.size === 0}
                            @click=${() => this._saveRoles()}
                        >
                            ${this.t('user_info_modal.action_save_roles')}
                        </platform-button>
                    </div>
                ` : null}
                <platform-button variant="primary" @click=${() => this._openSync()}>
                    ${this.t('user_info_modal.action_write_sync')}
                </platform-button>
                <platform-button variant="secondary" @click=${() => this._openTeamPage()}>
                    ${this.t('user_info_modal.action_open_team')}
                </platform-button>
            </div>
        `;
    }
}

customElements.define('platform-user-info-modal', PlatformUserInfoModal);
registerModalKind(PlatformUserInfoModal.modalKind, 'platform-user-info-modal');
