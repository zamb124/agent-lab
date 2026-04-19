/**
 * CRMAccessRequestsPage — список входящих запросов доступа к сущностям.
 *
 * Маршрут: `/crm/access-requests`. Показывает запросы, где текущий пользователь
 * является owner. Backend публикует ссылки `/crm/access-requests/{id}` в
 * нотификациях, отсюда entry-point.
 *
 * Источники:
 *   - `useResource('crm/access_requests', { autoload: true })` — list через
 *     listQuery({ status, limit, offset }).
 *   - `useOp('crm/access_request_update')` — PUT /access-requests/{id}.
 *
 * UI: chips-фильтр (pending / approved / rejected) → список запросов;
 * для pending — кнопки «Одобрить» / «Отклонить».
 *
 * Подписки:
 *   - `crm/access_request_update.SUCCEEDED` → reload текущего фильтра.
 *   - WS `crm/access_request/created` (если backend публикует) → reload.
 */

import { html, css, nothing } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-breadcrumbs.js';
import '@platform/lib/components/platform-icon.js';

const RESOURCE_NAME = 'crm/access_requests';
const UPDATE_OP = 'crm/access_request_update';

const STATUS_PENDING = 'pending';
const STATUS_APPROVED = 'approved';
const STATUS_REJECTED = 'rejected';
const STATUSES = [STATUS_PENDING, STATUS_APPROVED, STATUS_REJECTED];

const DATE_FORMAT = new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
});

function _formatDate(value) {
    if (typeof value !== 'string' || value.length === 0) return '';
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return value;
    return DATE_FORMAT.format(d);
}

export class CRMAccessRequestsPage extends PlatformPage {
    static i18nNamespace = 'crm';

    static properties = {
        _status: { state: true },
    };

    static styles = [
        PlatformPage.styles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                width: 100%;
                height: 100%;
                min-height: 0;
                overflow: hidden;
            }

            .breadcrumbs-wrap {
                flex-shrink: 0;
                padding: 0 var(--space-4);
                margin-top: var(--space-2);
                margin-bottom: var(--space-2);
            }

            .header-wrap {
                flex-shrink: 0;
                padding: 0 var(--space-4);
            }

            .filters {
                display: flex;
                gap: var(--space-2);
                padding: 0 var(--space-4) var(--space-3);
            }
            .chip {
                padding: 6px 14px;
                border: 1px solid var(--crm-stroke);
                background: var(--crm-surface);
                color: var(--text-secondary);
                border-radius: var(--radius-full);
                font-size: var(--text-sm);
                cursor: pointer;
            }
            .chip.active {
                background: var(--accent);
                color: white;
                border-color: var(--accent);
            }
            .chip:hover:not(.active) {
                background: var(--crm-surface-muted);
                color: var(--text-primary);
            }

            .body {
                flex: 1;
                min-height: 0;
                padding: 0 var(--space-4) var(--space-4);
                overflow-y: auto;
            }

            .center {
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                gap: var(--space-3);
                height: 100%;
                color: var(--text-tertiary);
                text-align: center;
                padding: var(--space-6);
            }

            .list {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                max-width: 880px;
            }

            .request {
                display: grid;
                grid-template-columns: 1fr auto;
                gap: var(--space-3);
                padding: var(--space-4);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-lg);
                background: var(--crm-surface);
            }

            .request-main {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                min-width: 0;
            }
            .request-title {
                margin: 0;
                font-size: var(--text-base);
                font-weight: 600;
                color: var(--text-primary);
            }
            .request-title button {
                background: transparent;
                border: none;
                color: var(--accent);
                cursor: pointer;
                padding: 0;
                font: inherit;
                font-weight: 600;
            }
            .request-title button:hover { text-decoration: underline; }

            .request-meta {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-3);
                color: var(--text-tertiary);
                font-size: var(--text-xs);
            }
            .request-meta span {
                display: inline-flex;
                align-items: center;
                gap: 4px;
            }

            .request-message {
                margin: 0;
                color: var(--text-secondary);
                font-size: var(--text-sm);
                line-height: 1.4;
                white-space: pre-wrap;
                padding: var(--space-2) var(--space-3);
                background: var(--glass-tint-subtle);
                border-radius: var(--radius-md);
            }

            .status-badge {
                display: inline-flex;
                align-items: center;
                padding: 2px 8px;
                font-size: var(--text-xs);
                border-radius: var(--radius-full);
            }
            .status-badge.pending { background: rgba(234, 179, 8, 0.15); color: #ca8a04; }
            .status-badge.approved { background: rgba(34, 197, 94, 0.15); color: #16a34a; }
            .status-badge.rejected { background: rgba(244, 63, 94, 0.15); color: #e11d48; }

            .request-actions {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                align-items: stretch;
            }
            .btn {
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-md);
                font-size: var(--text-sm);
                font-weight: 500;
                cursor: pointer;
                border: 1px solid var(--crm-stroke);
                background: var(--crm-surface);
                color: var(--text-secondary);
            }
            .btn:hover:not(:disabled) {
                background: var(--crm-surface-muted);
                color: var(--text-primary);
            }
            .btn-approve {
                background: rgba(34, 197, 94, 0.1);
                border-color: rgba(34, 197, 94, 0.4);
                color: #16a34a;
            }
            .btn-approve:hover:not(:disabled) {
                background: #16a34a;
                color: white;
                border-color: #16a34a;
            }
            .btn-reject {
                background: rgba(244, 63, 94, 0.1);
                border-color: rgba(244, 63, 94, 0.4);
                color: #e11d48;
            }
            .btn-reject:hover:not(:disabled) {
                background: #e11d48;
                color: white;
                border-color: #e11d48;
            }
            .btn:disabled { opacity: 0.5; cursor: not-allowed; }
        `,
    ];

    constructor() {
        super();
        this._status = STATUS_PENDING;
        this._requests = this.useResource(RESOURCE_NAME);
        this._updateOp = this.useOp(UPDATE_OP);
    }

    connectedCallback() {
        super.connectedCallback();
        this._reload();

        this.useEvent(this._updateOp.op.events.SUCCEEDED, () => this._reload());
        this.useEvent('crm/access_request/created', () => this._reload());
        this.useEvent('crm/access_request/updated', () => this._reload());
    }

    _reload() {
        this._requests.load({ status: this._status, limit: 100, offset: 0 });
    }

    _onPickStatus(status) {
        if (STATUSES.indexOf(status) === -1) return;
        this._status = status;
        this._reload();
    }

    _onApprove(requestId) {
        this._updateOp.run({ request_id: requestId, body: { status: STATUS_APPROVED } });
    }

    _onReject(requestId) {
        this._updateOp.run({ request_id: requestId, body: { status: STATUS_REJECTED } });
    }

    _onOpenEntity(entityId) {
        if (typeof entityId !== 'string' || entityId.length === 0) return;
        this.navigate('entity', { itemId: entityId });
    }

    render() {
        const items = this._requests.items;
        const loading = this._requests.loading;
        const updating = this._updateOp.busy;

        return html`
            <div class="breadcrumbs-wrap">
                <platform-breadcrumbs></platform-breadcrumbs>
            </div>
            <div class="header-wrap">
                <page-header
                    title=${this.t('access_requests_page.title')}
                    subtitle=${this.t('access_requests_page.subtitle')}
                ></page-header>
            </div>
            <div class="filters">
                ${STATUSES.map((status) => html`
                    <button
                        type="button"
                        class="chip ${this._status === status ? 'active' : ''}"
                        @click=${() => this._onPickStatus(status)}
                    >
                        ${this.t(`access_requests_page.filter_${status}`)}
                    </button>
                `)}
            </div>
            <div class="body">
                ${loading && items.length === 0
                    ? html`<div class="center"><glass-spinner size="lg"></glass-spinner></div>`
                    : items.length === 0
                        ? html`
                            <div class="center">
                                <platform-icon name="lock" size="48"></platform-icon>
                                <p>${this.t(`access_requests_page.empty_${this._status}`)}</p>
                            </div>
                        `
                        : html`
                            <div class="list">
                                ${items.map((req) => this._renderRequest(req, updating))}
                            </div>
                        `}
            </div>
        `;
    }

    _renderRequest(req, updating) {
        const resourceTitle = typeof req.resource_title === 'string' && req.resource_title.length > 0
            ? req.resource_title
            : req.resource_id;
        const requesterName = typeof req.requester_name === 'string' && req.requester_name.length > 0
            ? req.requester_name
            : req.requester_id;
        const isPending = req.status === STATUS_PENDING;
        const message = typeof req.message === 'string' && req.message.length > 0 ? req.message : '';

        return html`
            <article class="request">
                <div class="request-main">
                    <h3 class="request-title">
                        ${this.t('access_requests_page.requester_label')}
                        ${requesterName}
                        ${this.t('access_requests_page.requests_access_to')}
                        <button type="button" @click=${() => this._onOpenEntity(req.resource_id)}>
                            ${resourceTitle}
                        </button>
                    </h3>
                    <div class="request-meta">
                        <span>
                            <platform-icon name="calendar" size="11"></platform-icon>
                            ${_formatDate(req.created_at)}
                        </span>
                        <span class="status-badge ${req.status}">
                            ${this.t(`access_requests_page.status_${req.status}`)}
                        </span>
                    </div>
                    ${message.length > 0
                        ? html`<p class="request-message">${message}</p>`
                        : nothing}
                </div>
                ${isPending ? html`
                    <div class="request-actions">
                        <button
                            type="button"
                            class="btn btn-approve"
                            ?disabled=${updating}
                            @click=${() => this._onApprove(req.request_id)}
                        >
                            <platform-icon name="check" size="14"></platform-icon>
                            ${this.t('access_requests_page.action_approve')}
                        </button>
                        <button
                            type="button"
                            class="btn btn-reject"
                            ?disabled=${updating}
                            @click=${() => this._onReject(req.request_id)}
                        >
                            <platform-icon name="close" size="14"></platform-icon>
                            ${this.t('access_requests_page.action_reject')}
                        </button>
                    </div>
                ` : nothing}
            </article>
        `;
    }
}

customElements.define('crm-access-requests-page', CRMAccessRequestsPage);
