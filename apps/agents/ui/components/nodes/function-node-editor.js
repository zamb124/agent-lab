/**
 * FunctionNodeEditor - редактор для function типа
 * Python функция для обработки данных
 */
import { html } from 'lit';
import { BaseNodeEditor } from './base-node-editor.js';
import '../editors/python-code-editor.js';
import '../editors/input-mapping-editor.js';
import '../editors/test-panel.js';

export class FunctionNodeEditor extends BaseNodeEditor {
    static properties = {
        ...BaseNodeEditor.properties,
        codeMode: { type: String },
    };

    constructor() {
        super();
        this._nodeType = 'function';
        this.codeMode = 'INLINE_CODE';
    }

    updated(changedProperties) {
        if (changedProperties.has('config')) {
            this.codeMode = this.config.function ? 'CODE_REFERENCE' : 'INLINE_CODE';
        }
    }

    render() {
        const config = this.nodeConfig;
        
        return html`
            <div class="panel-body">
                <p class="panel-description">
                    Python функция для обработки данных.
                </p>
                
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
                
                <div class="code-mode-row">
                    <button 
                        type="button"
                        class="code-mode-btn ${this.codeMode === 'INLINE_CODE' ? 'active' : ''}"
                        @click=${() => { this.codeMode = 'INLINE_CODE'; }}
                    >INLINE_CODE</button>
                    <button 
                        type="button"
                        class="code-mode-btn ${this.codeMode === 'CODE_REFERENCE' ? 'active' : ''}"
                        @click=${() => { this.codeMode = 'CODE_REFERENCE'; }}
                    >CODE_REFERENCE</button>
                </div>
                
                ${this.codeMode === 'CODE_REFERENCE' ? html`
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
                        <span class="form-label-text">Input Mapping</span>
                        <span class="form-label-hint">Маппинг из state</span>
                    </div>
                    <input-mapping-editor
                        .mappings=${config.input_mapping || {}}
                        .availableState=${this._buildDefaultState()}
                        @change=${(e) => this._onInputChange('input_mapping', e.detail.value)}
                    ></input-mapping-editor>
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

customElements.define('function-node-editor', FunctionNodeEditor);


