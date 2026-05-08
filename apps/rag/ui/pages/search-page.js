/**
 * SearchPage — семантический поиск по выбранному namespace.
 *
 * Список namespaces — `useResource('rag/namespaces')` (autoload), запрос —
 * `useOp('rag/search')`. Локальные UI-state поля (query/limit/выбранный
 * namespace) объявлены через `static properties` с `state: true`.
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-breadcrumbs.js';

const LIMIT_OPTIONS = [3, 5, 10, 20];

export class SearchPage extends PlatformPage {
    static i18nNamespace = 'rag';

    static properties = {
        _query: { state: true },
        _selectedNamespace: { state: true },
        _limit: { state: true },
    };

    static styles = [
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
            .results { flex: 1; display: flex; flex-direction: column; gap: var(--space-4); }
            .result-card {
                padding: var(--space-4); background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle); border-radius: var(--radius-lg);
                transition: all var(--duration-fast);
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
        this._namespaces = this.useResource('rag/namespaces', { autoload: true });
        this._search = this.useOp('rag/search');
    }

    _runSearch(e) {
        e.preventDefault();
        const q = typeof this._query === 'string' ? this._query.trim() : '';
        const ns = typeof this._selectedNamespace === 'string' ? this._selectedNamespace.trim() : '';
        if (q.length === 0 || ns.length === 0) {
            this.toast('search_view.fill_all_fields', { type: 'warning' });
            return;
        }
        this._search.run({
            namespaceId: ns,
            query: q,
            limit: this._limit,
        });
    }

    _onNamespaceChange(e) {
        const v = e.detail && typeof e.detail.value === 'string' ? e.detail.value : '';
        this._selectedNamespace = v;
    }

    _onLimitChange(e) {
        const raw = e.detail && e.detail.value != null ? String(e.detail.value) : '';
        const n = parseInt(raw, 10);
        if (!Number.isFinite(n)) {
            throw new Error('SearchPage._onLimitChange: invalid limit');
        }
        this._limit = n;
    }

    _onQueryChange(e) {
        const v = e.detail && typeof e.detail.value === 'string' ? e.detail.value : '';
        this._query = v;
    }

    _namespaceEnumConfig(namespaces) {
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

    _limitEnumConfig() {
        return {
            values: LIMIT_OPTIONS.map((n) => ({ value: String(n), label: String(n) })),
        };
    }

    _renderResults() {
        const result = this._search.lastResult;
        const items = result && Array.isArray(result.results) ? result.results : [];
        if (items.length === 0) return null;
        return html`
            <div class="results">
                ${items.map((r) => html`
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
                            <div class="result-score">${(r.score * 100).toFixed(1)}%</div>
                        </div>
                        <div class="result-content">${r.content}</div>
                    </div>
                `)}
            </div>
        `;
    }

    render() {
        const namespaces = this._namespaces.items;
        const loading = this._search.busy;
        const result = this._search.lastResult;
        const hasResults = result && Array.isArray(result.results) && result.results.length > 0;

        return html`
            <div class="breadcrumbs-wrap">
                <platform-breadcrumbs></platform-breadcrumbs>
            </div>
            <page-header
                title=${this.t('search_view.header_title')}
                subtitle=${this.t('search_view.header_subtitle')}
            ></page-header>

            <form class="search-form" @submit=${this._runSearch.bind(this)}>
                <div class="form-row">
                    <platform-field
                        type="enum"
                        mode="edit"
                        .label=${this.t('search_view.label_namespace')}
                        .value=${this._selectedNamespace}
                        .config=${this._namespaceEnumConfig(namespaces)}
                        ?disabled=${loading}
                        @change=${this._onNamespaceChange}
                    ></platform-field>
                    <platform-field
                        class="limit-field"
                        type="enum"
                        mode="edit"
                        .label=${this.t('search_view.label_limit')}
                        .value=${String(this._limit)}
                        .config=${this._limitEnumConfig()}
                        ?disabled=${loading}
                        @change=${this._onLimitChange}
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
                        @change=${this._onQueryChange}
                    ></platform-field>
                    <button type="submit" class="btn btn-primary search-btn" ?disabled=${loading}>
                        ${loading
                            ? this.t('search_view.searching')
                            : this.t('search_view.find_button')}
                    </button>
                </div>
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
