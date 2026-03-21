/**
 * Team Page - Управление командой компании
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { copyTextToClipboard } from '@platform/lib/utils/clipboard.js';
import { FrontendStore } from '../../store/frontend.store.js';
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
        this.state = this.use((s) => ({
            members: s.entities.team.members,
            loading: s.entities.team.loading,
        }));
    }

    async connectedCallback() {
        super.connectedCallback();
        await this._loadMembers();
    }

    async _loadMembers() {
        const { members } = this.state.value;
        if (members.length > 0) return;
        
        FrontendStore.setTeamLoading(true);
        const teamMembers = await this.services.get('team').getMembers();
        FrontendStore.setTeamMembers(teamMembers);
    }

    render() {
        return html`
            <page-header title="Команда">
                <button slot="actions" class="primary-button" @click=${this._onCopyInviteLink}>
                    + Скопировать ссылку-приглашение
                </button>
            </page-header>

            ${this._renderContent()}
        `;
    }

    _renderContent() {
        const { members, loading } = this.state.value;
        
        if (loading) {
            return html`<div class="loading-state">Загрузка...</div>`;
        }

        if (members.length === 0) {
            return html`
                <div class="empty-state">
                    <div class="empty-icon">T</div>
                    <h2 class="empty-title">Нет участников</h2>
                    <p class="empty-description">Скопируйте ссылку-приглашение и отправьте коллеге</p>
                    <button class="primary-button" @click=${this._onCopyInviteLink}>
                        Скопировать ссылку-приглашение
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
        const initials = this._getInitials(member.name);
        
        return html`
            <div class="member-card">
                <div class="member-avatar">${initials}</div>
                
                <div class="member-info">
                    <h3 class="member-name">${member.name}</h3>
                    ${member.email ? html`
                        <p class="member-email">${member.email}</p>
                    ` : ''}
                    <div class="member-roles">
                        ${member.roles.map((role) => html`
                            <span class="role-badge ${role}">${role}</span>
                        `)}
                    </div>
                </div>
                
                <div class="member-actions">
                    <button 
                        class="icon-button" 
                        title="Изменить роль"
                        @click=${() => this._onEditRole(member)}
                    >
                        E
                    </button>
                    ${!member.roles.includes('owner') ? html`
                        <button 
                            class="icon-button danger" 
                            title="Удалить"
                            @click=${() => this._onRemoveMember(member)}
                        >
                            X
                        </button>
                    ` : ''}
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
        let result;
        try {
            result = await this.services.get('team').generateInviteLink('developer');
        } catch {
            this.error('Не удалось создать ссылку-приглашение');
            return;
        }

        try {
            await copyTextToClipboard(result.invite_url);
            this.success('Ссылка-приглашение скопирована в буфер обмена');
        } catch {
            this.error('Ссылка создана, но буфер обмена недоступен. Откройте ответ API и скопируйте invite_url.');
        }
    }

    async _reloadMembers() {
        FrontendStore.setTeamLoading(true);
        const members = await this.services.get('team').getMembers();
        FrontendStore.setTeamMembers(members);
    }

    _onEditRole(member) {
        this.info('Функция в разработке');
    }

    async _onRemoveMember(member) {
        const confirmed = confirm(`Удалить ${member.name} из команды?`);
        if (!confirmed) return;
        
        await this.services.get('team').removeMember(member.user_id);
        await this._reloadMembers();
        this.success(`${member.name} удален из команды`);
    }
}

customElements.define('team-page', TeamPage);
