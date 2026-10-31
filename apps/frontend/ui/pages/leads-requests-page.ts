/**
 * Страница заявок leads (system) — список заявок с лендинга.
 *
 * API: GET /frontend/api/lead-requests (доступно только для company=system).
 * 403 → terminal `forbidden`, прочие ошибки → error state.
 *
 * Каждая заявка содержит: lead_request_id, contact_name, email, phone,
 * organization_name, comment, created_at.
 */
import { html, css } from 'lit';

function textOrDash(value: unknown): string {
    if (typeof value === 'string' && value.length > 0) return value;
    if (typeof value === 'number' && Number.isFinite(value) && value !== 0) return String(value);
    return '—';
}
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { frontendIslandPageBodyStyles } from '../styles/frontend-island-page-body.styles.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-spinner.js';
import '@platform/lib/components/platform-empty-state.js';
import type {CSSResultGroup, TemplateResult} from 'lit';
import type { ControllerFor } from '@platform/lib/base/use-resource.js';

export class FrontendLeadsRequestsPage extends PlatformPage {
    static override styles: CSSResultGroup = [
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
        frontendIslandPageBodyStyles,
    ];

    constructor() {
        super();
        this._list = this.useCursorList('frontend/lead_requests', { autoload: true });
    }
    private _list: ControllerFor<'frontend/lead_requests'>;


    _renderForbidden() {
        return html`
            <div class="state forbidden">
                <div class="state-title">${this.t('leads_page.forbidden_title')}</div>
                <div class="state-desc">${this.t('leads_page.forbidden')}</div>
            </div>
        `;
    }

    _renderError(error: string) {
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

    _renderTable(list: Record<string, unknown>[]) {
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
                            <td class="created">${typeof l.created_at === 'string' || typeof l.created_at === 'number' ? new Date(l.created_at).toLocaleString() : ''}</td>
                            <td>${l.contact_name}</td>
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
                            <td>${textOrDash(l.organization_name)}</td>
                            <td class="message">${textOrDash(l.comment)}</td>
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
                            ? html`<platform-spinner size="xs"></platform-spinner>`
                            : this.t('leads_page.load_more')}
                    </button>
                </div>
            ` : ''}
        `;
    }

    override render(): TemplateResult {
        const rawItems = this._list.items;
        const list = Array.isArray(rawItems) ? rawItems : [];
        const loading = this._list.loading;
        const terminal = this._list.terminal;
        const error = this._list.error;
        let body;
        if (loading && list.length === 0) {
            body = html`<platform-empty-state loading></platform-empty-state>`;
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
            <div class="page-body">
            <div class="toolbar">
                <button class="btn"
                    ?disabled=${loading}
                    @click=${() => this._list.load()}
                >
                    ${loading ? html`<platform-spinner size="xs"></platform-spinner>` : this.t('leads_page.reload')}
                </button>
            </div>
            ${body}
            </div>
        `;
    }
}

customElements.define('frontend-leads-requests-page', FrontendLeadsRequestsPage);
