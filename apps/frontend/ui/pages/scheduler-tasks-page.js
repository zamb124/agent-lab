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
            }

            th {
                background: var(--glass-tint-medium);
                color: var(--text-secondary);
                border-top: none;
            }

            .actions {
                display: flex;
                gap: var(--space-2);
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
                text-transform: uppercase;
                font-size: var(--text-xs);
            }
        `,
    ];

    static properties = {
        tasks: { state: true },
        loading: { state: true },
        statusFilter: { state: true },
        serviceFilter: { state: true },
    };

    constructor() {
        super();
        this.tasks = [];
        this.loading = false;
        this.statusFilter = '';
        this.serviceFilter = '';
    }

    async connectedCallback() {
        super.connectedCallback();
        await this._load();
    }

    async _load() {
        this.loading = true;
        try {
            this.tasks = await this.services.get('schedulerTasks').list({
                status: this.statusFilter || undefined,
                target_service: this.serviceFilter || undefined,
            });
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
                                  ${this.tasks.map(
                                      (task) => html`
                                          <tr>
                                              <td>${task.id}</td>
                                              <td>${task.target_service}</td>
                                              <td>${task.task_name}</td>
                                              <td class="status">${task.status}</td>
                                              <td>
                                                  ${task.schedule_type}
                                                  ${task.cron ? html`<div>${task.cron}</div>` : ''}
                                                  ${task.interval_seconds ? html`<div>${task.interval_seconds}s</div>` : ''}
                                                  ${task.run_at ? html`<div>${task.run_at}</div>` : ''}
                                              </td>
                                              <td>
                                                  <div class="actions">
                                                      <button @click=${() => this._executeAction('run-now', task.id)}>Run now</button>
                                                      <button @click=${() => this._executeAction('pause', task.id)}>Pause</button>
                                                      <button @click=${() => this._executeAction('resume', task.id)}>Resume</button>
                                                      <button @click=${() => this._executeAction('cancel', task.id)}>Cancel</button>
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
