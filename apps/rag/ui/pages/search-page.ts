/**
 * SearchPage — семантический поиск по выбранному namespace.
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import type { OpController, ResourceController } from '@platform/lib/base/use-resource.js';

interface RagSearchResultItem {
    document_name?: unknown;
    page?: unknown;
    score?: number;
    content?: unknown;
    [key: string]: unknown;
}

interface RagSearchResult {
    results?: RagSearchResultItem[];
    [key: string]: unknown;
}
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import {
    buildAdvancedRetrievalPayloadFromPanel,
    defaultRetrievalPanelValue,
} from '@platform/lib/rag/pack_search_request_options.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-breadcrumbs.js';
import '@platform/lib/components/rag/platform-rag-retrieval-panel.js';

const LIMIT_OPTIONS = [3, 5, 10, 20];

export class SearchPage extends PlatformPage {
    static i18nNamespace = 'rag';

    declare _query: string;
    declare _selectedNamespace: string;
    declare _limit: number;
    declare _showAdvanced: boolean;
    declare _retrievalPanel: Record<string, unknown>;
    private _namespaces: ResourceController;
    private _search: OpController;
    private _searchDefaults: OpController;

    static override properties = {
        _query: { state: true },
        _selectedNamespace: { state: true },
        _limit: { state: true },
        _showAdvanced: { state: true },
        _retrievalPanel: { state: true },
    };

    static override styles = [
        PlatformPage.styles,
        buttonStyles,
        css`
            :host { display: flex; flex-direction: column; height: 100%; }
            .breadcrumbs-wrap { flex-shrink: 0; margin-bottom: var(--space-3); }
            .search-form { display: flex; flex-direction: column; gap: var(--space-4); margin-bottom: var(--space-6); }
            .form-row { display: flex; gap: var(--space-3); align-items: flex-start; }
            .form-row platform-field { flex: 1; min-width: 0; }
            .form-row .limit-field { max-width: 150px; flex: 0 1 150px; }
            .query-row {
                display: flex;
                flex-direction: row;
                align-items: flex-end;
                gap: var(--space-3);
            }
            .query-row .query-field { flex: 1; min-width: 0; }
            .advanced-toggle { align-self: flex-start; }
            .advanced-wrap {
                padding: var(--space-4);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
            }
            .results { flex: 1; display: flex; flex-direction: column; gap: var(--space-4); }
            .result-card {
                padding: var(--space-4); background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle); border-radius: var(--radius-lg);
                transition: var(--motion-transition-interactive);
            }
            .result-card:hover { background: var(--glass-solid-medium); border-color: var(--glass-border-medium); }
            .result-header { display: flex; justify-content: space-between; align-items: start; margin-bottom: var(--space-3); }
            .result-title { font-size: var(--text-base); font-weight: var(--font-semibold); color: var(--text-primary); margin-bottom: var(--space-1); }
            .result-meta { font-size: var(--text-sm); color: var(--text-tertiary); }
            .result-score {
                padding: var(--space-1) var(--space-2);
                background: var(--accent-subtle); color: var(--accent);
                border-radius: var(--radius-sm);
                font-size: var(--text-xs); font-weight: var(--font-semibold);
            }
            .result-content { font-size: var(--text-sm); color: var(--text-secondary); line-height: 1.6; }
            .empty {
                flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center;
                padding: var(--space-12); text-align: center;
            }
            .empty-text { font-size: var(--text-lg); font-weight: var(--font-semibold); color: var(--text-primary); margin-bottom: var(--space-2); }
            .empty-hint { font-size: var(--text-sm); color: var(--text-tertiary); }
        `,
    ];

    constructor() {
        super();
        this._query = '';
        this._selectedNamespace = '';
        this._limit = 5;
        this._showAdvanced = false;
        this._retrievalPanel = defaultRetrievalPanelValue();
        this._namespaces = this.useResource('rag/namespaces', { autoload: true });
        this._search = this.useOp('rag/search');
        this._searchDefaults = this.useOp('rag/search_defaults');
    }

    override connectedCallback() {
        super.connectedCallback();
        this._searchDefaults.run({});
    }

    private _platformDefaults(): Record<string, unknown> | null {
        const result = this._searchDefaults.lastResult;
        if (!result || typeof result !== 'object' || Array.isArray(result)) {
            return null;
        }
        return result as Record<string, unknown>;
    }

    private _runSearch(e: Event) {
        e.preventDefault();
        const q = typeof this._query === 'string' ? this._query.trim() : '';
        const ns = typeof this._selectedNamespace === 'string' ? this._selectedNamespace.trim() : '';
        if (q.length === 0 || ns.length === 0) {
            this.toast('search_view.fill_all_fields', { type: 'warning' });
            return;
        }
        this._search.run({
            namespace_id: ns,
            query: q,
            limit: this._limit,
            ...buildAdvancedRetrievalPayloadFromPanel(this._retrievalPanel),
        });
    }

    private _toggleAdvanced() {
        this._showAdvanced = !this._showAdvanced;
    }

    private _onRetrievalPanelChange(e: CustomEvent<{ value?: unknown }>) {
        const value = e.detail && e.detail.value;
        if (!value || typeof value !== 'object' || Array.isArray(value)) {
            throw new Error('SearchPage: invalid retrieval panel value');
        }
        this._retrievalPanel = value as Record<string, unknown>;
    }

    private _onNamespaceChange(e: CustomEvent<{ value?: unknown }>) {
        const v = e.detail && typeof e.detail.value === 'string' ? e.detail.value : '';
        this._selectedNamespace = v;
    }

    private _onLimitChange(e: CustomEvent<{ value?: unknown }>) {
        const raw = e.detail && e.detail.value != null ? String(e.detail.value) : '';
        const n = parseInt(raw, 10);
        if (!Number.isFinite(n)) {
            throw new Error('SearchPage._onLimitChange: invalid limit');
        }
        this._limit = n;
    }

    private _onQueryChange(e: CustomEvent<{ value?: unknown }>) {
        const v = e.detail && typeof e.detail.value === 'string' ? e.detail.value : '';
        this._query = v;
    }

    private _namespaceEnumConfig(namespaces: readonly Record<string, unknown>[]) {
        const opts = [{ value: '', label: this.t('search_view.select_namespace') }];
        if (!Array.isArray(namespaces)) {
            throw new Error('SearchPage._namespaceEnumConfig: namespaces must be array');
        }
        for (const ns of namespaces) {
            if (!ns || typeof ns.name !== 'string' || ns.name.length === 0) {
                throw new Error('SearchPage._namespaceEnumConfig: invalid namespace item');
            }
            opts.push({ value: ns.name, label: ns.name });
        }
        return { values: opts };
    }

    private _limitEnumConfig() {
        return {
            values: LIMIT_OPTIONS.map((n) => ({ value: String(n), label: String(n) })),
        };
    }

    private _renderResults() {
        const result = this._search.lastResult as RagSearchResult | null;
        const items = result && Array.isArray(result.results) ? result.results : [];
        if (items.length === 0) return null;
        return html`
            <div class="results">
                ${items.map((r: RagSearchResultItem) => html`
                    <div class="result-card">
                        <div class="result-header">
                            <div>
                                <div class="result-title">
                                    ${typeof r.document_name === 'string' && r.document_name.length > 0
                                        ? r.document_name
                                        : this.t('search_view.result_document_fallback')}
                                </div>
                                <div class="result-meta">
                                    ${typeof r.page === 'number'
                                        ? this.t('search_view.result_page_meta', { page: String(r.page) })
                                        : ''}
                                </div>
                            </div>
                            <div class="result-score">${(Number(r.score === undefined || r.score === null ? 0 : r.score) * 100).toFixed(1)}%</div>
                        </div>
                        <div class="result-content">${r.content}</div>
                    </div>
                `)}
            </div>
        `;
    }

    override render() {
        const namespaces = this._namespaces.items;
        const loading = this._search.busy;
        const result = this._search.lastResult as RagSearchResult | null;
        const hasResults = result && Array.isArray(result.results) && result.results.length > 0;

        return html`
            <div class="breadcrumbs-wrap">
                <platform-breadcrumbs></platform-breadcrumbs>
            </div>
            <page-header
                title=${this.t('search_view.header_title')}
                subtitle=${this.t('search_view.header_subtitle')}
            ></page-header>

            <form class="search-form" @submit=${(e: Event) => this._runSearch(e)}>
                <div class="form-row">
                    <platform-field
                        type="enum"
                        mode="edit"
                        .label=${this.t('search_view.label_namespace')}
                        .value=${this._selectedNamespace}
                        .config=${this._namespaceEnumConfig(namespaces)}
                        ?disabled=${loading}
                        @change=${(e: CustomEvent<{ value?: unknown }>) => this._onNamespaceChange(e)}
                    ></platform-field>
                    <platform-field
                        class="limit-field"
                        type="enum"
                        mode="edit"
                        .label=${this.t('search_view.label_limit')}
                        .value=${String(this._limit)}
                        .config=${this._limitEnumConfig()}
                        ?disabled=${loading}
                        @change=${(e: CustomEvent<{ value?: unknown }>) => this._onLimitChange(e)}
                    ></platform-field>
                </div>

                <div class="query-row">
                    <platform-field
                        class="query-field"
                        type="string"
                        mode="edit"
                        .label=${this.t('search_view.label_query')}
                        .placeholder=${this.t('search_view.query_placeholder')}
                        .value=${this._query}
                        ?disabled=${loading}
                        @change=${(e: CustomEvent<{ value?: unknown }>) => this._onQueryChange(e)}
                    ></platform-field>
                    <button type="submit" class="btn btn-primary search-btn" ?disabled=${loading}>
                        ${loading
                            ? this.t('search_view.searching')
                            : this.t('search_view.find_button')}
                    </button>
                </div>

                <button
                    type="button"
                    class="btn btn-secondary advanced-toggle"
                    @click=${() => this._toggleAdvanced()}
                >
                    ${this._showAdvanced
                        ? this.t('search_view.toggle_advanced_hide')
                        : this.t('search_view.toggle_advanced')}
                </button>

                ${this._showAdvanced ? html`
                    <div class="advanced-wrap">
                        <platform-rag-retrieval-panel
                            .value=${this._retrievalPanel}
                            .platformDefaults=${this._platformDefaults()}
                            ?disabled=${loading}
                            @change=${(e: CustomEvent<{ value?: unknown }>) => this._onRetrievalPanelChange(e)}
                        ></platform-rag-retrieval-panel>
                    </div>
                ` : ''}
            </form>

            ${hasResults ? this._renderResults() : (loading ? '' : html`
                <div class="empty">
                    <div class="empty-text">${this.t('search_view.empty_no_results_title')}</div>
                    <div class="empty-hint">${this.t('search_view.empty_hint')}</div>
                </div>
            `)}
        `;
    }
}

customElements.define('rag-search-page', SearchPage);
