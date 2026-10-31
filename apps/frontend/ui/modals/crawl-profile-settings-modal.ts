/**
 * Модалка настроек crawl-профиля (company system): фильтры, лимиты, периоды, LLM enrichment.
 *
 * Поля API (apps/search/models/contracts.py::CrawlProfilePatchRequest).
 */
import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/fields/platform-field.js';
import type {CSSResultGroup, PropertyDeclarations, PropertyValues} from 'lit';
import type { OpControllerOf } from '@platform/lib/base/use-resource.js';
import type { PlatformFactoryRegistry } from '@platform/lib/events/factory-registry.js';
import type { CrawlProfile } from '@platform/lib/events/wire/search.gen.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';

function joinedLines(value: unknown, label: string): string {
    if (value === undefined || value === null) return '';
    if (!Array.isArray(value)) throw new Error(`crawl profile: ${label} must be an array`);
    return value.map((item) => String(item)).join('\n');
}

export class FrontendCrawlProfileSettingsModal extends PlatformFormModal {
    static modalKind = 'frontend.crawl_profile_settings';
    static i18nNamespace = 'frontend';

    static override styles: CSSResultGroup = [
        PlatformFormModal.styles,
        css`
            .field-help {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                margin-top: 4px;
            }
            .section-title {
                font-weight: var(--font-semibold);
                color: var(--text-secondary);
                margin: var(--space-4) 0 var(--space-2);
            }
            .grid-2 {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: var(--space-3);
            }
        `,
    ];

    static override properties: PropertyDeclarations = {
        ...PlatformFormModal.properties,
        crawl_profile_id: { type: String },
        profile: { type: Object },
        _enabled: { state: true },
        _refreshInterval: { state: true },
        _maxUrlsPerDomain: { state: true },
        _maxDomains: { state: true },
        _maxUrlsPerBatch: { state: true },
        _httpConcurrency: { state: true },
        _sitemapStale: { state: true },
        _browserFallback: { state: true },
        _llmEnrichment: { state: true },
        _denylistDomains: { state: true },
        _includePatterns: { state: true },
        _excludePatterns: { state: true },
        _excludeExtensions: { state: true },
        _initialized: { state: true },
    }
    declare crawl_profile_id: string;
    declare profile: CrawlProfile | null;
    declare _enabled: boolean;
    declare _refreshInterval: string;
    declare _maxUrlsPerDomain: string;
    declare _maxDomains: string;
    declare _maxUrlsPerBatch: string;
    declare _httpConcurrency: string;
    declare _sitemapStale: string;
    declare _browserFallback: boolean;
    declare _llmEnrichment: boolean;
    declare _denylistDomains: string;
    declare _includePatterns: string;
    declare _excludePatterns: string;
    declare _excludeExtensions: string;
    declare _initialized: boolean;
;

    constructor() {
        super();
        this.crawl_profile_id = '';
        this.profile = null;
        this._enabled = true;
        this._refreshInterval = '';
        this._maxUrlsPerDomain = '';
        this._maxDomains = '';
        this._maxUrlsPerBatch = '';
        this._httpConcurrency = '';
        this._sitemapStale = '';
        this._browserFallback = true;
        this._llmEnrichment = false;
        this._denylistDomains = '';
        this._includePatterns = '';
        this._excludePatterns = '';
        this._excludeExtensions = '';
        this._initialized = false;
        this.size = 'lg';
        this._patchOp = this.useOp('search/crawl_profile_patch');
    }
    private _patchOp: OpControllerOf<PlatformFactoryRegistry['search/crawl_profile_patch']>;


    override willUpdate(changed: PropertyValues<this>): void {
        super.willUpdate(changed);
        this.title = this.t('crawl_report_page.profile_settings_title');
        if (!this._initialized && this.profile) {
            this._initialized = true;
            const p = this.profile;
            this._enabled = p.enabled ?? true;
            this._refreshInterval = String(p.refresh_interval_seconds);
            this._maxUrlsPerDomain = String(p.max_urls_per_domain_per_tick);
            this._maxDomains = String(p.max_domains_per_tick);
            this._maxUrlsPerBatch = String(p.max_urls_per_batch);
            this._httpConcurrency = String(p.http_concurrency);
            this._sitemapStale = String(p.sitemap_stale_after_seconds);
            this._browserFallback = p.browser_fallback_enabled;
            this._llmEnrichment = p.llm_enrichment_enabled ?? false;
            this._denylistDomains = joinedLines(p.denylist_domains, 'denylist_domains');
            this._includePatterns = joinedLines(p.include_url_patterns, 'include_url_patterns');
            this._excludePatterns = joinedLines(p.exclude_url_patterns, 'exclude_url_patterns');
            this._excludeExtensions = joinedLines(p.exclude_extensions, 'exclude_extensions');
        }
    }

    _lines(raw: string) {
        return raw
            .split('\n')
            .map((line) => line.trim())
            .filter((line) => line.length > 0);
    }

    _requirePositive(value: string, errors: Record<string, string>, key: string, min: number) {
        const num = Number(value);
        if (value === '' || Number.isNaN(num) || num < min) {
            errors[key] = this.t('crawl_report_page.err_positive');
        }
    }

    override validateForm(): Record<string, string> {
        const errors: Record<string, string> = {};
        this._requirePositive(this._refreshInterval, errors, 'refresh_interval_seconds', 60);
        this._requirePositive(this._maxUrlsPerDomain, errors, 'max_urls_per_domain_per_tick', 1);
        this._requirePositive(this._maxDomains, errors, 'max_domains_per_tick', 1);
        this._requirePositive(this._maxUrlsPerBatch, errors, 'max_urls_per_batch', 1);
        this._requirePositive(this._httpConcurrency, errors, 'http_concurrency', 1);
        this._requirePositive(this._sitemapStale, errors, 'sitemap_stale_after_seconds', 3600);
        return errors;
    }

    override async handleSubmit() {
        this._patchOp.run({
            crawl_profile_id: this.crawl_profile_id,
            enabled: this._enabled,
            refresh_interval_seconds: Number(this._refreshInterval),
            max_urls_per_domain_per_tick: Number(this._maxUrlsPerDomain),
            max_domains_per_tick: Number(this._maxDomains),
            max_urls_per_batch: Number(this._maxUrlsPerBatch),
            http_concurrency: Number(this._httpConcurrency),
            sitemap_stale_after_seconds: Number(this._sitemapStale),
            browser_fallback_enabled: this._browserFallback,
            llm_enrichment_enabled: this._llmEnrichment,
            denylist_domains: this._lines(this._denylistDomains),
            include_url_patterns: this._lines(this._includePatterns),
            exclude_url_patterns: this._lines(this._excludePatterns),
            exclude_extensions: this._lines(this._excludeExtensions),
        });
        this.closeAfterSave();
    }

    _boolOptions() {
        return [
            { value: 'true', label: this.t('crawl_report_page.bool_yes') },
            { value: 'false', label: this.t('crawl_report_page.bool_no') },
        ];
    }

    _intField(labelKey: string, value: string, setter: (v: string) => void, helpKey: string | null, errorKey: string) {
        return html`
            <div class="form-group">
                <platform-field
                    type="integer"
                    mode="edit"
                    label=${this.t(labelKey)}
                    .value=${value === '' ? null : Number(value)}
                    .error=${errorKey ? this.fieldError(errorKey) : ''}
                    @change=${(e: CustomEvent) => {
                        const next = e.detail ? e.detail.value : null;
                        setter(typeof next === 'number' ? String(next) : '');
                    }}
                ></platform-field>
                ${helpKey ? html`<div class="field-help">${this.t(helpKey)}</div>` : null}
            </div>
        `;
    }

    _textField(labelKey: string, value: string, setter: (v: string) => void, helpKey: string | null) {
        return html`
            <div class="form-group">
                <platform-field
                    type="text"
                    mode="edit"
                    label=${this.t(labelKey)}
                    .value=${value}
                    @change=${(e: CustomEvent) => {
                        if (!isPlainRecord(e.detail)) throw new Error('crawl profile: detail.value required');
                        const raw = e.detail.value;
                        setter(raw === undefined || raw === null ? '' : String(raw));
                    }}
                ></platform-field>
                ${helpKey ? html`<div class="field-help">${this.t(helpKey)}</div>` : null}
            </div>
        `;
    }

    _boolField(labelKey: string, value: boolean, setter: (v: boolean) => void) {
        return html`
            <div class="form-group">
                <platform-field
                    type="enum"
                    label=${this.t(labelKey)}
                    .value=${value ? 'true' : 'false'}
                    .enumConfig=${{ values: this._boolOptions() }}
                    @value-changed=${(e: CustomEvent) => { setter(e.detail.value === 'true'); this.isDirty = true; }}
                ></platform-field>
            </div>
        `;
    }

    override renderBody() {
        return html`
            <form @submit=${this._onSubmit} @input=${() => { this.isDirty = true; }}>
                <div class="section-title">${this.t('crawl_report_page.section_limits')}</div>
                <div class="grid-2">
                    ${this._intField('crawl_report_page.field_refresh_interval', this._refreshInterval,
                        (v: string) => { this._refreshInterval = v; }, 'crawl_report_page.help_refresh_interval', 'refresh_interval_seconds')}
                    ${this._intField('crawl_report_page.field_max_urls_per_domain', this._maxUrlsPerDomain,
                        (v: string) => { this._maxUrlsPerDomain = v; }, null, 'max_urls_per_domain_per_tick')}
                    ${this._intField('crawl_report_page.field_max_domains', this._maxDomains,
                        (v: string) => { this._maxDomains = v; }, null, 'max_domains_per_tick')}
                    ${this._intField('crawl_report_page.field_max_urls_per_batch', this._maxUrlsPerBatch,
                        (v: string) => { this._maxUrlsPerBatch = v; }, null, 'max_urls_per_batch')}
                    ${this._intField('crawl_report_page.field_http_concurrency', this._httpConcurrency,
                        (v: string) => { this._httpConcurrency = v; }, null, 'http_concurrency')}
                    ${this._intField('crawl_report_page.field_sitemap_stale', this._sitemapStale,
                        (v: string) => { this._sitemapStale = v; }, null, 'sitemap_stale_after_seconds')}
                </div>

                <div class="section-title">${this.t('crawl_report_page.section_toggles')}</div>
                <div class="grid-2">
                    ${this._boolField('crawl_report_page.field_enabled', this._enabled, (v: boolean) => { this._enabled = v; })}
                    ${this._boolField('crawl_report_page.field_browser_fallback', this._browserFallback, (v: boolean) => { this._browserFallback = v; })}
                    ${this._boolField('crawl_report_page.field_llm_enrichment', this._llmEnrichment, (v: boolean) => { this._llmEnrichment = v; })}
                </div>

                <div class="section-title">${this.t('crawl_report_page.section_filters')}</div>
                ${this._textField('crawl_report_page.field_include_patterns', this._includePatterns,
                    (v: string) => { this._includePatterns = v; }, 'crawl_report_page.help_include_patterns')}
                ${this._textField('crawl_report_page.field_exclude_patterns', this._excludePatterns,
                    (v: string) => { this._excludePatterns = v; }, 'crawl_report_page.help_exclude_patterns')}
                ${this._textField('crawl_report_page.field_exclude_extensions', this._excludeExtensions,
                    (v: string) => { this._excludeExtensions = v; }, 'crawl_report_page.help_exclude_extensions')}
                ${this._textField('crawl_report_page.field_denylist_domains', this._denylistDomains,
                    (v: string) => { this._denylistDomains = v; }, 'crawl_report_page.help_denylist_domains')}
            </form>
        `;
    }

    override renderFooter() {
        return html`
            <div class="form-actions">
                <button type="button" class="btn btn-secondary" @click=${() => this.close()}>
                    ${this.t('crawl_report_page.cancel')}
                </button>
                <button type="button" class="btn btn-primary" ?disabled=${this.loading} @click=${() => this._performSave()}>
                    ${this.t('crawl_report_page.save')}
                </button>
            </div>
        `;
    }
}

customElements.define('frontend-crawl-profile-settings-modal', FrontendCrawlProfileSettingsModal);
registerModalKind(FrontendCrawlProfileSettingsModal.modalKind, 'frontend-crawl-profile-settings-modal');
