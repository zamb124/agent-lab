/**
 * Админ-просмотр spans (только компания system).
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-button.js';

const FACET_DEBOUNCE_MS = 300;
const API_BASE = '/frontend/api/platform-tracing';

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
        _fCompanyExact: { type: String, state: true },
        _fUserExact: { type: String, state: true },
        _fFrom: { type: String, state: true },
        _fTo: { type: String, state: true },
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
        this._fCompanyExact = '';
        this._fUserExact = '';
        this._fFrom = '';
        this._fTo = '';
        this._facetDebounce = {};
        this._datalistIds = {
            company: 'tracing-facet-company',
            user: 'tracing-facet-user',
            service: 'tracing-facet-service',
            event: 'tracing-facet-event',
        };
    }

    connectedCallback() {
        super.connectedCallback();
        void this._search(false);
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        Object.values(this._facetDebounce).forEach((id) => clearTimeout(id));
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
        const trimmed = (q || '').trim();
        if (trimmed.length > 0 && trimmed.length < 2) {
            return;
        }
        const path =
            kind === 'company'
                ? 'facets/companies'
                : kind === 'user'
                  ? 'facets/users'
                  : kind === 'service'
                    ? 'facets/services'
                    : 'facets/event-types';
        const url = new URL(`${API_BASE}/${path}`, window.location.origin);
        if (trimmed.length >= 2) {
            url.searchParams.set('q', trimmed);
        }
        const response = await fetch(url.pathname + url.search, { credentials: 'include' });
        if (!response.ok) {
            return;
        }
        const data = await response.json();
        const items = Array.isArray(data.items) ? data.items : [];
        const dl = this.renderRoot?.querySelector(`#${this._datalistIds[kind]}`);
        if (!dl) {
            return;
        }
        dl.innerHTML = '';
        for (const v of items) {
            const opt = document.createElement('option');
            opt.value = v;
            dl.appendChild(opt);
        }
    }

    _buildSpanQueryParams() {
        const p = new URLSearchParams();
        const exSvc = this._fService.trim();
        if (exSvc) {
            p.set('service_name', exSvc);
        }
        const exCo = this._fCompanyExact.trim();
        if (exCo) {
            p.set('company_id', exCo);
        }
        const exUs = this._fUserExact.trim();
        if (exUs) {
            p.set('user_id', exUs);
        }
        const ns = this._fNamespace.trim();
        if (ns) {
            p.set('namespace', ns);
        }
        const qCo = this._fCompany.trim();
        if (qCo.length >= 2) {
            p.set('company_id_query', qCo);
        }
        const qUs = this._fUser.trim();
        if (qUs.length >= 2) {
            p.set('user_id_query', qUs);
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

    _onInputFacet(kind, e) {
        const v = e.target?.value ?? '';
        this._scheduleFacet(kind, v);
    }

    render() {
        const t = (k) => this.i18n.t(k, {});
        return html`
            <page-header
                title=${t('tracing_page.title')}
                subtitle=${t('tracing_page.subtitle')}
            ></page-header>

            <datalist id=${this._datalistIds.company}></datalist>
            <datalist id=${this._datalistIds.user}></datalist>
            <datalist id=${this._datalistIds.service}></datalist>
            <datalist id=${this._datalistIds.event}></datalist>

            <div class="filters">
                <label>
                    ${t('tracing_page.filter_service')}
                    <input
                        type="text"
                        .value=${this._fService}
                        list=${this._datalistIds.service}
                        @input=${(e) => {
                            this._fService = e.target.value;
                            this._onInputFacet('service', e);
                        }}
                    />
                </label>
                <label>
                    ${t('tracing_page.filter_company_exact')}
                    <input
                        type="text"
                        .value=${this._fCompanyExact}
                        @input=${(e) => (this._fCompanyExact = e.target.value)}
                    />
                </label>
                <label>
                    ${t('tracing_page.filter_company_sub')}
                    <input
                        type="text"
                        .value=${this._fCompany}
                        list=${this._datalistIds.company}
                        @input=${(e) => {
                            this._fCompany = e.target.value;
                            this._onInputFacet('company', e);
                        }}
                    />
                </label>
                <label>
                    ${t('tracing_page.filter_user_exact')}
                    <input
                        type="text"
                        .value=${this._fUserExact}
                        @input=${(e) => (this._fUserExact = e.target.value)}
                    />
                </label>
                <label>
                    ${t('tracing_page.filter_user_sub')}
                    <input
                        type="text"
                        .value=${this._fUser}
                        list=${this._datalistIds.user}
                        @input=${(e) => {
                            this._fUser = e.target.value;
                            this._onInputFacet('user', e);
                        }}
                    />
                </label>
                <label>
                    ${t('tracing_page.filter_namespace')}
                    <input
                        type="text"
                        .value=${this._fNamespace}
                        @input=${(e) => (this._fNamespace = e.target.value)}
                    />
                </label>
                <label>
                    ${t('tracing_page.filter_operation_sub')}
                    <input
                        type="text"
                        .value=${this._fOperation}
                        @input=${(e) => (this._fOperation = e.target.value)}
                    />
                </label>
                <label>
                    ${t('tracing_page.filter_event_sub')}
                    <input
                        type="text"
                        .value=${this._fEventType}
                        list=${this._datalistIds.event}
                        @input=${(e) => {
                            this._fEventType = e.target.value;
                            this._onInputFacet('event', e);
                        }}
                    />
                </label>
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
