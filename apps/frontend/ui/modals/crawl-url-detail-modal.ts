import { html, css, nothing } from 'lit';
import { unsafeHTML } from 'lit/directives/unsafe-html.js';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import { markdownToHtml } from '@platform/lib/utils/markdown.js';
import { formatPlatformDateTime } from '@platform/lib/utils/format-platform-date.js';
import '@platform/lib/components/glass-spinner.js';
import '../components/crawl-report/crawl-report-metadata-panels.js';
import type {CSSResultGroup, PropertyDeclarations, PropertyValues} from 'lit';
import type { OpController } from '@platform/lib/base/use-resource.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';

function detailRecord(value: unknown): Record<string, any> | null {
    if (!isPlainRecord(value)) return null;
    const row: Record<string, any> = {};
    for (const [key, field] of Object.entries(value)) row[key] = field;
    return row;
}

function textOrDash(value: unknown): string {
    if (typeof value === 'string' && value.length > 0) return value;
    if (typeof value === 'number' && Number.isFinite(value) && value !== 0) return String(value);
    return '—';
}

function presentValue(value: unknown): unknown {
    if (value === undefined || value === null || value === false || value === 0 || value === '') return null;
    if (typeof value === 'number' && !Number.isFinite(value)) return null;
    return value;
}

const DETAIL_TABS = Object.freeze(['metadata', 'structural', 'enrichment', 'fetched', 'indexed']);

export class FrontendCrawlUrlDetailModal extends PlatformModal {
    static modalKind = 'frontend.crawl_url_detail';
    static i18nNamespace = 'frontend';

    static override properties: PropertyDeclarations = {
        ...PlatformModal.properties,
        crawl_url_id: { type: String },
        crawl_profile_id: { type: String },
        _activeTab: { state: true },
        _loaded: { state: true },
    }
    declare crawl_url_id: string;
    declare crawl_profile_id: string;
    declare _activeTab: string;
    declare _loaded: boolean;
;

    static override styles: CSSResultGroup = [
        PlatformModal.styles,
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
        this._detailOp = this.useOp('search/crawl_url_detail');
        this._localeSel = this.select((state: Record<string, any>) => {
            const locale = state.i18n.locale;
            if (typeof locale !== 'string' || locale.length === 0) {
                throw new Error('crawl-url-detail-modal: i18n.locale is required');
            }
            return locale;
        });
        this.size = 'lg';
    }
    private _detailOp: OpController;
    private _localeSel: SelectController<any>;


    override willUpdate(changed: PropertyValues<this>): void {
        super.willUpdate(changed);
        this.title = this.t('crawl_report_page.url_detail_title');
    }

    override updated(changed: PropertyValues<this>): void {
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

    _formatDt(value: unknown) {
        if (!value) return '—';
        return formatPlatformDateTime(value as string | number | Date, this._localeSel.value as string);
    }

    _renderMetadata(detail: Record<string, any>) {
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
                    <div class="meta-value mono">${textOrDash(url.document_id)}</div>
                </div>
                <div class="meta-item">
                    <div class="meta-label">${this.t('crawl_report_page.col_last_crawled')}</div>
                    <div class="meta-value">${this._formatDt(url.last_crawled_at)}</div>
                </div>
                <div class="meta-item">
                    <div class="meta-label">${this.t('crawl_report_page.col_error')}</div>
                    <div class="meta-value mono">${textOrDash(url.last_error)}</div>
                </div>
            </div>
        `;
    }

    _renderMarkdownTab(markdown: string, emptyKey: string) {
        if (!markdown || !markdown.trim()) {
            return html`<div class="state">${this.t(emptyKey)}</div>`;
        }
        const htmlContent = markdownToHtml(markdown);
        return html`<div class="markdown-preview">${unsafeHTML(htmlContent)}</div>`;
    }

    _renderIndexedTab(detail: Record<string, any>) {
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

    _detailForCurrentUrl(): Record<string, any> | null {
        const detail = detailRecord(this._detailOp.state.lastResult);
        if (detail === null) return null;
        const url = detailRecord(detail.url);
        if (url === null || url.crawl_url_id !== this.crawl_url_id) return null;
        return detail;
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
                    .filterMetadata=${(() => {
                        const indexed = detail.indexed_content;
                        const snapshot = detail.url.enrichment_snapshot;
                        const fromIndex = presentValue(indexed && typeof indexed === 'object' ? indexed.filter_metadata : undefined);
                        if (fromIndex !== null) return fromIndex;
                        return presentValue(snapshot && typeof snapshot === 'object' ? snapshot.filter_metadata : undefined);
                    })()}
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

    override renderBody() {
        return this._renderBodyContent();
    }
}

customElements.define('frontend-crawl-url-detail-modal', FrontendCrawlUrlDetailModal);
registerModalKind(FrontendCrawlUrlDetailModal.modalKind, 'frontend-crawl-url-detail-modal');
