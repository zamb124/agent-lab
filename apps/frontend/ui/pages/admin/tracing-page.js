/**
 * Админ-просмотр spans (только компания system).
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-button.js';

const FACET_DEBOUNCE_MS = 300;
const API_BASE = '/frontend/api/platform-tracing';

const FACET_PATHS = {
    company: 'facets/companies',
    user: 'facets/users',
    service: 'facets/services',
    event: 'facets/event-types',
    namespace: 'facets/namespaces',
    operation: 'facets/operations',
};

export class TracingPage extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
            }

            .filters {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(11rem, 1fr));
                gap: var(--space-3);
                margin-bottom: var(--space-4);
            }

            .filters label {
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
                font-size: var(--text-xs);
                color: var(--text-secondary);
            }

            .filters input {
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-md);
                border: 1px solid var(--border-default);
                background: var(--glass-solid-medium);
                color: var(--text-primary);
                font-size: var(--text-sm);
                width: 100%;
                box-sizing: border-box;
            }

            .suggest-wrap {
                position: relative;
                width: 100%;
            }

            .suggest-panel {
                position: absolute;
                left: 0;
                right: 0;
                top: calc(100% + 2px);
                z-index: 50;
                max-height: 220px;
                overflow: auto;
                border-radius: var(--radius-md);
                border: 1px solid var(--border-default);
                background: var(--glass-solid-strong);
                box-shadow: var(--shadow-md);
            }

            .suggest-item {
                display: block;
                width: 100%;
                text-align: left;
                padding: var(--space-2) var(--space-3);
                border: none;
                border-bottom: 1px solid var(--border-subtle);
                background: transparent;
                color: var(--text-primary);
                font-size: var(--text-sm);
                cursor: pointer;
                word-break: break-word;
            }

            .suggest-item:last-child {
                border-bottom: none;
            }

            .suggest-item:hover,
            .suggest-item:focus-visible {
                background: var(--glass-tint-medium);
                outline: none;
            }

            .actions {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-3);
                margin-bottom: var(--space-4);
                align-items: center;
            }

            .table-wrap {
                background: var(--glass-solid-medium);
                border-radius: var(--radius-lg);
                overflow-x: auto;
            }

            table {
                width: 100%;
                border-collapse: collapse;
            }

            th,
            td {
                padding: var(--space-2) var(--space-3);
                border-top: 1px solid var(--border-subtle);
                text-align: left;
                font-size: var(--text-xs);
                color: var(--text-primary);
                vertical-align: top;
            }

            th {
                background: var(--glass-tint-medium);
                color: var(--text-secondary);
                border-top: none;
                white-space: nowrap;
            }

            td {
                word-break: break-word;
            }

            tr[data-clickable] {
                cursor: pointer;
            }

            tr[data-clickable]:hover {
                background: var(--glass-tint-subtle);
            }

            .muted {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
            }

            .error-box {
                padding: var(--space-4);
                border-radius: var(--radius-md);
                background: rgba(239, 68, 68, 0.12);
                border: 1px solid rgba(239, 68, 68, 0.35);
                color: var(--text-primary);
                margin-bottom: var(--space-4);
            }

            .overlay {
                position: fixed;
                inset: 0;
                z-index: var(--z-modal, 1000);
                background: rgba(0, 0, 0, 0.55);
                backdrop-filter: blur(4px);
                display: flex;
                align-items: center;
                justify-content: center;
                padding: var(--space-4);
                box-sizing: border-box;
            }

            .overlay-panel {
                width: min(56rem, 100%);
                max-height: min(85vh, 100%);
                overflow: hidden;
                display: flex;
                flex-direction: column;
                background: var(--glass-solid-strong);
                border-radius: var(--radius-lg);
                border: 1px solid var(--border-default);
                box-shadow: var(--shadow-lg);
            }

            .overlay-head {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: var(--space-3) var(--space-4);
                border-bottom: 1px solid var(--border-subtle);
            }

            .overlay-body {
                padding: var(--space-3);
                overflow: auto;
                flex: 1;
            }

            .overlay-body pre {
                margin: 0;
                font-family: 'SF Mono', 'Monaco', 'Menlo', monospace;
                font-size: 11px;
                line-height: 1.45;
                white-space: pre-wrap;
                word-break: break-word;
                color: var(--text-primary);
            }
        `,
    ];

    static properties = {
        _rows: { type: Array, state: true },
        _nextCursor: { type: String, state: true },
        _loading: { type: Boolean, state: true },
        _loadingMore: { type: Boolean, state: true },
        _error: { type: String, state: true },
        _detailOpen: { type: Boolean, state: true },
        _detailJson: { type: String, state: true },
        _detailTitle: { type: String, state: true },
        _detailLoading: { type: Boolean, state: true },
        _fCompany: { type: String, state: true },
        _fUser: { type: String, state: true },
        _fService: { type: String, state: true },
        _fEventType: { type: String, state: true },
        _fOperation: { type: String, state: true },
        _fNamespace: { type: String, state: true },
        _fFrom: { type: String, state: true },
        _fTo: { type: String, state: true },
        _pickCompany: { type: String, state: true },
        _pickUser: { type: String, state: true },
        _pickNamespace: { type: String, state: true },
        _pickService: { type: String, state: true },
        _facetOpen: { type: String, state: true },
        _facetItems: { type: Object, state: true },
    };

    constructor() {
        super();
        this._rows = [];
        this._nextCursor = '';
        this._loading = false;
        this._loadingMore = false;
        this._error = '';
        this._detailOpen = false;
        this._detailJson = '';
        this._detailTitle = '';
        this._detailLoading = false;
        this._fCompany = '';
        this._fUser = '';
        this._fService = '';
        this._fEventType = '';
        this._fOperation = '';
        this._fNamespace = '';
        this._fFrom = '';
        this._fTo = '';
        this._pickCompany = '';
        this._pickUser = '';
        this._pickNamespace = '';
        this._pickService = '';
        this._facetOpen = '';
        this._facetItems = {
            company: [],
            user: [],
            service: [],
            event: [],
            namespace: [],
            operation: [],
        };
        this._facetDebounce = {};
        this._onDocClick = (e) => {
            if (!this._facetOpen) {
                return;
            }
            const path = e.composedPath();
            const hit = path.some(
                (n) => n instanceof HTMLElement && n.classList?.contains('suggest-wrap')
            );
            if (!hit) {
                this._facetOpen = '';
            }
        };
    }

    connectedCallback() {
        super.connectedCallback();
        document.addEventListener('click', this._onDocClick);
        void this._search(false);
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        document.removeEventListener('click', this._onDocClick);
        Object.values(this._facetDebounce).forEach((id) => clearTimeout(id));
    }

    _scopeCompanyId() {
        const p = this._pickCompany.trim();
        const v = this._fCompany.trim();
        return p && p === v ? p : '';
    }

    _scopeNamespace() {
        const p = this._pickNamespace.trim();
        const v = this._fNamespace.trim();
        return p && p === v ? p : '';
    }

    _scheduleFacet(kind, q) {
        if (this._facetDebounce[kind]) {
            clearTimeout(this._facetDebounce[kind]);
        }
        this._facetDebounce[kind] = window.setTimeout(() => {
            void this._loadFacet(kind, q);
        }, FACET_DEBOUNCE_MS);
    }

    async _loadFacet(kind, q) {
        const path = FACET_PATHS[kind];
        if (!path) {
            return;
        }
        const trimmed = (q || '').trim();
        const url = new URL(`${API_BASE}/${path}`, window.location.origin);
        if (trimmed.length >= 2) {
            url.searchParams.set('q', trimmed);
        }
        const co = this._scopeCompanyId();
        if (co && kind !== 'company') {
            url.searchParams.set('company_id', co);
        }
        const ns = this._scopeNamespace();
        if (ns && kind !== 'company' && kind !== 'namespace') {
            url.searchParams.set('namespace', ns);
        }
        const response = await fetch(url.pathname + url.search, { credentials: 'include' });
        if (!response.ok) {
            return;
        }
        const data = await response.json();
        const items = Array.isArray(data.items) ? data.items : [];
        this._facetItems = { ...this._facetItems, [kind]: items };
    }

    _onSuggestInput(kind, e) {
        const raw = e.target?.value ?? '';
        if (kind === 'company') {
            this._fCompany = raw;
            if (raw.trim() !== this._pickCompany.trim()) {
                this._pickCompany = '';
            }
        } else if (kind === 'user') {
            this._fUser = raw;
            if (raw.trim() !== this._pickUser.trim()) {
                this._pickUser = '';
            }
        } else if (kind === 'namespace') {
            this._fNamespace = raw;
            if (raw.trim() !== this._pickNamespace.trim()) {
                this._pickNamespace = '';
            }
        } else if (kind === 'service') {
            this._fService = raw;
            if (raw.trim() !== this._pickService.trim()) {
                this._pickService = '';
            }
        } else if (kind === 'event') {
            this._fEventType = raw;
        } else if (kind === 'operation') {
            this._fOperation = raw;
        }
        this._facetOpen = kind;
        this._scheduleFacet(kind, raw);
    }

    _onSuggestFocus(kind) {
        this._facetOpen = kind;
        const q =
            kind === 'company'
                ? this._fCompany
                : kind === 'user'
                  ? this._fUser
                  : kind === 'namespace'
                    ? this._fNamespace
                    : kind === 'service'
                      ? this._fService
                      : kind === 'event'
                        ? this._fEventType
                        : this._fOperation;
        void this._loadFacet(kind, q);
    }

    _pickSuggest(kind, value) {
        const v = value ?? '';
        if (kind === 'company') {
            this._fCompany = v;
            this._pickCompany = v;
        } else if (kind === 'user') {
            this._fUser = v;
            this._pickUser = v;
        } else if (kind === 'namespace') {
            this._fNamespace = v;
            this._pickNamespace = v;
        } else if (kind === 'service') {
            this._fService = v;
            this._pickService = v;
        } else if (kind === 'event') {
            this._fEventType = v;
        } else if (kind === 'operation') {
            this._fOperation = v;
        }
        this._facetOpen = '';
    }

    _renderSuggest(kind, label, value) {
        const open = this._facetOpen === kind;
        const items = Array.isArray(this._facetItems[kind]) ? this._facetItems[kind] : [];
        return html`
            <label>
                ${label}
                <div class="suggest-wrap" @click=${(e) => e.stopPropagation()}>
                    <input
                        type="text"
                        .value=${value}
                        @focus=${() => this._onSuggestFocus(kind)}
                        @input=${(e) => this._onSuggestInput(kind, e)}
                    />
                    ${open && items.length > 0
                        ? html`
                              <div class="suggest-panel" role="listbox">
                                  ${items.map(
                                      (item) => html`
                                          <button
                                              type="button"
                                              class="suggest-item"
                                              role="option"
                                              @mousedown=${(e) => e.preventDefault()}
                                              @click=${() => this._pickSuggest(kind, item)}
                                          >
                                              ${item}
                                          </button>
                                      `
                                  )}
                              </div>
                          `
                        : ''}
                </div>
            </label>
        `;
    }

    _buildSpanQueryParams() {
        const p = new URLSearchParams();
        const co = this._fCompany.trim();
        const pickCo = this._pickCompany.trim();
        if (pickCo && pickCo === co) {
            p.set('company_id', pickCo);
        } else if (co.length >= 2) {
            p.set('company_id_query', co);
        }
        const us = this._fUser.trim();
        const pickUs = this._pickUser.trim();
        if (pickUs && pickUs === us) {
            p.set('user_id', pickUs);
        } else if (us.length >= 2) {
            p.set('user_id_query', us);
        }
        const ns = this._fNamespace.trim();
        const pickNs = this._pickNamespace.trim();
        if (pickNs && pickNs === ns) {
            p.set('namespace', pickNs);
        } else if (ns.length >= 2) {
            p.set('namespace_query', ns);
        }
        const svc = this._fService.trim();
        const pickSvc = this._pickService.trim();
        if (pickSvc && pickSvc === svc) {
            p.set('service_name', pickSvc);
        } else if (svc.length >= 2) {
            p.set('service_name_query', svc);
        }
        const qOp = this._fOperation.trim();
        if (qOp.length >= 2) {
            p.set('operation_name_query', qOp);
        }
        const qEv = this._fEventType.trim();
        if (qEv.length >= 2) {
            p.set('event_type_query', qEv);
        }
        if (this._fFrom) {
            const d = new Date(this._fFrom);
            if (!Number.isNaN(d.getTime())) {
                p.set('from_time', d.toISOString());
            }
        }
        if (this._fTo) {
            const d = new Date(this._fTo);
            if (!Number.isNaN(d.getTime())) {
                p.set('to_time', d.toISOString());
            }
        }
        p.set('limit', '50');
        return p;
    }

    async _search(append) {
        if (append) {
            this._loadingMore = true;
        } else {
            this._loading = true;
            this._error = '';
        }
        const p = this._buildSpanQueryParams();
        if (append && this._nextCursor) {
            p.set('cursor', this._nextCursor);
        }
        const response = await fetch(`${API_BASE}/spans?${p.toString()}`, {
            credentials: 'include',
        });
        if (response.status === 403) {
            this._error = this.i18n.t('tracing_page.forbidden', {});
            this._rows = [];
            this._nextCursor = '';
            this._loading = false;
            this._loadingMore = false;
            return;
        }
        if (response.status === 503) {
            const body = await response.json().catch(() => ({}));
            this._error =
                typeof body.detail === 'string'
                    ? body.detail
                    : this.i18n.t('tracing_page.unavailable', {});
            this._rows = [];
            this._nextCursor = '';
            this._loading = false;
            this._loadingMore = false;
            return;
        }
        if (!response.ok) {
            this._error = this.i18n.t('tracing_page.load_error', {});
            this._rows = append ? this._rows : [];
            this._nextCursor = '';
            this._loading = false;
            this._loadingMore = false;
            return;
        }
        const data = await response.json();
        const items = Array.isArray(data.items) ? data.items : [];
        this._rows = append ? [...this._rows, ...items] : items;
        this._nextCursor = data.next_cursor || '';
        this._loading = false;
        this._loadingMore = false;
    }

    async _openTrace(traceId) {
        this._detailOpen = true;
        this._detailLoading = true;
        this._detailTitle = traceId;
        this._detailJson = '';
        const response = await fetch(
            `${API_BASE}/traces/${encodeURIComponent(traceId)}`,
            { credentials: 'include' }
        );
        if (!response.ok) {
            this._detailJson = JSON.stringify(
                { error: this.i18n.t('tracing_page.trace_load_error', {}) },
                null,
                2
            );
            this._detailLoading = false;
            return;
        }
        const data = await response.json();
        this._detailJson = JSON.stringify(data, null, 2);
        this._detailLoading = false;
    }

    _closeDetail() {
        this._detailOpen = false;
        this._detailJson = '';
        this._detailTitle = '';
    }

    render() {
        const t = (k) => this.i18n.t(k, {});
        return html`
            <page-header
                title=${t('tracing_page.title')}
                subtitle=${t('tracing_page.subtitle')}
            ></page-header>

            <div class="filters">
                ${this._renderSuggest('company', t('tracing_page.filter_company'), this._fCompany)}
                ${this._renderSuggest('namespace', t('tracing_page.filter_namespace'), this._fNamespace)}
                ${this._renderSuggest('user', t('tracing_page.filter_user'), this._fUser)}
                ${this._renderSuggest('service', t('tracing_page.filter_service'), this._fService)}
                ${this._renderSuggest(
                    'operation',
                    t('tracing_page.filter_operation'),
                    this._fOperation
                )}
                ${this._renderSuggest('event', t('tracing_page.filter_event'), this._fEventType)}
                <label>
                    ${t('tracing_page.filter_from')}
                    <input
                        type="datetime-local"
                        .value=${this._fFrom}
                        @input=${(e) => (this._fFrom = e.target.value)}
                    />
                </label>
                <label>
                    ${t('tracing_page.filter_to')}
                    <input
                        type="datetime-local"
                        .value=${this._fTo}
                        @input=${(e) => (this._fTo = e.target.value)}
                    />
                </label>
            </div>

            <div class="actions">
                <platform-button variant="primary" @click=${() => void this._search(false)}>
                    ${t('tracing_page.apply')}
                </platform-button>
                <span class="muted">${t('tracing_page.facet_hint')}</span>
            </div>

            ${this._error ? html`<div class="error-box">${this._error}</div>` : ''}

            ${this._loading
                ? html`<p class="muted">${t('tracing_page.loading')}</p>`
                : html`
                      <div class="table-wrap">
                          <table>
                              <thead>
                                  <tr>
                                      <th>${t('tracing_page.col_time')}</th>
                                      <th>${t('tracing_page.col_trace')}</th>
                                      <th>${t('tracing_page.col_span')}</th>
                                      <th>${t('tracing_page.col_service')}</th>
                                      <th>${t('tracing_page.col_operation')}</th>
                                      <th>${t('tracing_page.col_company')}</th>
                                      <th>${t('tracing_page.col_user')}</th>
                                      <th>${t('tracing_page.col_event')}</th>
                                  </tr>
                              </thead>
                              <tbody>
                                  ${this._rows.length === 0
                                      ? html`<tr>
                                            <td colspan="8" class="muted">${t('tracing_page.empty')}</td>
                                        </tr>`
                                      : this._rows.map(
                                            (row) => html`
                                                <tr
                                                    data-clickable
                                                    @click=${() => void this._openTrace(row.trace_id)}
                                                >
                                                    <td>${row.start_time ?? ''}</td>
                                                    <td>${row.trace_id ?? ''}</td>
                                                    <td>${row.span_id ?? ''}</td>
                                                    <td>${row.service_name ?? ''}</td>
                                                    <td>${row.operation_name ?? ''}</td>
                                                    <td>${row.company_id ?? ''}</td>
                                                    <td>${row.user_id ?? ''}</td>
                                                    <td>${row.event_type ?? ''}</td>
                                                </tr>
                                            `
                                        )}
                              </tbody>
                          </table>
                      </div>
                      ${this._nextCursor
                          ? html`
                                <div class="actions">
                                    <platform-button
                                        variant="secondary"
                                        ?disabled=${this._loadingMore}
                                        @click=${() => void this._search(true)}
                                    >
                                        ${this._loadingMore
                                            ? t('tracing_page.loading')
                                            : t('tracing_page.load_more')}
                                    </platform-button>
                                </div>
                            `
                          : ''}
                  `}

            ${this._detailOpen
                ? html`
                      <div class="overlay" @click=${(e) => e.target === e.currentTarget && this._closeDetail()}>
                          <div class="overlay-panel" @click=${(e) => e.stopPropagation()}>
                              <div class="overlay-head">
                                  <strong>${this._detailTitle}</strong>
                                  <platform-button variant="ghost" @click=${() => this._closeDetail()}>
                                      ${t('tracing_page.close')}
                                  </platform-button>
                              </div>
                              <div class="overlay-body">
                                  ${this._detailLoading
                                      ? html`<p class="muted">${t('tracing_page.loading')}</p>`
                                      : html`<pre>${this._detailJson}</pre>`}
                              </div>
                          </div>
                      </div>
                  `
                : ''}
        `;
    }
}

customElements.define('tracing-page', TracingPage);
