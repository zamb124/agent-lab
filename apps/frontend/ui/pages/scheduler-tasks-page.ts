/**
 * Страница задач scheduler — расписания платформенного scheduler.
 *
 * Фильтры: status, target_service, task_name. Колонки: schedule_task_id, service, task,
 * schedule, status, next_run, actions. Действия: run-now, pause/resume,
 * cancel, redis snapshot. Redis snapshot — inline expandable section
 * под строкой задачи (без модалки).
 *
 * Statuses: pending, paused, executed, cancelled, failed
 * (см. ScheduledTaskStatus в core/scheduler/models.py).
 */
import { html, css } from 'lit';

function displayText(value: unknown): string {
    if (value === undefined || value === null || value === false || value === 0 || value === '') return '';
    if (typeof value === 'number' && !Number.isFinite(value)) return '';
    return String(value);
}

function requireScheduleTaskId(task: Record<string, unknown>): string {
    const scheduleTaskId = task.schedule_task_id;
    if (typeof scheduleTaskId !== 'string' || scheduleTaskId.length === 0) {
        throw new Error('scheduler tasks: schedule_task_id required');
    }
    return scheduleTaskId;
}

function scheduleKind(task: Record<string, unknown>): string {
    if (typeof task.schedule_type === 'string' && task.schedule_type.length > 0) {
        return task.schedule_type;
    }
    if (typeof task.cron === 'string' && task.cron.length > 0) {
        return 'cron';
    }
    if (typeof task.interval_seconds === 'number' || (typeof task.interval_seconds === 'string' && task.interval_seconds.length > 0)) {
        return 'interval';
    }
    return 'one_time';
}

function shownCount(value: unknown): number | string {
    if (typeof value === 'number' && Number.isFinite(value)) return value;
    if (typeof value === 'string' && value.length > 0) return value;
    return 0;
}
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { frontendIslandPageBodyStyles } from '../styles/frontend-island-page-body.styles.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-spinner.js';
import '@platform/lib/components/platform-empty-state.js';
import { FrontendCreateSchedulerTaskModal } from '../modals/create-scheduler-task-modal.js';
import '@platform/lib/components/fields/platform-field.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';
import type {CSSResultGroup, PropertyDeclarations, TemplateResult} from 'lit';
import type { OpController, ResourceController} from '@platform/lib/base/use-resource.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';

const STATUSES = Object.freeze(['pending', 'paused', 'executed', 'cancelled', 'failed']);

export class FrontendSchedulerTasksPage extends PlatformPage {
    static override styles: CSSResultGroup = [
        PlatformPage.styles,
        css`
            :host { display: block; }

            .filters {
                display: flex; gap: var(--space-2); flex-wrap: wrap;
                margin-bottom: var(--space-4);
                padding: var(--space-3);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
            }
            .filters label { display: flex; flex-direction: column; gap: 4px; font-size: var(--text-xs); color: var(--text-tertiary); }
            .filters select, .filters input { min-width: 140px; }

            .btn {
                padding: var(--space-2) var(--space-4);
                background: var(--accent); color: white; border: none;
                border-radius: var(--radius-md); cursor: pointer;
                font-size: var(--text-sm); font-weight: var(--font-medium);
            }
            .btn:hover { filter: brightness(1.1); }
            .btn-ghost {
                background: transparent; color: var(--text-secondary);
                border: 1px solid var(--glass-border-subtle);
            }
            .btn-ghost:hover { color: var(--text-primary); border-color: var(--accent); }
            .btn-danger { color: var(--error); }

            table { width: 100%; border-collapse: collapse; }
            th, td {
                padding: var(--space-3);
                border-bottom: 1px solid var(--glass-border-subtle);
                text-align: left;
                vertical-align: middle;
            }
            th {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                text-transform: uppercase; letter-spacing: 0.05em;
            }
            td { color: var(--text-primary); font-size: var(--text-sm); }
            td.actions { text-align: right; white-space: nowrap; }
            td.actions button + button { margin-left: var(--space-2); }
            td.schedule-task-id { font-family: var(--font-mono); font-size: var(--text-xs); color: var(--text-tertiary); }
            td code { font-family: var(--font-mono); font-size: var(--text-xs); background: var(--glass-solid-subtle); padding: 2px 6px; border-radius: var(--radius-sm); }

            .status-tag {
                padding: 2px 8px;
                border-radius: var(--radius-full);
                font-size: var(--text-xs);
                background: var(--glass-solid-medium); color: var(--text-secondary);
            }
            .status-tag.pending { background: var(--accent); color: white; }
            .status-tag.paused { background: var(--warning); color: white; }
            .status-tag.executed { background: var(--success); color: white; }
            .status-tag.cancelled { background: var(--text-tertiary); color: white; }
            .status-tag.failed { background: var(--error); color: white; }

            .redis-row td {
                background: var(--glass-solid-subtle);
                padding: var(--space-3) var(--space-4);
            }
            .redis-row pre {
                font-family: var(--font-mono);
                font-size: var(--text-xs);
                white-space: pre-wrap; word-break: break-all;
                margin: 0; color: var(--text-primary);
                max-height: 240px; overflow: auto;
            }
            platform-empty-state { margin-top: var(--space-4); }
        `,
        frontendIslandPageBodyStyles,
    ];

    static override properties: PropertyDeclarations = {
        _filterStatus: { state: true },
        _filterService: { state: true },
        _filterTask: { state: true },
        _expandedScheduleTaskId: { state: true },
    }
    declare _filterStatus: string;
    declare _filterService: string;
    declare _filterTask: string;
    declare _expandedScheduleTaskId: string | null;
;

    constructor() {
        super();
        this._tasks = this.useResource('scheduler/schedule_tasks');
        this._pause = this.useOp('scheduler/schedule_pause');
        this._resume = this.useOp('scheduler/schedule_resume');
        this._cancelOp = this.useOp('scheduler/schedule_cancel');
        this._runNowOp = this.useOp('scheduler/schedule_run_now');
        this._redis = this.useOp('scheduler/schedule_redis');
        this._loaded = false;
        this._filterStatus = '';
        this._filterService = '';
        this._filterTask = '';
        this._expandedScheduleTaskId = null;
    }
    private _tasks: ResourceController;
    private _pause: OpController;
    private _resume: OpController;
    private _cancelOp: OpController;
    private _runNowOp: OpController;
    private _redis: OpController;
    private _loaded: boolean;


    override updated() {
        if (!this._loaded) {
            this._loaded = true;
            this._reload();
        }
    }

    _reload() {
        const filter: Record<string, unknown> = {};
        if (this._filterStatus) filter.status = this._filterStatus;
        if (this._filterService) filter.target_service = this._filterService;
        if (this._filterTask) filter.task_name = this._filterTask;
        this._tasks.load(filter);
    }

    _create() {
        this.openModal(FrontendCreateSchedulerTaskModal);
    }

    _runNow(task: Record<string, unknown>) {
        this._runNowOp.run({ schedule_task_id: requireScheduleTaskId(task) });
    }

    _pauseTask(task: Record<string, unknown>) {
        this._pause.run({ schedule_task_id: requireScheduleTaskId(task) });
    }

    _resumeTask(task: Record<string, unknown>) {
        this._resume.run({ schedule_task_id: requireScheduleTaskId(task) });
    }

    async _cancelTask(task: Record<string, unknown>) {
        const scheduleTaskId = requireScheduleTaskId(task);
        const taskName = typeof task.task_name === 'string' && task.task_name.length > 0 ? task.task_name : scheduleTaskId;
        const message = this.t('scheduler_page.confirm_cancel', { name: taskName });
        if (!(await platformConfirm(message))) return;
        this._cancelOp.run({ schedule_task_id: scheduleTaskId });
    }

    _toggleRedis(task: Record<string, unknown>) {
        const scheduleTaskId = requireScheduleTaskId(task);
        if (this._expandedScheduleTaskId === scheduleTaskId) {
            this._expandedScheduleTaskId = null;
            return;
        }
        this._expandedScheduleTaskId = scheduleTaskId;
        this._redis.run({ schedule_task_id: scheduleTaskId });
    }

    _statusFilterEnumConfig() {
        return {
            values: [
                { value: '', label: this.t('scheduler_page.filter_all_status') },
                ...STATUSES.map((s) => ({
                    value: s,
                    label: s,
                })),
            ],
        };
    }

    _formatSchedule(task: Record<string, unknown>) {
        const type = scheduleKind(task);
        if (type === 'cron') return this.t('scheduler_page.schedule_cron', { cron: displayText(task.cron) });
        if (type === 'interval') return this.t('scheduler_page.schedule_interval', { sec: shownCount(task.interval_seconds) });
        const at = typeof task.run_at === 'string' || typeof task.run_at === 'number'
            ? new Date(task.run_at).toLocaleString()
            : '';
        return this.t('scheduler_page.schedule_once', { at });
    }

    _renderFilters() {
        return html`
            <div class="filters">
                <platform-field
                    type="enum"
                    mode="edit"
                    label=${this.t('scheduler_page.filter_status')}
                    .value=${this._filterStatus}
                    .config=${this._statusFilterEnumConfig()}
                    @change=${(e: CustomEvent) => {
                        if (!e.detail || typeof e.detail.value !== 'string') {
                            throw new Error('scheduler tasks: status filter expects detail.value string');
                        }
                        this._filterStatus = e.detail.value;
                        this._reload();
                    }}
                ></platform-field>
                <platform-field
                    type="string"
                    mode="edit"
                    label=${this.t('scheduler_page.filter_service')}
                    placeholder=${this.t('scheduler_page.prompt_target')}
                    .value=${this._filterService}
                    @change=${(e: CustomEvent) => {
                        if (!e.detail || typeof e.detail.value !== 'string') {
                            throw new Error('scheduler tasks: service filter expects detail.value string');
                        }
                        this._filterService = e.detail.value;
                        this._reload();
                    }}
                ></platform-field>
                <platform-field
                    type="string"
                    mode="edit"
                    label=${this.t('scheduler_page.filter_task')}
                    placeholder=${this.t('scheduler_page.prompt_task')}
                    .value=${this._filterTask}
                    @change=${(e: CustomEvent) => {
                        if (!e.detail || typeof e.detail.value !== 'string') {
                            throw new Error('scheduler tasks: task filter expects detail.value string');
                        }
                        this._filterTask = e.detail.value;
                        this._reload();
                    }}
                ></platform-field>
            </div>
        `;
    }

    _renderEmpty() {
        return html`
            <platform-empty-state
                icon="schedule"
                title=${this.t('scheduler_page.empty_title')}
                hint=${this.t('scheduler_page.empty_description')}
            ></platform-empty-state>
        `;
    }

    _renderRedisRow(t: Record<string, unknown>) {
        const snapshotByScheduleTaskId = this._redis.state.snapshotByScheduleTaskId;
        const loadingByScheduleTaskId = this._redis.state.loadingByScheduleTaskId;
        if (!isPlainRecord(snapshotByScheduleTaskId)) {
            throw new Error('scheduler redis: snapshotByScheduleTaskId must be an object');
        }
        if (!isPlainRecord(loadingByScheduleTaskId)) {
            throw new Error('scheduler redis: loadingByScheduleTaskId must be an object');
        }
        const scheduleTaskId = t.schedule_task_id;
        if (typeof scheduleTaskId !== 'string' || scheduleTaskId === '') {
            throw new Error('scheduler tasks: schedule_task_id required');
        }
        const snapshot = snapshotByScheduleTaskId[scheduleTaskId];
        const loadingFlag = loadingByScheduleTaskId[scheduleTaskId];
        if (loadingFlag !== undefined && typeof loadingFlag !== 'boolean') {
            throw new Error('scheduler redis: loadingByScheduleTaskId flag must be a boolean');
        }
        const loading = loadingFlag === true;
        const data = !snapshot && loading
            ? html`<div><platform-spinner></platform-spinner></div>`
            : snapshot
                ? html`<pre>${JSON.stringify(snapshot, null, 2)}</pre>`
                : html`<div>${this.t('scheduler_page.redis_empty')}</div>`;
        return html`
            <tr class="redis-row">
                <td colspan="7">
                    <strong>${this.t('scheduler_page.redis_title')}</strong>
                    ${data}
                </td>
            </tr>
        `;
    }

    _renderRow(task: Record<string, unknown>) {
        const scheduleTaskId = requireScheduleTaskId(task);
        const status = typeof task.status === 'string' && task.status.length > 0 ? task.status : 'pending';
        const expanded = this._expandedScheduleTaskId === scheduleTaskId;
        const nextRun = task.next_run_at;
        const nextLabel = typeof nextRun === 'string' || typeof nextRun === 'number'
            ? new Date(nextRun).toLocaleString()
            : '—';
        return html`
            <tr>
                <td class="schedule-task-id">${scheduleTaskId}</td>
                <td>${displayText(task.target_service)}</td>
                <td>${displayText(task.task_name)}</td>
                <td><code>${this._formatSchedule(task)}</code></td>
                <td><span class="status-tag ${status}">${status}</span></td>
                <td>${nextLabel}</td>
                <td class="actions">
                    <button class="btn btn-ghost" @click=${() => this._runNow(task)}>${this.t('scheduler_page.run_now')}</button>
                    <button class="btn btn-ghost"
                        @click=${() => status === 'paused' ? this._resumeTask(task) : this._pauseTask(task)}
                    >
                        ${status === 'paused' ? this.t('scheduler_page.resume') : this.t('scheduler_page.pause')}
                    </button>
                    <button class="btn btn-ghost btn-danger" @click=${() => this._cancelTask(task)}>${this.t('scheduler_page.cancel')}</button>
                    <button class="btn btn-ghost" @click=${() => this._toggleRedis(task)}>${this.t('scheduler_page.redis_open')}</button>
                </td>
            </tr>
            ${expanded ? this._renderRedisRow(task) : ''}
        `;
    }

    override render(): TemplateResult {
        const list = this._tasks.items;
        const loading = this._tasks.loading;
        return html`
            <page-header
                title=${this.t('scheduler_page.title')}
                subtitle=${this.t('scheduler_page.subtitle')}
            >
                <button slot="actions" class="btn" @click=${this._create}>
                    ${this.t('scheduler_page.create')}
                </button>
            </page-header>
            <div class="page-body">
            ${this._renderFilters()}
            ${loading && list.length === 0
                ? html`<platform-empty-state loading></platform-empty-state>`
                : list.length === 0
                    ? this._renderEmpty()
                    : html`
                        <table>
                            <thead><tr>
                                <th>${this.t('scheduler_page.th_id')}</th>
                                <th>${this.t('scheduler_page.th_service')}</th>
                                <th>${this.t('scheduler_page.th_task')}</th>
                                <th>${this.t('scheduler_page.th_schedule')}</th>
                                <th>${this.t('scheduler_page.th_status')}</th>
                                <th>${this.t('scheduler_page.next_run')}</th>
                                <th>${this.t('scheduler_page.th_actions')}</th>
                            </tr></thead>
                            <tbody>
                                ${list.map((t) => this._renderRow(t))}
                            </tbody>
                        </table>
                    `
            }
            </div>
        `;
    }
}

customElements.define('frontend-scheduler-tasks-page', FrontendSchedulerTasksPage);
