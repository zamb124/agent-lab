/**
 * Crawl report — мониторинг platform crawl pipeline (system company).
 */
import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { frontendIslandPageBodyStyles } from '../../styles/frontend-island-page-body.styles.js';
import { formatPlatformDateTime } from '@platform/lib/utils/format-platform-date.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-help-hint.js';
import '@platform/lib/components/platform-icon.js';

const TABS = Object.freeze(['domains', 'urls', 'jobs']);
const DEFAULT_PROFILE_ID = 'runet_platform';
const DOMAIN_STATUS_VALUES = Object.freeze(['active', 'error', 'paused', 'blocked']);
const URL_STATUS_VALUES = Object.freeze(['indexed', 'failed', 'pending', 'fetching', 'skipped']);
const CATEGORY_KEYS = Object.freeze(['gov', 'wiki', 'ecommerce', 'social', 'docs', 'media', 'news', 'unknown']);

export class FrontendCrawlReportPage extends PlatformPage {
    static styles = [
        PlatformPage.styles,
        css`
            :host { display: block; }

            .control-panel {
                display: grid;
                grid-template-columns: minmax(260px, 1fr) auto;
                gap: var(--space-4);
                align-items: end;
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                padding: var(--space-4);
                margin-bottom: var(--space-4);
            }
            .control-fields {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-3);
                align-items: flex-end;
            }
            .control-fields .field { min-width: 240px; flex: 1 1 240px; }
            .control-actions {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
                justify-content: flex-end;
                align-items: center;
            }
            .index-meta {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-top: var(--space-1);
            }
            .index-meta strong {
                color: var(--text-secondary);
                font-weight: var(--font-medium);
            }

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
                font-size: var(--text-sm);
                color: var(--text-secondary);
                font-family: var(--font-mono);
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

            .summary-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(148px, 1fr));
                gap: var(--space-3);
                margin-bottom: var(--space-4);
            }
            .summary-card {
                padding: var(--space-3);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
            }
            .summary-card.highlight {
                border-color: color-mix(in srgb, var(--accent) 40%, transparent);
            }
            .summary-card.warn {
                border-color: color-mix(in srgb, var(--warning) 45%, transparent);
            }
            .summary-card.danger {
                border-color: color-mix(in srgb, var(--error) 45%, transparent);
            }
            .summary-card .label {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                text-transform: uppercase;
                letter-spacing: 0.04em;
            }
            .summary-card .value {
                font-size: var(--text-xl);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                margin-top: var(--space-1);
            }

            .filters-panel {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-3);
                align-items: flex-end;
                padding: var(--space-3) var(--space-4);
                margin-bottom: var(--space-3);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
            }
            .filters-panel .field { min-width: 200px; flex: 1 1 200px; }
            .filter-chip-row {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
                align-items: center;
                width: 100%;
            }
            .filter-chip {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-1) var(--space-3);
                border-radius: var(--radius-full);
                background: var(--glass-solid-medium);
                border: 1px solid var(--glass-border-subtle);
                font-size: var(--text-xs);
                color: var(--text-secondary);
            }
            .filter-chip button {
                background: none;
                border: none;
                color: var(--text-tertiary);
                cursor: pointer;
                padding: 0;
                font-size: var(--text-xs);
            }
            .filter-chip button:hover { color: var(--text-primary); }

            .tabs {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
                border-bottom: 1px solid var(--glass-border-subtle);
                margin-bottom: var(--space-4);
            }
            .tab {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-4);
                background: transparent;
                border: none;
                color: var(--text-tertiary);
                cursor: pointer;
                font-size: var(--text-sm);
                border-bottom: 2px solid transparent;
                margin-bottom: -1px;
            }
            .tab[aria-selected="true"] {
                color: var(--text-primary);
                border-bottom-color: var(--accent);
                font-weight: var(--font-semibold);
            }
            .tab-count {
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
                padding: 1px 7px;
                border-radius: var(--radius-full);
                background: var(--glass-solid-medium);
                color: var(--text-secondary);
            }
            .tab[aria-selected="true"] .tab-count {
                background: color-mix(in srgb, var(--accent) 15%, transparent);
                color: var(--accent);
            }

            .btn {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-4);
                background: transparent;
                color: var(--text-secondary);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                cursor: pointer;
                font-size: var(--text-sm);
            }
            .btn:hover:not(:disabled) {
                border-color: var(--accent);
                color: var(--text-primary);
            }
            .btn.primary {
                background: var(--accent);
                color: white;
                border-color: var(--accent);
            }
            .btn.primary:hover:not(:disabled) {
                filter: brightness(1.05);
                color: white;
            }
            .btn:disabled { opacity: 0.5; cursor: not-allowed; }
            .btn-sm {
                padding: var(--space-1) var(--space-2);
                font-size: var(--text-xs);
            }

            .table-panel {
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                overflow: hidden;
            }
            table { width: 100%; border-collapse: collapse; }
            th, td {
                padding: var(--space-2) var(--space-3);
                border-bottom: 1px solid var(--glass-border-subtle);
                text-align: left;
                vertical-align: top;
            }
            th {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                text-transform: uppercase;
                letter-spacing: 0.05em;
                background: color-mix(in srgb, var(--glass-solid-medium) 60%, transparent);
            }
            td { color: var(--text-primary); font-size: var(--text-sm); }
            tr.data-row:hover { background: var(--glass-solid-medium); }
            .domain-link {
                background: none;
                border: none;
                color: var(--accent);
                cursor: pointer;
                padding: 0;
                font: inherit;
                text-align: left;
            }
            .domain-link:hover { text-decoration: underline; }
            .actions-cell {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
            }
            .status-tag {
                display: inline-block;
                padding: 2px 8px;
                border-radius: var(--radius-full);
                font-size: var(--text-xs);
                background: var(--glass-solid-medium);
                color: var(--text-secondary);
            }
            .status-tag.running { background: var(--accent); color: white; }
            .status-tag.error, .status-tag.failed { background: var(--error); color: white; }
            .status-tag.indexed, .status-tag.completed { background: var(--success); color: white; }
            .status-tag.fetching, .status-tag.pending { background: var(--warning); color: white; }
            .status-tag.http { background: var(--glass-solid-medium); color: var(--text-secondary); }
            .status-tag.browser { background: color-mix(in srgb, var(--accent) 12%, transparent); color: var(--accent); }
            .status-tag.category {
                background: color-mix(in srgb, var(--text-tertiary) 12%, transparent);
                color: var(--text-secondary);
            }

            .state {
                padding: var(--space-8) var(--space-6);
                text-align: center;
                color: var(--text-tertiary);
            }
            .state .state-title {
                color: var(--text-primary);
                font-weight: var(--font-semibold);
                margin-bottom: var(--space-2);
            }
            .state.unavailable { border-top: 1px dashed var(--glass-border-subtle); }
            .mono {
                font-family: var(--font-mono);
                font-size: var(--text-xs);
                color: var(--text-secondary);
                word-break: break-all;
            }
            .hint {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-bottom: var(--space-3);
            }
            .table-loading {
                padding: var(--space-6);
                display: flex;
                justify-content: center;
            }
        `,
        frontendIslandPageBodyStyles,
    ];

    static properties = {
        _profileId: { state: true },
        _activeTab: { state: true },
        _urlStatusFilter: { state: true },
        _domainStatusFilter: { state: true },
        _urlDomainFilter: { state: true },
        _runningDomainId: { state: true },
        _loaded: { state: true },
    };

    constructor() {
        super();
        this._profilesOp = this.useOp('frontend/crawl_profiles_load');
        this._summaryOp = this.useOp('frontend/crawl_summary_load');
        this._domains = this.useResource('frontend/crawl_domains');
        this._urls = this.useResource('frontend/crawl_urls');
        this._jobs = this.useResource('frontend/crawl_jobs');
        this._queueTickOp = this.useOp('frontend/crawl_queue_tick');
        this._domainRun = this.useOp('frontend/crawl_domain_run');
        this._localeSel = this.select((state) => {
            const locale = state.i18n.locale;
            if (typeof locale !== 'string' || locale.length === 0) {
                throw new Error('crawl-report-page: i18n.locale is required');
            }
            return locale;
        });
        this._profileId = DEFAULT_PROFILE_ID;
        this._activeTab = 'domains';
        this._urlStatusFilter = '';
        this._domainStatusFilter = '';
        this._urlDomainFilter = '';
        this._runningDomainId = null;
        this._loaded = false;
        this._pollIntervalId = null;
    }

    connectedCallback() {
        super.connectedCallback();
        this._pollIntervalId = window.setInterval(() => this._maybeAutoRefresh(), 15000);
    }

    disconnectedCallback() {
        if (this._pollIntervalId !== null) {
            window.clearInterval(this._pollIntervalId);
            this._pollIntervalId = null;
        }
        super.disconnectedCallback();
    }

    updated() {
        if (!this._loaded) {
            this._loaded = true;
            this._profilesOp.run({});
            this._reloadAll();
        }
        if (!this._domainRun.state.busy && this._runningDomainId !== null) {
            this._runningDomainId = null;
        }
    }

    _shouldAutoRefresh() {
        const summary = this._summaryOp.state.lastResult;
        if (!summary) return false;
        if (summary.running_job) return true;
        return this._countFromSummary('url_fetching') > 0 || this._countFromSummary('url_pending') > 0;
    }

    _maybeAutoRefresh() {
        if (!this._shouldAutoRefresh()) return;
        this._reloadAll();
    }

    _formatDt(value) {
        if (!value) return '—';
        return formatPlatformDateTime(value, this._localeSel.value);
    }

    _profileOptions() {
        const result = this._profilesOp.state.lastResult;
        const items = result && result.items ? result.items : [];
        if (items.length === 0) {
            return [{ value: this._profileId, label: this._profileId }];
        }
        return items.map((item) => ({
            value: item.profile.crawl_profile_id,
            label: `${item.profile.crawl_profile_id} · ${item.search_index.display_name}`,
        }));
    }

    _selectedProfileBundle() {
        const result = this._profilesOp.state.lastResult;
        const items = result && result.items ? result.items : [];
        return items.find((item) => item.profile.crawl_profile_id === this._profileId) ?? null;
    }

    _reloadAll() {
        const payload = { crawl_profile_id: this._profileId };
        this._summaryOp.run(payload);
        this._domains.load({ ...payload, status: this._domainStatusFilter || undefined });
        this._urls.load({
            ...payload,
            crawl_status: this._urlStatusFilter || undefined,
            domain: this._urlDomainFilter || undefined,
        });
        this._jobs.load(payload);
    }

    _onProfileChange(e) {
        this._profileId = e.detail.value;
        this._urlDomainFilter = '';
        this._reloadAll();
    }

    _onDomainStatusFilterChange(e) {
        this._domainStatusFilter = e.detail.value;
        this._domains.load({
            crawl_profile_id: this._profileId,
            status: this._domainStatusFilter || undefined,
        });
    }

    _onUrlStatusFilterChange(e) {
        this._urlStatusFilter = e.detail.value;
        this._urls.load({
            crawl_profile_id: this._profileId,
            crawl_status: this._urlStatusFilter || undefined,
            domain: this._urlDomainFilter || undefined,
        });
    }

    _onUrlDomainFilterChange(e) {
        this._urlDomainFilter = e.detail.value.trim();
        this._urls.load({
            crawl_profile_id: this._profileId,
            crawl_status: this._urlStatusFilter || undefined,
            domain: this._urlDomainFilter || undefined,
        });
    }

    _clearUrlDomainFilter() {
        this._urlDomainFilter = '';
        this._urls.load({
            crawl_profile_id: this._profileId,
            crawl_status: this._urlStatusFilter || undefined,
        });
    }

    _viewDomainUrls(domain) {
        this._activeTab = 'urls';
        this._urlDomainFilter = domain;
        this._urls.load({
            crawl_profile_id: this._profileId,
            crawl_status: this._urlStatusFilter || undefined,
            domain,
        });
    }

    _runDomain(row) {
        this._runningDomainId = row.crawl_domain_id;
        this._domainRun.run({
            crawl_domain_id: row.crawl_domain_id,
            crawl_profile_id: this._profileId,
        });
    }

    _statusLabel(status) {
        const key = `crawl_report_page.status_${status}`;
        const translated = this.t(key);
        if (translated === key) return status;
        return translated;
    }

    _categoryLabel(category) {
        const normalized = CATEGORY_KEYS.includes(category) ? category : 'unknown';
        return this.t(`crawl_report_page.category_${normalized}`);
    }

    _triggerLabel(trigger) {
        const key = `crawl_report_page.trigger_${trigger}`;
        const translated = this.t(key);
        if (translated === key) return trigger;
        return translated;
    }

    _statusTag(status) {
        return html`<span class="status-tag ${status}">${this._statusLabel(status)}</span>`;
    }

    _categoryTag(category) {
        return html`<span class="status-tag category">${this._categoryLabel(category)}</span>`;
    }

    _transportTag(fetchTransport) {
        if (fetchTransport !== 'http' && fetchTransport !== 'browser') {
            return html`<span>—</span>`;
        }
        return html`<span class="status-tag ${fetchTransport}">${this.t(`crawl_report_page.transport_${fetchTransport}`)}</span>`;
    }

    _enrichmentTag(row) {
        if (row.enriched_content_hash) {
            return html`<span class="status-tag indexed">${this.t('crawl_report_page.enrichment_llm')}</span>`;
        }
        return html`<span>—</span>`;
    }

    _enumValues(statusKeys) {
        return [
            { value: '', label: this.t('crawl_report_page.filter_all') },
            ...statusKeys.map((status) => ({
                value: status,
                label: this._statusLabel(status),
            })),
        ];
    }

    _tabCount(tab) {
        if (tab === 'domains') return this._countFromSummary('domains_total');
        if (tab === 'jobs') {
            const jobs = this._jobs.state.items;
            return jobs ? jobs.length : 0;
        }
        const indexed = this._countFromSummary('url_indexed');
        const fetching = this._countFromSummary('url_fetching');
        const pending = this._countFromSummary('url_pending');
        const failed = this._countFromSummary('url_failed');
        return indexed + fetching + pending + failed;
    }

    _renderFilters() {
        if (this._activeTab === 'domains') {
            return html`
                <platform-field
                    class="field"
                    type="enum"
                    label=${this.t('crawl_report_page.filter_domain_status')}
                    .value=${this._domainStatusFilter}
                    .enumConfig=${{ values: this._enumValues(DOMAIN_STATUS_VALUES) }}
                    @value-changed=${this._onDomainStatusFilterChange}
                ></platform-field>
            `;
        }
        if (this._activeTab === 'urls') {
            return html`
                <platform-field
                    class="field"
                    type="enum"
                    label=${this.t('crawl_report_page.filter_url_status')}
                    .value=${this._urlStatusFilter}
                    .enumConfig=${{ values: this._enumValues(URL_STATUS_VALUES) }}
                    @value-changed=${this._onUrlStatusFilterChange}
                ></platform-field>
                <platform-field
                    class="field"
                    type="query"
                    label=${this.t('crawl_report_page.filter_url_domain')}
                    .value=${this._urlDomainFilter}
                    @value-changed=${this._onUrlDomainFilterChange}
                ></platform-field>
                ${this._urlDomainFilter ? html`
                    <div class="filter-chip-row">
                        <span class="filter-chip">
                            ${this._urlDomainFilter}
                            <button type="button" @click=${() => this._clearUrlDomainFilter()}>${this.t('crawl_report_page.clear_domain_filter')}</button>
                        </span>
                    </div>
                ` : null}
            `;
        }
        return null;
    }

    _queueTick() {
        this._queueTickOp.run({ crawl_profile_id: this._profileId, trigger: 'manual' });
    }

    _countFromSummary(key) {
        const summary = this._summaryOp.state.lastResult;
        if (!summary) return 0;
        if (key === 'domains_total') return summary.domains_total;
        if (key === 'domains_due') return summary.domains_due;
        const list = key.startsWith('url_') ? summary.url_counts : summary.domain_counts;
        const status = key.replace(/^(url_|domain_)/, '');
        const found = list.find((row) => row.status === status);
        return found ? found.count : 0;
    }

    _renderRunningBanner() {
        const summary = this._summaryOp.state.lastResult;
        const runningJob = summary && summary.running_job;
        if (!runningJob) return null;
        return html`
            <div class="running-banner">
                <div class="running-banner-title">
                    <span class="pulse-dot"></span>
                    ${this.t('crawl_report_page.running_banner_title')}
                </div>
                <div class="running-banner-stats">
                    ${this.t('crawl_report_page.running_banner_stats', {
                        fetched: runningJob.urls_fetched,
                        indexed: runningJob.urls_indexed,
                        enriched: runningJob.urls_enriched,
                        errors: runningJob.errors,
                    })}
                </div>
            </div>
        `;
    }

    _renderSummary() {
        if (this._summaryOp.state.busy) {
            return html`<glass-spinner size="sm"></glass-spinner>`;
        }
        if (this._summaryOp.state.errorKind === 'forbidden') {
            return html`
                <div class="state unavailable">
                    <div class="state-title">${this.t('crawl_report_page.forbidden')}</div>
                </div>
            `;
        }
        if (this._summaryOp.state.errorKind === 'unavailable') {
            return html`
                <div class="state unavailable">
                    <div class="state-title">${this.t('crawl_report_page.unavailable')}</div>
                </div>
            `;
        }
        const dueCount = this._countFromSummary('domains_due');
        const fetchingCount = this._countFromSummary('url_fetching');
        const failedCount = this._countFromSummary('url_failed');
        return html`
            <div class="summary-grid">
                <div class="summary-card">
                    <div class="label">${this.t('crawl_report_page.domains_total')}</div>
                    <div class="value">${this._countFromSummary('domains_total')}</div>
                </div>
                <div class="summary-card ${dueCount > 0 ? 'highlight' : ''}">
                    <div class="label">${this.t('crawl_report_page.domains_due')}</div>
                    <div class="value">${dueCount}</div>
                </div>
                <div class="summary-card">
                    <div class="label">${this.t('crawl_report_page.urls_indexed')}</div>
                    <div class="value">${this._countFromSummary('url_indexed')}</div>
                </div>
                <div class="summary-card ${fetchingCount > 0 ? 'warn' : ''}">
                    <div class="label">${this.t('crawl_report_page.urls_fetching')}</div>
                    <div class="value">${fetchingCount}</div>
                </div>
                <div class="summary-card">
                    <div class="label">${this.t('crawl_report_page.urls_pending')}</div>
                    <div class="value">${this._countFromSummary('url_pending')}</div>
                </div>
                <div class="summary-card ${failedCount > 0 ? 'danger' : ''}">
                    <div class="label">${this.t('crawl_report_page.urls_failed')}</div>
                    <div class="value">${failedCount}</div>
                </div>
            </div>
        `;
    }

    _renderTableLoading() {
        return html`<div class="table-loading"><glass-spinner size="sm"></glass-spinner></div>`;
    }

    _renderDomainsTable() {
        const { items, loading } = this._domains.state;
        if (loading) return this._renderTableLoading();
        if (!items || items.length === 0) {
            return html`
                <div class="state">
                    <div class="state-title">${this.t('crawl_report_page.empty_domains')}</div>
                </div>
            `;
        }
        return html`
            <table>
                <thead>
                    <tr>
                        <th>${this.t('crawl_report_page.col_domain')}</th>
                        <th>${this.t('crawl_report_page.col_category')}</th>
                        <th>${this.t('crawl_report_page.col_status')}</th>
                        <th>${this.t('crawl_report_page.col_last_crawled')}</th>
                        <th>${this.t('crawl_report_page.col_next_crawl')}</th>
                        <th>${this.t('crawl_report_page.col_error')}</th>
                        <th>${this.t('crawl_report_page.col_actions')}</th>
                    </tr>
                </thead>
                <tbody>
                    ${items.map((row) => html`
                        <tr class="data-row">
                            <td>
                                <button type="button" class="domain-link" @click=${() => this._viewDomainUrls(row.domain)}>${row.domain}</button>
                            </td>
                            <td>${this._categoryTag(row.category)}</td>
                            <td>${this._statusTag(row.status)}</td>
                            <td>${this._formatDt(row.last_crawled_at)}</td>
                            <td>${this._formatDt(row.next_crawl_after)}</td>
                            <td class="mono">${row.last_error || '—'}</td>
                            <td>
                                <div class="actions-cell">
                                    <button
                                        type="button"
                                        class="btn primary btn-sm"
                                        ?disabled=${this._runningDomainId === row.crawl_domain_id && this._domainRun.state.busy}
                                        @click=${() => this._runDomain(row)}
                                    >${this.t('crawl_report_page.run_domain')}</button>
                                    <button type="button" class="btn btn-sm" @click=${() => this._viewDomainUrls(row.domain)}>${this.t('crawl_report_page.view_urls')}</button>
                                </div>
                            </td>
                        </tr>
                    `)}
                </tbody>
            </table>
        `;
    }

    _renderUrlsTable() {
        const { items, loading } = this._urls.state;
        if (loading) return this._renderTableLoading();
        if (!items || items.length === 0) {
            return html`
                <div class="state">
                    <div class="state-title">${this.t('crawl_report_page.empty_urls')}</div>
                </div>
            `;
        }
        return html`
            <table>
                <thead>
                    <tr>
                        <th>${this.t('crawl_report_page.col_domain')}</th>
                        <th>${this.t('crawl_report_page.col_url')}</th>
                        <th>${this.t('crawl_report_page.col_status')}</th>
                        <th>${this.t('crawl_report_page.col_transport')}</th>
                        <th>${this.t('crawl_report_page.col_enrichment')}</th>
                        <th>${this.t('crawl_report_page.col_last_crawled')}</th>
                        <th>${this.t('crawl_report_page.col_error')}</th>
                    </tr>
                </thead>
                <tbody>
                    ${items.map((row) => html`
                        <tr class="data-row">
                            <td>
                                <button type="button" class="domain-link" @click=${() => this._viewDomainUrls(row.domain)}>${row.domain}</button>
                            </td>
                            <td class="mono">${row.url}</td>
                            <td>${this._statusTag(row.crawl_status)}</td>
                            <td>${this._transportTag(row.fetch_transport)}</td>
                            <td>${this._enrichmentTag(row)}</td>
                            <td>${this._formatDt(row.last_crawled_at)}</td>
                            <td class="mono">${row.last_error || '—'}</td>
                        </tr>
                    `)}
                </tbody>
            </table>
        `;
    }

    _renderJobsTable() {
        const { items, loading } = this._jobs.state;
        if (loading) return this._renderTableLoading();
        if (!items || items.length === 0) {
            return html`
                <div class="state">
                    <div class="state-title">${this.t('crawl_report_page.empty_jobs')}</div>
                </div>
            `;
        }
        return html`
            <table>
                <thead>
                    <tr>
                        <th>${this.t('crawl_report_page.col_started')}</th>
                        <th>${this.t('crawl_report_page.col_status')}</th>
                        <th>${this.t('crawl_report_page.col_trigger')}</th>
                        <th>${this.t('crawl_report_page.col_fetched')}</th>
                        <th>${this.t('crawl_report_page.col_indexed')}</th>
                        <th>${this.t('crawl_report_page.col_enriched')}</th>
                        <th>${this.t('crawl_report_page.col_errors')}</th>
                    </tr>
                </thead>
                <tbody>
                    ${items.map((row) => html`
                        <tr class="data-row">
                            <td>${this._formatDt(row.started_at)}</td>
                            <td>${this._statusTag(row.status)}</td>
                            <td>${this._triggerLabel(row.trigger)}</td>
                            <td>${row.urls_fetched}</td>
                            <td>${row.urls_indexed}</td>
                            <td>${row.urls_enriched}</td>
                            <td>${row.errors}</td>
                        </tr>
                    `)}
                </tbody>
            </table>
        `;
    }

    _renderTabContent() {
        if (this._activeTab === 'domains') return this._renderDomainsTable();
        if (this._activeTab === 'urls') return this._renderUrlsTable();
        return this._renderJobsTable();
    }

    render() {
        const profileBundle = this._selectedProfileBundle();
        const indexName = profileBundle ? profileBundle.search_index.display_name : null;
        const indexId = profileBundle ? profileBundle.search_index.search_index_id : null;
        return html`
            <page-header
                title=${this.t('crawl_report_page.title')}
                subtitle=${this.t('crawl_report_page.subtitle')}
            ></page-header>
            <div class="page-body">
                <section class="control-panel">
                    <div>
                        <div class="control-fields">
                            <platform-field
                                class="field"
                                type="enum"
                                label=${this.t('crawl_report_page.profile')}
                                .value=${this._profileId}
                                .enumConfig=${{ values: this._profileOptions() }}
                                @value-changed=${this._onProfileChange}
                            ></platform-field>
                        </div>
                        ${indexName && indexId ? html`
                            <div class="index-meta">
                                ${this.t('crawl_report_page.index_label')}:
                                <strong>${indexName}</strong> (${indexId})
                            </div>
                        ` : null}
                    </div>
                    <div class="control-actions">
                        <button type="button" class="btn" @click=${() => this._reloadAll()}>
                            <platform-icon name="refresh" size="16"></platform-icon>
                            ${this.t('crawl_report_page.refresh')}
                        </button>
                        <platform-help-hint .text=${this.t('crawl_report_page.queue_tick_hint')}></platform-help-hint>
                        <button
                            type="button"
                            class="btn primary"
                            ?disabled=${this._queueTickOp.state.busy}
                            @click=${() => this._queueTick()}
                        >${this.t('crawl_report_page.queue_tick')}</button>
                    </div>
                </section>

                ${this._renderSummary()}
                ${this._renderRunningBanner()}

                ${this._shouldAutoRefresh() ? html`
                    <div class="hint">${this.t('crawl_report_page.auto_refresh_hint')}</div>
                ` : null}

                <div class="tabs" role="tablist">
                    ${TABS.map((tab) => html`
                        <button
                            type="button"
                            class="tab"
                            role="tab"
                            aria-selected=${this._activeTab === tab ? 'true' : 'false'}
                            @click=${() => { this._activeTab = tab; }}
                        >
                            ${this.t(`crawl_report_page.tab_${tab}`)}
                            <span class="tab-count">${this._tabCount(tab)}</span>
                        </button>
                    `)}
                </div>

                ${this._renderFilters() ? html`
                    <div class="filters-panel">${this._renderFilters()}</div>
                ` : null}

                <div class="table-panel">${this._renderTabContent()}</div>
            </div>
        `;
    }
}

customElements.define('frontend-crawl-report-page', FrontendCrawlReportPage);
