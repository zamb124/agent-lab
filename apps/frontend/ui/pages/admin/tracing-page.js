/**
 * Admin tracing page (system) — поиск spans с typeahead-подсказками
 * по 6 фасетам и просмотр дерева одного трейса в выезжающем drawer.
 *
 * Доступно только при активной компании system. 503 → unavailable state.
 */
import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-user-chip.js';

const FACETS = Object.freeze([
    { key: 'companies',   field: 'company_id',     labelKey: 'tracing_page.filter_company' },
    { key: 'users',       field: 'user_id',        labelKey: 'tracing_page.filter_user' },
    { key: 'services',    field: 'service_name',   labelKey: 'tracing_page.filter_service' },
    { key: 'namespaces',  field: 'namespace',      labelKey: 'tracing_page.filter_namespace' },
    { key: 'operations',  field: 'operation_name', labelKey: 'tracing_page.filter_operation' },
    { key: 'event_types', field: 'event_type',     labelKey: 'tracing_page.filter_event' },
]);

export class FrontendTracingPage extends PlatformPage {
    static properties = {
        _activeFacet: { state: true },
        _draftFilters: { state: true },
    };

    static styles = [
        PlatformPage.styles,
        css`
            :host { display: block; }

            .filters {
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: var(--space-3);
                margin-bottom: var(--space-3);
                background: var(--glass-solid-subtle);
                padding: var(--space-3);
                border-radius: var(--radius-lg);
                border: 1px solid var(--glass-border-subtle);
            }
            .field { position: relative; display: flex; flex-direction: column; gap: var(--space-1); }
            .field label {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                text-transform: uppercase;
                letter-spacing: 0.05em;
            }
            input {
                background: var(--glass-solid-medium);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                padding: var(--space-2) var(--space-3);
                color: var(--text-primary);
                font-size: var(--text-sm);
                width: 100%;
                box-sizing: border-box;
            }
            input:focus { outline: none; border-color: var(--accent); }

            .suggest {
                position: absolute;
                top: calc(100% + 4px);
                left: 0; right: 0;
                background: var(--bg-primary);
                border: 1px solid var(--glass-border-medium);
                border-radius: var(--radius-md);
                box-shadow: var(--shadow-xl);
                max-height: 240px;
                overflow-y: auto;
                z-index: 20;
            }
            .suggest-item {
                padding: var(--space-2) var(--space-3);
                font-size: var(--text-sm);
                color: var(--text-primary);
                cursor: pointer;
            }
            .suggest-item:hover { background: var(--glass-solid-medium); }
            .suggest-empty {
                padding: var(--space-2) var(--space-3);
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }

            .actions {
                display: flex; gap: var(--space-2); justify-content: flex-end;
                margin-bottom: var(--space-3);
            }
            .btn {
                padding: var(--space-2) var(--space-4);
                background: transparent; color: var(--text-secondary);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md); cursor: pointer;
                font-size: var(--text-sm);
            }
            .btn:hover { border-color: var(--accent); color: var(--text-primary); }
            .btn.primary {
                background: var(--accent); color: white; border-color: var(--accent);
            }
            .btn:disabled { opacity: 0.5; cursor: not-allowed; }

            .hint {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-bottom: var(--space-2);
            }

            table { width: 100%; border-collapse: collapse; }
            th, td {
                padding: var(--space-2) var(--space-3);
                border-bottom: 1px solid var(--glass-border-subtle);
                text-align: left;
                vertical-align: top;
            }
            th {
                color: var(--text-tertiary); font-size: var(--text-xs);
                text-transform: uppercase; letter-spacing: 0.05em;
            }
            td { color: var(--text-primary); font-size: var(--text-xs); }
            tr.row { cursor: pointer; }
            tr.row:hover { background: var(--glass-solid-medium); }
            td.mono { font-family: var(--font-mono); color: var(--text-secondary); }

            .state {
                padding: var(--space-8) var(--space-6);
                text-align: center;
                background: var(--glass-solid-subtle);
                border: 1px dashed var(--glass-border-subtle);
                border-radius: var(--radius-lg);
            }
            .state.forbidden { border-color: var(--warning); }
            .state.unavailable { border-color: var(--warning); }
            .state.error { border-color: var(--error); }
            .state-title { font-weight: var(--font-semibold); margin-bottom: var(--space-2); }
            .state-desc { color: var(--text-tertiary); font-size: var(--text-sm); }

            .footer-actions { display: flex; justify-content: center; padding: var(--space-3); }

            .drawer-backdrop {
                position: fixed; inset: 0;
                background: rgba(0, 0, 0, 0.5);
                z-index: 100;
            }
            .drawer {
                position: fixed; top: 0; right: 0; bottom: 0;
                width: min(900px, 90vw);
                background: var(--bg-primary);
                box-shadow: var(--shadow-2xl);
                z-index: 101;
                display: flex; flex-direction: column;
            }
            .drawer-header {
                padding: var(--space-4);
                border-bottom: 1px solid var(--glass-border-subtle);
                display: flex; justify-content: space-between; align-items: center;
            }
            .drawer-body { padding: var(--space-4); overflow-y: auto; flex: 1; }

            .span-node {
                margin-left: var(--indent, 0);
                padding: var(--space-2) var(--space-3);
                border-left: 2px solid var(--glass-border-subtle);
                margin-bottom: var(--space-1);
                background: var(--glass-solid-subtle);
                border-radius: var(--radius-sm);
            }
            .span-node-title {
                font-weight: var(--font-medium);
                font-size: var(--text-sm);
                color: var(--text-primary);
            }
            .span-node-meta {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-top: var(--space-1);
            }
        `,
    ];

    constructor() {
        super();
        this._spans = this.useCursorList('frontend/tracing_spans', { autoload: true });
        this._facets = this.useFacets('frontend/tracing_facets');
        this._trace = this.useOp('frontend/tracing_trace_load');
        this._activeFacet = null;
        this._draftFilters = {};
    }

    _filters() {
        return { ...this._spans.filters, ...this._draftFilters };
    }

    _apply() {
        this._spans.changeFilters(this._draftFilters);
        this._draftFilters = {};
        this._spans.load();
    }

    _onFilterInput(field, facetKey, value) {
        this._draftFilters = { ...this._draftFilters, [field]: value };
        if (facetKey && value && value.length >= 2) {
            this._activeFacet = facetKey;
            const filters = this._filters();
            const context = {};
            if (facetKey !== 'companies' && filters.company_id) context.company_id = filters.company_id;
            if (facetKey !== 'namespaces' && filters.namespace) context.namespace = filters.namespace;
            this._facets.search(facetKey, value, context);
        } else {
            this._activeFacet = null;
        }
    }

    _onFacetFocus(facetKey) {
        this._activeFacet = facetKey;
        const filters = this._filters();
        const value = filters[FACETS.find((f) => f.key === facetKey).field] || '';
        if (value && value.length >= 2) {
            const context = {};
            if (facetKey !== 'companies' && filters.company_id) context.company_id = filters.company_id;
            if (facetKey !== 'namespaces' && filters.namespace) context.namespace = filters.namespace;
            this._facets.search(facetKey, value, context);
        }
    }

    _selectSuggest(field, value) {
        this._draftFilters = { ...this._draftFilters, [field]: value };
        this._activeFacet = null;
    }

    _renderFacetField({ key, field, labelKey }, filters) {
        const value = filters[field] || '';
        const items = this._facets.items(key);
        const isOpen = this._activeFacet === key && value && value.length >= 2;
        return html`
            <div class="field">
                <label>${this.t(labelKey)}</label>
                <input
                    type="text"
                    .value=${value}
                    @input=${(e) => this._onFilterInput(field, key, e.target.value)}
                    @focus=${() => this._onFacetFocus(key)}
                    @blur=${() => setTimeout(() => { this._activeFacet = null; }, 180)}
                />
                ${isOpen ? html`
                    <div class="suggest">
                        ${this._facets.loading(key)
                            ? html`<div class="suggest-empty">${this.t('tracing_page.loading')}</div>`
                            : (items.length === 0
                                ? html`<div class="suggest-empty">${this.t('tracing_page.empty')}</div>`
                                : items.map((it) => html`
                                    <div class="suggest-item"
                                        @mousedown=${(e) => { e.preventDefault(); this._selectSuggest(field, typeof it === 'string' ? it : it.value); }}>
                                        ${typeof it === 'string' ? it : (typeof it.label === 'string' && it.label !== '' ? it.label : it.value)}
                                    </div>
                                `))}
                    </div>
                ` : null}
            </div>
        `;
    }

    _renderTimeField(field, labelKey, value) {
        return html`
            <div class="field">
                <label>${this.t(labelKey)}</label>
                <input
                    type="datetime-local"
                    .value=${value}
                    @input=${(e) => this._onFilterInput(field, null, e.target.value)}
                />
            </div>
        `;
    }

    _renderFilters() {
        const filters = this._filters();
        return html`
            <div class="hint">${this.t('tracing_page.facet_hint')}</div>
            <div class="filters">
                ${FACETS.map((f) => this._renderFacetField(f, filters))}
                ${this._renderTimeField('from_time', 'tracing_page.filter_from', filters.from_time || '')}
                ${this._renderTimeField('to_time', 'tracing_page.filter_to', filters.to_time || '')}
            </div>
            <div class="actions">
                <button class="btn primary" @click=${() => this._apply()}>
                    ${this.t('tracing_page.apply')}
                </button>
            </div>
        `;
    }

    _renderTable(records) {
        return html`
            <table>
                <thead><tr>
                    <th>${this.t('tracing_page.col_time')}</th>
                    <th>${this.t('tracing_page.col_service')}</th>
                    <th>${this.t('tracing_page.col_operation')}</th>
                    <th>${this.t('tracing_page.col_event')}</th>
                    <th>${this.t('tracing_page.col_company')}</th>
                    <th>${this.t('tracing_page.col_user')}</th>
                    <th>${this.t('tracing_page.col_trace')}</th>
                </tr></thead>
                <tbody>
                    ${records.map((r) => html`
                        <tr class="row" @click=${() => this._open(r.trace_id)}>
                            <td>${r.start_time ? new Date(r.start_time).toLocaleString() : (r.created_at ? new Date(r.created_at).toLocaleString() : '')}</td>
                            <td>${r.service_name || ''}</td>
                            <td>${r.operation_name || ''}</td>
                            <td>${r.event_type || ''}</td>
                            <td>${r.company_name || r.company_id || ''}</td>
                            <td>${r.user_id ? html`<platform-user-chip user-id=${r.user_id} size="sm"></platform-user-chip>` : ''}</td>
                            <td class="mono">${r.trace_id ? r.trace_id.slice(0, 16) : ''}</td>
                        </tr>
                    `)}
                </tbody>
            </table>
        `;
    }

    _renderSpan(node, depth = 0) {
        return html`
            <div class="span-node" style="--indent: ${depth * 16}px">
                <div class="span-node-title">${node.operation_name || node.span_id}</div>
                <div class="span-node-meta">
                    ${node.service_name || ''} · ${node.event_type || ''}
                    ${node.duration_ms != null ? html` · ${node.duration_ms} ms` : null}
                </div>
            </div>
            ${Array.isArray(node.children) ? node.children.map((c) => this._renderSpan(c, depth + 1)) : ''}
        `;
    }

    _renderTraceDrawer() {
        const trace = this._trace.lastResult;
        const loading = this._trace.busy;
        const error = this._trace.error;
        if (!trace && !loading && !error) return null;
        const tree = trace && trace.tree ? trace.tree : [];
        return html`
            <div class="drawer-backdrop" @click=${() => this._close()}></div>
            <div class="drawer">
                <div class="drawer-header">
                    <div>
                        <div class="span-node-title">${this.t('tracing_page.col_trace')}</div>
                        <div class="span-node-meta">${trace ? trace.trace_id : ''}</div>
                    </div>
                    <button class="btn" @click=${() => this._close()}>${this.t('tracing_page.close')}</button>
                </div>
                <div class="drawer-body">
                    ${loading
                        ? html`<glass-spinner></glass-spinner>`
                        : (error
                            ? html`<div class="state error">
                                <div class="state-title">${this.t('tracing_page.trace_load_error')}</div>
                                <div class="state-desc">${error}</div>
                            </div>`
                            : tree.map((n) => this._renderSpan(n, 0)))}
                </div>
            </div>
        `;
    }

    _open(traceId) {
        if (!traceId) return;
        this._trace.run({ trace_id: traceId });
    }

    _close() {
        this._trace.closeTrace();
    }

    render() {
        const records = this._spans.items;
        const loading = this._spans.loading;
        const loadingMore = this._spans.loadingMore;
        const hasMore = this._spans.hasMore;
        const terminal = this._spans.terminal;
        const error = this._spans.error;
        let body;
        if (loading && records.length === 0) {
            body = html`<div class="state"><glass-spinner></glass-spinner></div>`;
        } else if (terminal === 'forbidden') {
            body = html`<div class="state forbidden">
                <div class="state-title">${this.t('tracing_page.forbidden')}</div>
            </div>`;
        } else if (terminal === 'unavailable') {
            body = html`<div class="state unavailable">
                <div class="state-title">${this.t('tracing_page.unavailable')}</div>
            </div>`;
        } else if (error) {
            body = html`<div class="state error">
                <div class="state-title">${this.t('tracing_page.load_error')}</div>
                <div class="state-desc">${error}</div>
            </div>`;
        } else if (records.length === 0) {
            body = html`<div class="state">
                <div class="state-title">${this.t('tracing_page.empty')}</div>
            </div>`;
        } else {
            body = html`
                ${this._renderTable(records)}
                ${hasMore ? html`
                    <div class="footer-actions">
                        <button class="btn" ?disabled=${loadingMore} @click=${() => this._spans.loadMore()}>
                            ${loadingMore ? this.t('tracing_page.loading') : this.t('tracing_page.load_more')}
                        </button>
                    </div>
                ` : null}
            `;
        }
        return html`
            <page-header
                title=${this.t('tracing_page.title')}
                subtitle=${this.t('tracing_page.subtitle')}
            ></page-header>
            ${this._renderFilters()}
            ${body}
            ${this._renderTraceDrawer()}
        `;
    }
}

customElements.define('frontend-tracing-page', FrontendTracingPage);
