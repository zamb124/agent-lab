/**
 * Crawl report — мониторинг platform crawl pipeline (system company).
 */
import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { frontendIslandPageBodyStyles } from '../../styles/frontend-island-page-body.styles.js';
import { formatPlatformDateTime } from '@platform/lib/utils/format-platform-date.js';
import { FrontendCrawlUrlDetailModal } from '../../modals/crawl-url-detail-modal.js';
import { FrontendCrawlDomainAddModal } from '../../modals/crawl-domain-add-modal.js';
import { FrontendCrawlDomainEditModal } from '../../modals/crawl-domain-edit-modal.js';
import { FrontendCrawlUrlAddModal } from '../../modals/crawl-url-add-modal.js';
import { FrontendCrawlProfileSettingsModal } from '../../modals/crawl-profile-settings-modal.js';

function optionalText(value: string): string | undefined {
    return value.length > 0 ? value : undefined;
}

function textOrDash(value: unknown): string {
    if (typeof value === 'string' && value.length > 0) return value;
    if (typeof value === 'number' && Number.isFinite(value) && value !== 0) return String(value);
    return '—';
}

function patternList(value: unknown): unknown[] {
    if (value === undefined || value === null) return [];
    if (!Array.isArray(value)) throw new Error('crawl-report: url patterns must be an array');
    return value;
}
import '../../components/crawl-report/crawl-report-enrichment-tags.js';
import '../../components/crawl-report/crawl-report-metric-strip.js';
import '../../components/crawl-report/crawl-report-running-banner.js';
import '../../components/crawl-report/crawl-report-charts-panel.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-help-hint.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-button.js';
import type {CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult} from 'lit';
import type { OpController, ResourceController} from '@platform/lib/base/use-resource.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';

type CrawlRowSnapshots = {
    domains: Map<unknown, unknown>;
    urls: Map<unknown, unknown>;
    jobs: Map<unknown, unknown>;
};

function requireText(value: unknown, label: string): string {
    if (typeof value !== 'string' || value.length === 0) {
        throw new Error(`crawl-report-page: ${label} required`);
    }
    return value;
}

function listedItems(result: unknown): Record<string, unknown>[] {
    if (result === null || result === undefined) {
        return [];
    }
    if (!isPlainRecord(result) || !Array.isArray(result.items)) {
        throw new Error('crawl-report-page: items array required');
    }
    const items: Record<string, unknown>[] = [];
    for (const item of result.items) {
        if (!isPlainRecord(item)) {
            throw new Error('crawl-report-page: profile item must be an object');
        }
        items.push(item);
    }
    return items;
}

function summaryRecord(value: unknown): Record<string, unknown> | null {
    return isPlainRecord(value) ? value : null;
}

function numericCount(value: unknown): number {
    return typeof value === 'number' && Number.isFinite(value) ? value : 0;
}

function rowSnapshot(snapshots: CrawlRowSnapshots, scope: string): Map<unknown, unknown> | null {
    if (scope === 'domains' || scope === 'urls' || scope === 'jobs') {
        return snapshots[scope];
    }
    return null;
}

const TABS = Object.freeze(['domains', 'urls', 'jobs']);
const DEFAULT_PROFILE_ID = 'runet_platform';
const DOMAIN_STATUS_VALUES = Object.freeze(['active', 'error', 'paused', 'blocked']);
const URL_STATUS_VALUES = Object.freeze(['indexed', 'failed', 'pending', 'fetching', 'skipped']);
const CATEGORY_KEYS = Object.freeze([
    'gov', 'wiki', 'docs', 'forum', 'blog', 'media', 'tech', 'finance', 'ecommerce', 'social',
    'sport', 'education', 'health', 'travel', 'auto', 'real_estate', 'law', 'culture', 'science',
    'reference', 'jobs', 'food', 'lifestyle', 'gaming', 'tools', 'news', 'unknown',
]);
const CONTENT_TYPE_FILTER_VALUES = Object.freeze([
    'article', 'news', 'blog', 'product', 'documentation', 'tutorial', 'guide', 'faq', 'review',
    'research', 'wiki', 'forum', 'legal', 'landing', 'reference', 'other',
]);
const ACTIVE_POLL_MS = 5000;

export class FrontendCrawlReportPage extends PlatformPage {
    static override styles: CSSResultGroup = [
        PlatformPage.styles,
        css`
            :host { display: block; }

            .control-panel {
                display: grid;
                grid-template-columns: minmax(260px, 1fr) auto;
                gap: var(--space-4);
                align-items: center;
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
            .tick-action {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
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
            .btn.danger:hover:not(:disabled) {
                border-color: var(--error);
                color: var(--error);
            }
            .btn-sm {
                padding: var(--space-1) var(--space-2);
                font-size: var(--text-xs);
            }
            .confirm-text {
                font-size: var(--text-xs);
                color: var(--text-secondary);
                align-self: center;
            }

            .table-panel {
                position: relative;
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                overflow: hidden;
            }
            .table-panel.refreshing::after {
                content: '';
                position: absolute;
                inset: 0;
                background: color-mix(in srgb, var(--glass-solid-subtle) 35%, transparent);
                pointer-events: none;
            }
            .table-refresh-indicator {
                position: absolute;
                top: var(--space-3);
                right: var(--space-3);
                z-index: 1;
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
            tr.data-row.row-updated {
                animation: crawl-row-highlight 1.5s ease-out;
            }
            @keyframes crawl-row-highlight {
                0% { background: color-mix(in srgb, var(--accent) 18%, transparent); }
                100% { background: transparent; }
            }
            .domain-link, .url-link {
                background: none;
                border: none;
                color: var(--accent);
                cursor: pointer;
                padding: 0;
                font: inherit;
                text-align: left;
            }
            .domain-link:hover, .url-link:hover { text-decoration: underline; }
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

    static override properties: PropertyDeclarations = {
        _profileId: { state: true },
        _activeTab: { state: true },
        _urlStatusFilter: { state: true },
        _urlContentTypeFilter: { state: true },
        _urlPrimaryTopicFilter: { state: true },
        _urlEnrichedOnlyFilter: { state: true },
        _domainStatusFilter: { state: true },
        _urlDomainFilter: { state: true },
        _runningDomainId: { state: true },
        _loaded: { state: true },
        _rowHighlightIds: { state: true },
        _confirmDeleteDomainId: { state: true },
    }
    declare _profileId: unknown;
    declare _activeTab: string;
    declare _urlStatusFilter: string;
    declare _urlContentTypeFilter: string;
    declare _urlPrimaryTopicFilter: string;
    declare _urlEnrichedOnlyFilter: boolean;
    declare _domainStatusFilter: string;
    declare _urlDomainFilter: string;
    declare _runningDomainId: string | null;
    declare _loaded: boolean;
    declare _rowHighlightIds: string[];
    declare _confirmDeleteDomainId: string | null;
;

    constructor() {
        super();
        this._profilesOp = this.useOp('search/crawl_profiles_load');
        this._summaryOp = this.useOp('search/crawl_summary_load');
        this._domains = this.useResource('search/crawl_domains');
        this._urls = this.useResource('search/crawl_urls');
        this._jobs = this.useResource('search/crawl_jobs');
        this._queueTickOp = this.useOp('search/crawl_queue_tick');
        this._domainRun = this.useOp('search/crawl_domain_run');
        this._domainPatch = this.useOp('search/crawl_domain_patch');
        this._domainDelete = this.useOp('search/crawl_domain_delete');
        this._urlRecrawl = this.useOp('search/crawl_url_recrawl');
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
        this._urlContentTypeFilter = '';
        this._urlPrimaryTopicFilter = '';
        this._urlEnrichedOnlyFilter = false;
        this._domainStatusFilter = '';
        this._urlDomainFilter = '';
        this._runningDomainId = null;
        this._loaded = false;
        this._pollIntervalId = null;
        this._rowHighlightIds = [];
        this._confirmDeleteDomainId = null;
        this._rowSnapshots = {
            domains: new Map(),
            urls: new Map(),
            jobs: new Map(),
        };
    }
    private _profilesOp: OpController;
    private _summaryOp: OpController;
    private _domains: ResourceController;
    private _urls: ResourceController;
    private _jobs: ResourceController;
    private _queueTickOp: OpController;
    private _domainRun: OpController;
    private _domainPatch: OpController;
    private _domainDelete: OpController;
    private _urlRecrawl: OpController;
    private _localeSel: SelectController<string>;
    private _pollIntervalId: number | null;
    private _rowSnapshots: CrawlRowSnapshots;


    override connectedCallback(): void {
        super.connectedCallback();
        this._syncPollTimer();
    }

    override disconnectedCallback(): void {
        this._clearPollTimer();
        super.disconnectedCallback();
    }

    override updated(changed: PropertyValues<this>): void {
        if (!this._loaded) {
            this._loaded = true;
            this._profilesOp.run({ limit: 200, offset: 0 });
            this._reloadAll();
        }
        if (!this._domainRun.state.busy && this._runningDomainId !== null) {
            this._runningDomainId = null;
        }
        if (this._loaded) {
            this._trackRowHighlights();
            this._syncPollTimer();
        }
    }

    _clearPollTimer() {
        if (this._pollIntervalId !== null) {
            window.clearInterval(this._pollIntervalId);
            this._pollIntervalId = null;
        }
    }

    _syncPollTimer() {
        this._clearPollTimer();
        if (!this._shouldAutoRefresh()) {
            return;
        }
        this._pollIntervalId = window.setInterval(() => this._maybeAutoRefresh(), ACTIVE_POLL_MS);
    }

    _shouldAutoRefresh() {
        const summary = summaryRecord(this._summaryOp.state.lastResult);
        if (summary === null) return false;
        if (summary.running_job) return true;
        return this._countFromSummary('url_fetching') > 0 || this._countFromSummary('url_pending') > 0;
    }

    _maybeAutoRefresh() {
        if (!this._shouldAutoRefresh()) {
            this._syncPollTimer();
            return;
        }
        this._reloadSummaryAndActiveTab();
    }

    _formatDt(value: unknown) {
        if (value === null || value === undefined || value === '') return '—';
        if (typeof value !== 'string' && typeof value !== 'number' && !(value instanceof Date)) {
            throw new Error('crawl-report-page: datetime must be a string, number, or Date');
        }
        return formatPlatformDateTime(value, this._localeSel.value);
    }

    _profileOptions() {
        const items = listedItems(this._profilesOp.state.lastResult);
        if (items.length === 0) {
            return [{ value: this._profileId, label: this._profileId }];
        }
        return items.map((item) => {
            if (!isPlainRecord(item.profile) || typeof item.profile.crawl_profile_id !== 'string') {
                throw new Error('crawl-report-page: crawl_profile_id required');
            }
            const displayName = isPlainRecord(item.search_index) && typeof item.search_index.display_name === 'string'
                ? item.search_index.display_name
                : '';
            return {
                value: item.profile.crawl_profile_id,
                label: `${item.profile.crawl_profile_id} · ${displayName}`,
            };
        });
    }

    _selectedProfileBundle() {
        const items = listedItems(this._profilesOp.state.lastResult);
        const found = items.find((item) => isPlainRecord(item.profile) && item.profile.crawl_profile_id === this._profileId);
        return found === undefined ? null : found;
    }

    _profilePayload() {
        return { crawl_profile_id: this._profileId };
    }

    _urlListPayload() {
        return {
            crawl_profile_id: this._profileId,
            crawl_status: optionalText(this._urlStatusFilter),
            domain: optionalText(this._urlDomainFilter),
            content_type: optionalText(this._urlContentTypeFilter),
            primary_topic: optionalText(this._urlPrimaryTopicFilter),
            enriched_only: this._urlEnrichedOnlyFilter === true ? true : undefined,
        };
    }

    _reloadAll() {
        const payload = this._profilePayload();
        this._summaryOp.run(payload);
        this._domains.load({ ...payload, status: optionalText(this._domainStatusFilter) });
        this._urls.load(this._urlListPayload());
        this._jobs.load(payload);
    }

    _reloadSummaryAndActiveTab() {
        const payload = this._profilePayload();
        this._summaryOp.run(payload);
        if (this._activeTab === 'domains') {
            this._domains.load({ ...payload, status: optionalText(this._domainStatusFilter) });
        } else if (this._activeTab === 'urls') {
            this._urls.load(this._urlListPayload());
        } else {
            this._jobs.load(payload);
        }
    }

    _onProfileChange(e: CustomEvent) {
        this._profileId = e.detail.value;
        this._urlDomainFilter = '';
        this._urlContentTypeFilter = '';
        this._urlPrimaryTopicFilter = '';
        this._urlEnrichedOnlyFilter = false;
        this._rowSnapshots.domains.clear();
        this._rowSnapshots.urls.clear();
        this._rowSnapshots.jobs.clear();
        this._reloadAll();
        this._syncPollTimer();
    }

    _onDomainStatusFilterChange(e: CustomEvent) {
        this._domainStatusFilter = e.detail.value;
        this._domains.load({
            crawl_profile_id: this._profileId,
            status: optionalText(this._domainStatusFilter),
        });
    }

    _onUrlStatusFilterChange(e: CustomEvent) {
        this._urlStatusFilter = e.detail.value;
        this._urls.load(this._urlListPayload());
    }

    _onUrlContentTypeFilterChange(e: CustomEvent) {
        this._urlContentTypeFilter = e.detail.value;
        this._urls.load(this._urlListPayload());
    }

    _onUrlPrimaryTopicFilterChange(e: CustomEvent) {
        this._urlPrimaryTopicFilter = e.detail.value;
        this._urls.load(this._urlListPayload());
    }

    _onUrlEnrichedOnlyFilterChange(e: CustomEvent) {
        this._urlEnrichedOnlyFilter = e.detail.value === 'true';
        this._urls.load(this._urlListPayload());
    }

    _onUrlDomainFilterChange(e: CustomEvent) {
        this._urlDomainFilter = e.detail.value.trim();
        this._urls.load(this._urlListPayload());
    }

    _clearUrlDomainFilter() {
        this._urlDomainFilter = '';
        this._urls.load(this._urlListPayload());
    }

    _viewDomainUrls(domain: unknown) {
        this._activeTab = 'urls';
        if (typeof domain !== 'string') {
            throw new Error('crawl-report-page: domain must be a string');
        }
        this._urlDomainFilter = domain;
        this._urls.load(this._urlListPayload());
    }

    _openUrlDetail(row: Record<string, unknown>) {
        this.openModal(FrontendCrawlUrlDetailModal, {
            crawl_url_id: row.crawl_url_id,
            crawl_profile_id: this._profileId,
        });
    }

    _runDomain(row: Record<string, unknown>) {
        this._runningDomainId = requireText(row.crawl_domain_id, 'crawl_domain_id');
        this._domainRun.run({
            crawl_domain_id: row.crawl_domain_id,
            crawl_profile_id: this._profileId,
        });
    }

    _openProfileSettings() {
        const bundle = this._selectedProfileBundle();
        if (!bundle) return;
        this.openModal(FrontendCrawlProfileSettingsModal, {
            crawl_profile_id: this._profileId,
            profile: bundle.profile,
        });
    }

    _openAddDomain() {
        this.openModal(FrontendCrawlDomainAddModal, {
            crawl_profile_id: this._profileId,
        });
    }

    _openEditDomain(row: Record<string, unknown>) {
        this.openModal(FrontendCrawlDomainEditModal, {
            crawl_profile_id: this._profileId,
            crawl_domain_id: row.crawl_domain_id,
            domain: row.domain,
            status: row.status,
            refresh_interval_seconds: row.refresh_interval_seconds,
            include_url_patterns: patternList(row.include_url_patterns),
            exclude_url_patterns: patternList(row.exclude_url_patterns),
        });
    }

    _openAddUrl(row: Record<string, unknown>) {
        this.openModal(FrontendCrawlUrlAddModal, {
            crawl_profile_id: this._profileId,
            crawl_domain_id: row.crawl_domain_id,
            domain: row.domain,
        });
    }

    _toggleDomainPause(row: Record<string, unknown>) {
        const nextStatus = row.status === 'paused' ? 'active' : 'paused';
        this._domainPatch.run({
            crawl_domain_id: row.crawl_domain_id,
            crawl_profile_id: this._profileId,
            status: nextStatus,
        });
    }

    _requestDeleteDomain(row: Record<string, unknown>) {
        this._confirmDeleteDomainId = requireText(row.crawl_domain_id, 'crawl_domain_id');
    }

    _cancelDeleteDomain() {
        this._confirmDeleteDomainId = null;
    }

    _confirmDeleteDomain(row: Record<string, unknown>) {
        this._confirmDeleteDomainId = null;
        this._domainDelete.run({
            crawl_domain_id: row.crawl_domain_id,
            crawl_profile_id: this._profileId,
        });
    }

    _recrawlUrl(row: Record<string, unknown>) {
        this._urlRecrawl.run({
            crawl_url_id: row.crawl_url_id,
            crawl_profile_id: this._profileId,
        });
    }

    _statusLabel(status: string) {
        const key = `crawl_report_page.status_${status}`;
        const translated = this.t(key);
        if (translated === key) return status;
        return translated;
    }

    _contentTypeLabel(contentType: string) {
        const key = `crawl_report_page.content_type_${contentType}`;
        const translated = this.t(key);
        if (translated === key) return contentType;
        return translated;
    }

    _topicLabel(topic: string) {
        const key = `crawl_report_page.topic_${topic}`;
        const translated = this.t(key);
        if (translated === key) return topic;
        return translated;
    }

    _categoryLabel(category: string) {
        const normalized = CATEGORY_KEYS.includes(category) ? category : 'unknown';
        return this.t(`crawl_report_page.category_${normalized}`);
    }

    _triggerLabel(trigger: unknown) {
        if (typeof trigger !== 'string' || trigger.length === 0) {
            throw new Error('crawl-report-page: trigger required');
        }
        const key = `crawl_report_page.trigger_${trigger}`;
        const translated = this.t(key);
        if (translated === key) return trigger;
        return translated;
    }

    _statusTag(status: unknown) {
        const s = typeof status === 'string' ? status : '';
        return html`<span class="status-tag ${s}">${this._statusLabel(s)}</span>`;
    }

    _categoryTag(category: unknown) {
        const value = typeof category === 'string' ? category : 'unknown';
        return html`<span class="status-tag category">${this._categoryLabel(value)}</span>`;
    }

    _transportTag(fetchTransport: string) {
        if (fetchTransport !== 'http' && fetchTransport !== 'browser') {
            return html`<span>—</span>`;
        }
        return html`<span class="status-tag ${fetchTransport}">${this.t(`crawl_report_page.transport_${fetchTransport}`)}</span>`;
    }

    _enrichmentCell(row: Record<string, unknown>) {
        return html`
            <crawl-report-enrichment-tags
                .enrichmentSnapshot=${row.enrichment_snapshot}
                .structuralSignals=${row.structural_signals}
                compact
            ></crawl-report-enrichment-tags>
        `;
    }

    _primaryTopicFilterValues() {
        const summary = summaryRecord(this._summaryOp.state.lastResult);
        const topicCounts = summary === null ? undefined : summary.primary_topic_counts;
        const rows = Array.isArray(topicCounts) ? topicCounts : [];
        return [
            { value: '', label: this.t('crawl_report_page.filter_all') },
            ...rows.slice(0, 40).map((row) => {
                if (!isPlainRecord(row) || typeof row.status !== 'string') {
                    throw new Error('crawl-report-page: topic status required');
                }
                return {
                    value: row.status,
                    label: `${this._topicLabel(row.status)} (${textOrDash(row.count)})`,
                };
            }),
        ];
    }

    _contentTypeFilterValues() {
        return [
            { value: '', label: this.t('crawl_report_page.filter_all') },
            ...CONTENT_TYPE_FILTER_VALUES.map((contentType) => ({
                value: contentType,
                label: this._contentTypeLabel(contentType),
            })),
        ];
    }

    _enumValues(statusKeys: readonly string[]) {
        return [
            { value: '', label: this.t('crawl_report_page.filter_all') },
            ...statusKeys.map((status: string) => ({
                value: status,
                label: this._statusLabel(status),
            })),
        ];
    }

    _tabCount(tab: string) {
        if (tab === 'domains') return this._countFromSummary('domains_total');
        if (tab === 'jobs') {
            const total = this._jobs.listTotal;
            if (total !== null) return total;
            const jobs = this._jobs.state.items;
            return jobs ? jobs.length : 0;
        }
        const indexed = this._countFromSummary('url_indexed');
        const fetching = this._countFromSummary('url_fetching');
        const pending = this._countFromSummary('url_pending');
        const failed = this._countFromSummary('url_failed');
        return indexed + fetching + pending + failed;
    }

    _countFromSummary(key: string) {
        const summary = summaryRecord(this._summaryOp.state.lastResult);
        if (summary === null) return 0;
        if (key === 'domains_total') return numericCount(summary.domains_total);
        if (key === 'domains_due') return numericCount(summary.domains_due);
        const counts = key.startsWith('url_') ? summary.url_counts : summary.domain_counts;
        if (!Array.isArray(counts)) return 0;
        const status = key.replace(/^(url_|domain_)/, '');
        const found = counts.find((row) => isPlainRecord(row) && row.status === status);
        if (!isPlainRecord(found)) return 0;
        return numericCount(found.count);
    }

    _trackRowHighlights() {
        const highlights: string[] = [];
        this._collectRowHighlights('domains', this._domains.items, 'crawl_domain_id', (row) => typeof row.status === 'string' ? row.status : '', highlights);
        this._collectRowHighlights('urls', this._urls.items, 'crawl_url_id', (row) => typeof row.crawl_status === 'string' ? row.crawl_status : '', highlights);
        this._collectRowHighlights('jobs', this._jobs.items, 'crawl_job_id', (row: Record<string, unknown>) => (
            `${row.status}:${row.urls_fetched}:${row.urls_indexed}:${row.urls_enriched}:${row.errors}`
        ), highlights);
        if (highlights.length > 0) {
            this._rowHighlightIds = highlights;
            window.setTimeout(() => {
                this._rowHighlightIds = [];
            }, 1600);
        }
    }

    _collectRowHighlights(scope: string, items: readonly Record<string, unknown>[] | undefined, idField: string, signatureFn: (row: Record<string, unknown>) => string, highlights: string[]) {
        if (!items) return;
        const snapshot = rowSnapshot(this._rowSnapshots, scope);
        if (!snapshot) return;
        for (const row of items) {
            const rowId = row[idField];
            const signature = signatureFn(row);
            const previous = snapshot.get(rowId);
            if (previous !== undefined && previous !== signature) {
                highlights.push(`${scope}:${rowId}`);
            }
            snapshot.set(rowId, signature);
        }
    }

    _rowClass(scope: string, rowId: unknown) {
        return this._rowHighlightIds.includes(`${scope}:${rowId}`) ? 'data-row row-updated' : 'data-row';
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
                <platform-button
                    variant="primary"
                    density="compact"
                    @click=${() => this._openAddDomain()}
                >
                    <platform-icon name="plus" size="16"></platform-icon>
                    ${this.t('crawl_report_page.add_domain')}
                </platform-button>
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
                    type="enum"
                    label=${this.t('crawl_report_page.filter_content_type')}
                    .value=${this._urlContentTypeFilter}
                    .enumConfig=${{ values: this._contentTypeFilterValues() }}
                    @value-changed=${this._onUrlContentTypeFilterChange}
                ></platform-field>
                <platform-field
                    class="field"
                    type="enum"
                    label=${this.t('crawl_report_page.filter_primary_topic')}
                    .value=${this._urlPrimaryTopicFilter}
                    .enumConfig=${{ values: this._primaryTopicFilterValues() }}
                    @value-changed=${this._onUrlPrimaryTopicFilterChange}
                ></platform-field>
                <platform-field
                    class="field"
                    type="enum"
                    label=${this.t('crawl_report_page.filter_enriched_only')}
                    .value=${this._urlEnrichedOnlyFilter ? 'true' : ''}
                    .enumConfig=${{
                        values: [
                            { value: '', label: this.t('crawl_report_page.filter_all') },
                            { value: 'true', label: this.t('crawl_report_page.filter_enriched_only_yes') },
                        ],
                    }}
                    @value-changed=${this._onUrlEnrichedOnlyFilterChange}
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

    _renderTableLoading() {
        return html`<div class="table-loading"><glass-spinner size="sm"></glass-spinner></div>`;
    }

    _renderTableShell(refreshing: boolean, content: unknown) {
        return html`
            <div class="table-panel ${refreshing ? 'refreshing' : ''}">
                ${refreshing ? html`<div class="table-refresh-indicator"><glass-spinner size="sm"></glass-spinner></div>` : null}
                ${content}
            </div>
        `;
    }

    _renderDomainActions(row: Record<string, unknown>) {
        if (this._confirmDeleteDomainId === row.crawl_domain_id) {
            return html`
                <div class="actions-cell">
                    <span class="confirm-text">${this.t('crawl_report_page.confirm_delete_domain')}</span>
                    <button type="button" class="btn btn-sm danger" @click=${() => this._confirmDeleteDomain(row)}>
                        ${this.t('crawl_report_page.confirm_yes')}
                    </button>
                    <button type="button" class="btn btn-sm" @click=${() => this._cancelDeleteDomain()}>
                        ${this.t('crawl_report_page.confirm_no')}
                    </button>
                </div>
            `;
        }
        const pauseLabel = row.status === 'paused'
            ? this.t('crawl_report_page.resume_domain')
            : this.t('crawl_report_page.pause_domain');
        return html`
            <div class="actions-cell">
                <button
                    type="button"
                    class="btn primary btn-sm"
                    ?disabled=${this._runningDomainId === row.crawl_domain_id && this._domainRun.state.busy}
                    @click=${() => this._runDomain(row)}
                >${this.t('crawl_report_page.run_domain')}</button>
                <button type="button" class="btn btn-sm" @click=${() => this._openAddUrl(row)}>${this.t('crawl_report_page.add_url')}</button>
                <button type="button" class="btn btn-sm" @click=${() => this._openEditDomain(row)}>${this.t('crawl_report_page.edit')}</button>
                <button type="button" class="btn btn-sm" @click=${() => this._toggleDomainPause(row)}>${pauseLabel}</button>
                <button type="button" class="btn btn-sm danger" @click=${() => this._requestDeleteDomain(row)}>${this.t('crawl_report_page.delete')}</button>
            </div>
        `;
    }

    _renderDomainsTable() {
        const { items, loading, refreshing } = this._domains.state;
        if (loading && (!items || items.length === 0)) {
            return this._renderTableShell(false, this._renderTableLoading());
        }
        if (!items || items.length === 0) {
            return this._renderTableShell(refreshing, html`
                <div class="state">
                    <div class="state-title">${this.t('crawl_report_page.empty_domains')}</div>
                </div>
            `);
        }
        return this._renderTableShell(refreshing, html`
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
                        <tr class=${this._rowClass('domains', row.crawl_domain_id)}>
                            <td>
                                <button type="button" class="domain-link" @click=${() => this._viewDomainUrls(row.domain)}>${row.domain}</button>
                            </td>
                            <td>${this._categoryTag(row.category)}</td>
                            <td>${this._statusTag(row.status)}</td>
                            <td>${this._formatDt(row.last_crawled_at)}</td>
                            <td>${this._formatDt(row.next_crawl_after)}</td>
                            <td class="mono">${textOrDash(row.last_error)}</td>
                            <td>
                                ${this._renderDomainActions(row)}
                            </td>
                        </tr>
                    `)}
                </tbody>
            </table>
        `);
    }

    _renderUrlsTable() {
        const { items, loading, refreshing } = this._urls.state;
        if (loading && (!items || items.length === 0)) {
            return this._renderTableShell(false, this._renderTableLoading());
        }
        if (!items || items.length === 0) {
            return this._renderTableShell(refreshing, html`
                <div class="state">
                    <div class="state-title">${this.t('crawl_report_page.empty_urls')}</div>
                </div>
            `);
        }
        return this._renderTableShell(refreshing, html`
            <table>
                <thead>
                    <tr>
                        <th>${this.t('crawl_report_page.col_domain')}</th>
                        <th>${this.t('crawl_report_page.col_url')}</th>
                        <th>${this.t('crawl_report_page.col_status')}</th>
                        <th>${this.t('crawl_report_page.col_enrichment')}</th>
                        <th>${this.t('crawl_report_page.col_transport')}</th>
                        <th>${this.t('crawl_report_page.col_last_crawled')}</th>
                        <th>${this.t('crawl_report_page.col_error')}</th>
                        <th>${this.t('crawl_report_page.col_actions')}</th>
                    </tr>
                </thead>
                <tbody>
                    ${items.map((row) => html`
                        <tr class=${this._rowClass('urls', row.crawl_url_id)}>
                            <td>
                                <button type="button" class="domain-link" @click=${() => this._viewDomainUrls(row.domain)}>${row.domain}</button>
                            </td>
                            <td class="mono">
                                <button type="button" class="url-link" @click=${() => this._openUrlDetail(row)}>${row.url}</button>
                            </td>
                            <td>${this._statusTag(row.crawl_status)}</td>
                            <td>${this._enrichmentCell(row)}</td>
                            <td>${this._transportTag(typeof row.fetch_transport === 'string' ? row.fetch_transport : '')}</td>
                            <td>${this._formatDt(row.last_crawled_at)}</td>
                            <td class="mono">${textOrDash(row.last_error)}</td>
                            <td>
                                <div class="actions-cell">
                                    <button type="button" class="btn btn-sm" @click=${() => this._openUrlDetail(row)}>
                                        ${this.t('crawl_report_page.view_url_detail')}
                                    </button>
                                    <button type="button" class="btn btn-sm" @click=${() => this._recrawlUrl(row)}>
                                        ${this.t('crawl_report_page.recrawl_url')}
                                    </button>
                                </div>
                            </td>
                        </tr>
                    `)}
                </tbody>
            </table>
        `);
    }

    _renderJobsTable() {
        const { items, loading, refreshing } = this._jobs.state;
        if (loading && (!items || items.length === 0)) {
            return this._renderTableShell(false, this._renderTableLoading());
        }
        if (!items || items.length === 0) {
            return this._renderTableShell(refreshing, html`
                <div class="state">
                    <div class="state-title">${this.t('crawl_report_page.empty_jobs')}</div>
                </div>
            `);
        }
        return this._renderTableShell(refreshing, html`
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
                        <tr class=${this._rowClass('jobs', row.crawl_job_id)}>
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
        `);
    }

    _summaryErrorKind() {
        const error = this._summaryOp.state.error;
        if (!error) return '';
        if (error.includes('403')) return 'forbidden';
        if (error.includes('503')) return 'unavailable';
        return '';
    }

    _renderTabContent() {
        if (this._activeTab === 'domains') return this._renderDomainsTable();
        if (this._activeTab === 'urls') return this._renderUrlsTable();
        return this._renderJobsTable();
    }

    override render(): TemplateResult {
        const profileBundle = this._selectedProfileBundle();
        const searchIndex = profileBundle !== null && isPlainRecord(profileBundle.search_index)
            ? profileBundle.search_index
            : null;
        const indexName = searchIndex !== null && typeof searchIndex.display_name === 'string'
            ? searchIndex.display_name
            : null;
        const indexId = searchIndex !== null && typeof searchIndex.search_index_id === 'string'
            ? searchIndex.search_index_id
            : null;
        const summary = this._summaryOp.state.lastResult;
        const summaryRefreshing = this._summaryOp.state.busy && summary !== null;
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
                        <platform-button
                            variant="secondary"
                            density="compact"
                            aria-label=${this.t('crawl_report_page.refresh')}
                            ?disabled=${summaryRefreshing}
                            @click=${() => this._reloadSummaryAndActiveTab()}
                        >
                            <platform-icon name="refresh" size="16"></platform-icon>
                            ${this.t('crawl_report_page.refresh')}
                        </platform-button>
                        <platform-button
                            variant="secondary"
                            density="compact"
                            ?disabled=${!this._selectedProfileBundle()}
                            @click=${() => this._openProfileSettings()}
                        >
                            <platform-icon name="settings" size="16"></platform-icon>
                            ${this.t('crawl_report_page.profile_settings')}
                        </platform-button>
                        <div class="tick-action">
                            <platform-button
                                variant="primary"
                                density="compact"
                                ?disabled=${this._queueTickOp.state.busy}
                                ?loading=${this._queueTickOp.state.busy}
                                @click=${() => this._queueTick()}
                            >${this.t('crawl_report_page.queue_tick')}</platform-button>
                            <platform-help-hint
                                size="md"
                                .text=${this.t('crawl_report_page.queue_tick_hint')}
                            ></platform-help-hint>
                        </div>
                    </div>
                </section>

                <crawl-report-metric-strip
                    .summary=${summary}
                    .locale=${this._localeSel.value}
                    .busy=${this._summaryOp.state.busy}
                    .refreshing=${summaryRefreshing}
                    .errorKind=${this._summaryErrorKind()}
                    .countFromSummary=${(key: string) => this._countFromSummary(key)}
                ></crawl-report-metric-strip>

                <crawl-report-running-banner
                    .runningJob=${isPlainRecord(summary) ? summary.running_job : null}
                    .locale=${this._localeSel.value}
                ></crawl-report-running-banner>

                <crawl-report-charts-panel
                    .summary=${summary}
                    .jobs=${this._jobs.items}
                    .domains=${this._domains.items}
                    .locale=${this._localeSel.value}
                    .statusLabel=${(status: string) => this._statusLabel(status)}
                    .categoryLabel=${(category: string) => this._categoryLabel(category)}
                    .contentTypeLabel=${(contentType: string) => this._contentTypeLabel(contentType)}
                    .topicLabel=${(topic: string) => this._topicLabel(topic)}
                ></crawl-report-charts-panel>

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

                ${this._renderTabContent()}
            </div>
        `;
    }
}

customElements.define('frontend-crawl-report-page', FrontendCrawlReportPage);
