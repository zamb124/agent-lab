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

            .redis-panel {
                margin-top: var(--space-4);
                border: 1px solid var(--border-default);
                border-radius: var(--radius-lg);
                background: var(--glass-solid-medium);
                padding: var(--space-4);
            }

            .redis-panel-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: var(--space-3);
                font-weight: 600;
            }

            .redis-panel pre {
                margin: 0;
                white-space: pre-wrap;
                word-break: break-word;
                font-size: 12px;
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
        menuPosition: { state: true },
        redisSnapshot: { state: true },
        redisSnapshotLoading: { state: true },
    };

    constructor() {
        super();
        this.tasks = [];
        this.loading = false;
        this.statusFilter = '';
        this.serviceFilter = '';
        this.openMenuTaskId = null;
        this.menuPosition = null;
        this.redisSnapshot = null;
        this.redisSnapshotLoading = false;
        this._handleDocumentClick = this._handleDocumentClick.bind(this);
        this._handleWindowScroll = this._handleWindowScroll.bind(this);
    }

    async connectedCallback() {
        super.connectedCallback();
        document.addEventListener('click', this._handleDocumentClick);
        window.addEventListener('scroll', this._handleWindowScroll, true);
        await this._load();
    }

    disconnectedCallback() {
        document.removeEventListener('click', this._handleDocumentClick);
        window.removeEventListener('scroll', this._handleWindowScroll, true);
        super.disconnectedCallback();
    }

    _handleDocumentClick(event) {
        if (!event.target.closest('.actions-menu') && !event.target.closest('.actions-dropdown')) {
            this.openMenuTaskId = null;
            this.menuPosition = null;
        }
    }

    _handleWindowScroll() {
        this.openMenuTaskId = null;
        this.menuPosition = null;
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
        if (this.openMenuTaskId === taskId) {
            this.openMenuTaskId = null;
            this.menuPosition = null;
            return;
        }
        const triggerRect = event.currentTarget.getBoundingClientRect();
        this.openMenuTaskId = taskId;
        this.menuPosition = {
            top: triggerRect.bottom + 6,
            left: triggerRect.right,
        };
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
        this.menuPosition = null;
        await this._load();
    }

    async _openRedisSnapshot(taskId) {
        this.redisSnapshotLoading = true;
        try {
            this.redisSnapshot = await this.services.get('schedulerTasks').getRedisSnapshot(taskId);
            this.openMenuTaskId = null;
            this.menuPosition = null;
        } finally {
            this.redisSnapshotLoading = false;
        }
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
                                                        </div>
                                                    </td>
                                                </tr>
                                            `,
                                        )}
                              </tbody>
                          </table>
                      </div>
                      ${this.openMenuTaskId && this.menuPosition
                          ? html`
                                <div
                                    class="actions-dropdown"
                                    style="position: fixed; top: ${this.menuPosition.top}px; left: ${this.menuPosition.left}px; transform: translateX(-100%);"
                                >
                                    <button
                                        class="menu-item"
                                        @click=${() => this._executeAction('run-now', this.openMenuTaskId)}
                                    >
                                        <svg class="play-icon" viewBox="0 0 24 24" aria-hidden="true">
                                            <polygon points="8 5 19 12 8 19 8 5"></polygon>
                                        </svg>
                                        Run now
                                    </button>
                                    <button
                                        class="menu-item"
                                        @click=${() => this._openRedisSnapshot(this.openMenuTaskId)}
                                    >
                                        <svg viewBox="0 0 24 24" aria-hidden="true">
                                            <ellipse cx="12" cy="6" rx="7" ry="3"></ellipse>
                                            <path d="M5 6v6c0 1.7 3.1 3 7 3s7-1.3 7-3V6"></path>
                                            <path d="M5 12v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6"></path>
                                        </svg>
                                        Redis snapshot
                                    </button>
                                    ${this.tasks.find((task) => task.id === this.openMenuTaskId)?.status === 'paused'
                                        ? html`
                                              <button
                                                  class="menu-item"
                                                  @click=${() => this._executeAction('resume', this.openMenuTaskId)}
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
                                                  @click=${() => this._executeAction('pause', this.openMenuTaskId)}
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
                                        @click=${() => this._executeAction('cancel', this.openMenuTaskId)}
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
                      ${this.redisSnapshotLoading
                          ? html`
                                <div class="redis-panel">
                                    <div class="redis-panel-header">Redis snapshot</div>
                                    <div>Загрузка...</div>
                                </div>
                            `
                          : ''}
                      ${this.redisSnapshot
                          ? html`
                                <div class="redis-panel">
                                    <div class="redis-panel-header">
                                        <span>Redis snapshot: ${this.redisSnapshot.schedule_task_id}</span>
                                        <button @click=${() => (this.redisSnapshot = null)}>Close</button>
                                    </div>
                                    <pre>${JSON.stringify(this.redisSnapshot, null, 2)}</pre>
                                </div>
                            `
                          : ''}
                  `}
        `;
    }
}

customElements.define('scheduler-tasks-page', SchedulerTasksPage);
