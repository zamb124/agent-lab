/**
 * TasksPage — kanban-доска пользовательских задач (entity_type=task) для
 * активного namespace. Загружает задачи через `crm/entities_lookup`,
 * создаёт через `crm/entities` (create), переносит между колонками через
 * `crm/entity_update`. Drag&drop работает на десктопе, на мобильном —
 * вкладки колонок. Открытие задачи — модалка `crm.entity` (mode='edit').
 */

import { html, css, nothing } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { CoreEvents } from '@platform/lib/events/index.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-breadcrumbs.js';
import '@platform/lib/components/layout/page-header.js';

const TASK_DND_MIME = 'application/x-crm-task-id';
const VALID_STATUSES = ['todo', 'in_progress', 'done'];

function _normalizeStatus(value) {
    if (typeof value === 'string' && VALID_STATUSES.includes(value)) {
        return value;
    }
    return 'todo';
}

export class CRMTasksPage extends PlatformPage {
    static i18nNamespace = 'crm';

    static properties = {
        _tasks: { state: true },
        _loading: { state: true },
        _filter: { state: true },
        _isMobile: { state: true },
        _activeStatus: { state: true },
        _dragOverStatus: { state: true },
        _draggingTaskId: { state: true },
        _dndInsert: { state: true },
        _dndSourceStatus: { state: true },
        _boardBusy: { state: true },
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

            .page-toolbar {
                flex-shrink: 0;
                padding-bottom: var(--space-2);
            }

            .top-row {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                margin-bottom: var(--space-3);
            }

            .title {
                font-size: 42px;
                line-height: 1;
                font-weight: 700;
                color: var(--text-primary);
                margin: 0;
                white-space: nowrap;
            }

            .search-box {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: 0 var(--space-3);
                border-radius: var(--radius-full);
                border: 1px solid var(--crm-stroke);
                background: var(--crm-surface-muted);
                min-height: 40px;
                flex: 1;
                min-width: 0;
            }

            .search-input {
                width: 100%;
                border: none;
                background: transparent;
                color: var(--text-primary);
                font-size: var(--text-sm);
                outline: none;
            }

            .toolbar-actions {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                flex-shrink: 0;
            }

            .icon-btn-toolbar {
                width: 40px;
                height: 40px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-full);
                border: 1px solid var(--crm-stroke);
                background: var(--crm-surface-muted);
                color: var(--text-secondary);
                cursor: pointer;
                transition: all var(--duration-fast);
                flex-shrink: 0;
                padding: 0;
            }

            .icon-btn-toolbar:hover {
                background: var(--crm-surface);
                color: var(--text-primary);
            }

            .cta-btn {
                min-height: 40px;
                border: none;
                border-radius: var(--radius-full);
                background: var(--crm-daily-notes-cta-bg);
                color: var(--text-inverse);
                font-size: var(--text-base);
                font-weight: 500;
                padding: 0 var(--space-5);
                cursor: pointer;
                transition: background var(--duration-fast);
                white-space: nowrap;
                flex-shrink: 0;
            }

            .cta-btn:hover {
                background: var(--crm-daily-notes-cta-hover);
            }

            .status-tabs {
                display: flex;
                gap: var(--space-2);
                margin-bottom: var(--space-3);
            }

            .status-tab {
                display: inline-flex;
                align-items: center;
                gap: 6px;
                padding: 6px 14px;
                border-radius: var(--radius-full);
                border: 1px solid var(--crm-stroke);
                background: var(--crm-surface-muted);
                color: var(--text-secondary);
                font-size: 13px;
                font-weight: 500;
                cursor: pointer;
                transition: all var(--duration-fast);
                white-space: nowrap;
            }

            .status-tab:hover {
                background: var(--crm-surface);
                color: var(--text-primary);
            }

            .status-tab.active {
                background: var(--crm-selected-bg);
                border-color: var(--crm-selected-stroke);
                color: var(--crm-selected-text);
            }

            .status-count {
                font-size: 11px;
                color: var(--text-tertiary);
            }

            .board-shell {
                flex: 1;
                min-height: 0;
                position: relative;
                display: flex;
                flex-direction: column;
                overflow: hidden;
            }

            .board {
                flex: 1;
                min-height: 0;
                display: grid;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                gap: var(--space-3);
                overflow: auto;
                transition: filter 0.2s ease, opacity 0.2s ease;
            }

            .board-shell.busy .board {
                filter: saturate(0.92);
                opacity: 0.92;
            }

            .board-overlay {
                position: absolute;
                inset: 0;
                display: flex;
                align-items: center;
                justify-content: center;
                background: var(--glass-solid-subtle);
                backdrop-filter: blur(2px);
                z-index: 10;
                pointer-events: auto;
            }

            .column {
                display: flex;
                flex-direction: column;
                min-height: 0;
                background: var(--crm-surface-muted);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-lg);
                overflow: hidden;
            }

            .column-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: var(--space-3);
                border-bottom: 1px solid var(--crm-stroke);
            }

            .column-title {
                font-weight: 600;
                color: var(--text-primary);
                font-size: var(--text-sm);
            }

            .column-count {
                color: var(--text-tertiary);
                font-size: 11px;
            }

            .column-body {
                flex: 1;
                min-height: 0;
                overflow: auto;
                padding: var(--space-3);
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }

            .column-body.dnd-target {
                outline: 2px dashed var(--crm-selected-stroke);
                outline-offset: -6px;
                background: var(--crm-selected-bg);
            }

            .dnd-gap {
                height: 12px;
                border-radius: 6px;
                background: var(--crm-selected-bg);
                border: 1px dashed var(--crm-selected-stroke);
            }

            .task-card {
                background: var(--crm-surface);
                border: 1px solid var(--crm-stroke);
                border-radius: 14px;
                padding: 14px 16px;
                cursor: pointer;
                display: flex;
                flex-direction: column;
                gap: 10px;
                transition: border-color var(--duration-fast), background var(--duration-fast);
            }

            .task-card:hover {
                border-color: var(--crm-selected-stroke);
            }

            .task-card.dnd-dragging {
                opacity: 0.45;
            }

            .task-card-top {
                display: flex;
                align-items: center;
                gap: 10px;
            }

            .task-card-top-main {
                display: flex;
                align-items: center;
                gap: 10px;
                flex: 1;
                min-width: 0;
            }

            .task-icon {
                width: 36px;
                height: 36px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-full);
                background: var(--crm-surface-tint);
                color: var(--text-secondary);
                flex-shrink: 0;
            }

            .task-name {
                font-size: 15px;
                font-weight: 500;
                color: var(--text-primary);
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                flex: 1;
                min-width: 0;
            }

            .task-drag-handle {
                width: 28px;
                height: 28px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-full);
                color: var(--text-tertiary);
                cursor: grab;
                flex-shrink: 0;
            }

            .task-drag-handle:active { cursor: grabbing; }

            .task-footer {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 8px;
            }

            .task-priority {
                display: inline-flex;
                align-items: center;
                padding: 0 10px;
                min-height: 22px;
                font-size: 11px;
                border-radius: 12px;
                font-weight: 500;
                background: var(--crm-surface-tint);
                color: var(--text-secondary);
            }

            .task-move-btn {
                display: inline-flex;
                align-items: center;
                gap: 4px;
                padding: 4px 12px;
                min-height: 26px;
                border-radius: var(--radius-full);
                border: 1px solid var(--crm-selected-stroke);
                background: var(--crm-selected-bg);
                color: var(--crm-selected-text);
                font-size: 12px;
                font-weight: 500;
                cursor: pointer;
                transition: all var(--duration-fast);
            }

            .task-move-btn:hover {
                background: var(--crm-daily-notes-cta-bg);
                border-color: var(--crm-daily-notes-cta-bg);
                color: var(--text-inverse);
            }

            .empty {
                display: flex;
                align-items: center;
                justify-content: center;
                color: var(--text-tertiary);
                padding: var(--space-6);
                text-align: center;
            }

            @media (max-width: 1023px) {
                .board { grid-template-columns: 1fr; }
            }

            @media (max-width: 767px) {
                .title, .cta-btn { display: none; }
                .top-row { margin-bottom: var(--space-2); }
                .search-box { display: none; }
                .toolbar-actions { display: none; }

                .status-tabs {
                    gap: 6px;
                    margin-bottom: var(--space-2);
                }

                .status-tab {
                    flex: 1;
                    justify-content: center;
                    padding: 6px 8px;
                    font-size: 12px;
                }

                .board {
                    grid-template-columns: 1fr;
                    padding: 0 var(--space-3);
                    gap: 0;
                }

                .board .column {
                    display: none;
                    background: transparent;
                    border: none;
                    border-radius: 0;
                }

                .board .column.mobile-active { display: flex; }
                .board .column.mobile-active .column-header { display: none; }

                .task-card { padding: 14px; border-radius: 12px; }
                .task-icon { width: 32px; height: 32px; }
                .task-name { font-size: 14px; }
            }
        `,
    ];

    constructor() {
        super();
        this._tasks = [];
        this._loading = false;
        this._filter = '';
        this._isMobile = false;
        this._activeStatus = 'todo';
        this._dragOverStatus = null;
        this._draggingTaskId = null;
        this._dndInsert = null;
        this._dndSourceStatus = null;
        this._boardBusy = false;
        this._suppressTaskClick = false;
        this._mql = null;
        this._onMqlChange = null;

        this._lookupOp = this.useOp('crm/entities_lookup');
        this._updateOp = this.useOp('crm/entity_update');
        this._entitiesResource = this.useResource('crm/entities');

        this._namespaceSel = this.select((s) => {
            const user = s.auth.user;
            if (!user || typeof user.company_id !== 'string') return 'all';
            const cid = user.company_id;
            const map = s.ui.namespace.selectionByCompany;
            const sel = map[cid];
            if (sel === 'all' || sel === undefined) return 'all';
            return sel;
        });
    }

    connectedCallback() {
        super.connectedCallback();
        this._mql = window.matchMedia('(max-width: 767px)');
        this._isMobile = this._mql.matches;
        this._onMqlChange = (e) => { this._isMobile = e.matches; };
        this._mql.addEventListener('change', this._onMqlChange);

        this.useEvent(CoreEvents.UI_NAMESPACE_CHANGED, () => this._loadTasks());
        this.useEvent(this._lookupOp.op.events.SUCCEEDED, (event) => this._onTasksLoaded(event.payload.result));
        this.useEvent(this._lookupOp.op.events.FAILED, () => { this._loading = false; });
        this.useEvent(this._updateOp.op.events.SUCCEEDED, () => { this._boardBusy = false; this._loadTasks({ silent: true }); });
        this.useEvent(this._updateOp.op.events.FAILED, (event) => {
            this._boardBusy = false;
            this.toast('crm:tasks_page.move_failed', { type: 'error', vars: { message: event.payload.message } });
            this._loadTasks({ silent: true });
        });
        this.useEvent(this._entitiesResource.resource.events.CREATED, () => this._loadTasks({ silent: true }));

        this._loadTasks();
    }

    disconnectedCallback() {
        if (this._mql && this._onMqlChange) {
            this._mql.removeEventListener('change', this._onMqlChange);
        }
        super.disconnectedCallback();
    }

    _currentNamespace() {
        const sel = this._namespaceSel.value;
        return sel === 'all' ? null : sel;
    }

    _loadTasks(options) {
        const silent = options && options.silent === true;
        if (!silent) {
            this._loading = true;
        }
        const namespace = this._currentNamespace();
        const payload = {
            entity_type: 'task',
            limit: 200,
        };
        if (namespace !== null) {
            payload.namespace = namespace;
        }
        this._lookupOp.run(payload);
    }

    _onTasksLoaded(response) {
        this._loading = false;
        const items = response && Array.isArray(response.items) ? response.items : [];
        this._tasks = items.filter((item) => item && item.entity_type === 'task');
    }

    _onSearchInput(event) {
        this._filter = event.target.value;
    }

    _filteredTasks() {
        if (!this._filter) {
            return this._tasks;
        }
        const query = this._filter.toLowerCase();
        return this._tasks.filter((task) => {
            const name = typeof task.name === 'string' ? task.name : '';
            const description = typeof task.description === 'string' ? task.description : '';
            return name.toLowerCase().includes(query) || description.toLowerCase().includes(query);
        });
    }

    _taskStatus(task) {
        const attrs = task && task.attributes;
        return _normalizeStatus(attrs ? attrs.status : null);
    }

    _nextStatus(status) {
        if (status === 'todo') return 'in_progress';
        if (status === 'in_progress') return 'done';
        return 'todo';
    }

    _nextStatusLabel(status) {
        if (status === 'todo') return this.t('tasks_page.next_to_progress');
        if (status === 'in_progress') return this.t('tasks_page.next_to_done');
        return this.t('tasks_page.next_revert');
    }

    _nextStatusIcon(status) {
        if (status === 'todo') return 'play';
        if (status === 'in_progress') return 'check';
        return 'refresh';
    }

    _statusColumns() {
        return [
            { id: 'todo', label: this.t('tasks_page.column_todo') },
            { id: 'in_progress', label: this.t('tasks_page.column_in_progress') },
            { id: 'done', label: this.t('tasks_page.column_done') },
        ];
    }

    _openTask(taskId) {
        this.openModal('crm.entity', { mode: 'edit', id: taskId });
    }

    _createTask() {
        const namespace = this._currentNamespace();
        const body = {
            entity_type: 'task',
            name: this.t('tasks.new'),
            description: '',
            namespace: namespace === null ? 'default' : namespace,
            priority: 'medium',
            attributes: { status: 'todo' },
        };
        this._entitiesResource.create(body);
    }

    _moveTask(task, targetStatus) {
        const from = this._taskStatus(task);
        if (from === targetStatus) return;
        if (this._boardBusy) return;

        const taskId = task.entity_id;
        this._boardBusy = true;
        this._tasks = this._tasks.map((t) => {
            if (t.entity_id !== taskId) return t;
            const attrs = t.attributes && typeof t.attributes === 'object' ? t.attributes : {};
            return { ...t, attributes: { ...attrs, status: targetStatus } };
        });

        const attributes = task.attributes && typeof task.attributes === 'object' ? task.attributes : {};
        this._updateOp.run({
            id: taskId,
            body: {
                attributes: { ...attributes, status: targetStatus },
            },
        });
    }

    _scheduleClearSuppressTaskClick() {
        this._suppressTaskClick = true;
        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                this._suppressTaskClick = false;
            });
        });
    }

    _onTaskDragStart(e, task) {
        if (this._isMobile) return;
        this._draggingTaskId = task.entity_id;
        this._dndSourceStatus = this._taskStatus(task);
        this._dndInsert = null;
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData(TASK_DND_MIME, task.entity_id);
        e.dataTransfer.setData('text/plain', task.entity_id);
        const card = e.currentTarget.closest('.task-card');
        if (card) card.classList.add('dnd-dragging');
    }

    _onTaskDragEnd(e) {
        const card = e.currentTarget.closest('.task-card');
        if (card) card.classList.remove('dnd-dragging');
        this._draggingTaskId = null;
        this._dragOverStatus = null;
        this._dndInsert = null;
        this._dndSourceStatus = null;
        this._scheduleClearSuppressTaskClick();
    }

    _computeDndInsert(e, statusId) {
        const source = this._dndSourceStatus;
        if (!source || source === statusId) {
            this._dndInsert = null;
            return;
        }
        const body = e.currentTarget;
        const cards = [...body.querySelectorAll('.task-card:not(.dnd-dragging)')];
        const y = e.clientY;
        let beforeTaskId = '__end__';
        for (const el of cards) {
            const id = el.dataset.taskId;
            if (!id) continue;
            const r = el.getBoundingClientRect();
            const mid = r.top + r.height / 2;
            if (y < mid) {
                beforeTaskId = id;
                break;
            }
        }
        const prev = this._dndInsert;
        if (prev && prev.status === statusId && prev.beforeTaskId === beforeTaskId) return;
        this._dndInsert = { status: statusId, beforeTaskId };
    }

    _onColumnBodyDragOver(e, targetStatus) {
        if (this._isMobile || !this._draggingTaskId) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        if (this._dragOverStatus !== targetStatus) {
            this._dragOverStatus = targetStatus;
        }
        this._computeDndInsert(e, targetStatus);
    }

    _onColumnDragLeave(e) {
        if (this._isMobile || !this._draggingTaskId) return;
        const col = e.currentTarget;
        const related = e.relatedTarget;
        if (related && col.contains(related)) return;
        this._dragOverStatus = null;
        this._dndInsert = null;
    }

    _dndGapBeforeTask(statusId, taskId) {
        if (this._isMobile || !this._dndInsert || this._dndSourceStatus === statusId) return false;
        if (this._dndInsert.status !== statusId) return false;
        return this._dndInsert.beforeTaskId === taskId;
    }

    _dndGapAfterLast(statusId, taskCount) {
        if (this._isMobile || !this._dndInsert || this._dndSourceStatus === statusId) return false;
        if (this._dndInsert.status !== statusId) return false;
        if (this._dndInsert.beforeTaskId !== '__end__') return false;
        return taskCount > 0;
    }

    _dndGapEmptyColumn(statusId) {
        if (this._isMobile || !this._dndInsert || this._dndSourceStatus === statusId) return false;
        if (this._dndInsert.status !== statusId) return false;
        return this._dndInsert.beforeTaskId === '__end__';
    }

    _onColumnDrop(e, targetStatus) {
        if (this._isMobile) return;
        e.preventDefault();
        e.stopPropagation();
        this._dragOverStatus = null;
        this._dndInsert = null;
        const rawId = e.dataTransfer.getData(TASK_DND_MIME) || e.dataTransfer.getData('text/plain');
        const taskId = typeof rawId === 'string' ? rawId.trim() : '';
        if (!taskId) {
            this._draggingTaskId = null;
            return;
        }
        const task = this._tasks.find((t) => t.entity_id === taskId);
        this._draggingTaskId = null;
        if (!task) return;
        const from = this._taskStatus(task);
        if (from === targetStatus) return;
        this._moveTask(task, targetStatus);
    }

    _onTaskCardClick(task, e) {
        if (this._suppressTaskClick) return;
        const path = e.composedPath();
        if (path.some((node) => node instanceof Element && (node.classList.contains('task-move-btn') || node.classList.contains('task-drag-handle')))) {
            return;
        }
        this._openTask(task.entity_id);
    }

    render() {
        const taskStatuses = this._statusColumns();
        const tasks = this._filteredTasks();
        const tasksByStatus = {
            todo: tasks.filter((task) => this._taskStatus(task) === 'todo'),
            in_progress: tasks.filter((task) => this._taskStatus(task) === 'in_progress'),
            done: tasks.filter((task) => this._taskStatus(task) === 'done'),
        };

        return html`
            <div class="page-toolbar">
                <platform-breadcrumbs></platform-breadcrumbs>
                <div class="top-row">
                    <h1 class="title">${this.t('tasks.title')}</h1>
                    <label class="search-box">
                        <platform-icon name="search" size="14"></platform-icon>
                        <input
                            class="search-input"
                            type="text"
                            placeholder=${this.t('search.placeholder')}
                            .value=${this._filter}
                            @input=${this._onSearchInput}
                        />
                    </label>
                    <div class="toolbar-actions">
                        <button class="icon-btn-toolbar" type="button" @click=${() => this._loadTasks()} title=${this.t('refresh', {}, 'common')}>
                            <platform-icon name="refresh" size="16"></platform-icon>
                        </button>
                        <button class="cta-btn" type="button" @click=${this._createTask}>${this.t('create', {}, 'common')}</button>
                    </div>
                </div>
                <div class="status-tabs">
                    ${taskStatuses.map((s) => html`
                        <button
                            class="status-tab ${this._activeStatus === s.id ? 'active' : ''}"
                            type="button"
                            @click=${() => { this._activeStatus = s.id; }}
                        >
                            ${s.label}
                            <span class="status-count">${tasksByStatus[s.id].length}</span>
                        </button>
                    `)}
                </div>
            </div>

            <div class="board-shell ${this._boardBusy ? 'busy' : ''}">
                <div
                    class="board"
                    aria-busy=${this._boardBusy ? 'true' : 'false'}
                    aria-live=${this._boardBusy ? 'polite' : 'off'}
                >
                    ${taskStatuses.map((s) => {
                        const isActive = !this._isMobile || this._activeStatus === s.id;
                        const statusTasks = tasksByStatus[s.id];
                        return html`
                            <section class="column ${isActive ? 'mobile-active' : ''}">
                                <div class="column-header">
                                    <div class="column-title">${s.label}</div>
                                    <div class="column-count">${statusTasks.length}</div>
                                </div>
                                <div
                                    class="column-body ${this._dragOverStatus === s.id ? 'dnd-target' : ''}"
                                    @dragover=${(e) => this._onColumnBodyDragOver(e, s.id)}
                                    @dragleave=${this._onColumnDragLeave}
                                    @drop=${(e) => this._onColumnDrop(e, s.id)}
                                >
                                    ${this._loading ? html`
                                        <div class="empty">${this.t('loading', {}, 'common')}</div>
                                    ` : statusTasks.length === 0 ? html`
                                        ${this._dndGapEmptyColumn(s.id) ? html`<div class="dnd-gap" aria-hidden="true"></div>` : nothing}
                                        <div class="empty">${this.t('tasks.empty')}</div>
                                    ` : html`
                                        ${statusTasks.map((task) => html`
                                            ${this._dndGapBeforeTask(s.id, task.entity_id) ? html`<div class="dnd-gap" aria-hidden="true"></div>` : nothing}
                                            <article
                                                class="task-card"
                                                data-task-id=${task.entity_id}
                                                @click=${(e) => this._onTaskCardClick(task, e)}
                                            >
                                                <div class="task-card-top">
                                                    <div class="task-card-top-main">
                                                        <div class="task-icon">
                                                            <platform-icon name="checklist" size="18"></platform-icon>
                                                        </div>
                                                        <span class="task-name">${task.name}</span>
                                                    </div>
                                                    ${!this._isMobile ? html`
                                                        <div
                                                            class="task-drag-handle"
                                                            draggable="true"
                                                            title=${this.t('tasks_page.drag_hint')}
                                                            role="button"
                                                            tabindex="0"
                                                            aria-label=${this.t('tasks_page.drag_hint')}
                                                            @dragstart=${(e) => this._onTaskDragStart(e, task)}
                                                            @dragend=${this._onTaskDragEnd}
                                                            @click=${(e) => e.stopPropagation()}
                                                        >
                                                            <platform-icon name="drag-handle" size="18"></platform-icon>
                                                        </div>
                                                    ` : nothing}
                                                </div>
                                                <div class="task-footer">
                                                    <span class="task-priority">${task.priority ? task.priority : 'medium'}</span>
                                                    <button class="task-move-btn" type="button" @click=${(e) => { e.stopPropagation(); this._moveTask(task, this._nextStatus(s.id)); }}>
                                                        <platform-icon name="${this._nextStatusIcon(s.id)}" size="12"></platform-icon>
                                                        ${this._nextStatusLabel(s.id)}
                                                    </button>
                                                </div>
                                            </article>
                                        `)}
                                        ${this._dndGapAfterLast(s.id, statusTasks.length) ? html`<div class="dnd-gap" aria-hidden="true"></div>` : nothing}
                                    `}
                                </div>
                            </section>
                        `;
                    })}
                </div>
                ${this._boardBusy ? html`
                    <div
                        class="board-overlay"
                        role="status"
                        aria-label=${this.t('tasks_page.board_syncing')}
                    >
                        <glass-spinner size="lg"></glass-spinner>
                    </div>
                ` : nothing}
            </div>
        `;
    }
}

customElements.define('crm-tasks-page', CRMTasksPage);
