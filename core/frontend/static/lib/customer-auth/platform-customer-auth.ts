/**
 * `<platform-customer-auth>` — платформенный виджет авторизации покупателя
 * по номеру телефона (→ `.cursor/rules/customers.mdc`).
 *
 * Встраивание — одна строка на страницу продукта:
 *   <script src="/static/core/lib/customer-auth/autoload.js" defer></script>
 *   <platform-customer-auth api-base="/shop/api/v1/public/customer-auth"
 *                           company-id="cmp_..."></platform-customer-auth>
 *
 * API:
 *   el.open()               — начать/проверить сессию; если `customer_token`
 *                             уже валиден — сразу событие `confirmed`.
 *   `customer-authenticated` CustomEvent<{customer_id, phone_e164, name}>
 *   `customer-auth-cancelled` CustomEvent — закрыли без подтверждения.
 *
 * Все провайдеры, fallback и коды — на стороне core-роутера; компонент
 * ничего не знает о конкретных провайдерах, кроме подписей кнопок.
 */
import { css, html, LitElement, nothing } from 'lit';

type Step =
    | 'phone'
    | 'methods'
    | 'code'
    | 'awaiting_contact'
    | 'awaiting_oauth'
    | 'done';

interface MethodOption {
    kind: string;
    ui: 'deep_link' | 'oauth' | 'contact_share' | 'code_input' | 'auto';
    priority: number;
    provider?: string | null;
    deep_link?: string | null;
}

interface ChallengeView {
    status: 'challenge_sent' | 'awaiting_contact' | 'awaiting_oauth';
    challenge_id: string;
    method: string;
    expires_in: number;
    resend_after: number;
    deep_link?: string | null;
    oauth_url?: string | null;
}

interface CustomerMe {
    customer_id: string;
    phone_e164: string;
    scope_company_id: string;
    name?: string | null;
}

const T: Record<string, { ru: string; en: string }> = {
    title: { ru: 'Вход по номеру телефона', en: 'Sign in with phone number' },
    subtitle: {
        ru: 'Чтобы оформить заказ, подтвердите номер — это займёт секунды',
        en: 'Confirm your number to place the order — it takes seconds',
    },
    phone_placeholder: { ru: '+7 999 123-45-67', en: '+7 999 123-45-67' },
    continue: { ru: 'Продолжить', en: 'Continue' },
    choose_method: { ru: 'Как подтвердить номер?', en: 'How to confirm the number?' },
    sms_code: { ru: 'Код по SMS', en: 'SMS code' },
    telegram_contact: { ru: 'Telegram', en: 'Telegram' },
    max_contact: { ru: 'MAX', en: 'MAX' },
    yandex_id: { ru: 'Яндекс ID', en: 'Yandex ID' },
    vk_id: { ru: 'VK ID', en: 'VK ID' },
    sber_id: { ru: 'Sber ID', en: 'Sber ID' },
    emulator: { ru: 'Эмулятор (dev)', en: 'Emulator (dev)' },
    code_sent: { ru: 'Код отправлен. Введите его ниже', en: 'Code sent. Enter it below' },
    code_placeholder: { ru: 'Код из SMS', en: 'SMS code' },
    confirm: { ru: 'Подтвердить', en: 'Confirm' },
    open_app: { ru: 'Открыть приложение', en: 'Open the app' },
    waiting_contact: {
        ru: 'Отправьте контакт в приложении — мы подтвердим номер автоматически',
        en: 'Share your contact in the app — we will confirm automatically',
    },
    waiting_oauth: {
        ru: 'Завершите вход в открывшейся вкладке',
        en: 'Finish sign-in in the opened tab',
    },
    back: { ru: 'Назад', en: 'Back' },
    close: { ru: 'Закрыть', en: 'Close' },
    resend: { ru: 'Отправить ещё раз', en: 'Resend' },
    error_invalid_phone: { ru: 'Проверьте номер', en: 'Check the phone number' },
    error_code_invalid: { ru: 'Неверный код', en: 'Wrong code' },
    error_generic: { ru: 'Не получилось. Попробуйте ещё раз', en: 'Something went wrong. Try again' },
    error_rate: { ru: 'Слишком часто. Подождите немного', en: 'Too often. Wait a bit' },
    done: { ru: 'Номер подтверждён', en: 'Number confirmed' },
};

const ERROR_KEYS: Record<string, string> = {
    invalid_phone: 'error_invalid_phone',
    code_invalid: 'error_code_invalid',
    code_expired: 'error_code_invalid',
    rate_limited: 'error_rate',
    attempts_exceeded: 'error_rate',
    challenge_expired: 'error_generic',
};

export class PlatformCustomerAuth extends LitElement {
    static override properties = {
        apiBase: { type: String, attribute: 'api-base' },
        companyId: { type: String, attribute: 'company-id' },
        locale: { type: String },
        _opened: { state: true },
        _step: { state: true },
        _phone: { state: true },
        _methods: { state: true },
        _challenge: { state: true },
        _challengeId: { state: true },
        _code: { state: true },
        _error: { state: true },
        _busy: { state: true },
        _deepLink: { state: true },
        _resendIn: { state: true },
    };

    apiBase = '';
    companyId = '';
    locale = 'ru';
    private _opened = false;
    private _step: Step = 'phone';
    private _phone = '';
    private _methods: MethodOption[] = [];
    private _challenge: ChallengeView | null = null;
    private _challengeId = '';
    private _code = '';
    private _error = '';
    private _busy = false;
    private _deepLink: string | null = null;
    private _resendIn = 0;
    private _pollTimer: number | undefined;
    private _resendTimer: number | undefined;

    static override styles = css`
        :host { display: contents; }
        .overlay {
            position: fixed; inset: 0; z-index: 100000;
            background: rgba(0, 0, 0, 0.45);
            display: flex; align-items: flex-end; justify-content: center;
        }
        @media (min-width: 560px) { .overlay { align-items: center; } }
        .sheet {
            background: #fff; color: #1b1b1f; width: 100%; max-width: 420px;
            border-radius: 20px 20px 0 0; padding: 20px 20px 28px;
            font-family: -apple-system, 'Segoe UI', Roboto, sans-serif;
            box-shadow: 0 -8px 40px rgba(0, 0, 0, 0.25);
            max-height: 90vh; overflow-y: auto;
        }
        @media (min-width: 560px) { .sheet { border-radius: 20px; } }
        .sheet h2 { margin: 0 0 4px; font-size: 19px; font-weight: 650; }
        .sheet p.sub { margin: 0 0 16px; font-size: 14px; color: #5b5b66; line-height: 1.35; }
        .grab { width: 36px; height: 4px; border-radius: 2px; background: #d9d9e0; margin: 0 auto 14px; }
        input {
            width: 100%; box-sizing: border-box; font-size: 17px;
            padding: 13px 14px; border: 1.5px solid #d7d7e0; border-radius: 12px;
            outline: none; background: #fafafd;
        }
        input:focus { border-color: #3f6df6; background: #fff; }
        button.primary {
            width: 100%; margin-top: 12px; padding: 14px; font-size: 16px; font-weight: 600;
            border: none; border-radius: 12px; background: #3f6df6; color: #fff; cursor: pointer;
        }
        button.primary:disabled { opacity: 0.55; cursor: default; }
        button.method {
            display: flex; align-items: center; gap: 10px; width: 100%;
            padding: 13px 14px; margin-top: 8px; font-size: 15px; font-weight: 550;
            border: 1.5px solid #e2e2ea; border-radius: 12px; background: #fff;
            color: #1b1b1f; cursor: pointer; text-align: left;
        }
        button.method:hover { border-color: #3f6df6; }
        button.ghost {
            width: 100%; margin-top: 10px; padding: 11px; font-size: 14px;
            border: none; background: none; color: #5b5b66; cursor: pointer;
        }
        .err { color: #c93a3a; font-size: 13.5px; margin-top: 10px; min-height: 18px; }
        .hint { font-size: 13.5px; color: #5b5b66; line-height: 1.4; margin-top: 12px; }
        .spinner {
            width: 20px; height: 20px; border: 2.5px solid #d7d7e0;
            border-top-color: #3f6df6; border-radius: 50%;
            animation: spin 0.9s linear infinite; margin: 18px auto;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
        .ok { font-size: 15px; font-weight: 600; color: #208a50; text-align: center; margin: 14px 0 4px; }
    `;

    private _t(key: string): string {
        const pair: { ru: string; en: string } = T[key] ?? { ru: 'Error', en: 'Error' };
        return this.locale.startsWith('en') ? pair.en : pair.ru;
    }

    private _emit(type: string, detail?: unknown): void {
        this.dispatchEvent(
            new CustomEvent(type, { detail, bubbles: true, composed: true }),
        );
    }

    /** Открыть лист: если сессия уже есть — сразу `customer-authenticated`. */
    async open(): Promise<void> {
        this._opened = true;
        this._error = '';
        const me = await this._fetch<CustomerMe>('me', undefined, 'GET');
        if (me) {
            this._confirm(me);
            return;
        }
        this._step = 'phone';
    }

    close(cancelled = true): void {
        this._opened = false;
        this._stopPoll();
        if (cancelled) this._emit('customer-auth-cancelled');
    }

    private async _fetch<T>(
        path: string,
        body?: unknown,
        method = 'POST',
    ): Promise<T | null> {
        const url = `${this.apiBase}/${path}`;
        const init: RequestInit = { method, credentials: 'same-origin' };
        if (body !== undefined) {
            init.headers = { 'content-type': 'application/json' };
            init.body = JSON.stringify(body);
        }
        try {
            const resp = await fetch(url, init);
            if (!resp.ok) {
                const detail = (await resp.json().catch(() => null))?.detail;
                this._error = this._t(ERROR_KEYS[detail] ?? 'error_generic');
                return null;
            }
            this._error = '';
            return (await resp.json()) as T;
        } catch {
            this._error = this._t('error_generic');
            return null;
        }
    }

    private _confirm(me: CustomerMe): void {
        this._step = 'done';
        this._opened = false;
        this._stopPoll();
        this._emit('customer-authenticated', me);
    }

    private async _start(): Promise<void> {
        this._busy = true;
        const view = await this._fetch<{ challenge_id: string; methods: MethodOption[] }>(
            'start',
            {
                company_id: this.companyId,
                phone: this._phone.trim() || null,
                client: 'mobile_web',
            },
        );
        this._busy = false;
        if (!view) return;
        this._challengeId = view.challenge_id;
        this._methods = [...view.methods].sort((a, b) => b.priority - a.priority);
        this._step = 'methods';
    }

    private async _choose(method: MethodOption): Promise<void> {
        this._busy = true;
        const view = await this._fetch<ChallengeView>('method', {
            challenge_id: this._challengeId,
            company_id: this.companyId,
            method: method.kind,
            return_url: window.location.href,
        });
        this._busy = false;
        if (!view) return;
        this._challenge = view;
        this._code = '';
        this._deepLink = view.deep_link ?? null;
        if (view.status === 'challenge_sent') {
            this._step = 'code';
            this._startResendCountdown(view.resend_after);
        } else {
            this._step = view.status === 'awaiting_oauth' ? 'awaiting_oauth' : 'awaiting_contact';
            if (view.status === 'awaiting_oauth' && view.oauth_url) {
                window.open(view.oauth_url, '_self');
                return;
            }
            this._pollStatus();
        }
    }

    private async _verify(): Promise<void> {
        this._busy = true;
        const view = await this._fetch<{ status: string; customer?: CustomerMe }>(
            'verify',
            {
                challenge_id: this._challengeId,
                company_id: this.companyId,
                code: this._code.trim(),
            },
        );
        this._busy = false;
        if (view?.status === 'confirmed' && view.customer) this._confirm(view.customer);
    }

    private _pollStatus(): void {
        this._stopPoll();
        const tick = async () => {
            const view = await this._fetch<{
                status: string;
                customer?: CustomerMe;
            }>(`status?challenge_id=${this._challengeId}&company_id=${this.companyId}`, undefined, 'GET');
            if (view?.status === 'confirmed' && view.customer) {
                this._confirm(view.customer);
                return;
            }
            if (view?.status === 'failed' || view?.status === 'expired') {
                this._step = 'methods';
                return;
            }
            this._pollTimer = window.setTimeout(tick, 2000);
        };
        this._pollTimer = window.setTimeout(tick, 2000);
    }

    private _stopPoll(): void {
        if (this._pollTimer !== undefined) window.clearTimeout(this._pollTimer);
        this._pollTimer = undefined;
    }

    private _startResendCountdown(seconds: number): void {
        this._resendIn = Math.max(0, seconds);
        if (this._resendTimer !== undefined) window.clearInterval(this._resendTimer);
        this._resendTimer = window.setInterval(() => {
            this._resendIn = Math.max(0, this._resendIn - 1);
            if (this._resendIn === 0 && this._resendTimer !== undefined) {
                window.clearInterval(this._resendTimer);
                this._resendTimer = undefined;
            }
        }, 1000);
    }

    override disconnectedCallback(): void {
        this._stopPoll();
        if (this._resendTimer !== undefined) window.clearInterval(this._resendTimer);
        super.disconnectedCallback();
    }

    private _methodLabel(kind: string): string {
        return this._t(kind in T ? kind : 'sms_code');
    }

    override render() {
        if (!this._opened) return nothing;
        const busy = this._busy;
        return html`
            <div class="overlay" @click=${(e: Event) => {
                if (e.target === e.currentTarget) this.close();
            }}>
                <div class="sheet" role="dialog" aria-modal="true">
                    <div class="grab"></div>
                    <h2>${this._t('title')}</h2>
                    <p class="sub">${this._t('subtitle')}</p>
                    ${this._step === 'phone' ? html`
                        <input type="tel" inputmode="tel" autocomplete="tel"
                               .value=${this._phone}
                               placeholder=${this._t('phone_placeholder')}
                               @input=${(e: InputEvent) =>
                                   (this._phone = (e.target as HTMLInputElement).value)}
                               @keydown=${(e: KeyboardEvent) =>
                                   e.key === 'Enter' && this._start()} />
                        <button class="primary" ?disabled=${busy}
                                @click=${this._start}>${this._t('continue')}</button>
                    ` : nothing}
                    ${this._step === 'methods' ? html`
                        <p class="sub">${this._t('choose_method')}</p>
                        ${this._methods.map(
                            (m) => html`
                                <button class="method" ?disabled=${busy}
                                        @click=${() => this._choose(m)}>
                                    ${this._methodLabel(m.kind)}
                                </button>`,
                        )}
                        <button class="ghost" @click=${() => (this._step = 'phone')}>
                            ${this._t('back')}
                        </button>
                    ` : nothing}
                    ${this._step === 'code' ? html`
                        <p class="sub">${this._t('code_sent')}</p>
                        <input type="text" inputmode="numeric" autocomplete="one-time-code"
                               .value=${this._code}
                               placeholder=${this._t('code_placeholder')}
                               @input=${(e: InputEvent) =>
                                   (this._code = (e.target as HTMLInputElement).value)}
                               @keydown=${(e: KeyboardEvent) =>
                                   e.key === 'Enter' && this._verify()} />
                        <button class="primary" ?disabled=${busy || !this._code.trim()}
                                @click=${this._verify}>${this._t('confirm')}</button>
                        ${this._resendIn > 0
                            ? html`<p class="hint">${this._t('resend')} · ${this._resendIn}s</p>`
                            : html`<button class="ghost" @click=${() =>
                                this._choose({ kind: this._challenge?.method ?? 'sms_code', ui: 'code_input', priority: 0 })}>
                                ${this._t('resend')}</button>`}
                        <button class="ghost" @click=${() => (this._step = 'methods')}>
                            ${this._t('back')}
                        </button>
                    ` : nothing}
                    ${this._step === 'awaiting_contact' ? html`
                        <div class="spinner"></div>
                        <p class="hint">${this._t('waiting_contact')}</p>
                        ${this._deepLink ? html`
                            <button class="primary" @click=${() =>
                                window.open(this._deepLink!, '_blank')}>
                                ${this._t('open_app')}
                            </button>` : nothing}
                        <button class="ghost" @click=${() => { this._stopPoll(); this._step = 'methods'; }}>
                            ${this._t('back')}
                        </button>
                    ` : nothing}
                    ${this._step === 'awaiting_oauth' ? html`
                        <div class="spinner"></div>
                        <p class="hint">${this._t('waiting_oauth')}</p>
                    ` : nothing}
                    ${this._step === 'done' ? html`
                        <p class="ok">${this._t('done')}</p>
                    ` : nothing}
                    <div class="err">${this._error}</div>
                </div>
            </div>`;
    }
}

if (!customElements.get('platform-customer-auth')) {
    customElements.define('platform-customer-auth', PlatformCustomerAuth);
}
