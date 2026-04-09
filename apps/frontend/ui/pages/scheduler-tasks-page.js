import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/glass-modal.js';

export class SchedulerTasksPage extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
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
                overflow-x: auto;
                overflow-y: visible;
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
                background: rgba(153, 166, 249, 0.12);
                color: #7c8af4;
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
                min-width: 220px;
                border: 1px solid var(--border-default);
                background: var(--glass-solid-medium);
                border-radius: var(--radius-md);
                box-shadow: 0 12px 28px rgba(0, 0, 0, 0.24);
                overflow: hidden;
                backdrop-filter: blur(10px);
            }

            .actions-dropdown-inline {
                position: absolute;
                right: 0;
                top: calc(100% + 6px);
                z-index: 40;
            }

            .menu-item {
                width: 100%;
                border: 1px solid var(--border-default);
                border-radius: 0;
                border-left: none;
                border-right: none;
                border-top: none;
                background: transparent;
                display: flex;
                align-items: center;
                gap: 8px;
                padding: 10px 12px;
                text-align: left;
                font-size: var(--text-xs);
            }

            .menu-item:last-child {
                border-bottom: none;
            }

            .menu-item:hover {
                background: var(--glass-tint-medium);
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

            .redis-json {
                font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New',
                    monospace;
                font-size: 12px;
                color: var(--text-secondary);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                padding: var(--space-3);
                max-height: 60vh;
                overflow: auto;
                margin: 0;
            }
        `,
    ];

    static properties = {
        tasks: { state: true },
        loading: { state: true },
        statusFilter: { state: true },
        serviceFilter: { state: true },
        openMenuTaskId: { state: true },
        redisSnapshot: { state: true },
        redisSnapshotLoading: { state: true },
        redisSnapshotModalOpen: { state: true },
    };

    constructor() {
        super();
        this.tasks = [];
        this.loading = false;
        this.statusFilter = '';
        this.serviceFilter = '';
        this.openMenuTaskId = null;
        this.redisSnapshot = null;
        this.redisSnapshotLoading = false;
        this.redisSnapshotModalOpen = false;
    }

    async connectedCallback() {
        super.connectedCallback();
        this._i18nUnsub = this.i18n.subscribe(() => this.requestUpdate());
        await this._load();
    }

    disconnectedCallback() {
        if (this._i18nUnsub) {
            this._i18nUnsub();
            this._i18nUnsub = null;
        }
        super.disconnectedCallback();
    }

    _closeActionsMenu() {
        this.openMenuTaskId = null;
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
        const loc = this.i18n.getCurrentLocale() === 'en' ? 'en-US' : 'ru-RU';
        return date.toLocaleString(loc, { hour12: false });
    }

    _formatSchedule(task) {
        const td = (k, p) => this.i18n.t(k, p ?? {});
        if (task.schedule_type === 'cron') {
            return td('scheduler_page.schedule_cron', { cron: task.cron ?? '' });
        }
        if (task.schedule_type === 'interval') {
            return td('scheduler_page.schedule_interval', { sec: String(task.interval_seconds ?? '') });
        }
        if (task.schedule_type === 'one_time') {
            return td('scheduler_page.schedule_once', { at: this._formatDate(task.run_at) });
        }
        throw new Error(`Unknown schedule_type: ${task.schedule_type}`);
    }

    _toggleActionsMenu(taskId, event) {
        event.stopPropagation();
        if (this.openMenuTaskId === taskId) {
            this._closeActionsMenu();
            return;
        }
        this.openMenuTaskId = taskId;
    }

    async _load() {
        this.loading = true;
        try {
            const response = await this.services.get('schedulerTasks').list({
                status: this.statusFilter || undefined,
                target_service: this.serviceFilter || undefined,
                limit: 500,
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
        this._closeActionsMenu();
        await this._load();
    }

    async _openRedisSnapshot(taskId) {
        this.redisSnapshotModalOpen = true;
        this.redisSnapshotLoading = true;
        try {
            this.redisSnapshot = await this.services.get('schedulerTasks').getRedisSnapshot(taskId);
            this._closeActionsMenu();
        } finally {
            this.redisSnapshotLoading = false;
        }
    }

    _closeRedisSnapshotModal() {
        this.redisSnapshotModalOpen = false;
    }

    async _createSchedule() {
        const td = (k) => this.i18n.t(k, {});
        const targetService = prompt(td('scheduler_page.prompt_target'), 'flows');
        if (!targetService) {
            return;
        }
        const taskName = prompt(td('scheduler_page.prompt_task'), 'sync_llm_models_task');
        if (!taskName) {
            return;
        }
        const scheduleType = prompt(td('scheduler_page.prompt_schedule_type'), 'interval');
        if (!scheduleType) {
            return;
        }
        const payloadRaw = prompt(td('scheduler_page.prompt_payload'), '{}');
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
            request.cron = prompt(td('scheduler_page.prompt_cron'), '*/5 * * * *');
        } else if (scheduleType === 'interval') {
            request.interval_seconds = Number(prompt(td('scheduler_page.prompt_interval'), '60'));
        } else if (scheduleType === 'one_time') {
            request.run_at = prompt(td('scheduler_page.prompt_run_at'), new Date(Date.now() + 60000).toISOString());
        } else {
            throw new Error(`Unknown schedule_type: ${scheduleType}`);
        }
        await this.services.get('schedulerTasks').create(request);
        await this._load();
    }

    render() {
        const td = (k, p) => this.i18n.t(k, p ?? {});
        return html`
            <div @click=${() => this._closeActionsMenu()}>
            <page-header title=${td('scheduler_page.title')}></page-header>

            <div class="toolbar">
                <button @click=${() => this._createSchedule()}>${td('scheduler_page.create')}</button>
                <select
                    .value=${this.statusFilter}
                    @change=${(event) => {
                        this.statusFilter = event.target.value;
                        this._load();
                    }}
                >
                    <option value="">${td('scheduler_page.filter_all_status')}</option>
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
                ? html`<div>${td('scheduler_page.loading')}</div>`
                : html`
                      <div class="table-wrap">
                          <table>
                              <thead>
                                  <tr>
                                      <th>${td('scheduler_page.th_id')}</th>
                                      <th>${td('scheduler_page.th_service')}</th>
                                      <th>${td('scheduler_page.th_task')}</th>
                                      <th>${td('scheduler_page.th_status')}</th>
                                      <th>${td('scheduler_page.th_schedule')}</th>
                                      <th>${td('scheduler_page.th_actions')}</th>
                                  </tr>
                              </thead>
                              <tbody>
                                  ${this.tasks.length === 0
                                      ? html`
                                            <tr>
                                                <td class="empty" colspan="6">${td('scheduler_page.empty')}</td>
                                            </tr>
                                        `
                                      : this.tasks.map(
                                            (task) => html`
                                                <tr class="task-row">
                                                    <td><code>${task.id}</code></td>
                                                    <td>${task.target_service}</td>
                                                    <td>${task.task_name}</td>
                                                    <td>
                                                        <span class="status ${task.status}">${task.status}</span>
                                                    </td>
                                                    <td>
                                                        ${this._formatSchedule(task)}
                                                        <div class="schedule-secondary">
                                                            ${td('scheduler_page.next_run')} ${this._formatDate(task.next_run_at)}
                                                        </div>
                                                    </td>
                                                    <td class="actions-cell">
                                                        <div class="actions-menu">
                                                            <button
                                                                class="actions-trigger"
                                                                title=${td('scheduler_page.actions_title')}
                                                                @click=${(event) => this._toggleActionsMenu(task.id, event)}
                                                            >
                                                                ...
                                                            </button>
                                                            ${this.openMenuTaskId === task.id
                                                                ? html`
                                                                      <div class="actions-dropdown actions-dropdown-inline" @click=${(event) => event.stopPropagation()}>
                                                                          <button class="menu-item" @click=${() => this._executeAction('run-now', task.id)}>
                                                                              <platform-icon name="play" size="16" aria-hidden="true"></platform-icon>
                                                                              Run now
                                                                          </button>
                                                                          <button class="menu-item" @click=${() => this._openRedisSnapshot(task.id)}>
                                                                              <platform-icon name="database" size="16" aria-hidden="true"></platform-icon>
                                                                              Redis snapshot
                                                                          </button>
                                                                          ${task.status === 'paused'
                                                                              ? html`
                                                                                    <button class="menu-item" @click=${() => this._executeAction('resume', task.id)}>
                                                                                        <platform-icon name="play" size="16" aria-hidden="true"></platform-icon>
                                                                                        Resume
                                                                                    </button>
                                                                                `
                                                                              : html`
                                                                                    <button class="menu-item" @click=${() => this._executeAction('pause', task.id)}>
                                                                                        <platform-icon name="stop" size="16" aria-hidden="true"></platform-icon>
                                                                                        Pause
                                                                                    </button>
                                                                                `}
                                                                          <button class="menu-item" @click=${() => this._executeAction('cancel', task.id)}>
                                                                              <platform-icon name="close" size="16" aria-hidden="true"></platform-icon>
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
            <glass-modal
                size="lg"
                .heading=${td('scheduler_page.redis_title')}
                ?open=${this.redisSnapshotModalOpen}
                @modal-closed=${() => this._closeRedisSnapshotModal()}
            >
                <div slot="content">
                    ${this.redisSnapshotLoading
                        ? html`<div>${td('scheduler_page.redis_loading')}</div>`
                        : this.redisSnapshot
                          ? html`<pre class="redis-json">${JSON.stringify(this.redisSnapshot, null, 2)}</pre>`
                          : html`<div>${td('scheduler_page.redis_empty')}</div>`}
                </div>
                <div slot="actions">
                    <button @click=${() => this._closeRedisSnapshotModal()}>${td('scheduler_page.close')}</button>
                </div>
            </glass-modal>
            </div>
        `;
    }
}

customElements.define('scheduler-tasks-page', SchedulerTasksPage);
