/**
 * Страница admin tracing (system) — поиск spans с typeahead-подсказками
 * по 6 фасетам и просмотр дерева одного трейса в выезжающем drawer.
 *
 * Доступно только при активной компании system. 503 → unavailable state.
 */
import { html, css } from 'lit';
import { isPlainRecord } from '@platform/lib/events/payload.js';

function displayText(value: unknown): string {
    if (value === undefined || value === null || value === false || value === 0 || value === '') return '';
    if (typeof value === 'number' && !Number.isFinite(value)) return '';
    return String(value);
}

function facetContext(filters: Record<string, unknown>, facetKey: string): Record<string, unknown> {
    const context: Record<string, unknown> = {};
    const companyId = filters.company_id;
    if (facetKey !== 'companies' && typeof companyId === 'string' && companyId.length > 0) {
        context.company_id = companyId;
    }
    const namespace = filters.namespace;
    if (facetKey !== 'namespaces' && typeof namespace === 'string' && namespace.length > 0) {
        context.namespace = namespace;
    }
    return context;
}

function instantText(value: unknown): string {
    if (typeof value === 'number' && Number.isFinite(value)) {
        return new Date(value).toLocaleString();
    }
    if (typeof value === 'string' && value.length > 0) {
        return new Date(value).toLocaleString();
    }
    return '';
}

function firstText(values: readonly unknown[]): string {
    for (const value of values) {
        const text = displayText(value);
        if (text.length > 0) return text;
    }
    return '';
}
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { frontendIslandPageBodyStyles } from '../../styles/frontend-island-page-body.styles.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-spinner.js';
import '@platform/lib/components/platform-empty-state.js';
import '@platform/lib/components/platform-trace-viewer.js';
import '@platform/lib/components/platform-span-attributes-viewer.js';
import '@platform/lib/components/fields/platform-field.js';
import type {CSSResultGroup, PropertyDeclarations, TemplateResult} from 'lit';
import type { ControllerFor, FacetsController } from '@platform/lib/base/use-resource.js';

const FACETS = Object.freeze([
    { key: 'companies',   field: 'company_id',     labelKey: 'tracing_page.filter_company' },
    { key: 'users',       field: 'user_id',        labelKey: 'tracing_page.filter_user' },
    { key: 'services',    field: 'service_name',   labelKey: 'tracing_page.filter_service' },
    { key: 'namespaces',  field: 'namespace',      labelKey: 'tracing_page.filter_namespace' },
    { key: 'operations',  field: 'operation_name', labelKey: 'tracing_page.filter_operation' },
    { key: 'event_types', field: 'event_type',     labelKey: 'tracing_page.filter_event' },
]);

export class FrontendTracingPage extends PlatformPage {
    static override properties: PropertyDeclarations = {
        _activeFacet: { state: true },
        _draftFilters: { state: true },
        _traceDrawerSpan: { state: true },
    }
    declare _activeFacet: string | null;
    declare _draftFilters: Record<string, unknown>;
    declare _traceDrawerSpan: unknown;
;

    static override styles: CSSResultGroup = [
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
            .field { position: relative; display: block; min-width: 0; }

            .suggest {
                position: absolute;
                top: calc(100% + 4px);
                left: 0; right: 0;
                background: var(--bg-primary);
                border: 1px solid var(--glass-border-medium);
                border-radius: var(--radius-md);
                box-shadow: var(--glass-shadow-strong);
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
                box-shadow: var(--glass-shadow-ultra);
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
        frontendIslandPageBodyStyles,
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
    private _spans: ControllerFor<'frontend/tracing_spans'>;
    private _facets: FacetsController;
    private _trace: ControllerFor<'frontend/tracing_trace_load'>;


    _filters() {
        return { ...this._spans.filters, ...this._draftFilters };
    }

    _apply() {
        this._spans.changeFilters(this._draftFilters);
        this._draftFilters = {};
        this._spans.load();
    }

    _onFilterInput(field: string, facetKey: string | null, value: unknown) {
        this._draftFilters = { ...this._draftFilters, [field]: value };
        if (facetKey && typeof value === 'string' && value.length >= 2) {
            this._activeFacet = facetKey;
            const filters = this._filters();
            this._facets.search(facetKey, String(value), facetContext(filters, facetKey));
        } else {
            this._activeFacet = null;
        }
    }

    _onFacetFocus(facetKey: string) {
        this._activeFacet = facetKey;
        const filters = this._filters();
        const facet = FACETS.find((f) => f.key === facetKey);
        if (!facet) {
            throw new Error(`frontend-tracing-page: unknown facet key ${facetKey}`);
        }
        const raw = filters[facet.field];
        const value = typeof raw === 'string' ? raw : '';
        if (value.length >= 2) {
            this._facets.search(facetKey, String(value), facetContext(filters, facetKey));
        }
    }

    _selectSuggest(field: string, value: unknown) {
        this._draftFilters = { ...this._draftFilters, [field]: value };
        this._activeFacet = null;
    }

    _renderFacetField({ key, field, labelKey }: { key: string; field: string; labelKey: string }, filters: Record<string, unknown>) {
        const raw = filters[field];
        const value = typeof raw === 'string' ? raw : '';
        const rawItems = this._facets.items(key);
        const items = rawItems === undefined ? [] : rawItems;
        const isOpen = this._activeFacet === key && value.length >= 2;
        return html`
            <div class="field">
                <platform-field
                    type="string"
                    mode="edit"
                    input-type="search"
                    .label=${this.t(labelKey)}
                    .value=${value}
                    @change=${(e: CustomEvent) => {
                        const v = typeof e.detail.value === 'string' ? e.detail.value : '';
                        this._onFilterInput(field, key, v);
                    }}
                    @platform-field-managed-focus-in=${() => this._onFacetFocus(key)}
                    @platform-field-managed-focus-out=${(e: CustomEvent) => {
                        const d = e.detail;
                        const rt = d && 'relatedTarget' in d ? d.relatedTarget : null;
                        const current = e.currentTarget;
                        if (!(current instanceof Element)) {
                            throw new Error('frontend-tracing-page: focus-out target required');
                        }
                        const wrap = current.parentElement;
                        if (rt instanceof Node && wrap !== null && wrap.contains(rt)) {
                            return;
                        }
                        setTimeout(() => {
                            if (this._activeFacet === key) {
                                this._activeFacet = null;
                            }
                        }, 180);
                    }}
                ></platform-field>
                ${isOpen ? html`
                    <div class="suggest">
                        ${this._facets.loading(key)
                            ? html`<platform-empty-state loading></platform-empty-state>`
                            : (items.length === 0
                                ? html`<platform-empty-state icon="trace-timeline" title=${this.t('tracing_page.empty')}></platform-empty-state>`
                                : items.map((it) => {
                                    const suggestValue = typeof it === 'string'
                                        ? it
                                        : (isPlainRecord(it) && typeof it.value === 'string' ? it.value : '');
                                    if (suggestValue.length === 0) {
                                        throw new Error('frontend-tracing-page: suggest value required');
                                    }
                                    const label = typeof it === 'string'
                                        ? it
                                        : (isPlainRecord(it) && typeof it.label === 'string' && it.label.length > 0 ? it.label : suggestValue);
                                    return html`
                                    <div class="suggest-item"
                                        @mousedown=${(event: Event) => { event.preventDefault(); this._selectSuggest(field, suggestValue); }}>
                                        ${label}
                                    </div>
                                `;
                                }))}
                    </div>
                ` : null}
            </div>
        `;
    }

    _renderTimeField(field: string, labelKey: string, filters: Record<string, unknown>) {
        const raw = filters[field];
        const value = typeof raw === 'string' ? raw : '';
        return html`
            <div class="field">
                <platform-field
                    type="datetime"
                    mode="edit"
                    .label=${this.t(labelKey)}
                    .value=${value}
                    @change=${(e: CustomEvent) => {
                        const v = typeof e.detail.value === 'string' ? e.detail.value : '';
                        this._onFilterInput(field, null, v);
                    }}
                ></platform-field>
            </div>
        `;
    }

    _renderFilters() {
        const filters = this._filters();
        return html`
            <div class="hint">${this.t('tracing_page.facet_hint')}</div>
            <div class="filters">
                ${FACETS.map((f) => this._renderFacetField(f, filters))}
                ${this._renderTimeField('from_time', 'tracing_page.filter_from', filters)}
                ${this._renderTimeField('to_time', 'tracing_page.filter_to', filters)}
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
    _spanUserColumn(row: unknown) {
        if (!isPlainRecord(row)) {
            throw new Error('frontend-tracing-page: row must be an object');
        }
        const rawName = row.user_display_name;
        const rawId = row.user_id;
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

    _renderTable(records: readonly unknown[]) {
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
                    ${records.map((row) => {
                        if (!isPlainRecord(row)) {
                            throw new Error('frontend-tracing-page: span row must be an object');
                        }
                        const started = instantText(row.start_time);
                        const when = started.length > 0 ? started : instantText(row.created_at);
                        const traceId = typeof row.trace_id === 'string' ? row.trace_id : '';
                        return html`
                        <tr class="row" @click=${() => this._open(traceId)}>
                            <td>${when}</td>
                            <td>${displayText(row.service_name)}</td>
                            <td>${displayText(row.operation_name)}</td>
                            <td>${displayText(row.event_type)}</td>
                            <td>${firstText([row.company_name, row.company_id])}</td>
                            <td>${this._spanUserColumn(row)}</td>
                            <td class="mono">${traceId.length > 0 ? traceId.slice(0, 16) : ''}</td>
                        </tr>
                    `;
                    })}
                </tbody>
            </table>
        `;
    }

    /** @param {CustomEvent<{ span?: unknown }>} e */
    _onDrawerTraceSpanSelect(e: CustomEvent) {
        const d = e.detail;
        if (d == null || typeof d !== 'object' || !('span' in d)) {
            throw new Error('frontend-tracing-page: trace-span-select requires detail.span');
        }
        this._traceDrawerSpan = d.span;
    }

    /** @param {unknown} span */
    _renderDrawerSpanDetail(span: unknown) {
        if (span == null) {
            return null;
        }
        if (!isPlainRecord(span)) {
            throw new Error('frontend-tracing-page: span must be an object');
        }
        return html`
            <div class="drawer-detail">
                <platform-span-attributes-viewer .span=${span}></platform-span-attributes-viewer>
            </div>
        `;
    }

    _renderTraceDrawer() {
        const trace = this._trace.lastResult;
        const loading = this._trace.busy;
        const error = this._trace.error;
        if (!trace && !loading && !error) return null;
        const loaded = isPlainRecord(trace) ? trace : null;
        const treeValue = loaded === null ? undefined : loaded.tree;
        const tree = Array.isArray(treeValue) ? treeValue : [];
        const traceId = loaded === null ? '' : displayText(loaded.trace_id);
        return html`
            <div
                class="drawer-backdrop"
                @click=${(e: Event) => { if (e.target === e.currentTarget) this._close(); }}
            ></div>
            <div class="drawer">
                <div class="drawer-header">
                    <div>
                        <div class="drawer-trace-title">${this.t('tracing_page.col_trace')}</div>
                        <div class="drawer-trace-id">${traceId}</div>
                    </div>
                    <button class="btn" @click=${() => this._close()}>${this.t('tracing_page.close')}</button>
                </div>
                <div class="drawer-body">
                    ${loading
                        ? html`<platform-spinner></platform-spinner>`
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

    _open(traceId: unknown) {
        if (typeof traceId !== 'string' || traceId.length === 0) {
            return;
        }
        this._traceDrawerSpan = null;
        this._trace.run({ trace_id: traceId });
    }

    _close() {
        this._traceDrawerSpan = null;
        this._trace.closeTrace(null);
    }

    override render(): TemplateResult {
        const records = this._spans.items;
        const loading = this._spans.loading;
        const loadingMore = this._spans.loadingMore;
        const hasMore = this._spans.hasMore;
        const terminal = this._spans.terminal;
        const error = this._spans.error;
        let body;
        if (loading && records.length === 0) {
            body = html`<platform-empty-state loading></platform-empty-state>`;
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
                            ${loadingMore ? html`<platform-spinner size="xs"></platform-spinner>` : this.t('tracing_page.load_more')}
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
            <div class="page-body">
            ${this._renderFilters()}
            ${body}
            ${this._renderTraceDrawer()}
            </div>
        `;
    }
}

customElements.define('frontend-tracing-page', FrontendTracingPage);
