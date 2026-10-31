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
 *   - Сохранение ролей → useResource('frontend/team').update(userId, { roles }).
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

import { isPlainRecord } from '../events/payload.js';
import { html, css } from 'lit';
import type { CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult } from 'lit';
import { PlatformFormModal } from './glass-form-modal.js';
import { registerModalKind } from '../utils/modal-registry.js';
import { TEAM_EVENTS } from '../events/reducers/team.js';
import { hasFactory } from '../events/factory-registry.js';
import { httpRequest } from '../events/http.js';
import type { SelectController } from '../events/select-controller.js';
import type { ResourceController, OpController } from '../base/use-resource.js';

interface AuthUserRecord {
    id?: string;
    user_id?: string;
    name?: string;
    canAdmin?: boolean;
    raw?: Record<string, unknown>;
}

interface AuthSliceView {
    status?: string;
    user?: AuthUserRecord | undefined;
}

interface TeamMemberRecord {
    user_id?: string;
    name?: string;
    email?: string;
    avatar_url?: string;
    roles?: unknown;
    joined_at?: string;
    is_flow_employee?: boolean;
    flow_id?: string;
    curator_user_ids?: unknown;
}

interface TeamSliceView {
    members?: TeamMemberRecord[];
    loading?: boolean;
}

interface WorkCountsView {
    total_open_count?: number;
}

interface UserInfoUser {
    user_id: string;
    name: string;
    first_name?: string;
    last_name?: string;
    bio?: string;
    email?: string | null | undefined;
    avatar_url?: string | null | undefined;
    roles: string[];
    joined_at?: string | null;
    language?: string;
    ui_preferences?: Record<string, unknown>;
    is_flow_employee?: boolean;
    flow_id?: string | null;
    curator_user_ids?: string[];
}

interface ResolvedUser {
    isOwn: boolean;
    source: string;
    user: UserInfoUser | null;
}

interface SharedChannelRecord {
    channel_id: string;
    [key: string]: unknown;
}

import { CoreEvents } from '../events/contract.js';
import { resolveAvatarImageSrc } from '../utils/placeholder-avatar.js';
import './platform-button.js';
import './platform-icon.js';
import './platform-work-item-badge.js';
import './platform-user-chip.js';

const TEAM_MEMBERS_RESOURCE_NAME = 'frontend/team';
const SYNC_SHARED_CHANNELS_OP_NAME = 'sync/shared_channels';
const AVAILABLE_ROLES = Object.freeze(['owner', 'admin', 'developer', 'viewer']);

function teamMemberView(member: Record<string, unknown>): TeamMemberRecord {
    const view: TeamMemberRecord = {};
    if (typeof member.user_id === 'string') view.user_id = member.user_id;
    if (typeof member.name === 'string') view.name = member.name;
    if (typeof member.email === 'string') view.email = member.email;
    if (typeof member.avatar_url === 'string') view.avatar_url = member.avatar_url;
    if (Array.isArray(member.roles)) view.roles = member.roles;
    if (typeof member.joined_at === 'string') view.joined_at = member.joined_at;
    if (member.is_flow_employee === true) view.is_flow_employee = true;
    if (typeof member.flow_id === 'string') view.flow_id = member.flow_id;
    if (Array.isArray(member.curator_user_ids)) view.curator_user_ids = member.curator_user_ids;
    return view;
}

function teamSliceView(team: { loading: boolean; members: readonly Record<string, unknown>[] }): TeamSliceView {
    return {
        loading: team.loading,
        members: team.members.map(teamMemberView),
    };
}

function authUserView(user: Record<string, unknown>): AuthUserRecord {
    const view: AuthUserRecord = {};
    if (typeof user.id === 'string') view.id = user.id;
    if (typeof user.user_id === 'string') view.user_id = user.user_id;
    if (typeof user.name === 'string') view.name = user.name;
    if (user.canAdmin === true) view.canAdmin = true;
    if (isPlainRecord(user.raw)) view.raw = user.raw;
    return view;
}

function authSliceView(auth: { status: string; user: Record<string, unknown> | null }): AuthSliceView {
    if (auth.user === null) return { status: auth.status };
    return { status: auth.status, user: authUserView(auth.user) };
}

function workCountsView(value: unknown): WorkCountsView | undefined {
    if (value === undefined) return undefined;
    if (!isPlainRecord(value)) {
        throw new Error('platform-user-info-modal: work item counts must be an object');
    }
    if (value.total_open_count !== undefined && typeof value.total_open_count !== 'number') {
        throw new Error('platform-user-info-modal: total_open_count must be a number');
    }
    const view: WorkCountsView = {};
    if (typeof value.total_open_count === 'number') view.total_open_count = value.total_open_count;
    return view;
}

function preferenceRecord(value: unknown): Record<string, unknown> {
    if (value === undefined || value === null) return {};
    if (!isPlainRecord(value)) {
        throw new Error('platform-user-info-modal: ui_preferences must be an object');
    }
    return value;
}

function isSharedChannel(channel: unknown): channel is SharedChannelRecord {
    return isPlainRecord(channel) && typeof channel.channel_id === 'string' && channel.channel_id !== '';
}

function sharedChannelItems(source: unknown): unknown[] {
    if (Array.isArray(source)) return source;
    if (isPlainRecord(source) && Array.isArray(source.items)) return source.items;
    return [];
}

export class PlatformUserInfoModal extends PlatformFormModal {
    static modalKind = 'platform.user_info';
    static i18nNamespace = 'platform';

    static override properties: PropertyDeclarations = {
        ...PlatformFormModal.properties,
        userId: { type: String, attribute: 'user-id' },
        _roles: { state: true },
        _rolesDirty: { state: true },
        _avatarLgFallback: { state: true },
        _sharedChannels: { state: true },
        _sharedChannelsLoading: { state: true },
        _sharedChannelsError: { state: true },
    };
    declare userId: string;
    declare _roles: Set<string>;
    declare _rolesDirty: boolean;
    declare _avatarLgFallback: number;
    declare _sharedChannels: SharedChannelRecord[];
    declare _sharedChannelsLoading: boolean;
    declare _sharedChannelsError: string;

    private _avatarLgSig: string;
    private _sharedChannelsPeerId: string;
    private _sharedChannelsOp: OpController | null;
    private _teamSel: SelectController<TeamSliceView>;
    private _authSel: SelectController<AuthSliceView>;
    private _localeSel: SelectController<string>;
    private _workCountsSel: SelectController<WorkCountsView | undefined>;
    private _loadDispatched: boolean;
    private _members: ResourceController | null;

    static override styles: CSSResultGroup = [
        ...(Array.isArray(PlatformFormModal.styles) ? PlatformFormModal.styles : [PlatformFormModal.styles]),
        css`
            .user-card {
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: var(--space-3);
                padding: var(--space-2) 0 var(--space-4);
            }

            .avatar-lg {
                width: 96px;
                height: 96px;
                border-radius: 50%;
                background: var(--accent-subtle);
                color: var(--accent);
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 36px;
                font-weight: var(--font-semibold);
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
                font-size: var(--text-xl);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                text-align: center;
            }

            .email {
                font-size: var(--text-sm);
                color: var(--text-secondary);
                text-align: center;
                word-break: break-all;
            }

            .meta {
                width: 100%;
                display: grid;
                grid-template-columns: max-content 1fr;
                gap: var(--space-2) var(--space-3);
                margin-top: var(--space-2);
            }

            .meta-label {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                text-transform: uppercase;
                letter-spacing: 0.04em;
                align-self: center;
            }

            .meta-value {
                color: var(--text-primary);
                font-size: var(--text-sm);
            }

            .role-chips {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
            }

            .role-chip {
                padding: 2px 10px;
                border-radius: var(--radius-full);
                background: var(--glass-tint-medium);
                color: var(--text-primary);
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
            }

            .actions {
                display: flex;
                flex-direction: row;
                flex-wrap: wrap;
                align-items: center;
                gap: var(--space-2);
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
                padding: var(--space-4);
                color: var(--text-tertiary);
                font-size: var(--text-sm);
                text-align: center;
            }

            .roles-section {
                margin-top: var(--space-4);
                padding-top: var(--space-4);
                border-top: 1px solid var(--glass-border-subtle);
            }

            .roles-section-title {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                margin-bottom: var(--space-2);
            }

            .roles-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }

            .role-row {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                padding: var(--space-2) var(--space-3);
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
                margin-top: var(--space-4);
                padding-top: var(--space-4);
                border-top: 1px solid var(--glass-border-subtle);
            }

            .channels-section-title {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                margin-bottom: var(--space-2);
            }

            .channels-grid {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
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
                padding: var(--space-3);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                color: var(--text-tertiary);
                font-size: var(--text-sm);
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
        this._teamSel = this.select((s) => teamSliceView(s.team));
        this._authSel = this.select((s) => authSliceView(s.auth));
        this._localeSel = this.select((s) => s.i18n.locale);
        this._workCountsSel = this.select((s) => workCountsView(s.worktrackerWorkItemCounts));
        this._loadDispatched = false;
        // Редактирование ролей живёт в фабрике сервиса frontend
        // (`frontend/team`). В сервисах без админ-панели команд
        // (office, rag, ...) фабрика не зарегистрирована — секция ролей
        // в модалке скрывается, а резолвить контроллер мы будем лениво
        // при сохранении ролей у админа.
        this._members = null;
    }

    _ensureTeamMembersResource(): ResourceController | null {
        if (this._members) return this._members;
        if (!hasFactory(TEAM_MEMBERS_RESOURCE_NAME)) return null;
        this._members = this.useResource(TEAM_MEMBERS_RESOURCE_NAME);
        return this._members;
    }

    _ensureSharedChannelsOp(): OpController | null {
        if (this._sharedChannelsOp) return this._sharedChannelsOp;
        if (!hasFactory(SYNC_SHARED_CHANNELS_OP_NAME)) return null;
        this._sharedChannelsOp = this.useOp(SYNC_SHARED_CHANNELS_OP_NAME);
        return this._sharedChannelsOp;
    }

    override willUpdate(changed: PropertyValues<this>): void {
        super.willUpdate(changed);
        const auth = this._authSel.value;
        const team = this._teamSel.value;
        const members = team === undefined || !Array.isArray(team.members) ? [] : team.members;
        if (
            !this._loadDispatched
            && auth?.status === 'authenticated'
            && members.length === 0
            && team?.loading === false
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
                this._roles = new Set<string>(resolved.user.roles);
            } else if (resolved && !resolved.isOwn && !resolved.user) {
                this._roles = new Set();
            }
        } else if (!this._rolesDirty) {
            const resolved = this._resolveUser();
            if (resolved && !resolved.isOwn && resolved.user) {
                const incoming = new Set<string>(resolved.user.roles);
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

    _maybeLoadSharedChannels(resolved: ResolvedUser | null): void {
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

    async _loadSharedChannels(peerId: string, op: OpController): Promise<void> {
        try {
            const result = await op.run({ peer_user_id: peerId });
            if (this.userId !== peerId || this._sharedChannelsPeerId !== peerId) return;
            const source = isPlainRecord(result) || Array.isArray(result) ? result : op.lastResult;
            this._sharedChannels = sharedChannelItems(source).filter(isSharedChannel);
        } catch (err) {
            if (this.userId === peerId && this._sharedChannelsPeerId === peerId) {
                this._sharedChannels = [];
                this._sharedChannelsError = err instanceof Error && typeof err.message === 'string'
                    ? err.message
                    : 'failed';
            }
        } finally {
            if (this.userId === peerId && this._sharedChannelsPeerId === peerId) {
                this._sharedChannelsLoading = false;
            }
        }
    }

    _resolveUser(): ResolvedUser | null {
        const userId = this.userId;
        if (typeof userId !== 'string' || userId.length === 0) {
            return null;
        }
        const auth = this._authSel.value;
        const currentUser = auth?.user;
        const rawRecord = currentUser?.raw;
        const currentId = currentUser
            ? ((rawRecord && typeof rawRecord.user_id === 'string' ? rawRecord.user_id : undefined) || currentUser.id)
            : null;
        if (currentUser && currentId === userId) {
            const raw = isPlainRecord(rawRecord) ? rawRecord : {};
            const prefs = preferenceRecord(raw.ui_preferences);
            const prefLanguage = typeof prefs.language === 'string' ? prefs.language : undefined;
            const emails = Array.isArray(raw.emails) ? raw.emails : [];
            return {
                isOwn: true,
                source: 'auth',
                user: {
                    user_id: userId,
                    name: currentUser.name || (typeof raw.name === 'string' ? raw.name : '') || this.t('user_chip.you'),
                    first_name: typeof raw.first_name === 'string' ? raw.first_name : '',
                    last_name: typeof raw.last_name === 'string' ? raw.last_name : '',
                    bio: typeof raw.bio === 'string' ? raw.bio : '',
                    email: emails.length > 0 && typeof emails[0] === 'string' ? emails[0] : null,
                    avatar_url: typeof raw.avatar_url === 'string' && raw.avatar_url.length > 0 ? raw.avatar_url : null,
                    roles: Array.isArray(raw.roles) ? raw.roles.filter((r): r is string => typeof r === 'string') : [],
                    joined_at: typeof raw.created_at === 'string' ? raw.created_at : null,
                    language: prefLanguage || this._localeSel.value,
                    ui_preferences: prefs,
                },
            };
        }
        const team = this._teamSel.value;
        const members = team === undefined || !Array.isArray(team.members) ? [] : team.members;
        const member = members.find((m) => m.user_id === userId);
        if (member) {
            return {
                isOwn: false,
                source: 'team',
                user: {
                    user_id: userId,
                    name: typeof member.name === 'string' ? member.name : '',
                    email: member.email,
                    avatar_url: member.avatar_url,
                    roles: Array.isArray(member.roles) ? member.roles.filter((r): r is string => typeof r === 'string') : [],
                    joined_at: typeof member.joined_at === 'string' && member.joined_at.length > 0 ? member.joined_at : null,
                    is_flow_employee: member.is_flow_employee === true,
                    flow_id: typeof member.flow_id === 'string' ? member.flow_id : null,
                    curator_user_ids: Array.isArray(member.curator_user_ids)
                        ? member.curator_user_ids.filter((c): c is string => typeof c === 'string')
                        : [],
                },
            };
        }
        return { isOwn: false, source: 'unknown', user: null };
    }

    _onAvatarLgError(): void {
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

    _renderAvatarLg(user: UserInfoUser): TemplateResult {
        if (this._avatarLgFallback >= 2) {
            return html`<div class="avatar-lg">${(user.name || '?').trim().charAt(0).toUpperCase()}</div>`;
        }
        const hadUrl = typeof user.avatar_url === 'string' && user.avatar_url.length > 0;
        const resolved = resolveAvatarImageSrc({
            avatarUrl: this._avatarLgFallback === 0 && hadUrl && typeof user.avatar_url === 'string' ? user.avatar_url : null,
            seed: user.user_id,
        });
        return html`<div class="avatar-lg"><img src=${resolved.src} alt=${user.name} @error=${this._onAvatarLgError} /></div>`;
    }

    _canEditRoles(): boolean {
        if (!hasFactory(TEAM_MEMBERS_RESOURCE_NAME)) return false;
        const auth = this._authSel.value;
        const user = auth?.user;
        return Boolean(user && user.canAdmin === true);
    }

    _canActAs(user: UserInfoUser | null): boolean {
        if (!user || user.is_flow_employee !== true) return false;
        const auth = this._authSel.value;
        const current = auth?.user;
        if (!current) return false;
        const currentId = current.user_id || current.id;
        const curators = Array.isArray(user.curator_user_ids) ? user.curator_user_ids : [];
        if (currentId && curators.includes(currentId)) return true;
        return current.canAdmin === true;
    }

    _isMemberOwner(memberRoles: unknown): boolean {
        return Array.isArray(memberRoles) && memberRoles.includes('owner');
    }

    _roleLabel(role: string): string {
        if (role === 'owner')     return this.t('user_info_modal.role_owner');
        if (role === 'admin')     return this.t('user_info_modal.role_admin');
        if (role === 'developer') return this.t('user_info_modal.role_developer');
        if (role === 'viewer')    return this.t('user_info_modal.role_viewer');
        return role;
    }

    _formatJoinedAt(value: unknown): string | null {
        if (typeof value !== 'string' && typeof value !== 'number' && !(value instanceof Date)) return null;
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return null;
        const locale = this._localeSel.value === 'ru' ? 'ru-RU' : 'en-US';
        return new Intl.DateTimeFormat(locale, {
            year: 'numeric',
            month: 'long',
            day: 'numeric',
        }).format(date);
    }

    override renderHeader(): string {
        return this.t('user_info_modal.header');
    }

    override renderBody(): TemplateResult {
        const resolved = this._resolveUser();
        if (!resolved) {
            return html`<div class="empty">${this.t('user_chip.unknown')}</div>`;
        }
        if (resolved.isOwn) {
            if (!resolved.user) {
                return html`<div class="empty">${this.t('user_chip.unknown')}</div>`;
            }
            return this._renderOwnForm(resolved.user);
        }
        if (!resolved.user) {
            return html`<div class="empty">${this.t('user_chip.unknown')}</div>`;
        }
        return this._renderOtherCard(resolved.user);
    }

    _renderOwnForm(user: UserInfoUser): TemplateResult {
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
                        .value=${user.email === undefined || user.email === null ? '' : user.email}
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

    _renderOtherCard(user: UserInfoUser): TemplateResult {
        const joined = this._formatJoinedAt(user.joined_at);
        const showRolesEditor = this._canEditRoles();
        return html`
            <div class="user-card">
                ${this._renderAvatarLg(user)}
                <div class="name">${user.name}</div>
                ${user.is_flow_employee
                    ? html`<span class="role-chip">${this.t('user_info_modal.flow_employee_badge')}</span>`
                    : null}
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
            ${user.is_flow_employee ? this._renderEmployeeSection(user) : null}
            ${this._renderSharedChannels()}
            ${this._renderActiveTasks(user, false)}
            ${showRolesEditor ? this._renderRolesEditor(user) : null}
        `;
    }

    _renderEmployeeSection(user: UserInfoUser): TemplateResult {
        const curators = Array.isArray(user.curator_user_ids) ? user.curator_user_ids : [];
        return html`
            <div class="channels-section">
                <div class="channels-section-title">${this.t('user_info_modal.flow_employee_section')}</div>
                ${user.flow_id
                    ? html`<a class="channels-empty" href="/flows/editor/${encodeURIComponent(user.flow_id)}">
                            ${this.t('user_info_modal.flow_employee_open_editor')}
                          </a>`
                    : null}
                ${curators.length > 0
                    ? html`<div class="curators">
                            <div class="meta-label">${this.t('user_info_modal.flow_employee_curators')}</div>
                            <div class="curators-chips">
                                ${curators.map((cid: string) => html`<platform-user-chip user-id=${cid}></platform-user-chip>`)}
                            </div>
                          </div>`
                    : null}
            </div>
        `;
    }

    async _actAs(user: UserInfoUser | null): Promise<void> {
        if (!user || typeof user.user_id !== 'string' || user.user_id === '') return;
        try {
            await httpRequest({
                method: 'POST',
                url: `/frontend/api/team/employees/${encodeURIComponent(user.user_id)}/act-as`,
            });
            this.toast('user_info_modal.act_as_started', { type: 'success' });
            window.location.reload();
        } catch (err) {
            this.toast('user_info_modal.act_as_failed', { type: 'error' });
        }
    }

    _renderSharedChannels(): TemplateResult | null {
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
                                    ${this._sharedChannels.map((channel: SharedChannelRecord) => html`
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

    _renderActiveTasks(user: UserInfoUser, isOwn: boolean): TemplateResult | null {
        if (!isOwn) {
            return null;
        }
        const counts = this._workCountsSel.value;
        const total = typeof counts?.total_open_count === 'number' ? counts.total_open_count : 0;
        return html`
            <div class="channels-section">
                <div class="channels-section-title">${this.t('user_info_modal.active_tasks_title')}</div>
                ${total <= 0
                    ? html`<div class="channels-empty">${this.t('user_info_modal.active_tasks_empty')}</div>`
                    : html`<a class="channels-empty" href="/worktracker/inbox">${this.t('user_info_modal.active_tasks_all')} (${total})</a>`}
            </div>
        `;
    }

    _renderRolesEditor(user: UserInfoUser): TemplateResult {
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

    _toggleRole(role: string): void {
        const resolved = this._resolveUser();
        if (!resolved || !resolved.user) return;
        if (role === 'owner' && this._isMemberOwner(resolved.user.roles)) return;
        const next = new Set(this._roles);
        if (next.has(role)) next.delete(role); else next.add(role);
        this._roles = next;
        this._rolesDirty = true;
    }

    _saveRoles(): void {
        const resolved = this._resolveUser();
        if (!resolved || resolved.isOwn || !resolved.user) return;
        if (this._roles.size === 0) {
            this.formErrors = { roles: this.t('user_info_modal.error_role_required') };
            return;
        }
        const members = this._ensureTeamMembersResource();
        if (!members) {
            throw new Error(
                'platform-user-info-modal: frontend/team factory required to update roles',
            );
        }
        this.formErrors = {};
        members.update(resolved.user.user_id, { roles: Array.from(this._roles) });
        this._rolesDirty = false;
        this.close();
    }

    override validateForm(): Record<string, string> {
        const errors: Record<string, string> = {};
        const data = this.getFormData();
        const name = typeof data.name === 'string' ? data.name : '';
        if (name.trim().length === 0) {
            errors.name = this.t('user_info_modal.error_name_required');
        }
        return errors;
    }

    override async handleSubmit(data: Record<string, FormDataEntryValue>): Promise<void> {
        const resolved = this._resolveUser();
        if (!resolved || !resolved.isOwn || !resolved.user) return;
        const field = (key: string): string => {
            const v = data[key];
            return typeof v === 'string' ? v : '';
        };
        const updates = {
            name: field('name').trim(),
            first_name: field('first_name').trim() ? field('first_name').trim() : null,
            last_name: field('last_name').trim() ? field('last_name').trim() : null,
            bio: field('bio').trim() ? field('bio').trim() : null,
            ui_preferences: {
                ...resolved.user.ui_preferences,
                language: field('language'),
            },
        };
        this.dispatch('auth/profile/update_requested', { updates });
        this.toast('user_info_modal.toast_profile_saved', { type: 'success' });
        this.closeAfterSave();
    }

    _logout(): void {
        this.dispatch(CoreEvents.AUTH_LOGOUT_REQUESTED, null);
        super.close();
    }

    _openSync(): void {
        if (typeof this.userId !== 'string' || this.userId.length === 0) return;
        window.location.href = `/sync?direct=${encodeURIComponent(this.userId)}`;
    }

    _openTeamPage(): void {
        if (typeof this.userId !== 'string' || this.userId.length === 0) return;
        window.location.href = `/frontend/team?focus=${encodeURIComponent(this.userId)}`;
    }

    _openAccess(): void {
        if (typeof this.userId !== 'string' || this.userId.length === 0) return;
        super.close();
        window.location.href = `/access?user_id=${encodeURIComponent(this.userId)}`;
    }

    _openSharedChannel(channel: SharedChannelRecord): void {
        if (!channel || typeof channel.channel_id !== 'string' || channel.channel_id === '') return;
        super.close();
        this.navigate('channel', { channelId: channel.channel_id });
    }

    _copyId(): void {
        if (typeof this.userId !== 'string' || this.userId.length === 0) return;
        this.copyToClipboard(this.userId, {
            success_i18n_key: 'platform:user_info_modal.toast_copied',
            error_i18n_key: 'platform:user_info_modal.toast_copy_failed',
        });
    }

    override renderHeaderActions(): TemplateResult {
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

    override renderFooter(): TemplateResult {
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
                    ${this._canEditRoles() ? html`
                        <platform-button variant="ghost" @click=${() => this._openAccess()}>
                            ${this.t('user_info_modal.action_open_access')}
                        </platform-button>
                    ` : null}
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
        const otherUser = resolved.user;
        const showActAs = this._canActAs(otherUser);
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
                ${this._canEditRoles() ? html`
                    <platform-button variant="secondary" @click=${() => this._openAccess()}>
                        ${this.t('user_info_modal.action_open_access')}
                    </platform-button>
                ` : null}
                ${showActAs ? html`
                    <platform-button variant="ghost" @click=${() => this._actAs(otherUser)}>
                        ${this.t('user_info_modal.action_act_as')}
                    </platform-button>
                ` : null}
            </div>
        `;
    }
}

customElements.define('platform-user-info-modal', PlatformUserInfoModal);
registerModalKind(PlatformUserInfoModal.modalKind, 'platform-user-info-modal');
