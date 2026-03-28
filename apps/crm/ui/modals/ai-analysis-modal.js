import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { CRMStore } from '../store/crm.store.js';
import '@platform/lib/components/platform-icon.js';

export class AIAnalysisModal extends PlatformModal {
    static properties = {
        ...PlatformModal.properties,
        _suggestions: { state: true },
        _notes: { state: true },
        _currentNoteId: { state: true },
        _taskStates: { state: true },
        _taskDraft: { state: true },
        _saving: { state: true },
    };

    static styles = [
        PlatformModal.styles,
        css`
            :host {
                --modal-max-width: 1120px;
            }

            .root {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: var(--space-3);
                min-height: 520px;
            }

            .column {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                min-height: 0;
            }

            .block {
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-xl);
                background: var(--crm-surface-muted);
                padding: var(--space-3);
            }

            .ai-summary {
                background: var(--crm-selected-bg);
                border-color: var(--crm-selected-stroke);
            }

            .block-title {
                margin: 0 0 var(--space-2) 0;
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                font-size: var(--text-2xl);
                font-weight: 700;
                color: var(--text-primary);
            }

            .gradient-title {
                background: var(--accent-gradient);
                -webkit-background-clip: text;
                background-clip: text;
                -webkit-text-fill-color: transparent;
            }

            .summary-text {
                margin: 0;
                color: var(--text-primary);
                line-height: 1.45;
                font-size: var(--text-base);
            }

            .chips {
                margin-top: var(--space-3);
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
            }

            .chip {
                display: inline-flex;
                align-items: center;
                gap: 6px;
                font-size: var(--text-xs);
                padding: 4px 10px;
                border-radius: var(--radius-full);
                border: 1px solid var(--crm-stroke);
                background: var(--crm-surface-elevated);
            }

            .tasks-wrap {
                display: flex;
                flex-direction: column;
                min-height: 0;
                flex: 1;
            }

            .tasks-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                max-height: 220px;
                overflow: auto;
                margin-bottom: var(--space-3);
            }

            .task-row {
                display: grid;
                grid-template-columns: auto 1fr auto;
                align-items: center;
                gap: var(--space-2);
                color: var(--text-secondary);
            }

            .task-row.done {
                color: var(--text-tertiary);
                text-decoration: line-through;
            }

            .task-remove {
                border: none;
                background: transparent;
                color: var(--text-tertiary);
                width: 20px;
                height: 20px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                cursor: pointer;
            }

            .task-input-wrap {
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-full);
                background: var(--crm-surface-elevated);
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: 0 var(--space-3);
                min-height: 40px;
            }

            .task-input {
                border: none;
                background: transparent;
                outline: none;
                color: var(--text-primary);
                width: 100%;
                font-size: var(--text-sm);
            }

            .connections-title {
                margin: 0 0 var(--space-3) 0;
                font-size: 40px;
                line-height: 1.1;
                font-weight: 700;
                color: var(--text-primary);
            }

            .connections-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                overflow: auto;
            }

            .connection-card {
                border-radius: var(--radius-xl);
                padding: var(--space-2) var(--space-3);
                display: flex;
                align-items: center;
                gap: var(--space-2);
            }

            .connection-card.blue {
                background: rgba(153, 166, 249, 0.3);
            }

            .connection-card.yellow {
                background: rgba(250, 209, 122, 0.34);
            }

            .connection-card.orange {
                background: rgba(255, 154, 118, 0.28);
            }

            .connection-avatar {
                width: 48px;
                height: 48px;
                border-radius: var(--radius-md);
                background: var(--crm-surface-elevated);
                border: 1px solid var(--crm-stroke);
                display: flex;
                align-items: center;
                justify-content: center;
                color: var(--text-secondary);
            }

            .connection-main {
                flex: 1;
                min-width: 0;
            }

            .connection-name {
                font-weight: 600;
                color: var(--text-primary);
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }

            .connection-subtitle {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                margin-top: 2px;
            }

            .score-track {
                height: 12px;
                border-radius: var(--radius-full);
                background: rgba(34, 34, 34, 0.08);
                margin-top: var(--space-2);
                position: relative;
                overflow: hidden;
            }

            .score-fill {
                height: 100%;
                border-radius: inherit;
            }

            .score-fill.blue {
                background: #8e9bf7;
            }

            .score-fill.yellow {
                background: #f0c35f;
            }

            .score-fill.orange {
                background: #f78d61;
            }

            .score-label {
                position: absolute;
                inset: 0;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: var(--text-xs);
                color: var(--text-inverse);
            }

            .connection-actions {
                display: flex;
                flex-direction: column;
                align-items: flex-end;
                gap: var(--space-2);
            }

            .new-badge {
                font-size: var(--text-xs);
                border-radius: var(--radius-full);
                padding: 3px 10px;
                color: var(--text-primary);
            }

            .new-badge.blue {
                background: #8e9bf7;
                color: #fff;
            }

            .new-badge.yellow {
                background: #f0c35f;
            }

            .new-badge.orange {
                background: #f78d61;
                color: #fff;
            }

            .remove-connection {
                border: none;
                background: transparent;
                color: var(--text-tertiary);
                cursor: pointer;
                width: 22px;
                height: 22px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
            }

            .footer-actions {
                display: flex;
                gap: var(--space-2);
                justify-content: flex-end;
                width: 100%;
            }

            .btn {
                border: none;
                border-radius: var(--radius-full);
                min-height: 40px;
                padding: 0 var(--space-4);
                font-size: var(--text-base);
                cursor: pointer;
            }

            .btn-secondary {
                background: var(--crm-selected-bg);
                color: var(--text-secondary);
            }

            .btn-primary {
                background: var(--accent);
                color: var(--text-inverse);
            }

            .btn-primary:disabled {
                opacity: 0.6;
                cursor: not-allowed;
            }

            @media (max-width: 1024px) {
                .root {
                    grid-template-columns: 1fr;
                }
                .connections-title {
                    font-size: 30px;
                }
                .block-title {
                    font-size: var(--text-xl);
                }
            }
        `,
    ];

    constructor() {
        super();
        this.size = 'xl';
        this._suggestions = [];
        this._notes = [];
        this._currentNoteId = null;
        this._taskStates = [];
        this._taskDraft = '';
        this._saving = false;
        this._unsubscribe = null;
    }

    connectedCallback() {
        super.connectedCallback();
        this._initFromStore();
        this._unsubscribe = CRMStore.subscribe(() => {
            this._initFromStore();
        });
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._unsubscribe?.();
    }

    _initFromStore() {
        const state = CRMStore.state;
        this._suggestions = Array.isArray(state.ai.suggestions) ? state.ai.suggestions : [];
        this._notes = Array.isArray(state.entities.notes) ? state.entities.notes : [];
        this._currentNoteId = state.entities.currentNoteId;
        const taskSuggestions = this._getTaskSuggestions();
        const currentDoneMap = new Map(this._taskStates.map((task) => [task.id, task.done]));
        this._taskStates = taskSuggestions.map((task) => ({
            id: this._getTaskId(task),
            name: this._getTaskName(task),
            done: this._getTaskDoneState(currentDoneMap, task),
        }));
    }

    _getTaskId(task) {
        if (typeof task.entity_id === 'string' && task.entity_id.length > 0) {
            return task.entity_id;
        }
        if (typeof task.name === 'string' && task.name.length > 0) {
            return task.name;
        }
        throw new Error('Task suggestion requires entity_id or name');
    }

    _getTaskName(task) {
        if (typeof task.name === 'string' && task.name.length > 0) {
            return task.name;
        }
        return 'Задача';
    }

    _getTaskDoneState(currentDoneMap, task) {
        const taskId = this._getTaskId(task);
        const doneState = currentDoneMap.get(taskId);
        return doneState === true;
    }

    _getCurrentNote() {
        const note = this._notes.find((entry) => entry.entity_id === this._currentNoteId);
        return note === undefined ? null : note;
    }

    _getTaskSuggestions() {
        return this._suggestions.filter((item) => item.entity_type === 'task');
    }

    _getConnectionSuggestions() {
        return this._suggestions.filter((item) => item.entity_type !== 'task');
    }

    _onToggleTask(taskId) {
        this._taskStates = this._taskStates.map((task) => (
            task.id === taskId ? { ...task, done: !task.done } : task
        ));
    }

    _onRemoveTask(taskId) {
        this._taskStates = this._taskStates.filter((task) => task.id !== taskId);
    }

    _onTaskDraftInput(event) {
        this._taskDraft = event.target.value;
    }

    _onTaskDraftKeydown(event) {
        if (event.key !== 'Enter') {
            return;
        }
        const value = this._taskDraft.trim();
        if (!value) {
            return;
        }
        const id = `${Date.now()}-${value}`;
        this._taskStates = [...this._taskStates, { id, name: value, done: false }];
        this._taskDraft = '';
    }

    _onRemoveConnection(name) {
        this._suggestions = this._suggestions.filter((item) => item.name !== name);
    }

    _buildSummaryTags() {
        const selected = this._suggestions.slice(0, 2);
        return selected.map((item) => {
            if (typeof item.name === 'string' && item.name.length > 0) {
                return item.name;
            }
            if (typeof item.entity_type === 'string' && item.entity_type.length > 0) {
                return item.entity_type;
            }
            return 'Entity';
        });
    }

    _getScoreValue(item) {
        const raw = item.dedup_confidence;
        if (typeof raw === 'number' && Number.isFinite(raw)) {
            return Math.max(0, Math.min(100, Math.round(raw * 100)));
        }
        return 80;
    }

    _getConnectionTheme(index) {
        if (index % 3 === 0) {
            return 'blue';
        }
        if (index % 3 === 1) {
            return 'yellow';
        }
        return 'orange';
    }

    renderHeader() {
        return html`
            <span class="gradient-title" style="display:inline-flex;align-items:center;gap:8px;">
                <platform-icon name="sparkle" size="16"></platform-icon>
                AI-анализ
            </span>
        `;
    }

    renderBody() {
        const note = this._getCurrentNote();
        const noteText = note && typeof note.description === 'string' && note.description.length > 0
            ? note.description
            : 'Выберите заметку и запустите AI анализ.';
        const tags = this._buildSummaryTags();
        const connections = this._getConnectionSuggestions();

        return html`
            <div class="root">
                <section class="column">
                    <article class="block ai-summary">
                        <h3 class="block-title gradient-title">
                            <platform-icon name="sparkle" size="15"></platform-icon>
                            AI-summary
                        </h3>
                        <p class="summary-text">${noteText}</p>
                        <div class="chips">
                            ${tags.map((tag) => html`
                                <span class="chip">
                                    <platform-icon name="doc-detail" size="11"></platform-icon>
                                    ${tag}
                                </span>
                            `)}
                        </div>
                    </article>

                    <article class="block tasks-wrap">
                        <h3 class="block-title">Предложенные задачи</h3>
                        <div class="tasks-list">
                            ${this._taskStates.map((task) => html`
                                <label class="task-row ${task.done ? 'done' : ''}">
                                    <input type="checkbox" .checked=${task.done} @change=${() => this._onToggleTask(task.id)} />
                                    <span>${task.name}</span>
                                    <button class="task-remove" type="button" @click=${() => this._onRemoveTask(task.id)}>
                                        <platform-icon name="close" size="12"></platform-icon>
                                    </button>
                                </label>
                            `)}
                        </div>
                        <label class="task-input-wrap">
                            <platform-icon name="sparkle" size="12"></platform-icon>
                            <input
                                class="task-input"
                                type="text"
                                placeholder="Введите задачу + Enter"
                                .value=${this._taskDraft}
                                @input=${this._onTaskDraftInput}
                                @keydown=${this._onTaskDraftKeydown}
                            />
                        </label>
                    </article>
                </section>

                <section class="column">
                    <h3 class="connections-title">Выявленные связи</h3>
                    <div class="connections-list">
                        ${connections.map((item, index) => {
                            const theme = this._getConnectionTheme(index);
                            const score = this._getScoreValue(item);
                            return html`
                                <article class="connection-card ${theme}">
                                    <div class="connection-avatar">
                                        <platform-icon name="user" size="24"></platform-icon>
                                    </div>
                                    <div class="connection-main">
                                        <div class="connection-name">${this._getConnectionName(item)}</div>
                                        <div class="connection-subtitle">${this._getConnectionSubtitle(item)}</div>
                                        <div class="score-track">
                                            <div class="score-fill ${theme}" style="width:${score}%;"></div>
                                            <div class="score-label">Score - ${score}%</div>
                                        </div>
                                    </div>
                                    <div class="connection-actions">
                                        <span class="new-badge ${theme}">New</span>
                                        <button class="remove-connection" type="button" @click=${() => this._onRemoveConnection(item.name)}>
                                            <platform-icon name="close" size="12"></platform-icon>
                                        </button>
                                    </div>
                                </article>
                            `;
                        })}
                    </div>
                </section>
            </div>
        `;
    }

    async _onSave() {
        this._saving = true;
        const crmApi = this.services.get('crmApi');
        await CRMStore.confirmAllSuggestions(crmApi);
        this._saving = false;
        this.dispatchEvent(new CustomEvent('saved'));
        this.close();
    }

    _getConnectionName(item) {
        if (typeof item.name === 'string' && item.name.length > 0) {
            return item.name;
        }
        if (typeof item.entity_type === 'string' && item.entity_type.length > 0) {
            return item.entity_type;
        }
        return 'Связь';
    }

    _getConnectionSubtitle(item) {
        if (typeof item.entity_subtype === 'string' && item.entity_subtype.length > 0) {
            return item.entity_subtype;
        }
        if (typeof item.entity_type === 'string' && item.entity_type.length > 0) {
            return item.entity_type;
        }
        return 'Объект';
    }

    renderFooter() {
        return html`
            <div class="footer-actions">
                <button class="btn btn-secondary" type="button" @click=${() => this.close()}>К заметке</button>
                <button class="btn btn-primary" type="button" ?disabled=${this._saving} @click=${this._onSave}>
                    ${this._saving ? 'Сохранение...' : 'Сохранить'}
                </button>
            </div>
        `;
    }
}

customElements.define('ai-analysis-modal', AIAnalysisModal);
