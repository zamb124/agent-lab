import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-mini-bar-chart.js';
import '@platform/lib/components/platform-sparkline.js';
import '@platform/lib/components/platform-metric-card.js';
import {
    CATEGORY_CHART_COLORS,
    DOMAIN_STATUS_CHART_COLORS,
    URL_STATUS_CHART_COLORS,
} from './crawl-report-chart-colors.js';

export class CrawlReportChartsPanel extends PlatformElement {
    static i18nNamespace = 'frontend';

    static properties = {
        summary: { type: Object },
        jobs: { type: Array },
        domains: { type: Array },
        locale: { type: String },
        collapsed: { type: Boolean },
        statusLabel: { attribute: false },
        categoryLabel: { attribute: false },
        contentTypeLabel: { attribute: false },
        topicLabel: { attribute: false },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; margin-bottom: var(--space-4); }
            .panel {
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                overflow: hidden;
            }
            .panel-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-3);
                padding: var(--space-3) var(--space-4);
                border-bottom: 1px solid var(--glass-border-subtle);
            }
            .panel-title {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }
            .toggle-btn {
                background: none;
                border: none;
                color: var(--text-secondary);
                cursor: pointer;
                font-size: var(--text-xs);
            }
            .panel-body {
                padding: var(--space-4);
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
                gap: var(--space-4);
            }
            .chart-card {
                padding: var(--space-3);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: color-mix(in srgb, var(--glass-solid-medium) 35%, transparent);
            }
            .chart-title {
                font-size: var(--text-xs);
                text-transform: uppercase;
                letter-spacing: 0.04em;
                color: var(--text-tertiary);
                margin-bottom: var(--space-3);
            }
            .funnel-grid {
                display: grid;
                grid-template-columns: repeat(2, minmax(0, 1fr));
                gap: var(--space-2);
            }
        `,
    ];

    constructor() {
        super();
        this.summary = null;
        this.jobs = [];
        this.domains = [];
        this.locale = 'en';
        this.collapsed = false;
        this.statusLabel = (status) => status;
        this.categoryLabel = (category) => category;
        this.contentTypeLabel = (contentType) => contentType;
        this.topicLabel = (topic) => topic;
    }

    _urlSegments() {
        if (!this.summary || !Array.isArray(this.summary.url_counts)) return [];
        return this.summary.url_counts.map((row) => ({
            key: row.status,
            label: this.statusLabel(row.status),
            value: row.count,
            color: URL_STATUS_CHART_COLORS[row.status] || 'var(--text-tertiary)',
        }));
    }

    _domainSegments() {
        if (!this.summary || !Array.isArray(this.summary.domain_counts)) return [];
        return this.summary.domain_counts.map((row) => ({
            key: row.status,
            label: this.statusLabel(row.status),
            value: row.count,
            color: DOMAIN_STATUS_CHART_COLORS[row.status] || 'var(--text-tertiary)',
        }));
    }

    _categorySegments() {
        const counts = new Map();
        for (const domain of this.domains) {
            const category = domain.category || 'unknown';
            counts.set(category, (counts.get(category) || 0) + 1);
        }
        const entries = [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 8);
        return entries.map(([category, value], index) => ({
            key: category,
            label: this.categoryLabel(category),
            value,
            color: CATEGORY_CHART_COLORS[index % CATEGORY_CHART_COLORS.length],
        }));
    }

    _contentTypeSegments() {
        if (!this.summary || !Array.isArray(this.summary.content_type_counts)) return [];
        return this.summary.content_type_counts.slice(0, 10).map((row, index) => ({
            key: row.status,
            label: this.contentTypeLabel(row.status),
            value: row.count,
            color: CATEGORY_CHART_COLORS[index % CATEGORY_CHART_COLORS.length],
        }));
    }

    _primaryTopicSegments() {
        if (!this.summary || !Array.isArray(this.summary.primary_topic_counts)) return [];
        return this.summary.primary_topic_counts.slice(0, 10).map((row, index) => ({
            key: row.status,
            label: this.topicLabel(row.status),
            value: row.count,
            color: CATEGORY_CHART_COLORS[(index + 3) % CATEGORY_CHART_COLORS.length],
        }));
    }

    _jobSparklinePoints() {
        const sorted = [...this.jobs]
            .filter((job) => job && job.started_at)
            .sort((a, b) => new Date(a.started_at).getTime() - new Date(b.started_at).getTime())
            .slice(-24);
        return sorted.map((job) => ({
            label: job.started_at,
            value: job.urls_indexed,
        }));
    }

    _funnelMetrics() {
        const runningJob = this.summary && this.summary.running_job;
        if (runningJob) {
            return {
                fetched: runningJob.urls_fetched,
                indexed: runningJob.urls_indexed,
                enriched: runningJob.urls_enriched,
                errors: runningJob.errors,
            };
        }
        let fetched = 0;
        let indexed = 0;
        let enriched = 0;
        let errors = 0;
        for (const job of this.jobs.slice(0, 12)) {
            fetched += job.urls_fetched;
            indexed += job.urls_indexed;
            enriched += job.urls_enriched;
            errors += job.errors;
        }
        return { fetched, indexed, enriched, errors };
    }

    render() {
        const funnel = this._funnelMetrics();
        return html`
            <section class="panel">
                <div class="panel-header">
                    <div class="panel-title">${this.t('crawl_report_page.charts_title')}</div>
                    <button type="button" class="toggle-btn" @click=${() => { this.collapsed = !this.collapsed; }}>
                        ${this.collapsed
                            ? this.t('crawl_report_page.charts_expand')
                            : this.t('crawl_report_page.charts_collapse')}
                    </button>
                </div>
                ${this.collapsed ? null : html`
                    <div class="panel-body">
                        <div class="chart-card">
                            <div class="chart-title">${this.t('crawl_report_page.chart_urls_by_status')}</div>
                            <platform-mini-bar-chart
                                .segments=${this._urlSegments()}
                                .locale=${this.locale}
                                emptyLabel=${this.t('crawl_report_page.chart_empty')}
                            ></platform-mini-bar-chart>
                        </div>
                        <div class="chart-card">
                            <div class="chart-title">${this.t('crawl_report_page.chart_domains_by_status')}</div>
                            <platform-mini-bar-chart
                                .segments=${this._domainSegments()}
                                .locale=${this.locale}
                                emptyLabel=${this.t('crawl_report_page.chart_empty')}
                            ></platform-mini-bar-chart>
                        </div>
                        <div class="chart-card">
                            <div class="chart-title">${this.t('crawl_report_page.chart_job_throughput')}</div>
                            <platform-sparkline
                                .points=${this._jobSparklinePoints()}
                                emptyLabel=${this.t('crawl_report_page.chart_empty')}
                            ></platform-sparkline>
                        </div>
                        <div class="chart-card">
                            <div class="chart-title">${this.t('crawl_report_page.chart_enrichment_funnel')}</div>
                            <div class="funnel-grid">
                                <platform-metric-card
                                    label=${this.t('crawl_report_page.running_stat_fetched')}
                                    .value=${funnel.fetched}
                                    .locale=${this.locale}
                                ></platform-metric-card>
                                <platform-metric-card
                                    label=${this.t('crawl_report_page.running_stat_indexed')}
                                    .value=${funnel.indexed}
                                    .locale=${this.locale}
                                ></platform-metric-card>
                                <platform-metric-card
                                    label=${this.t('crawl_report_page.running_stat_enriched')}
                                    .value=${funnel.enriched}
                                    .locale=${this.locale}
                                ></platform-metric-card>
                                <platform-metric-card
                                    label=${this.t('crawl_report_page.running_stat_errors')}
                                    .value=${funnel.errors}
                                    .locale=${this.locale}
                                    tone=${funnel.errors > 0 ? 'danger' : ''}
                                ></platform-metric-card>
                            </div>
                        </div>
                        <div class="chart-card">
                            <div class="chart-title">${this.t('crawl_report_page.chart_domains_by_category')}</div>
                            <platform-mini-bar-chart
                                .segments=${this._categorySegments()}
                                .locale=${this.locale}
                                emptyLabel=${this.t('crawl_report_page.chart_empty')}
                            ></platform-mini-bar-chart>
                        </div>
                        <div class="chart-card">
                            <div class="chart-title">${this.t('crawl_report_page.chart_urls_by_content_type')}</div>
                            <platform-mini-bar-chart
                                .segments=${this._contentTypeSegments()}
                                .locale=${this.locale}
                                emptyLabel=${this.t('crawl_report_page.chart_empty')}
                            ></platform-mini-bar-chart>
                        </div>
                        <div class="chart-card">
                            <div class="chart-title">${this.t('crawl_report_page.chart_urls_by_primary_topic')}</div>
                            <platform-mini-bar-chart
                                .segments=${this._primaryTopicSegments()}
                                .locale=${this.locale}
                                emptyLabel=${this.t('crawl_report_page.chart_empty')}
                            ></platform-mini-bar-chart>
                        </div>
                    </div>
                `}
            </section>
        `;
    }
}

customElements.define('crawl-report-charts-panel', CrawlReportChartsPanel);
