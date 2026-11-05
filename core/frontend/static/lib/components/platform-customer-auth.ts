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
 * Тема: атрибут `theme="light|dark|auto"` (default `auto`). Auto берёт
 * унаследованный `color-scheme` страницы-витрины (forced light/dark), иначе
 * `prefers-color-scheme`. Акцент — `--accent`/`--on-accent` хост-страницы;
 * палитру листа переопределяют кастомные свойства `--pca-*`.
 *
 * Все провайдеры, fallback и коды — на стороне core-роутера; компонент
 * ничего не знает о конкретных провайдерах, кроме подписей кнопок.
 */
import { css, html, nothing } from 'lit';

import { PlatformElement } from '../platform-element/index.js';
import { storageGet, storageRemove, storageSet } from '../utils/platform-storage.js';
import { platformStorageKey } from '../utils/storage-keys.js';

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
        ru: 'Завершите вход в открывшемся окне',
        en: 'Finish sign-in in the opened window',
    },
    scan_qr: {
        ru: 'Наведите камеру телефона — откроется чат с ботом',
        en: 'Point your phone camera — it opens the bot chat',
    },
    open_again: { ru: 'Открыть окно ещё раз', en: 'Open the window again' },
    back: { ru: 'Назад', en: 'Back' },
    close: { ru: 'Закрыть', en: 'Close' },
    resend: { ru: 'Отправить ещё раз', en: 'Resend' },
    error_invalid_phone: { ru: 'Проверьте номер', en: 'Check the phone number' },
    error_code_invalid: { ru: 'Неверный код', en: 'Wrong code' },
    error_generic: { ru: 'Не получилось. Попробуйте ещё раз', en: 'Something went wrong. Try again' },
    error_rate: { ru: 'Слишком часто. Подождите немного', en: 'Too often. Wait a bit' },
    done: { ru: 'Номер подтверждён', en: 'Number confirmed' },
};

/** Цвет и короткий знак провайдера для бренд-кнопки метода. */
const BRAND: Record<string, { color: string; glyph: string }> = {
    telegram_contact: { color: '#229ED9', glyph: 'TG' },
    max_contact: { color: '#7B61FF', glyph: 'M' },
    yandex_id: { color: '#FC3F1D', glyph: 'Я' },
    vk_id: { color: '#0077FF', glyph: 'VK' },
    sber_id: { color: '#21A038', glyph: 'S' },
    sms_code: { color: '#8a8a99', glyph: 'SMS' },
    emulator: { color: '#6b6b76', glyph: 'DEV' },
};

const OAUTH_RESUME_KEY = platformStorageKey('core', 'customer_auth.resume');

const ERROR_KEYS: Record<string, string> = {
    invalid_phone: 'error_invalid_phone',
    code_invalid: 'error_code_invalid',
    code_expired: 'error_code_invalid',
    rate_limited: 'error_rate',
    attempts_exceeded: 'error_rate',
    challenge_expired: 'error_generic',
};

export class PlatformCustomerAuth extends PlatformElement {
    static override properties = {
        apiBase: { type: String, attribute: 'api-base' },
        companyId: { type: String, attribute: 'company-id' },
        locale: { type: String },
        // Имя property ≠ attribute: `theme` в core/lib занято гейтом
        // ui_canon (legacy service getter); внешний атрибут — `theme`.
        colorScheme: { type: String, attribute: 'theme' },
        _opened: { state: true },
        _resolvedTheme: { state: true },
        _step: { state: true },
        _phone: { state: true },
        _methods: { state: true },
        _challenge: { state: true },
        _challengeId: { state: true },
        _code: { state: true },
        _error: { state: true },
        _busy: { state: true },
        _deepLink: { state: true },
        _oauthUrl: { state: true },
        _resendIn: { state: true },
    };

    declare apiBase: string;
    declare companyId: string;
    declare locale: string;
    declare colorScheme: string;
    private declare _opened: boolean;
    private declare _resolvedTheme: 'light' | 'dark';
    private declare _step: Step;
    private declare _phone: string;
    private declare _methods: MethodOption[];
    private declare _challenge: ChallengeView | null;
    private declare _challengeId: string;
    private declare _code: string;
    private declare _error: string;
    private declare _busy: boolean;
    private declare _deepLink: string | null;
    private declare _oauthUrl: string | null;
    private declare _resendIn: number;
    private _pollTimer: number | undefined;
    private _resendTimer: number | undefined;
    private _oauthMsgHandler: ((ev: MessageEvent) => void) | undefined;
    private readonly _schemeMql = window.matchMedia('(prefers-color-scheme: dark)');
    private readonly _escHandler = (e: KeyboardEvent) => {
        if (e.key === 'Escape') this.close();
    };
    private readonly _onSchemeChange = () => {
        this._resolvedTheme = this._resolveTheme();
    };

    constructor() {
        super();
        this.apiBase = '';
        this.companyId = '';
        this.locale = 'ru';
        this.colorScheme = 'auto';
        this._opened = false;
        this._resolvedTheme = 'light';
        this._step = 'phone';
        this._phone = '';
        this._methods = [];
        this._challenge = null;
        this._challengeId = '';
        this._code = '';
        this._error = '';
        this._busy = false;
        this._deepLink = null;
        this._oauthUrl = null;
        this._resendIn = 0;
    }

    override connectedCallback(): void {
        super.connectedCallback();
        // Возврат с mobile OAuth-redirect: флаг ставится перед уходом,
        // по возвращении сессия уже есть → лист сам завершит вход.
        if (storageGet(OAUTH_RESUME_KEY) === this.companyId) {
            storageRemove(OAUTH_RESUME_KEY);
            void this.open();
        }
    }

    static override styles = css`
        :host { display: contents; }

        .overlay {
            position: fixed; inset: 0; z-index: 100000;
            background: rgba(6, 7, 12, 0.52);
            backdrop-filter: blur(10px) saturate(150%);
            -webkit-backdrop-filter: blur(10px) saturate(150%);
            display: flex; align-items: flex-end; justify-content: center;
            animation: pca-fade 0.22s ease-out;
        }
        @media (min-width: 560px) { .overlay { align-items: center; padding: 24px; } }

        /*
         * Палитра листа — --pca-* на .sheet (переопределяются извне через :host
         * или [data-theme]); акцент наследует --accent/--on-accent витрины.
         * color-scheme листа повторяет тему — UA-контролы (input, autofill,
         * caret, скроллбар) рендерятся в правильной схеме и не «белеют».
         */
        .sheet {
            --pca-surface: var(--pca-surface-override, #ffffff);
            --pca-text: #17171d;
            --pca-muted: #696a76;
            --pca-line: rgba(22, 22, 32, 0.1);
            --pca-fill: rgba(22, 22, 32, 0.045);
            --pca-fill-strong: rgba(22, 22, 32, 0.09);
            --pca-accent: var(--accent, #4f6ef7);
            --pca-on-accent: var(--on-accent, #ffffff);
            --pca-danger: #d64545;
            --pca-success: #1c9e57;
            color-scheme: light;
            position: relative;
            width: 100%; max-width: 400px;
            background: var(--pca-surface); color: var(--pca-text);
            border-radius: 28px 28px 0 0;
            padding: 12px 24px calc(26px + env(safe-area-inset-bottom));
            font-family: ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
            box-shadow: 0 -16px 56px rgba(0, 0, 0, 0.32);
            max-height: min(88vh, 720px); overflow-y: auto;
            animation: pca-rise 0.34s cubic-bezier(0.32, 0.72, 0.24, 1);
            -webkit-tap-highlight-color: transparent;
        }
        .sheet[data-theme='dark'] {
            --pca-surface: var(--pca-surface-override, #17171c);
            --pca-text: #f4f4f8;
            --pca-muted: #9c9ca8;
            --pca-line: rgba(255, 255, 255, 0.1);
            --pca-fill: rgba(255, 255, 255, 0.055);
            --pca-fill-strong: rgba(255, 255, 255, 0.1);
            color-scheme: dark;
        }
        @media (min-width: 560px) {
            .sheet { border-radius: 28px; animation-name: pca-pop; }
        }
        @keyframes pca-fade { from { opacity: 0; } }
        @keyframes pca-rise { from { transform: translateY(56px); opacity: 0.4; } }
        @keyframes pca-pop { from { transform: translateY(14px) scale(0.965); opacity: 0; } }
        @keyframes pca-step { from { opacity: 0; transform: translateY(6px); } }
        @media (prefers-reduced-motion: reduce) {
            .overlay, .sheet, .step { animation: none; }
        }

        .grab {
            width: 40px; height: 5px; border-radius: 99px;
            background: var(--pca-fill-strong); margin: 0 auto 16px;
        }
        @media (min-width: 560px) { .grab { display: none; } }
        .sheet h2 {
            margin: 0; font-size: 20px; font-weight: 720; letter-spacing: -0.02em;
        }
        .sheet p.sub {
            margin: 6px 0 18px; font-size: 14px;
            color: var(--pca-muted); line-height: 1.4;
        }
        .x {
            position: absolute; top: 14px; right: 14px;
            width: 34px; height: 34px; border: 0; border-radius: 50%;
            background: var(--pca-fill); color: var(--pca-muted);
            cursor: pointer; display: grid; place-items: center;
            transition: background 0.15s, color 0.15s;
        }
        .x:hover { background: var(--pca-fill-strong); color: var(--pca-text); }
        .x svg { width: 14px; height: 14px; }

        .step { animation: pca-step 0.26s cubic-bezier(0.32, 0.72, 0.24, 1); }

        /* :host input (0,1,1) — наравне с baseStyles, чтобы font:inherit не съел кегль */
        :host input {
            width: 100%; box-sizing: border-box;
            font-size: 16px; font-weight: 500; letter-spacing: 0.01em;
            padding: 15px 16px;
            border: 1.5px solid var(--pca-line); border-radius: 16px;
            background: var(--pca-fill); color: var(--pca-text);
            outline: none; appearance: none; -webkit-appearance: none;
            caret-color: var(--pca-accent);
            transition: border-color 0.15s, box-shadow 0.15s, background 0.15s;
        }
        :host input::placeholder { color: var(--pca-muted); opacity: 0.7; font-weight: 400; }
        :host input:focus {
            border-color: var(--pca-accent); background: var(--pca-surface);
            box-shadow: 0 0 0 4px color-mix(in srgb, var(--pca-accent) 20%, transparent);
        }
        :host input.otp {
            text-align: center; font-size: 22px; font-weight: 650;
            letter-spacing: 0.3em; padding-left: 22px;
        }
        :host input:-webkit-autofill,
        :host input:-webkit-autofill:hover,
        :host input:-webkit-autofill:focus {
            -webkit-text-fill-color: var(--pca-text);
            -webkit-box-shadow: 0 0 0 1000px var(--pca-fill) inset;
            transition: background-color 9999s ease-out;
        }

        button.primary {
            width: 100%; margin-top: 14px; padding: 16px;
            font-size: 16px; font-weight: 650; letter-spacing: 0.01em;
            border: 0; border-radius: 16px;
            background: var(--pca-accent); color: var(--pca-on-accent);
            cursor: pointer;
            box-shadow: 0 8px 22px color-mix(in srgb, var(--pca-accent) 30%, transparent);
            transition: transform 0.12s, box-shadow 0.18s, filter 0.15s;
        }
        button.primary:hover:not(:disabled) {
            transform: translateY(-1px);
            box-shadow: 0 10px 28px color-mix(in srgb, var(--pca-accent) 42%, transparent);
        }
        button.primary:active:not(:disabled) { transform: translateY(0) scale(0.985); }
        button.primary:disabled { opacity: 0.55; box-shadow: none; cursor: default; }

        button.method {
            display: flex; align-items: center; gap: 12px; width: 100%;
            padding: 12px 14px; margin-top: 10px;
            font-size: 15px; font-weight: 600;
            border: 1.5px solid var(--pca-line); border-radius: 16px;
            background: var(--pca-fill); color: var(--pca-text);
            cursor: pointer; text-align: left;
            transition: border-color 0.15s, transform 0.12s, box-shadow 0.15s, background 0.15s;
        }
        button.method:hover:not(:disabled) {
            border-color: var(--mcolor, var(--pca-accent));
            background: var(--pca-surface);
            transform: translateY(-1px);
            box-shadow: 0 6px 18px rgba(0, 0, 0, 0.12);
        }
        button.method:active:not(:disabled) { transform: translateY(0); }
        button.method:disabled { opacity: 0.55; cursor: default; }
        .mico {
            flex: 0 0 36px; height: 36px; border-radius: 12px;
            display: flex; align-items: center; justify-content: center;
            color: #fff; font-size: 12px; font-weight: 750; letter-spacing: -0.3px;
            background: var(--mcolor, #8a8a99);
        }
        .marrow { margin-left: auto; color: var(--pca-muted); display: flex; }
        .marrow svg { width: 16px; height: 16px; }

        .qrwrap { text-align: center; margin: 8px 0 4px; }
        .qr {
            width: 190px; height: 190px; border-radius: 16px;
            border: 1px solid var(--pca-line); background: #fff; padding: 10px;
        }
        .qrcap { font-size: 13px; color: var(--pca-muted); margin: 10px 0 4px; }

        button.ghost {
            width: 100%; margin-top: 8px; padding: 12px;
            font-size: 14px; font-weight: 600;
            border: 0; border-radius: 12px;
            background: transparent; color: var(--pca-muted); cursor: pointer;
            transition: color 0.15s, background 0.15s;
        }
        button.ghost:hover { color: var(--pca-text); background: var(--pca-fill); }

        .err { margin-top: 12px; font-size: 13.5px; line-height: 1.35; color: var(--pca-danger); }
        .err:empty { margin-top: 0; }
        .hint {
            font-size: 13.5px; color: var(--pca-muted);
            line-height: 1.4; margin-top: 12px; text-align: center;
        }
        .spinner {
            width: 22px; height: 22px;
            border: 2.5px solid var(--pca-line); border-top-color: var(--pca-accent);
            border-radius: 50%;
            animation: pca-spin 0.8s linear infinite; margin: 18px auto;
        }
        @keyframes pca-spin { to { transform: rotate(360deg); } }
        .ok {
            display: flex; align-items: center; justify-content: center; gap: 8px;
            font-size: 15px; font-weight: 650; color: var(--pca-success);
            margin: 16px 0 4px;
        }
        .ok svg { width: 20px; height: 20px; flex: 0 0 20px; }

        button.primary:focus-visible,
        button.method:focus-visible,
        button.ghost:focus-visible,
        .x:focus-visible {
            outline: 2px solid var(--pca-accent); outline-offset: 2px;
        }
    `;

    private _t(key: string): string {
        const pair: { ru: string; en: string } = T[key] ?? { ru: 'Error', en: 'Error' };
        return this.locale.startsWith('en') ? pair.en : pair.ru;
    }

    private _emit(type: string, detail: unknown = null): void {
        this.emit(type, detail);
    }

    /** Открыть лист: если сессия уже есть — сразу `customer-authenticated`. */
    async open(): Promise<void> {
        this._opened = true;
        this._resolvedTheme = this._resolveTheme();
        window.addEventListener('keydown', this._escHandler);
        this._schemeMql.addEventListener('change', this._onSchemeChange);
        this._error = '';
        // 401 /me для анонима — штатный путь, не ошибка для показа.
        const me = await this._fetch<CustomerMe>('me', undefined, 'GET', false);
        if (me) {
            this._confirm(me);
            return;
        }
        this._step = 'phone';
    }

    close(cancelled = true): void {
        this._opened = false;
        this._stopPoll();
        window.removeEventListener('keydown', this._escHandler);
        this._schemeMql.removeEventListener('change', this._onSchemeChange);
        if (cancelled) this._emit('customer-auth-cancelled');
    }

    override updated(changed: Map<string, unknown>): void {
        if (changed.has('colorScheme')) this._resolvedTheme = this._resolveTheme();
        super.updated(changed);
    }

    /*
     * `theme="light|dark"` — явно; `auto` (default): унаследованный
     * `color-scheme` витрины (forced тема), иначе prefers-color-scheme.
     */
    private _resolveTheme(): 'light' | 'dark' {
        if (this.colorScheme === 'light' || this.colorScheme === 'dark')
            return this.colorScheme;
        const scheme = getComputedStyle(this).colorScheme.trim();
        if (scheme === 'dark') return 'dark';
        if (scheme === 'light') return 'light';
        return this._schemeMql.matches ? 'dark' : 'light';
    }

    private async _fetch<T>(
        path: string,
        body?: unknown,
        method = 'POST',
        showError = true,
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
                if (showError) {
                    const detail = (await resp.json().catch(() => null))?.detail;
                    this._error = this._t(ERROR_KEYS[detail] ?? 'error_generic');
                }
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
        if (method.ui === 'auto' && method.provider) {
            // Авто-подтверждение (dev-эмулятор): direct-proof из введённого номера.
            await this._verifyDirect(method.provider);
            return;
        }
        if (view.status === 'challenge_sent') {
            this._step = 'code';
            this._startResendCountdown(view.resend_after);
        } else {
            this._step = view.status === 'awaiting_oauth' ? 'awaiting_oauth' : 'awaiting_contact';
            if (view.status === 'awaiting_oauth' && view.oauth_url) {
                this._oauthUrl = view.oauth_url;
                if (this._isDesktop()) {
                    this._openOauthPopup(view.oauth_url);
                } else {
                    // Мобильный flow — полный redirect; флаг вернёт юзера в лист.
                    storageSet(OAUTH_RESUME_KEY, this.companyId);
                    window.location.href = view.oauth_url;
                    return;
                }
            }
            this._pollStatus();
        }
    }

    private _isDesktop(): boolean {
        return window.matchMedia('(min-width: 560px)').matches;
    }

    /** OAuth в popup: closer-страница шлёт postMessage → опрашиваем /status. */
    private _openOauthPopup(url: string): void {
        const w = 540;
        const h = 720;
        const left = Math.max(0, (window.screen.width - w) / 2);
        const top = Math.max(0, (window.screen.height - h) / 2);
        const popup = window.open(
            url,
            'customer-auth',
            `width=${w},height=${h},left=${left},top=${top},popup=yes`,
        );
        if (!popup) {
            // popup заблокирован — деградируем в redirect с resume-флагом.
            storageSet(OAUTH_RESUME_KEY, this.companyId);
            window.location.href = url;
            return;
        }
        if (this._oauthMsgHandler) {
            window.removeEventListener('message', this._oauthMsgHandler);
        }
        this._oauthMsgHandler = (ev: MessageEvent) => {
            const data = ev.data as { type?: string } | null;
            if (data && data.type === 'customer-auth-done') {
                window.removeEventListener('message', this._oauthMsgHandler!);
                this._oauthMsgHandler = undefined;
                void this._pollStatus();
            }
        };
        window.addEventListener('message', this._oauthMsgHandler);
    }

    private async _verifyDirect(provider: string): Promise<void> {
        this._step = 'awaiting_contact';
        this._busy = true;
        const view = await this._fetch<{ status: string; customer?: CustomerMe }>(
            'verify',
            {
                challenge_id: this._challengeId,
                company_id: this.companyId,
                direct: {
                    kind: 'contact_share',
                    provider,
                    contact_phone: this._phone.trim() || null,
                },
            },
        );
        this._busy = false;
        if (view?.status === 'confirmed' && view.customer) {
            this._confirm(view.customer);
        } else {
            this._step = 'methods';
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
        if (this._oauthMsgHandler) {
            window.removeEventListener('message', this._oauthMsgHandler);
            this._oauthMsgHandler = undefined;
        }
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
        window.removeEventListener('keydown', this._escHandler);
        this._schemeMql.removeEventListener('change', this._onSchemeChange);
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
                <div class="sheet" data-theme=${this._resolvedTheme}
                     role="dialog" aria-modal="true">
                    <div class="grab"></div>
                    <button class="x" aria-label=${this._t('close')}
                            @click=${() => this.close()}>
                        <svg viewBox="0 0 14 14" fill="none">
                            <path d="M3 3l8 8M11 3l-8 8" stroke="currentColor"
                                  stroke-width="1.8" stroke-linecap="round" />
                        </svg>
                    </button>
                    <h2>${this._t('title')}</h2>
                    <p class="sub">${this._t('subtitle')}</p>
                    ${this._step === 'phone' ? html`
                        <div class="step">
                            <input type="tel" inputmode="tel" autocomplete="tel"
                                   .value=${this._phone}
                                   placeholder=${this._t('phone_placeholder')}
                                   @input=${(e: InputEvent) =>
                                       (this._phone = (e.target as HTMLInputElement).value)}
                                   @keydown=${(e: KeyboardEvent) =>
                                       e.key === 'Enter' && this._start()} />
                            <button class="primary" ?disabled=${busy}
                                    @click=${this._start}>${this._t('continue')}</button>
                        </div>
                    ` : nothing}
                    ${this._step === 'methods' ? html`
                        <div class="step">
                            <p class="sub">${this._t('choose_method')}</p>
                            ${this._methods.map((m) => {
                                const brand = BRAND[m.kind] ?? { color: '#8a8a99', glyph: '?' };
                                return html`
                                    <button class="method" ?disabled=${busy}
                                            style="--mcolor: ${brand.color}"
                                            @click=${() => this._choose(m)}>
                                        <span class="mico">${brand.glyph}</span>
                                        <span>${this._methodLabel(m.kind)}</span>
                                        <span class="marrow">
                                            <svg viewBox="0 0 16 16" fill="none">
                                                <path d="M6 3.5 10.5 8 6 12.5" stroke="currentColor"
                                                      stroke-width="1.8" stroke-linecap="round"
                                                      stroke-linejoin="round" />
                                            </svg>
                                        </span>
                                    </button>`;
                            })}
                            <button class="ghost" @click=${() => (this._step = 'phone')}>
                                ${this._t('back')}
                            </button>
                        </div>
                    ` : nothing}
                    ${this._step === 'code' ? html`
                        <div class="step">
                            <p class="sub">${this._t('code_sent')}</p>
                            <input class="otp" type="text" inputmode="numeric"
                                   autocomplete="one-time-code"
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
                        </div>
                    ` : nothing}
                    ${this._step === 'awaiting_contact' ? html`
                        <div class="step">
                            <div class="spinner"></div>
                            <p class="hint">${this._t('waiting_contact')}</p>
                            ${this._deepLink ? html`
                                <div class="qrwrap">
                                    ${this._isDesktop() ? html`
                                        <img class="qr" alt="QR"
                                             src="${this.apiBase}/deeplink-qr.svg?u=${encodeURIComponent(this._deepLink)}" />
                                        <p class="qrcap">${this._t('scan_qr')}</p>` : nothing}
                                    <button class="primary" @click=${() =>
                                        window.open(this._deepLink!, '_blank')}>
                                        ${this._t('open_app')}
                                    </button>
                                </div>` : nothing}
                            <button class="ghost" @click=${() => { this._stopPoll(); this._step = 'methods'; }}>
                                ${this._t('back')}
                            </button>
                        </div>
                    ` : nothing}
                    ${this._step === 'awaiting_oauth' ? html`
                        <div class="step">
                            <div class="spinner"></div>
                            <p class="hint">${this._t('waiting_oauth')}</p>
                            ${this._oauthUrl ? html`
                                <button class="ghost" @click=${() =>
                                    this._openOauthPopup(this._oauthUrl!)}>
                                    ${this._t('open_again')}
                                </button>` : nothing}
                            <button class="ghost" @click=${() => { this._stopPoll(); this._step = 'methods'; }}>
                                ${this._t('back')}
                            </button>
                        </div>
                    ` : nothing}
                    ${this._step === 'done' ? html`
                        <div class="step">
                            <p class="ok">
                                <svg viewBox="0 0 20 20" fill="none">
                                    <circle cx="10" cy="10" r="9" stroke="currentColor"
                                            stroke-width="1.6" />
                                    <path d="M6.4 10.2 8.9 12.7 13.8 7.6" stroke="currentColor"
                                          stroke-width="1.8" stroke-linecap="round"
                                          stroke-linejoin="round" />
                                </svg>
                                ${this._t('done')}
                            </p>
                        </div>
                    ` : nothing}
                    <div class="err">${this._error}</div>
                </div>
            </div>`;
    }
}

if (!customElements.get('platform-customer-auth')) {
    customElements.define('platform-customer-auth', PlatformCustomerAuth);
}
