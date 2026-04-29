/**
 * TasksPage — kanban-доска пользовательских задач (entity_type=task) для
 * активного namespace. Загружает задачи через `crm/entities_lookup`,
 * создаёт через `crm/entities` (create), переносит между колонками через
 * `crm/entity_update`. Drag&drop работает на десктопе, на мобильном —
 * вкладки колонок. Открытие задачи — страница сущности с `?edit=1`.
 */

import { html, css, nothing } from 'lit';
import { CRMNamespacePage } from '../base/crm-namespace-page.js';
import { CoreEvents } from '@platform/lib/events/index.js';
import {
    pruneToAllowedIds,
    readCollapsedStatusIds,
    writeCollapsedStatusIds,
} from '../utils/tasks-kanban-column-collapse.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-breadcrumbs.js';
import '@platform/lib/components/layout/page-header.js';

const TASK_DND_MIME = 'application/x-crm-task-id';

export class CRMTasksPage extends CRMNamespacePage {
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
        _mobileHeaderSearch: { state: true },
        _boardStages: { state: true },
        _boardKey: { state: true },
        _collapsedStatusIds: { state: true },
    };

    static styles = [
        CRMNamespacePage.styles,
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
                gap: var(--space-2);
                padding: var(--space-3);
                border-bottom: 1px solid var(--crm-stroke);
                flex-shrink: 0;
            }

            .column-header-aside {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                flex-shrink: 0;
            }

            .column-collapse-btn {
                width: 28px;
                height: 28px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-full);
                border: 1px solid var(--crm-stroke);
                background: var(--crm-surface);
                color: var(--text-secondary);
                cursor: pointer;
                padding: 0;
                flex-shrink: 0;
                transition: all var(--duration-fast);
            }

            .column-collapse-btn:hover {
                border-color: var(--crm-selected-stroke);
                color: var(--text-primary);
            }

            .column.collapsed .column-header {
                flex: 1;
                flex-direction: column;
                align-items: center;
                justify-content: flex-start;
                border-bottom: none;
                padding: var(--space-2) 4px;
                min-height: 0;
            }

            .column-title-vertical {
                font-weight: 600;
                color: var(--text-primary);
                font-size: var(--text-xs);
                writing-mode: vertical-rl;
                text-orientation: mixed;
                max-height: min(240px, 40vh);
                overflow: hidden;
                text-overflow: ellipsis;
                line-height: 1.3;
            }

            .column-count-vertical {
                color: var(--text-tertiary);
                font-size: 10px;
                font-weight: 600;
            }

            .column.collapsed {
                cursor: default;
            }

            .column.collapsed.dnd-target-col {
                outline: 2px dashed var(--crm-selected-stroke);
                outline-offset: -6px;
                background: var(--crm-selected-bg);
            }

            .column-title {
                font-weight: 600;
                color: var(--text-primary);
                font-size: var(--text-sm);
                min-width: 0;
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

            .column.collapsed .column-body {
                display: none;
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

            .tasks-mobile-header-wrap {
                display: none;
            }

            .mobile-header-icon-btn {
                width: 32px;
                height: 32px;
                flex-shrink: 0;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-medium);
                background: var(--glass-solid-strong);
                color: var(--text-primary);
                cursor: pointer;
                box-shadow: var(--glass-shadow-subtle);
                padding: 0;
            }
            .mobile-header-icon-btn:hover {
                background: var(--glass-solid-medium);
            }
            .mobile-header-icon-btn.active {
                border-color: var(--accent);
                color: var(--accent);
            }

            .mobile-toolbar-search-row {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                width: 100%;
                min-width: 0;
            }

            .mobile-header-search-box {
                flex: 1;
                min-width: 0;
                min-height: 40px;
            }

            .mobile-header-search-box .search-input {
                min-width: 0;
                flex: 1;
            }

            @media (max-width: 1023px) {
                .board { grid-template-columns: 1fr; }
            }

            @media (max-width: 767px) {
                :host {
                    padding: 0;
                    box-sizing: border-box;
                }
                .tasks-mobile-header-wrap {
                    display: block;
                }
                .page-toolbar {
                    padding-left: max(var(--space-2), env(safe-area-inset-left, 0px));
                    padding-right: max(var(--space-2), env(safe-area-inset-right, 0px));
                    box-sizing: border-box;
                }
                .top-row {
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
                    padding: 0 max(var(--space-2), env(safe-area-inset-right, 0px)) 0 max(var(--space-2), env(safe-area-inset-left, 0px));
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
        this._activeStatus = '';
        this._dragOverStatus = null;
        this._draggingTaskId = null;
        this._dndInsert = null;
        this._dndSourceStatus = null;
        this._boardBusy = false;
        this._mobileHeaderSearch = false;
        this._suppressTaskClick = false;
        this._mql = null;
        this._onMqlChange = null;
        this._boardStages = null;
        this._boardKey = '';
        this._collapsedStatusIds = [];

        this._lookupOp = this.useOp('crm/entities_lookup');
        this._updateOp = this.useOp('crm/entity_update');
        this._entitiesResource = this.useResource('crm/entities');
        this._taskBoardOp = this.useOp('crm/task_board_stages');

        this._companyIdSel = this.select((s) => {
            const user = s.auth.user;
            if (!user || typeof user.company_id !== 'string') return null;
            const id = user.company_id.trim();
            return id.length > 0 ? id : null;
        });
        this._routeKeySel = this.select((s) => s.router.routeKey);
        this._routerSearchSel = this.select((s) => {
            const raw = s.router.search;
            return typeof raw === 'string' ? raw : '';
        });
    }

    connectedCallback() {
        super.connectedCallback();
        this._mql = window.matchMedia('(max-width: 767px)');
        this._isMobile = this._mql.matches;
        this._onMqlChange = (e) => { this._isMobile = e.matches; };
        this._mql.addEventListener('change', this._onMqlChange);

        this.useEvent(CoreEvents.UI_NAMESPACE_CHANGED, () => this._reloadTasksPage());
        this.useEvent(CoreEvents.ROUTER_ROUTE_CHANGED, () => {
            if (this._routeKeySel.value !== 'tasks') {
                return;
            }
            this._reloadTasksPage();
        });
        this.useEvent(this._lookupOp.op.events.SUCCEEDED, (event) => this._onTasksLoaded(event.payload.result));
        this.useEvent(this._lookupOp.op.events.FAILED, () => { this._loading = false; });
        this.useEvent(this._taskBoardOp.op.events.SUCCEEDED, (event) => {
            this._onTaskBoardStagesLoaded(event.payload.result);
        });
        this.useEvent(this._taskBoardOp.op.events.FAILED, (event) => {
            this._boardStages = [];
            this._boardKey = '';
            this._collapsedStatusIds = [];
            this.toast('crm:tasks_page.board_stages_failed', {
                type: 'error',
                vars: { message: typeof event.payload.message === 'string' ? event.payload.message : '' },
            });
        });
        this.useEvent(this._updateOp.op.events.SUCCEEDED, () => { this._boardBusy = false; this._loadTasks({ silent: true }); });
        this.useEvent(this._updateOp.op.events.FAILED, (event) => {
            this._boardBusy = false;
            this.toast('crm:tasks_page.move_failed', { type: 'error', vars: { message: event.payload.message } });
            this._loadTasks({ silent: true });
        });
        this.useEvent(this._entitiesResource.resource.events.CREATED, () => this._loadTasks({ silent: true }));

        this._reloadTasksPage();
    }

    _reloadTasksPage() {
        this._loadTaskBoardStages();
        this._loadTasks();
    }

    disconnectedCallback() {
        if (this._mql && this._onMqlChange) {
            this._mql.removeEventListener('change', this._onMqlChange);
        }
        super.disconnectedCallback();
    }

    _currentNamespace() {
        return this._crmNamespaceSel.value;
    }

    /**
     * Фильтр досок задач по подтипу берётся из query, синхронизированного с роутером
     * (`state.router.search`), а не из window.location — так create и list используют
     * один и тот же источник после client-side navigate.
     */
    _taskSubtypeFromTasksRouterSearch() {
        const raw = this._routerSearchSel.value;
        if (typeof raw !== 'string' || raw.length === 0) {
            return '';
        }
        const sp = new URLSearchParams(raw);
        const et = sp.get('entity_type');
        const es = sp.get('entity_subtype');
        if (es === null || es.length === 0) {
            return '';
        }
        if (et !== null && et.length > 0 && et !== 'task') {
            return '';
        }
        return es;
    }

    _boardApiNamespace() {
        const ns = this._currentNamespace();
        if (ns !== null && typeof ns === 'string' && ns.length > 0) {
            return ns;
        }
        return 'default';
    }

    _loadTaskBoardStages() {
        const sub = this._taskSubtypeFromTasksRouterSearch();
        this._taskBoardOp.run({
            namespace_name: this._boardApiNamespace(),
            entity_subtype: sub.length > 0 ? sub : null,
        });
    }

    _parseTaskBoardStagesResult(result) {
        if (!result || typeof result !== 'object') {
            throw new Error('CRMTasksPage: ответ стадий доски должен быть объектом');
        }
        const boardKeyRaw = result.board_key;
        const boardKey = typeof boardKeyRaw === 'string' ? boardKeyRaw.trim() : '';
        if (!boardKey) {
            throw new Error('CRMTasksPage: в ответе стадий доски нужен непустой board_key');
        }
        if (!Array.isArray(result.stages)) {
            throw new Error('CRMTasksPage: в ответе стадий доски нужен массив stages');
        }
        const out = [];
        for (const row of result.stages) {
            if (!row || typeof row !== 'object') {
                continue;
            }
            const id = typeof row.id === 'string' ? row.id.trim() : '';
            const label = typeof row.label === 'string' ? row.label.trim() : '';
            if (!id || !label) {
                continue;
            }
            const color = typeof row.color === 'string' && row.color.trim().length > 0 ? row.color.trim() : null;
            out.push({ id, label, color });
        }
        return { boardKey, stages: out };
    }

    _hydrateCollapsedFromStorage(stages) {
        this._collapsedStatusIds = [];
        if (!Array.isArray(stages) || stages.length === 0) {
            return;
        }
        const companyId = this._companyIdSel.value;
        if (companyId === null) {
            return;
        }
        const raw = readCollapsedStatusIds(companyId, this._boardApiNamespace(), this._boardKey);
        const allowed = new Set(stages.map((row) => row.id));
        this._collapsedStatusIds = pruneToAllowedIds(raw, allowed);
    }

    _isColumnCollapsed(statusId) {
        return this._collapsedStatusIds.includes(statusId);
    }

    _persistCollapsedColumns() {
        const companyId = this._companyIdSel.value;
        if (companyId === null) {
            return;
        }
        if (typeof this._boardKey !== 'string' || this._boardKey.length === 0) {
            return;
        }
        writeCollapsedStatusIds(companyId, this._boardApiNamespace(), this._boardKey, this._collapsedStatusIds);
    }

    _toggleColumnCollapse(statusId, event) {
        event.stopPropagation();
        if (this._isMobile) {
            return;
        }
        const next = new Set(this._collapsedStatusIds);
        if (next.has(statusId)) {
            next.delete(statusId);
        } else {
            next.add(statusId);
        }
        this._collapsedStatusIds = [...next].sort();
        this._persistCollapsedColumns();
    }

    _boardGridTemplateColumns(taskStatuses) {
        if (this._isMobile) {
            return 'minmax(0, 1fr)';
        }
        return taskStatuses
            .map((s) => (this._isColumnCollapsed(s.id) ? 'minmax(36px, 44px)' : 'minmax(0, 1fr)'))
            .join(' ');
    }

    _onTaskBoardStagesLoaded(result) {
        const { boardKey, stages } = this._parseTaskBoardStagesResult(result);
        this._boardKey = boardKey;
        this._boardStages = stages;
        this._hydrateCollapsedFromStorage(stages);
        if (stages.length === 0) {
            this.toast('crm:tasks_page.board_stages_empty', { type: 'error' });
            return;
        }
        const ids = new Set(stages.map((sRow) => sRow.id));
        if (!ids.has(this._activeStatus)) {
            this._activeStatus = stages[0].id;
        }
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
        const sub = this._taskSubtypeFromTasksRouterSearch();
        if (sub.length > 0) {
            payload.entity_subtype = sub;
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
        const board = this._boardStages;
        const attrs = task && task.attributes;
        const raw = attrs && typeof attrs.status === 'string' ? attrs.status.trim() : '';
        if (!board || board.length === 0) {
            return raw.length > 0 ? raw : '';
        }
        const allowed = new Set(board.map((s) => s.id));
        const first = board[0].id;
        if (raw.length > 0 && allowed.has(raw)) {
            return raw;
        }
        return first;
    }

    _nextStatus(status) {
        const b = this._boardStages;
        if (!b || b.length === 0) {
            throw new Error('CRMTasksPage: доска стадий не загружена');
        }
        const idx = b.findIndex((s) => s.id === status);
        const i = idx >= 0 ? idx : 0;
        const nextIdx = (i + 1) % b.length;
        return b[nextIdx].id;
    }

    _nextStatusLabel() {
        return this.t('tasks_page.next_status');
    }

    _nextStatusIcon() {
        return 'arrow-right';
    }

    _statusColumns() {
        const b = this._boardStages;
        if (!b || b.length === 0) {
            return [];
        }
        return b.map((s) => ({ id: s.id, label: s.label, color: s.color }));
    }

    _openTask(taskId) {
        this.navigate('entity', { itemId: taskId }, { search: '?edit=1' });
    }

    _createTask() {
        const cols = this._statusColumns();
        if (cols.length === 0) {
            this.toast('crm:tasks_page.board_not_ready', { type: 'error' });
            return;
        }
        const namespace = this._currentNamespace();
        const body = {
            entity_type: 'task',
            name: this.t('tasks.new'),
            description: '',
            namespace: namespace === null ? 'default' : namespace,
            priority: 'medium',
            attributes: { status: cols[0].id },
        };
        const sub = this._taskSubtypeFromTasksRouterSearch();
        if (sub.length > 0) {
            body.entity_subtype = sub;
        }
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

    _onCollapsedColumnShellDragOver(e) {
        if (!(e.currentTarget instanceof HTMLElement)) {
            throw new Error('CRMTasksPage: ожидался HTMLElement');
        }
        const statusId = e.currentTarget.dataset.statusId;
        if (typeof statusId !== 'string' || statusId.length === 0) {
            throw new Error('CRMTasksPage: у колонки должен быть data-status-id');
        }
        if (this._isMobile || !this._isColumnCollapsed(statusId)) {
            return;
        }
        this._onColumnBodyDragOver(e, statusId, true);
    }

    _onCollapsedColumnShellDragLeave(e) {
        if (!(e.currentTarget instanceof HTMLElement)) {
            throw new Error('CRMTasksPage: ожидался HTMLElement');
        }
        const statusId = e.currentTarget.dataset.statusId;
        if (typeof statusId !== 'string' || statusId.length === 0) {
            throw new Error('CRMTasksPage: у колонки должен быть data-status-id');
        }
        if (this._isMobile || !this._isColumnCollapsed(statusId)) {
            return;
        }
        this._onColumnDragLeave(e);
    }

    _onCollapsedColumnShellDrop(e) {
        if (!(e.currentTarget instanceof HTMLElement)) {
            throw new Error('CRMTasksPage: ожидался HTMLElement');
        }
        const statusId = e.currentTarget.dataset.statusId;
        if (typeof statusId !== 'string' || statusId.length === 0) {
            throw new Error('CRMTasksPage: у колонки должен быть data-status-id');
        }
        if (this._isMobile || !this._isColumnCollapsed(statusId)) {
            return;
        }
        this._onColumnDrop(e, statusId);
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

    _onColumnBodyDragOver(e, targetStatus, collapsedStrip) {
        if (this._isMobile || !this._draggingTaskId) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        if (this._dragOverStatus !== targetStatus) {
            this._dragOverStatus = targetStatus;
        }
        if (collapsedStrip === true) {
            this._dndInsert = { status: targetStatus, beforeTaskId: '__end__' };
            return;
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

    _toggleMobileHeaderSearch() {
        this._mobileHeaderSearch = !this._mobileHeaderSearch;
    }

    _closeMobileHeaderSearch() {
        this._mobileHeaderSearch = false;
    }

    _renderMobileTasksHeader() {
        return html`
            <div class="tasks-mobile-header-wrap">
                <page-header
                    title=${this.t('tasks.title')}
                    subtitle=""
                    .mobileToolbarMode=${this._mobileHeaderSearch ? 'search' : 'title'}
                >
                    <div slot="toolbar-search" class="mobile-toolbar-search-row">
                        <button
                            type="button"
                            class="mobile-header-icon-btn"
                            @click=${this._closeMobileHeaderSearch}
                            title=${this.t('daily_notes_page.mobile_header_close_search')}
                        >
                            <platform-icon name="close" size="16"></platform-icon>
                        </button>
                        <label
                            class="search-box mobile-header-search-box"
                            style="display:flex;align-items:center;gap:var(--space-2);flex:1;min-width:0;width:100%;box-sizing:border-box"
                        >
                            <platform-icon name="search" size="14"></platform-icon>
                            <input
                                class="search-input"
                                type="text"
                                style="flex:1;min-width:0;width:100%;box-sizing:border-box"
                                placeholder=${this.t('search.placeholder')}
                                .value=${this._filter}
                                @input=${this._onSearchInput}
                            />
                        </label>
                    </div>
                    <div slot="actions">
                        <button
                            type="button"
                            class="mobile-header-icon-btn"
                            @click=${() => this._reloadTasksPage()}
                            title=${this.t('refresh', {}, 'common')}
                        >
                            <platform-icon name="refresh" size="18"></platform-icon>
                        </button>
                        <button
                            type="button"
                            class="mobile-header-icon-btn"
                            @click=${this._createTask}
                            title=${this.t('create', {}, 'common')}
                        >
                            <platform-icon name="plus" size="18"></platform-icon>
                        </button>
                        <button
                            type="button"
                            class="mobile-header-icon-btn ${this._mobileHeaderSearch ? 'active' : ''}"
                            @click=${this._toggleMobileHeaderSearch}
                            title=${this.t('daily_notes_page.mobile_header_search')}
                        >
                            <platform-icon name="search" size="18"></platform-icon>
                        </button>
                    </div>
                </page-header>
            </div>
        `;
    }

    render() {
        const taskStatuses = this._statusColumns();
        const tasks = this._filteredTasks();
        const tasksByStatus = {};
        for (const s of taskStatuses) {
            tasksByStatus[s.id] = tasks.filter((task) => this._taskStatus(task) === s.id);
        }
        const n = taskStatuses.length;
        const boardGridStyleStr =
            n > 0 ? `grid-template-columns: ${this._boardGridTemplateColumns(taskStatuses)}` : 'grid-template-columns: minmax(0, 1fr)';
        const boardGridPlaceholderStr = 'grid-template-columns: minmax(0, 1fr)';
        const boardBlocked = this._boardStages !== null && taskStatuses.length === 0;

        return html`
            ${this._isMobile ? this._renderMobileTasksHeader() : nothing}
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
                        <button class="icon-btn-toolbar" type="button" @click=${() => this._reloadTasksPage()} title=${this.t('refresh', {}, 'common')}>
                            <platform-icon name="refresh" size="16"></platform-icon>
                        </button>
                        <button class="cta-btn" type="button" @click=${this._createTask}>${this.t('create', {}, 'common')}</button>
                    </div>
                </div>
                ${boardBlocked ? html`
                    <div class="empty" style="padding:var(--space-3) 0;">${this.t('tasks_page.board_blocked')}</div>
                ` : html`
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
                `}
            </div>

            <div class="board-shell ${this._boardBusy ? 'busy' : ''}">
                ${this._boardStages === null ? html`
                    <div class="board" style=${boardGridPlaceholderStr}>
                        <div class="empty">${this.t('loading', {}, 'common')}</div>
                    </div>
                ` : boardBlocked ? html`
                    <div class="board" style=${boardGridPlaceholderStr}>
                        <div class="empty">${this.t('tasks_page.board_blocked')}</div>
                    </div>
                ` : html`
                <div
                    class="board"
                    style=${boardGridStyleStr}
                    aria-busy=${this._boardBusy ? 'true' : 'false'}
                    aria-live=${this._boardBusy ? 'polite' : 'off'}
                >
                    ${taskStatuses.map((s) => {
                        const isActive = !this._isMobile || this._activeStatus === s.id;
                        const statusTasks = tasksByStatus[s.id];
                        const isCollapsedDesktop = !this._isMobile && this._isColumnCollapsed(s.id);
                        const dragOverHere = this._dragOverStatus === s.id;
                        const collapseIconName = isCollapsedDesktop ? 'chevron-right' : 'chevron-left';
                        const collapseLabel = isCollapsedDesktop
                            ? this.t('tasks_page.expand_column')
                            : this.t('tasks_page.collapse_column');
                        return html`
                            <section
                                class="column ${isActive ? 'mobile-active' : ''} ${isCollapsedDesktop ? 'collapsed' : ''} ${isCollapsedDesktop && dragOverHere ? 'dnd-target-col' : ''}"
                                @dragover=${this._onCollapsedColumnShellDragOver}
                                @dragleave=${this._onCollapsedColumnShellDragLeave}
                                @drop=${this._onCollapsedColumnShellDrop}
                                data-status-id=${s.id}
                            >
                                ${isCollapsedDesktop
                                    ? html`
                                    <div class="column-header">
                                        <button
                                            type="button"
                                            class="column-collapse-btn"
                                            title=${collapseLabel}
                                            aria-label=${collapseLabel}
                                            aria-expanded="false"
                                            @click=${(e) => this._toggleColumnCollapse(s.id, e)}
                                        >
                                            <platform-icon name="${collapseIconName}" size="16"></platform-icon>
                                        </button>
                                        <span class="column-title-vertical">${s.label}</span>
                                        <span class="column-count-vertical" aria-hidden="true">${statusTasks.length}</span>
                                    </div>
                                `
                                    : html`
                                    <div class="column-header">
                                        <div class="column-title">${s.label}</div>
                                        <div class="column-header-aside">
                                            <span class="column-count">${statusTasks.length}</span>
                                            ${!this._isMobile
                                                ? html`
                                                <button
                                                    type="button"
                                                    class="column-collapse-btn"
                                                    title=${collapseLabel}
                                                    aria-label=${collapseLabel}
                                                    aria-expanded="true"
                                                    @click=${(e) => this._toggleColumnCollapse(s.id, e)}
                                                >
                                                    <platform-icon name="${collapseIconName}" size="16"></platform-icon>
                                                </button>
                                            `
                                                : nothing}
                                        </div>
                                    </div>
                                `}
                                <div
                                    class="column-body ${!isCollapsedDesktop && dragOverHere ? 'dnd-target' : ''}"
                                    @dragover=${(e) => this._onColumnBodyDragOver(e, s.id, false)}
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
                                                    <button class="task-move-btn" type="button" @click=${(e) => { e.stopPropagation(); this._moveTask(task, this._nextStatus(this._taskStatus(task))); }}>
                                                        <platform-icon name="${this._nextStatusIcon()}" size="12"></platform-icon>
                                                        ${this._nextStatusLabel()}
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
                `}
            </div>
        `;
    }
}

customElements.define('crm-tasks-page', CRMTasksPage);
