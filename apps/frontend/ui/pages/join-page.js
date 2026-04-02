/**
 * Страница принятия приглашения по ссылке.
 *
 * Сценарии:
 *  - Не авторизован: показывает кнопки OAuth; после логина возвращает на эту же страницу с token
 *  - Авторизован: сразу вызывает accept
 *  - Уже участник: сообщает об этом
 *  - Токен истёк / использован / поддельный: понятная ошибка
 */
import { html, css } from 'lit';
import { unsafeHTML } from 'lit/directives/unsafe-html.js';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { AuthService } from '@platform/services/auth.service.js';
import '@platform/lib/components/auth-modal.js';

export class JoinPage extends PlatformElement {
    static properties = {
        _state: { state: true },
        _error: { state: true },
        _companyName: { state: true },
        _role: { state: true },
        _alreadyMember: { state: true },
        _loading: { state: true },
        _authChecked: { state: true },
        _isAuthed: { state: true },
        _showAuthModal: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: flex;
                align-items: center;
                justify-content: center;
                min-height: var(--app-vh, 100vh);
                background: var(--bg-gradient, #0F0F0F);
                padding: 24px;
            }

            .card {
                background: var(--glass-solid-medium, rgba(255,255,255,0.05));
                border: 1px solid var(--glass-border-subtle, rgba(255,255,255,0.1));
                border-radius: 24px;
                padding: 48px 40px;
                max-width: 460px;
                width: 100%;
                text-align: center;
                backdrop-filter: blur(20px);
            }

            .logo {
                font-size: 48px;
                margin-bottom: 16px;
            }

            .title {
                font-size: 28px;
                font-weight: 600;
                color: var(--text-primary, #fff);
                margin: 0 0 8px 0;
            }

            .subtitle {
                font-size: 16px;
                color: var(--text-secondary, rgba(255,255,255,0.6));
                margin: 0 0 32px 0;
            }

            .company-name {
                color: var(--accent, #10B981);
                font-weight: 600;
            }

            .role-badge {
                display: inline-block;
                padding: 4px 12px;
                background: var(--accent-subtle, rgba(16,185,129,0.15));
                border: 1px solid var(--accent, #10B981);
                border-radius: 999px;
                font-size: 13px;
                font-weight: 600;
                color: var(--accent, #10B981);
                text-transform: uppercase;
                letter-spacing: 0.5px;
                margin-bottom: 32px;
            }

            .primary-button {
                display: block;
                width: 100%;
                padding: 14px 24px;
                background: var(--accent, #10B981);
                color: white;
                border: none;
                border-radius: 12px;
                font-size: 16px;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.2s;
                margin-bottom: 12px;
            }

            .primary-button:hover {
                opacity: 0.9;
                transform: translateY(-1px);
            }

            .primary-button:disabled {
                opacity: 0.5;
                cursor: not-allowed;
                transform: none;
            }

            .provider-button {
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 10px;
                width: 100%;
                padding: 14px 20px;
                background: rgba(255,255,255,0.05);
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 12px;
                font-size: 15px;
                color: var(--text-primary, #fff);
                cursor: pointer;
                transition: all 0.2s;
                margin-bottom: 10px;
            }

            .provider-button:hover {
                background: rgba(255,255,255,0.1);
            }

            .provider-button:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }

            .error-box {
                padding: 12px 16px;
                background: rgba(239,68,68,0.1);
                border: 1px solid rgba(239,68,68,0.3);
                border-radius: 10px;
                color: #EF4444;
                font-size: 14px;
                margin-bottom: 16px;
            }

            .success-box {
                padding: 12px 16px;
                background: rgba(16,185,129,0.1);
                border: 1px solid rgba(16,185,129,0.3);
                border-radius: 10px;
                color: var(--accent, #10B981);
                font-size: 15px;
                margin-bottom: 16px;
            }

            .dashboard-link {
                display: block;
                margin-top: 16px;
                color: var(--accent, #10B981);
                text-decoration: none;
                font-size: 14px;
            }

            .dashboard-link:hover {
                text-decoration: underline;
            }

            .loading-spinner {
                width: 40px;
                height: 40px;
                border: 3px solid var(--glass-border-subtle, rgba(255,255,255,0.1));
                border-top: 3px solid var(--accent, #10B981);
                border-radius: 50%;
                animation: spin 0.8s linear infinite;
                margin: 0 auto 16px;
            }

            @keyframes spin {
                from { transform: rotate(0deg); }
                to { transform: rotate(360deg); }
            }

            .divider {
                margin: 16px 0;
                color: var(--text-secondary, rgba(255,255,255,0.4));
                font-size: 13px;
            }
        `
    ];

    constructor() {
        super();
        this._state = 'loading';
        this._error = null;
        this._companyName = null;
        this._role = null;
        this._alreadyMember = false;
        this._loading = false;
        this._authChecked = false;
        this._isAuthed = false;
        this._showAuthModal = false;
        this._token = new URLSearchParams(window.location.search).get('token');
    }

    async connectedCallback() {
        super.connectedCallback();
        this._i18nUnsub = this.i18n.subscribe(() => this.requestUpdate());
        await this._init();
    }

    disconnectedCallback() {
        if (this._i18nUnsub) {
            this._i18nUnsub();
            this._i18nUnsub = null;
        }
        super.disconnectedCallback();
    }

    get _baseUrl() {
        return '/frontend';
    }

    get auth() {
        if (!this._authService) {
            this._authService = new AuthService(this._baseUrl);
        }
        return this._authService;
    }

    async _init() {
        if (!this._token) {
            this._state = 'no-token';
            return;
        }

        this._isAuthed = await this.auth.validateToken();
        this._authChecked = true;

        if (!this._isAuthed) {
            this._state = 'needs-auth';
            return;
        }

        await this._accept();
    }

    async _accept() {
        this._state = 'accepting';
        this._loading = true;
        this._error = null;

        try {
            const resp = await fetch(`${this._baseUrl}/api/invites/accept`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify({ token: this._token }),
            });

            const data = await resp.json();

            if (!resp.ok) {
                const msg = data.detail || this.i18n.t('join_page.accept_error', {});
                if (resp.status === 410) {
                    this._error = data.detail;
                    this._state = 'expired';
                } else if (resp.status === 403) {
                    this._error = this.i18n.t('join_page.invalid_platform', {});
                    this._state = 'invalid';
                } else if (resp.status === 404) {
                    this._error = data.detail;
                    this._state = 'not-found';
                } else {
                    this._error = msg;
                    this._state = 'error';
                }
                return;
            }

            this._companyName = data.company_name;
            this._role = Array.isArray(data.role) ? data.role[0] : data.role;
            this._alreadyMember = data.already_member;
            this._state = 'success';
        } catch (e) {
            this._error = this.i18n.t('join_page.network_error', {});
            this._state = 'error';
        } finally {
            this._loading = false;
        }
    }

    async _startOAuth(provider) {
        this._loading = true;
        const returnPath = `/join?token=${encodeURIComponent(this._token)}`;
        try {
            const resp = await fetch(
                `${this._baseUrl}/api/auth/login/${provider}?return_path=${encodeURIComponent(returnPath)}`,
                { credentials: 'include' }
            );
            const data = await resp.json();
            if (data.auth_url) {
                window.location.href = data.auth_url;
            }
        } catch (e) {
            this._error = this.i18n.t('join_page.oauth_error', {});
            this._loading = false;
        }
    }

    _goToDashboard() {
        window.location.href = '/dashboard';
    }

    render() {
        return html`
            <div class="card">
                <div class="logo">H</div>
                ${this._renderBody()}
            </div>
        `;
    }

    _renderBody() {
        const td = (key, params) => this.i18n.t(key, params ?? {});
        const roleLabel = (r) => this.i18n.t(`team_roles.${r}`, {});
        switch (this._state) {
            case 'loading':
            case 'accepting':
                return html`
                    <div class="loading-spinner"></div>
                    <p class="subtitle">${this._state === 'accepting' ? td('join_page.accepting') : td('join_page.loading')}</p>
                `;

            case 'no-token':
                return html`
                    <h1 class="title">${td('join_page.no_token_title')}</h1>
                    <p class="subtitle">${td('join_page.no_token_text')}</p>
                `;

            case 'needs-auth':
                return html`
                    <h1 class="title">${td('join_page.needs_auth_title')}</h1>
                    <p class="subtitle">${td('join_page.needs_auth_subtitle')}</p>

                    <button
                        class="provider-button"
                        ?disabled=${this._loading}
                        @click=${() => this._startOAuth('yandex')}
                    >
                        ${td('join_page.login_yandex')}
                    </button>
                    <button
                        class="provider-button"
                        ?disabled=${this._loading}
                        @click=${() => this._startOAuth('google')}
                    >
                        ${td('join_page.login_google')}
                    </button>
                    <button
                        class="provider-button"
                        ?disabled=${this._loading}
                        @click=${() => this._startOAuth('github')}
                    >
                        ${td('join_page.login_github')}
                    </button>
                    <button
                        class="provider-button"
                        ?disabled=${this._loading}
                        @click=${() => this._startOAuth('apple')}
                    >
                        ${td('join_page.login_apple')}
                    </button>

                    ${this._error ? html`<div class="error-box">${this._error}</div>` : ''}
                `;

            case 'success':
                return html`
                    <h1 class="title">
                        ${this._alreadyMember ? td('join_page.success_already_title') : td('join_page.success_welcome_title')}
                    </h1>
                    <div class="success-box">
                        ${unsafeHTML(
                            this._alreadyMember
                                ? td('join_page.success_already_body', { name: this._companyName ?? '' })
                                : td('join_page.success_joined_body', { name: this._companyName ?? '' }),
                        )}
                    </div>
                    ${this._role ? html`<div class="role-badge">${roleLabel(this._role)}</div>` : ''}
                    <button class="primary-button" @click=${this._goToDashboard}>
                        ${td('join_page.go_dashboard')}
                    </button>
                `;

            case 'expired':
                return html`
                    <h1 class="title">${td('join_page.expired_title')}</h1>
                    <div class="error-box">${this._error || td('join_page.expired_fallback')}</div>
                `;

            case 'invalid':
                return html`
                    <h1 class="title">${td('join_page.invalid_title')}</h1>
                    <div class="error-box">${this._error || td('join_page.invalid_fallback')}</div>
                `;

            case 'not-found':
                return html`
                    <h1 class="title">${td('join_page.not_found_title')}</h1>
                    <div class="error-box">${this._error || td('join_page.not_found_fallback')}</div>
                `;

            default:
                return html`
                    <h1 class="title">${td('join_page.error_title')}</h1>
                    <div class="error-box">${this._error || td('join_page.error_fallback')}</div>
                `;
        }
    }
}

customElements.define('join-page', JoinPage);
