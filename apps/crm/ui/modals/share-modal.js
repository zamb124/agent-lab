/**
 * Share Modal - Модальное окно для шаринга сущности
 * Использует PlatformModal с fullscreen и drag поддержкой
 */
import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { formStyles } from '@platform/lib/styles/shared/form.styles.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { CRMStore } from '../store/crm.store.js';

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
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                color: var(--text-secondary);
                font-size: var(--text-sm);
                text-align: center;
                cursor: pointer;
                transition: all 0.2s;
            }

            .role-chip:hover {
                background: var(--glass-solid-medium);
                color: var(--text-primary);
            }

            .role-chip.active {
                background: var(--accent-subtle);
                border-color: var(--accent);
                color: var(--accent);
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
                transition: all 0.2s;
            }

            .btn-secondary {
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                color: var(--text-secondary);
            }

            .btn-secondary:hover {
                background: var(--glass-solid-medium);
                color: var(--text-primary);
            }

            .btn-primary {
                background: var(--accent);
                border: 1px solid var(--accent);
                color: white;
            }

            .btn-primary:hover:not(:disabled) {
                background: var(--accent-hover);
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
                            <div>👁️ Просмотр</div>
                            <div class="role-description">Только чтение</div>
                        </button>
                        <button
                            type="button"
                            class="role-chip ${this._role === 'editor' ? 'active' : ''}"
                            @click=${() => this._onRoleSelect('editor')}
                        >
                            <div>✏️ Редактор</div>
                            <div class="role-description">Чтение и запись</div>
                        </button>
                        <button
                            type="button"
                            class="role-chip ${this._role === 'admin' ? 'active' : ''}"
                            @click=${() => this._onRoleSelect('admin')}
                        >
                            <div>👑 Админ</div>
                            <div class="role-description">Полный доступ</div>
                        </button>
                    </div>
                </div>

                <div class="form-group">
                    <label class="form-label">Срок действия (опционально)</label>
                    <input
                        type="date"
                        class="form-input"
                        .value=${this._expiresAt}
                        @change=${this._onExpiresAtChange}
                    />
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
