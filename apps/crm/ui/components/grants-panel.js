/**
 * Grants Panel - Управление доступами к сущности
 * Показывает текущие гранты и позволяет создавать новые
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { CRMStore } from '../store/crm.store.js';
import '@platform/lib/components/platform-icon.js';

export class GrantsPanel extends PlatformElement {
    static properties = {
        entityId: { type: String },
        _grants: { state: true },
        _loading: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        buttonStyles,
        css`
            :host {
                display: block;
            }

            .section {
                margin-top: var(--space-6);
            }

            .section-title {
                font-size: var(--text-sm);
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.05em;
                color: var(--text-tertiary);
                margin-bottom: var(--space-3);
            }

            .grants-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }

            .grant-item {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                padding: var(--space-3);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
            }

            .grant-icon {
                width: 32px;
                height: 32px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-md);
                font-size: var(--text-lg);
            }

            .grant-icon.public {
                background: rgba(255, 149, 0, 0.15);
                color: #ff9500;
            }

            .grant-icon.user {
                background: rgba(0, 122, 255, 0.15);
                color: #007aff;
            }

            .grant-icon.company {
                background: rgba(88, 86, 214, 0.15);
                color: #5856d6;
            }

            .grant-content {
                flex: 1;
            }

            .grant-target {
                font-size: var(--text-sm);
                font-weight: 500;
                color: var(--text-primary);
            }

            .grant-meta {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }

            .grant-role {
                padding: 2px 8px;
                background: var(--glass-solid-subtle);
                border-radius: var(--radius-sm);
                font-size: var(--text-xs);
                color: var(--text-secondary);
            }

            .revoke-btn {
                padding: var(--space-1) var(--space-2);
                background: transparent;
                border: 1px solid transparent;
                border-radius: var(--radius-md);
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                cursor: pointer;
                transition: all 0.2s;
            }

            .revoke-btn:hover {
                background: rgba(244, 63, 94, 0.1);
                border-color: var(--error);
                color: var(--error);
            }

            .action-buttons {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
                margin-top: var(--space-3);
            }

            .action-btn {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                color: var(--text-secondary);
                font-size: var(--text-sm);
                cursor: pointer;
                transition: all 0.2s;
            }

            .action-btn:hover {
                background: var(--glass-solid-medium);
                color: var(--text-primary);
            }

            .action-btn.public {
                border-color: rgba(255, 149, 0, 0.3);
            }

            .action-btn.public:hover {
                background: rgba(255, 149, 0, 0.1);
                color: #ff9500;
            }

            .empty-grants {
                padding: var(--space-4);
                text-align: center;
                color: var(--text-tertiary);
                font-size: var(--text-sm);
                background: var(--glass-solid-subtle);
                border-radius: var(--radius-lg);
            }
        `
    ];

    constructor() {
        super();
        this.entityId = null;
        this._grants = [];
        this._loading = false;

        this._unsubscribe = CRMStore.subscribe(state => {
            this._grants = state.grants.currentEntityGrants || [];
            this._loading = state.grants.loading;
        });
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._unsubscribe?.();
    }

    updated(changedProperties) {
        if (changedProperties.has('entityId') && this.entityId) {
            this._loadGrants();
        }
    }

    async _loadGrants() {
        if (!this.entityId) return;
        const crmApi = this.services.get('crmApi');
        await CRMStore.loadEntityGrants(crmApi, this.entityId);
    }

    async _onMakePublic() {
        const crmApi = this.services.get('crmApi');
        await CRMStore.makeEntityPublic(crmApi, this.entityId);
        this.success('Сущность стала публичной');
    }

    _onShareToUser() {
        const modal = document.createElement('share-modal');
        modal.entityId = this.entityId;
        modal.shareType = 'user';
        document.body.appendChild(modal);
        modal.showModal();
        modal.addEventListener('close', () => modal.remove());
        modal.addEventListener('shared', () => this._loadGrants());
    }

    _onShareToCompany() {
        const modal = document.createElement('share-modal');
        modal.entityId = this.entityId;
        modal.shareType = 'company';
        document.body.appendChild(modal);
        modal.showModal();
        modal.addEventListener('close', () => modal.remove());
        modal.addEventListener('shared', () => this._loadGrants());
    }

    async _onRevokeGrant(grantId) {
        if (!confirm('Отозвать доступ?')) return;
        
        const crmApi = this.services.get('crmApi');
        await CRMStore.revokeGrant(crmApi, grantId);
        this.success('Доступ отозван');
    }

    _getGrantTypeIcon(grantType) {
        switch (grantType) {
            case 'public':
                return 'globe';
            case 'user':
                return 'user';
            case 'company':
                return 'building-one';
            default:
                return 'lock';
        }
    }

    _getGrantTarget(grant) {
        if (grant.grant_type === 'public') {
            return 'Публичный доступ';
        }
        if (grant.grant_type === 'user') {
            return grant.target_user_id || 'Пользователь';
        }
        if (grant.grant_type === 'company') {
            return grant.target_company_id || 'Компания';
        }
        return 'Неизвестно';
    }

    _getRoleLabel(role) {
        switch (role) {
            case 'viewer':
                return 'Просмотр';
            case 'editor':
                return 'Редактирование';
            case 'admin':
                return 'Администратор';
            default:
                return role;
        }
    }

    _hasPublicGrant() {
        return this._grants.some(g => g.grant_type === 'public');
    }

    render() {
        if (!this.entityId) {
            return '';
        }

        return html`
            <div class="section">
                <div class="section-title">Управление доступом</div>

                ${this._loading ? html`
                    <div class="empty-grants">Загрузка...</div>
                ` : this._grants.length === 0 ? html`
                    <div class="empty-grants">
                        Нет настроенных доступов. Только вы можете видеть эту сущность.
                    </div>
                ` : html`
                    <div class="grants-list">
                        ${this._grants.map(grant => html`
                            <div class="grant-item">
                                <div class="grant-icon ${grant.grant_type}">
                                    <platform-icon name="${this._getGrantTypeIcon(grant.grant_type)}" size="18"></platform-icon>
                                </div>
                                <div class="grant-content">
                                    <div class="grant-target">
                                        ${this._getGrantTarget(grant)}
                                    </div>
                                    <div class="grant-meta">
                                        ${grant.expires_at
                                            ? `Истекает: ${new Date(grant.expires_at).toLocaleDateString('ru-RU')}`
                                            : 'Бессрочно'
                                        }
                                    </div>
                                </div>
                                <span class="grant-role">
                                    ${this._getRoleLabel(grant.role)}
                                </span>
                                <button
                                    class="revoke-btn"
                                    @click=${() => this._onRevokeGrant(grant.grant_id)}
                                >
                                    Отозвать
                                </button>
                            </div>
                        `)}
                    </div>
                `}

                <div class="action-buttons">
                    ${!this._hasPublicGrant() ? html`
                        <button class="action-btn public" @click=${this._onMakePublic}>
                            <platform-icon name="globe" size="14"></platform-icon>
                            Сделать публичной
                        </button>
                    ` : ''}
                    <button class="action-btn" @click=${this._onShareToUser}>
                        <platform-icon name="user" size="14"></platform-icon>
                        Поделиться с пользователем
                    </button>
                    <button class="action-btn" @click=${this._onShareToCompany}>
                        <platform-icon name="building-one" size="14"></platform-icon>
                        Поделиться с компанией
                    </button>
                </div>
            </div>
        `;
    }
}

customElements.define('grants-panel', GrantsPanel);
