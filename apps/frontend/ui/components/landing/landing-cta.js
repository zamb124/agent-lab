/**
 * Landing CTA - Call to Action с формой заявки
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { I18nNs } from '@platform/services/i18n/i18n.service.js';
import '@platform/lib/components/glass-modal.js';
import '@platform/lib/components/glass-input.js';
import '@platform/lib/components/glass-button.js';

export class LandingCta extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                padding: 120px 20px;
                position: relative;
                overflow: hidden;
            }
            
            .blur-bg-primary {
                position: absolute;
                width: 1000px;
                height: 800px;
                background: rgba(87, 104, 254, 0.6);
                filter: blur(150px);
                border-radius: 50%;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                pointer-events: none;
                z-index: 0;
            }
            
            .blur-bg-white {
                position: absolute;
                width: 1200px;
                height: 400px;
                background: rgba(255, 255, 255, 0.2);
                filter: blur(100px);
                bottom: 0;
                right: -300px;
                pointer-events: none;
                z-index: 0;
            }
            
            .cta-container {
                max-width: 800px;
                margin: 0 auto;
                text-align: center;
                position: relative;
                z-index: 1;
            }
            
            .cta-title {
                font-family: 'Fira Sans Condensed', sans-serif;
                font-size: 40px;
                font-weight: 500;
                line-height: 1.2;
                color: var(--landing-secondary);
                margin: 0 0 32px 0;
            }
            
            .cta-button {
                padding: 20px 48px;
                background: var(--landing-primary);
                color: var(--landing-secondary);
                border: none;
                border-radius: 40px;
                font-family: 'Fira Sans', sans-serif;
                font-weight: 500;
                font-size: 20px;
                cursor: pointer;
                transition: all 0.3s;
                box-shadow: 0 10px 40px rgba(87, 104, 254, 0.4);
            }
            
            .cta-button:hover {
                background: #6877ff;
                transform: translateY(-3px);
                box-shadow: 0 15px 50px rgba(87, 104, 254, 0.5);
            }
            
            .form-grid {
                display: flex;
                flex-direction: column;
                gap: 20px;
                margin-bottom: 24px;
            }
            
            .form-row {
                display: grid;
                grid-template-columns: 1fr;
                gap: 20px;
            }
            
            @media (min-width: 768px) {
                :host {
                    padding: 150px 40px;
                }
                
                .cta-title {
                    font-size: 56px;
                    margin-bottom: 48px;
                }
                
                .cta-button {
                    font-size: 22px;
                    padding: 22px 56px;
                }
                
                .form-row {
                    grid-template-columns: repeat(2, 1fr);
                }
            }
            
            @media (min-width: 1440px) {
                :host {
                    padding: 180px 80px;
                }
                
                .cta-title {
                    font-size: 72px;
                }
                
                .cta-button {
                    font-size: 24px;
                    padding: 24px 64px;
                }
            }
        `
    ];

    static properties = {
        showModal: { type: Boolean },
        formData: { type: Object },
        isSubmitting: { type: Boolean },
    };

    constructor() {
        super();
        this.showModal = false;
        this.isSubmitting = false;
        this.formData = {
            name: '',
            email: '',
            phone: '',
            company: '',
            comment: ''
        };
    }

    connectedCallback() {
        super.connectedCallback();
        this._i18nUnsub = this.i18n.subscribe(() => this.requestUpdate());
    }

    disconnectedCallback() {
        if (this._i18nUnsub) {
            this._i18nUnsub();
            this._i18nUnsub = null;
        }
        super.disconnectedCallback();
    }

    _openModal() {
        this.showModal = true;
    }

    _closeModal() {
        this.showModal = false;
        this._resetForm();
    }

    _resetForm() {
        this.formData = {
            name: '',
            email: '',
            phone: '',
            company: '',
            comment: ''
        };
    }

    _handleInput(field, event) {
        this.formData = {
            ...this.formData,
            [field]: event.target.value
        };
    }

    async _handleSubmit(event) {
        event.preventDefault();

        if (!this.formData.name || !this.formData.email) {
            this.warning(this.i18n.t('cta.toast_required', {}, I18nNs.LANDING));
            return;
        }

        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(this.formData.email)) {
            this.warning(this.i18n.t('cta.toast_email_invalid', {}, I18nNs.LANDING));
            return;
        }

        this.isSubmitting = true;

        try {
            const response = await fetch('/frontend/api/leads', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(this.formData)
            });

            if (response.ok) {
                this.success(this.i18n.t('cta.toast_success', {}, I18nNs.LANDING));
                this._closeModal();
            } else {
                this.error(this.i18n.t('cta.toast_error', {}, I18nNs.LANDING));
            }
        } catch {
            this.error(this.i18n.t('cta.toast_error', {}, I18nNs.LANDING));
        } finally {
            this.isSubmitting = false;
        }
    }

    render() {
        const t = (key) => this.i18n.t(key, {}, I18nNs.LANDING);
        return html`
            <div class="blur-bg-primary"></div>
            <div class="blur-bg-white"></div>
            
            <div class="cta-container">
                <h2 class="cta-title">
                    ${t('cta.title_plain')}
                </h2>
                
                <button class="cta-button" @click=${this._openModal}>
                    ${t('cta.button')}
                </button>
            </div>
            
            ${this.showModal ? html`
                <glass-modal
                    title=${t('cta.modal_title')}
                    @close=${this._closeModal}
                >
                    <form @submit=${this._handleSubmit}>
                        <div class="form-grid">
                            <div class="form-row">
                                <glass-input
                                    type="text"
                                    placeholder=${t('cta.placeholder_name')}
                                    .value=${this.formData.name}
                                    @input=${(e) => this._handleInput('name', e)}
                                    required
                                ></glass-input>
                                
                                <glass-input
                                    type="email"
                                    placeholder=${t('cta.placeholder_email')}
                                    .value=${this.formData.email}
                                    @input=${(e) => this._handleInput('email', e)}
                                    required
                                ></glass-input>
                            </div>
                            
                            <div class="form-row">
                                <glass-input
                                    type="tel"
                                    placeholder=${t('cta.placeholder_phone')}
                                    .value=${this.formData.phone}
                                    @input=${(e) => this._handleInput('phone', e)}
                                ></glass-input>
                                
                                <glass-input
                                    type="text"
                                    placeholder=${t('cta.placeholder_company')}
                                    .value=${this.formData.company}
                                    @input=${(e) => this._handleInput('company', e)}
                                ></glass-input>
                            </div>
                            
                            <glass-input
                                type="text"
                                placeholder=${t('cta.placeholder_comment')}
                                .value=${this.formData.comment}
                                @input=${(e) => this._handleInput('comment', e)}
                            ></glass-input>
                        </div>
                        
                        <glass-button
                            type="submit"
                            variant="primary"
                            ?loading=${this.isSubmitting}
                            ?disabled=${this.isSubmitting}
                        >
                            ${this.isSubmitting ? t('cta.submit_sending') : t('cta.submit_idle')}
                        </glass-button>
                    </form>
                </glass-modal>
            ` : ''}
        `;
    }
}

customElements.define('landing-cta', LandingCta);

