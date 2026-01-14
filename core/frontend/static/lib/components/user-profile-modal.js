/**
 * Модальное окно для редактирования профиля пользователя
 */
import { html, css } from 'lit';
import { PlatformFormModal } from './glass-form-modal.js';

export class UserProfileModal extends PlatformFormModal {
    static get properties() {
        return {
            user: { type: Object }
        };
    }

    constructor() {
        super();
        this.user = null;
        this.title = 'Редактирование профиля';
        this.maxWidth = '600px';
    }

    validateForm() {
        const errors = {};
        const data = this.getFormData();

        if (!data.name || data.name.trim().length === 0) {
            errors.name = 'Имя обязательно';
        }

        if (data.name && data.name.length > 100) {
            errors.name = 'Имя не должно превышать 100 символов';
        }

        if (data.bio && data.bio.length > 500) {
            errors.bio = 'Описание не должно превышать 500 символов';
        }

        return errors;
    }

    async handleSubmit(data) {
        try {
            await this.auth.updateProfile({
                name: data.name.trim(),
                bio: data.bio?.trim() || null,
                ui_preferences: {
                    ...this.user?.ui_preferences,
                    language: data.language
                }
            });
            
            this.success('Профиль обновлен');
            this.emit('updated');
            this.close();
        } catch (error) {
            console.error('[UserProfileModal] Failed to update profile:', error);
            this.error(`Ошибка обновления: ${error.message}`);
            throw error;
        }
    }

    _onInput() {
        this.isDirty = true;
    }

    renderBody() {
        if (!this.user) {
            return html`
                <div class="loading-state">
                    <p>Загрузка данных пользователя...</p>
                </div>
            `;
        }

        return html`
            <form @submit=${this._onSubmit} @input=${this._onInput}>
                <div class="form-group">
                    <label for="name" class="form-label">Имя</label>
                    <input
                        type="text"
                        id="name"
                        name="name"
                        class="form-input"
                        .value=${this.user.name || ''}
                        placeholder="Введите ваше имя"
                        required
                    />
                    ${this.renderFieldError('name')}
                </div>

                <div class="form-group">
                    <label for="email" class="form-label">Email</label>
                    <input
                        type="email"
                        id="email"
                        class="form-input"
                        .value=${this.user.emails?.[0] || ''}
                        disabled
                    />
                    <small class="form-help">Email нельзя изменить</small>
                </div>

                <div class="form-group">
                    <label for="bio" class="form-label">О себе</label>
                    <textarea
                        id="bio"
                        name="bio"
                        class="form-textarea"
                        rows="4"
                        placeholder="Расскажите о себе"
                        .value=${this.user.bio || ''}
                    ></textarea>
                    ${this.renderFieldError('bio')}
                    <small class="form-help">Максимум 500 символов</small>
                </div>

                <div class="form-group">
                    <label for="language" class="form-label">Язык интерфейса</label>
                    <select
                        id="language"
                        name="language"
                        class="form-select"
                    >
                        <option value="ru" ?selected=${this.user.ui_preferences?.language === 'ru'}>
                            Русский
                        </option>
                        <option value="en" ?selected=${this.user.ui_preferences?.language === 'en'}>
                            English
                        </option>
                    </select>
                </div>

                <div class="info-section">
                    <div class="info-item">
                        <span class="info-label">Компания:</span>
                        <span class="info-value">${this.user.company_id || 'Не указана'}</span>
                    </div>
                    ${this.user.roles && this.user.roles.length > 0 ? html`
                        <div class="info-item">
                            <span class="info-label">Роли:</span>
                            <span class="info-value">${this.user.roles.join(', ')}</span>
                        </div>
                    ` : ''}
                </div>
            </form>
        `;
    }

    static styles = [
        PlatformFormModal.styles,
        css`
            .loading-state {
                padding: var(--space-8);
                text-align: center;
                color: var(--text-secondary);
            }

            .form-help {
                display: block;
                margin-top: var(--space-1);
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }

            .info-section {
                margin-top: var(--space-6);
                padding: var(--space-4);
                background: var(--glass-solid-subtle);
                border-radius: var(--radius-lg);
                border: 1px solid var(--glass-border-subtle);
            }

            .info-item {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: var(--space-2) 0;
            }

            .info-item:not(:last-child) {
                border-bottom: 1px solid var(--glass-border-subtle);
            }

            .info-label {
                font-size: var(--text-sm);
                color: var(--text-secondary);
                font-weight: var(--font-medium);
            }

            .info-value {
                font-size: var(--text-sm);
                color: var(--text-primary);
            }
        `
    ];
}

console.log('[UserProfileModal] Registering component...');
console.log('[UserProfileModal] Class:', UserProfileModal);
console.log('[UserProfileModal] Class prototype:', UserProfileModal.prototype);
console.log('[UserProfileModal] Class extends:', Object.getPrototypeOf(UserProfileModal));

try {
    customElements.define('user-profile-modal', UserProfileModal);
    console.log('[UserProfileModal] Successfully registered!');
} catch (error) {
    console.error('[UserProfileModal] Registration failed:', error);
    throw error;
}

