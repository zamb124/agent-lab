import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/layout/page-header.js';

export class SchedulerTasksPage extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                padding: var(--space-6);
            }

            .toolbar {
                display: flex;
                gap: var(--space-3);
                margin-bottom: var(--space-4);
            }

            .toolbar input,
            .toolbar select {
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-md);
                border: 1px solid var(--border-default);
                background: var(--glass-solid-subtle);
                color: var(--text-primary);
            }

            .table-wrap {
                background: var(--glass-solid-medium);
                border-radius: var(--radius-lg);
                overflow: auto;
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
                vertical-align: middle;
            }

            th {
                background: var(--glass-tint-medium);
                color: var(--text-secondary);
                border-top: none;
            }

            td code {
                font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New',
                    monospace;
                font-size: 12px;
            }

            .schedule-secondary {
                color: var(--text-secondary);
                font-size: var(--text-xs);
                margin-top: 4px;
            }

            button {
                border: 1px solid var(--border-default);
                border-radius: var(--radius-md);
                padding: var(--space-1) var(--space-2);
                cursor: pointer;
                background: var(--glass-solid-subtle);
                color: var(--text-primary);
            }

            .status {
                font-size: var(--text-xs);
                display: inline-flex;
                align-items: center;
                border-radius: 999px;
                padding: 2px 8px;
                border: 1px solid var(--border-default);
            }

            .status.pending {
                background: rgba(59, 130, 246, 0.12);
                color: #1d4ed8;
            }

            .status.paused {
                background: rgba(245, 158, 11, 0.12);
                color: #b45309;
            }

            .status.executed {
                background: rgba(16, 185, 129, 0.12);
                color: #047857;
            }

            .status.cancelled {
                background: rgba(107, 114, 128, 0.12);
                color: #4b5563;
            }

            .status.failed {
                background: rgba(239, 68, 68, 0.12);
                color: #b91c1c;
            }

            .actions-cell {
                width: 56px;
            }

            .actions-menu {
                position: relative;
                display: inline-block;
            }

            .actions-trigger {
                width: 34px;
                height: 34px;
                padding: 0;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                font-size: 18px;
                line-height: 1;
                font-weight: 700;
            }

            .actions-dropdown {
                position: absolute;
                right: 0;
                top: calc(100% + 6px);
                min-width: 170px;
                border: 1px solid var(--border-default);
                background: var(--glass-solid-medium);
                border-radius: var(--radius-md);
                box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);
                overflow: hidden;
                z-index: 20;
                backdrop-filter: blur(10px);
            }

            .menu-item {
                width: 100%;
                border: none;
                border-radius: 0;
                border-bottom: 1px solid var(--border-subtle);
                background: transparent;
                display: flex;
                align-items: center;
                gap: 8px;
                padding: 10px 12px;
                text-align: left;
            }

            .menu-item:last-child {
                border-bottom: none;
            }

            .menu-item:hover {
                background: var(--glass-solid-subtle);
            }

            .menu-item svg {
                width: 16px;
                height: 16px;
                stroke: currentColor;
                fill: none;
                stroke-width: 2;
                flex-shrink: 0;
            }

            .menu-item svg.play-icon {
                fill: currentColor;
                stroke: none;
            }

            .empty {
                padding: var(--space-6);
                color: var(--text-secondary);
            }
        `,
    ];

    static properties = {
        tasks: { state: true },
        loading: { state: true },
        statusFilter: { state: true },
        serviceFilter: { state: true },
        openMenuTaskId: { state: true },
    };

    constructor() {
        super();
        this.tasks = [];
        this.loading = false;
        this.statusFilter = '';
        this.serviceFilter = '';
        this.openMenuTaskId = null;
        this._handleDocumentClick = this._handleDocumentClick.bind(this);
    }

    async connectedCallback() {
        super.connectedCallback();
        document.addEventListener('click', this._handleDocumentClick);
        await this._load();
    }

    disconnectedCallback() {
        document.removeEventListener('click', this._handleDocumentClick);
        super.disconnectedCallback();
    }

    _handleDocumentClick(event) {
        if (!event.target.closest('.actions-menu')) {
            this.openMenuTaskId = null;
        }
    }

    _normalizeTask(task) {
        const normalizedTask = {
            id: task.id,
            target_service: task.target_service,
            task_name: task.task_name,
            status: task.status,
            schedule_type: task.schedule_type,
            cron: task.cron,
            interval_seconds: task.interval_seconds,
            run_at: task.run_at,
            next_run_at: task.next_run_at,
        };
        return normalizedTask;
    }

    _formatDate(value) {
        if (!value) {
            return '—';
        }
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) {
            throw new Error(`Invalid date value: ${value}`);
        }
        return date.toLocaleString('ru-RU', { hour12: false });
    }

    _formatSchedule(task) {
        if (task.schedule_type === 'cron') {
            return `CRON: ${task.cron}`;
        }
        if (task.schedule_type === 'interval') {
            return `Каждые ${task.interval_seconds} сек.`;
        }
        if (task.schedule_type === 'one_time') {
            return `Один раз: ${this._formatDate(task.run_at)}`;
        }
        throw new Error(`Unknown schedule_type: ${task.schedule_type}`);
    }

    _toggleActionsMenu(taskId, event) {
        event.stopPropagation();
        this.openMenuTaskId = this.openMenuTaskId === taskId ? null : taskId;
    }

    async _load() {
        this.loading = true;
        try {
            const response = await this.services.get('schedulerTasks').list({
                status: this.statusFilter || undefined,
                target_service: this.serviceFilter || undefined,
            });
            if (Array.isArray(response)) {
                this.tasks = response.map((task) => this._normalizeTask(task));
                return;
            }
            if (response && Array.isArray(response.items)) {
                this.tasks = response.items.map((task) => this._normalizeTask(task));
                return;
            }
            throw new Error('Scheduler list response must be array');
        } finally {
            this.loading = false;
        }
    }

    async _executeAction(action, taskId) {
        const service = this.services.get('schedulerTasks');
        if (action === 'pause') {
            await service.pause(taskId);
        } else if (action === 'resume') {
            await service.resume(taskId);
        } else if (action === 'cancel') {
            await service.cancel(taskId);
        } else if (action === 'run-now') {
            await service.runNow(taskId);
        } else {
            throw new Error(`Unknown action: ${action}`);
        }
        this.openMenuTaskId = null;
        await this._load();
    }

    async _createSchedule() {
        const targetService = prompt('target_service (например flows)', 'flows');
        if (!targetService) {
            return;
        }
        const taskName = prompt('task_name (например sync_llm_models_task)', 'sync_llm_models_task');
        if (!taskName) {
            return;
        }
        const scheduleType = prompt('schedule_type: cron | interval | one_time', 'interval');
        if (!scheduleType) {
            return;
        }
        const payloadRaw = prompt('payload JSON', '{}');
        if (payloadRaw === null) {
            return;
        }
        const payload = JSON.parse(payloadRaw);
        const request = {
            target_service: targetService,
            task_name: taskName,
            schedule_type: scheduleType,
            timezone: 'UTC',
            payload,
        };
        if (scheduleType === 'cron') {
            request.cron = prompt('cron', '*/5 * * * *');
        } else if (scheduleType === 'interval') {
            request.interval_seconds = Number(prompt('interval_seconds', '60'));
        } else if (scheduleType === 'one_time') {
            request.run_at = prompt('run_at ISO8601', new Date(Date.now() + 60000).toISOString());
        } else {
            throw new Error(`Unknown schedule_type: ${scheduleType}`);
        }
        await this.services.get('schedulerTasks').create(request);
        await this._load();
    }

    render() {
        return html`
            <page-header title="Scheduler задачи"></page-header>

            <div class="toolbar">
                <button @click=${() => this._createSchedule()}>Create</button>
                <select
                    .value=${this.statusFilter}
                    @change=${(event) => {
                        this.statusFilter = event.target.value;
                        this._load();
                    }}
                >
                    <option value="">Все статусы</option>
                    <option value="pending">pending</option>
                    <option value="paused">paused</option>
                    <option value="executed">executed</option>
                    <option value="cancelled">cancelled</option>
                    <option value="failed">failed</option>
                </select>
                <input
                    type="text"
                    placeholder="target_service"
                    .value=${this.serviceFilter}
                    @change=${(event) => {
                        this.serviceFilter = event.target.value.trim();
                        this._load();
                    }}
                />
            </div>

            ${this.loading
                ? html`<div>Загрузка...</div>`
                : html`
                      <div class="table-wrap">
                          <table>
                              <thead>
                                  <tr>
                                      <th>ID</th>
                                      <th>Service</th>
                                      <th>Task</th>
                                      <th>Status</th>
                                      <th>Schedule</th>
                                      <th>Actions</th>
                                  </tr>
                              </thead>
                              <tbody>
                                  ${this.tasks.length === 0
                                      ? html`
                                            <tr>
                                                <td class="empty" colspan="6">Задач пока нет.</td>
                                            </tr>
                                        `
                                      : this.tasks.map(
                                            (task) => html`
                                                <tr>
                                                    <td><code>${task.id}</code></td>
                                                    <td>${task.target_service}</td>
                                                    <td>${task.task_name}</td>
                                                    <td>
                                                        <span class="status ${task.status}">${task.status}</span>
                                                    </td>
                                                    <td>
                                                        ${this._formatSchedule(task)}
                                                        <div class="schedule-secondary">
                                                            Следующий запуск: ${this._formatDate(task.next_run_at)}
                                                        </div>
                                                    </td>
                                                    <td class="actions-cell">
                                                        <div class="actions-menu">
                                                            <button
                                                                class="actions-trigger"
                                                                title="Действия"
                                                                @click=${(event) => this._toggleActionsMenu(task.id, event)}
                                                            >
                                                                ...
                                                            </button>
                                                            ${this.openMenuTaskId === task.id
                                                                ? html`
                                                                      <div class="actions-dropdown">
                                                                          <button
                                                                              class="menu-item"
                                                                              @click=${() => this._executeAction('run-now', task.id)}
                                                                          >
                                                                              <svg class="play-icon" viewBox="0 0 24 24" aria-hidden="true">
                                                                                  <polygon points="8 5 19 12 8 19 8 5"></polygon>
                                                                              </svg>
                                                                              Run now
                                                                          </button>
                                                                          ${task.status === 'paused'
                                                                              ? html`
                                                                                    <button
                                                                                        class="menu-item"
                                                                                        @click=${() => this._executeAction('resume', task.id)}
                                                                                    >
                                                                                        <svg class="play-icon" viewBox="0 0 24 24" aria-hidden="true">
                                                                                            <polygon points="8 5 19 12 8 19 8 5"></polygon>
                                                                                        </svg>
                                                                                        Resume
                                                                                    </button>
                                                                                `
                                                                              : html`
                                                                                    <button
                                                                                        class="menu-item"
                                                                                        @click=${() => this._executeAction('pause', task.id)}
                                                                                    >
                                                                                        <svg viewBox="0 0 24 24" aria-hidden="true">
                                                                                            <rect x="6" y="5" width="4" height="14"></rect>
                                                                                            <rect x="14" y="5" width="4" height="14"></rect>
                                                                                        </svg>
                                                                                        Pause
                                                                                    </button>
                                                                                `}
                                                                          <button
                                                                              class="menu-item"
                                                                              @click=${() => this._executeAction('cancel', task.id)}
                                                                          >
                                                                              <svg viewBox="0 0 24 24" aria-hidden="true">
                                                                                  <line x1="18" y1="6" x2="6" y2="18"></line>
                                                                                  <line x1="6" y1="6" x2="18" y2="18"></line>
                                                                              </svg>
                                                                              Cancel
                                                                          </button>
                                                                      </div>
                                                                  `
                                                                : ''}
                                                        </div>
                                                    </td>
                                                </tr>
                                            `,
                                        )}
                              </tbody>
                          </table>
                      </div>
                  `}
        `;
    }
}

customElements.define('scheduler-tasks-page', SchedulerTasksPage);
