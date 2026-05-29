/**
 * Ориентировочный калькулятор экономического эффекта (иллюстративная модель).
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { formatPlatformNumber } from '@platform/lib/utils/format-platform-number.js';

function _clamp(n, lo, hi) {
    return Math.min(hi, Math.max(lo, n));
}

export class LandingRoiCalculator extends PlatformElement {
    static i18nNamespace = 'landing';

    static properties = {
        _headcount: { state: true, type: Number },
        _monthlySpendRub: { state: true, type: Number },
    };

    static styles = [
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
                border: 1px solid var(--landing-panel-border, rgba(255, 255, 255, 0.12));
                background: radial-gradient(circle at top right, rgba(87, 104, 254, 0.18), var(--landing-panel-bg-strong, rgba(15, 15, 15, 0.95)));
            }
            h2 {
                font-family: 'Fira Sans Condensed', sans-serif;
                font-size: clamp(26px, 3.5vw, 36px);
                margin: 0 0 12px;
                color: var(--landing-secondary, #e8e8e8);
            }
            .sub {
                margin: 0 0 32px;
                font-size: 15px;
                color: var(--landing-text-subtle, rgba(232, 232, 232, 0.72));
                line-height: 1.5;
            }
            .field {
                margin-bottom: 24px;
            }
            label {
                display: flex;
                justify-content: space-between;
                align-items: baseline;
                font-family: 'Fira Sans', sans-serif;
                font-size: 14px;
                color: var(--landing-secondary, #e8e8e8);
                margin-bottom: 10px;
            }
            .value {
                font-weight: 600;
                color: var(--landing-primary, #5768fe);
            }
            input[type='range'] {
                width: 100%;
                accent-color: var(--landing-primary, #5768fe);
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
                background: var(--landing-panel-bg, rgba(0, 0, 0, 0.35));
                border: 1px solid var(--landing-panel-border, rgba(255, 255, 255, 0.08));
            }
            .tile span {
                display: block;
                font-size: 12px;
                text-transform: uppercase;
                letter-spacing: 0.04em;
                color: var(--landing-text-faint, rgba(232, 232, 232, 0.55));
                margin-bottom: 6px;
            }
            .tile strong {
                font-family: 'Fira Sans Condensed', sans-serif;
                font-size: 22px;
                color: var(--landing-secondary, #e8e8e8);
            }
            .disclaimer {
                margin-top: 24px;
                font-size: 12px;
                line-height: 1.45;
                color: var(--landing-text-faint, rgba(232, 232, 232, 0.5));
            }
        `,
    ];

    constructor() {
        super();
        this._headcount = 200;
        this._monthlySpendRub = 800000;
        this._localeSel = this.select((s) => {
            const loc = s.i18n && typeof s.i18n.locale === 'string' ? s.i18n.locale.trim() : '';
            if (loc.length > 0) {
                return loc;
            }
            return 'en';
        });
    }

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

    _formatRub(n) {
        const raw = this._localeSel.value;
        const locale = typeof raw === 'string' && raw.length > 0 ? raw : 'en';
        const formatted = formatPlatformNumber(n, locale);
        return `${formatted} ${this.t('roi.currency_rub')}`;
    }

    render() {
        const t = (key) => this.t(key);
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
                        @input=${(e) => {
                            this._headcount = Number(e.target.value);
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
                        @input=${(e) => {
                            this._monthlySpendRub = Number(e.target.value);
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
