/**
 * Плавающий CTA на лендинге: ссылка в Telegram после таймера или скролла.
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import type {CSSResultGroup, PropertyDeclarations, TemplateResult} from 'lit';
import type { OpController } from '@platform/lib/base/use-resource.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';

const SHOW_AFTER_MS = 30_000;
const SHOW_AFTER_SCROLL_Y = 480;

export class LandingFloatingCta extends PlatformElement {
    static i18nNamespace = 'landing';

    static override properties: PropertyDeclarations = {
        _visible: { state: true, type: Boolean },
        _dismissed: { state: true, type: Boolean },
        _telegramUrl: { state: true, type: String },
        _timerElapsed: { state: true, type: Boolean },
    }
    declare _visible: boolean;
    declare _dismissed: boolean;
    declare _telegramUrl: string;
    declare _timerElapsed: boolean;
;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
            }
            .bar {
                position: fixed;
                right: 16px;
                bottom: 16px;
                left: 16px;
                z-index: 12000;
                max-width: 420px;
                margin-left: auto;
                padding: 14px 16px;
                border-radius: 16px;
                border: 1px solid var(--glass-border-strong);
                background: var(--glass-solid-strong);
                backdrop-filter: blur(12px);
                display: flex;
                flex-direction: column;
                gap: 10px;
                box-shadow: var(--glass-shadow-strong);
            }
            .row {
                display: flex;
                align-items: flex-start;
                justify-content: space-between;
                gap: 12px;
            }
            .text {
                font-family: var(--font-sans);
                font-size: 15px;
                line-height: 1.45;
                color: var(--text-secondary);
                margin: 0;
            }
            .actions {
                display: flex;
                flex-wrap: wrap;
                gap: 10px;
                align-items: center;
            }
            a.tg {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                padding: 10px 18px;
                border-radius: 999px;
                background: var(--marketing-product-accent);
                color: var(--text-on-accent);
                font-family: var(--font-sans);
                font-size: 14px;
                font-weight: 600;
                text-decoration: none;
            }
            button.dismiss {
                border: none;
                background: transparent;
                color: var(--text-secondary);
                font-family: var(--font-sans);
                font-size: 13px;
                cursor: pointer;
                text-decoration: underline;
                padding: 0;
            }
        `,
    ];

    constructor() {
        super();
        this._visible = false;
        this._dismissed = false;
        this._telegramUrl = '';
        this._timerElapsed = false;
        this._bundleOp = this.useOp('frontend/public_site_bundle');
        this._timerId = null;
        this._onScroll = this._onScroll.bind(this);
    }
    private _bundleOp: OpController;
    private _timerId: number | null = null;


    override connectedCallback(): void {
        super.connectedCallback();
        if (typeof window === 'undefined') return;
        this.useDomEvent(window, 'scroll', this._onScroll, { passive: true });
        this._timerId = window.setTimeout(() => {
            this._timerElapsed = true;
            this._timerId = null;
            this._tryShow();
        }, SHOW_AFTER_MS);
        void this._loadTelegramUrl();
    }

    override disconnectedCallback(): void {
        super.disconnectedCallback();
        if (typeof window === 'undefined') return;
        if (this._timerId !== null) {
            window.clearTimeout(this._timerId);
            this._timerId = null;
        }
    }

    async _loadTelegramUrl() {
        const res = await this._bundleOp.run(null);
        if (!isPlainRecord(res)) return;
        const marketing = res.marketing;
        if (!isPlainRecord(marketing)) {
            throw new Error('landing-floating-cta: marketing missing');
        }
        const url = marketing.telegram_community_url;
        if (typeof url !== 'string' || url === '') return;
        this._telegramUrl = url;
        this._tryShow();
    }

    _onScroll() {
        this._tryShow();
    }

    _tryShow() {
        if (this._dismissed) return;
        if (this._telegramUrl === '') return;
        if (typeof window === 'undefined') return;
        const scrolled = window.scrollY >= SHOW_AFTER_SCROLL_Y;
        if (scrolled || this._timerElapsed) {
            this._visible = true;
        }
    }

    override render(): TemplateResult {
        if (!this._visible || this._dismissed || this._telegramUrl === '') {
            return html``;
        }
        return html`
            <div class="bar" role="dialog" aria-live="polite">
                <div class="row">
                    <p class="text">${this.t('floating_cta.text')}</p>
                    <button type="button" class="dismiss" @click=${() => { this._dismissed = true; }}>
                        ${this.t('floating_cta.dismiss')}
                    </button>
                </div>
                <div class="actions">
                    <a class="tg" href=${this._telegramUrl} target="_blank" rel="noopener noreferrer">
                        ${this.t('footer.telegram')}
                    </a>
                </div>
            </div>
        `;
    }
}

customElements.define('landing-floating-cta', LandingFloatingCta);
