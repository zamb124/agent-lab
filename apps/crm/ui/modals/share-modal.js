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

            .btn {
                padding: var(--space-2) var(--space-4);
                border-radius: var(--radius-lg);
                font-size: var(--text-sm);
                font-weight: 500;
                cursor: pointer;
                transition: all var(--duration-fast);
            }

            .btn-secondary {
                background: var(--crm-button-secondary-bg);
                border: 1px solid var(--crm-button-secondary-bg);
                color: var(--crm-button-secondary-text);
            }

            .btn-secondary:hover {
                background: var(--crm-button-secondary-hover);
                border-color: var(--crm-button-secondary-hover);
                color: var(--crm-button-secondary-text);
            }

            .btn-primary {
                background: var(--crm-button-primary-bg);
                border: 1px solid var(--crm-button-primary-bg);
                color: var(--crm-button-primary-text);
            }

            .role-title {
                display: flex;
                align-items: center;
                justify-content: center;
                gap: var(--space-1);
            }

            .btn-primary:hover:not(:disabled) {
                background: var(--crm-button-primary-hover);
                border-color: var(--crm-button-primary-hover);
            }

            .btn-primary:disabled {
                opacity: 0.5;
                cursor: not-allowed;
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
            ? 'Поделиться с пользователем'
            : 'Поделиться с компанией';
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
                ? 'Введите ID пользователя'
                : 'Введите ID компании'
            );
            return;
        }

        this._saving = true;

        const crmApi = this.services.get('crmApi');

        if (this.shareType === 'user') {
            await CRMStore.grantToUser(crmApi, this.entityId, this._targetId.trim(), this._role);
            this.success('Доступ предоставлен пользователю');
        } else {
            await CRMStore.grantToCompany(crmApi, this.entityId, this._targetId.trim(), this._role);
            this.success('Доступ предоставлен компании');
        }

        this._saving = false;
        this.dispatchEvent(new CustomEvent('shared'));
        this.close();
    }

    renderBody() {
        const targetLabel = this.shareType === 'user' ? 'ID пользователя' : 'ID компании';
        const targetPlaceholder = this.shareType === 'user'
            ? 'Введите user_id'
            : 'Введите company_id';

        return html`
            <div class="form-grid">
                <div class="form-group">
                    <label class="form-label">${targetLabel} *</label>
                    <input
                        type="text"
                        class="form-input"
                        placeholder="${targetPlaceholder}"
                        .value=${this._targetId}
                        @input=${this._onTargetIdInput}
                    />
                </div>

                <div class="form-group">
                    <label class="form-label">Уровень доступа</label>
                    <div class="role-chips">
                        <button
                            type="button"
                            class="role-chip ${this._role === 'viewer' ? 'active' : ''}"
                            @click=${() => this._onRoleSelect('viewer')}
                        >
                            <div class="role-title">
                                <platform-icon name="eye" size="14"></platform-icon>
                                <span>Просмотр</span>
                            </div>
                            <div class="role-description">Только чтение</div>
                        </button>
                        <button
                            type="button"
                            class="role-chip ${this._role === 'editor' ? 'active' : ''}"
                            @click=${() => this._onRoleSelect('editor')}
                        >
                            <div class="role-title">
                                <platform-icon name="edit" size="14"></platform-icon>
                                <span>Редактор</span>
                            </div>
                            <div class="role-description">Чтение и запись</div>
                        </button>
                        <button
                            type="button"
                            class="role-chip ${this._role === 'admin' ? 'active' : ''}"
                            @click=${() => this._onRoleSelect('admin')}
                        >
                            <div class="role-title">
                                <platform-icon name="settings" size="14"></platform-icon>
                                <span>Админ</span>
                            </div>
                            <div class="role-description">Полный доступ</div>
                        </button>
                    </div>
                </div>

                <div class="form-group">
                    <label class="form-label">Срок действия (опционально)</label>
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

    renderFooter() {
        return html`
            <div class="footer-actions">
                <button
                    type="button"
                    class="btn btn-secondary"
                    @click=${() => this.close()}
                >
                    Отмена
                </button>
                <button
                    type="button"
                    class="btn btn-primary"
                    ?disabled=${this._saving || !this._targetId.trim()}
                    @click=${this._onShare}
                >
                    ${this._saving ? 'Сохранение...' : 'Предоставить доступ'}
                </button>
            </div>
        `;
    }
}

customElements.define('share-modal', ShareModal);
