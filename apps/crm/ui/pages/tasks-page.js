import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { resolveObjectName } from '@platform/lib/utils/entity-ref.js';
import { CRMStore } from '../store/crm.store.js';
import '../modals/entity-modal.js';
import '@platform/lib/components/platform-icon.js';

const TASK_STATUS = ['todo', 'in_progress', 'done'];

export class TasksPage extends PlatformElement {
    static properties = {
        _tasks: { state: true },
        _loading: { state: true },
        _filter: { state: true },
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
                background: var(--crm-surface);
                border: 1px solid var(--crm-stroke-strong);
                border-radius: var(--radius-2xl);
                overflow: hidden;
            }

            .toolbar {
                display: flex;
                justify-content: space-between;
                align-items: center;
                gap: var(--space-3);
                padding: var(--space-4);
                border-bottom: 1px solid var(--crm-stroke);
                background: var(--crm-surface-tint);
                flex-wrap: wrap;
            }

            .title {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                font-size: var(--text-base);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }

            .toolbar-actions {
                display: flex;
                align-items: center;
                gap: var(--space-2);
            }

            .search {
                min-width: 220px;
                padding: var(--space-2) var(--space-3);
                background: var(--crm-surface-muted);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-lg);
                color: var(--text-primary);
                font-size: var(--text-sm);
            }

            .search:focus {
                outline: none;
                border-color: var(--crm-selected-stroke);
            }

            .board {
                flex: 1;
                min-height: 0;
                display: grid;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                gap: var(--space-3);
                padding: var(--space-4);
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
                font-weight: var(--font-semibold);
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
            }

            .task-card {
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-md);
                background: var(--crm-surface);
                padding: var(--space-3);
                display: grid;
                gap: var(--space-2);
            }

            .task-name {
                font-size: var(--text-sm);
                color: var(--text-primary);
                font-weight: var(--font-medium);
                background: transparent;
                border: none;
                padding: 0;
                text-align: left;
                cursor: pointer;
            }

            .task-meta {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }

            .task-actions {
                display: flex;
                gap: var(--space-2);
                flex-wrap: wrap;
            }

            .empty {
                display: flex;
                align-items: center;
                justify-content: center;
                flex-direction: column;
                gap: var(--space-2);
                color: var(--text-tertiary);
                text-align: center;
                padding: var(--space-6);
            }

            @media (max-width: 1023px) {
                .board {
                    grid-template-columns: 1fr;
                }
            }

            @media (max-width: 767px) {
                :host {
                    border: none;
                    border-radius: 0;
                }

                .toolbar {
                    padding: var(--space-3);
                }

                .search {
                    min-width: 0;
                    width: 100%;
                }

                .toolbar-actions {
                    width: 100%;
                }

                .board {
                    padding: var(--space-3);
                }
            }
        `,
    ];

    constructor() {
        super();
        this._tasks = [];
        this._loading = false;
        this._filter = '';
    }

    async firstUpdated() {
        await this._loadTasks();
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

    async _createTask() {
        const crmApi = this.crmApi;
        const namespaceName = resolveObjectName(CRMStore.state.namespaces.current, null);
        await crmApi.createEntity({
            entity_type: 'task',
            name: 'Новая задача',
            description: '',
            namespace: namespaceName || 'default',
            priority: 'medium',
            attributes: { status: 'todo' },
        });
        await this._loadTasks();
        this.success('Задача создана');
    }

    _taskStatus(task) {
        const status = task.attributes?.status;
        if (TASK_STATUS.includes(status)) {
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

    _columnTitle(status) {
        if (status === 'todo') {
            return 'К выполнению';
        }
        if (status === 'in_progress') {
            return 'В работе';
        }
        return 'Готово';
    }

    _nextStatus(status) {
        if (status === 'todo') {
            return 'in_progress';
        }
        if (status === 'in_progress') {
            return 'done';
        }
        return 'todo';
    }

    _nextStatusLabel(status) {
        if (status === 'todo') {
            return 'В работу';
        }
        if (status === 'in_progress') {
            return 'Завершить';
        }
        return 'Вернуть в todo';
    }

    render() {
        const tasks = this._filteredTasks();
        const tasksByStatus = {
            todo: tasks.filter((task) => this._taskStatus(task) === 'todo'),
            in_progress: tasks.filter((task) => this._taskStatus(task) === 'in_progress'),
            done: tasks.filter((task) => this._taskStatus(task) === 'done'),
        };

        return html`
            <div class="toolbar">
                <div class="title">
                    <platform-icon name="checklist" size="18"></platform-icon>
                    <span>Задачи</span>
                </div>
                <div class="toolbar-actions">
                    <input
                        class="search"
                        type="text"
                        placeholder="Поиск задач..."
                        .value=${this._filter}
                        @input=${(event) => {
                            this._filter = event.target.value;
                        }}
                    />
                    <button class="btn btn-secondary" type="button" @click=${this._loadTasks}>
                        Обновить
                    </button>
                    <button class="btn btn-primary" type="button" @click=${this._createTask}>
                        Создать задачу
                    </button>
                </div>
            </div>

            <div class="board">
                ${TASK_STATUS.map((status) => html`
                    <section class="column">
                        <div class="column-header">
                            <div class="column-title">${this._columnTitle(status)}</div>
                            <div class="column-count">${tasksByStatus[status].length}</div>
                        </div>
                        <div class="column-body">
                            ${this._loading ? html`
                                <div class="empty">Загрузка задач...</div>
                            ` : tasksByStatus[status].length === 0 ? html`
                                <div class="empty">Нет задач</div>
                            ` : tasksByStatus[status].map((task) => {
                                const nextStatus = this._nextStatus(status);
                                return html`
                                    <article class="task-card">
                                        <button class="task-name" type="button" @click=${() => this._openTask(task.entity_id)}>
                                            ${task.name}
                                        </button>
                                        <div class="task-meta">
                                            <span>${task.priority || 'medium'}</span>
                                            <span>${task.due_date || 'без дедлайна'}</span>
                                        </div>
                                        <div class="task-actions">
                                            <button class="btn btn-secondary" type="button" @click=${() => this._moveTask(task, nextStatus)}>
                                                ${this._nextStatusLabel(status)}
                                            </button>
                                        </div>
                                    </article>
                                `;
                            })}
                        </div>
                    </section>
                `)}
            </div>
        `;
    }
}

customElements.define('tasks-page', TasksPage);
