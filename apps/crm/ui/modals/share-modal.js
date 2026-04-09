/**
 * Share Modal - Модальное окно для шаринга сущности
 * Использует PlatformModal с fullscreen и drag поддержкой
 */
import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { formStyles } from '@platform/lib/styles/shared/form.styles.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { CRMStore } from '../store/crm.store.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-date-picker.js';

export class ShareModal extends PlatformModal {
    static properties = {
        ...PlatformModal.properties,
        entityId: { type: String },
        shareType: { type: String },
        _targetId: { state: true },
        _role: { state: true },
        _expiresAt: { state: true },
        _saving: { state: true },
    };

    static styles = [
        PlatformModal.styles,
        formStyles,
        buttonStyles,
        css`
            .form-grid {
                display: grid;
                gap: var(--space-4);
            }

            .role-chips {
                display: flex;
                gap: var(--space-2);
            }

            .role-chip {
                flex: 1;
                padding: var(--space-3);
                background: var(--crm-surface-muted);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-lg);
                color: var(--text-secondary);
                font-size: var(--text-sm);
                text-align: center;
                cursor: pointer;
                transition: all var(--duration-fast);
            }

            .role-chip:hover {
                background: var(--crm-surface);
                color: var(--text-primary);
            }

            .role-chip.active {
                background: var(--crm-selected-bg);
                border-color: var(--crm-selected-stroke);
                color: var(--crm-selected-text);
            }

            .role-description {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-top: var(--space-1);
            }

            .footer-actions {
                display: flex;
                gap: var(--space-3);
                justify-content: flex-end;
                width: 100%;
            }

            .role-title {
                display: flex;
                align-items: center;
                justify-content: center;
                gap: var(--space-1);
            }
        `
    ];

    constructor() {
        super();
        this.size = 'md';
        this.entityId = null;
        this.shareType = 'user';
        this._targetId = '';
        this._role = 'viewer';
        this._expiresAt = '';
        this._saving = false;
    }

    renderHeader() {
        return this.shareType === 'user'
            ? this.i18n.t('grants.share_user')
            : this.i18n.t('grants.share_company');
    }

    _onTargetIdInput(e) {
        this._targetId = e.target.value;
    }

    _onRoleSelect(role) {
        this._role = role;
    }

    _onExpiresAtChange(e) {
        this._expiresAt = e.target.value;
    }

    async _onShare() {
        if (!this._targetId.trim()) {
            this.error(this.shareType === 'user'
                ? this.i18n.t('share_modal.err_enter_user_id')
                : this.i18n.t('share_modal.err_enter_company_id')
            );
            return;
        }

        this._saving = true;
        try {
            const crmApi = this.services.get('crmApi');

            if (this.shareType === 'user') {
                await CRMStore.grantToUser(crmApi, this.entityId, this._targetId.trim(), this._role);
                this.success(this.i18n.t('share_modal.success_user'));
            } else {
                await CRMStore.grantToCompany(crmApi, this.entityId, this._targetId.trim(), this._role);
                this.success(this.i18n.t('share_modal.success_company'));
            }

            this.dispatchEvent(new CustomEvent('shared'));
            this.close();
        } catch (error) {
            const message = error instanceof Error
                ? error.message
                : this.i18n.t('share_modal.err_share');
            this.error(message);
            throw error;
        } finally {
            this._saving = false;
        }
    }

    renderBody() {
        const targetLabel = this.shareType === 'user'
            ? this.i18n.t('share_modal.label_user_id')
            : this.i18n.t('share_modal.label_company_id');
        const targetPlaceholder = this.shareType === 'user'
            ? this.i18n.t('share_modal.placeholder_user_id')
            : this.i18n.t('share_modal.placeholder_company_id');

        return html`
            <div class="form-grid">
                <div class="form-group">
                    <label class="form-label">${targetLabel}</label>
                    <input
                        type="text"
                        class="form-input"
                        placeholder="${targetPlaceholder}"
                        .value=${this._targetId}
                        @input=${this._onTargetIdInput}
                    />
                </div>

                <div class="form-group">
                    <label class="form-label">${this.i18n.t('share_modal.label_access_level')}</label>
                    <div class="role-chips">
                        <button
                            type="button"
                            class="role-chip ${this._role === 'viewer' ? 'active' : ''}"
                            @click=${() => this._onRoleSelect('viewer')}
                        >
                            <div class="role-title">
                                <platform-icon name="eye" size="14"></platform-icon>
                                <span>${this.i18n.t('grants.role_viewer')}</span>
                            </div>
                            <div class="role-description">${this.i18n.t('share_modal.role_viewer_desc')}</div>
                        </button>
                        <button
                            type="button"
                            class="role-chip ${this._role === 'editor' ? 'active' : ''}"
                            @click=${() => this._onRoleSelect('editor')}
                        >
                            <div class="role-title">
                                <platform-icon name="edit" size="14"></platform-icon>
                                <span>${this.i18n.t('grants.role_editor')}</span>
                            </div>
                            <div class="role-description">${this.i18n.t('share_modal.role_editor_desc')}</div>
                        </button>
                        <button
                            type="button"
                            class="role-chip ${this._role === 'admin' ? 'active' : ''}"
                            @click=${() => this._onRoleSelect('admin')}
                        >
                            <div class="role-title">
                                <platform-icon name="settings" size="14"></platform-icon>
                                <span>${this.i18n.t('grants.role_admin')}</span>
                            </div>
                            <div class="role-description">${this.i18n.t('share_modal.role_admin_desc')}</div>
                        </button>
                    </div>
                </div>

                <div class="form-group">
                    <label class="form-label">${this.i18n.t('share_modal.label_expires_optional')}</label>
                    <platform-date-picker
                        class="form-input"
                        mode="date"
                        value-format="iso"
                        .value=${this._expiresAt || null}
                        @change=${this._onExpiresAtChange}
                    ></platform-date-picker>
                </div>
            </div>
        `;
    }

    renderSaveHeaderButton() {
        const title = this._saving
            ? this.i18n.t('share_modal.saving')
            : this.i18n.t('share_modal.submit_grant');
        return this._renderHeaderSaveIcon({
            onClick: () => this._onShare(),
            disabled: this._saving || !this._targetId.trim(),
            title,
        });
    }

    renderFooter() {
        return html`
            <div class="footer-actions">
                <button
                    type="button"
                    class="btn btn-secondary"
                    @click=${() => this.close()}
                >
                    ${this.i18n.t('cancel', {}, 'common')}
                </button>
            </div>
        `;
    }
}

customElements.define('share-modal', ShareModal);
