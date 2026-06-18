import { html, css, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { formatPlatformDate } from '@platform/lib/utils/format-platform-date.js';

export class CrawlReportStructuralPanel extends PlatformElement {
    static i18nNamespace = 'frontend';

    static properties = {
        signals: { type: Object },
        locale: { type: String },
    };

    static styles = [
        PlatformElement.styles,
        css`
            .meta-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
                gap: var(--space-3);
            }
            .meta-item {
                padding: var(--space-3);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-solid-subtle);
            }
            .meta-label {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                text-transform: uppercase;
                letter-spacing: 0.04em;
            }
            .meta-value {
                margin-top: var(--space-1);
                font-size: var(--text-sm);
                color: var(--text-primary);
                word-break: break-word;
            }
            .chip-row {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-1);
                margin-top: var(--space-1);
            }
            .chip {
                padding: 2px 8px;
                border-radius: var(--radius-full);
                font-size: var(--text-xs);
                background: var(--glass-solid-medium);
                color: var(--text-secondary);
            }
        `,
    ];

    constructor() {
        super();
        this.signals = null;
        this.locale = 'en';
    }

    _formatDate(value) {
        if (!value) return '—';
        return formatPlatformDate(value, this.locale);
    }

    _item(labelKey, value) {
        return html`
            <div class="meta-item">
                <div class="meta-label">${this.t(labelKey)}</div>
                <div class="meta-value">${value}</div>
            </div>
        `;
    }

    _chips(labelKey, values) {
        if (!Array.isArray(values) || values.length === 0) {
            return this._item(labelKey, '—');
        }
        return html`
            <div class="meta-item">
                <div class="meta-label">${this.t(labelKey)}</div>
                <div class="chip-row">
                    ${values.map((value) => html`<span class="chip">${value}</span>`)}
                </div>
            </div>
        `;
    }

    render() {
        const signals = this.signals;
        if (!signals) {
            return html`<div class="meta-value">${this.t('crawl_report_page.structural_empty')}</div>`;
        }
        const contentType = signals.content_type_hint
            ? this.t(`crawl_report_page.content_type_${signals.content_type_hint}`)
            : '—';
        return html`
            <div class="meta-grid">
                ${this._item('crawl_report_page.structural_title', signals.title || '—')}
                ${this._item('crawl_report_page.structural_content_type_hint', contentType)}
                ${this._item('crawl_report_page.structural_date_published', this._formatDate(signals.date_published))}
                ${this._item('crawl_report_page.structural_date_modified', this._formatDate(signals.date_modified))}
                ${this._item('crawl_report_page.structural_author', signals.author || '—')}
                ${this._item('crawl_report_page.structural_publisher', signals.publisher || '—')}
                ${this._item('crawl_report_page.structural_language', signals.language || '—')}
                ${this._chips('crawl_report_page.structural_category_hints', signals.category_hints)}
                ${this._chips('crawl_report_page.structural_topic_hints', signals.topic_hints)}
            </div>
        `;
    }
}

customElements.define('crawl-report-structural-panel', CrawlReportStructuralPanel);

export class CrawlReportFilterMetadataPanel extends PlatformElement {
    static i18nNamespace = 'frontend';

    static properties = {
        filterMetadata: { type: Object },
        enrichmentSnapshot: { type: Object },
        locale: { type: String },
    };

    static styles = CrawlReportStructuralPanel.styles;

    constructor() {
        super();
        this.filterMetadata = null;
        this.enrichmentSnapshot = null;
        this.locale = 'en';
    }

    _formatDate(value) {
        if (!value) return '—';
        return formatPlatformDate(value, this.locale);
    }

    _label(prefix, slug) {
        const key = `crawl_report_page.${prefix}_${slug}`;
        const translated = this.t(key);
        if (translated === key) return slug;
        return translated;
    }

    render() {
        const meta = this.filterMetadata;
        const snapshot = this.enrichmentSnapshot;
        if (!meta) {
            return html`<div class="meta-value">${this.t('crawl_report_page.enrichment_empty')}</div>`;
        }
        const topicTags = Array.isArray(meta.topic_tags) ? meta.topic_tags : [];
        const categoryPath = Array.isArray(meta.category_path) ? meta.category_path : [];
        return html`
            <div class="meta-grid">
                <div class="meta-item">
                    <div class="meta-label">${this.t('crawl_report_page.col_page_title')}</div>
                    <div class="meta-value">${snapshot?.page_title || '—'}</div>
                </div>
                <div class="meta-item">
                    <div class="meta-label">${this.t('crawl_report_page.col_content_type')}</div>
                    <div class="meta-value">${this._label('content_type', meta.content_type)}</div>
                </div>
                <div class="meta-item">
                    <div class="meta-label">${this.t('crawl_report_page.col_primary_topic')}</div>
                    <div class="meta-value">${this._label('topic', meta.primary_topic)}</div>
                </div>
                <div class="meta-item">
                    <div class="meta-label">${this.t('crawl_report_page.col_category_path')}</div>
                    <div class="meta-value">${categoryPath.length > 0
                        ? categoryPath.map((segment) => this._label('topic', segment)).join(' / ')
                        : '—'}</div>
                </div>
                <div class="meta-item">
                    <div class="meta-label">${this.t('crawl_report_page.col_language')}</div>
                    <div class="meta-value">${meta.language}</div>
                </div>
                <div class="meta-item">
                    <div class="meta-label">${this.t('crawl_report_page.col_audience')}</div>
                    <div class="meta-value">${this._label('audience', meta.audience)}</div>
                </div>
                <div class="meta-item">
                    <div class="meta-label">${this.t('crawl_report_page.col_freshness')}</div>
                    <div class="meta-value">${meta.freshness_relevance
                        ? this._label('freshness', meta.freshness_relevance)
                        : '—'}</div>
                </div>
                <div class="meta-item">
                    <div class="meta-label">${this.t('crawl_report_page.col_date_published')}</div>
                    <div class="meta-value">${this._formatDate(meta.date_published)}</div>
                </div>
                <div class="meta-item">
                    <div class="meta-label">${this.t('crawl_report_page.col_date_modified')}</div>
                    <div class="meta-value">${this._formatDate(meta.date_modified)}</div>
                </div>
                <div class="meta-item">
                    <div class="meta-label">${this.t('crawl_report_page.col_topic_tags')}</div>
                    <div class="chip-row">
                        ${topicTags.map((tag) => html`<span class="chip">${this._label('topic', tag)}</span>`)}
                    </div>
                </div>
                ${snapshot?.page_summary ? html`
                    <div class="meta-item" style="grid-column: 1 / -1;">
                        <div class="meta-label">${this.t('crawl_report_page.url_detail_page_summary')}</div>
                        <div class="meta-value">${snapshot.page_summary}</div>
                    </div>
                ` : nothing}
            </div>
        `;
    }
}

customElements.define('crawl-report-filter-metadata-panel', CrawlReportFilterMetadataPanel);
