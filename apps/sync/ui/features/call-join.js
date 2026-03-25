/**
 * CallJoinPage — страница входа в звонок по ссылке.
 *
 * Сценарии:
 * - Зарегистрированный пользователь: auth cookie есть → кнопка "Войти как {name}".
 * - Гость: нет cookie → поле имени + кнопка "Присоединиться".
 * - Гость может нажать "Войти" → redirect на /login?next=текущий_url.
 *
 * После входа открывает call-overlay с полученным LiveKit токеном.
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

const token = window.location.pathname.split('/').at(-1);
const API_BASE = '/sync/api/v1/calls';

class CallJoinPage extends PlatformElement {
    static properties = {
        _linkInfo: { state: true },
        _currentUser: { state: true },
        _guestName: { state: true },
        _loading: { state: true },
        _error: { state: true },
        _joinData: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
        :host {
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            background: var(--bg-primary, #0f0f0f);
            font-family: var(--font-sans, system-ui, sans-serif);
        }

        .card {
            background: var(--glass-solid-subtle, rgba(255,255,255,0.05));
            border: 1px solid var(--glass-border-medium, rgba(255,255,255,0.12));
            border-radius: var(--radius-2xl, 20px);
            padding: 40px 48px;
            max-width: 420px;
            width: 100%;
            margin: 16px;
            display: flex;
            flex-direction: column;
            gap: 24px;
            backdrop-filter: blur(16px);
        }

        .logo {
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 4px;
        }

        .logo img { width: 36px; height: 36px; }

        .logo-name {
            font-size: 18px;
            font-weight: 600;
            color: var(--text-primary, #fff);
        }

        h1 {
            font-size: 22px;
            font-weight: 700;
            color: var(--text-primary, #fff);
            margin: 0;
            line-height: 1.3;
        }

        .meta {
            font-size: 14px;
            color: var(--text-secondary, rgba(255,255,255,0.6));
            display: flex;
            flex-direction: column;
            gap: 4px;
        }

        .meta span { display: flex; align-items: center; gap: 6px; }

        input {
            width: 100%;
            box-sizing: border-box;
            padding: 12px 16px;
            font-size: 15px;
            border-radius: var(--radius-lg, 12px);
            border: 1px solid var(--glass-border-medium, rgba(255,255,255,0.16));
            background: var(--glass-solid-subtle, rgba(255,255,255,0.06));
            color: var(--text-primary, #fff);
            outline: none;
            transition: border-color 0.15s;
        }

        input:focus { border-color: var(--accent-primary, #6366f1); }

        input::placeholder { color: var(--text-tertiary, rgba(255,255,255,0.35)); }

        .btn {
            padding: 13px 24px;
            font-size: 15px;
            font-weight: 600;
            border-radius: var(--radius-lg, 12px);
            border: none;
            cursor: pointer;
            transition: all 0.15s;
            width: 100%;
        }

        .btn-primary {
            background: var(--accent-primary, #6366f1);
            color: #fff;
        }

        .btn-primary:hover:not(:disabled) {
            background: var(--accent-primary-hover, #4f52cc);
        }

        .btn-primary:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }

        .btn-ghost {
            background: transparent;
            color: var(--text-secondary, rgba(255,255,255,0.6));
            border: 1px solid var(--glass-border-medium, rgba(255,255,255,0.16));
            font-size: 13px;
            padding: 10px 16px;
        }

        .btn-ghost:hover { background: var(--glass-solid-subtle, rgba(255,255,255,0.06)); }

        .error {
            color: var(--color-error, #f87171);
            font-size: 13px;
            padding: 10px 14px;
            background: rgba(248,113,113,0.1);
            border-radius: var(--radius-md, 8px);
        }

        .divider {
            display: flex;
            align-items: center;
            gap: 12px;
            color: var(--text-tertiary, rgba(255,255,255,0.3));
            font-size: 12px;
        }

        .divider::before, .divider::after {
            content: '';
            flex: 1;
            height: 1px;
            background: var(--glass-border-subtle, rgba(255,255,255,0.08));
        }

        .spinner {
            width: 20px; height: 20px;
            border: 2px solid rgba(255,255,255,0.2);
            border-top-color: #fff;
            border-radius: 50%;
            animation: spin 0.6s linear infinite;
            margin: 0 auto;
        }
        @keyframes spin { to { transform: rotate(360deg); } }

        .call-icon {
            display: flex;
            align-items: center;
            color: var(--accent-primary, #6366f1);
            margin-bottom: 4px;
        }
    `,
    ];

    constructor() {
        super();
        this._linkInfo = null;
        this._currentUser = null;
        this._guestName = '';
        this._loading = true;
        this._error = null;
        this._joinData = null;
    }

    async connectedCallback() {
        super.connectedCallback();
        try {
            await Promise.all([this._fetchLinkInfo(), this._fetchCurrentUser()]);
        } finally {
            // Гарантируем снятие спиннера даже при исключении.
            this._loading = false;
        }
    }

    async _fetchLinkInfo() {
        try {
            const res = await fetch(`${API_BASE}/join/${token}`);
            if (!res.ok) {
                this._error = res.status === 404 ? 'Ссылка не найдена или истекла.' : 'Ошибка загрузки информации о звонке.';
                return;
            }
            this._linkInfo = await res.json();
        } catch {
            this._error = 'Не удалось загрузить информацию о звонке.';
        }
    }

    async _fetchCurrentUser() {
        try {
            const res = await fetch('/sync/api/auth/me', { credentials: 'include' });
            if (res.ok) this._currentUser = await res.json();
        } catch {
            // гость — не ошибка
        }
    }

    async _join() {
        this._error = null;
        this._loading = true;
        try {
            // Зарегистрированный: не отправляем тело — сервер берёт user_id из cookie.
            // Гость: отправляем { guest_name }.
            const fetchOptions = this._currentUser
                ? { method: 'POST', credentials: 'include' }
                : {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'include',
                    body: JSON.stringify({ guest_name: this._guestName.trim() }),
                };
            const res = await fetch(`${API_BASE}/join/${token}`, fetchOptions);
            if (!res.ok) {
                const err = await res.json().catch(() => ({ detail: 'Ошибка входа.' }));
                throw new Error(err.detail || 'Ошибка входа.');
            }
            this._joinData = await res.json();
        } catch (e) {
            this._error = e.message;
        } finally {
            this._loading = false;
        }
    }

    _loginRedirect() {
        const next = encodeURIComponent(window.location.href);
        window.location.href = `/login?next=${next}`;
    }

    _canJoin() {
        if (this._currentUser) return true;
        return this._guestName.trim().length >= 1;
    }

    render() {
        if (this._joinData) {
            return html`
                <call-overlay
                    livekit-url=${this._joinData.livekit_url}
                    livekit-token=${this._joinData.livekit_token}
                    call-id=${this._joinData.call_id}
                    mode="sfu"
                    .identity=${this._joinData.identity}
                    .names=${this._joinData.participant_names ?? {}}
                ></call-overlay>
            `;
        }

        return html`
            <div class="card">
                <div class="logo">
                    <img src="/static/core/assets/service_logos/sync_logo.svg" alt="Sync">
                    <span class="logo-name">Sync</span>
                </div>

                ${this._loading ? html`<div class="spinner"></div>` : this._renderContent()}
            </div>
        `;
    }

    _renderContent() {
        if (this._error && !this._linkInfo) {
            return html`<div class="error">${this._error}</div>`;
        }
        if (!this._linkInfo) return html``;

        return html`
            <div>
                <div class="call-icon" aria-hidden="true">
                    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07 19.5 19.5 0 01-6-6 19.79 19.79 0 01-3.07-8.67A2 2 0 014.11 2h3a2 2 0 012 1.72 12.84 12.84 0 00.7 2.81 2 2 0 01-.45 2.11L8.09 9.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45 12.84 12.84 0 002.81.7A2 2 0 0122 16.92z"/>
                    </svg>
                </div>
                <h1>Приглашение на звонок</h1>
            </div>

            <div class="meta">
                <span>Канал: ${this._linkInfo.channel_name ?? '—'}</span>
                <span>Организатор: ${this._linkInfo.creator_display_name}</span>
                <span>Звонок</span>
            </div>

            ${this._error ? html`<div class="error">${this._error}</div>` : ''}

            ${this._currentUser
                ? html`
                    <button
                        class="btn btn-primary"
                        ?disabled=${this._loading}
                        @click=${this._join}
                    >
                        ${this._loading ? html`<div class="spinner"></div>` : `Войти как ${this._currentUser.name ?? this._currentUser.user_id}`}
                    </button>
                `
                : html`
                    <input
                        type="text"
                        placeholder="Ваше имя"
                        maxlength="64"
                        .value=${this._guestName}
                        @input=${e => this._guestName = e.target.value}
                        @keydown=${e => e.key === 'Enter' && this._canJoin() && this._join()}
                        autocomplete="nickname"
                    >
                    <button
                        class="btn btn-primary"
                        ?disabled=${!this._canJoin() || this._loading}
                        @click=${this._join}
                    >
                        ${this._loading ? html`<div class="spinner"></div>` : 'Присоединиться'}
                    </button>

                    <div class="divider">или</div>

                    <button class="btn btn-ghost" @click=${this._loginRedirect}>
                        Войти в аккаунт
                    </button>
                `
            }
        `;
    }
}

customElements.define('call-join-page', CallJoinPage);

// Динамически загружаем call-overlay
import('./call-overlay.js');
