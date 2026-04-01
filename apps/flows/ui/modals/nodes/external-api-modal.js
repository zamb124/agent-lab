/**
 * ExternalApiNodeModal - модалка редактирования External API Node
 */
import { html, css } from 'lit';
import { BaseNodeModal } from './base-node-modal.js';

export class ExternalApiNodeModal extends BaseNodeModal {
    static styles = [
        BaseNodeModal.styles,
        css`
            .api-section {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }
            
            .url-row {
                display: flex;
                gap: var(--space-3);
            }
            
            .url-input {
                flex: 1;
            }
            
            .method-select {
                width: 120px;
            }
        `
    ];

    getNodeType() {
        return 'external_api';
    }

    getModalTitle() {
        return this.i18n.t('node_modal.titles.external_api');
    }

    _buildConfig() {
        const name = this.shadowRoot.querySelector('[name="name"]')?.value?.trim() || '';
        const url = this.shadowRoot.querySelector('[name="url"]')?.value?.trim() || '';
        const method = this.shadowRoot.querySelector('[name="method"]')?.value || 'GET';
        
        if (!url) {
            throw new Error(this.i18n.t('node_modal.external_api.err_url'));
        }
        
        const config = {
            type: 'external_api',
            url,
            method,
        };
        
        if (name) config.name = name;
        
        const authHeadersEditor = this.shadowRoot.querySelector('json-field-editor[name="auth_headers"]');
        if (authHeadersEditor?.getValue()?.trim()) {
            if (!authHeadersEditor.isValid()) {
                throw new Error(this.i18n.t('node_modal.external_api.err_auth_headers'));
            }
            config.auth_headers = authHeadersEditor.getParsedValue();
        }
        
        const parametersEditor = this.shadowRoot.querySelector('json-field-editor[name="parameters"]');
        if (parametersEditor?.getValue()?.trim()) {
            if (!parametersEditor.isValid()) {
                throw new Error(this.i18n.t('node_modal.external_api.err_parameters'));
            }
            config.parameters = parametersEditor.getParsedValue();
        }
        
        const stateMappingEditor = this.shadowRoot.querySelector('json-field-editor[name="state_mapping"]');
        if (stateMappingEditor?.getValue()?.trim()) {
            if (!stateMappingEditor.isValid()) {
                throw new Error(this.i18n.t('node_modal.external_api.err_state_mapping'));
            }
            config.state_mapping = stateMappingEditor.getParsedValue();
        }
        
        return this._applyStateSettings(config);
    }

    renderBody() {
        const config = this.nodeConfig;
        
        return html`
            <div class="form-layout">
                <div class="form-sidebar">
                    <div class="form-group">
                        <label class="form-label">${this.i18n.t('node_modal.common.node_id_label')}</label>
                        <input 
                            type="text" 
                            name="node_id"
                            class="form-input ${this.isEdit ? 'readonly' : ''}"
                            .value=${this.nodeId || ''}
                            ?readonly=${this.isEdit}
                            placeholder="my_api_node"
                            required
                        />
                    </div>
                    
                    <div class="form-group">
                        <label class="form-label">${this.i18n.t('node_modal.common.field_name')}</label>
                        <input 
                            type="text" 
                            name="name"
                            class="form-input"
                            .value=${config.name || ''}
                            placeholder=${this.i18n.t('node_modal.external_api.placeholder_name')}
                        />
                    </div>
                    
                    <div class="api-section">
                        <div class="form-group">
                            <label class="form-label">${this.i18n.t('node_modal.external_api.url_label')}</label>
                            <input 
                                type="text" 
                                name="url"
                                class="form-input"
                                .value=${config.url || ''}
                                placeholder="https://api.example.com/endpoint"
                                required
                            />
                        </div>
                        
                        <div class="form-group">
                            <label class="form-label">${this.i18n.t('node_modal.external_api.method_label')}</label>
                            <select name="method" class="form-select">
                                <option value="GET" ?selected=${!config.method || config.method === 'GET'}>GET</option>
                                <option value="POST" ?selected=${config.method === 'POST'}>POST</option>
                                <option value="PUT" ?selected=${config.method === 'PUT'}>PUT</option>
                                <option value="DELETE" ?selected=${config.method === 'DELETE'}>DELETE</option>
                            </select>
                        </div>
                    </div>
                    
                    <div class="form-group">
                        <label class="form-label">${this.i18n.t('node_modal.external_api.auth_headers_label')}</label>
                        <json-field-editor
                            name="auth_headers"
                            .value=${config.auth_headers ? JSON.stringify(config.auth_headers, null, 2) : '{}'}
                            min-height="80"
                            placeholder='{"Authorization": "Bearer @var:token"}'
                            hint=${this.i18n.t('node_modal.external_api.var_path_hint')}
                        ></json-field-editor>
                    </div>
                    
                    ${this.renderStateSettings()}
                </div>
                
                <div class="form-main">
                    <div class="form-group">
                        <label class="form-label">${this.i18n.t('node_modal.external_api.parameters_label')}</label>
                        <json-field-editor
                            name="parameters"
                            .value=${config.parameters ? JSON.stringify(config.parameters, null, 2) : '[]'}
                            min-height="120"
                            placeholder='[{"name": "city", "source": "@state:user.city", "location": "query"}]'
                            hint=${this.i18n.t('node_modal.external_api.parameters_hint')}
                        ></json-field-editor>
                    </div>
                    
                    <div class="form-group">
                        <label class="form-label">${this.i18n.t('node_modal.external_api.state_mapping_label')}</label>
                        <json-field-editor
                            name="state_mapping"
                            .value=${config.state_mapping ? JSON.stringify(config.state_mapping, null, 2) : '{}'}
                            min-height="80"
                            placeholder='{"result": "api_response.data"}'
                            hint=${this.i18n.t('node_modal.external_api.state_mapping_hint')}
                        ></json-field-editor>
                    </div>
                    
                    <test-panel
                        .flowId=${this.flowId || ''}
                        .inputState=${this._buildDefaultState()}
                        .defaultInputState=${this._buildDefaultState()}
                        @validate=${this._onValidate}
                        @execute=${this._onExecute}
                    ></test-panel>
                </div>
            </div>
        `;
    }
}

customElements.define('external-api-modal', ExternalApiNodeModal);


