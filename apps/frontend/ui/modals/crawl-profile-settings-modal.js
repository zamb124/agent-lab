/**
 * Модалка настроек crawl-профиля (company system): фильтры, лимиты, периоды, LLM enrichment.
 *
 * Поля API (core/crawl/models.py::CrawlProfilePatchRequest).
 */
import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/fields/platform-field.js';

export class FrontendCrawlProfileSettingsModal extends PlatformFormModal {
    static modalKind = 'frontend.crawl_profile_settings';
    static i18nNamespace = 'frontend';

    static styles = [
        ...PlatformFormModal.styles,
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

    static properties = {
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
    };

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
        this._patchOp = this.useOp('frontend/crawl_profile_patch');
    }

    willUpdate(changed) {
        super.willUpdate(changed);
        this.title = this.t('crawl_report_page.profile_settings_title');
        if (!this._initialized && this.profile) {
            this._initialized = true;
            const p = this.profile;
            this._enabled = p.enabled;
            this._refreshInterval = String(p.refresh_interval_seconds);
            this._maxUrlsPerDomain = String(p.max_urls_per_domain_per_tick);
            this._maxDomains = String(p.max_domains_per_tick);
            this._maxUrlsPerBatch = String(p.max_urls_per_batch);
            this._httpConcurrency = String(p.http_concurrency);
            this._sitemapStale = String(p.sitemap_stale_after_seconds);
            this._browserFallback = p.browser_fallback_enabled;
            this._llmEnrichment = p.llm_enrichment_enabled;
            this._denylistDomains = (p.denylist_domains || []).join('\n');
            this._includePatterns = (p.include_url_patterns || []).join('\n');
            this._excludePatterns = (p.exclude_url_patterns || []).join('\n');
            this._excludeExtensions = (p.exclude_extensions || []).join('\n');
        }
    }

    _lines(raw) {
        return raw
            .split('\n')
            .map((line) => line.trim())
            .filter((line) => line.length > 0);
    }

    _requirePositive(value, errors, key, min) {
        const num = Number(value);
        if (value === '' || Number.isNaN(num) || num < min) {
            errors[key] = this.t('crawl_report_page.err_positive');
        }
    }

    validateForm() {
        const errors = {};
        this._requirePositive(this._refreshInterval, errors, 'refresh_interval_seconds', 60);
        this._requirePositive(this._maxUrlsPerDomain, errors, 'max_urls_per_domain_per_tick', 1);
        this._requirePositive(this._maxDomains, errors, 'max_domains_per_tick', 1);
        this._requirePositive(this._maxUrlsPerBatch, errors, 'max_urls_per_batch', 1);
        this._requirePositive(this._httpConcurrency, errors, 'http_concurrency', 1);
        this._requirePositive(this._sitemapStale, errors, 'sitemap_stale_after_seconds', 3600);
        return errors;
    }

    async handleSubmit() {
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

    _intField(labelKey, value, setter, helpKey, errorKey) {
        return html`
            <div class="form-group">
                <platform-field
                    type="integer"
                    mode="edit"
                    label=${this.t(labelKey)}
                    .value=${value === '' ? null : Number(value)}
                    @change=${(e) => {
                        const next = e.detail ? e.detail.value : null;
                        setter(typeof next === 'number' ? String(next) : '');
                    }}
                ></platform-field>
                ${errorKey ? this.renderFieldError(errorKey) : null}
                ${helpKey ? html`<div class="field-help">${this.t(helpKey)}</div>` : null}
            </div>
        `;
    }

    _textField(labelKey, value, setter, helpKey) {
        return html`
            <div class="form-group">
                <platform-field
                    type="text"
                    mode="edit"
                    label=${this.t(labelKey)}
                    .value=${value}
                    @change=${(e) => setter(String(e.detail.value ?? ''))}
                ></platform-field>
                ${helpKey ? html`<div class="field-help">${this.t(helpKey)}</div>` : null}
            </div>
        `;
    }

    _boolField(labelKey, value, setter) {
        return html`
            <div class="form-group">
                <platform-field
                    type="enum"
                    label=${this.t(labelKey)}
                    .value=${value ? 'true' : 'false'}
                    .enumConfig=${{ values: this._boolOptions() }}
                    @value-changed=${(e) => { setter(e.detail.value === 'true'); this.isDirty = true; }}
                ></platform-field>
            </div>
        `;
    }

    renderBody() {
        return html`
            <form @submit=${this._onSubmit} @input=${() => { this.isDirty = true; }}>
                <div class="section-title">${this.t('crawl_report_page.section_limits')}</div>
                <div class="grid-2">
                    ${this._intField('crawl_report_page.field_refresh_interval', this._refreshInterval,
                        (v) => { this._refreshInterval = v; }, 'crawl_report_page.help_refresh_interval', 'refresh_interval_seconds')}
                    ${this._intField('crawl_report_page.field_max_urls_per_domain', this._maxUrlsPerDomain,
                        (v) => { this._maxUrlsPerDomain = v; }, null, 'max_urls_per_domain_per_tick')}
                    ${this._intField('crawl_report_page.field_max_domains', this._maxDomains,
                        (v) => { this._maxDomains = v; }, null, 'max_domains_per_tick')}
                    ${this._intField('crawl_report_page.field_max_urls_per_batch', this._maxUrlsPerBatch,
                        (v) => { this._maxUrlsPerBatch = v; }, null, 'max_urls_per_batch')}
                    ${this._intField('crawl_report_page.field_http_concurrency', this._httpConcurrency,
                        (v) => { this._httpConcurrency = v; }, null, 'http_concurrency')}
                    ${this._intField('crawl_report_page.field_sitemap_stale', this._sitemapStale,
                        (v) => { this._sitemapStale = v; }, null, 'sitemap_stale_after_seconds')}
                </div>

                <div class="section-title">${this.t('crawl_report_page.section_toggles')}</div>
                <div class="grid-2">
                    ${this._boolField('crawl_report_page.field_enabled', this._enabled, (v) => { this._enabled = v; })}
                    ${this._boolField('crawl_report_page.field_browser_fallback', this._browserFallback, (v) => { this._browserFallback = v; })}
                    ${this._boolField('crawl_report_page.field_llm_enrichment', this._llmEnrichment, (v) => { this._llmEnrichment = v; })}
                </div>

                <div class="section-title">${this.t('crawl_report_page.section_filters')}</div>
                ${this._textField('crawl_report_page.field_include_patterns', this._includePatterns,
                    (v) => { this._includePatterns = v; }, 'crawl_report_page.help_include_patterns')}
                ${this._textField('crawl_report_page.field_exclude_patterns', this._excludePatterns,
                    (v) => { this._excludePatterns = v; }, 'crawl_report_page.help_exclude_patterns')}
                ${this._textField('crawl_report_page.field_exclude_extensions', this._excludeExtensions,
                    (v) => { this._excludeExtensions = v; }, 'crawl_report_page.help_exclude_extensions')}
                ${this._textField('crawl_report_page.field_denylist_domains', this._denylistDomains,
                    (v) => { this._denylistDomains = v; }, 'crawl_report_page.help_denylist_domains')}
            </form>
        `;
    }

    renderFooter() {
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
