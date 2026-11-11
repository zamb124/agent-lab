/**
 * Вход оператора ТСД: «отсканируйте бейдж» всем экраном.
 *
 * Аппаратный сканер и ручной ввод идут в `stock/operator_login` → общий
 * `POST /auth/login/badge` (платформенный вход по бейджу): ответ ставит
 * session-куки, после чего страница перезагружается — шина поднимается
 * уже с настоящей сессией сотрудника.
 */

import { html, css } from 'lit';
import type { TemplateResult } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import type { ControllerFor } from '@platform/lib/base/use-resource.js';
import { TsdScanInput } from './scan/scan-input.js';
import { tsdScanFeedback } from './scan/scan-feedback.js';
import { tsdCameraScanSupported } from './scan/scan-camera.js';
import './scan/scan-camera.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-spinner.js';

export class StockTsdLoginPage extends PlatformPage {
    static i18nNamespace = 'stock_tsd';

    private _login: ControllerFor<'stock/operator_login'>;
    private _scanInput: TsdScanInput | null = null;
    private _error = '';
    private _busy = false;
    private _cameraOpen = false;
    private readonly _cameraSupported = tsdCameraScanSupported();

    static override styles = [
        PlatformPage.styles,
        css`
            :host { display: block; height: 100%; }
            .wrap {
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                gap: var(--space-6);
                min-height: 100%;
                padding: var(--space-6);
                box-sizing: border-box;
                text-align: center;
            }
            .badge-hero {
                display: flex;
                align-items: center;
                justify-content: center;
                width: 120px;
                height: 120px;
                border-radius: 50%;
                background: var(--accent-subtle);
                color: var(--accent);
            }
            h1 {
                margin: 0;
                font-size: var(--tsd-text-hero);
                font-weight: var(--font-bold);
                color: var(--text-primary);
            }
            .sub {
                margin: 0;
                font-size: var(--tsd-text-body);
                color: var(--text-secondary);
                max-width: 480px;
            }
            .manual {
                display: flex;
                gap: var(--space-3);
                width: min(100%, 480px);
            }
            .manual-input {
                flex: 1;
                min-height: var(--tsd-touch-min);
                padding: 0 var(--space-4);
                font-size: var(--tsd-text-body);
                border: 1px solid var(--border-default);
                border-radius: var(--radius-xl);
                background: var(--bg-surface);
                color: var(--text-primary);
                text-align: center;
            }
            .manual-btn {
                display: flex;
                align-items: center;
                justify-content: center;
                width: var(--tsd-touch-min);
                min-height: var(--tsd-touch-min);
                border: none;
                border-radius: var(--radius-xl);
                background: var(--accent);
                color: var(--text-inverse);
                cursor: pointer;
            }
            .manual-btn:disabled { opacity: 0.5; }
            .error {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-3) var(--space-5);
                border-radius: var(--radius-xl);
                background: var(--tsd-error-subtle);
                color: var(--tsd-error);
                font-size: var(--tsd-text-body);
                font-weight: var(--font-semibold);
            }
        `,
    ];

    constructor() {
        super();
        this._login = this.useOp('stock/operator_login');
    }

    override connectedCallback(): void {
        super.connectedCallback();
        this._scanInput = new TsdScanInput((code) => void this._submit(code));
        this._scanInput.attach();
    }

    override disconnectedCallback(): void {
        this._scanInput?.detach();
        this._scanInput = null;
        super.disconnectedCallback();
    }

    private async _submit(code: string): Promise<void> {
        if (this._busy) return;
        this._busy = true;
        this._error = '';
        this.requestUpdate();
        try {
            const result = await this._login.run({ code });
            if (result === null) throw new Error('stock/operator_login: empty response');
            tsdScanFeedback('ok');
            window.location.reload();
        } catch {
            this._error = this.t('login.badge_rejected');
            tsdScanFeedback('error');
            this._busy = false;
            this.requestUpdate();
        }
    }

    override render(): TemplateResult {
        return html`
            <div class="wrap">
                <div class="badge-hero"><platform-icon name="user" size="56"></platform-icon></div>
                <h1>${this.t('login.title')}</h1>
                <p class="sub">${this.t('login.hint')}</p>
                ${this._busy
                    ? html`<platform-spinner size="l"></platform-spinner>`
                    : html`
                        <div class="manual">
                            <input
                                class="manual-input"
                                type="text"
                                data-canon="search-as-you-type"
                                autocomplete="off"
                                placeholder=${this.t('login.badge_placeholder')}
                                @keydown=${(e: KeyboardEvent) => {
                                    if (e.key === 'Enter') {
                                        const input = e.target as HTMLInputElement;
                                        void this._submit(input.value.trim());
                                        input.value = '';
                                    }
                                }}
                            >
                            ${this._cameraSupported ? html`
                                <button class="manual-btn" @click=${() => { this._cameraOpen = true; this.requestUpdate(); }}>
                                    <platform-icon name="qr-code" size="22"></platform-icon>
                                </button>
                            ` : ''}
                        </div>
                    `}
                ${this._error !== '' ? html`
                    <div class="error"><platform-icon name="close" size="20"></platform-icon>${this._error}</div>
                ` : ''}
            </div>
            <stock-tsd-camera-scanner
                ?active=${this._cameraOpen}
                @tsd-scan=${(e: CustomEvent<{ code: string }>) => { this._cameraOpen = false; void this._submit(e.detail.code); }}
                @tsd-scan-close=${() => { this._cameraOpen = false; }}
            ><span slot="error">${this.t('home.camera_error')}</span></stock-tsd-camera-scanner>
        `;
    }
}

customElements.define('stock-tsd-login-page', StockTsdLoginPage);
