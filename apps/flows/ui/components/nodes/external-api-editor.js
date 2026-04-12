/**
 * ExternalApiEditor - редактор для external_api типа
 * HTTP вызов внешнего API
 */
import { html } from 'lit';
import { BaseNodeEditor } from './base-node-editor.js';
import '../editors/json-field-editor.js';

export class ExternalApiEditor extends BaseNodeEditor {
    constructor() {
        super();
        this._nodeType = 'external_api';
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
                    <span class="form-label-text">${this.i18n.t('node_modal.external_api.url_label')}</span>
                </div>
                <input 
                    type="text" 
                    class="form-input"
                    .value=${config.url || ''}
                    @change=${(e) => this._onInputChange('url', e.target.value)}
                    placeholder="https://api.example.com/endpoint"
                />
            </div>
            
            <div class="form-group">
                <div class="form-label">
                    <span class="form-label-text">${this.i18n.t('node_modal.external_api.method_label')}</span>
                </div>
                <select 
                    class="form-input form-select"
                    .value=${config.method || 'POST'}
                    @change=${(e) => this._onInputChange('method', e.target.value)}
                >
                    <option value="GET">GET</option>
                    <option value="POST">POST</option>
                    <option value="PUT">PUT</option>
                    <option value="DELETE">DELETE</option>
                </select>
            </div>
            
            <div class="form-group">
                <div class="form-label">
                    <span class="form-label-text">${this.i18n.t('node_modal.external_api.auth_headers_label')}</span>
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
                    hint=${this.i18n.t('node_modal.external_api.var_path_hint')}
                ></json-field-editor>
            </div>
            
            <div class="form-group">
                <div class="form-label">
                    <span class="form-label-text">${this.i18n.t('node_modal.external_api.parameters_label')}</span>
                </div>
                <json-field-editor
                    .value=${config.parameters ? JSON.stringify(config.parameters, null, 2) : '[]'}
                    @change=${(e) => {
                        const editor = e.target;
                        if (editor.isValid()) {
                            this._onInputChange('parameters', editor.getParsedValue());
                        }
                    }}
                    min-height="80"
                    hint=${this.i18n.t('node_modal.external_api.parameters_hint')}
                ></json-field-editor>
            </div>
            
            ${this.renderMappingSection({ showInput: false })}
            
            ${this._renderTestPanel()}
        `;
    }
}

customElements.define('external-api-editor', ExternalApiEditor);


