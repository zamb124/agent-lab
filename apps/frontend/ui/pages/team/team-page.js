/**
 * Team Page - Управление командой компании
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { copyTextToClipboard } from '@platform/lib/utils/clipboard.js';
import { createAvatarRetry } from '@platform/lib/utils/avatar-retry.js';
import { FrontendStore } from '../../store/frontend.store.js';
import '../../modals/edit-team-member-modal.js';
import '@platform/lib/components/layout/page-header.js';

export class TeamPage extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                height: 100%;
            }

            .primary-button {
                padding: var(--space-3) var(--space-6);
                background: var(--accent);
                color: white;
                border: none;
                border-radius: var(--radius-lg);
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                cursor: pointer;
                transition: all var(--duration-fast);
                box-shadow: 0 4px 12px rgba(16, 185, 129, 0.25);
            }

            .primary-button:hover {
                transform: scale(1.05);
                box-shadow: 0 8px 24px rgba(16, 185, 129, 0.4);
            }

            .members-grid {
                display: grid;
                gap: 16px;
            }

            .member-card {
                background: var(--glass-solid-medium);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-xl);
                padding: var(--space-6);
                backdrop-filter: blur(20px);
                display: flex;
                align-items: center;
                gap: var(--space-5);
                transition: all var(--duration-normal);
            }

            .member-card:hover {
                background: var(--glass-solid-strong);
                border-color: var(--glass-border-medium);
            }

            .member-avatar {
                width: 56px;
                height: 56px;
                border-radius: 50%;
                background: var(--accent-gradient);
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: var(--text-xl);
                font-weight: var(--font-semibold);
                color: white;
                flex-shrink: 0;
                overflow: hidden;
            }

            .member-avatar img {
                width: 100%;
                height: 100%;
                object-fit: cover;
                border-radius: 50%;
            }

            .member-info {
                flex: 1;
            }

            .member-name {
                font-size: var(--text-lg);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                margin: 0 0 var(--space-1) 0;
            }

            .member-email {
                font-size: var(--text-sm);
                color: var(--text-secondary);
                margin: 0 0 var(--space-2) 0;
            }

            .member-roles {
                display: flex;
                gap: var(--space-2);
                flex-wrap: wrap;
            }

            .role-badge {
                padding: var(--space-1) var(--space-3);
                background: var(--accent-subtle);
                border: 1px solid var(--accent);
                border-radius: var(--radius-md);
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                color: var(--accent);
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }

            .role-badge.owner {
                background: rgba(255, 215, 0, 0.15);
                border-color: rgba(255, 215, 0, 0.3);
                color: #FFD700;
            }

            .role-badge.admin {
                background: rgba(255, 69, 58, 0.15);
                border-color: rgba(255, 69, 58, 0.3);
                color: #FF453A;
            }

            .member-actions {
                display: flex;
                gap: var(--space-2);
            }

            .icon-button {
                width: 40px;
                height: 40px;
                display: flex;
                align-items: center;
                justify-content: center;
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                color: var(--text-secondary);
                font-size: var(--text-base);
                cursor: pointer;
                transition: all var(--duration-fast);
            }

            .icon-button:hover {
                background: var(--glass-solid-medium);
                transform: scale(1.1);
            }

            .icon-button.danger:hover {
                background: var(--error-subtle);
                border-color: var(--error);
                color: var(--error);
            }

            .empty-state {
                text-align: center;
                padding: var(--space-16) var(--space-6);
                color: var(--text-secondary);
            }

            .empty-icon {
                font-size: 64px;
                margin-bottom: var(--space-4);
            }

            .empty-title {
                font-size: var(--text-2xl);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                margin: 0 0 var(--space-2) 0;
            }

            .empty-description {
                font-size: var(--text-base);
                margin: 0 0 var(--space-6) 0;
            }

            .loading-state {
                text-align: center;
                padding: var(--space-12);
                color: var(--text-secondary);
            }

            @media (max-width: 768px) {
                .page-header {
                    flex-direction: column;
                    align-items: flex-start;
                    gap: var(--space-4);
                }

                .member-card {
                    flex-direction: column;
                    align-items: flex-start;
                }

                .member-actions {
                    width: 100%;
                    justify-content: flex-end;
                }
            }
        `
    ];

    constructor() {
        super();
        this._canManageTeam = false;
        this._avatarRetries = new Map();
        this.state = this.use((s) => ({
            members: s.entities.team.members,
            loading: s.entities.team.loading,
        }));
    }

    disconnectedCallback() {
        super.disconnectedCallback?.();
        for (const ctrl of this._avatarRetries.values()) {
            ctrl.cancel();
        }
        this._avatarRetries.clear();
    }

    _getAvatarRetry(memberId) {
        if (!this._avatarRetries.has(memberId)) {
            this._avatarRetries.set(memberId, createAvatarRetry(() => this.requestUpdate()));
        }
        return this._avatarRetries.get(memberId);
    }

    _computeCanManageTeam() {
        const u = this.services.get('auth').user;
        if (!u || !Array.isArray(u.roles)) {
            return false;
        }
        return u.roles.includes('owner') || u.roles.includes('admin');
    }

    async connectedCallback() {
        super.connectedCallback();
        this._i18nUnsub = this.i18n.subscribe(() => this.requestUpdate());
        await this.services.get('auth').validateToken();
        this._canManageTeam = this._computeCanManageTeam();
        this.requestUpdate();
        await this._loadMembers();
    }

    disconnectedCallback() {
        if (this._i18nUnsub) {
            this._i18nUnsub();
            this._i18nUnsub = null;
        }
        super.disconnectedCallback();
    }

    async _loadMembers() {
        FrontendStore.setTeamLoading(true);
        const teamMembers = await this.services.get('team').getMembers();
        FrontendStore.setTeamMembers(teamMembers);
    }

    render() {
        const td = (key, params) => this.i18n.t(key, params ?? {}, 'dashboard');
        return html`
            <page-header title=${td('team_page.title')}>
                <button slot="actions" class="primary-button" @click=${this._onCopyInviteLink}>
                    ${td('team_page.copy_invite')}
                </button>
            </page-header>

            ${this._renderContent()}
        `;
    }

    _renderContent() {
        const td = (key, params) => this.i18n.t(key, params ?? {}, 'dashboard');
        const { members, loading } = this.state.value;
        
        if (loading) {
            return html`<div class="loading-state">${td('team_page.loading')}</div>`;
        }

        if (members.length === 0) {
            return html`
                <div class="empty-state">
                    <div class="empty-icon">T</div>
                    <h2 class="empty-title">${td('team_page.empty_title')}</h2>
                    <p class="empty-description">${td('team_page.empty_description')}</p>
                    <button class="primary-button" @click=${this._onCopyInviteLink}>
                        ${td('team_page.copy_invite_action')}
                    </button>
                </div>
            `;
        }

        return html`
            <div class="members-grid">
                ${members.map((member) => this._renderMemberCard(member))}
            </div>
        `;
    }

    _renderMemberCard(member) {
        const td = (key, params) => this.i18n.t(key, params ?? {}, 'dashboard');
        const roleLabel = (r) => this.i18n.t(`team_roles.${r}`, {}, 'dashboard');
        const initials = this._getInitials(member.name);
        const retry = this._getAvatarRetry(member.user_id);
        const originalUrl = member.avatar_url ?? null;
        const avatarSrc = retry.currentSrc(originalUrl);
        
        return html`
            <div class="member-card">
                <div class="member-avatar">
                    ${avatarSrc
                        ? html`<img src=${avatarSrc} alt=""
                            @load=${() => retry.onLoad()}
                            @error=${() => retry.onError(originalUrl)} />`
                        : initials}
                </div>
                
                <div class="member-info">
                    <h3 class="member-name">${member.name}</h3>
                    ${member.email ? html`
                        <p class="member-email">${member.email}</p>
                    ` : ''}
                    <div class="member-roles">
                        ${member.roles.map((role) => html`
                            <span class="role-badge ${role}">${roleLabel(role)}</span>
                        `)}
                    </div>
                </div>
                
                <div class="member-actions">
                    ${this._canManageTeam
                        ? html`
                              <button
                                  class="icon-button"
                                  title=${td('team_page.edit_role')}
                                  @click=${() => this._onEditRole(member)}
                              >
                                  E
                              </button>
                              ${!member.roles.includes('owner')
                                  ? html`
                                        <button
                                            class="icon-button danger"
                                            title=${td('team_page.remove')}
                                            @click=${() => this._onRemoveMember(member)}
                                        >
                                            X
                                        </button>
                                    `
                                  : ''}
                          `
                        : ''}
                </div>
            </div>
        `;
    }

    _getInitials(name) {
        if (!name) return 'U';
        const parts = name.split(' ');
        if (parts.length >= 2) {
            return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
        }
        return name[0].toUpperCase();
    }

    async _onCopyInviteLink() {
        const td = (key) => this.i18n.t(key, {}, 'dashboard');
        let result;
        try {
            result = await this.services.get('team').generateInviteLink('developer');
        } catch {
            this.error(td('team_page.err_invite'));
            return;
        }

        try {
            await copyTextToClipboard(result.invite_url);
            this.success(td('team_page.toast_invite_copied'));
        } catch {
            this.error(td('team_page.err_clipboard'));
        }
    }

    async _reloadMembers() {
        FrontendStore.setTeamLoading(true);
        const members = await this.services.get('team').getMembers();
        FrontendStore.setTeamMembers(members);
    }

    _onEditRole(member) {
        const modal = document.createElement('edit-team-member-modal');
        document.body.appendChild(modal);
        modal.addEventListener('close', () => modal.remove());
        modal.addEventListener('saved', () => this._reloadMembers());
        modal.show(member);
    }

    async _onRemoveMember(member) {
        const td = (key, params) => this.i18n.t(key, params ?? {}, 'dashboard');
        const confirmed = confirm(td('team_page.confirm_remove', { name: member.name }));
        if (!confirmed) return;
        
        await this.services.get('team').removeMember(member.user_id);
        await this._reloadMembers();
        this.success(td('team_page.toast_removed', { name: member.name }));
    }
}

customElements.define('team-page', TeamPage);
