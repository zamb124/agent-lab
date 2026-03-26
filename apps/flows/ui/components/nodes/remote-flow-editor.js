/**
 * RemoteFlowEditor - редактор для remote_flow типа
 * Удалённый A2A endpoint (remote_flow)
 */
import { html } from 'lit';
import { BaseNodeEditor } from './base-node-editor.js';
import '../editors/json-field-editor.js';

export class RemoteFlowEditor extends BaseNodeEditor {
    constructor() {
        super();
        this._nodeType = 'remote_flow';
    }

    renderFields() {
        const config = this.nodeConfig;
        const showCommonFields = !this.expanded;
        
        return html`
            ${showCommonFields ? html`
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
            ` : ''}
            
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
            
            ${this.renderMappingSection()}
            
            ${this._renderTestPanel()}
        `;
    }
}

customElements.define('remote-flow-editor', RemoteFlowEditor);

