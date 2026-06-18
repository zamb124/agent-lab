import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-metric-card.js';

export class CrawlReportMetricStrip extends PlatformElement {
    static i18nNamespace = 'frontend';

    static properties = {
        summary: { type: Object },
        locale: { type: String },
        busy: { type: Boolean },
        refreshing: { type: Boolean },
        errorKind: { type: String },
        countFromSummary: { attribute: false },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; }
            .summary-grid {
                display: grid;
                grid-template-columns: repeat(4, minmax(0, 1fr));
                gap: var(--space-3);
                margin-bottom: var(--space-4);
                align-items: stretch;
            }
            @media (max-width: 1200px) {
                .summary-grid {
                    grid-template-columns: repeat(2, minmax(0, 1fr));
                }
            }
            @media (max-width: 640px) {
                .summary-grid {
                    grid-template-columns: repeat(2, minmax(0, 1fr));
                }
            }
            .initial-loading {
                padding: var(--space-4) 0;
                display: flex;
                justify-content: center;
            }
            .state {
                padding: var(--space-6);
                text-align: center;
                color: var(--text-tertiary);
            }
            .state-title {
                color: var(--text-primary);
                font-weight: var(--font-semibold);
            }
        `,
    ];

    constructor() {
        super();
        this.summary = null;
        this.locale = 'en';
        this.busy = false;
        this.refreshing = false;
        this.errorKind = '';
        this.countFromSummary = () => 0;
    }

    render() {
        if (this.errorKind === 'forbidden') {
            return html`
                <div class="state">
                    <div class="state-title">${this.t('crawl_report_page.forbidden')}</div>
                </div>
            `;
        }
        if (this.errorKind === 'unavailable') {
            return html`
                <div class="state">
                    <div class="state-title">${this.t('crawl_report_page.unavailable')}</div>
                </div>
            `;
        }
        if (!this.summary && this.busy) {
            return html`<div class="initial-loading"><glass-spinner size="sm"></glass-spinner></div>`;
        }
        if (!this.summary) {
            return null;
        }
        const dueCount = this.countFromSummary('domains_due');
        const fetchingCount = this.countFromSummary('url_fetching');
        const failedCount = this.countFromSummary('url_failed');
        const enrichedTotal = this.summary.urls_enriched_total ?? 0;
        const enrichmentPending = this.summary.urls_enrichment_pending ?? 0;
        return html`
            <div class="summary-grid">
                <platform-metric-card
                    label=${this.t('crawl_report_page.domains_total')}
                    .value=${this.countFromSummary('domains_total')}
                    .locale=${this.locale}
                    .refreshing=${this.refreshing}
                ></platform-metric-card>
                <platform-metric-card
                    label=${this.t('crawl_report_page.domains_due')}
                    .value=${dueCount}
                    .locale=${this.locale}
                    tone=${dueCount > 0 ? 'accent' : ''}
                    .refreshing=${this.refreshing}
                ></platform-metric-card>
                <platform-metric-card
                    label=${this.t('crawl_report_page.urls_indexed')}
                    .value=${this.countFromSummary('url_indexed')}
                    .locale=${this.locale}
                    .refreshing=${this.refreshing}
                ></platform-metric-card>
                <platform-metric-card
                    label=${this.t('crawl_report_page.urls_enriched_total')}
                    .value=${enrichedTotal}
                    .locale=${this.locale}
                    tone=${enrichedTotal > 0 ? 'accent' : ''}
                    .refreshing=${this.refreshing}
                ></platform-metric-card>
                <platform-metric-card
                    label=${this.t('crawl_report_page.urls_enrichment_pending')}
                    .value=${enrichmentPending}
                    .locale=${this.locale}
                    tone=${enrichmentPending > 0 ? 'warn' : ''}
                    .refreshing=${this.refreshing}
                ></platform-metric-card>
                <platform-metric-card
                    label=${this.t('crawl_report_page.urls_fetching')}
                    .value=${fetchingCount}
                    .locale=${this.locale}
                    tone=${fetchingCount > 0 ? 'warn' : ''}
                    .refreshing=${this.refreshing}
                ></platform-metric-card>
                <platform-metric-card
                    label=${this.t('crawl_report_page.urls_pending')}
                    .value=${this.countFromSummary('url_pending')}
                    .locale=${this.locale}
                    .refreshing=${this.refreshing}
                ></platform-metric-card>
                <platform-metric-card
                    label=${this.t('crawl_report_page.urls_failed')}
                    .value=${failedCount}
                    .locale=${this.locale}
                    tone=${failedCount > 0 ? 'danger' : ''}
                    .refreshing=${this.refreshing}
                ></platform-metric-card>
            </div>
        `;
    }
}

customElements.define('crawl-report-metric-strip', CrawlReportMetricStrip);
