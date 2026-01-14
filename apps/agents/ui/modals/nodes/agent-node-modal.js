/**
 * AgentNodeModal - модалка редактирования Agent Node (вызов субагента)
 */
import { html, css } from 'lit';
import { BaseNodeModal } from './base-node-modal.js';

export class AgentNodeModal extends BaseNodeModal {
    static styles = [
        BaseNodeModal.styles,
        css`
            .agent-section {
                padding: var(--space-3);
                background: var(--glass-tint-subtle);
                border-radius: var(--radius-md);
            }
            
            .agent-title {
                margin-bottom: var(--space-3);
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-secondary);
            }
        `
    ];

    static properties = {
        ...BaseNodeModal.properties,
        availableAgents: { type: Array },
        availableSkills: { type: Array },
        selectedAgentId: { type: String },
    };

    constructor() {
        super();
        this.availableAgents = [];
        this.availableSkills = [];
        this.selectedAgentId = '';
    }

    getNodeType() {
        return 'agent';
    }

    getModalTitle() {
        return 'Agent Node';
    }

    showModal(nodeId = '', config = {}) {
        super.showModal(nodeId, config);
        this.selectedAgentId = config.agent_id || '';
        this._loadAgents();
    }

    async _loadAgents() {
        if (!this.a2a) {
            throw new Error('[AgentNodeModal] a2a service not available');
        }
        
        const agents = await this.a2a.getAgents();
        this.availableAgents = agents.filter(a => a.agent_id !== this.agentId);
        
        if (this.selectedAgentId) {
            this._loadSkills(this.selectedAgentId);
        }
    }

    _loadSkills(agentId) {
        const agent = this.availableAgents.find(a => a.agent_id === agentId);
        if (agent?.skills) {
            this.availableSkills = Object.entries(agent.skills).map(([id, skill]) => ({
                skill_id: id,
                name: skill.name || id,
            }));
        } else {
            this.availableSkills = [];
        }
    }

    _onAgentChange(e) {
        this.selectedAgentId = e.target.value;
        this._loadSkills(this.selectedAgentId);
    }

    _buildDefaultState() {
        return {
            content: 'Текст запроса пользователя',
            messages: [],
            variables: this.agentVariables || {},
            user_query: 'Пример значения',
        };
    }

    _buildConfig() {
        const name = this.shadowRoot.querySelector('[name="name"]')?.value?.trim() || '';
        const agentId = this.shadowRoot.querySelector('[name="agent_id"]')?.value?.trim() || '';
        const skillId = this.shadowRoot.querySelector('[name="skill_id"]')?.value?.trim() || 'default';
        
        if (!agentId) {
            throw new Error('Agent обязателен');
        }
        
        const config = {
            type: 'agent',
            agent_id: agentId,
            skill_id: skillId,
        };
        
        if (name) config.name = name;
        
        const inputMappingEditor = this.shadowRoot.querySelector('input-mapping-editor');
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
                            placeholder="my_agent_node"
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
                            placeholder="Обработчик заказов"
                        />
                    </div>
                    
                    <div class="agent-section">
                        <div class="agent-title">Вызываемый агент</div>
                        
                        <div class="form-group">
                            <label class="form-label">Agent *</label>
                            <select 
                                name="agent_id" 
                                class="form-select"
                                .value=${this.selectedAgentId}
                                @change=${this._onAgentChange}
                                required
                            >
                                <option value="">Выберите agent...</option>
                                ${this.availableAgents.map(agent => html`
                                    <option 
                                        value=${agent.agent_id}
                                        ?selected=${agent.agent_id === this.selectedAgentId}
                                    >
                                        ${agent.name || agent.agent_id} (${agent.agent_id})
                                    </option>
                                `)}
                            </select>
                            <span class="form-hint">Вложенный agent для вызова</span>
                        </div>
                        
                        <div class="form-group">
                            <label class="form-label">Skill</label>
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
                            <span class="form-hint">Skill вложенного agent</span>
                        </div>
                    </div>
                    
                    ${this.renderStateSettings()}
                </div>
                
                <div class="form-main">
                    <div class="form-group">
                        <input-mapping-editor
                            .mappings=${this._parseMappings(config.input_mapping)}
                            .availableState=${this._buildDefaultState()}
                        ></input-mapping-editor>
                    </div>
                    
                    <test-panel
                        .inputState=${this._buildDefaultState()}
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

customElements.define('agent-node-modal', AgentNodeModal);

