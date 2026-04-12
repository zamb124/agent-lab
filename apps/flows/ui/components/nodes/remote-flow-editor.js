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
                        <span class="form-label-text">${this.i18n.t('node_modal.common.field_name')}</span>
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
                    <span class="form-label-text">${this.i18n.t('node_modal.remote_flow.url_label')}</span>
                </div>
                <input 
                    type="text" 
                    class="form-input"
                    .value=${config.url || ''}
                    @change=${(e) => this._onInputChange('url', e.target.value)}
                    placeholder="http://agent:8080"
                />
                <span class="form-label-hint">${this.i18n.t('node_modal.remote_flow.url_hint')}</span>
            </div>
            
            <div class="form-group">
                <div class="form-label">
                    <span class="form-label-text">${this.i18n.t('node_modal.remote_flow.skill_id_label')}</span>
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
                    <span class="form-label-text">${this.i18n.t('node_modal.remote_flow.auth_headers_label')}</span>
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

