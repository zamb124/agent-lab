import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { resolveObjectName } from '@platform/lib/utils/entity-ref.js';
import { CRMStore } from '../store/crm.store.js';
import '../modals/entity-modal.js';
import '@platform/lib/components/platform-icon.js';

const TASK_DND_MIME = 'application/x-crm-task-id';

export class TasksPage extends PlatformElement {
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
    };

    static styles = [
        PlatformElement.styles,
        buttonStyles,
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

            .section-label {
                color: var(--text-tertiary);
                font-size: var(--text-sm);
                margin-bottom: var(--space-1);
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

            /* === STATUS TABS === */

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

            /* === BOARD (desktop) === */

            .board {
                flex: 1;
                min-height: 0;
                display: grid;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                gap: var(--space-3);
                overflow: auto;
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
                font-size: var(--text-sm);
                font-weight: 600;
                color: var(--text-primary);
            }

            .column-count {
                font-size: var(--text-xs);
                color: var(--text-secondary);
                background: var(--crm-surface-tint-strong);
                border-radius: var(--radius-full);
                padding: var(--space-1) var(--space-2);
            }

            .column-body {
                flex: 1;
                min-height: 0;
                overflow: auto;
                padding: var(--space-2);
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                transition: background var(--duration-fast), box-shadow var(--duration-fast), outline-color var(--duration-fast);
            }

            .column-body.dnd-target {
                outline: 2px dashed var(--crm-selected-stroke);
                outline-offset: -2px;
                background: color-mix(in srgb, var(--crm-selected-bg) 55%, transparent);
                box-shadow: inset 0 0 0 1px var(--crm-selected-stroke);
            }

            .dnd-gap {
                height: 4px;
                margin: 4px 0;
                border-radius: var(--radius-sm);
                background: linear-gradient(
                    90deg,
                    var(--crm-daily-notes-cta-bg),
                    var(--accent-tertiary, #8794f0)
                );
                box-shadow: 0 0 0 1px var(--crm-selected-stroke);
                flex-shrink: 0;
                pointer-events: none;
            }

            @media (prefers-reduced-motion: reduce) {
                .column-body {
                    transition: none;
                }
            }

            /* === TASK CARDS === */

            .task-card {
                border: 1px solid var(--crm-stroke);
                border-radius: 16px;
                background: var(--crm-surface);
                padding: 16px;
                display: flex;
                flex-direction: column;
                gap: 10px;
                cursor: pointer;
                transition: border-color var(--duration-fast), background var(--duration-fast), transform var(--duration-fast), opacity var(--duration-fast), box-shadow var(--duration-fast);
            }

            .task-card:hover {
                border-color: var(--crm-stroke-strong);
                background: var(--crm-surface-elevated);
            }

            .task-card.dnd-dragging {
                opacity: 0.55;
                transform: scale(0.98);
                box-shadow: var(--glass-shadow-medium, 0 8px 24px rgba(0, 0, 0, 0.12));
            }

            .task-card-top {
                display: flex;
                align-items: flex-start;
                justify-content: space-between;
                gap: var(--space-2);
                min-width: 0;
            }

            .task-card-top-main {
                display: flex;
                align-items: center;
                gap: 10px;
                min-width: 0;
                flex: 1;
            }

            .task-drag-handle {
                flex-shrink: 0;
                width: 32px;
                height: 32px;
                margin: -4px -4px 0 0;
                padding: 0;
                box-sizing: border-box;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-md);
                background: transparent;
                color: var(--text-tertiary);
                cursor: grab;
                touch-action: none;
                user-select: none;
                -webkit-user-select: none;
                transition: color var(--duration-fast), background var(--duration-fast);
            }

            .task-drag-handle * {
                pointer-events: none;
            }

            .task-drag-handle:hover {
                color: var(--text-secondary);
                background: var(--crm-surface-tint);
            }

            .task-drag-handle:active {
                cursor: grabbing;
            }

            .task-icon {
                width: 36px;
                height: 36px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-lg);
                background: rgba(255, 152, 0, 0.15);
                color: #FF9800;
                flex-shrink: 0;
            }

            .task-name {
                font-size: 15px;
                line-height: 20px;
                font-weight: 700;
                color: var(--text-primary);
                margin: 0;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                flex: 1;
                min-width: 0;
                padding: 0;
                text-align: left;
            }

            .task-meta {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                font-size: 11px;
                color: var(--text-tertiary);
            }

            .task-footer {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 8px;
                margin-top: auto;
            }

            .task-priority {
                display: inline-flex;
                align-items: center;
                gap: 4px;
                padding: 0 10px;
                min-height: 22px;
                font-size: 11px;
                border-radius: 12px;
                font-weight: 500;
                border: none;
                white-space: nowrap;
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

            /* === MOBILE === */

            @media (max-width: 1023px) {
                .board {
                    grid-template-columns: 1fr;
                }
            }

            @media (max-width: 767px) {
                .page-toolbar {
                    padding: var(--space-2) var(--space-3);
                    max-width: 100%;
                    box-sizing: border-box;
                    overflow: hidden;
                }

                .section-label,
                .title,
                .cta-btn {
                    display: none;
                }

                .top-row {
                    margin-bottom: var(--space-2);
                }

                .search-box {
                    display: none;
                }

                .toolbar-actions {
                    display: none;
                }

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
                }

                .board .column.mobile-active {
                    display: flex;
                    background: transparent;
                    border: none;
                    border-radius: 0;
                }

                .board .column.mobile-active .column-header {
                    display: none;
                }

                .board .column.mobile-active .column-body {
                    padding: var(--space-1) 0;
                }

                .task-card {
                    padding: 14px;
                    border-radius: 12px;
                }

                .task-icon {
                    width: 32px;
                    height: 32px;
                }

                .task-name {
                    font-size: 14px;
                }
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
        this._currentNamespace = null;

        this._unsubscribe = CRMStore.subscribe((state) => {
            this._isMobile = state.ui.isMobile;

            const prevNs = this._currentNamespace;
            this._currentNamespace = state.namespaces.current;
            const prevName = this._resolveNamespaceName(prevNs);
            const nextName = this._resolveNamespaceName(this._currentNamespace);
            if (prevName !== nextName && prevName !== null) {
                this._loadTasks();
            }
        });

        this._onTasksCreate = this._onTasksCreate.bind(this);
        this._onTasksRefresh = this._onTasksRefresh.bind(this);
        this._onMobileSearch = this._onMobileSearch.bind(this);
        this._suppressTaskClick = false;
    }

    connectedCallback() {
        super.connectedCallback();
        window.addEventListener('tasks-create', this._onTasksCreate);
        window.addEventListener('tasks-refresh', this._onTasksRefresh);
        window.addEventListener('crm-mobile-search', this._onMobileSearch);
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._unsubscribe?.();
        window.removeEventListener('tasks-create', this._onTasksCreate);
        window.removeEventListener('tasks-refresh', this._onTasksRefresh);
        window.removeEventListener('crm-mobile-search', this._onMobileSearch);
    }

    async firstUpdated() {
        await this._loadTasks();
    }

    _onTasksCreate() {
        this._createTask();
    }

    _onTasksRefresh() {
        this._loadTasks();
    }

    _onMobileSearch(event) {
        this._filter = typeof event.detail?.query === 'string' ? event.detail.query : '';
    }

    _onTasksSearchInput(event) {
        this._filter = event.target.value;
        CRMStore.setTasksListSearchQuery(this._filter);
    }

    _resolveNamespaceName(ns) {
        if (!ns) {
            return null;
        }
        if (typeof ns === 'string') {
            return ns;
        }
        if (typeof ns === 'object' && typeof ns.name === 'string') {
            return ns.name;
        }
        throw new Error('Invalid namespace value');
    }

    async _loadTasks() {
        this._loading = true;
        const crmApi = this.crmApi;
        const namespaceName = resolveObjectName(CRMStore.state.namespaces.current, null);
        const tasks = await crmApi.getEntities({
            entity_type: 'task',
            namespace: namespaceName,
            limit: 200,
        });
        this._tasks = Array.isArray(tasks) ? tasks : [];
        this._loading = false;
    }

    _openTask(taskId) {
        CRMStore.setCurrentView('entities');
        CRMStore.setCurrentEntity(taskId);
    }

    async _moveTask(task, targetStatus) {
        const crmApi = this.crmApi;
        const attributes = {
            ...(task.attributes || {}),
            status: targetStatus,
        };
        await crmApi.updateEntity(task.entity_id, { attributes });
        await this._loadTasks();
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
        if (this._isMobile) {
            return;
        }
        this._draggingTaskId = task.entity_id;
        this._dndSourceStatus = this._taskStatus(task);
        this._dndInsert = null;
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData(TASK_DND_MIME, task.entity_id);
        e.dataTransfer.setData('text/plain', task.entity_id);
        const card = e.currentTarget.closest('.task-card');
        if (card) {
            card.classList.add('dnd-dragging');
        }
    }

    _onTaskDragEnd(e) {
        const card = e.currentTarget.closest('.task-card');
        if (card) {
            card.classList.remove('dnd-dragging');
        }
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
            if (!id) {
                continue;
            }
            const r = el.getBoundingClientRect();
            const mid = r.top + r.height / 2;
            if (y < mid) {
                beforeTaskId = id;
                break;
            }
        }
        const prev = this._dndInsert;
        if (prev && prev.status === statusId && prev.beforeTaskId === beforeTaskId) {
            return;
        }
        this._dndInsert = { status: statusId, beforeTaskId };
    }

    _onColumnBodyDragOver(e, targetStatus) {
        if (this._isMobile || !this._draggingTaskId) {
            return;
        }
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        if (this._dragOverStatus !== targetStatus) {
            this._dragOverStatus = targetStatus;
        }
        this._computeDndInsert(e, targetStatus);
    }

    _onColumnDragLeave(e) {
        if (this._isMobile || !this._draggingTaskId) {
            return;
        }
        const col = e.currentTarget;
        const related = e.relatedTarget;
        if (related && col.contains(related)) {
            return;
        }
        this._dragOverStatus = null;
        this._dndInsert = null;
    }

    _dndGapBeforeTask(statusId, taskId) {
        if (this._isMobile || !this._dndInsert || this._dndSourceStatus === statusId) {
            return false;
        }
        if (this._dndInsert.status !== statusId) {
            return false;
        }
        return this._dndInsert.beforeTaskId === taskId;
    }

    _dndGapAfterLast(statusId, taskCount) {
        if (this._isMobile || !this._dndInsert || this._dndSourceStatus === statusId) {
            return false;
        }
        if (this._dndInsert.status !== statusId) {
            return false;
        }
        if (this._dndInsert.beforeTaskId !== '__end__') {
            return false;
        }
        return taskCount > 0;
    }

    _dndGapEmptyColumn(statusId) {
        if (this._isMobile || !this._dndInsert || this._dndSourceStatus === statusId) {
            return false;
        }
        if (this._dndInsert.status !== statusId) {
            return false;
        }
        return this._dndInsert.beforeTaskId === '__end__';
    }

    async _onColumnDrop(e, targetStatus) {
        if (this._isMobile) {
            return;
        }
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
        if (!task) {
            return;
        }
        const from = this._taskStatus(task);
        if (from === targetStatus) {
            return;
        }
        await this._moveTask(task, targetStatus);
    }

    _onTaskCardClick(task, e) {
        if (this._suppressTaskClick) {
            return;
        }
        const path = e.composedPath();
        if (path.some((node) => node instanceof Element && (node.classList.contains('task-move-btn') || node.classList.contains('task-drag-handle')))) {
            return;
        }
        this._openTask(task.entity_id);
    }

    async _createTask() {
        const crmApi = this.crmApi;
        const namespaceName = resolveObjectName(CRMStore.state.namespaces.current, null);
        await crmApi.createEntity({
            entity_type: 'task',
            name: this.i18n.t('tasks.new'),
            description: '',
            namespace: namespaceName || 'default',
            priority: 'medium',
            attributes: { status: 'todo' },
        });
        await this._loadTasks();
        this.success(this.i18n.t('tasks_page.success_created'));
    }

    _taskStatus(task) {
        const status = task.attributes?.status;
        if (['todo', 'in_progress', 'done'].includes(status)) {
            return status;
        }
        return 'todo';
    }

    _filteredTasks() {
        if (!this._filter) {
            return this._tasks;
        }
        const query = this._filter.toLowerCase();
        return this._tasks.filter((task) => {
            const name = task.name || '';
            const description = task.description || '';
            return name.toLowerCase().includes(query) || description.toLowerCase().includes(query);
        });
    }

    _nextStatus(status) {
        if (status === 'todo') return 'in_progress';
        if (status === 'in_progress') return 'done';
        return 'todo';
    }

    _nextStatusLabel(status) {
        if (status === 'todo') return this.i18n.t('tasks_page.next_to_progress');
        if (status === 'in_progress') return this.i18n.t('tasks_page.next_to_done');
        return this.i18n.t('tasks_page.next_revert');
    }

    _getTaskColumnStatuses() {
        return [
            { id: 'todo', label: this.i18n.t('tasks_page.column_todo') },
            { id: 'in_progress', label: this.i18n.t('tasks_page.column_in_progress') },
            { id: 'done', label: this.i18n.t('tasks_page.column_done') },
        ];
    }

    _nextStatusIcon(status) {
        if (status === 'todo') return 'play';
        if (status === 'in_progress') return 'check';
        return 'refresh';
    }

    render() {
        const taskStatuses = this._getTaskColumnStatuses();
        const tasks = this._filteredTasks();
        const tasksByStatus = {
            todo: tasks.filter((task) => this._taskStatus(task) === 'todo'),
            in_progress: tasks.filter((task) => this._taskStatus(task) === 'in_progress'),
            done: tasks.filter((task) => this._taskStatus(task) === 'done'),
        };

        return html`
            <div class="page-toolbar">
                <div class="section-label">${this.i18n.t('tasks.title')}</div>
                <div class="top-row">
                    <div class="title">${this.i18n.t('tasks.title')}</div>
                    <label class="search-box">
                        <platform-icon name="search" size="14"></platform-icon>
                        <input
                            class="search-input"
                            type="text"
                            placeholder=${this.i18n.t('search.placeholder')}
                            .value=${this._filter}
                            @input=${this._onTasksSearchInput}
                        />
                    </label>
                    <div class="toolbar-actions">
                        <button class="icon-btn-toolbar" type="button" @click=${this._loadTasks} title=${this.i18n.t('refresh', {}, 'common')}>
                            <platform-icon name="refresh" size="16"></platform-icon>
                        </button>
                        <button class="cta-btn" type="button" @click=${this._createTask}>${this.i18n.t('create', {}, 'common')}</button>
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

            <div class="board">
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
                                    <div class="empty">${this.i18n.t('loading', {}, 'common')}</div>
                                ` : statusTasks.length === 0 ? html`
                                    ${this._dndGapEmptyColumn(s.id) ? html`<div class="dnd-gap" aria-hidden="true"></div>` : ''}
                                    <div class="empty">${this.i18n.t('tasks.empty')}</div>
                                ` : html`
                                    ${statusTasks.map((task) => html`
                                        ${this._dndGapBeforeTask(s.id, task.entity_id) ? html`<div class="dnd-gap" aria-hidden="true"></div>` : ''}
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
                                                        title=${this.i18n.t('tasks_page.drag_hint')}
                                                        role="button"
                                                        tabindex="0"
                                                        aria-label=${this.i18n.t('tasks_page.drag_hint')}
                                                        @dragstart=${(e) => this._onTaskDragStart(e, task)}
                                                        @dragend=${this._onTaskDragEnd}
                                                        @click=${(e) => e.stopPropagation()}
                                                    >
                                                        <platform-icon name="drag-handle" size="18" ?filled=${true}></platform-icon>
                                                    </div>
                                                ` : ''}
                                            </div>
                                            <div class="task-footer">
                                                <span class="task-priority">${task.priority || 'medium'}${task.due_date ? ` \u00b7 ${task.due_date}` : ''}</span>
                                                <button class="task-move-btn" type="button" @click=${(e) => { e.stopPropagation(); this._moveTask(task, this._nextStatus(s.id)); }}>
                                                    <platform-icon name="${this._nextStatusIcon(s.id)}" size="12"></platform-icon>
                                                    ${this._nextStatusLabel(s.id)}
                                                </button>
                                            </div>
                                        </article>
                                    `)}
                                    ${this._dndGapAfterLast(s.id, statusTasks.length) ? html`<div class="dnd-gap" aria-hidden="true"></div>` : ''}
                                `}
                            </div>
                        </section>
                    `;
                })}
            </div>
        `;
    }
}

customElements.define('tasks-page', TasksPage);
