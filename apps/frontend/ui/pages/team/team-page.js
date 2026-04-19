/**
 * Team page — участники компании, роли, ссылки-приглашения.
 *
 * Поток данных:
 *   - resource frontend/team_members → list/update/remove
 *   - op       frontend/team_invite  → генерация invite-ссылки на роль,
 *     результат хранится в slice как `links: { [role]: link }`.
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
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-user-chip.js';

const INVITE_ROLES = Object.freeze(['developer', 'admin', 'viewer']);

export class FrontendTeamPage extends PlatformPage {
    static styles = [
        PlatformPage.styles,
        css`
            :host { display: block; }

            .invite-toolbar {
                display: flex; align-items: center; flex-wrap: nowrap;
                gap: var(--space-2);
                margin-bottom: var(--space-4);
                padding: var(--space-3);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
            }
            .invite-toolbar .invite-role {
                flex: 0 0 auto;
                width: auto;
                min-width: 160px;
                padding: var(--space-2) var(--space-3);
                background: var(--glass-solid-strong);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                color: var(--text-primary);
                font-size: var(--text-sm);
                cursor: pointer;
            }
            .invite-toolbar .btn { flex: 0 0 auto; white-space: nowrap; }
            .invite-link {
                flex: 1 1 0;
                min-width: 0;
                padding: var(--space-2) var(--space-3);
                font-family: var(--font-mono);
                font-size: var(--text-xs);
                background: var(--glass-solid-strong);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                color: var(--text-primary);
                user-select: all;
                overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
            }

            .btn {
                padding: var(--space-2) var(--space-4);
                background: var(--accent); color: white; border: none;
                border-radius: var(--radius-md); cursor: pointer;
                font-size: var(--text-sm); font-weight: var(--font-medium);
            }
            .btn:hover { filter: brightness(1.1); }
            .btn-ghost {
                background: transparent; color: var(--text-secondary);
                border: 1px solid var(--glass-border-subtle);
            }
            .btn-ghost:hover { color: var(--text-primary); border-color: var(--accent); }
            .btn-danger { color: var(--error); }

            table { width: 100%; border-collapse: collapse; }
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

            .role-tag {
                padding: 2px 8px;
                background: var(--glass-solid-medium);
                border-radius: var(--radius-full);
                font-size: var(--text-xs); color: var(--text-secondary);
                margin-right: var(--space-1);
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
    ];

    static properties = {
        _selectedRole: { state: true },
    };

    constructor() {
        super();
        this._members = this.useResource('frontend/team_members', { autoload: true });
        this._invite = this.useOp('frontend/team_invite');
        this._selectedRole = 'developer';
    }

    _generateInvite() {
        this._invite.run({ role: this._selectedRole });
    }

    _copyInvite(link) {
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

    _renderRoles(member) {
        const roles = member.roles || [];
        if (roles.length === 0) return '';
        return roles.map((r) => html`
            <span class="role-tag ${r === 'owner' ? 'owner' : ''}">${this.t(`team_roles.${r}`)}</span>
        `);
    }

    _renderInviteToolbar(inviteLinks) {
        const link = inviteLinks[this._selectedRole];
        return html`
            <div class="invite-toolbar">
                <select
                    class="invite-role"
                    .value=${this._selectedRole}
                    @change=${(e) => { this._selectedRole = e.target.value; }}
                >
                    ${INVITE_ROLES.map((r) => html`
                        <option value=${r}>${this.t(`team_roles.${r}`)}</option>
                    `)}
                </select>
                ${link ? html`
                    <span class="invite-link" title=${link}>${link}</span>
                    <button class="btn btn-ghost" @click=${() => this._copyInvite(link)}>
                        ${this.t('api_keys_page.copy_title')}
                    </button>
                ` : ''}
                <button class="btn" @click=${this._generateInvite}>
                    ${this.t('team_page.copy_invite')}
                </button>
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

    render() {
        const members = this._members.items;
        const loading = this._members.loading;
        const inviteLinks = this._invite.state.links;
        return html`
            <page-header
                title=${this.t('team_page.title')}
                subtitle=${this.t('team_page.subtitle')}
            ></page-header>

            ${this._renderInviteToolbar(inviteLinks)}

            ${loading && members.length === 0
                ? html`<div class="empty"><glass-spinner></glass-spinner></div>`
                : members.length === 0
                    ? this._renderEmpty()
                    : html`
                        <table>
                            <thead><tr>
                                <th>${this.t('team_page.col_name')}</th>
                                <th>${this.t('team_page.col_email')}</th>
                                <th>${this.t('team_page.col_role')}</th>
                                <th>${this.t('team_page.col_actions')}</th>
                            </tr></thead>
                            <tbody>
                                ${members.map((m) => this._renderRow(m))}
                            </tbody>
                        </table>
                    `
            }
        `;
    }
}

customElements.define('frontend-team-page', FrontendTeamPage);
