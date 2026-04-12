import { html, css } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import { nextModalLayerZIndex } from '../utils/modal-z-stack.js';
import './platform-icon.js';

export class AuthModal extends PlatformElement {
    static properties = {
        open: { type: Boolean, reflect: true },
        loading: { type: Boolean },
        error: { type: String },
        /** Путь на том же origin (например /sync или /dashboard) для редиректа после OAuth */
        returnPath: { type: String, attribute: 'return-path' },
        _demoEnabled: { state: true },
        _demoEmail: { state: true },
        _demoPassword: { state: true },
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
                background: rgba(0, 0, 0, 0.7);
                backdrop-filter: blur(10px);
            }

            :host([open]) {
                display: flex;
                align-items: center;
                justify-content: center;
            }

            .modal-content {
                background: var(--glass-bg);
                border: 1px solid var(--glass-border);
                border-radius: 24px;
                padding: 40px;
                max-width: 400px;
                width: 90%;
                backdrop-filter: blur(20px);
                box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
                position: relative;
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

            .providers {
                display: flex;
                flex-direction: column;
                gap: 12px;
            }

            .provider-button {
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 12px;
                padding: 14px 20px;
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 12px;
                font-family: 'Fira Sans', sans-serif;
                font-size: 16px;
                color: var(--landing-secondary);
                cursor: pointer;
                transition: all 0.3s ease;
            }

            .provider-button:hover {
                background: rgba(255, 255, 255, 0.1);
                border-color: var(--landing-primary);
                transform: translateY(-2px);
            }

            .provider-button:disabled {
                opacity: 0.5;
                cursor: not-allowed;
                transform: none;
            }

            .provider-icon {
                width: 24px;
                height: 24px;
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

            .close-button {
                position: absolute;
                top: 16px;
                right: 16px;
                width: 32px;
                height: 32px;
                border: none;
                background: rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                color: var(--landing-secondary);
                font-size: 20px;
                cursor: pointer;
                transition: all 0.2s ease;
            }

            .close-button:hover {
                background: rgba(255, 255, 255, 0.2);
            }

            .demo-title {
                font-family: 'Fira Sans', sans-serif;
                font-size: 14px;
                color: var(--landing-secondary);
                opacity: 0.85;
                margin: 24px 0 12px 0;
                text-align: center;
            }

            .demo-form {
                display: flex;
                flex-direction: column;
                gap: 10px;
                margin-top: 8px;
            }

            .demo-label {
                font-family: 'Fira Sans', sans-serif;
                font-size: 13px;
                color: var(--landing-secondary);
                opacity: 0.8;
            }

            .demo-input {
                width: 100%;
                box-sizing: border-box;
                padding: 12px 14px;
                border-radius: 10px;
                border: 1px solid rgba(255, 255, 255, 0.15);
                background: rgba(255, 255, 255, 0.06);
                color: var(--landing-secondary);
                font-family: 'Fira Sans', sans-serif;
                font-size: 15px;
            }

            .demo-input:focus {
                outline: none;
                border-color: var(--landing-primary);
            }
        `
    ];

    constructor() {
        super();
        this.open = false;
        this.loading = false;
        this.error = '';
        this.returnPath = '';
        this._demoEnabled = false;
        this._demoEmail = '';
        this._demoPassword = '';
        this._onPageShow = (event) => {
            if (event.persisted) {
                this.loading = false;
            }
        };
    }

    connectedCallback() {
        super.connectedCallback();
        window.addEventListener('pageshow', this._onPageShow);
    }

    disconnectedCallback() {
        window.removeEventListener('pageshow', this._onPageShow);
        super.disconnectedCallback();
    }

    willUpdate(changedProperties) {
        super.willUpdate(changedProperties);
        if (changedProperties.has('open') && this.open) {
            this.loading = false;
            this.error = '';
            this._demoPassword = '';
            this.style.setProperty(
                '--platform-modal-layer-z',
                String(nextModalLayerZIndex()),
            );
            this._loadDemoStatus();
        }
    }

    async _loadDemoStatus() {
        try {
            const st = await this.auth.getDemoStatus();
            this._demoEnabled = Boolean(st.enabled);
            this._demoEmail = typeof st.email === 'string' ? st.email : '';
        } catch {
            this._demoEnabled = false;
        }
        this.requestUpdate();
    }

    async _handleDemoSubmit(e) {
        e.preventDefault();
        if (this.loading) return;
        this.loading = true;
        this.error = '';
        try {
            const redirectUrl = await this.auth.loginDemo(
                this._demoEmail.trim(),
                this._demoPassword,
            );
            window.location.href = redirectUrl;
        } catch (error) {
            this.error =
                error.message || this.i18n.t('auth.demo_error', {}, 'shell');
            this.loading = false;
        }
    }

    async handleProviderClick(provider) {
        if (this.loading) return;

        this.loading = true;
        this.error = '';

        try {
            const rp = typeof this.returnPath === 'string' && this.returnPath !== '' ? this.returnPath : null;
            const authUrl = await this.auth.startOAuth(provider, rp);
            window.location.href = authUrl;
        } catch (error) {
            this.error = error.message || this.i18n.t('auth.oauth_error', {}, 'shell');
            this.loading = false;
        }
    }

    close() {
        this.open = false;
        this.loading = false;
        this.error = '';
        this.dispatchEvent(new CustomEvent('close'));
    }

    render() {
        const t = (key) => this.i18n.t(key, {}, 'shell');
        return html`
            <div class="modal-content">
                <button class="close-button" @click=${this.close}>×</button>
                
                <div class="modal-header">
                    <h2 class="modal-title">${t('auth.title')}</h2>
                    <p class="modal-subtitle">${t('auth.subtitle')}</p>
                </div>

                <div class="providers">
                    <button 
                        class="provider-button" 
                        @click=${() => this.handleProviderClick('yandex')}
                        ?disabled=${this.loading}
                    >
                        <platform-icon name="yandex" size="24" colored></platform-icon>
                        <span>${t('auth.yandex')}</span>
                    </button>

                    <button 
                        class="provider-button" 
                        @click=${() => this.handleProviderClick('google')}
                        ?disabled=${this.loading}
                    >
                        <platform-icon name="google" size="24" colored></platform-icon>
                        <span>${t('auth.google')}</span>
                    </button>

                    <button 
                        class="provider-button" 
                        @click=${() => this.handleProviderClick('github')}
                        ?disabled=${this.loading}
                    >
                        <img src="/static/frontend/assets/icons/providers/github.svg" class="provider-icon" alt="GitHub">
                        <span>${t('auth.github')}</span>
                    </button>

                    <button 
                        class="provider-button" 
                        @click=${() => this.handleProviderClick('apple')}
                        ?disabled=${this.loading}
                    >
                        <img src="/static/frontend/assets/icons/providers/apple.svg" class="provider-icon" alt="Apple">
                        <span>${t('auth.apple')}</span>
                    </button>
                </div>

                ${this._demoEnabled
                    ? html`
                          <p class="demo-title">${t('auth.demo_title')}</p>
                          <form class="demo-form" @submit=${this._handleDemoSubmit}>
                              <label class="demo-label" for="demo-email">${t('auth.demo_email_label')}</label>
                              <input
                                  id="demo-email"
                                  class="demo-input"
                                  type="email"
                                  name="username"
                                  autocomplete="username"
                                  .value=${this._demoEmail}
                                  @input=${(ev) => {
                                      this._demoEmail = ev.target.value;
                                  }}
                              />
                              <label class="demo-label" for="demo-password">${t('auth.demo_password_label')}</label>
                              <input
                                  id="demo-password"
                                  class="demo-input"
                                  type="password"
                                  name="password"
                                  autocomplete="current-password"
                                  .value=${this._demoPassword}
                                  @input=${(ev) => {
                                      this._demoPassword = ev.target.value;
                                  }}
                              />
                              <button
                                  type="submit"
                                  class="provider-button"
                                  ?disabled=${this.loading}
                              >
                                  ${t('auth.demo_submit')}
                              </button>
                          </form>
                      `
                    : ''}

                ${this.error ? html`<div class="error">${this.error}</div>` : ''}
            </div>
        `;
    }
}

customElements.define('auth-modal', AuthModal);

