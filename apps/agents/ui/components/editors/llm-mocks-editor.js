/**
 * LLMMocksEditor - редактор мок-ответов для нод агента
 * Позволяет настраивать мок-ответы для любых нод (LLM, tools, API и т.д.)
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

export class LLMMocksEditor extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
            }
            
            .mocks-container {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }
            
            .mock-item {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                padding: var(--space-3);
                background: var(--glass-tint-subtle);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
            }
            
            .mock-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
            }
            
            .mock-number {
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-secondary);
            }
            
            .mock-actions {
                display: flex;
                gap: var(--space-2);
            }
            
            .node-input {
                flex: 1;
                padding: 4px 8px;
                font-size: var(--text-xs);
                color: var(--text-primary);
                background: var(--bg-primary);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-sm);
                outline: none;
            }
            
            .node-input:focus {
                border-color: var(--accent);
            }
            
            .node-input::placeholder {
                color: var(--text-tertiary);
            }
            
            .mock-type-select {
                padding: 4px 8px;
                font-size: var(--text-xs);
                color: var(--text-primary);
                background: var(--glass-bg-subtle);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-sm);
                cursor: pointer;
            }
            
            .remove-btn {
                padding: 4px 8px;
                font-size: var(--text-xs);
                color: var(--error);
                background: transparent;
                border: 1px solid var(--error);
                border-radius: var(--radius-sm);
                cursor: pointer;
                transition: all 0.2s ease;
            }
            
            .remove-btn:hover {
                background: var(--error);
                color: white;
            }
            
            .mock-textarea {
                width: 100%;
                min-height: 80px;
                padding: var(--space-2);
                font-size: var(--text-sm);
                font-family: var(--font-mono);
                color: var(--text-primary);
                background: var(--bg-primary);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                resize: vertical;
                outline: none;
            }
            
            .mock-textarea:focus {
                border-color: var(--accent);
            }
            
            .mock-textarea::placeholder {
                color: var(--text-tertiary);
            }
            
            .tool-fields {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }
            
            .tool-input {
                padding: var(--space-2);
                font-size: var(--text-sm);
                color: var(--text-primary);
                background: var(--bg-primary);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                outline: none;
            }
            
            .tool-input:focus {
                border-color: var(--accent);
            }
            
            .add-btn {
                display: flex;
                align-items: center;
                justify-content: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--accent);
                background: transparent;
                border: 1px dashed var(--accent);
                border-radius: var(--radius-md);
                cursor: pointer;
                transition: all 0.2s ease;
            }
            
            .add-btn:hover {
                background: var(--accent-bg);
            }
            
            .empty-state {
                padding: var(--space-6) var(--space-4);
                text-align: center;
                font-size: var(--text-sm);
                color: var(--text-tertiary);
            }
            
            .hint {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-top: var(--space-2);
            }
            
            .mock-label {
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
                color: var(--text-secondary);
                margin-bottom: var(--space-1);
            }
        `
    ];

    static properties = {
        mocks: { type: Array },
    };

    constructor() {
        super();
        this.mocks = [];
        this._mocksList = [];
    }

    updated(changed) {
        if (changed.has('mocks')) {
            this._mocksList = (this.mocks || []).map((m, i) => ({
                id: `mock-${i}-${Date.now()}`,
                ...m
            }));
        }
    }

    _addMock() {
        this._mocksList = [
            ...this._mocksList,
            {
                id: `mock-${Date.now()}`,
                node_id: '',
                type: 'text',
                content: ''
            }
        ];
        this._emitChange();
    }

    _removeMock(id) {
        this._mocksList = this._mocksList.filter(m => m.id !== id);
        this._emitChange();
    }

    _updateNodeId(id, nodeId) {
        this._mocksList = this._mocksList.map(m => 
            m.id === id ? { ...m, node_id: nodeId } : m
        );
        this._emitChange();
    }

    _updateMockType(id, type) {
        this._mocksList = this._mocksList.map(m => {
            if (m.id === id) {
                if (type === 'text') {
                    return { 
                        id: m.id,
                        node_id: m.node_id || '',
                        type, 
                        content: m.content || '' 
                    };
                } else if (type === 'tool_call') {
                    return { 
                        id: m.id,
                        node_id: m.node_id || '',
                        type, 
                        tool: m.tool || '', 
                        args: m.args || '{}' 
                    };
                } else {
                    return {
                        id: m.id,
                        node_id: m.node_id || '',
                        type,
                        response: m.response || '{}'
                    };
                }
            }
            return m;
        });
        this._emitChange();
    }

    _updateMockContent(id, content) {
        this._mocksList = this._mocksList.map(m => 
            m.id === id ? { ...m, content } : m
        );
        this._emitChange();
    }

    _updateMockResponse(id, response) {
        this._mocksList = this._mocksList.map(m => 
            m.id === id ? { ...m, response } : m
        );
        this._emitChange();
    }

    _updateMockTool(id, tool) {
        this._mocksList = this._mocksList.map(m => 
            m.id === id ? { ...m, tool } : m
        );
        this._emitChange();
    }

    _updateMockArgs(id, args) {
        this._mocksList = this._mocksList.map(m => 
            m.id === id ? { ...m, args } : m
        );
        this._emitChange();
    }

    _emitChange() {
        const value = this._mocksList.map(({ id, ...rest }) => rest);
        this.emit('change', { value });
    }

    getValue() {
        return this._mocksList.map(({ id, ...rest }) => rest);
    }

    render() {
        if (this._mocksList.length === 0) {
            return html`
                <div class="mocks-container">
                    <div class="empty-state">
                        Нет мок-ответов. Добавьте для тестирования без реальных вызовов нод.
                    </div>
                    <button class="add-btn" @click=${this._addMock}>
                        + Добавить мок-ответ
                    </button>
                    <div class="hint">
                        Укажите node_id ноды и её мок-ответ. Поддерживаются LLM, tools, API и другие ноды.
                    </div>
                </div>
            `;
        }

        return html`
            <div class="mocks-container">
                ${this._mocksList.map((mock, index) => html`
                    <div class="mock-item">
                        <div class="mock-header">
                            <span class="mock-number">Ответ ${index + 1}</span>
                            <input
                                class="node-input"
                                type="text"
                                placeholder="node_id (например: llm_node_1)"
                                .value=${mock.node_id || ''}
                                @input=${(e) => this._updateNodeId(mock.id, e.target.value)}
                            />
                            <div class="mock-actions">
                                <select 
                                    class="mock-type-select"
                                    .value=${mock.type}
                                    @change=${(e) => this._updateMockType(mock.id, e.target.value)}
                                >
                                    <option value="text">Text</option>
                                    <option value="tool_call">Tool Call</option>
                                    <option value="json">JSON</option>
                                </select>
                                <button 
                                    class="remove-btn"
                                    @click=${() => this._removeMock(mock.id)}
                                >
                                    Удалить
                                </button>
                            </div>
                        </div>
                        
                        ${mock.type === 'text' ? html`
                            <div>
                                <div class="mock-label">Текстовый ответ</div>
                                <textarea
                                    class="mock-textarea"
                                    placeholder="Текст ответа от ноды..."
                                    .value=${mock.content || ''}
                                    @input=${(e) => this._updateMockContent(mock.id, e.target.value)}
                                ></textarea>
                            </div>
                        ` : mock.type === 'tool_call' ? html`
                            <div class="tool-fields">
                                <div>
                                    <div class="mock-label">Имя инструмента</div>
                                    <input
                                        class="tool-input"
                                        type="text"
                                        placeholder="calculator"
                                        .value=${mock.tool || ''}
                                        @input=${(e) => this._updateMockTool(mock.id, e.target.value)}
                                    />
                                </div>
                                <div>
                                    <div class="mock-label">Аргументы (JSON)</div>
                                    <textarea
                                        class="mock-textarea"
                                        placeholder='{"x": 1, "y": 2}'
                                        .value=${mock.args || '{}'}
                                        @input=${(e) => this._updateMockArgs(mock.id, e.target.value)}
                                    ></textarea>
                                </div>
                            </div>
                        ` : html`
                            <div>
                                <div class="mock-label">JSON ответ ноды</div>
                                <textarea
                                    class="mock-textarea"
                                    placeholder='{"result": "mock_value", "status": "success"}'
                                    .value=${mock.response || '{}'}
                                    @input=${(e) => this._updateMockResponse(mock.id, e.target.value)}
                                ></textarea>
                            </div>
                        `}
                    </div>
                `)}
                
                <button class="add-btn" @click=${this._addMock}>
                    + Добавить еще
                </button>
            </div>
        `;
    }
}

customElements.define('llm-mocks-editor', LLMMocksEditor);


