/**
 * Ориентировочный калькулятор экономического эффекта (иллюстративная модель).
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { formatPlatformNumber } from '@platform/lib/utils/format-platform-number.js';
import type {CSSResultGroup, PropertyDeclarations, TemplateResult} from 'lit';
import type { SelectController } from '@platform/lib/events/select-controller.js';

function _clamp(n: number, lo: number, hi: number) {
    return Math.min(hi, Math.max(lo, n));
}

function rangeValue(event: Event): number {
    const input = event.target;
    if (!(input instanceof HTMLInputElement)) {
        throw new Error('landing-roi-calculator: range input required');
    }
    return Number(input.value);
}

export class LandingRoiCalculator extends PlatformElement {
    static i18nNamespace = 'landing';

    static override properties: PropertyDeclarations = {
        _headcount: { state: true, type: Number },
        _monthlySpendRub: { state: true, type: Number },
    }
    declare _headcount: number;
    declare _monthlySpendRub: number;
;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                padding: 80px 20px;
            }
            .wrap {
                max-width: 900px;
                margin: 0 auto;
                padding: 40px 28px;
                border-radius: 24px;
                border: 1px solid var(--glass-border-medium);
                background: radial-gradient(circle at top right, color-mix(in srgb, var(--accent) 18%, transparent), var(--glass-bg-medium));
            }
            h2 {
                font-family: var(--font-sans); letter-spacing: var(--tracking-tight);
                font-size: clamp(26px, 3.5vw, 36px);
                margin: 0 0 12px;
                color: var(--text-secondary);
            }
            .sub {
                margin: 0 0 32px;
                font-size: 15px;
                color: var(--text-secondary);
                line-height: 1.5;
            }
            .field {
                margin-bottom: 24px;
            }
            label {
                display: flex;
                justify-content: space-between;
                align-items: baseline;
                font-family: var(--font-sans);
                font-size: 14px;
                color: var(--text-secondary);
                margin-bottom: 10px;
            }
            .value {
                font-weight: 600;
                color: var(--marketing-product-accent);
            }
            input[type='range'] {
                width: 100%;
                accent-color: var(--marketing-product-accent);
            }
            .results {
                display: grid;
                grid-template-columns: 1fr;
                gap: 16px;
                margin-top: 28px;
            }
            @media (min-width: 640px) {
                .results {
                    grid-template-columns: repeat(2, 1fr);
                }
            }
            .tile {
                padding: 16px 18px;
                border-radius: 16px;
                background: var(--glass-bg-subtle);
                border: 1px solid var(--glass-border-medium);
            }
            .tile span {
                display: block;
                font-size: 12px;
                text-transform: uppercase;
                letter-spacing: 0.04em;
                color: var(--text-disabled);
                margin-bottom: 6px;
            }
            .tile strong {
                font-family: var(--font-sans); letter-spacing: var(--tracking-tight);
                font-size: 22px;
                color: var(--text-secondary);
            }
            .disclaimer {
                margin-top: 24px;
                font-size: 12px;
                line-height: 1.45;
                color: var(--text-disabled);
            }
        `,
    ];

    constructor() {
        super();
        this._headcount = 200;
        this._monthlySpendRub = 800000;
        this._localeSel = this.select((s: Record<string, unknown>) => {
            const loc = s.i18n && typeof s.i18n.locale === 'string' ? s.i18n.locale.trim() : '';
            if (loc.length > 0) {
                return loc;
            }
            return 'en';
        });
    }
    private _localeSel: SelectController<any>;


    _compute() {
        const hc = _clamp(this._headcount, 50, 2000);
        const spend = _clamp(this._monthlySpendRub, 100000, 50000000);
        const scaleHc = hc / 200;
        const scaleSpend = spend / 800000;
        const yearlySaving = Math.round(20000000 * scaleHc * scaleSpend);
        const investment = Math.round(5000000 * scaleHc);
        const roiPct = investment > 0 ? Math.round(((yearlySaving - investment) / investment) * 100) : 0;
        const paybackMonths =
            yearlySaving > 0 ? Math.max(1, Math.round(investment / (yearlySaving / 12))) : 0;
        return { yearlySaving, investment, roiPct, paybackMonths };
    }

    _formatRub(n: number) {
        const raw = this._localeSel.value;
        const locale = typeof raw === 'string' && raw.length > 0 ? raw : 'en';
        const formatted = formatPlatformNumber(n, locale);
        return `${formatted} ${this.t('roi.currency_rub')}`;
    }

    override render(): TemplateResult {
        const t = (key: string) => this.t(key);
        const { yearlySaving, investment, roiPct, paybackMonths } = this._compute();
        return html`
            <section class="wrap" aria-labelledby="landing-roi-heading">
                <h2 id="landing-roi-heading">${t('roi.title')}</h2>
                <p class="sub">${t('roi.subtitle')}</p>
                <div class="field">
                    <label>
                        <span>${t('roi.headcount_label')}</span>
                        <span class="value">${this._headcount}</span>
                    </label>
                    <input
                        type="range"
                        min="50"
                        max="2000"
                        step="10"
                        .value=${String(this._headcount)}
                        @input=${(e: Event) => {
                            this._headcount = rangeValue(e);
                        }}
                    />
                </div>
                <div class="field">
                    <label>
                        <span>${t('roi.monthly_spend_label')}</span>
                        <span class="value">${this._formatRub(this._monthlySpendRub)}</span>
                    </label>
                    <input
                        type="range"
                        min="100000"
                        max="50000000"
                        step="50000"
                        .value=${String(this._monthlySpendRub)}
                        @input=${(e: Event) => {
                            this._monthlySpendRub = rangeValue(e);
                        }}
                    />
                </div>
                <div class="results">
                    <div class="tile">
                        <span>${t('roi.yearly_savings')}</span>
                        <strong>${this._formatRub(yearlySaving)}</strong>
                    </div>
                    <div class="tile">
                        <span>${t('roi.investment')}</span>
                        <strong>${this._formatRub(investment)}</strong>
                    </div>
                    <div class="tile">
                        <span>${t('roi.roi_percent')}</span>
                        <strong>${roiPct}%</strong>
                    </div>
                    <div class="tile">
                        <span>${t('roi.payback_months')}</span>
                        <strong>${paybackMonths}</strong>
                    </div>
                </div>
                <p class="disclaimer">${t('roi.disclaimer')}</p>
            </section>
        `;
    }
}

customElements.define('landing-roi-calculator', LandingRoiCalculator);
