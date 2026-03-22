/**
 * Модальное окно списка сессий с фильтрацией и просмотром деталей
 */
import { html, css } from 'lit';
import { repeat } from 'lit/directives/repeat.js';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { FlowsStore } from '../store/flows.store.js';
import { confirm } from './confirm-modal.js';

export class SessionsModal extends PlatformModal {
    static styles = [
        PlatformModal.styles,
        css`
            .filters {
                display: flex;
                gap: var(--space-3);
                align-items: center;
                padding-bottom: var(--space-3);
                border-bottom: 1px solid var(--glass-border-subtle);
            }
            
            .filter-label {
                font-size: var(--text-sm);
                color: var(--text-secondary);
            }
            
            .filter-select {
                flex: 1;
                max-width: 300px;
                padding: var(--space-2) var(--space-3);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                color: var(--text-primary);
                font-size: var(--text-sm);
                cursor: pointer;
            }
            
            .filter-select:focus {
                outline: none;
                border-color: var(--accent);
            }
            
            .sessions-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                overflow-y: auto;
                max-height: 500px;
                width: 100%;
            }
            
            .session-item {
                display: grid;
                grid-template-columns: 40px 1fr auto;
                align-items: start;
                gap: var(--space-3);
                padding: var(--space-3) var(--space-4);
                background: var(--glass-solid-subtle);
                border-radius: var(--radius-md);
                border: none;
                box-shadow: 0 1px 3px rgba(0,0,0,0.1);
                cursor: pointer;
                transition: all var(--duration-fast) var(--easing-default);
                width: 100%;
                box-sizing: border-box;
            }
            
            .session-item:hover {
                background: var(--glass-solid-medium);
                box-shadow: 0 2px 6px rgba(0,0,0,0.15);
            }
            
            .session-item.active {
                background: var(--accent-subtle);
                box-shadow: 0 2px 8px rgba(16, 185, 129, 0.25);
            }
            
            .session-icon {
                width: 40px;
                height: 40px;
                display: flex;
                align-items: center;
                justify-content: center;
                background: var(--glass-solid-medium);
                border-radius: var(--radius-md);
                color: var(--text-secondary);
                box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            }
            
            .session-info {
                flex: 1;
                min-width: 0;
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
                overflow: hidden;
            }
            
            .session-header {
                display: flex;
                align-items: center;
                gap: var(--space-2);
            }
            
            .session-flow {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--accent);
                background: var(--accent-subtle);
                padding: 2px 8px;
                border-radius: var(--radius-sm);
            }
            
            .session-user {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
            
            .session-first-message {
                font-size: var(--text-sm);
                color: var(--text-primary);
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            
            .session-meta {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
            
            .session-meta-item {
                display: flex;
                align-items: center;
                gap: var(--space-1);
            }
            
            .session-actions {
                display: flex;
                flex-direction: column;
                align-items: flex-end;
                gap: var(--space-2);
            }
            
            .session-btn {
                width: 32px;
                height: 32px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-sm);
                color: var(--text-secondary);
                background: var(--glass-solid-subtle);
                border: none;
                box-shadow: 0 1px 3px rgba(0,0,0,0.1);
                transition: all var(--duration-fast) var(--easing-default);
                cursor: pointer;
            }
            
            .session-btn:hover {
                background: var(--glass-solid-strong);
                color: var(--text-primary);
                box-shadow: 0 2px 6px rgba(0,0,0,0.15);
            }
            
            .session-btn.danger:hover {
                background: var(--error-bg);
                color: var(--error);
                box-shadow: 0 2px 6px rgba(239, 68, 68, 0.2);
            }
            
            .session-btn.primary {
                background: var(--accent);
                color: white;
            }
            
            .session-btn.primary:hover {
                background: var(--accent-hover);
            }
            
            .empty-state {
                text-align: center;
                padding: var(--space-8);
                color: var(--text-tertiary);
            }
            
            .loading {
                display: flex;
                justify-content: center;
                padding: var(--space-8);
            }
            
            .stats {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding-top: var(--space-2);
                border-top: 1px solid var(--glass-border-subtle);
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
        `
    ];

    static properties = {
        ...PlatformModal.properties,
        flowId: { type: String },
        currentSession: { type: String },
        sessions: { type: Array },
        flows: { type: Array },
        selectedFlowId: { type: String },
        loading: { type: Boolean },
    };

    constructor() {
        super();
        this.title = 'Сессии';
        this.size = 'xl';
        this.flowId = '';
        this.currentSession = '';
        this.sessions = [];
        this.flows = [];
        this.selectedFlowId = '';
        this.loading = false;
    }

    async showModal() {
        super.showModal();
        await this._loadFlows();
        await this._loadSessions();
    }

    async _loadFlows() {
        const list = await this.a2a.listFlows();
        this.flows = list || [];
    }

    async _loadSessions() {
        this.loading = true;
        this.sessions = await this.a2a.getSessions(this.selectedFlowId || null);
        this.loading = false;
    }

    _onFlowFilterChange(e) {
        this.selectedFlowId = e.target.value;
        this._loadSessions();
    }

    async _selectSession(session) {
        this.loading = true;
        
        const state = await this.a2a.getSessionState(session.session_id);
        const messages = state?.messages || [];
        const sessionTaskId = state?.task_id || null;
        
        FlowsStore.loadSession(session.session_id, messages, session.flow_id, sessionTaskId);
        
        this.loading = false;
        this.close();
    }

    async _deleteSession(sessionId, e) {
        e.stopPropagation();
        
        const confirmed = await confirm('Удалить эту сессию?', {
            title: 'Удаление сессии',
            confirmText: 'Удалить',
            variant: 'danger',
        });
        
        if (!confirmed) return;
        
        await this.a2a.deleteSession(this.selectedFlowId, sessionId);
        this.success('Сессия удалена');
        await this._loadSessions();
    }

    _formatDate(dateString) {
        if (!dateString) return '';
        const date = new Date(dateString);
        return date.toLocaleString('ru-RU', {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    }

    _truncate(text, maxLength = 60) {
        if (!text) return '';
        return text.length > maxLength ? text.substring(0, maxLength) + '...' : text;
    }

    _getFlowName(flowId) {
        const flow = this.flows.find(a => a.flow_id === flowId);
        return flow?.name || flowId;
    }

    renderBody() {
        if (this.loading) {
            return html`
                <div class="loading">
                    <platform-spinner variant="ai" size="48"></platform-spinner>
                </div>
            `;
        }

        return html`
            <div class="filters">
                <span class="filter-label">Flow:</span>
                <select 
                    class="filter-select" 
                    .value=${this.selectedFlowId}
                    @change=${this._onFlowFilterChange}
                >
                    <option value="">Все flows</option>
                    ${this.flows.map(flowItem => html`
                        <option value="${flowItem.flow_id}">${flowItem.name || flowItem.flow_id}</option>
                    `)}
                </select>
            </div>

            ${this.sessions.length === 0 ? html`
                <div class="empty-state">
                    <platform-icon name="folder" size="48"></platform-icon>
                    <p>Нет сохраненных сессий</p>
                </div>
            ` : html`
                <div class="sessions-list">
                    ${repeat(
                        this.sessions,
                        (s) => s.session_id || s.id,
                        (session) => html`
                            <div 
                                class="session-item ${session.session_id === this.currentSession ? 'active' : ''}"
                                @click=${() => this._selectSession(session)}
                            >
                                <div class="session-icon">
                                    <platform-icon name="chat" size="20"></platform-icon>
                                </div>
                                <div class="session-info">
                                    <div class="session-header">
                                        <span class="session-flow">${this._getFlowName(session.flow_id)}</span>
                                        <span class="session-user">user: ${session.user_id || 'anonymous'}</span>
                                    </div>
                                    <div class="session-first-message">
                                        ${this._truncate(session.first_message) || 'Нет сообщений'}
                                    </div>
                                    <div class="session-meta">
                                        <span class="session-meta-item">
                                            <platform-icon name="calendar" size="12"></platform-icon>
                                            ${this._formatDate(session.created_at)}
                                        </span>
                                        <span class="session-meta-item">
                                            <platform-icon name="chat" size="12"></platform-icon>
                                            ${session.message_count || 0} сообщений
                                        </span>
                                    </div>
                                </div>
                                <div class="session-actions">
                                    <button 
                                        class="session-btn primary" 
                                        @click=${(e) => { e.stopPropagation(); this._selectSession(session); }}
                                        title="Продолжить диалог"
                                    >
                                        <platform-icon name="play" size="16"></platform-icon>
                                    </button>
                                    <button 
                                        class="session-btn danger" 
                                        @click=${(e) => this._deleteSession(session.session_id, e)}
                                        title="Удалить"
                                    >
                                        <platform-icon name="delete" size="16"></platform-icon>
                                    </button>
                                </div>
                            </div>
                        `
                    )}
                </div>
                <div class="stats">
                    <span>Всего сессий: ${this.sessions.length}</span>
                </div>
            `}
        `;
    }
}

customElements.define('sessions-modal', SessionsModal);
