/**
 * ToolNodeEditor - редактор для tool типа
 * Инструмент для LLM агента
 */
import { html } from 'lit';
import { BaseNodeEditor } from './base-node-editor.js';
import '../editors/python-code-editor.js';
import '../editors/json-field-editor.js';
import '../editors/state-mapping-editor.js';
import '../editors/test-panel.js';

export class ToolNodeEditor extends BaseNodeEditor {
    constructor() {
        super();
        this._nodeType = 'tool';
    }

    render() {
        const config = this.nodeConfig;
        
        return html`
            <div class="panel-body">
                <p class="panel-description">
                    Инструмент для LLM агента.
                </p>
                
                ${this.renderNodeIdField()}
                
                <div class="form-group">
                    <div class="form-label">
                        <span class="form-label-text">Tool ID</span>
                        <span class="form-label-hint">Уникальный идентификатор</span>
                    </div>
                    <input 
                        type="text" 
                        class="form-input"
                        .value=${config.tool_id || ''}
                        @change=${(e) => this._onInputChange('tool_id', e.target.value)}
                        placeholder="calculator, weather_api"
                    />
                </div>
                
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
                        <span class="form-label-text">Описание</span>
                    </div>
                    <textarea 
                        class="form-input form-textarea"
                        .value=${config.description || ''}
                        @change=${(e) => this._onInputChange('description', e.target.value)}
                        placeholder="Описание для LLM"
                        rows="2"
                    ></textarea>
                </div>
                
                <div class="form-group">
                    <python-code-editor
                        .value=${config.code || ''}
                        @change=${(e) => this._onInputChange('code', e.detail.value)}
                        min-height="200"
                    ></python-code-editor>
                </div>
                
                <div class="form-group">
                    <div class="form-label">
                        <span class="form-label-text">Args Schema (JSON)</span>
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
                        hint="Схема параметров для LLM"
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

customElements.define('tool-node-editor', ToolNodeEditor);


