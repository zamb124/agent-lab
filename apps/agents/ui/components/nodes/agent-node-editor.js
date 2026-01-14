/**
 * AgentNodeEditor - редактор для agent типа
 * Вызов вложенного агента
 */
import { html } from 'lit';
import { BaseNodeEditor } from './base-node-editor.js';
import '../editors/input-mapping-editor.js';
import '../editors/test-panel.js';

export class AgentNodeEditor extends BaseNodeEditor {
    constructor() {
        super();
        this._nodeType = 'agent';
    }

    render() {
        const config = this.nodeConfig;
        
        return html`
            <div class="panel-body">
                <p class="panel-description">
                    Вызов вложенного агента.
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
                
                <div class="form-group">
                    <div class="form-label">
                        <span class="form-label-text">Agent ID</span>
                    </div>
                    <input 
                        type="text" 
                        class="form-input"
                        .value=${config.agent_id || ''}
                        @change=${(e) => this._onInputChange('agent_id', e.target.value)}
                        placeholder="nested_agent"
                    />
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

customElements.define('agent-node-editor', AgentNodeEditor);


