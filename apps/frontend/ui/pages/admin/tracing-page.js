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
import '@platform/lib/components/platform-trace-viewer.js';

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
        _traceDrawerSpan: { state: true },
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
            .user-col-name {
                font-size: var(--text-xs);
                color: var(--text-primary);
                word-break: break-word;
            }

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
                background: transparent;
                z-index: 100;
                cursor: default;
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
            .drawer-trace-title {
                font-weight: var(--font-medium);
                font-size: var(--text-sm);
                color: var(--text-primary);
            }
            .drawer-trace-id {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-top: var(--space-1);
            }
            .drawer-body { padding: var(--space-4); overflow-y: auto; flex: 1; }

            .drawer-detail {
                margin-top: var(--space-4);
                padding-top: var(--space-4);
                border-top: 1px solid var(--glass-border-subtle);
            }
            .drawer-detail h4 {
                margin: 0 0 var(--space-2);
                font-size: var(--text-sm);
                color: var(--text-primary);
            }
            .drawer-detail dl {
                display: grid;
                grid-template-columns: max-content 1fr;
                gap: var(--space-1) var(--space-3);
                font-size: var(--text-xs);
                color: var(--text-secondary);
                margin: 0 0 var(--space-3);
            }
            .drawer-detail dt { color: var(--text-tertiary); }
            .drawer-detail pre {
                margin: 0;
                padding: var(--space-3);
                background: var(--glass-solid-subtle);
                border-radius: var(--radius-md);
                font-size: var(--text-xs);
                overflow: auto;
                max-height: 36vh;
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
        this._traceDrawerSpan = null;
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

    /**
     * Колонка user: API уже кладёт user_display_name (UserRepository + fallback user_name из span).
     * platform-user-chip смотрит только state.team.members активной компании — для админского
     * спан-листа это даёт «Unknown» для чужих компаний и несистемных id (например канал).
     */
    _spanUserColumn(row) {
        if (row === null || typeof row !== 'object') {
            throw new Error('frontend-tracing-page: row must be an object');
        }
        const rec = /** @type {Record<string, unknown>} */ (row);
        const rawName = rec.user_display_name;
        const rawId = rec.user_id;
        const hasName = typeof rawName === 'string' && rawName.length > 0;
        const hasId = typeof rawId === 'string' && rawId.length > 0;
        if (hasName) {
            const title = hasId ? rawId : rawName;
            return html`<span class="user-col-name" title=${title}>${rawName}</span>`;
        }
        if (hasId) {
            return html`<span class="mono" title=${rawId}>${rawId}</span>`;
        }
        return '';
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
                            <td>${this._spanUserColumn(r)}</td>
                            <td class="mono">${r.trace_id ? r.trace_id.slice(0, 16) : ''}</td>
                        </tr>
                    `)}
                </tbody>
            </table>
        `;
    }

    /** @param {CustomEvent<{ span?: unknown }>} e */
    _onDrawerTraceSpanSelect(e) {
        const d = e.detail;
        if (d == null || typeof d !== 'object' || !('span' in d)) {
            throw new Error('frontend-tracing-page: trace-span-select requires detail.span');
        }
        this._traceDrawerSpan = d.span;
    }

    /** @param {unknown} span */
    _renderDrawerSpanDetail(span) {
        if (span == null) {
            return null;
        }
        if (typeof span !== 'object' || span === null) {
            throw new Error('frontend-tracing-page: span must be an object');
        }
        const s = /** @type {Record<string, unknown>} */ (span);
        const sid = typeof s.span_id === 'string' ? s.span_id : '';
        const tid = typeof s.trace_id === 'string' ? s.trace_id : '';
        const op = typeof s.operation_name === 'string' ? s.operation_name : '';
        const dur = typeof s.duration_ms === 'number' ? `${s.duration_ms} ms` : '';
        const st = typeof s.status === 'string' ? s.status : '';
        const rawAttrs = s.attributes;
        const attrs =
            typeof rawAttrs === 'object' && rawAttrs !== null && !Array.isArray(rawAttrs)
                ? rawAttrs
                : {};
        const json = JSON.stringify(attrs, null, 2);
        return html`
            <div class="drawer-detail">
                <h4>${this.t('trace_viewer.detail_title', undefined, 'platform')}</h4>
                <dl>
                    <dt>span_id</dt>
                    <dd>${sid}</dd>
                    <dt>trace_id</dt>
                    <dd>${tid}</dd>
                    <dt>operation</dt>
                    <dd>${op}</dd>
                    <dt>duration</dt>
                    <dd>${dur}</dd>
                    <dt>status</dt>
                    <dd>${st}</dd>
                </dl>
                <div style="font-size:var(--text-xs);color:var(--text-tertiary);margin-bottom:var(--space-1);">
                    ${this.t('trace_viewer.detail_attributes', undefined, 'platform')}
                </div>
                <pre>${json}</pre>
            </div>
        `;
    }

    _renderTraceDrawer() {
        const trace = this._trace.lastResult;
        const loading = this._trace.busy;
        const error = this._trace.error;
        if (!trace && !loading && !error) return null;
        const tree = trace && trace.tree ? trace.tree : [];
        return html`
            <div
                class="drawer-backdrop"
                @click=${(e) => { if (e.target === e.currentTarget) this._close(); }}
            ></div>
            <div class="drawer">
                <div class="drawer-header">
                    <div>
                        <div class="drawer-trace-title">${this.t('tracing_page.col_trace')}</div>
                        <div class="drawer-trace-id">${trace ? trace.trace_id : ''}</div>
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
                            : html`
                                  <platform-trace-viewer
                                      .roots=${tree}
                                      @trace-span-select=${this._onDrawerTraceSpanSelect}
                                  ></platform-trace-viewer>
                                  ${this._renderDrawerSpanDetail(this._traceDrawerSpan)}
                              `)}
                </div>
            </div>
        `;
    }

    _open(traceId) {
        if (!traceId) return;
        this._traceDrawerSpan = null;
        this._trace.run({ trace_id: traceId });
    }

    _close() {
        this._traceDrawerSpan = null;
        this._trace.closeTrace(null);
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
