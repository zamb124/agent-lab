/**
 * CodeNodeEditor - редактор для code типа
 * Универсальная нода для выполнения кода (Python, JavaScript, Go)
 */
import { html } from 'lit';
import { BaseNodeEditor } from './base-node-editor.js';
import '../editors/python-code-editor.js';
import '../editors/json-field-editor.js';
import '../editors/state-mapping-editor.js';
import '../editors/test-panel.js';

export class CodeNodeEditor extends BaseNodeEditor {
    static properties = {
        ...BaseNodeEditor.properties,
        codeMode: { type: String },
    };

    constructor() {
        super();
        this._nodeType = 'code';
        this.codeMode = 'INLINE_CODE';
    }

    updated(changedProperties) {
        if (changedProperties.has('config')) {
            if (this.config.tool_id) {
                this.codeMode = 'TOOL_ID';
            } else if (this.config.function) {
                this.codeMode = 'CODE_REFERENCE';
            } else {
                this.codeMode = 'INLINE_CODE';
            }
        }
    }

    render() {
        const config = this.nodeConfig;
        
        return html`
            <div class="panel-body">
                <p class="panel-description">
                    Выполнение кода (Python, JavaScript, Go).
                </p>
                
                ${this.renderNodeIdField()}
                
                <div class="form-group">
                    <div class="form-label">
                        <span class="form-label-text">Имя</span>
                    </div>
                    <input 
                        type="text" 
                        class="form-input"
                        .value=${config.name || ''}
                        @change=${(e) => this._onInputChange('name', e.target.value)}
                    />
                </div>
                
                <div class="form-group">
                    <div class="form-label">
                        <span class="form-label-text">Язык</span>
                    </div>
                    <select 
                        class="form-input"
                        .value=${config.language || 'python'}
                        @change=${(e) => this._onInputChange('language', e.target.value)}
                    >
                        <option value="python">Python</option>
                        <option value="javascript">JavaScript</option>
                        <option value="go">Go</option>
                    </select>
                </div>
                
                <div class="code-mode-row">
                    <button 
                        type="button"
                        class="code-mode-btn ${this.codeMode === 'INLINE_CODE' ? 'active' : ''}"
                        @click=${() => { this.codeMode = 'INLINE_CODE'; }}
                    >Inline Code</button>
                    <button 
                        type="button"
                        class="code-mode-btn ${this.codeMode === 'CODE_REFERENCE' ? 'active' : ''}"
                        @click=${() => { this.codeMode = 'CODE_REFERENCE'; }}
                    >Function Path</button>
                    <button 
                        type="button"
                        class="code-mode-btn ${this.codeMode === 'TOOL_ID' ? 'active' : ''}"
                        @click=${() => { this.codeMode = 'TOOL_ID'; }}
                    >Tool ID</button>
                </div>
                
                ${this.codeMode === 'TOOL_ID' ? html`
                    <div class="form-group">
                        <div class="form-label">
                            <span class="form-label-text">Tool ID</span>
                            <span class="form-label-hint">Загрузка tool из реестра</span>
                        </div>
                        <input 
                            type="text" 
                            class="form-input"
                            .value=${config.tool_id || ''}
                            @change=${(e) => this._onInputChange('tool_id', e.target.value)}
                            placeholder="calculator, weather_api"
                        />
                    </div>
                ` : this.codeMode === 'CODE_REFERENCE' ? html`
                    <div class="form-group">
                        <div class="form-label">
                            <span class="form-label-text">Function Path</span>
                        </div>
                        <input 
                            type="text" 
                            class="form-input"
                            .value=${config.function || ''}
                            @change=${(e) => this._onInputChange('function', e.target.value)}
                            placeholder="agents.my_agent.functions.func"
                        />
                    </div>
                ` : html`
                    <div class="form-group">
                        <python-code-editor
                            .value=${config.code || ''}
                            @change=${(e) => this._onInputChange('code', e.detail.value)}
                            min-height="250"
                        ></python-code-editor>
                    </div>
                `}
                
                <div class="form-group">
                    <div class="form-label">
                        <span class="form-label-text">Args Schema (JSON)</span>
                        <span class="form-label-hint">Опционально</span>
                    </div>
                    <json-field-editor
                        .value=${config.args_schema ? JSON.stringify(config.args_schema, null, 2) : '{}'}
                        @change=${(e) => {
                            const editor = e.target;
                            if (editor.isValid()) {
                                this._onInputChange('args_schema', editor.getParsedValue());
                            }
                        }}
                        min-height="80"
                        hint="Схема параметров"
                    ></json-field-editor>
                </div>
                
                <div class="form-group">
                    <state-mapping-editor
                        mode="input"
                        .mappings=${config.input_mapping || {}}
                        .stateVariables=${Object.keys(this._buildDefaultState())}
                        @change=${(e) => this._onInputChange('input_mapping', e.detail.value)}
                    ></state-mapping-editor>
                </div>
                
                <div class="form-group">
                    <state-mapping-editor
                        mode="output"
                        .mappings=${config.output_mapping || {}}
                        @change=${(e) => this._onInputChange('output_mapping', e.detail.value)}
                    ></state-mapping-editor>
                </div>
                
                <test-panel
                    .inputState=${this._buildDefaultState()}
                    ?expanded=${this.expanded}
                    @validate=${this._onValidate}
                    @execute=${this._onExecute}
                ></test-panel>
            </div>
        `;
    }
}

customElements.define('code-node-editor', CodeNodeEditor);
