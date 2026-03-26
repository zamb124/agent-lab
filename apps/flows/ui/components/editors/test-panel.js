/**
 * TestPanel - панель тестирования нод с Input State и Result
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

export class TestPanel extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
            }
            
            .test-section {
                border-top: 1px solid var(--border-subtle);
                padding-top: var(--space-4);
            }
            
            .test-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                margin-bottom: var(--space-3);
            }
            
            .test-title {
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-secondary);
            }
            
            .test-actions {
                display: flex;
                gap: var(--space-2);
            }
            
            .test-btn {
                display: flex;
                align-items: center;
                gap: var(--space-1);
                padding: var(--space-2) var(--space-3);
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
                border: none;
                border-radius: var(--radius-md);
                cursor: pointer;
                transition: all var(--duration-fast) var(--easing-default);
            }
            
            .test-btn:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }

            .session-state-row {
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                gap: var(--space-2);
                margin-bottom: var(--space-3);
                font-size: var(--text-xs);
            }

            .session-state-label {
                color: var(--text-tertiary);
            }

            .session-state-select {
                flex: 1;
                min-width: 120px;
                padding: var(--space-1) var(--space-2);
                font-size: var(--text-xs);
                border-radius: var(--radius-sm);
                border: 1px solid var(--border-subtle);
                background: var(--glass-tint-subtle);
                color: var(--text-primary);
            }

            .session-state-btn {
                padding: var(--space-1) var(--space-2);
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
                color: var(--accent-text);
                background: var(--accent-bg);
                border: 1px solid var(--accent);
                border-radius: var(--radius-sm);
                cursor: pointer;
            }

            .session-state-btn:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }
            
            .btn-validate {
                color: var(--text-secondary);
                background: var(--glass-tint-subtle);
            }
            
            .btn-validate:hover:not(:disabled) {
                color: var(--text-primary);
                background: var(--glass-tint-medium);
            }
            
            .btn-execute {
                color: white;
                background: var(--accent);
            }
            
            .btn-execute:hover:not(:disabled) {
                background: var(--accent-hover);
            }
            
            .test-panels {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: var(--space-3);
            }
            
            :host(:not([expanded])) .test-panels {
                grid-template-columns: 1fr;
            }
            
            :host([hide-input-state]) .test-panels {
                grid-template-columns: 1fr;
            }
            
            @media (max-width: 768px) {
                .test-panels {
                    grid-template-columns: 1fr;
                }
            }
            
            .panel {
                display: flex;
                flex-direction: column;
            }
            
            .panel-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                margin-bottom: var(--space-2);
            }
            
            .panel-title {
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
                color: var(--text-secondary);
            }
            
            .panel-action {
                padding: var(--space-1);
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                background: none;
                border: none;
                cursor: pointer;
            }
            
            .panel-action:hover {
                color: var(--text-primary);
            }
            
            .result-meta {
                display: flex;
                align-items: center;
                gap: var(--space-2);
            }
            
            .result-duration {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
            
            .result-content {
                flex: 1;
                min-height: 150px;
                max-height: 300px;
                padding: var(--space-3);
                font-family: var(--font-mono);
                font-size: var(--text-xs);
                line-height: 1.5;
                color: var(--text-primary);
                background: var(--bg-secondary);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                overflow: auto;
            }
            
            .result-placeholder {
                color: var(--text-tertiary);
            }
            
            .result-loading {
                color: var(--text-secondary);
            }
            
            .result-success {
                color: var(--success);
            }
            
            .result-label {
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
                color: var(--text-secondary);
                margin-bottom: var(--space-2);
            }
            
            .result-content {
                color: var(--text-primary);
                white-space: pre-wrap;
                word-break: break-word;
            }
            
            .result-error {
                color: var(--error);
            }
            
            .diff-view {
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
            }
            
            .diff-item {
                display: flex;
                align-items: flex-start;
                gap: var(--space-2);
                padding: var(--space-1);
                border-radius: var(--radius-sm);
            }
            
            .diff-added {
                background: var(--success-bg);
            }
            
            .diff-removed {
                background: var(--error-bg);
            }
            
            .diff-modified {
                background: var(--warning-bg);
            }
            
            .diff-icon {
                font-weight: bold;
                min-width: 12px;
            }
            
            .diff-added .diff-icon { color: var(--success); }
            .diff-removed .diff-icon { color: var(--error); }
            .diff-modified .diff-icon { color: var(--warning); }
            
            .diff-path {
                color: var(--text-secondary);
            }
            
            .diff-old {
                text-decoration: line-through;
                color: var(--error);
            }
            
            .diff-new {
                color: var(--success);
            }
        `
    ];

    static properties = {
        inputState: { type: Object, attribute: 'input-state' },
        defaultInputState: { type: Object },
        flowId: { type: String, attribute: 'flow-id' },
        loading: { type: Boolean },
        result: { type: Object },
        showFullState: { type: Boolean, attribute: 'show-full-state' },
        expanded: { type: Boolean, reflect: true },
        hideInputState: { type: Boolean, attribute: 'hide-input-state', reflect: true },
        _sessionList: { state: true },
        _sessionLoading: { state: true },
        _pickedSessionId: { state: true },
    };

    constructor() {
        super();
        this.inputState = { content: '', messages: [], variables: {} };
        this.defaultInputState = null;
        this.flowId = '';
        this.loading = false;
        this.result = null;
        this.showFullState = false;
        this.expanded = false;
        this.hideInputState = false;
        this._sessionList = [];
        this._sessionLoading = false;
        this._pickedSessionId = '';
    }

    getInputState() {
        const editor = this.shadowRoot.querySelector('json-field-editor');
        if (editor) {
            return editor.getParsedValue();
        }
        return this.inputState;
    }

    setInputState(state) {
        this.inputState = state;
        const editor = this.shadowRoot.querySelector('json-field-editor');
        if (editor) {
            editor.setValue(state);
        }
    }

    setResult(result) {
        this.result = result;
        this.loading = false;
    }

    setLoading(loading) {
        this.loading = loading;
        if (loading) {
            this.result = null;
        }
    }

    resetInputState(override) {
        let base;
        if (override !== undefined && override !== null) {
            base = structuredClone(override);
        } else if (this.defaultInputState && typeof this.defaultInputState === 'object') {
            base = structuredClone(this.defaultInputState);
        } else {
            base = { content: '', messages: [], variables: {} };
        }
        this.setInputState(base);
    }

    _onValidate() {
        this.emit('validate', { state: this.getInputState() });
    }

    _onExecute() {
        this.emit('execute', { state: this.getInputState() });
    }

    _onResetState() {
        this.resetInputState();
    }

    updated(changedProperties) {
        super.updated(changedProperties);
        if (changedProperties.has('flowId') && this.flowId) {
            this._loadSessionsForPicker();
        }
    }

    async _loadSessionsForPicker() {
        if (!this.flowId) {
            this._sessionList = [];
            return;
        }
        this._sessionLoading = true;
        try {
            const sessions = await this.a2a.getSessions(this.flowId, { limit: 100 });
            this._sessionList = sessions;
        } catch (err) {
            this.error(`Список сессий: ${err.message}`);
        } finally {
            this._sessionLoading = false;
        }
    }

    _onSessionSelect(e) {
        this._pickedSessionId = e.target.value;
    }

    async _onApplySessionState() {
        const sessionId = this._pickedSessionId?.trim();
        if (!sessionId) {
            this.error('Выберите сессию');
            return;
        }
        const state = await this.a2a.getSessionState(sessionId);
        this.setInputState(state);
    }

    _toggleView() {
        this.showFullState = !this.showFullState;
    }

    _renderResult() {
        if (this.loading) {
            return html`<div class="result-loading">Выполнение...</div>`;
        }
        
        if (!this.result) {
            return html`<div class="result-placeholder">Нажмите Execute для запуска</div>`;
        }
        
        if (this.result.error) {
            return html`<div class="result-error">${this.result.error}</div>`;
        }
        
        if (this.result.success === false) {
            return html`<div class="result-error">${this.result.error || 'Ошибка выполнения'}</div>`;
        }
        
        if (this.showFullState && this.result.output_state) {
            return html`<pre>${JSON.stringify(this.result.output_state, null, 2)}</pre>`;
        }
        
        // Сначала проверяем diff - он главнее
        if (this.result.diff && this.result.diff.length > 0) {
            return this._renderDiff(this.result.diff);
        }
        
        // Если diff пустой, но есть response - показываем его
        if (this.result.output_state?.response) {
            return html`
                <div class="result-success">
                    <div class="result-label">Ответ:</div>
                    <div class="result-content">${this.result.output_state.response}</div>
                </div>
            `;
        }
        
        if (this.result.valid !== undefined) {
            return html`<div class="result-success">Конфигурация валидна</div>`;
        }
        
        return html`<div class="result-success">Выполнено успешно</div>`;
    }

    _renderDiff(diff) {
        if (!diff || diff.length === 0) {
            return html`<div class="result-success">State не изменился</div>`;
        }
        
        return html`
            <div class="diff-view">
                ${diff.map(item => {
                    const icon = item.change_type === 'added' ? '+' 
                        : item.change_type === 'removed' ? '-' : '~';
                    const oldVal = item.old_value !== null ? JSON.stringify(item.old_value) : 'null';
                    const newVal = item.new_value !== null ? JSON.stringify(item.new_value) : 'null';
                    
                    return html`
                        <div class="diff-item diff-${item.change_type}">
                            <span class="diff-icon">${icon}</span>
                            <span class="diff-path">${item.path}</span>
                            ${item.change_type === 'added' 
                                ? html`<span class="diff-new">${newVal}</span>`
                                : item.change_type === 'removed'
                                    ? html`<span class="diff-old">${oldVal}</span>`
                                    : html`<span class="diff-old">${oldVal}</span> → <span class="diff-new">${newVal}</span>`
                            }
                        </div>
                    `;
                })}
            </div>
        `;
    }

    renderInputStatePanel() {
        return html`
            <div class="panel">
                <div class="panel-header">
                    <span class="panel-title">Input State (JSON)</span>
                    <button 
                        type="button" 
                        class="panel-action"
                        @click=${this._onResetState}
                    >↺ Сбросить</button>
                </div>
                ${this.flowId ? html`
                    <div class="session-state-row">
                        <label class="session-state-label">Сессия</label>
                        <select
                            class="session-state-select"
                            name="session_pick"
                            .value=${this._pickedSessionId}
                            @change=${this._onSessionSelect}
                            ?disabled=${this._sessionLoading}
                        >
                            <option value="">${this._sessionLoading ? 'Загрузка…' : '— выберите —'}</option>
                            ${(this._sessionList || []).map(
                                (s) => html`<option value=${s.session_id}>${s.session_id}</option>`
                            )}
                        </select>
                        <button
                            type="button"
                            class="session-state-btn"
                            ?disabled=${this._sessionLoading}
                            @click=${this._onApplySessionState}
                        >Подставить state</button>
                        <button
                            type="button"
                            class="panel-action"
                            @click=${() => this._loadSessionsForPicker()}
                            title="Обновить список"
                        >Обновить</button>
                    </div>
                ` : ''}
                <json-field-editor
                    .value=${JSON.stringify(this.inputState, null, 2)}
                    min-height="150"
                    placeholder='{"content": "", "messages": []}'
                ></json-field-editor>
            </div>
        `;
    }

    render() {
        return html`
            <div class="test-section">
                <div class="test-header">
                    <span class="test-title">Тестирование</span>
                    <div class="test-actions">
                        <button 
                            type="button" 
                            class="test-btn btn-validate"
                            ?disabled=${this.loading}
                            @click=${this._onValidate}
                        >
                            Validate
                        </button>
                        <button 
                            type="button" 
                            class="test-btn btn-execute"
                            ?disabled=${this.loading}
                            @click=${this._onExecute}
                        >
                            ${this.loading ? 'Выполнение...' : 'Execute'}
                        </button>
                    </div>
                </div>
                
                <div class="test-panels">
                    ${!this.hideInputState ? this.renderInputStatePanel() : ''}
                    
                    <div class="panel">
                        <div class="panel-header">
                            <span class="panel-title">Результат</span>
                            <div class="result-meta">
                                ${this.result && this.result.duration_ms ? html`
                                    <span class="result-duration">${this.result.duration_ms}ms</span>
                                ` : ''}
                                ${this.result && this.result.output_state ? html`
                                    <button 
                                        type="button" 
                                        class="panel-action"
                                        @click=${this._toggleView}
                                    >${this.showFullState ? 'Diff' : 'Full'}</button>
                                ` : ''}
                            </div>
                        </div>
                        <div class="result-content">
                            ${this._renderResult()}
                        </div>
                    </div>
                </div>
            </div>
        `;
    }
}

customElements.define('test-panel', TestPanel);

