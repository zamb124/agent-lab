/**
 * RemoteAgentEditor - редактор для remote_agent типа
 * Удалённый A2A агент
 */
import { html } from 'lit';
import { BaseNodeEditor } from './base-node-editor.js';
import '../editors/json-field-editor.js';
import '../editors/state-mapping-editor.js';
import '../editors/test-panel.js';

export class RemoteAgentEditor extends BaseNodeEditor {
    constructor() {
        super();
        this._nodeType = 'remote_agent';
    }

    render() {
        const config = this.nodeConfig;
        
        return html`
            <div class="panel-body">
                <p class="panel-description">
                    Удалённый A2A агент.
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
                        <span class="form-label-text">URL</span>
                    </div>
                    <input 
                        type="text" 
                        class="form-input"
                        .value=${config.url || ''}
                        @change=${(e) => this._onInputChange('url', e.target.value)}
                        placeholder="http://agent:8080"
                    />
                    <span class="form-label-hint">Поддерживает @var:path</span>
                </div>
                
                <div class="form-group">
                    <div class="form-label">
                        <span class="form-label-text">Skill ID</span>
                    </div>
                    <input 
                        type="text" 
                        class="form-input"
                        .value=${config.skill_id || 'default'}
                        @change=${(e) => this._onInputChange('skill_id', e.target.value)}
                    />
                </div>
                
                <div class="form-group">
                    <div class="form-label">
                        <span class="form-label-text">Auth Headers (JSON)</span>
                    </div>
                    <json-field-editor
                        .value=${config.auth_headers ? JSON.stringify(config.auth_headers, null, 2) : '{}'}
                        @change=${(e) => {
                            const editor = e.target;
                            if (editor.isValid()) {
                                this._onInputChange('auth_headers', editor.getParsedValue());
                            }
                        }}
                        min-height="60"
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

customElements.define('remote-agent-editor', RemoteAgentEditor);

