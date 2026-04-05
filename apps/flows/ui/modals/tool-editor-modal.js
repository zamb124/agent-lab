/**
 * ToolEditorModal - модалка для создания/редактирования inline tools
 */
import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import '../components/editors/code-editor.js';
import '../components/editors/json-field-editor.js';
import '../components/editors/test-panel.js';
import './code-docs-modal.js';

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
        flowVariables: { type: Object },
        previewExecutionState: { type: Object },
        name: { type: String },
        description: { type: String },
        reactRole: { type: String },
        code: { type: String },
        language: { type: String },
        argsSchema: { type: String },
    };

    constructor() {
        super();
        this.toolConfig = {};
        this.mode = 'create';
        this.flowVariables = {};
        this.previewExecutionState = null;
        this.title = '';
        this.name = '';
        this.description = '';
        this.reactRole = 'standard';
        this.language = 'python';
        this.code = `async def execute(args):
    """
    Run the tool with the given arguments.

    Args:
        args: Argument dict for the tool

    Returns:
        Execution result
    """
    # Example: read from args
    # user_query = args.get('user_query')

    return {"result": "success"}
`;
        this.argsSchema = '{}';
    }

    connectedCallback() {
        super.connectedCallback();
        
        if (this.mode === 'edit' && this.toolConfig) {
            this.title = this.i18n.t('tool_editor_modal.title_edit');
            this.name = this.toolConfig.name || '';
            this.description = this.toolConfig.description || '';
            const rr = this.toolConfig.react_role || this.toolConfig.tool_type;
            this.reactRole = rr === 'tool' || rr === undefined ? 'standard' : rr;
            this.code = this.toolConfig.code || this.code;
            this.argsSchema = typeof this.toolConfig.args_schema === 'string' 
                ? this.toolConfig.args_schema 
                : JSON.stringify(this.toolConfig.args_schema || {}, null, 2);
        } else {
            this.title = this.i18n.t('tool_editor_modal.title_create');
        }
    }

    _buildDefaultState() {
        if (this.previewExecutionState && typeof this.previewExecutionState === 'object') {
            return structuredClone(this.previewExecutionState);
        }
        return { content: '', messages: [], variables: {} };
    }

    _onValidate = async (e) => {
        const { state } = e.detail;
        const codeEditor = this.shadowRoot.querySelector('code-editor');
        const jsonEditor = this.shadowRoot.querySelector('json-field-editor');
        
        if (!codeEditor || !jsonEditor) {
            this.error(this.i18n.t('tool_editor_modal.err_editors'));
            return;
        }
        
        const code = codeEditor.getValue();
        const argsSchemaStr = jsonEditor.getValue();
        
        let argsSchema = {};
        try {
            argsSchema = argsSchemaStr ? JSON.parse(argsSchemaStr) : {};
        } catch (e) {
            this.error(this.i18n.t('tool_editor_modal.err_args_schema'));
            return;
        }
        
        try {
            const response = await this.a2a.post('/api/v1/code/validate', {
                code,
                node_type: 'code'
            });
            
            if (response.valid) {
                this.success(this.i18n.t('tool_editor_modal.code_valid'));
            } else {
                this.error(this.i18n.t('tool_editor_modal.validation_error', {
                    message: response.error || this.i18n.t('tool_editor_modal.error_unknown'),
                }));
            }
        } catch (error) {
            this.error(this.i18n.t('tool_editor_modal.validation_error', { message: error.message }));
        }
    }

    _onExecute = async (e) => {
        const { state } = e.detail;
        const codeEditor = this.shadowRoot.querySelector('code-editor');
        const jsonEditor = this.shadowRoot.querySelector('json-field-editor');
        
        if (!codeEditor || !jsonEditor) {
            this.error(this.i18n.t('tool_editor_modal.err_editors'));
            return;
        }
        
        const code = codeEditor.getValue();
        const argsSchemaStr = jsonEditor.getValue();
        
        let argsSchema = {};
        try {
            argsSchema = argsSchemaStr ? JSON.parse(argsSchemaStr) : {};
        } catch (e) {
            this.error(this.i18n.t('tool_editor_modal.err_args_schema'));
            return;
        }
        
        try {
            const response = await this.a2a.post('/api/v1/code/execute', {
                code,
                node_type: 'code',
                state,
                args: state,
                args_schema: argsSchema
            });
            
            if (response.success) {
                this.success(this.i18n.t('tool_editor_modal.execute_ok'));
                return response;
            } else {
                this.error(this.i18n.t('tool_editor_modal.execute_error', {
                    message: response.error || this.i18n.t('tool_editor_modal.error_unknown'),
                }));
                return response;
            }
        } catch (error) {
            this.error(this.i18n.t('tool_editor_modal.execute_error', { message: error.message }));
            return { success: false, error: error.message };
        }
    }

    _onSave() {
        const codeEditor = this.shadowRoot.querySelector('code-editor');
        const jsonEditor = this.shadowRoot.querySelector('json-field-editor');
        
        if (!this.name.trim()) {
            this.error(this.i18n.t('tool_editor_modal.err_name'));
            return;
        }
        
        if (!codeEditor || !jsonEditor) {
            this.error(this.i18n.t('tool_editor_modal.err_editors'));
            return;
        }
        
        const code = codeEditor.getValue();
        const argsSchemaStr = jsonEditor.getValue();
        
        if (!code.trim()) {
            this.error(this.i18n.t('tool_editor_modal.err_code'));
            return;
        }
        
        let argsSchema = {};
        try {
            argsSchema = argsSchemaStr ? JSON.parse(argsSchemaStr) : {};
        } catch (e) {
            this.error(this.i18n.t('tool_editor_modal.err_args_schema'));
            return;
        }
        
        const toolId = this.toolConfig.tool_id || this._generateToolId(this.name);
        
        const config = {
            tool_id: toolId,
            type: 'code',
            name: this.name.trim(),
            description: this.description.trim(),
            react_role: this.reactRole,
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
        if (e.detail.language) {
            this.language = e.detail.language;
        }
    }

    _onLanguageChange(e) {
        this.language = e.detail.language;
    }

    _onOpenDocs(e) {
        const modal = document.querySelector('code-docs-modal') || document.createElement('code-docs-modal');
        if (!modal.parentElement) {
            document.body.appendChild(modal);
        }
        modal.showModal({
            language: e.detail.language || this.language || 'python',
            nodeType: 'code',
            perspective: 'editor',
        });
    }

    _onArgsSchemaChange(e) {
        this.argsSchema = e.detail.value;
    }

    renderBody() {
        return html`
            <div class="form-grid">
                <div class="form-group">
                    <label class="form-label required">${this.i18n.t('tool_editor_modal.field_name')}</label>
                    <input 
                        type="text" 
                        class="form-input"
                        .value=${this.name}
                        @input=${(e) => this.name = e.target.value}
                        placeholder=${this.i18n.t('tool_editor_modal.placeholder_name')}
                    />
                </div>
                
                <div class="form-group">
                    <label class="form-label">${this.i18n.t('tool_editor_modal.field_description')}</label>
                    <textarea 
                        class="form-input form-textarea"
                        .value=${this.description}
                        @input=${(e) => this.description = e.target.value}
                        placeholder=${this.i18n.t('tool_editor_modal.placeholder_description')}
                    ></textarea>
                </div>
                
                <div class="form-group">
                    <label class="form-label">${this.i18n.t('tool_editor_modal.field_react_role')}</label>
                    <select 
                        class="form-select"
                        .value=${this.reactRole}
                        @change=${(e) => this.reactRole = e.target.value}
                    >
                        <option value="standard">${this.i18n.t('tool_editor_modal.option_standard')}</option>
                        <option value="reason">${this.i18n.t('tool_editor_modal.option_reason')}</option>
                        <option value="exit">${this.i18n.t('tool_editor_modal.option_exit')}</option>
                    </select>
                    <span class="form-hint">
                        ${this.i18n.t('tool_editor_modal.react_role_hint')}
                    </span>
                </div>
                
                <div class="form-group">
                    <label class="form-label required">${this.i18n.t('tool_editor_modal.args_schema_label')}</label>
                    <json-field-editor
                        .value=${this.argsSchema}
                        min-height="120"
                        hint=${this.i18n.t('tool_editor_modal.args_schema_hint')}
                        @change=${this._onArgsSchemaChange}
                    ></json-field-editor>
                </div>
                
                <div class="form-group">
                    <label class="form-label required">${this.i18n.t('tool_editor_modal.code_label')}</label>
                    <code-editor
                        .value=${this.code}
                        .language=${this.language || 'python'}
                        node-type="code"
                        min-height="300"
                        @change=${this._onCodeChange}
                        @language-change=${this._onLanguageChange}
                        @open-docs=${this._onOpenDocs}
                    ></code-editor>
                </div>
                
                <test-panel
                    .inputState=${this._buildDefaultState()}
                    .defaultInputState=${this._buildDefaultState()}
                    @validate=${this._onValidate}
                    @execute=${this._onExecute}
                ></test-panel>
            </div>
        `;
    }

    renderSaveHeaderButton() {
        const title =
            this.mode === 'create'
                ? this.i18n.t('inline_tool_modal.create')
                : this.i18n.t('inline_tool_modal.save');
        return this._renderHeaderSaveIcon({
            onClick: () => this._onSave(),
            disabled: false,
            title,
        });
    }

    renderFooter() {
        return html`
            <div class="action-row">
                <button type="button" class="btn btn-secondary" @click=${this.close}>
                    ${this.i18n.t('editor.cancel')}
                </button>
            </div>
        `;
    }
}

customElements.define('tool-editor-modal', ToolEditorModal);

