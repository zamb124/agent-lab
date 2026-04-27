/**
 * Team page — участники компании, роли, ссылки-приглашения.
 *
 * Поток данных:
 *   - resource frontend/team_members → list/update/remove
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
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-user-chip.js';

const INVITE_ROLES = Object.freeze(['developer', 'admin', 'viewer']);
const ROLE_FILTER_KEYS = Object.freeze(['owner', 'admin', 'developer', 'viewer']);

export class FrontendTeamPage extends PlatformPage {
    static styles = [
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
            .invite-row .invite-role {
                flex: 1 1 0;
                min-width: 0;
                padding: var(--space-2) var(--space-3);
                background: var(--glass-solid-strong);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                color: var(--text-primary);
                font-size: var(--text-sm);
                cursor: pointer;
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

            .empty {
                padding: var(--space-8) var(--space-6);
                text-align: center; color: var(--text-tertiary);
                background: var(--glass-solid-subtle);
                border: 1px dashed var(--glass-border-subtle);
                border-radius: var(--radius-lg);
            }
            .empty .empty-title { color: var(--text-primary); font-weight: var(--font-semibold); margin-bottom: var(--space-2); }
        `,
        frontendIslandPageBodyStyles,
    ];

    static properties = {
        _selectedRole: { state: true },
        _filterRole: { state: true },
    };

    constructor() {
        super();
        this._members = this.useResource('frontend/team_members', { autoload: true });
        this._invite = this.useOp('frontend/team_invite');
        this._selectedRole = 'developer';
        this._filterRole = null;
    }

    async _copyInviteForRole() {
        if (this._invite.busy) return;
        const role = this._selectedRole;
        const links = this._invite.state.links;
        const cached = links[role];
        let link = typeof cached === 'string' && cached.length > 0 ? cached : '';
        if (link === '') {
            const result = await this._invite.run({ role });
            if (!result || typeof result.link !== 'string' || result.link.length === 0) {
                this.toast('team_page.err_invite', { type: 'error' });
                return;
            }
            link = result.link;
        }
        this.copyToClipboard(link, {
            success_i18n_key: 'team_page.toast_invite_copied',
            error_i18n_key: 'team_page.err_clipboard',
        });
    }

    _removeMember(member) {
        const name = member.name || member.email || this.t('team_page.member_fallback');
        const message = this.t('team_page.confirm_remove', { name });
        if (!confirm(message)) return;
        this._members.remove(member.user_id);
    }

    _isOwner(member) {
        return Array.isArray(member.roles) && member.roles.includes('owner');
    }

    _memberMatchesFilter(member) {
        if (this._filterRole === null) return true;
        const roles = member.roles;
        if (!Array.isArray(roles)) return false;
        return roles.includes(this._filterRole);
    }

    _filteredItems(items) {
        return items.filter((m) => this._memberMatchesFilter(m));
    }

    _setFilter(role) {
        this._filterRole = role;
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

    _renderRoles(member) {
        const roles = member.roles || [];
        if (roles.length === 0) return '';
        return roles.map((r) => html`
            <span class="role-tag ${r === 'owner' ? 'owner' : ''}">${this.t(`team_roles.${r}`)}</span>
        `);
    }

    _renderInviteToolbar() {
        return html`
            <div class="invite-toolbar">
                <div class="invite-row">
                    <select
                        class="invite-role"
                        .value=${this._selectedRole}
                        ?disabled=${this._invite.busy}
                        @change=${(e) => { this._selectedRole = e.target.value; }}
                    >
                        ${INVITE_ROLES.map((r) => html`
                            <option value=${r}>${this.t(`team_roles.${r}`)}</option>
                        `)}
                    </select>
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
            <div class="empty">
                <div class="empty-title">${this.t('team_page.empty_title')}</div>
                <div>${this.t('team_page.empty_description')}</div>
            </div>
        `;
    }

    _renderFilterEmpty() {
        return html`
            <div class="empty">
                <div class="empty-title">${this.t('team_page.filter_empty')}</div>
            </div>
        `;
    }

    _renderRow(m) {
        const isOwner = this._isOwner(m);
        return html`
            <tr>
                <td><platform-user-chip user-id=${m.user_id} size="md"></platform-user-chip></td>
                <td>${m.email || ''}</td>
                <td>${this._renderRoles(m)}</td>
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

    _renderCard(m) {
        const isOwner = this._isOwner(m);
        return html`
            <div class="member-card">
                <div class="member-card-top">
                    <platform-user-chip user-id=${m.user_id} size="md"></platform-user-chip>
                    <div class="member-card-actions">
                        ${isOwner ? '' : html`
                            <button class="btn btn-ghost btn-danger" @click=${() => this._removeMember(m)}>
                                ${this.t('team_page.remove')}
                            </button>
                        `}
                    </div>
                </div>
                <div class="member-card-email">${m.email || ''}</div>
                <div class="member-card-roles">${this._renderRoles(m)}</div>
            </div>
        `;
    }

    _renderMemberList(members) {
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

    render() {
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
                ? html`<div class="empty"><glass-spinner></glass-spinner></div>`
                : members.length === 0
                    ? this._renderEmpty()
                    : this._renderMemberList(members)
            }
            </div>
        `;
    }
}

customElements.define('frontend-team-page', FrontendTeamPage);
