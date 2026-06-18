import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-animated-number.js';

export class CrawlReportRunningBanner extends PlatformElement {
    static i18nNamespace = 'frontend';

    static properties = {
        runningJob: { type: Object },
        locale: { type: String },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; }
            .running-banner {
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-3);
                padding: var(--space-3) var(--space-4);
                margin-bottom: var(--space-4);
                border-radius: var(--radius-lg);
                border: 1px solid color-mix(in srgb, var(--accent) 35%, transparent);
                background: color-mix(in srgb, var(--accent) 8%, var(--glass-solid-subtle));
            }
            .running-banner-title {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }
            .running-banner-stats {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-3);
                font-size: var(--text-sm);
                color: var(--text-secondary);
                font-family: var(--font-mono);
            }
            .stat-item {
                display: inline-flex;
                align-items: baseline;
                gap: var(--space-1);
            }
            .pulse-dot {
                width: 8px;
                height: 8px;
                border-radius: var(--radius-full);
                background: var(--accent);
                animation: crawl-pulse 1.4s ease-in-out infinite;
            }
            @keyframes crawl-pulse {
                0%, 100% { opacity: 0.35; transform: scale(0.9); }
                50% { opacity: 1; transform: scale(1); }
            }
        `,
    ];

    constructor() {
        super();
        this.runningJob = null;
        this.locale = 'en';
    }

    _stat(labelKey, value) {
        return html`
            <span class="stat-item">
                <span>${this.t(labelKey)}</span>
                <platform-animated-number .value=${value} .locale=${this.locale}></platform-animated-number>
            </span>
        `;
    }

    render() {
        if (!this.runningJob) return null;
        return html`
            <div class="running-banner">
                <div class="running-banner-title">
                    <span class="pulse-dot"></span>
                    ${this.t('crawl_report_page.running_banner_title')}
                </div>
                <div class="running-banner-stats">
                    ${this._stat('crawl_report_page.running_stat_fetched', this.runningJob.urls_fetched)}
                    ${this._stat('crawl_report_page.running_stat_indexed', this.runningJob.urls_indexed)}
                    ${this._stat('crawl_report_page.running_stat_enriched', this.runningJob.urls_enriched)}
                    ${this._stat('crawl_report_page.running_stat_errors', this.runningJob.errors)}
                </div>
            </div>
        `;
    }
}

customElements.define('crawl-report-running-banner', CrawlReportRunningBanner);
