/**
 * Страница команды — участники компании, роли, ссылки-приглашения.
 *
 * Поток данных:
 *   - ресурс frontend/team → list/update/remove
 *   - op       frontend/team_invite  → генерация invite-ссылки на роль (silent);
 *     ссылки в slice `links: { [role]: link }` для кэша кнопки «Приглашение».
 *
 * Имя участника отображается через core <platform-user-chip>; клик по чипу
 * открывает единую модалку platform.user_info, где админ редактирует роли
 * инлайн (отдельной строки «Изменить роль» в таблице нет).
 *
 * Защита owner: на бэке (apps/frontend/api/team.py) запрещено удалять owner и
 * снимать роль owner; UI скрывает кнопку удаления для строки владельца.
 */
import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { frontendIslandPageBodyStyles } from '../../styles/frontend-island-page-body.styles.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-empty-state.js';
import '@platform/lib/components/platform-user-chip.js';
import '@platform/lib/components/fields/platform-field.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';
import type {CSSResultGroup, PropertyDeclarations, TemplateResult} from 'lit';
import type { OpController, ResourceController} from '@platform/lib/base/use-resource.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';

const INVITE_ROLES = Object.freeze(['developer', 'admin', 'viewer']);
const ROLE_FILTER_KEYS = Object.freeze(['owner', 'admin', 'developer', 'viewer']);

function memberUserId(member: Record<string, unknown>): string {
    const userId = member.user_id;
    if (typeof userId !== 'string' || userId === '') {
        throw new Error('team-page: user_id required');
    }
    return userId;
}

function memberDisplayName(member: Record<string, unknown>, fallback: string): string {
    const name = member.name;
    if (typeof name === 'string' && name !== '') return name;
    const email = member.email;
    if (typeof email === 'string' && email !== '') return email;
    return fallback;
}

function memberRoles(member: Record<string, unknown>): string[] {
    const roles = member.roles;
    if (roles === undefined || roles === null) return [];
    if (!Array.isArray(roles)) return [];
    const out: string[] = [];
    for (const role of roles) {
        if (typeof role !== 'string') {
            throw new Error('team-page: role must be a string');
        }
        out.push(role);
    }
    return out;
}

export class FrontendTeamPage extends PlatformPage {
    static override styles: CSSResultGroup = [
        PlatformPage.styles,
        css`
            :host { display: block; }

            .role-filters {
                display: flex;
                flex-wrap: nowrap;
                align-items: center;
                gap: var(--space-2);
                margin-bottom: var(--space-3);
                padding-bottom: var(--space-1);
                overflow-x: auto;
                -webkit-overflow-scrolling: touch;
                scrollbar-width: thin;
            }
            .role-filters::-webkit-scrollbar { height: 4px; }
            .filter-tag {
                flex: 0 0 auto;
                padding: var(--space-2) var(--space-3);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-full);
                background: var(--glass-solid-subtle);
                color: var(--text-secondary);
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                cursor: pointer;
                white-space: nowrap;
                transition: background var(--duration-fast), color var(--duration-fast), border-color var(--duration-fast);
            }
            .filter-tag:hover {
                background: var(--glass-solid-medium);
                color: var(--text-primary);
            }
            .filter-tag[aria-pressed="true"] {
                background: var(--accent-subtle);
                border-color: var(--accent);
                color: var(--accent);
            }

            .invite-toolbar {
                margin-bottom: var(--space-4);
                padding: var(--space-3);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
            }
            .invite-row {
                display: flex;
                flex-direction: row;
                align-items: center;
                gap: var(--space-2);
                width: 100%;
                box-sizing: border-box;
            }
            .invite-row platform-field.invite-role {
                flex: 1 1 0;
                min-width: 0;
            }
            .invite-row .btn { flex: 0 0 auto; white-space: nowrap; }
            .btn-invite {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
            }
            .btn-invite platform-icon { color: inherit; flex-shrink: 0; }

            .btn {
                padding: var(--space-2) var(--space-4);
                background: var(--accent); color: white; border: none;
                border-radius: var(--radius-md); cursor: pointer;
                font-size: var(--text-sm); font-weight: var(--font-medium);
            }
            .btn:disabled { opacity: 0.6; cursor: not-allowed; }
            .btn:hover:not(:disabled) { filter: brightness(1.1); }
            .btn-ghost {
                background: transparent; color: var(--text-secondary);
                border: 1px solid var(--glass-border-subtle);
            }
            .btn-ghost:hover { color: var(--text-primary); border-color: var(--accent); }
            .btn-danger { color: var(--error); }

            .team-table { display: none; }
            @media (min-width: 768px) {
                .team-table { display: block; width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch; }
            }
            .team-table table { width: 100%; min-width: 520px; border-collapse: collapse; }
            th, td {
                padding: var(--space-3);
                border-bottom: 1px solid var(--glass-border-subtle);
                text-align: left;
            }
            th {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                text-transform: uppercase; letter-spacing: 0.05em;
            }
            td { color: var(--text-primary); font-size: var(--text-sm); vertical-align: middle; }
            td.actions { text-align: right; }
            td.actions button + button { margin-left: var(--space-2); }

            .member-cards {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }
            @media (min-width: 768px) {
                .member-cards { display: none; }
            }
            .member-card {
                padding: var(--space-3);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
            }
            .member-card-top {
                display: flex;
                align-items: flex-start;
                justify-content: space-between;
                gap: var(--space-2);
            }
            .member-card-top platform-user-chip { min-width: 0; }
            .member-card-actions { flex: 0 0 auto; }
            .member-card-email {
                margin-top: var(--space-2);
                font-size: var(--text-sm);
                color: var(--text-secondary);
                word-break: break-all;
            }
            .member-card-roles {
                margin-top: var(--space-2);
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                gap: var(--space-1);
            }

            .role-tag {
                display: inline-block;
                padding: 2px 8px;
                background: var(--glass-solid-medium);
                border-radius: var(--radius-full);
                font-size: var(--text-xs); color: var(--text-secondary);
            }
            .role-tag.owner { background: var(--accent); color: white; }
            platform-empty-state { margin-top: var(--space-4); }
        `,
        frontendIslandPageBodyStyles,
    ];

    static override properties: PropertyDeclarations = {
        _selectedRole: { state: true },
        _filterRole: { state: true },
    }
    declare _selectedRole: string;
    declare _filterRole: string | null;
;

    constructor() {
        super();
        this._members = this.useResource('frontend/team', { autoload: true });
        this._invite = this.useOp('frontend/team_invite');
        this._selectedRole = 'developer';
        this._filterRole = null;
    }
    private _members: ResourceController;
    private _invite: OpController;


    async _copyInviteForRole() {
        if (this._invite.busy) return;
        const role = this._selectedRole;
        const links = this._invite.state.links;
        if (!isPlainRecord(links)) {
            throw new Error('team-page: invite links must be an object');
        }
        const cached = links[role];
        let link = typeof cached === 'string' && cached.length > 0 ? cached : '';
        if (link === '') {
            const result = await this._invite.run({ role });
            if (!isPlainRecord(result)) {
                this.toast('team_page.err_invite', { type: 'error' });
                return;
            }
            const inviteUrl = result.invite_url;
            if (typeof inviteUrl !== 'string' || inviteUrl.length === 0) {
                this.toast('team_page.err_invite', { type: 'error' });
                return;
            }
            link = inviteUrl;
        }
        this.copyToClipboard(link, {
            success_i18n_key: 'team_page.toast_invite_copied',
            error_i18n_key: 'team_page.err_clipboard',
        });
    }

    async _removeMember(member: Record<string, unknown>) {
        const name = memberDisplayName(member, this.t('team_page.member_fallback'));
        const message = this.t('team_page.confirm_remove', { name });
        if (!(await platformConfirm(message))) return;
        this._members.remove(memberUserId(member));
    }

    _isOwner(member: Record<string, unknown>) {
        return memberRoles(member).includes('owner');
    }

    _memberMatchesFilter(member: Record<string, unknown>) {
        if (this._filterRole === null) return true;
        return memberRoles(member).includes(this._filterRole);
    }

    _filteredItems(items: readonly Record<string, unknown>[]): readonly Record<string, unknown>[] {
        return items.filter((m) => this._memberMatchesFilter(m));
    }

    _setFilter(role: string | null) {
        this._filterRole = role;
    }

    _inviteRoleEnumConfig() {
        return {
            values: INVITE_ROLES.map((r) => ({
                value: r,
                label: this.t(`team_roles.${r}`),
            })),
        };
    }

    _renderRoleFilters() {
        return html`
            <div class="role-filters" role="tablist" aria-label=${this.t('team_page.col_role')}>
                <button
                    type="button"
                    class="filter-tag"
                    aria-pressed=${this._filterRole === null ? 'true' : 'false'}
                    @click=${() => this._setFilter(null)}
                >${this.t('team_page.filter_all')}</button>
                ${ROLE_FILTER_KEYS.map((key) => html`
                    <button
                        type="button"
                        class="filter-tag"
                        aria-pressed=${this._filterRole === key ? 'true' : 'false'}
                        @click=${() => this._setFilter(key)}
                    >${this.t(`team_roles.${key}`)}</button>
                `)}
            </div>
        `;
    }

    _renderRoles(member: Record<string, unknown>) {
        const roles = memberRoles(member);
        if (roles.length === 0) return '';
        return roles.map((r) => html`
            <span class="role-tag ${r === 'owner' ? 'owner' : ''}">${this.t(`team_roles.${r}`)}</span>
        `);
    }

    _renderInviteToolbar() {
        return html`
            <div class="invite-toolbar">
                <div class="invite-row">
                    <platform-field
                        class="invite-role"
                        type="enum"
                        mode="edit"
                        pill-density="dense"
                        pill-embed
                        label=""
                        .value=${this._selectedRole}
                        .config=${this._inviteRoleEnumConfig()}
                        ?disabled=${this._invite.busy}
                        @change=${(e: CustomEvent) => {
                            if (!e.detail || typeof e.detail.value !== 'string') {
                                throw new Error('team page: invite role expects detail.value string');
                            }
                            this._selectedRole = e.detail.value;
                        }}
                    ></platform-field>
                    <button
                        type="button"
                        class="btn btn-invite"
                        ?disabled=${this._invite.busy}
                        @click=${this._copyInviteForRole}
                    >
                        <platform-icon name="copy" size="18"></platform-icon>
                        <span>${this.t('team_page.copy_invite')}</span>
                    </button>
                </div>
            </div>
        `;
    }

    _renderEmpty() {
        return html`
            <platform-empty-state
                icon="users"
                title=${this.t('team_page.empty_title')}
                hint=${this.t('team_page.empty_description')}
            ></platform-empty-state>
        `;
    }

    _renderFilterEmpty() {
        return html`
            <platform-empty-state
                icon="search"
                title=${this.t('team_page.filter_empty')}
            ></platform-empty-state>
        `;
    }

    _renderRow(m: Record<string, unknown>) {
        const isOwner = this._isOwner(m);
        return html`
            <tr>
                <td><platform-user-chip user-id=${memberUserId(m)} size="md"></platform-user-chip></td>
                <td>${typeof m.email === 'string' ? m.email : ''}</td>
                <td>
                    ${m.is_flow_employee === true
                        ? html`<span class="role-tag">${this.t('team_page.flow_employee_badge')}</span>`
                        : ''}
                    ${this._renderRoles(m)}
                </td>
                <td class="actions">
                    ${isOwner ? '' : html`
                        <button class="btn btn-ghost btn-danger" @click=${() => this._removeMember(m)}>
                            ${this.t('team_page.remove')}
                        </button>
                    `}
                </td>
            </tr>
        `;
    }

    _renderCard(m: Record<string, unknown>) {
        const isOwner = this._isOwner(m);
        return html`
            <div class="member-card">
                <div class="member-card-top">
                    <platform-user-chip user-id=${memberUserId(m)} size="md"></platform-user-chip>
                    <div class="member-card-actions">
                        ${isOwner ? '' : html`
                            <button class="btn btn-ghost btn-danger" @click=${() => this._removeMember(m)}>
                                ${this.t('team_page.remove')}
                            </button>
                        `}
                    </div>
                </div>
                <div class="member-card-email">${typeof m.email === 'string' ? m.email : ''}</div>
                <div class="member-card-roles">
                    ${m.is_flow_employee === true
                        ? html`<span class="role-tag">${this.t('team_page.flow_employee_badge')}</span>`
                        : ''}
                    ${this._renderRoles(m)}
                </div>
            </div>
        `;
    }

    _renderMemberList(members: readonly Record<string, unknown>[]) {
        const visible = this._filteredItems(members);
        if (visible.length === 0) {
            return this._renderFilterEmpty();
        }
        return html`
            <div class="team-table">
                <table>
                    <thead><tr>
                        <th>${this.t('team_page.col_name')}</th>
                        <th>${this.t('team_page.col_email')}</th>
                        <th>${this.t('team_page.col_role')}</th>
                        <th>${this.t('team_page.col_actions')}</th>
                    </tr></thead>
                    <tbody>
                        ${visible.map((m) => this._renderRow(m))}
                    </tbody>
                </table>
            </div>
            <div class="member-cards">
                ${visible.map((m) => this._renderCard(m))}
            </div>
        `;
    }

    override render(): TemplateResult {
        const members = this._members.items;
        const loading = this._members.loading;
        return html`
            <page-header
                title=${this.t('team_page.title')}
                subtitle=${this.t('team_page.subtitle')}
            ></page-header>
            <div class="page-body">
            ${this._renderInviteToolbar()}
            ${this._renderRoleFilters()}
            ${loading && members.length === 0
                ? html`<platform-empty-state loading></platform-empty-state>`
                : members.length === 0
                    ? this._renderEmpty()
                    : this._renderMemberList(members)
            }
            </div>
        `;
    }
}

customElements.define('frontend-team-page', FrontendTeamPage);
