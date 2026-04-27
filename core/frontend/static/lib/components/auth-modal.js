/**
 * auth-modal — окно входа в платформу.
 *
 * Открытие: dispatch CoreEvents.UI_MODAL_OPEN { kind: 'auth.login',
 *                                               props: { returnPath?, plan? } }.
 * Закрытие: this.close() (dispatch CoreEvents.UI_MODAL_CLOSE).
 *
 * Логика входа: модалка только диспатчит auth/oauth/start_requested и
 * auth/demo/login_requested; редирект делает auth.effect. Состояние демо
 * (enabled, email) приходит из state.auth.demo.
 */
import { html, css } from 'lit';
import { PlatformModal } from './glass-modal.js';
import { registerModalKind } from '../utils/modal-registry.js';
import { CoreAuthEvents } from '../events/effects/auth.effect.js';
import './platform-icon.js';

export class AuthModal extends PlatformModal {
    static modalKind = 'auth.login';

    static properties = {
        ...PlatformModal.properties,
        returnPath: { type: String, attribute: 'return-path' },
        plan: { type: String },
        loading: { state: true },
        error: { state: true },
        _demoPassword: { state: true },
    };

    static styles = [
        PlatformModal.styles,
        css`
            .modal-subtitle { text-align: center; opacity: 0.7; margin-bottom: var(--space-6); }
            .providers { display: flex; flex-direction: column; gap: var(--space-3); }
            .provider-button {
                display: flex; align-items: center; justify-content: center; gap: var(--space-3);
                padding: var(--space-3) var(--space-4);
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: var(--radius-md);
                font-size: var(--text-base); color: var(--text-primary);
                cursor: pointer; transition: all 0.2s ease;
            }
            .provider-button:hover { background: rgba(255, 255, 255, 0.1); transform: translateY(-1px); }
            .provider-button:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }
            .provider-icon { width: 24px; height: 24px; }
            .error {
                margin-top: var(--space-4); padding: var(--space-3);
                background: rgba(255, 59, 48, 0.1); border: 1px solid rgba(255, 59, 48, 0.3);
                border-radius: var(--radius-sm); color: #FF3B30;
                font-size: var(--text-sm); text-align: center;
            }
            .demo-title { margin: var(--space-6) 0 var(--space-3); text-align: center; opacity: 0.85; font-size: var(--text-sm); }
            .demo-form { display: flex; flex-direction: column; gap: var(--space-2); }
            .demo-label { font-size: var(--text-xs); opacity: 0.8; }
            .demo-input {
                width: 100%; box-sizing: border-box;
                padding: var(--space-3);
                background: rgba(255, 255, 255, 0.06);
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: var(--radius-sm);
                color: var(--text-primary); font-size: var(--text-base);
            }
            .demo-input:focus { outline: none; border-color: var(--accent); }
        `,
    ];

    constructor() {
        super();
        this.returnPath = '';
        this.plan = '';
        this.loading = false;
        this.error = '';
        this._demoPassword = '';
        this.size = 'sm';
        this._demoSel = this.select((s) => s.auth.demo);
    }

    connectedCallback() {
        super.connectedCallback();
        this.dispatch(CoreAuthEvents.DEMO_STATUS_REQUESTED, null);
        this.useEvent(CoreAuthEvents.OAUTH_FAILED, (event) => {
            this.loading = false;
            this.error = (event.payload && event.payload.message) || (this.t('auth.oauth_error') || 'OAuth error');
        });
        this.useEvent(CoreAuthEvents.DEMO_LOGIN_FAILED, (event) => {
            this.loading = false;
            this.error = (event.payload && event.payload.message) || (this.t('auth.demo_error') || 'Demo login error');
        });
    }

    willUpdate(changed) {
        super.willUpdate(changed);
        this.title = this.t('auth.title') || 'auth.title';
        if (changed.has('open') && this.open) {
            this.loading = false;
            this.error = '';
            this._demoPassword = '';
        }
    }

    _handleProvider(provider) {
        if (this.loading) return;
        this.loading = true;
        this.error = '';
        const returnPath = (typeof this.returnPath === 'string' && this.returnPath !== '') ? this.returnPath : undefined;
        const plan = (typeof this.plan === 'string' && this.plan !== '') ? this.plan : undefined;
        this.startOAuth(provider, { returnPath, plan });
    }

    _openSupport() {
        this.close();
        this.navigate('support');
    }

    renderHeaderActions() {
        const label = this.t('auth.support_link_aria');
        return html`
            <button
                type="button"
                class="header-btn"
                title=${label}
                aria-label=${label}
                @click=${this._openSupport}
            >
                <platform-icon name="help" size="16"></platform-icon>
            </button>
        `;
    }

    _handleDemoSubmit(e) {
        e.preventDefault();
        if (this.loading) return;
        const demo = (this._demoSel && this._demoSel.value) || { email: '' };
        const email = (demo.email || '').trim();
        if (!email || !this._demoPassword) {
            this.error = this.t('auth.demo_error') || 'Email and password required';
            return;
        }
        this.loading = true;
        this.error = '';
        this.dispatch(CoreAuthEvents.DEMO_LOGIN_REQUESTED, {
            email,
            password: this._demoPassword,
        });
    }

    renderBody() {
        const t = (key) => this.t(key) || key;
        const demo = (this._demoSel && this._demoSel.value) || { enabled: false, email: '' };
        return html`
            <p class="modal-subtitle">${t('auth.subtitle')}</p>
            <div class="providers">
                <button class="provider-button" @click=${() => this._handleProvider('yandex')} ?disabled=${this.loading}>
                    <platform-icon name="yandex" size="24" colored></platform-icon>
                    <span>${t('auth.yandex')}</span>
                </button>
                <button class="provider-button" @click=${() => this._handleProvider('google')} ?disabled=${this.loading}>
                    <platform-icon name="google" size="24" colored></platform-icon>
                    <span>${t('auth.google')}</span>
                </button>
                <button class="provider-button" @click=${() => this._handleProvider('github')} ?disabled=${this.loading}>
                    <img src="/static/frontend/assets/icons/providers/github.svg" class="provider-icon" alt="GitHub">
                    <span>${t('auth.github')}</span>
                </button>
                <button class="provider-button" @click=${() => this._handleProvider('apple')} ?disabled=${this.loading}>
                    <img src="/static/frontend/assets/icons/providers/apple.svg" class="provider-icon" alt="Apple">
                    <span>${t('auth.apple')}</span>
                </button>
            </div>

            ${demo.enabled ? html`
                <p class="demo-title">${t('auth.demo_title')}</p>
                <form class="demo-form" @submit=${(e) => this._handleDemoSubmit(e)}>
                    <label class="demo-label" for="demo-email">${t('auth.demo_email_label')}</label>
                    <input id="demo-email" class="demo-input" type="email" name="username" autocomplete="username"
                        .value=${demo.email || ''} disabled />
                    <label class="demo-label" for="demo-password">${t('auth.demo_password_label')}</label>
                    <input id="demo-password" class="demo-input" type="password" name="password" autocomplete="current-password"
                        .value=${this._demoPassword}
                        @input=${(ev) => { this._demoPassword = ev.target.value; }} />
                    <button type="submit" class="provider-button" ?disabled=${this.loading}>
                        ${t('auth.demo_submit')}
                    </button>
                </form>
            ` : ''}

            ${this.error ? html`<div class="error">${this.error}</div>` : ''}
        `;
    }

    renderFooter() {
        return html``;
    }
}

customElements.define('auth-modal', AuthModal);
registerModalKind(AuthModal.modalKind, 'auth-modal');
