/**
 * CRMNamespaceTasksPage — журнал системных TaskIQ-задач выбранного пространства.
 *
 * Источник данных:
 *  - useResource('crm/tasks', { autoload: false }) — список задач (OffsetPage).
 *    Запрашиваем вручную через `_loadTasks()` после получения namespace,
 *    потому что backend требует параметр `namespace`.
 *
 * Управление задачами (createAsyncOp):
 *  - crm/task_cancel           — POST /tasks/{id}/cancel        (для pending/running)
 *  - crm/task_retry            — POST /tasks/{id}/retry         (для failed/cancelled)
 *  - crm/task_rollback         — POST /tasks/{id}/rollback      (только knowledge_import)
 *  - crm/task_review_complete  — POST /tasks/{id}/review-complete (status=review_required)
 *
 * Live-обновление: пока есть хотя бы одна задача в `pending|running`, опрашиваем
 * список каждые 3000ms (silent reload). Дополнительно подписываемся на доменное
 * событие `crm/task/updated` (если backend публикует) и на UI_NAMESPACE_CHANGED.
 *
 * Wizard knowledge-import живёт отдельной модалкой `crm.knowledge_import`
 * (PlatformModal). Открывается кнопкой в toolbar страницы (только при
 * выбранном конкретном namespace).
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { CoreEvents } from '@platform/lib/events/index.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-breadcrumbs.js';

const POLL_MS = 3000;

const TASK_TYPE_FILTERS = Object.freeze([
    Object.freeze({ id: '', labelKey: 'namespace_tasks_page.filter_all' }),
    Object.freeze({ id: 'knowledge_import', labelKey: 'namespace_tasks_page.filter_knowledge_import' }),
    Object.freeze({ id: 'note_analyze', labelKey: 'namespace_tasks_page.filter_note_analyze' }),
    Object.freeze({ id: 'daily_summary', labelKey: 'namespace_tasks_page.filter_daily_summary' }),
    Object.freeze({ id: 'period_summary', labelKey: 'namespace_tasks_page.filter_period_summary' }),
]);

const ACTIVE_STATUSES = new Set(['pending', 'running']);

const TYPE_LABEL_KEYS = Object.freeze({
    knowledge_import: 'namespace_tasks_page.type_knowledge_import',
    note_analyze: 'namespace_tasks_page.type_note_analyze',
    daily_summary: 'namespace_tasks_page.type_daily_summary',
    period_summary: 'namespace_tasks_page.type_period_summary',
});

const STATUS_LABEL_KEYS = Object.freeze({
    pending: 'namespace_tasks_page.status_pending',
    running: 'namespace_tasks_page.status_running',
    completed: 'namespace_tasks_page.status_completed',
    failed: 'namespace_tasks_page.status_failed',
    cancelled: 'namespace_tasks_page.status_cancelled',
    review_required: 'namespace_tasks_page.status_review_required',
});

function statusVariant(status) {
    switch (status) {
        case 'completed':
            return 'ok';
        case 'failed':
            return 'error';
        case 'cancelled':
            return 'muted';
        case 'review_required':
            return 'warn';
        case 'running':
            return 'progress';
        case 'pending':
        default:
            return 'pending';
    }
}

function formatDateTime(value) {
    if (typeof value !== 'string' || value.length === 0) {
        return '—';
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
        return value;
    }
    return date.toLocaleString();
}

export class CRMNamespaceTasksPage extends PlatformPage {
    static i18nNamespace = 'crm';

    static properties = {
        _typeFilter: { state: true },
        _polling: { state: true },
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

            .scroll {
                flex: 1;
                min-height: 0;
                overflow-y: auto;
                overflow-x: hidden;
                padding: var(--space-2);
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }

            .breadcrumbs-wrap {
                flex-shrink: 0;
                padding: var(--space-2) var(--space-2) 0;
            }

            .panel {
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-xl);
                padding: var(--space-4);
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }

            .toolbar {
                display: flex;
                gap: var(--space-2);
                flex-wrap: wrap;
                align-items: center;
                justify-content: space-between;
            }

            .filters {
                display: flex;
                gap: var(--space-2);
                flex-wrap: wrap;
            }

            .filter-pill {
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-medium);
                color: var(--text-secondary);
                border-radius: var(--radius-full);
                padding: 4px var(--space-3);
                font: inherit;
                font-size: var(--text-sm);
                cursor: pointer;
            }

            .filter-pill.active {
                border-color: var(--accent);
                color: var(--text-primary);
                background: var(--accent-subtle);
            }

            .reload-btn {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-medium);
                color: var(--text-primary);
                border-radius: var(--radius-md);
                padding: var(--space-2) var(--space-3);
                font: inherit;
                font-size: var(--text-sm);
                cursor: pointer;
            }

            .reload-btn:hover:not(:disabled) {
                border-color: var(--accent);
            }

            .reload-btn:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }

            .empty {
                color: var(--text-tertiary);
                font-size: var(--text-sm);
                text-align: center;
                padding: var(--space-6) var(--space-3);
            }

            .table-shell {
                width: 100%;
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                background: var(--glass-solid-medium);
                overflow: hidden;
            }

            table {
                width: 100%;
                border-collapse: collapse;
                font-size: var(--text-sm);
            }

            thead th {
                text-align: left;
                padding: var(--space-3);
                color: var(--text-secondary);
                font-weight: var(--font-semibold);
                font-size: var(--text-xs);
                text-transform: uppercase;
                letter-spacing: 0.04em;
                border-bottom: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
            }

            tbody td {
                padding: var(--space-3);
                border-bottom: 1px solid var(--glass-border-subtle);
                vertical-align: top;
            }

            tbody tr:last-child td {
                border-bottom: none;
            }

            tbody tr:hover td {
                background: var(--glass-solid-subtle);
            }

            .mono {
                font-family: var(--font-mono, ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace);
                font-size: var(--text-xs);
            }

            .status {
                display: inline-flex;
                align-items: center;
                gap: 6px;
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                padding: 2px var(--space-2);
                border-radius: var(--radius-full);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-secondary);
                white-space: nowrap;
            }

            .status.ok       { border-color: var(--success-border); color: var(--success); background: var(--success-bg); }
            .status.error    { border-color: var(--error-border);   color: var(--error);   background: var(--error-bg); }
            .status.warn     { border-color: var(--warning-border); color: var(--warning); background: var(--warning-bg); }
            .status.muted    { color: var(--text-tertiary); }
            .status.progress { border-color: var(--info-border);    color: var(--info);    background: var(--info-bg); }
            .status.pending  { border-color: var(--glass-border-strong); color: var(--text-secondary); background: var(--glass-solid-medium); }

            .progress-bar {
                width: 100%;
                height: 6px;
                background: var(--glass-solid-subtle);
                border-radius: var(--radius-full);
                overflow: hidden;
                border: 1px solid var(--glass-border-subtle);
            }

            .progress-bar > div {
                height: 100%;
                background: var(--accent);
                transition: width var(--duration-fast);
            }

            .stage {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                margin-top: 4px;
            }

            .actions {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-1);
                justify-content: flex-end;
            }

            .action-btn {
                display: inline-flex;
                align-items: center;
                gap: 4px;
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-medium);
                color: var(--text-primary);
                border-radius: var(--radius-md);
                padding: 4px var(--space-2);
                font: inherit;
                font-size: var(--text-xs);
                cursor: pointer;
            }

            .action-btn:hover:not(:disabled) {
                border-color: var(--accent);
            }

            .action-btn.danger {
                color: var(--error);
                border-color: var(--error-border);
                background: var(--error-bg);
            }

            .action-btn:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }

            .err {
                color: var(--error);
                font-size: var(--text-xs);
                margin-top: 4px;
                white-space: pre-wrap;
                word-break: break-word;
            }

            .live-dot {
                display: inline-block;
                width: 8px;
                height: 8px;
                border-radius: 50%;
                background: var(--success);
                box-shadow: 0 0 6px var(--success-border);
                animation: pulse 1.4s ease-in-out infinite;
            }

            @keyframes pulse {
                0%, 100% { opacity: 0.6; }
                50%      { opacity: 1; }
            }
        `,
    ];

    constructor() {
        super();
        this._typeFilter = '';
        this._polling = false;
        this._pollTimer = null;
        this._lastNamespace = null;

        this._tasks = this.useResource('crm/tasks');
        this._cancelOp = this.useOp('crm/task_cancel');
        this._retryOp = this.useOp('crm/task_retry');
        this._rollbackOp = this.useOp('crm/task_rollback');
        this._reviewCompleteOp = this.useOp('crm/task_review_complete');

        this._namespaceSel = this.select((s) => {
            const user = s.auth.user;
            if (!user || typeof user.company_id !== 'string') {
                return '__all__';
            }
            const cid = user.company_id;
            const map = s.ui.namespace.selectionByCompany;
            const sel = map[cid];
            if (sel === 'all' || sel === undefined || sel === null) {
                return '__all__';
            }
            return sel;
        });
    }

    connectedCallback() {
        super.connectedCallback();
        this.useEvent(CoreEvents.UI_NAMESPACE_CHANGED, () => this._loadTasks());
        this.useEvent('crm/task/updated', () => this._loadTasks());
        this.useEvent('crm/daily_summary/updated', () => this._loadTasks());
        this.useEvent(this._cancelOp.op.events.SUCCEEDED, () => this._loadTasks());
        this.useEvent(this._retryOp.op.events.SUCCEEDED, () => this._loadTasks());
        this.useEvent(this._rollbackOp.op.events.SUCCEEDED, () => this._loadTasks());
        this.useEvent(this._reviewCompleteOp.op.events.SUCCEEDED, () => this._loadTasks());
        this.useEvent(this._tasks.resource.events.LIST_LOADED, () => this._maybeStartPolling());
        this._loadTasks();
    }

    disconnectedCallback() {
        this._stopPolling();
        super.disconnectedCallback();
    }

    _currentNamespace() {
        return this._namespaceSel.value;
    }

    _loadTasks() {
        const namespace = this._currentNamespace();
        this._lastNamespace = namespace;
        const payload = { limit: 100, offset: 0 };
        if (typeof namespace === 'string' && namespace.length > 0 && namespace !== '__all__') {
            payload.namespace = namespace;
        }
        if (this._typeFilter.length > 0) {
            payload.task_type = this._typeFilter;
        }
        this._tasks.load(payload);
    }

    _maybeStartPolling() {
        const items = this._tasks.items;
        const hasActive = items.some((row) => ACTIVE_STATUSES.has(row.status));
        if (hasActive) {
            this._startPolling();
        } else {
            this._stopPolling();
        }
    }

    _startPolling() {
        if (this._pollTimer !== null) {
            return;
        }
        this._polling = true;
        this._pollTimer = window.setInterval(() => {
            this._loadTasks();
        }, POLL_MS);
    }

    _stopPolling() {
        if (this._pollTimer !== null) {
            window.clearInterval(this._pollTimer);
            this._pollTimer = null;
        }
        this._polling = false;
    }

    _setTypeFilter(typeId) {
        if (typeof typeId !== 'string') {
            throw new Error('CRMNamespaceTasksPage._setTypeFilter: typeId required (string)');
        }
        this._typeFilter = typeId;
        this._loadTasks();
    }

    async _onCancel(task) {
        if (!task || typeof task.task_id !== 'string') {
            throw new Error('_onCancel: task.task_id required');
        }
        const confirmed = await platformConfirm(
            this.t('namespace_tasks_page.confirm_cancel_msg', { task_id: task.task_id }),
            {
                title: this.t('namespace_tasks_page.confirm_cancel_title'),
                variant: 'warning',
                confirmText: this.t('namespace_tasks_page.confirm_cancel_ok'),
                cancelText: this.t('namespace_tasks_page.btn_back'),
            },
        );
        if (!confirmed) {
            return;
        }
        this._cancelOp.run({ task_id: task.task_id });
    }

    _onRetry(task) {
        if (!task || typeof task.task_id !== 'string') {
            throw new Error('_onRetry: task.task_id required');
        }
        this._retryOp.run({ task_id: task.task_id });
    }

    async _onRollback(task) {
        if (!task || typeof task.task_id !== 'string') {
            throw new Error('_onRollback: task.task_id required');
        }
        const confirmed = await platformConfirm(
            this.t('namespace_tasks_page.confirm_rollback_msg', { task_id: task.task_id }),
            {
                title: this.t('namespace_tasks_page.confirm_rollback_title'),
                variant: 'danger',
                confirmText: this.t('namespace_tasks_page.confirm_rollback_ok'),
                cancelText: this.t('namespace_tasks_page.btn_back'),
            },
        );
        if (!confirmed) {
            return;
        }
        this._rollbackOp.run({ task_id: task.task_id });
    }

    _onReviewComplete(task) {
        if (!task || typeof task.task_id !== 'string') {
            throw new Error('_onReviewComplete: task.task_id required');
        }
        this._reviewCompleteOp.run({ task_id: task.task_id });
    }

    _typeLabel(taskType) {
        if (typeof taskType !== 'string' || taskType.length === 0) {
            return this.t('namespace_tasks_page.type_unknown');
        }
        const key = TYPE_LABEL_KEYS[taskType];
        if (typeof key !== 'string') {
            return taskType;
        }
        return this.t(key);
    }

    _statusLabel(status) {
        if (typeof status !== 'string' || status.length === 0) {
            return this.t('namespace_tasks_page.status_unknown');
        }
        const key = STATUS_LABEL_KEYS[status];
        if (typeof key !== 'string') {
            return status;
        }
        return this.t(key);
    }

    _isAnyOpBusy() {
        return (
            this._cancelOp.busy
            || this._retryOp.busy
            || this._rollbackOp.busy
            || this._reviewCompleteOp.busy
        );
    }

    render() {
        const namespace = this._currentNamespace();
        const tasks = this._tasks.items;
        const loading = this._tasks.loading;
        return html`
            <div class="breadcrumbs-wrap">
                <platform-breadcrumbs></platform-breadcrumbs>
            </div>
            <page-header
                title=${this.t('namespace_tasks_page.title')}
                subtitle=${this.t('namespace_tasks_page.subtitle')}
            ></page-header>
            <div class="scroll">
                ${this._renderTasksPanel(tasks, loading, namespace)}
            </div>
        `;
    }

    _renderTasksPanel(tasks, loading, namespace) {
        return html`
            <div class="panel">
                <div class="toolbar">
                    <div class="filters">
                        ${TASK_TYPE_FILTERS.map((flt) => html`
                            <button
                                type="button"
                                class="filter-pill ${this._typeFilter === flt.id ? 'active' : ''}"
                                @click=${() => this._setTypeFilter(flt.id)}
                            >
                                ${this.t(flt.labelKey)}
                            </button>
                        `)}
                    </div>
                    <div style="display:inline-flex;align-items:center;gap:var(--space-3);">
                        ${this._polling
                            ? html`<span class="live-dot" title=${this.t('namespace_tasks_page.live_polling')}></span>`
                            : ''}
                        ${namespace !== '__all__' ? html`
                            <button
                                type="button"
                                class="reload-btn"
                                @click=${() => this.openModal('crm.knowledge_import')}
                            >
                                <platform-icon name="cloud" size="14"></platform-icon>
                                ${this.t('namespace_tasks_page.action_import')}
                            </button>
                        ` : ''}
                        <button
                            type="button"
                            class="reload-btn"
                            ?disabled=${loading}
                            @click=${() => this._loadTasks()}
                        >
                            <platform-icon name="refresh" size="14"></platform-icon>
                            ${loading
                                ? this.t('namespace_tasks_page.loading')
                                : this.t('namespace_tasks_page.refresh')}
                        </button>
                    </div>
                </div>
                <div class="mono" style="color: var(--text-tertiary); font-size: var(--text-xs);">
                    ${namespace === '__all__'
                        ? this.t('namespace_tasks_page.namespace_label_all')
                        : this.t('namespace_tasks_page.namespace_label', { namespace })}
                </div>
                ${tasks.length > 0
                    ? this._renderTable(tasks)
                    : html`<div class="empty">${this.t('namespace_tasks_page.empty')}</div>`}
            </div>
        `;
    }

    _renderTable(tasks) {
        return html`
            <div class="table-shell">
                <table>
                    <thead>
                        <tr>
                            <th>${this.t('namespace_tasks_page.col_created')}</th>
                            <th>${this.t('namespace_tasks_page.col_type')}</th>
                            <th>${this.t('namespace_tasks_page.col_status')}</th>
                            <th>${this.t('namespace_tasks_page.col_progress')}</th>
                            <th style="text-align:right;">${this.t('namespace_tasks_page.col_actions')}</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${tasks.map((task) => this._renderRow(task))}
                    </tbody>
                </table>
            </div>
        `;
    }

    _renderRow(task) {
        const variant = statusVariant(task.status);
        const showCancel = ACTIVE_STATUSES.has(task.status) && task.cancel_requested !== true;
        const showRetry = task.status === 'failed' || task.status === 'cancelled';
        const showRollback = task.task_type === 'knowledge_import' && task.status === 'completed';
        const showReviewComplete = task.task_type === 'knowledge_import' && task.status === 'review_required';
        const opBusy = this._isAnyOpBusy();
        return html`
            <tr>
                <td class="mono">${formatDateTime(task.created_at)}</td>
                <td>
                    <div>${this._typeLabel(task.task_type)}</div>
                    <div class="mono" style="color: var(--text-tertiary);">${task.task_id}</div>
                </td>
                <td>
                    <span class="status ${variant}">
                        ${this._statusLabel(task.status)}
                    </span>
                    ${task.cancel_requested
                        ? html`<div class="stage">${this.t('namespace_tasks_page.cancel_requested')}</div>`
                        : ''}
                    ${task.error_message
                        ? html`<div class="err">${task.error_message}</div>`
                        : ''}
                </td>
                <td>
                    <div class="progress-bar">
                        <div style="width: ${Math.max(0, Math.min(100, task.progress_pct))}%"></div>
                    </div>
                    <div class="stage">
                        ${task.progress_pct}% · ${task.stage || this.t('namespace_tasks_page.no_stage')}
                    </div>
                </td>
                <td>
                    <div class="actions">
                        ${showCancel ? html`
                            <button
                                type="button"
                                class="action-btn danger"
                                ?disabled=${opBusy}
                                @click=${() => this._onCancel(task)}
                            >
                                <platform-icon name="close" size="12"></platform-icon>
                                ${this.t('namespace_tasks_page.action_cancel')}
                            </button>
                        ` : ''}
                        ${showRetry ? html`
                            <button
                                type="button"
                                class="action-btn"
                                ?disabled=${opBusy}
                                @click=${() => this._onRetry(task)}
                            >
                                <platform-icon name="refresh" size="12"></platform-icon>
                                ${this.t('namespace_tasks_page.action_retry')}
                            </button>
                        ` : ''}
                        ${showReviewComplete ? html`
                            <button
                                type="button"
                                class="action-btn"
                                ?disabled=${opBusy}
                                @click=${() => this._onReviewComplete(task)}
                            >
                                <platform-icon name="check" size="12"></platform-icon>
                                ${this.t('namespace_tasks_page.action_review_complete')}
                            </button>
                        ` : ''}
                        ${showRollback ? html`
                            <button
                                type="button"
                                class="action-btn danger"
                                ?disabled=${opBusy}
                                @click=${() => this._onRollback(task)}
                            >
                                <platform-icon name="rotate-ccw" size="12"></platform-icon>
                                ${this.t('namespace_tasks_page.action_rollback')}
                            </button>
                        ` : ''}
                    </div>
                </td>
            </tr>
        `;
    }
}

customElements.define('crm-namespace-tasks-page', CRMNamespaceTasksPage);
