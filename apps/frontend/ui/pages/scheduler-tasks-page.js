/**
 * Scheduler tasks page — расписания платформенного scheduler.
 *
 * Фильтры: status, target_service, task_name. Колонки: id, service, task,
 * schedule, status, next_run, actions. Действия: run-now, pause/resume,
 * cancel, redis snapshot. Redis snapshot — inline expandable section
 * под строкой задачи (без модалки).
 *
 * Statuses: pending, paused, executed, cancelled, failed
 * (см. ScheduledTaskStatus в core/scheduler/models.py).
 */
import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/glass-spinner.js';
import { FrontendCreateSchedulerTaskModal } from '../modals/create-scheduler-task-modal.js';

const STATUSES = Object.freeze(['pending', 'paused', 'executed', 'cancelled', 'failed']);

export class FrontendSchedulerTasksPage extends PlatformPage {
    static styles = [
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
            td.id { font-family: var(--font-mono); font-size: var(--text-xs); color: var(--text-tertiary); }
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

            .empty {
                padding: var(--space-8) var(--space-6);
                text-align: center; color: var(--text-tertiary);
                background: var(--glass-solid-subtle);
                border: 1px dashed var(--glass-border-subtle);
                border-radius: var(--radius-lg);
            }
            .empty .empty-title { color: var(--text-primary); font-weight: var(--font-semibold); margin-bottom: var(--space-2); }
        `,
    ];

    static properties = {
        _filterStatus: { state: true },
        _filterService: { state: true },
        _filterTask: { state: true },
        _expandedRedisId: { state: true },
    };

    constructor() {
        super();
        this._tasks = this.useResource('frontend/scheduler_tasks');
        this._pause = this.useOp('frontend/scheduler_pause');
        this._resume = this.useOp('frontend/scheduler_resume');
        this._cancelOp = this.useOp('frontend/scheduler_cancel');
        this._runNowOp = this.useOp('frontend/scheduler_run_now');
        this._redis = this.useOp('frontend/scheduler_redis');
        this._loaded = false;
        this._filterStatus = '';
        this._filterService = '';
        this._filterTask = '';
        this._expandedRedisId = null;
    }

    updated() {
        if (!this._loaded) {
            this._loaded = true;
            this._reload();
        }
    }

    _reload() {
        const filter = {};
        if (this._filterStatus) filter.status = this._filterStatus;
        if (this._filterService) filter.target_service = this._filterService;
        if (this._filterTask) filter.task_name = this._filterTask;
        this._tasks.load(filter);
    }

    _create() {
        this.openModal(FrontendCreateSchedulerTaskModal);
    }

    _runNow(t) {
        this._runNowOp.run({ task_id: t.id });
    }

    _pauseTask(t) {
        this._pause.run({ task_id: t.id });
    }

    _resumeTask(t) {
        this._resume.run({ task_id: t.id });
    }

    _cancelTask(t) {
        const message = this.t('scheduler_page.confirm_cancel', { name: t.task_name || t.id });
        if (!confirm(message)) return;
        this._cancelOp.run({ task_id: t.id });
    }

    _toggleRedis(t) {
        if (this._expandedRedisId === t.id) {
            this._expandedRedisId = null;
            return;
        }
        this._expandedRedisId = t.id;
        this._redis.run({ task_id: t.id });
    }

    _formatSchedule(t) {
        const type = t.schedule_type || (t.cron ? 'cron' : (t.interval_seconds ? 'interval' : 'one_time'));
        if (type === 'cron') return this.t('scheduler_page.schedule_cron', { cron: t.cron || '' });
        if (type === 'interval') return this.t('scheduler_page.schedule_interval', { sec: t.interval_seconds || 0 });
        const at = t.run_at ? new Date(t.run_at).toLocaleString() : '';
        return this.t('scheduler_page.schedule_once', { at });
    }

    _renderFilters() {
        return html`
            <div class="filters">
                <label>
                    <span>${this.t('scheduler_page.filter_status')}</span>
                    <select
                        class="form-select"
                        .value=${this._filterStatus}
                        @change=${(e) => { this._filterStatus = e.target.value; this._reload(); }}
                    >
                        <option value="">${this.t('scheduler_page.filter_all_status')}</option>
                        ${STATUSES.map((s) => html`<option value=${s} ?selected=${this._filterStatus === s}>${s}</option>`)}
                    </select>
                </label>
                <label>
                    <span>${this.t('scheduler_page.filter_service')}</span>
                    <input
                        class="form-input"
                        .value=${this._filterService}
                        @change=${(e) => { this._filterService = e.target.value; this._reload(); }}
                        placeholder=${this.t('scheduler_page.prompt_target')}
                    />
                </label>
                <label>
                    <span>${this.t('scheduler_page.filter_task')}</span>
                    <input
                        class="form-input"
                        .value=${this._filterTask}
                        @change=${(e) => { this._filterTask = e.target.value; this._reload(); }}
                        placeholder=${this.t('scheduler_page.prompt_task')}
                    />
                </label>
            </div>
        `;
    }

    _renderEmpty() {
        return html`
            <div class="empty">
                <div class="empty-title">${this.t('scheduler_page.empty_title')}</div>
                <div>${this.t('scheduler_page.empty_description')}</div>
            </div>
        `;
    }

    _renderRedisRow(t) {
        const snapshotById = this._redis.state.snapshotById;
        const loadingById = this._redis.state.loadingById;
        const snapshot = snapshotById[t.id];
        const loading = Boolean(loadingById[t.id]);
        const data = !snapshot && loading
            ? html`<div>${this.t('scheduler_page.redis_loading')}</div>`
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

    _renderRow(t) {
        const status = t.status || 'pending';
        const expanded = this._expandedRedisId === t.id;
        return html`
            <tr>
                <td class="id">${t.id}</td>
                <td>${t.target_service || ''}</td>
                <td>${t.task_name || ''}</td>
                <td><code>${this._formatSchedule(t)}</code></td>
                <td><span class="status-tag ${status}">${status}</span></td>
                <td>${t.next_run_at ? new Date(t.next_run_at).toLocaleString() : '—'}</td>
                <td class="actions">
                    <button class="btn btn-ghost" @click=${() => this._runNow(t)}>${this.t('scheduler_page.run_now')}</button>
                    <button class="btn btn-ghost"
                        @click=${() => status === 'paused' ? this._resumeTask(t) : this._pauseTask(t)}
                    >
                        ${status === 'paused' ? this.t('scheduler_page.resume') : this.t('scheduler_page.pause')}
                    </button>
                    <button class="btn btn-ghost btn-danger" @click=${() => this._cancelTask(t)}>${this.t('scheduler_page.cancel')}</button>
                    <button class="btn btn-ghost" @click=${() => this._toggleRedis(t)}>${this.t('scheduler_page.redis_open')}</button>
                </td>
            </tr>
            ${expanded ? this._renderRedisRow(t) : ''}
        `;
    }

    render() {
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

            ${this._renderFilters()}

            ${loading && list.length === 0
                ? html`<div class="empty"><glass-spinner></glass-spinner></div>`
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
        `;
    }
}

customElements.define('frontend-scheduler-tasks-page', FrontendSchedulerTasksPage);
