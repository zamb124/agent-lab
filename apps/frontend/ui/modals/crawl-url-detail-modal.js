import { html, css, nothing } from 'lit';
import { unsafeHTML } from 'lit/directives/unsafe-html.js';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import { flowsChatMarkdownToHtml } from '@platform/lib/flows-chat/markdown.js';
import { formatPlatformDateTime } from '@platform/lib/utils/format-platform-date.js';
import '@platform/lib/components/glass-spinner.js';
import '../components/crawl-report/crawl-report-metadata-panels.js';

const DETAIL_TABS = Object.freeze(['metadata', 'structural', 'enrichment', 'fetched', 'indexed']);

export class FrontendCrawlUrlDetailModal extends PlatformModal {
    static modalKind = 'frontend.crawl_url_detail';
    static i18nNamespace = 'frontend';

    static properties = {
        ...PlatformModal.properties,
        crawl_url_id: { type: String },
        crawl_profile_id: { type: String },
        _activeTab: { state: true },
        _loaded: { state: true },
    };

    static styles = [
        ...PlatformModal.styles,
        css`
            .tabs {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
                margin-bottom: var(--space-4);
                border-bottom: 1px solid var(--glass-border-subtle);
            }
            .tab {
                padding: var(--space-2) var(--space-3);
                background: none;
                border: none;
                border-bottom: 2px solid transparent;
                margin-bottom: -1px;
                color: var(--text-tertiary);
                cursor: pointer;
                font-size: var(--text-sm);
            }
            .tab[aria-selected="true"] {
                color: var(--text-primary);
                border-bottom-color: var(--accent);
                font-weight: var(--font-semibold);
            }
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
            .markdown-preview {
                padding: var(--space-4);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-solid-subtle);
                max-height: 420px;
                overflow: auto;
                font-size: var(--text-sm);
                line-height: 1.55;
            }
            .markdown-preview :is(p, ul, ol, pre, blockquote) {
                margin: 0 0 var(--space-3);
            }
            .state {
                padding: var(--space-6);
                text-align: center;
                color: var(--text-tertiary);
            }
            .loading {
                display: flex;
                justify-content: center;
                padding: var(--space-8);
            }
            .mono {
                font-family: var(--font-mono);
                font-size: var(--text-xs);
            }
        `,
    ];

    constructor() {
        super();
        this.crawl_url_id = '';
        this.crawl_profile_id = '';
        this._activeTab = 'metadata';
        this._loaded = false;
        this._detailOp = this.useOp('frontend/crawl_url_detail');
        this._localeSel = this.select((state) => {
            const locale = state.i18n.locale;
            if (typeof locale !== 'string' || locale.length === 0) {
                throw new Error('crawl-url-detail-modal: i18n.locale is required');
            }
            return locale;
        });
        this.size = 'lg';
    }

    willUpdate(changed) {
        super.willUpdate(changed);
        this.title = this.t('crawl_report_page.url_detail_title');
    }

    updated(changed) {
        super.updated(changed);
        if ((changed.has('crawl_url_id') || changed.has('crawl_profile_id')) && this.crawl_url_id && this.crawl_profile_id) {
            this._loaded = false;
        }
        if (!this._loaded && this.crawl_url_id && this.crawl_profile_id) {
            this._loaded = true;
            this._detailOp.run({
                crawl_url_id: this.crawl_url_id,
                crawl_profile_id: this.crawl_profile_id,
            });
        }
    }

    _formatDt(value) {
        if (!value) return '—';
        return formatPlatformDateTime(value, this._localeSel.value);
    }

    _renderMetadata(detail) {
        const url = detail.url;
        return html`
            <div class="meta-grid">
                <div class="meta-item">
                    <div class="meta-label">${this.t('crawl_report_page.col_url')}</div>
                    <div class="meta-value mono">${url.url}</div>
                </div>
                <div class="meta-item">
                    <div class="meta-label">${this.t('crawl_report_page.col_domain')}</div>
                    <div class="meta-value">${url.domain}</div>
                </div>
                <div class="meta-item">
                    <div class="meta-label">${this.t('crawl_report_page.col_status')}</div>
                    <div class="meta-value">${this.t(`crawl_report_page.status_${url.crawl_status}`)}</div>
                </div>
                <div class="meta-item">
                    <div class="meta-label">${this.t('crawl_report_page.col_transport')}</div>
                    <div class="meta-value">${url.fetch_transport
                        ? this.t(`crawl_report_page.transport_${url.fetch_transport}`)
                        : '—'}</div>
                </div>
                <div class="meta-item">
                    <div class="meta-label">${this.t('crawl_report_page.url_detail_document_id')}</div>
                    <div class="meta-value mono">${url.document_id || '—'}</div>
                </div>
                <div class="meta-item">
                    <div class="meta-label">${this.t('crawl_report_page.col_last_crawled')}</div>
                    <div class="meta-value">${this._formatDt(url.last_crawled_at)}</div>
                </div>
                <div class="meta-item">
                    <div class="meta-label">${this.t('crawl_report_page.col_error')}</div>
                    <div class="meta-value mono">${url.last_error || '—'}</div>
                </div>
            </div>
        `;
    }

    _renderMarkdownTab(markdown, emptyKey) {
        if (!markdown || !markdown.trim()) {
            return html`<div class="state">${this.t(emptyKey)}</div>`;
        }
        const htmlContent = flowsChatMarkdownToHtml(markdown);
        return html`<div class="markdown-preview">${unsafeHTML(htmlContent)}</div>`;
    }

    _renderIndexedTab(detail) {
        const indexed = detail.indexed_content;
        if (!detail.url.document_id) {
            return html`<div class="state">${this.t('crawl_report_page.url_detail_indexed_not_ready')}</div>`;
        }
        if (!indexed) {
            return html`<div class="state">${this.t('crawl_report_page.url_detail_indexed_unavailable')}</div>`;
        }
        return html`
            ${indexed.filter_metadata ? html`
                <crawl-report-filter-metadata-panel
                    style="margin-bottom: var(--space-4); display: block;"
                    .filterMetadata=${indexed.filter_metadata}
                    .enrichmentSnapshot=${{
                        page_title: detail.url.enrichment_snapshot?.page_title || indexed.document_name,
                        page_summary: indexed.page_summary,
                        filter_metadata: indexed.filter_metadata,
                    }}
                    .locale=${this._localeSel.value}
                ></crawl-report-filter-metadata-panel>
            ` : nothing}
            ${this._renderMarkdownTab(indexed.markdown, 'crawl_report_page.url_detail_indexed_unavailable')}
        `;
    }

    _detailForCurrentUrl() {
        const { lastResult } = this._detailOp.state;
        if (!lastResult || lastResult.url?.crawl_url_id !== this.crawl_url_id) {
            return null;
        }
        return lastResult;
    }

    _renderBodyContent() {
        const { busy, error } = this._detailOp.state;
        const detail = this._detailForCurrentUrl();
        if (busy && !detail) {
            return html`<div class="loading"><glass-spinner size="sm"></glass-spinner></div>`;
        }
        if (error && error.includes('404')) {
            return html`<div class="state">${this.t('crawl_report_page.url_detail_not_found')}</div>`;
        }
        if (!detail) {
            if (busy) {
                return html`<div class="loading"><glass-spinner size="sm"></glass-spinner></div>`;
            }
            return html`<div class="state">${this.t('crawl_report_page.url_detail_unavailable')}</div>`;
        }
        return html`
            <div class="tabs" role="tablist">
                ${DETAIL_TABS.map((tab) => html`
                    <button
                        type="button"
                        class="tab"
                        role="tab"
                        aria-selected=${this._activeTab === tab ? 'true' : 'false'}
                        @click=${() => { this._activeTab = tab; }}
                    >${this.t(`crawl_report_page.url_detail_tab_${tab}`)}</button>
                `)}
            </div>
            ${this._activeTab === 'metadata' ? this._renderMetadata(detail) : nothing}
            ${this._activeTab === 'structural' ? html`
                <crawl-report-structural-panel
                    .signals=${detail.url.structural_signals}
                    .locale=${this._localeSel.value}
                ></crawl-report-structural-panel>
            ` : nothing}
            ${this._activeTab === 'enrichment' ? html`
                <crawl-report-filter-metadata-panel
                    .filterMetadata=${detail.indexed_content?.filter_metadata || detail.url.enrichment_snapshot?.filter_metadata || null}
                    .enrichmentSnapshot=${detail.url.enrichment_snapshot || (detail.indexed_content?.filter_metadata ? {
                        page_title: detail.indexed_content.document_name,
                        page_summary: detail.indexed_content.page_summary,
                        filter_metadata: detail.indexed_content.filter_metadata,
                    } : null)}
                    .locale=${this._localeSel.value}
                ></crawl-report-filter-metadata-panel>
            ` : nothing}
            ${this._activeTab === 'fetched' ? html`
                ${detail.extract_title ? html`
                    <div class="meta-item" style="margin-bottom: var(--space-3);">
                        <div class="meta-label">${this.t('crawl_report_page.url_detail_extract_title')}</div>
                        <div class="meta-value">${detail.extract_title}</div>
                    </div>
                ` : nothing}
                ${this._renderMarkdownTab(detail.extract_markdown, 'crawl_report_page.url_detail_fetched_empty')}
            ` : nothing}
            ${this._activeTab === 'indexed' ? this._renderIndexedTab(detail) : nothing}
        `;
    }

    renderBody() {
        return this._renderBodyContent();
    }
}

customElements.define('frontend-crawl-url-detail-modal', FrontendCrawlUrlDetailModal);
registerModalKind(FrontendCrawlUrlDetailModal.modalKind, 'frontend-crawl-url-detail-modal');
