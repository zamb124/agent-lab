/**
 * Leads requests page (system) — список заявок с лендинга.
 *
 * API: GET /frontend/api/lead-requests (доступно только для company=system).
 * 403 → terminal `forbidden`, прочие ошибки → error state.
 *
 * Каждая заявка содержит: storage_key, id, name, email, phone, company,
 * comment, created_at.
 */
import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/glass-spinner.js';

export class FrontendLeadsRequestsPage extends PlatformPage {
    static styles = [
        PlatformPage.styles,
        css`
            :host { display: block; }

            .toolbar {
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

            table { width: 100%; border-collapse: collapse; }
            th, td {
                padding: var(--space-3);
                border-bottom: 1px solid var(--glass-border-subtle);
                text-align: left;
                vertical-align: top;
            }
            th {
                color: var(--text-tertiary); font-size: var(--text-xs);
                text-transform: uppercase; letter-spacing: 0.05em;
            }
            td { color: var(--text-primary); font-size: var(--text-sm); }
            td.created { white-space: nowrap; color: var(--text-tertiary); font-size: var(--text-xs); }
            td.message { max-width: 360px; word-break: break-word; }

            .state {
                padding: var(--space-8) var(--space-6);
                text-align: center;
                background: var(--glass-solid-subtle);
                border: 1px dashed var(--glass-border-subtle);
                border-radius: var(--radius-lg);
            }
            .state .state-title {
                color: var(--text-primary);
                font-weight: var(--font-semibold);
                margin-bottom: var(--space-2);
            }
            .state .state-desc { color: var(--text-tertiary); font-size: var(--text-sm); }
            .state.forbidden { border-color: var(--warning); }
            .state.error { border-color: var(--error); }

            .load-more {
                display: flex; justify-content: center;
                padding: var(--space-3);
            }
        `,
    ];

    constructor() {
        super();
        this._list = this.useCursorList('frontend/lead_requests', { autoload: true });
    }

    _renderForbidden() {
        return html`
            <div class="state forbidden">
                <div class="state-title">${this.t('leads_page.forbidden_title')}</div>
                <div class="state-desc">${this.t('leads_page.forbidden')}</div>
            </div>
        `;
    }

    _renderError(error) {
        return html`
            <div class="state error">
                <div class="state-title">${this.t('leads_page.error_title')}</div>
                <div class="state-desc">${error || this.t('leads_page.load_error')}</div>
            </div>
        `;
    }

    _renderEmpty() {
        return html`
            <div class="state">
                <div class="state-title">${this.t('leads_page.empty_title')}</div>
                <div class="state-desc">${this.t('leads_page.empty_description')}</div>
            </div>
        `;
    }

    _renderTable(list) {
        return html`
            <table>
                <thead><tr>
                    <th>${this.t('leads_page.col_created')}</th>
                    <th>${this.t('leads_page.col_name')}</th>
                    <th>${this.t('leads_page.col_email')}</th>
                    <th>${this.t('leads_page.col_phone')}</th>
                    <th>${this.t('leads_page.col_company')}</th>
                    <th>${this.t('leads_page.col_message')}</th>
                </tr></thead>
                <tbody>
                    ${list.map((l) => html`
                        <tr>
                            <td class="created">${l.created_at ? new Date(l.created_at).toLocaleString() : '—'}</td>
                            <td>${l.name || '—'}</td>
                            <td>
                                ${l.email
                                    ? html`<a href="mailto:${l.email}">${l.email}</a>`
                                    : '—'}
                            </td>
                            <td>
                                ${l.phone
                                    ? html`<a href="tel:${l.phone}">${l.phone}</a>`
                                    : '—'}
                            </td>
                            <td>${l.company || '—'}</td>
                            <td class="message">${l.comment || l.message || '—'}</td>
                        </tr>
                    `)}
                </tbody>
            </table>
            ${this._list.hasMore ? html`
                <div class="load-more">
                    <button class="btn"
                        ?disabled=${this._list.loadingMore}
                        @click=${() => this._list.loadMore()}
                    >
                        ${this._list.loadingMore
                            ? this.t('leads_page.loading')
                            : this.t('leads_page.load_more')}
                    </button>
                </div>
            ` : ''}
        `;
    }

    render() {
        const list = this._list.items;
        const loading = this._list.loading;
        const terminal = this._list.terminal;
        const error = this._list.error;
        let body;
        if (loading && list.length === 0) {
            body = html`<div class="state"><glass-spinner></glass-spinner></div>`;
        } else if (terminal === 'forbidden') {
            body = this._renderForbidden();
        } else if (error) {
            body = this._renderError(error);
        } else if (list.length === 0) {
            body = this._renderEmpty();
        } else {
            body = this._renderTable(list);
        }
        return html`
            <page-header
                title=${this.t('leads_page.title')}
                subtitle=${this.t('leads_page.subtitle')}
            ></page-header>
            <div class="toolbar">
                <button class="btn"
                    ?disabled=${loading}
                    @click=${() => this._list.load()}
                >
                    ${loading ? this.t('leads_page.loading') : this.t('leads_page.reload')}
                </button>
            </div>
            ${body}
        `;
    }
}

customElements.define('frontend-leads-requests-page', FrontendLeadsRequestsPage);
