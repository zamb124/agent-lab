/**
 * Landing CTA - Call to Action с формой заявки
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { I18nNs } from '@platform/services/i18n/i18n.service.js';
import '@platform/lib/components/platform-icon.js';

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
                display: inline-flex;
                align-items: center;
                justify-content: center;
                gap: 12px;
                padding: 20px 48px;
                background: var(--landing-primary);
                color: var(--landing-secondary);
                border: none;
                border-radius: 40px;
                font-family: 'Fira Sans', sans-serif;
                font-weight: 500;
                font-size: 20px;
                cursor: pointer;
                transition:
                    transform 0.25s ease,
                    box-shadow 0.25s ease,
                    background 0.25s ease;
                box-shadow:
                    0 10px 40px rgba(87, 104, 254, 0.45),
                    0 0 0 1px rgba(255, 255, 255, 0.12) inset;
            }

            .cta-button:hover {
                background: #6877ff;
                transform: translateY(-3px);
                box-shadow:
                    0 16px 48px rgba(87, 104, 254, 0.55),
                    0 0 0 1px rgba(255, 255, 255, 0.18) inset;
            }

            .cta-button platform-icon {
                flex-shrink: 0;
                color: inherit;
            }

            .lead-modal-root {
                position: fixed;
                inset: 0;
                z-index: 1200;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: max(16px, var(--platform-safe-top)) max(16px, var(--platform-safe-right))
                    max(16px, var(--platform-safe-bottom)) max(16px, var(--platform-safe-left));
                box-sizing: border-box;
            }

            .lead-modal-backdrop {
                position: absolute;
                inset: 0;
                background: rgba(6, 8, 14, 0.78);
                backdrop-filter: blur(18px) saturate(140%);
                -webkit-backdrop-filter: blur(18px) saturate(140%);
                animation: leadModalBackdropIn 0.28s ease forwards;
            }

            .lead-modal-dialog {
                position: relative;
                z-index: 1;
                width: min(520px, 100%);
                max-height: min(90dvh, 880px);
                display: flex;
                flex-direction: column;
                border-radius: 24px;
                overflow: hidden;
                background: linear-gradient(
                    165deg,
                    rgba(42, 44, 64, 0.97) 0%,
                    rgba(20, 22, 34, 0.99) 48%,
                    rgba(16, 18, 28, 1) 100%
                );
                border: 1px solid rgba(255, 255, 255, 0.12);
                box-shadow:
                    0 28px 90px rgba(0, 0, 0, 0.65),
                    0 0 0 1px rgba(87, 104, 254, 0.18),
                    inset 0 1px 0 rgba(255, 255, 255, 0.08);
                animation: leadModalPanelIn 0.38s cubic-bezier(0.22, 1, 0.36, 1) forwards;
            }

            .lead-modal-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 16px;
                padding: 22px 22px 16px 26px;
                flex-shrink: 0;
                border-bottom: 1px solid rgba(255, 255, 255, 0.08);
            }

            .lead-modal-title {
                margin: 0;
                font-family: 'Fira Sans Condensed', sans-serif;
                font-size: clamp(1.35rem, 4vw, 1.6rem);
                font-weight: 600;
                color: var(--landing-secondary, #e8e8e8);
                letter-spacing: -0.02em;
                line-height: 1.2;
            }

            .lead-modal-close {
                flex-shrink: 0;
                width: 44px;
                height: 44px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: 50%;
                border: 1px solid rgba(255, 255, 255, 0.14);
                background: rgba(255, 255, 255, 0.06);
                color: rgba(255, 255, 255, 0.88);
                cursor: pointer;
                transition:
                    background 0.2s ease,
                    color 0.2s ease,
                    border-color 0.2s ease,
                    transform 0.2s ease;
            }

            .lead-modal-close:hover {
                background: rgba(255, 255, 255, 0.12);
                color: #ffffff;
                border-color: rgba(255, 255, 255, 0.22);
                transform: scale(1.05);
            }

            .lead-modal-body {
                padding: 20px 26px 26px;
                overflow-y: auto;
                -webkit-overflow-scrolling: touch;
            }

            .form-grid {
                display: flex;
                flex-direction: column;
                gap: 16px;
                margin-bottom: 22px;
            }

            .form-row {
                display: grid;
                grid-template-columns: 1fr;
                gap: 16px;
            }

            .field {
                display: flex;
                flex-direction: column;
                gap: 0;
            }

            .field-input {
                width: 100%;
                box-sizing: border-box;
                padding: 14px 16px;
                border-radius: 14px;
                border: 1px solid rgba(255, 255, 255, 0.12);
                background: rgba(255, 255, 255, 0.06);
                color: #f4f4f8;
                font-family: 'Fira Sans', sans-serif;
                font-size: 16px;
                line-height: 1.35;
                outline: none;
                transition:
                    border-color 0.2s ease,
                    box-shadow 0.2s ease,
                    background 0.2s ease;
            }

            .field-input::placeholder {
                color: rgba(255, 255, 255, 0.42);
            }

            .field-input:hover {
                border-color: rgba(255, 255, 255, 0.18);
                background: rgba(255, 255, 255, 0.08);
            }

            .field-input:focus {
                border-color: var(--landing-primary, #5768fe);
                box-shadow: 0 0 0 3px rgba(87, 104, 254, 0.28);
                background: rgba(255, 255, 255, 0.08);
            }

            .lead-modal-submit {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                gap: 10px;
                min-height: 52px;
                padding: 0 32px;
                border: none;
                border-radius: 999px;
                background: var(--landing-primary);
                color: var(--landing-secondary);
                font-family: 'Fira Sans', sans-serif;
                font-weight: 600;
                font-size: 17px;
                cursor: pointer;
                transition:
                    transform 0.22s ease,
                    box-shadow 0.22s ease,
                    filter 0.22s ease,
                    opacity 0.22s ease;
                box-shadow:
                    0 12px 40px rgba(87, 104, 254, 0.42),
                    0 0 0 1px rgba(255, 255, 255, 0.14) inset;
            }

            .lead-modal-submit platform-icon {
                flex-shrink: 0;
                color: inherit;
            }

            .lead-modal-submit:hover:not(:disabled) {
                transform: translateY(-2px);
                filter: brightness(1.06);
                box-shadow:
                    0 16px 48px rgba(87, 104, 254, 0.5),
                    0 0 0 1px rgba(255, 255, 255, 0.2) inset;
            }

            .lead-modal-submit:disabled {
                opacity: 0.65;
                cursor: not-allowed;
                transform: none;
            }

            .submit-spinner {
                width: 20px;
                height: 20px;
                border: 2px solid rgba(255, 255, 255, 0.25);
                border-top-color: var(--landing-secondary);
                border-radius: 50%;
                animation: leadModalSpin 0.7s linear infinite;
            }

            @keyframes leadModalBackdropIn {
                from {
                    opacity: 0;
                }
                to {
                    opacity: 1;
                }
            }

            @keyframes leadModalPanelIn {
                from {
                    opacity: 0;
                    transform: translateY(16px) scale(0.97);
                }
                to {
                    opacity: 1;
                    transform: translateY(0) scale(1);
                }
            }

            @keyframes leadModalSpin {
                to {
                    transform: rotate(360deg);
                }
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

            @media (prefers-reduced-motion: reduce) {
                .lead-modal-backdrop,
                .lead-modal-dialog {
                    animation: none;
                }

                .submit-spinner {
                    animation: none;
                    border-color: rgba(255, 255, 255, 0.4);
                }

                .cta-button:hover,
                .lead-modal-submit:hover:not(:disabled) {
                    transform: none;
                }
            }
        `,
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
            comment: '',
        };
        this._onDocumentKeydown = this._onDocumentKeydown.bind(this);
    }

    connectedCallback() {
        super.connectedCallback();
        this._i18nUnsub = this.i18n.subscribe(() => this.requestUpdate());
        document.addEventListener('keydown', this._onDocumentKeydown);
    }

    disconnectedCallback() {
        document.removeEventListener('keydown', this._onDocumentKeydown);
        document.body.style.overflow = '';
        if (this._i18nUnsub) {
            this._i18nUnsub();
            this._i18nUnsub = null;
        }
        super.disconnectedCallback();
    }

    updated(changed) {
        super.updated(changed);
        if (changed.has('showModal')) {
            document.body.style.overflow = this.showModal ? 'hidden' : '';
            if (this.showModal) {
                requestAnimationFrame(() => {
                    const first = this.shadowRoot?.querySelector('.field-input');
                    if (first instanceof HTMLElement) {
                        first.focus();
                    }
                });
            }
        }
    }

    _onDocumentKeydown(e) {
        if (e.key === 'Escape' && this.showModal) {
            this._closeModal();
        }
    }

    _openModal() {
        this.showModal = true;
    }

    openRequestModal() {
        this._openModal();
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
            comment: '',
        };
    }

    _handleInput(field, event) {
        const target = event.target;
        if (!(target instanceof HTMLInputElement)) {
            return;
        }
        this.formData = {
            ...this.formData,
            [field]: target.value,
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
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(this.formData),
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
                <h2 class="cta-title">${t('cta.title_plain')}</h2>

                <button type="button" class="cta-button" @click=${this._openModal}>
                    <platform-icon name="send" size="22"></platform-icon>
                    <span>${t('cta.button')}</span>
                </button>
            </div>

            ${this.showModal
                ? html`
                      <div class="lead-modal-root">
                          <div class="lead-modal-backdrop" @click=${this._closeModal}></div>
                          <div
                              class="lead-modal-dialog"
                              role="dialog"
                              aria-modal="true"
                              aria-labelledby="lead-modal-title"
                              @click=${(e) => e.stopPropagation()}
                          >
                              <div class="lead-modal-header">
                                  <h2 id="lead-modal-title" class="lead-modal-title">${t('cta.modal_title')}</h2>
                                  <button
                                      type="button"
                                      class="lead-modal-close"
                                      aria-label=${t('cta.modal_close_aria')}
                                      @click=${this._closeModal}
                                  >
                                      <platform-icon name="close" size="22"></platform-icon>
                                  </button>
                              </div>
                              <div class="lead-modal-body">
                                  <form @submit=${this._handleSubmit}>
                                      <div class="form-grid">
                                          <div class="form-row">
                                              <label class="field">
                                                  <input
                                                      class="field-input"
                                                      type="text"
                                                      autocomplete="name"
                                                      placeholder=${t('cta.placeholder_name')}
                                                      .value=${this.formData.name}
                                                      @input=${(e) => this._handleInput('name', e)}
                                                      required
                                                  />
                                              </label>
                                              <label class="field">
                                                  <input
                                                      class="field-input"
                                                      type="email"
                                                      autocomplete="email"
                                                      placeholder=${t('cta.placeholder_email')}
                                                      .value=${this.formData.email}
                                                      @input=${(e) => this._handleInput('email', e)}
                                                      required
                                                  />
                                              </label>
                                          </div>
                                          <div class="form-row">
                                              <label class="field">
                                                  <input
                                                      class="field-input"
                                                      type="tel"
                                                      autocomplete="tel"
                                                      placeholder=${t('cta.placeholder_phone')}
                                                      .value=${this.formData.phone}
                                                      @input=${(e) => this._handleInput('phone', e)}
                                                  />
                                              </label>
                                              <label class="field">
                                                  <input
                                                      class="field-input"
                                                      type="text"
                                                      autocomplete="organization"
                                                      placeholder=${t('cta.placeholder_company')}
                                                      .value=${this.formData.company}
                                                      @input=${(e) => this._handleInput('company', e)}
                                                  />
                                              </label>
                                          </div>
                                          <label class="field">
                                              <input
                                                  class="field-input"
                                                  type="text"
                                                  placeholder=${t('cta.placeholder_comment')}
                                                  .value=${this.formData.comment}
                                                  @input=${(e) => this._handleInput('comment', e)}
                                              />
                                          </label>
                                      </div>
                                      <button
                                          type="submit"
                                          class="lead-modal-submit"
                                          ?disabled=${this.isSubmitting}
                                      >
                                          ${this.isSubmitting
                                              ? html`
                                                    <span class="submit-spinner" aria-hidden="true"></span>
                                                    <span>${t('cta.submit_sending')}</span>
                                                `
                                              : html`
                                                    <platform-icon name="send" size="20"></platform-icon>
                                                    <span>${t('cta.submit_idle')}</span>
                                                `}
                                      </button>
                                  </form>
                              </div>
                          </div>
                      </div>
                  `
                : ''}
        `;
    }
}

customElements.define('landing-cta', LandingCta);
