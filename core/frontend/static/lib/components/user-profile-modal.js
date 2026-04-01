/**
 * Модальное окно для редактирования профиля пользователя
 */
import { html, css } from 'lit';
import { PlatformFormModal } from './glass-form-modal.js';

export class UserProfileModal extends PlatformFormModal {
    static get properties() {
        return {
            user: { type: Object },
            activeCompanyName: { type: String }
        };
    }

    constructor() {
        super();
        this.user = null;
        this.activeCompanyName = '';
        this.title = '';
        this.maxWidth = '600px';
    }

    willUpdate(changedProperties) {
        super.willUpdate(changedProperties);
        this.title = this.i18n.t('profile.title', {}, 'shell');
    }

    validateForm() {
        const errors = {};
        const data = this.getFormData();
        const tp = (key) => this.i18n.t(key, {}, 'shell');

        if (!data.name || data.name.trim().length === 0) {
            errors.name = tp('profile.error_name_required');
        }

        if (data.name && data.name.length > 100) {
            errors.name = tp('profile.error_name_length');
        }

        if (data.bio && data.bio.length > 4000) {
            errors.bio = tp('profile.error_bio_length');
        }

        return errors;
    }

    async handleSubmit(data) {
        try {
            await this.auth.updateProfile({
                name: data.name.trim(),
                first_name: data.first_name?.trim() || null,
                last_name: data.last_name?.trim() || null,
                bio: data.bio?.trim() || null,
                ui_preferences: {
                    ...this.user?.ui_preferences,
                    language: data.language
                }
            });
            
            this.success(this.i18n.t('profile.success_updated', {}, 'shell'));
            this.emit('updated');
            this.close();
        } catch (error) {
            console.error('[UserProfileModal] Failed to update profile:', error);
            this.error(`${this.i18n.t('profile.error_update_prefix', {}, 'shell')} ${error.message}`);
            throw error;
        }
    }

    _onInput() {
        this.isDirty = true;
    }

    renderBody() {
        const t = (key) => this.i18n.t(key, {}, 'shell');
        if (!this.user) {
            return html`
                <div class="loading-state">
                    <p>${t('profile.loading')}</p>
                </div>
            `;
        }

        return html`
            <form @submit=${this._onSubmit} @input=${this._onInput}>
                <div class="form-group">
                    <label for="first_name" class="form-label">${t('profile.first_name_label')}</label>
                    <input
                        type="text"
                        id="first_name"
                        name="first_name"
                        class="form-input"
                        .value=${this.user.first_name || ''}
                        placeholder=${t('profile.first_name_placeholder')}
                        maxlength="100"
                    />
                    ${this.renderFieldError('first_name')}
                </div>
                <div class="form-group">
                    <label for="last_name" class="form-label">${t('profile.last_name_label')}</label>
                    <input
                        type="text"
                        id="last_name"
                        name="last_name"
                        class="form-input"
                        .value=${this.user.last_name || ''}
                        placeholder=${t('profile.last_name_placeholder')}
                        maxlength="100"
                    />
                    ${this.renderFieldError('last_name')}
                </div>
                <div class="form-group">
                    <label for="name" class="form-label">${t('profile.display_name_label')}</label>
                    <input
                        type="text"
                        id="name"
                        name="name"
                        class="form-input"
                        .value=${this.user.name || ''}
                        placeholder=${t('profile.display_name_placeholder')}
                        required
                    />
                    ${this.renderFieldError('name')}
                </div>

                <div class="form-group">
                    <label for="email" class="form-label">${t('profile.email_label')}</label>
                    <input
                        type="email"
                        id="email"
                        class="form-input"
                        .value=${this.user.emails?.[0] || ''}
                        disabled
                    />
                    <small class="form-help">${t('profile.email_locked')}</small>
                </div>

                <div class="form-group">
                    <label for="bio" class="form-label">${t('profile.bio_label')}</label>
                    <textarea
                        id="bio"
                        name="bio"
                        class="form-textarea"
                        rows="4"
                        placeholder=${t('profile.bio_placeholder')}
                        .value=${this.user.bio || ''}
                    ></textarea>
                    ${this.renderFieldError('bio')}
                    <small class="form-help">${t('profile.bio_max_hint')}</small>
                </div>

                <div class="form-group">
                    <label for="language" class="form-label">${t('profile.language_label')}</label>
                    <select
                        id="language"
                        name="language"
                        class="form-select"
                    >
                        <option value="ru" ?selected=${this.user.ui_preferences?.language === 'ru'}>
                            ${t('profile.lang_ru')}
                        </option>
                        <option value="en" ?selected=${this.user.ui_preferences?.language === 'en'}>
                            ${t('profile.lang_en')}
                        </option>
                    </select>
                </div>

                <div class="info-section">
                    <div class="info-item">
                        <span class="info-label">${t('profile.company_label')}</span>
                        <span class="info-value">${this.activeCompanyName || t('profile.company_empty')}</span>
                    </div>
                    ${this.user.roles && this.user.roles.length > 0 ? html`
                        <div class="info-item">
                            <span class="info-label">${t('profile.roles_label')}</span>
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

