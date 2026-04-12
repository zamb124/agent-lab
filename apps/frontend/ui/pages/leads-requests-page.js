/**
 * Страница списка заявок с лендинга (только компания system).
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/layout/page-header.js';

export class LeadsRequestsPage extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
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
                padding: var(--space-3) var(--space-4);
                border-top: 1px solid var(--border-subtle);
                text-align: left;
                font-size: var(--text-sm);
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
            }
        `,
    ];

    static properties = {
        _items: { type: Array, state: true },
        _loading: { type: Boolean, state: true },
        _error: { type: String, state: true },
    };

    constructor() {
        super();
        this._items = [];
        this._loading = true;
        this._error = '';
    }

    connectedCallback() {
        super.connectedCallback();
        void this._load();
    }

    async _load() {
        this._loading = true;
        this._error = '';
        const response = await fetch('/frontend/api/lead-requests', {
            credentials: 'include',
        });
        if (response.status === 403) {
            this._error = this.i18n.t('leads_page.forbidden', {});
            this._items = [];
            this._loading = false;
            return;
        }
        if (!response.ok) {
            this._error = this.i18n.t('leads_page.load_error', {});
            this._items = [];
            this._loading = false;
            return;
        }
        const data = await response.json();
        this._items = Array.isArray(data.items) ? data.items : [];
        this._loading = false;
    }

    render() {
        const t = (k) => this.i18n.t(k, {});
        return html`
            <page-header
                title=${t('leads_page.title')}
                subtitle=${t('leads_page.subtitle')}
            ></page-header>

            ${this._error
                ? html`<div class="error-box">${this._error}</div>`
                : ''}

            ${this._loading
                ? html`<p class="muted">${t('leads_page.loading')}</p>`
                : html`
                      <div class="table-wrap">
                          <table>
                              <thead>
                                  <tr>
                                      <th>${t('leads_page.col_created')}</th>
                                      <th>${t('leads_page.col_name')}</th>
                                      <th>${t('leads_page.col_email')}</th>
                                      <th>${t('leads_page.col_phone')}</th>
                                      <th>${t('leads_page.col_company')}</th>
                                      <th>${t('leads_page.col_comment')}</th>
                                  </tr>
                              </thead>
                              <tbody>
                                  ${this._items.length === 0
                                      ? html`<tr>
                                            <td colspan="6" class="muted">${t('leads_page.empty')}</td>
                                        </tr>`
                                      : this._items.map(
                                            (row) => html`
                                                <tr>
                                                    <td>${row.created_at ?? ''}</td>
                                                    <td>${row.name ?? ''}</td>
                                                    <td>${row.email ?? ''}</td>
                                                    <td>${row.phone ?? ''}</td>
                                                    <td>${row.company ?? ''}</td>
                                                    <td>${row.comment ?? ''}</td>
                                                </tr>
                                            `
                                        )}
                              </tbody>
                          </table>
                      </div>
                  `}
        `;
    }
}

customElements.define('leads-requests-page', LeadsRequestsPage);
