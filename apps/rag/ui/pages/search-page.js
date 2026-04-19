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
import { formStyles } from '@platform/lib/styles/shared/form.styles.js';
import '@platform/lib/components/layout/page-header.js';
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
        formStyles,
        css`
            :host { display: flex; flex-direction: column; height: 100%; }
            .breadcrumbs-wrap { flex-shrink: 0; margin-bottom: var(--space-3); }
            .search-form { display: flex; flex-direction: column; gap: var(--space-4); margin-bottom: var(--space-6); }
            .form-row { display: flex; gap: var(--space-3); }
            .search-input-wrapper { position: relative; }
            .search-input { width: 100%; padding-right: 100px; }
            .search-btn { position: absolute; right: 4px; top: 4px; bottom: 4px; }
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
        if (!this._query || !this._selectedNamespace) {
            this.toast('search_view.fill_all_fields', { type: 'warning' });
            return;
        }
        this._search.run({
            namespaceId: this._selectedNamespace,
            query: this._query,
            limit: this._limit,
        });
    }

    _onNamespaceChange(e) { this._selectedNamespace = e.target.value; }
    _onLimitChange(e) { this._limit = parseInt(e.target.value, 10); }
    _onQueryInput(e) { this._query = e.target.value; }

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
                    <div class="form-group" style="flex: 1;">
                        <label class="form-label">${this.t('search_view.label_namespace')}</label>
                        <select class="form-select"
                                @change=${this._onNamespaceChange}
                                .value=${this._selectedNamespace}>
                            <option value="">${this.t('search_view.select_namespace')}</option>
                            ${namespaces.map((ns) => html`
                                <option value=${ns.name}>${ns.name}</option>
                            `)}
                        </select>
                    </div>
                    <div class="form-group" style="max-width: 150px;">
                        <label class="form-label">${this.t('search_view.label_limit')}</label>
                        <select class="form-select"
                                @change=${this._onLimitChange}
                                .value=${String(this._limit)}>
                            ${LIMIT_OPTIONS.map((n) => html`<option value=${n}>${n}</option>`)}
                        </select>
                    </div>
                </div>

                <div class="form-group">
                    <label class="form-label">${this.t('search_view.label_query')}</label>
                    <div class="search-input-wrapper">
                        <input class="form-input search-input"
                               type="text"
                               placeholder=${this.t('search_view.query_placeholder')}
                               .value=${this._query}
                               @input=${this._onQueryInput} />
                        <button type="submit" class="btn btn-primary search-btn" ?disabled=${loading}>
                            ${loading
                                ? this.t('search_view.searching')
                                : this.t('search_view.find_button')}
                        </button>
                    </div>
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
