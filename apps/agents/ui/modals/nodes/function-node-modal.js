/**
 * FunctionNodeModal - модалка редактирования Function Node
 */
import { html, css } from 'lit';
import { BaseNodeModal } from './base-node-modal.js';

export class FunctionNodeModal extends BaseNodeModal {
    static styles = [
        BaseNodeModal.styles,
        css`
            .code-section {
                flex: 1;
                display: flex;
                flex-direction: column;
            }
            
            .code-mode-row {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                margin-bottom: var(--space-3);
            }
            
            .code-mode-row .form-select {
                width: auto;
            }
            
            .function-path-section {
                margin-bottom: var(--space-3);
            }
            
            .help-section {
                padding: var(--space-3);
                background: var(--glass-tint-subtle);
                border-radius: var(--radius-md);
                font-size: var(--text-xs);
            }
            
            .help-section h4 {
                margin: 0 0 var(--space-2);
                color: var(--text-secondary);
            }
            
            .help-section ul {
                margin: 0;
                padding-left: var(--space-4);
            }
            
            .help-section li {
                margin-bottom: var(--space-1);
                color: var(--text-tertiary);
            }
            
            .help-section code {
                color: var(--accent);
                background: var(--glass-tint-medium);
                padding: 1px 4px;
                border-radius: 3px;
            }
            
            .code-mode-toggle {
                display: flex;
                gap: 0;
                background: var(--glass-tint-subtle);
                border-radius: var(--radius-md);
                padding: 2px;
                border: 1px solid var(--border-subtle);
            }
            
            .code-mode-btn {
                padding: var(--space-2) var(--space-3);
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-secondary);
                background: transparent;
                border: none;
                border-radius: calc(var(--radius-md) - 2px);
                cursor: pointer;
                transition: all var(--duration-fast) var(--easing-default);
                flex: 1;
                text-align: center;
            }
            
            .code-mode-btn:hover {
                color: var(--text-primary);
                background: var(--glass-tint-medium);
            }
            
            .code-mode-btn.active {
                background: var(--accent);
                color: white;
                box-shadow: var(--shadow-sm);
            }
        `
    ];

    static properties = {
        ...BaseNodeModal.properties,
        codeMode: { type: String },
        functionPath: { type: String },
    };

    constructor() {
        super();
        this.codeMode = 'INLINE_CODE';
        this.functionPath = '';
    }

    getNodeType() {
        return 'function';
    }

    getModalTitle() {
        return 'Function Node';
    }

    showModal(nodeId = '', config = {}) {
        super.showModal(nodeId, config);
        
        if (config.function && !config.code) {
            this.codeMode = 'CODE_REFERENCE';
            this.functionPath = config.function;
        } else {
            this.codeMode = 'INLINE_CODE';
            this.functionPath = '';
        }
    }

    _onCodeModeChange(mode) {
        this.codeMode = mode;
    }

    _buildConfig() {
        const name = this.shadowRoot.querySelector('[name="name"]')?.value?.trim() || '';
        
        const config = {
            type: 'function',
        };
        
        if (name) {
            config.name = name;
        }
        
        if (this.codeMode === 'CODE_REFERENCE') {
            const functionPath = this.shadowRoot.querySelector('[name="function_path"]')?.value?.trim();
            if (!functionPath) {
                throw new Error('Укажите путь к функции');
            }
            config.function = functionPath;
        } else {
            const codeEditor = this.shadowRoot.querySelector('python-code-editor');
            const code = codeEditor?.getValue()?.trim();
            if (!code) {
                throw new Error('Введите код функции');
            }
            config.code = code;
        }
        
        return this._applyStateSettings(config);
    }

    renderBody() {
        const config = this.nodeConfig;
        
        return html`
            <div class="form-layout">
                <div class="form-sidebar">
                    <div class="form-group">
                        <label class="form-label">Node ID *</label>
                        <input 
                            type="text" 
                            name="node_id"
                            class="form-input ${this.isEdit ? 'readonly' : ''}"
                            .value=${this.nodeId || ''}
                            ?readonly=${this.isEdit}
                            placeholder="my_function"
                            required
                        />
                    </div>
                    
                    <div class="form-group">
                        <label class="form-label">Имя</label>
                        <input 
                            type="text" 
                            name="name"
                            class="form-input"
                            .value=${config.name || ''}
                            placeholder="Классификатор"
                        />
                        <span class="form-hint">Используется для генерации Node ID</span>
                    </div>
                    
                    <div class="form-group">
                        <label class="form-label">Режим кода</label>
                        <div class="code-mode-toggle">
                            <button 
                                type="button"
                                class="code-mode-btn ${this.codeMode === 'INLINE_CODE' ? 'active' : ''}"
                                @click=${() => this._onCodeModeChange('INLINE_CODE')}
                            >
                                INLINE_CODE
                            </button>
                            <button 
                                type="button"
                                class="code-mode-btn ${this.codeMode === 'CODE_REFERENCE' ? 'active' : ''}"
                                @click=${() => this._onCodeModeChange('CODE_REFERENCE')}
                            >
                                CODE_REFERENCE
                            </button>
                        </div>
                    </div>
                    
                    ${this.codeMode === 'CODE_REFERENCE' ? html`
                        <div class="form-group function-path-section">
                            <label class="form-label">Function Path *</label>
                            <input 
                                type="text" 
                                name="function_path"
                                class="form-input"
                                .value=${this.functionPath}
                                placeholder="agents.my_agent.functions.my_func"
                            />
                            <span class="form-hint">Путь к функции в agents/&lt;agent&gt;/functions.py</span>
                        </div>
                    ` : ''}
                    
                    <div class="help-section">
                        <h4>Справка по API</h4>
                        <ul>
                            <li><code>async def run(state):</code> - основная функция</li>
                            <li><code>state["content"]</code> - текст от пользователя</li>
                            <li><code>state["response"] = "..."</code> - ответ пользователю</li>
                            <li><code>llm</code> - LLM клиент</li>
                            <li><code>context</code> - контекст выполнения</li>
                            <li><code>httpx</code> - HTTP клиент</li>
                        </ul>
                    </div>
                    
                    ${this.renderStateSettings()}
                </div>
                
                <div class="form-main">
                    <div class="code-section">
                        <div class="form-group" style="flex: 1;">
                            <label class="form-label">
                                ${this.codeMode === 'CODE_REFERENCE' ? 'Python Code (readonly)' : 'Python Code'}
                            </label>
                            <python-code-editor
                                .value=${config.code || ''}
                                ?readonly=${this.codeMode === 'CODE_REFERENCE'}
                                min-height="300"
                            ></python-code-editor>
                        </div>
                    </div>
                    
                    <test-panel
                        .inputState=${this._buildDefaultState()}
                        @validate=${this._onValidate}
                        @execute=${this._onExecute}
                    ></test-panel>
                </div>
            </div>
        `;
    }
}

customElements.define('function-node-modal', FunctionNodeModal);


