/**
 * RemoteFlowNodeModal - модалка ноды remote_flow (A2A)
 */
import { html, css } from 'lit';
import { BaseNodeModal } from './base-node-modal.js';

export class RemoteFlowNodeModal extends BaseNodeModal {
    static styles = [
        BaseNodeModal.styles,
        css`
            .connection-section {
                padding: var(--space-3);
                background: var(--glass-tint-subtle);
                border-radius: var(--radius-md);
            }
            
            .connection-title {
                margin-bottom: var(--space-3);
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-secondary);
            }
        `
    ];

    getNodeType() {
        return 'remote_flow';
    }

    getModalTitle() {
        return 'Remote A2A flow';
    }

    _buildConfig() {
        const name = this.shadowRoot.querySelector('[name="name"]')?.value?.trim() || '';
        const url = this.shadowRoot.querySelector('[name="url"]')?.value?.trim() || '';
        const skillId = this.shadowRoot.querySelector('[name="skill_id"]')?.value?.trim() || 'default';
        
        if (!url) {
            throw new Error('URL обязателен');
        }
        
        const config = {
            type: 'remote_flow',
            url,
            skill_id: skillId,
        };
        
        if (name) config.name = name;
        
        const authHeadersEditor = this.shadowRoot.querySelector('json-field-editor[name="auth_headers"]');
        if (authHeadersEditor?.getValue()?.trim()) {
            if (!authHeadersEditor.isValid()) {
                throw new Error('Неверный формат Auth Headers JSON');
            }
            const headers = authHeadersEditor.getParsedValue();
            if (Object.keys(headers).length > 0) {
                config.auth_headers = headers;
            }
        }
        
        const inputMappingEditor = this.shadowRoot.querySelector('state-mapping-editor');
        const inputMapping = inputMappingEditor?.getValue() || {};
        if (Object.keys(inputMapping).length > 0) {
            config.input_mapping = inputMapping;
        }
        
        return this._applyStateSettings(config);
    }

    renderBody() {
        const config = this.nodeConfig;
        
        return html`
            <div class="form-layout">
                <div class="form-sidebar">
                    <div class="form-group">
                        <label class="form-label">Node ID *</label>
                        <input 
                            type="text" 
                            name="node_id"
                            class="form-input ${this.isEdit ? 'readonly' : ''}"
                            .value=${this.nodeId || ''}
                            ?readonly=${this.isEdit}
                            placeholder="my_remote_flow"
                            required
                        />
                    </div>
                    
                    <div class="form-group">
                        <label class="form-label">Имя</label>
                        <input 
                            type="text" 
                            name="name"
                            class="form-input"
                            .value=${config.name || ''}
                            placeholder="Удалённый агент"
                        />
                    </div>
                    
                    <div class="connection-section">
                        <div class="connection-title">Подключение</div>
                        
                        <div class="form-group">
                            <label class="form-label">URL *</label>
                            <input 
                                type="text" 
                                name="url"
                                class="form-input"
                                .value=${config.url || ''}
                                placeholder="http://agent:8080"
                                required
                            />
                            <span class="form-hint">Поддерживает @var:path (например: @var:config.agent_url)</span>
                        </div>
                        
                        <div class="form-group">
                            <label class="form-label">Skill ID</label>
                            <input 
                                type="text" 
                                name="skill_id"
                                class="form-input"
                                .value=${config.skill_id || 'default'}
                                placeholder="default"
                            />
                        </div>
                        
                        <div class="form-group">
                            <label class="form-label">Auth Headers (JSON)</label>
                            <json-field-editor
                                name="auth_headers"
                                .value=${config.auth_headers ? JSON.stringify(config.auth_headers, null, 2) : '{}'}
                                min-height="80"
                                placeholder='{"Authorization": "Bearer @var:token"}'
                                hint="Поддерживает @var:path для переменных"
                            ></json-field-editor>
                        </div>
                    </div>
                    
                    ${this.renderStateSettings()}
                </div>
                
                <div class="form-main">
                    <div class="form-group">
                        <state-mapping-editor
                            mode="input"
                            .mappings=${config.input_mapping || {}}
                            .stateVariables=${Object.keys(this._buildDefaultState())}
                        ></state-mapping-editor>
                        <span class="form-hint">Определяет какие поля из state передать удалённому агенту</span>
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

    _parseMappings(mapping) {
        if (!mapping) return [];
        return Object.entries(mapping).map(([param, source]) => ({
            param,
            source,
            id: crypto.randomUUID(),
        }));
    }
}

customElements.define('remote-flow-modal', RemoteFlowNodeModal);


