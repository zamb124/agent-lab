/**
 * FlowNodeModal - нода вызова другого flow (type в конфиге: flow)
 */
import { html, css } from 'lit';
import { BaseNodeModal } from './base-node-modal.js';

export class FlowNodeModal extends BaseNodeModal {
    static styles = [
        BaseNodeModal.styles,
        css`
            .flow-section {
                padding: var(--space-3);
                background: var(--glass-tint-subtle);
                border-radius: var(--radius-md);
            }
            
            .flow-section-title {
                margin-bottom: var(--space-3);
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-secondary);
            }
        `
    ];

    static properties = {
        ...BaseNodeModal.properties,
        availableFlows: { type: Array },
        availableSkills: { type: Array },
        selectedFlowId: { type: String },
    };

    constructor() {
        super();
        this.availableFlows = [];
        this.availableSkills = [];
        this.selectedFlowId = '';
    }

    getNodeType() {
        return 'flow';
    }

    getModalTitle() {
        return this.i18n.t('node_modal.titles.flow');
    }

    showModal(nodeId = '', config = {}) {
        super.showModal(nodeId, config);
        this.selectedFlowId = config.flow_id || '';
        this._loadFlows();
    }

    async _loadFlows() {
        if (!this.a2a) {
            throw new Error('[FlowNodeModal] a2a service not available');
        }
        
        const listed = await this.a2a.listFlows();
        this.availableFlows = listed.filter(a => a.flow_id !== this.flowId);
        
        if (this.selectedFlowId) {
            this._loadSkills(this.selectedFlowId);
        }
    }

    _loadSkills(flowId) {
        const callee = this.availableFlows.find(a => a.flow_id === flowId);
        if (callee?.skills) {
            this.availableSkills = Object.entries(callee.skills).map(([id, skill]) => ({
                skill_id: id,
                name: skill.name || id,
            }));
        } else {
            this.availableSkills = [];
        }
    }

    _onCalleeFlowChange(e) {
        this.selectedFlowId = e.target.value;
        this._loadSkills(this.selectedFlowId);
    }

    _buildConfig() {
        const name = this.shadowRoot.querySelector('[name="name"]')?.value?.trim() || '';
        const flowId = this.shadowRoot.querySelector('[name="flow_id"]')?.value?.trim() || '';
        const skillId = this.shadowRoot.querySelector('[name="skill_id"]')?.value?.trim() || 'default';
        
        if (!flowId) {
            throw new Error(this.i18n.t('node_modal.flow.err_target_flow'));
        }
        
        const config = {
            type: 'flow',
            flow_id: flowId,
            skill_id: skillId,
        };
        
        if (name) config.name = name;
        
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
                        <label class="form-label">${this.i18n.t('node_modal.common.node_id_label')}</label>
                        <input 
                            type="text" 
                            name="node_id"
                            class="form-input ${this.isEdit ? 'readonly' : ''}"
                            .value=${this.nodeId || ''}
                            ?readonly=${this.isEdit}
                            placeholder="my_node_id"
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
                            placeholder=${this.i18n.t('node_modal.flow.placeholder_name')}
                        />
                    </div>
                    
                    <div class="flow-section">
                        <div class="flow-section-title">${this.i18n.t('node_modal.flow.section_title')}</div>
                        
                        <div class="form-group">
                            <label class="form-label">${this.i18n.t('node_modal.flow.flow_label')}</label>
                            <select 
                                name="flow_id" 
                                class="form-select"
                                .value=${this.selectedFlowId}
                                @change=${this._onCalleeFlowChange}
                                required
                            >
                                <option value="">${this.i18n.t('node_modal.flow.select_flow')}</option>
                                ${this.availableFlows.map(flowItem => html`
                                    <option 
                                        value=${flowItem.flow_id}
                                        ?selected=${flowItem.flow_id === this.selectedFlowId}
                                    >
                                        ${flowItem.name || flowItem.flow_id} (${flowItem.flow_id})
                                    </option>
                                `)}
                            </select>
                            <span class="form-hint">${this.i18n.t('node_modal.flow.flow_hint')}</span>
                        </div>
                        
                        <div class="form-group">
                            <label class="form-label">${this.i18n.t('node_modal.flow.skill_label')}</label>
                            <select name="skill_id" class="form-select">
                                <option value="default" ?selected=${!config.skill_id || config.skill_id === 'default'}>
                                    default
                                </option>
                                ${this.availableSkills.map(skill => html`
                                    <option 
                                        value=${skill.skill_id}
                                        ?selected=${skill.skill_id === config.skill_id}
                                    >
                                        ${skill.name} (${skill.skill_id})
                                    </option>
                                `)}
                            </select>
                            <span class="form-hint">${this.i18n.t('node_modal.flow.skill_hint')}</span>
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

customElements.define('flow-node-modal', FlowNodeModal);

