/**
 * Grants Panel - Управление доступами к сущности
 * Показывает текущие гранты и позволяет создавать новые
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
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

    async _onRevokeGrant(grantId) {
        if (!confirm(this.i18n.t('grants.confirm_revoke'))) return;
        
        const crmApi = this.services.get('crmApi');
        await CRMStore.revokeGrant(crmApi, grantId);
        this.success(this.i18n.t('grants.success_revoked'));
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
            return this.i18n.t('grants.target_public');
        }
        if (grant.grant_type === 'user') {
            return grant.target_user_id || this.i18n.t('grants.target_user_fallback');
        }
        if (grant.grant_type === 'company') {
            return grant.target_company_id || this.i18n.t('grants.target_company_fallback');
        }
        return this.i18n.t('grants.unknown');
    }

    _getRoleLabel(role) {
        switch (role) {
            case 'viewer':
                return this.i18n.t('grants.role_viewer');
            case 'editor':
                return this.i18n.t('grants.role_editor');
            case 'admin':
                return this.i18n.t('grants.role_admin');
            default:
                return role;
        }
    }

    _formatGrantExpiry(iso) {
        const loc = this.i18n.getCurrentLocale() === 'ru' ? 'ru-RU' : 'en-US';
        return new Date(iso).toLocaleDateString(loc, {
            day: 'numeric',
            month: 'short',
            year: 'numeric',
        });
    }

    render() {
        if (!this.entityId) {
            return '';
        }

        return html`
            <div class="section">
                <div class="section-title">${this.i18n.t('grants.section_title')}</div>

                ${this._loading ? html`
                    <div class="empty-grants">${this.i18n.t('grants.loading')}</div>
                ` : this._grants.length === 0 ? html`
                    <div class="empty-grants">
                        ${this.i18n.t('grants.empty_entity')}
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
                                            ? this.i18n.t('grants.expires', {
                                                  date: this._formatGrantExpiry(grant.expires_at),
                                              })
                                            : this.i18n.t('grants.perpetual')
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
                                    ${this.i18n.t('grants.revoke')}
                                </button>
                            </div>
                        `)}
                    </div>
                `}
            </div>
        `;
    }
}

customElements.define('grants-panel', GrantsPanel);
