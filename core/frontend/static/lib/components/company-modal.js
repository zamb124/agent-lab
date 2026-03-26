import { html, css } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import { Services } from '@platform/services/index.js';
import { nextModalLayerZIndex } from '../utils/modal-z-stack.js';
import { formatCompanySubdomainLabel } from '../utils/tenant-url.js';

export class CompanyModal extends PlatformElement {
    static properties = {
        open: { type: Boolean },
        loading: { type: Boolean },
        error: { type: String },
        companyName: { type: String },
        companySlug: { type: String },
        slugAvailable: { type: Boolean },
        slugChecking: { type: Boolean },
        slugError: { type: String },
        slugTouched: { type: Boolean }
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: none;
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                z-index: var(--platform-modal-layer-z, var(--z-modal, 1000));
            }

            :host([open]) {
                display: flex;
                align-items: center;
                justify-content: center;
            }

            .modal-overlay {
                position: absolute;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(0, 0, 0, 0.7);
                backdrop-filter: blur(10px);
                display: flex;
                align-items: center;
                justify-content: center;
            }

            .modal-content {
                background: var(--glass-bg);
                border: 1px solid var(--glass-border);
                border-radius: 24px;
                padding: 40px;
                max-width: 500px;
                width: 90%;
                backdrop-filter: blur(20px);
                box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
            }

            .modal-header {
                text-align: center;
                margin-bottom: 32px;
            }

            .modal-title {
                font-family: 'Fira Sans Condensed', sans-serif;
                font-size: 28px;
                font-weight: 600;
                color: var(--landing-secondary);
                margin: 0 0 8px 0;
            }

            .modal-subtitle {
                font-family: 'Fira Sans', sans-serif;
                font-size: 16px;
                color: var(--landing-secondary);
                opacity: 0.7;
            }

            .form-group {
                margin-bottom: 24px;
            }

            .form-label {
                display: block;
                font-family: 'Fira Sans', sans-serif;
                font-size: 14px;
                color: var(--landing-secondary);
                margin-bottom: 8px;
            }

            .form-input {
                width: 100%;
                padding: 12px 16px;
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 12px;
                font-family: 'Fira Sans', sans-serif;
                font-size: 16px;
                color: var(--landing-secondary);
                transition: all 0.3s ease;
            }

            .form-input:focus {
                outline: none;
                border-color: var(--landing-primary);
                background: rgba(255, 255, 255, 0.08);
            }

            .button-group {
                display: flex;
                gap: 12px;
            }

            .button {
                flex: 1;
                padding: 14px 20px;
                border-radius: 12px;
                font-family: 'Fira Sans', sans-serif;
                font-size: 16px;
                font-weight: 500;
                cursor: pointer;
                transition: all 0.3s ease;
                border: none;
            }

            .button-primary {
                background: var(--landing-primary);
                color: var(--landing-secondary);
            }

            .button-primary:hover:not(:disabled) {
                background: #6877ff;
            }

            .button-secondary {
                background: rgba(255, 255, 255, 0.05);
                color: var(--landing-secondary);
                border: 1px solid rgba(255, 255, 255, 0.1);
            }

            .button-secondary:hover:not(:disabled) {
                background: rgba(255, 255, 255, 0.1);
            }

            .button:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }

            .error {
                margin-top: 16px;
                padding: 12px;
                background: rgba(255, 59, 48, 0.1);
                border: 1px solid rgba(255, 59, 48, 0.3);
                border-radius: 8px;
                color: #FF3B30;
                font-size: 14px;
                text-align: center;
            }

            .input-wrapper {
                position: relative;
            }

            .slug-status {
                position: absolute;
                right: 16px;
                top: 50%;
                transform: translateY(-50%);
                font-size: 14px;
            }

            .slug-status.checking {
                color: var(--landing-secondary);
                opacity: 0.5;
            }

            .slug-status.available {
                color: #34C759;
            }

            .slug-status.unavailable {
                color: #FF3B30;
            }

            .slug-hint {
                font-size: 12px;
                color: var(--landing-secondary);
                opacity: 0.6;
                margin-top: 4px;
            }

            .slug-preview {
                font-size: 12px;
                color: var(--landing-primary);
                margin-top: 4px;
            }

            .slug-error {
                font-size: 12px;
                color: #FF3B30;
                margin-top: 4px;
            }
        `
    ];

    constructor() {
        super();
        this.open = false;
        this.loading = false;
        this.error = '';
        this.companyName = '';
        this.companySlug = '';
        this.slugAvailable = null;
        this.slugChecking = false;
        this.slugError = '';
        this.slugTouched = false;
        this._debounceTimer = null;
    }

    willUpdate(changedProperties) {
        super.willUpdate(changedProperties);
        if (changedProperties.has('open') && this.open) {
            this.style.setProperty(
                '--platform-modal-layer-z',
                String(nextModalLayerZIndex()),
            );
        }
    }

    _slugify(text) {
        if (!text) return '';
        
        const translitMap = {
            'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo', 'ж': 'zh', 
            'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o', 
            'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'h', 'ц': 'ts', 
            'ч': 'ch', 'ш': 'sh', 'щ': 'sch', 'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya'
        };
        
        let slug = text.toLowerCase();
        for (const [cyr, lat] of Object.entries(translitMap)) {
            slug = slug.replace(new RegExp(cyr, 'g'), lat);
        }
        
        slug = slug.replace(/[^a-z0-9-]/g, '-');
        slug = slug.replace(/-+/g, '-');
        slug = slug.replace(/^-+|-+$/g, '');
        
        return slug;
    }

    _handleNameInput(e) {
        this.companyName = e.target.value;
        
        if (!this.slugTouched) {
            this.companySlug = this._slugify(this.companyName);
            this._debouncedCheckSlug();
        }
    }

    _handleSlugInput(e) {
        this.companySlug = e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '');
        this.slugTouched = true;
        this._debouncedCheckSlug();
    }

    _debouncedCheckSlug() {
        clearTimeout(this._debounceTimer);
        this._debounceTimer = setTimeout(() => this._checkSlugAvailability(), 500);
    }

    async _checkSlugAvailability() {
        if (!this.companySlug || this.companySlug.length < 3) {
            this.slugAvailable = null;
            this.slugError = this.companySlug ? 'Минимум 3 символа' : '';
            return;
        }

        this.slugChecking = true;
        this.slugError = '';

        try {
            const data = await Services.companies.checkSlugAvailability(this.companySlug);
            this.slugAvailable = data.available;
            
            if (!data.available) {
                this.slugError = 'Этот адрес уже занят';
            }
        } catch (error) {
            console.error('Error checking slug:', error);
            this.slugError = 'Ошибка проверки доступности';
        } finally {
            this.slugChecking = false;
        }
    }

    async handleSubmit(e) {
        e.preventDefault();
        
        if (!this.companyName.trim()) {
            this.error = 'Введите название компании';
            return;
        }

        if (!this.companySlug || this.companySlug.length < 3) {
            this.error = 'Введите корректный адрес компании';
            return;
        }

        if (this.slugAvailable === false) {
            this.error = 'Адрес компании уже занят';
            return;
        }

        this.loading = true;
        this.error = '';

        try {
            const data = await Services.companies.createCompany(this.companyName, this.companySlug);

            this.open = false;
            this.dispatchEvent(new CustomEvent('company-created', { detail: data }));
            
            if (data.redirect_url) {
                window.location.href = data.redirect_url;
            } else {
                window.location.reload();
            }
        } catch (error) {
            this.error = error.message;
        } finally {
            this.loading = false;
        }
    }

    _handleContentClick(e) {
        // Предотвращаем закрытие модалки при клике на содержимое
        e.stopPropagation();
    }

    _handleOverlayClick(e) {
        // Закрываем модалку только при клике на overlay (фон), но не на содержимое
        if (e.target === e.currentTarget) {
            this.open = false;
            this.dispatchEvent(new CustomEvent('close', { bubbles: true, composed: true }));
        }
    }

    render() {
        return html`
            <div class="modal-overlay" @click=${this._handleOverlayClick}>
                <div class="modal-content" @click=${this._handleContentClick}>
                <div class="modal-header">
                    <h2 class="modal-title">Создание компании</h2>
                    <p class="modal-subtitle">Для начала работы создайте компанию</p>
                </div>

                <form @submit=${this.handleSubmit}>
                    <div class="form-group">
                        <label class="form-label">Название компании</label>
                        <input
                            type="text"
                            class="form-input"
                            .value=${this.companyName}
                            @input=${this._handleNameInput}
                            placeholder="Моя компания"
                            ?disabled=${this.loading}
                            required
                        />
                    </div>

                    <div class="form-group">
                        <label class="form-label">Адрес компании</label>
                        <div class="input-wrapper">
                            <input
                                type="text"
                                class="form-input"
                                .value=${this.companySlug}
                                @input=${this._handleSlugInput}
                                placeholder="moya-kompaniya"
                                pattern="[a-z0-9-]+"
                                minlength="3"
                                maxlength="63"
                                ?disabled=${this.loading}
                                required
                            />
                            ${this.slugChecking ? html`
                                <span class="slug-status checking">⏳</span>
                            ` : this.slugAvailable === true ? html`
                                <span class="slug-status available">✓</span>
                            ` : this.slugAvailable === false ? html`
                                <span class="slug-status unavailable">✗</span>
                            ` : ''}
                        </div>
                        ${this.companySlug && !this.slugError ? html`
                            <div class="slug-preview">
                                ${formatCompanySubdomainLabel(this.companySlug)}
                            </div>
                        ` : ''}
                        ${this.slugError ? html`
                            <div class="slug-error">${this.slugError}</div>
                        ` : html`
                            <div class="slug-hint">Только латинские буквы, цифры и дефис</div>
                        `}
                    </div>

                    <div class="button-group">
                        <button
                            type="submit"
                            class="button button-primary"
                            ?disabled=${this.loading || this.slugChecking || this.slugAvailable === false}
                        >
                            ${this.loading ? 'Создание...' : 'Создать'}
                        </button>
                    </div>

                    ${this.error ? html`<div class="error">${this.error}</div>` : ''}
                </form>
                </div>
            </div>
        `;
    }
}

customElements.define('company-modal', CompanyModal);

