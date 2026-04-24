/**
 * dashboard-service-card — пресентейшнл-карточка одного сервиса:
 * бренд-градиентный «холст», крупное лого, заголовок/описание,
 * нижний бар с метрикой и health-pill.
 *
 * Никаких подписок на state и HTTP — только props.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

const HEALTH_TONES = {
    healthy: 'var(--success)',
    unhealthy: 'var(--error)',
    loading: 'var(--text-tertiary)',
};

export class DashboardServiceCard extends PlatformElement {
    static i18nNamespace = 'frontend';

    static properties = {
        svcId: { type: String, attribute: 'svc-id' },
        nameKey: { type: String, attribute: 'name-key' },
        descriptionKey: { type: String, attribute: 'description-key' },
        logoSrc: { type: String, attribute: 'logo-src' },
        href: { type: String },
        brandFrom: { type: String, attribute: 'brand-from' },
        brandTo: { type: String, attribute: 'brand-to' },
        metricValue: { type: String, attribute: 'metric-value' },
        healthState: { type: String, attribute: 'health-state' },
        latencyMs: { type: Number, attribute: 'latency-ms' },
        disabled: { type: Boolean },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; }
            .card {
                position: relative;
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
                padding: var(--space-6);
                min-height: 220px;
                border-radius: var(--radius-2xl);
                color: inherit;
                background: var(--glass-solid-medium);
                backdrop-filter: blur(var(--glass-blur-medium));
                -webkit-backdrop-filter: blur(var(--glass-blur-medium));
                border: 1px solid var(--glass-border-medium);
                box-shadow: var(--glass-shadow-medium);
                overflow: hidden;
                isolation: isolate;
                transition: transform var(--duration-normal) var(--easing-default),
                            box-shadow var(--duration-normal) var(--easing-default);
            }
            a.card { text-decoration: none; }
            .card::before {
                content: '';
                position: absolute;
                inset: 0 0 auto 0;
                height: 4px;
                background: linear-gradient(90deg, var(--brand-from) 0%, var(--brand-to) 100%);
                pointer-events: none;
            }
            .card::after {
                content: '';
                position: absolute;
                inset: -40% -20% auto auto;
                width: 320px;
                height: 320px;
                background: radial-gradient(circle at 50% 50%, var(--brand-from), transparent 70%);
                opacity: 0.18;
                pointer-events: none;
                z-index: -1;
            }
            .card > * { position: relative; z-index: 1; }
            a.card:hover { transform: translateY(-4px); box-shadow: var(--glass-shadow-strong); }
            .card--disabled {
                cursor: not-allowed;
                pointer-events: none;
                opacity: 0.82;
            }
            .card--disabled:hover { transform: none; box-shadow: var(--glass-shadow-medium); }
            .head { display: flex; align-items: center; gap: var(--space-4); }
            .logo {
                width: 56px;
                height: 56px;
                flex-shrink: 0;
                border-radius: var(--radius-lg);
                background: linear-gradient(135deg,
                    color-mix(in srgb, var(--brand-from) 22%, transparent) 0%,
                    color-mix(in srgb, var(--brand-to) 22%, transparent) 100%);
                border: 1px solid var(--glass-border-subtle);
                display: flex;
                align-items: center;
                justify-content: center;
                padding: var(--space-2);
            }
            .logo img { width: 100%; height: 100%; }
            .title {
                font-size: var(--text-xl);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }
            .description {
                color: var(--text-secondary);
                font-size: var(--text-sm);
                line-height: 1.5;
                flex: 1;
            }
            .footer {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-3);
                padding-top: var(--space-3);
                border-top: 1px solid var(--glass-border-subtle);
            }
            .metric {
                font-size: var(--text-sm);
                color: var(--text-secondary);
                font-weight: var(--font-medium);
            }
            .health {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                padding: 4px var(--space-3);
                border-radius: var(--radius-full);
                background: color-mix(in srgb, var(--health-tone) 18%, transparent);
                color: var(--health-tone);
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
            }
            .health .dot {
                width: 8px;
                height: 8px;
                border-radius: 50%;
                background: var(--health-tone);
                box-shadow: 0 0 10px var(--health-tone);
            }
        `,
    ];

    constructor() {
        super();
        this.svcId = '';
        this.nameKey = '';
        this.descriptionKey = '';
        this.logoSrc = '';
        this.href = '';
        this.brandFrom = '#6366f1';
        this.brandTo = '#0ea5e9';
        this.metricValue = '';
        this.healthState = 'loading';
        this.latencyMs = 0;
        this.disabled = false;
    }

    _healthLabel() {
        if (this.healthState === 'healthy') {
            return this.t('console_home.stat_available');
        }
        if (this.healthState === 'unhealthy') {
            return this.t('console_home.stat_unavailable');
        }
        return this.t('console_home.stat_loading');
    }

    render() {
        const tone = HEALTH_TONES[this.healthState];
        const cardStyle = `--brand-from: ${this.brandFrom}; --brand-to: ${this.brandTo}; --health-tone: ${tone};`;
        const title = this.t(this.nameKey, null, 'platform');
        const description = this.t(this.descriptionKey, null, 'platform');
        const body = html`
                <div class="head">
                    <div class="logo"><img src=${this.logoSrc} alt=${title}></div>
                    <div class="title">${title}</div>
                </div>
                <div class="description">${description}</div>
                <div class="footer">
                    <span class="metric">${this.metricValue}</span>
                    <span class="health">
                        <span class="dot"></span>
                        <span>${this._healthLabel()}</span>
                    </span>
                </div>
        `;
        if (this.disabled) {
            return html`
            <div class="card card--disabled" aria-label=${title} style=${cardStyle}>
                ${body}
            </div>`;
        }
        return html`
            <a class="card" href=${this.href} aria-label=${title} style=${cardStyle}>
                ${body}
            </a>
        `;
    }
}

customElements.define('dashboard-service-card', DashboardServiceCard);
