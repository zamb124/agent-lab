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
        await this._init();
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
                const msg = data.detail || 'Ошибка принятия приглашения';
                if (resp.status === 410) {
                    this._error = data.detail;
                    this._state = 'expired';
                } else if (resp.status === 403) {
                    this._error = 'Ссылка недействительна. Возможно, она была создана не для этой платформы.';
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
            this._error = 'Ошибка сети. Проверьте подключение и попробуйте снова.';
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
            this._error = 'Ошибка запуска авторизации';
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
        switch (this._state) {
            case 'loading':
            case 'accepting':
                return html`
                    <div class="loading-spinner"></div>
                    <p class="subtitle">${this._state === 'accepting' ? 'Вступаем в компанию...' : 'Загрузка...'}</p>
                `;

            case 'no-token':
                return html`
                    <h1 class="title">Ссылка недействительна</h1>
                    <p class="subtitle">В ссылке отсутствует токен приглашения.</p>
                `;

            case 'needs-auth':
                return html`
                    <h1 class="title">Вас пригласили!</h1>
                    <p class="subtitle">Войдите в аккаунт, чтобы принять приглашение в компанию.</p>

                    <button
                        class="provider-button"
                        ?disabled=${this._loading}
                        @click=${() => this._startOAuth('yandex')}
                    >
                        Войти через Яндекс
                    </button>
                    <button
                        class="provider-button"
                        ?disabled=${this._loading}
                        @click=${() => this._startOAuth('google')}
                    >
                        Войти через Google
                    </button>
                    <button
                        class="provider-button"
                        ?disabled=${this._loading}
                        @click=${() => this._startOAuth('github')}
                    >
                        Войти через GitHub
                    </button>

                    ${this._error ? html`<div class="error-box">${this._error}</div>` : ''}
                `;

            case 'success':
                return html`
                    <h1 class="title">
                        ${this._alreadyMember ? 'Вы уже в команде' : 'Добро пожаловать!'}
                    </h1>
                    <div class="success-box">
                        ${this._alreadyMember
                            ? html`Вы уже являетесь участником компании <strong>${this._companyName}</strong>.`
                            : html`Вы вступили в компанию <strong>${this._companyName}</strong>.`}
                    </div>
                    ${this._role ? html`<div class="role-badge">${this._role}</div>` : ''}
                    <button class="primary-button" @click=${this._goToDashboard}>
                        Перейти в панель управления
                    </button>
                `;

            case 'expired':
                return html`
                    <h1 class="title">Ссылка устарела</h1>
                    <div class="error-box">${this._error || 'Срок действия ссылки-приглашения истёк. Попросите отправить новую.'}</div>
                `;

            case 'invalid':
                return html`
                    <h1 class="title">Недействительная ссылка</h1>
                    <div class="error-box">${this._error || 'Ссылка-приглашение недействительна или была подделана.'}</div>
                `;

            case 'not-found':
                return html`
                    <h1 class="title">Компания не найдена</h1>
                    <div class="error-box">${this._error || 'Компания, в которую вас пригласили, не существует или была удалена.'}</div>
                `;

            default:
                return html`
                    <h1 class="title">Что-то пошло не так</h1>
                    <div class="error-box">${this._error || 'Неизвестная ошибка. Попробуйте позже.'}</div>
                `;
        }
    }
}

customElements.define('join-page', JoinPage);
