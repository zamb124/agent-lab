/**
 * CodeNodeModal - модалка редактирования Code Node
 * Универсальная нода для выполнения кода (Python, JavaScript, Go)
 */
import { html, css } from 'lit';
import { BaseNodeModal } from './base-node-modal.js';

export class CodeNodeModal extends BaseNodeModal {
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
        language: { type: String },
    };

    constructor() {
        super();
        this.codeMode = 'INLINE_CODE';
        this.language = 'python';
    }

    getNodeType() {
        return 'code';
    }

    getModalTitle() {
        return 'Code Node';
    }

    showModal(nodeId = '', config = {}) {
        super.showModal(nodeId, config);
        
        this.language = config.language || 'python';
        
        if (config.tool_id) {
            this.codeMode = 'TOOL_ID';
        } else if (config.function) {
            this.codeMode = 'CODE_REFERENCE';
        } else {
            this.codeMode = 'INLINE_CODE';
        }
    }

    _onCodeModeChange(mode) {
        this.codeMode = mode;
    }

    _buildConfig() {
        const name = this.shadowRoot.querySelector('[name="name"]')?.value?.trim() || '';
        const language = this.shadowRoot.querySelector('[name="language"]')?.value || 'python';
        
        const config = {
            type: 'code',
            language: language,
        };
        
        if (name) {
            config.name = name;
        }
        
        if (this.codeMode === 'TOOL_ID') {
            const toolId = this.shadowRoot.querySelector('[name="tool_id"]')?.value?.trim();
            if (!toolId) {
                throw new Error('Укажите Tool ID');
            }
            config.tool_id = toolId;
        } else if (this.codeMode === 'CODE_REFERENCE') {
            const functionPath = this.shadowRoot.querySelector('[name="function_path"]')?.value?.trim();
            if (!functionPath) {
                throw new Error('Укажите путь к функции');
            }
            config.function = functionPath;
        } else {
            const codeEditor = this.shadowRoot.querySelector('python-code-editor');
            const code = codeEditor?.getValue()?.trim();
            if (!code) {
                throw new Error('Введите код');
            }
            config.code = code;
        }
        
        // Args schema
        const argsSchemaEditor = this.shadowRoot.querySelector('json-field-editor[name="args_schema"]');
        if (argsSchemaEditor && argsSchemaEditor.isValid()) {
            const argsSchema = argsSchemaEditor.getParsedValue();
            if (argsSchema && Object.keys(argsSchema).length > 0) {
                config.args_schema = argsSchema;
            }
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
                            placeholder="my_code_node"
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
                    </div>
                    
                    <div class="form-group">
                        <label class="form-label">Язык</label>
                        <select name="language" class="form-input">
                            <option value="python" ?selected=${this.language === 'python'}>Python</option>
                            <option value="javascript" ?selected=${this.language === 'javascript'}>JavaScript</option>
                            <option value="go" ?selected=${this.language === 'go'}>Go</option>
                        </select>
                    </div>
                    
                    <div class="form-group">
                        <label class="form-label">Режим</label>
                        <div class="code-mode-toggle">
                            <button 
                                type="button"
                                class="code-mode-btn ${this.codeMode === 'INLINE_CODE' ? 'active' : ''}"
                                @click=${() => this._onCodeModeChange('INLINE_CODE')}
                            >Inline</button>
                            <button 
                                type="button"
                                class="code-mode-btn ${this.codeMode === 'CODE_REFERENCE' ? 'active' : ''}"
                                @click=${() => this._onCodeModeChange('CODE_REFERENCE')}
                            >Path</button>
                            <button 
                                type="button"
                                class="code-mode-btn ${this.codeMode === 'TOOL_ID' ? 'active' : ''}"
                                @click=${() => this._onCodeModeChange('TOOL_ID')}
                            >Tool</button>
                        </div>
                    </div>
                    
                    ${this.codeMode === 'TOOL_ID' ? html`
                        <div class="form-group">
                            <label class="form-label">Tool ID *</label>
                            <input 
                                type="text" 
                                name="tool_id"
                                class="form-input"
                                .value=${config.tool_id || ''}
                                placeholder="calculator, weather_api"
                            />
                            <span class="form-hint">Загрузка tool из реестра</span>
                        </div>
                    ` : this.codeMode === 'CODE_REFERENCE' ? html`
                        <div class="form-group function-path-section">
                            <label class="form-label">Function Path *</label>
                            <input 
                                type="text" 
                                name="function_path"
                                class="form-input"
                                .value=${config.function || ''}
                                placeholder="apps.flows.bundles.example_react.functions.my_func"
                            />
                        </div>
                    ` : ''}
                    
                    <div class="form-group">
                        <label class="form-label">Args Schema</label>
                        <json-field-editor
                            name="args_schema"
                            .value=${config.args_schema ? JSON.stringify(config.args_schema, null, 2) : '{}'}
                            min-height="60"
                            hint="Схема параметров (опционально)"
                        ></json-field-editor>
                    </div>
                    
                    <div class="help-section">
                        <h4>Справка</h4>
                        <ul>
                            <li><code>def execute(args, state):</code> - функция с параметрами</li>
                            <li><code>def run(state):</code> - простая функция</li>
                            <li><code>args["param"]</code> - параметры из input_mapping</li>
                            <li><code>state["response"] = "..."</code> - ответ</li>
                        </ul>
                    </div>
                    
                    ${this.renderStateSettings()}
                </div>
                
                <div class="form-main">
                    <div class="code-section">
                        <div class="form-group" style="flex: 1;">
                            <label class="form-label">
                                ${this.codeMode === 'TOOL_ID' ? 'Code (не используется)' : 'Code'}
                            </label>
                            <python-code-editor
                                .value=${config.code || ''}
                                ?readonly=${this.codeMode === 'TOOL_ID'}
                                min-height="300"
                            ></python-code-editor>
                        </div>
                    </div>
                    
                    <test-panel
                        .flowId=${this.flowId || ''}
                        .inputState=${this._buildDefaultState()}
                        .defaultInputState=${this._buildDefaultState()}
                        @validate=${this._onValidate}
                        @execute=${this._onExecute}
                    ></test-panel>
                </div>
            </div>
        `;
    }
}

customElements.define('code-node-modal', CodeNodeModal);
