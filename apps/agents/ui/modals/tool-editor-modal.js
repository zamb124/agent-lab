/**
 * ToolEditorModal - модалка для создания/редактирования inline tools
 */
import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import '../components/editors/python-code-editor.js';
import '../components/editors/json-field-editor.js';
import '../components/editors/test-panel.js';

export class ToolEditorModal extends PlatformModal {
    static styles = [
        PlatformModal.styles,
        css`
            :host {
                --modal-max-width: 900px;
            }
            
            .form-grid {
                display: grid;
                gap: var(--space-4);
            }
            
            .form-group {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }
            
            .form-label {
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-secondary);
            }
            
            .form-label.required::after {
                content: ' *';
                color: var(--error);
            }
            
            .form-input {
                padding: var(--space-2) var(--space-3);
                font-size: var(--text-sm);
                color: var(--text-primary);
                background: var(--glass-tint-subtle);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                outline: none;
                transition: all var(--duration-fast) var(--easing-default);
            }
            
            .form-input:focus {
                border-color: var(--accent);
                background: var(--glass-tint-medium);
            }
            
            .form-textarea {
                min-height: 80px;
                resize: vertical;
                font-family: inherit;
            }
            
            .form-select {
                padding: var(--space-2) var(--space-3);
                font-size: var(--text-sm);
                color: var(--text-primary);
                background: var(--glass-tint-subtle);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                outline: none;
                cursor: pointer;
            }
            
            .form-select:focus {
                border-color: var(--accent);
            }
            
            .form-hint {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-top: -var(--space-1);
            }
            
            .action-row {
                display: flex;
                gap: var(--space-3);
                padding-top: var(--space-2);
            }
            
            .btn {
                padding: var(--space-2) var(--space-4);
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                border-radius: var(--radius-md);
                border: 1px solid var(--border-default);
                cursor: pointer;
                transition: all var(--duration-fast) var(--easing-default);
            }
            
            .btn-primary {
                color: white;
                background: var(--accent);
                border-color: var(--accent);
            }
            
            .btn-primary:hover {
                background: var(--accent-hover);
            }
            
            .btn-secondary {
                color: var(--text-primary);
                background: var(--glass-tint-medium);
            }
            
            .btn-secondary:hover {
                background: var(--glass-tint-strong);
            }
        `
    ];

    static properties = {
        toolConfig: { type: Object },
        mode: { type: String },
        agentVariables: { type: Object },
        name: { type: String },
        description: { type: String },
        toolType: { type: String },
        code: { type: String },
        argsSchema: { type: String },
    };

    constructor() {
        super();
        this.toolConfig = {};
        this.mode = 'create';
        this.agentVariables = {};
        this.title = 'Создать Inline Tool';
        this.name = '';
        this.description = '';
        this.toolType = 'tool';
        this.code = `async def execute(args):
    """
    Выполняет действие с переданными аргументами.
    
    Args:
        args: Словарь с аргументами инструмента
    
    Returns:
        Результат выполнения
    """
    # Пример: можно получить доступ к state через args
    # user_query = args.get('user_query')
    
    return {"result": "success"}
`;
        this.argsSchema = '{}';
    }

    connectedCallback() {
        super.connectedCallback();
        
        if (this.mode === 'edit' && this.toolConfig) {
            this.title = 'Редактировать Tool';
            this.name = this.toolConfig.name || '';
            this.description = this.toolConfig.description || '';
            this.toolType = this.toolConfig.tool_type || 'tool';
            this.code = this.toolConfig.code || this.code;
            this.argsSchema = typeof this.toolConfig.args_schema === 'string' 
                ? this.toolConfig.args_schema 
                : JSON.stringify(this.toolConfig.args_schema || {}, null, 2);
        }
    }

    _buildDefaultState() {
        const state = {
            content: "Текст запроса пользователя",
            messages: [],
        };
        
        for (const [key, varData] of Object.entries(this.agentVariables || {})) {
            state[key] = varData.value || '';
        }
        
        return state;
    }

    _onValidate = async (e) => {
        const { state } = e.detail;
        const codeEditor = this.shadowRoot.querySelector('python-code-editor');
        const jsonEditor = this.shadowRoot.querySelector('json-field-editor');
        
        if (!codeEditor || !jsonEditor) {
            this.error('Редакторы не инициализированы');
            return;
        }
        
        const code = codeEditor.getValue();
        const argsSchemaStr = jsonEditor.getValue();
        
        let argsSchema = {};
        try {
            argsSchema = argsSchemaStr ? JSON.parse(argsSchemaStr) : {};
        } catch (e) {
            this.error('Неверный формат args_schema');
            return;
        }
        
        try {
            const response = await this.a2a.post('/api/v1/code/validate', {
                code,
                node_type: 'tool'
            });
            
            if (response.valid) {
                this.success('Код валиден');
            } else {
                this.error(`Ошибка валидации: ${response.error || 'Unknown error'}`);
            }
        } catch (error) {
            this.error(`Ошибка валидации: ${error.message}`);
        }
    }

    _onExecute = async (e) => {
        const { state } = e.detail;
        const codeEditor = this.shadowRoot.querySelector('python-code-editor');
        const jsonEditor = this.shadowRoot.querySelector('json-field-editor');
        
        if (!codeEditor || !jsonEditor) {
            this.error('Редакторы не инициализированы');
            return;
        }
        
        const code = codeEditor.getValue();
        const argsSchemaStr = jsonEditor.getValue();
        
        let argsSchema = {};
        try {
            argsSchema = argsSchemaStr ? JSON.parse(argsSchemaStr) : {};
        } catch (e) {
            this.error('Неверный формат args_schema');
            return;
        }
        
        try {
            const response = await this.a2a.post('/api/v1/code/execute', {
                code,
                node_type: 'tool',
                state,
                args: state,
                args_schema: argsSchema
            });
            
            if (response.success) {
                this.success('Выполнено успешно');
                return response;
            } else {
                this.error(`Ошибка выполнения: ${response.error || 'Unknown error'}`);
                return response;
            }
        } catch (error) {
            this.error(`Ошибка выполнения: ${error.message}`);
            return { success: false, error: error.message };
        }
    }

    _onSave() {
        const codeEditor = this.shadowRoot.querySelector('python-code-editor');
        const jsonEditor = this.shadowRoot.querySelector('json-field-editor');
        
        if (!this.name.trim()) {
            this.error('Название обязательно');
            return;
        }
        
        if (!codeEditor || !jsonEditor) {
            this.error('Редакторы не инициализированы');
            return;
        }
        
        const code = codeEditor.getValue();
        const argsSchemaStr = jsonEditor.getValue();
        
        if (!code.trim()) {
            this.error('Код обязателен');
            return;
        }
        
        let argsSchema = {};
        try {
            argsSchema = argsSchemaStr ? JSON.parse(argsSchemaStr) : {};
        } catch (e) {
            this.error('Неверный формат args_schema');
            return;
        }
        
        const toolId = this.toolConfig.tool_id || this._generateToolId(this.name);
        
        const config = {
            tool_id: toolId,
            type: 'tool',
            name: this.name.trim(),
            description: this.description.trim(),
            tool_type: this.toolType,
            code: code,
            args_schema: argsSchema,
        };
        
        this.emit('tool-saved', { toolId, config });
        this.close();
    }

    _generateToolId(name) {
        return name
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, '_')
            .replace(/^_+|_+$/g, '');
    }

    _onCodeChange(e) {
        this.code = e.detail.value;
    }

    _onArgsSchemaChange(e) {
        this.argsSchema = e.detail.value;
    }

    renderBody() {
        return html`
            <div class="form-grid">
                <div class="form-group">
                    <label class="form-label required">Название</label>
                    <input 
                        type="text" 
                        class="form-input"
                        .value=${this.name}
                        @input=${(e) => this.name = e.target.value}
                        placeholder="Название инструмента"
                    />
                </div>
                
                <div class="form-group">
                    <label class="form-label">Описание</label>
                    <textarea 
                        class="form-input form-textarea"
                        .value=${this.description}
                        @input=${(e) => this.description = e.target.value}
                        placeholder="Что делает этот инструмент?"
                    ></textarea>
                </div>
                
                <div class="form-group">
                    <label class="form-label">Тип инструмента</label>
                    <select 
                        class="form-select"
                        .value=${this.toolType}
                        @change=${(e) => this.toolType = e.target.value}
                    >
                        <option value="tool">Tool - обычный инструмент</option>
                        <option value="reason">Reason - инструмент для размышлений</option>
                        <option value="exit">Exit - инструмент для завершения</option>
                    </select>
                    <span class="form-hint">
                        Reason/Exit инструменты имеют особую роль в ReAct агентах
                    </span>
                </div>
                
                <div class="form-group">
                    <label class="form-label required">Args Schema</label>
                    <json-field-editor
                        .value=${this.argsSchema}
                        min-height="120"
                        hint="JSON схема аргументов (например: {&quot;query&quot;: {&quot;type&quot;: &quot;string&quot;}})"
                        @change=${this._onArgsSchemaChange}
                    ></json-field-editor>
                </div>
                
                <div class="form-group">
                    <label class="form-label required">Код</label>
                    <python-code-editor
                        .value=${this.code}
                        min-height="300"
                        @change=${this._onCodeChange}
                    ></python-code-editor>
                </div>
                
                <test-panel
                    .inputState=${this._buildDefaultState()}
                    @validate=${this._onValidate}
                    @execute=${this._onExecute}
                ></test-panel>
            </div>
        `;
    }

    renderFooter() {
        return html`
            <div class="action-row">
                <button type="button" class="btn btn-secondary" @click=${this.close}>
                    Отмена
                </button>
                <button type="button" class="btn btn-primary" @click=${this._onSave}>
                    ${this.mode === 'create' ? 'Создать' : 'Сохранить'}
                </button>
            </div>
        `;
    }
}

customElements.define('tool-editor-modal', ToolEditorModal);

