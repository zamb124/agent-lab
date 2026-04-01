import { html, css } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import { ServiceRegistry } from '../services/ServiceRegistry.js';
import { nextModalLayerZIndex } from '../utils/modal-z-stack.js';

export class AuthModal extends PlatformElement {
    static properties = {
        open: { type: Boolean, reflect: true },
        loading: { type: Boolean },
        error: { type: String },
        /** Путь на том же origin (например /sync или /dashboard) для редиректа после OAuth */
        returnPath: { type: String, attribute: 'return-path' },
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
        `
    ];

    constructor() {
        super();
        this.open = false;
        this.loading = false;
        this.error = '';
        this.returnPath = '';
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

    willUpdate(changedProperties) {
        super.willUpdate(changedProperties);
        if (changedProperties.has('open') && this.open) {
            this.style.setProperty(
                '--platform-modal-layer-z',
                String(nextModalLayerZIndex()),
            );
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
                        <img src="/static/frontend/assets/icons/providers/yandex.svg" class="provider-icon" alt="Yandex">
                        <span>${t('auth.yandex')}</span>
                    </button>

                    <button 
                        class="provider-button" 
                        @click=${() => this.handleProviderClick('google')}
                        ?disabled=${this.loading}
                    >
                        <img src="/static/frontend/assets/icons/providers/google.svg" class="provider-icon" alt="Google">
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
                </div>

                ${this.error ? html`<div class="error">${this.error}</div>` : ''}
            </div>
        `;
    }
}

customElements.define('auth-modal', AuthModal);

