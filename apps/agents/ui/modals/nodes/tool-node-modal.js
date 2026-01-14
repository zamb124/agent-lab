/**
 * ToolNodeModal - модалка редактирования Tool Node
 */
import { html, css } from 'lit';
import { BaseNodeModal } from './base-node-modal.js';

export class ToolNodeModal extends BaseNodeModal {
    static styles = [
        BaseNodeModal.styles,
        css`
            .code-section {
                flex: 1;
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }
            
            .schema-section {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }
            
            .schema-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
            }
            
            .generate-btn {
                padding: var(--space-1) var(--space-2);
                font-size: var(--text-xs);
                color: var(--accent);
                background: var(--accent-subtle);
                border: none;
                border-radius: var(--radius-sm);
                cursor: pointer;
            }
            
            .generate-btn:hover {
                background: var(--accent);
                color: white;
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
        toolId: { type: String },
    };

    constructor() {
        super();
        this.codeMode = 'INLINE_CODE';
        this.toolId = '';
    }

    getNodeType() {
        return 'tool';
    }

    getModalTitle() {
        return 'Tool Node';
    }

    showModal(nodeId = '', config = {}) {
        super.showModal(nodeId, config);
        
        if (config.tool_id && !config.code) {
            this.codeMode = 'CODE_REFERENCE';
            this.toolId = config.tool_id;
        } else {
            this.codeMode = 'INLINE_CODE';
            this.toolId = '';
        }
    }

    _onCodeModeChange(mode) {
        this.codeMode = mode;
    }

    _buildConfig() {
        const name = this.shadowRoot.querySelector('[name="tool_name"]')?.value?.trim() || '';
        const description = this.shadowRoot.querySelector('[name="description"]')?.value?.trim() || '';
        const permission = this.shadowRoot.querySelector('[name="permission"]')?.value || 'public';
        const toolType = this.shadowRoot.querySelector('[name="tool_type"]')?.value || 'tool';
        
        const config = {
            type: 'tool',
        };
        
        if (name) config.name = name;
        if (description) config.description = description;
        if (permission !== 'public') config.permission = permission;
        if (toolType !== 'tool') config.tool_type = toolType;
        
        const tagsEditor = this.shadowRoot.querySelector('tag-input');
        const tags = tagsEditor?.getTags() || [];
        if (tags.length > 0) config.tags = tags;
        
        if (this.codeMode === 'CODE_REFERENCE') {
            const toolId = this.shadowRoot.querySelector('[name="tool_id"]')?.value?.trim();
            if (!toolId) {
                throw new Error('Выберите Tool');
            }
            config.tool_id = toolId;
        } else {
            const codeEditor = this.shadowRoot.querySelector('python-code-editor');
            const code = codeEditor?.getValue()?.trim();
            if (!code) {
                throw new Error('Введите код tool');
            }
            config.code = code;
            
            const argsSchemaEditor = this.shadowRoot.querySelector('json-field-editor[name="args_schema"]');
            if (argsSchemaEditor?.getValue()?.trim()) {
                if (!argsSchemaEditor.isValid()) {
                    throw new Error('Неверный формат Args Schema JSON');
                }
                config.args_schema = argsSchemaEditor.getParsedValue();
            }
            
            const mockEditor = this.shadowRoot.querySelector('json-field-editor[name="mock_response"]');
            if (mockEditor?.getValue()?.trim()) {
                if (!mockEditor.isValid()) {
                    throw new Error('Неверный формат Mock Response JSON');
                }
                config.mock_response = mockEditor.getParsedValue();
            }
        }
        
        const inputMappingEditor = this.shadowRoot.querySelector('input-mapping-editor');
        const inputMapping = inputMappingEditor?.getValue() || {};
        if (Object.keys(inputMapping).length > 0) {
            config.input_mapping = inputMapping;
        }
        
        return this._applyStateSettings(config);
    }

    _getDefaultCode() {
        return `async def execute(query: str = "test", state: dict = None):
    """
    Tool для выполнения задачи.
    
    Args:
        query: Параметр запроса
        state: Текущее состояние (опционально)
    
    Returns:
        Результат выполнения
    """
    return {"result": query}
`;
    }

    _getDefaultArgsSchema() {
        return JSON.stringify({
            query: {
                type: 'string',
                description: 'Параметр запроса',
                default: 'test',
            },
        }, null, 2);
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
                            placeholder="my_tool"
                            required
                        />
                    </div>
                    
                    <div class="form-group">
                        <label class="form-label">Имя</label>
                        <input 
                            type="text" 
                            name="tool_name"
                            class="form-input"
                            .value=${config.name || ''}
                            placeholder="Calculator"
                        />
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
                        <div class="form-group">
                            <label class="form-label">Tool *</label>
                            <input 
                                type="text" 
                                name="tool_id"
                                class="form-input"
                                .value=${this.toolId}
                                placeholder="tool_id"
                            />
                        </div>
                    ` : ''}
                    
                    <div class="form-group">
                        <label class="form-label">Описание</label>
                        <textarea 
                            name="description"
                            class="form-textarea"
                            rows="2"
                            .value=${config.description || ''}
                            placeholder="Описание инструмента"
                        ></textarea>
                    </div>
                    
                    <div class="form-group">
                        <label class="form-label">Теги</label>
                        <tag-input .tags=${config.tags || []}></tag-input>
                    </div>
                    
                    <div class="form-group">
                        <label class="form-label">Permission</label>
                        <select name="permission" class="form-select">
                            <option value="public" ?selected=${config.permission === 'public'}>public</option>
                            <option value="private" ?selected=${config.permission === 'private'}>private</option>
                            <option value="admin" ?selected=${config.permission === 'admin'}>admin</option>
                        </select>
                    </div>
                    
                    <div class="form-group">
                        <label class="form-label">Tool Type</label>
                        <select name="tool_type" class="form-select">
                            <option value="tool" ?selected=${!config.tool_type || config.tool_type === 'tool'}>Default (tool)</option>
                            <option value="reason" ?selected=${config.tool_type === 'reason'}>Reasoning</option>
                            <option value="exit" ?selected=${config.tool_type === 'exit'}>Exit</option>
                        </select>
                        <span class="form-hint">Только 1 reasoning и 1 exit tool разрешены в react_node</span>
                    </div>
                    
                    <div class="form-group">
                        <input-mapping-editor
                            .mappings=${[]}
                            .availableState=${this._buildDefaultState()}
                        ></input-mapping-editor>
                    </div>
                    
                    ${this.renderStateSettings()}
                </div>
                
                <div class="form-main">
                    <div class="code-section">
                        <div class="form-group" style="flex: 1;">
                            <label class="form-label">
                                ${this.codeMode === 'CODE_REFERENCE' ? 'Tool Code (readonly)' : 'Python Code'}
                            </label>
                            <python-code-editor
                                .value=${config.code || this._getDefaultCode()}
                                ?readonly=${this.codeMode === 'CODE_REFERENCE'}
                                min-height="200"
                            ></python-code-editor>
                        </div>
                        
                        ${this.codeMode === 'INLINE_CODE' ? html`
                            <div class="schema-section">
                                <div class="schema-header">
                                    <label class="form-label">Args Schema (JSON)</label>
                                    <button type="button" class="generate-btn">
                                        Из кода
                                    </button>
                                </div>
                                <json-field-editor
                                    name="args_schema"
                                    .value=${config.args_schema ? JSON.stringify(config.args_schema, null, 2) : this._getDefaultArgsSchema()}
                                    min-height="100"
                                    placeholder='{"param": {"type": "string", "description": "..."}}'
                                    hint="Схема параметров для LLM"
                                ></json-field-editor>
                            </div>
                            
                            <div class="form-group">
                                <label class="form-label">Mock Response (JSON)</label>
                                <json-field-editor
                                    name="mock_response"
                                    .value=${config.mock_response ? JSON.stringify(config.mock_response, null, 2) : ''}
                                    min-height="60"
                                    placeholder='{"result": "test_value"}'
                                    hint="Ответ для тестирования без выполнения"
                                ></json-field-editor>
                            </div>
                        ` : ''}
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

customElements.define('tool-node-modal', ToolNodeModal);


