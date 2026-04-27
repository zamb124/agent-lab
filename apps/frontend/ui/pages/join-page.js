/**
 * Join page — приём инвайта по ссылке.
 *
 * Без сессии показывает выбор провайдера OAuth с return_path на текущий URL
 * (включая ?c=). После входа пользователь снова на этой странице и может
 * принять приглашение через `frontend/invite_accept`.
 */
import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-spinner.js';

export class JoinPage extends PlatformPage {
    static properties = {
        _oauthLoading: { state: true },
        _oauthError: { state: true },
    };

    static styles = [
        PlatformPage.styles,
        css`
            :host {
                display: flex; align-items: center; justify-content: center;
                min-height: 100vh; padding: var(--space-6);
            }
            .card {
                max-width: 460px; padding: var(--space-8);
                background: var(--glass-solid-medium);
                border: 1px solid var(--glass-border-medium);
                border-radius: var(--radius-2xl);
                text-align: center;
            }
            .card h1 { color: var(--text-primary); margin-bottom: var(--space-4); }
            .card p { color: var(--text-secondary); }
            .btn {
                margin-top: var(--space-4); padding: var(--space-3) var(--space-6);
                background: var(--accent); color: white; border: none;
                border-radius: var(--radius-lg); cursor: pointer;
                font-size: var(--text-base);
            }
            .btn:disabled { opacity: 0.5; cursor: not-allowed; }
            .err { color: var(--error); margin-top: var(--space-2); }
            .providers { display: flex; flex-direction: column; gap: var(--space-3); margin-top: var(--space-6); }
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
            .checking { display: flex; flex-direction: column; align-items: center; gap: var(--space-4); }
        `,
    ];

    constructor() {
        super();
        this._invite = this.useOp('frontend/invite_accept');
        this._authStatus = this.select((s) => s.auth.status);
        this._oauthLoading = false;
        this._oauthError = '';
        this.useEvent('auth/oauth/failed', (event) => {
            this._oauthLoading = false;
            const p = event.payload;
            const msg = p && typeof p.message === 'string' ? p.message : '';
            this._oauthError = msg.length > 0 ? msg : this.t('join_page.oauth_failed');
        });
    }

    _shortCode() {
        const u = new URL(window.location.href);
        return u.searchParams.get('c');
    }

    _inviteReturnPath() {
        if (typeof window === 'undefined') return '';
        return `${window.location.pathname}${window.location.search}`;
    }

    _accept() {
        const code = this._shortCode();
        if (!code) return;
        this._invite.run({ short_code: code });
    }

    _startProvider(provider) {
        if (this._oauthLoading) return;
        this._oauthLoading = true;
        this._oauthError = '';
        this.startOAuth(provider, { returnPath: this._inviteReturnPath() });
    }

    render() {
        const authStatus = this._authStatus.value;
        const codeMissing = !this._shortCode();
        const busy = this._invite.busy;
        const error = this._invite.error;
        const done = !!this._invite.lastResult;

        if (authStatus === 'unknown' || authStatus === 'validating') {
            return html`
                <div class="card">
                    <div class="checking">
                        <glass-spinner></glass-spinner>
                        <p>${this.t('join_page.session_checking')}</p>
                    </div>
                </div>
            `;
        }

        if (authStatus === 'unauthenticated' || authStatus === 'error') {
            return html`
                <div class="card">
                    <h1>${this.t('join_page.needs_auth_title')}</h1>
                    <p>${this.t('join_page.needs_auth_subtitle')}</p>
                    ${this._oauthError ? html`<p class="err">${this._oauthError}</p>` : ''}
                    <div class="providers">
                        <button type="button" class="provider-button" ?disabled=${this._oauthLoading}
                            @click=${() => this._startProvider('yandex')}>
                            <platform-icon name="yandex" size="24" colored></platform-icon>
                            <span>${this.t('join_page.login_yandex')}</span>
                        </button>
                        <button type="button" class="provider-button" ?disabled=${this._oauthLoading}
                            @click=${() => this._startProvider('google')}>
                            <platform-icon name="google" size="24" colored></platform-icon>
                            <span>${this.t('join_page.login_google')}</span>
                        </button>
                        <button type="button" class="provider-button" ?disabled=${this._oauthLoading}
                            @click=${() => this._startProvider('github')}>
                            <img src="/static/frontend/assets/icons/providers/github.svg" class="provider-icon" alt="GitHub">
                            <span>${this.t('join_page.login_github')}</span>
                        </button>
                        <button type="button" class="provider-button" ?disabled=${this._oauthLoading}
                            @click=${() => this._startProvider('apple')}>
                            <img src="/static/frontend/assets/icons/providers/apple.svg" class="provider-icon" alt="Apple">
                            <span>${this.t('join_page.login_apple')}</span>
                        </button>
                    </div>
                </div>
            `;
        }

        if (done) {
            return html`
                <div class="card">
                    <h1>${this.t('join_page.title')}</h1>
                    <p>${this.t('join_page.done')}</p>
                </div>
            `;
        }

        const errorMessage = codeMissing
            ? this.t('join_page.no_token_text')
            : error;

        return html`
            <div class="card">
                <h1>${this.t('join_page.title')}</h1>
                <p>${this.t('join_page.text')}</p>
                ${errorMessage ? html`<p class="err">${errorMessage}</p>` : ''}
                <button class="btn" ?disabled=${busy || codeMissing} @click=${() => this._accept()}>
                    ${busy
                        ? this.t('join_page.processing')
                        : this.t('join_page.accept')}
                </button>
            </div>
        `;
    }
}

customElements.define('join-page', JoinPage);
