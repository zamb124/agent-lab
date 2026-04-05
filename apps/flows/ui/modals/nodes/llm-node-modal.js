/**
 * LlmNodeModal - модалка редактирования LLM Node (LLM агент с tools)
 */
import { html, css } from 'lit';
import { BaseNodeModal } from './base-node-modal.js';
import '@platform/lib/components/prompt-editor.js';
import '@platform/lib/components/platform-switch.js';

export class LlmNodeModal extends BaseNodeModal {
    static styles = [
        BaseNodeModal.styles,
        css`
            .tools-section {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }
            
            .tools-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
            }
            
            .tools-actions {
                display: flex;
                gap: var(--space-2);
            }
            
            .tool-add-btn {
                padding: var(--space-1) var(--space-2);
                font-size: var(--text-xs);
                color: var(--accent);
                background: var(--accent-subtle);
                border: none;
                border-radius: var(--radius-sm);
                cursor: pointer;
            }
            
            .tool-add-btn:hover {
                background: var(--accent);
                color: white;
            }
            
            .tools-list {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
                min-height: 40px;
                padding: var(--space-2);
                background: var(--glass-tint-subtle);
                border-radius: var(--radius-md);
            }
            
            .tool-tag {
                display: flex;
                align-items: center;
                gap: var(--space-1);
                padding: var(--space-1) var(--space-2);
                font-size: var(--text-xs);
                color: var(--text-primary);
                background: var(--accent-subtle);
                border-radius: var(--radius-sm);
            }
            
            .tool-tag-remove {
                display: flex;
                align-items: center;
                justify-content: center;
                width: 14px;
                height: 14px;
                color: var(--text-secondary);
                background: none;
                border: none;
                cursor: pointer;
            }
            
            .tool-tag-remove:hover {
                color: var(--error);
            }
            
            .tools-empty {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
            }
            
            .react-loop-section {
                padding: var(--space-3);
                background: var(--glass-tint-subtle);
                border-radius: var(--radius-md);
            }
            
            .loop-options {
                margin-top: var(--space-3);
            }

            .loop-explicit-row {
                display: grid;
                grid-template-columns: 1fr;
                gap: var(--space-3);
                align-items: start;
            }

            .loop-explicit-row.has-reminder {
                grid-template-columns: 1fr 1fr;
            }

            @media (max-width: 520px) {
                .loop-explicit-row.has-reminder {
                    grid-template-columns: 1fr;
                }
            }

            .loop-explicit-left {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                min-width: 0;
            }

            .loop-explicit-strict-block {
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
            }

            .loop-explicit-reminder {
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
                min-width: 0;
            }
            
            .prompt-section {
                flex: 1;
                display: flex;
                flex-direction: column;
            }
            
            .mode-toggle-section {
                padding: var(--space-3);
                background: var(--glass-tint-subtle);
                border-radius: var(--radius-md);
                margin-bottom: var(--space-3);
            }
            
            .mode-toggle-row {
                display: flex;
                align-items: center;
                gap: var(--space-3);
            }
            
            .mode-option {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-sm);
                cursor: pointer;
                transition: all 0.2s;
            }
            
            .mode-option.active {
                background: var(--accent-subtle);
                color: var(--accent);
            }
            
            .mode-option input[type="radio"] {
                width: 16px;
                height: 16px;
                cursor: pointer;
            }
            
            .output-schema-section {
                margin-top: var(--space-3);
            }
            
            .schema-editor {
                width: 100%;
                min-height: 150px;
                font-family: var(--font-mono);
                font-size: var(--text-sm);
                padding: var(--space-2);
                border: 1px solid var(--border);
                border-radius: var(--radius-sm);
                background: var(--bg-primary);
                color: var(--text-primary);
                resize: vertical;
            }
            
            .schema-editor:focus {
                outline: none;
                border-color: var(--accent);
            }
            
            .schema-hint {
                margin-top: var(--space-2);
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
        `
    ];

    static properties = {
        ...BaseNodeModal.properties,
        selectedTools: { type: Array },
        loopMode: { type: String },
        exitTool: { type: String },
        strictMode: { type: Boolean },
        structuredOutput: { type: Boolean },
        outputSchema: { type: Object },
        outputMapping: { type: Object },
    };

    constructor() {
        super();
        this.selectedTools = [];
        this.loopMode = 'auto';
        this.exitTool = '';
        this.strictMode = true;
        this.structuredOutput = false;
        this.outputSchema = this._getDefaultSchema();
        this.outputMapping = {};
    }
    
    _getDefaultSchema() {
        return {
            type: "object",
            properties: {
                result: { type: "string", description: "Execution result" }
            },
            required: ["result"],
            additionalProperties: false
        };
    }

    getNodeType() {
        return 'llm_node';
    }

    getModalTitle() {
        return this.i18n.t('node_modal.titles.llm_node');
    }

    showModal(nodeId = '', config = {}) {
        super.showModal(nodeId, config);
        
        this.selectedTools = this._parseTools(config.tools || []);
        
        const react = config.react || {};
        this.loopMode = react.loop_mode || 'auto';
        this.exitTool = react.exit_tool || '';
        this.strictMode = react.strict !== false;
        
        this.structuredOutput = config.structured_output || false;
        this.outputSchema = config.output_schema || this._getDefaultSchema();
        this.outputMapping = config.output_mapping || {};

        queueMicrotask(() => {
            const editor = this.shadowRoot?.querySelector('llm-config-editor');
            if (editor) {
                editor.setValue(config.llm && typeof config.llm === 'object' ? config.llm : {});
            }
        });
    }

    _parseTools(tools) {
        return tools.map(t => {
            if (typeof t === 'string') {
                return { tool_id: t, name: t };
            }
            return { tool_id: t.tool_id, name: t.name || t.tool_id };
        });
    }

    _addTool() {
        const toolId = prompt(this.i18n.t('llm_node.prompt_tool_id'));
        if (toolId && !this.selectedTools.find(t => t.tool_id === toolId)) {
            this.selectedTools = [...this.selectedTools, { tool_id: toolId, name: toolId }];
        }
    }

    _removeTool(toolId) {
        this.selectedTools = this.selectedTools.filter(t => t.tool_id !== toolId);
    }

    _onLoopModeChange(e) {
        this.loopMode = e.target.value;
    }

    _onExitToolChange(e) {
        this.exitTool = e.target.value;
    }

    _onStrictModeSwitchChange(e) {
        this.strictMode = e.detail.value;
    }
    
    _onModeChange(mode) {
        this.structuredOutput = mode === 'structured';
        if (this.structuredOutput) {
            this.selectedTools = [];
        }
    }
    
    _onOutputSchemaChange(e) {
        try {
            this.outputSchema = JSON.parse(e.target.value);
        } catch (err) {
            // Невалидный JSON - не обновляем
        }
    }
    
    _onOutputMappingChange(e) {
        try {
            const value = e.target.value.trim();
            this.outputMapping = value ? JSON.parse(value) : {};
        } catch (err) {
            // Невалидный JSON - не обновляем
        }
    }

    _buildConfig() {
        const nameInput = this.shadowRoot.querySelector('[name="name"]');
        const name = nameInput ? (nameInput.value.trim() || '') : '';
        
        const descInput = this.shadowRoot.querySelector('[name="description"]');
        const description = descInput ? (descInput.value.trim() || '') : '';
        
        const promptEditor = this.shadowRoot.querySelector('prompt-editor');
        const prompt = promptEditor ? promptEditor.getValue() : '';
        
        const reminderInput = this.shadowRoot.querySelector('[name="reminder_message"]');
        const reminderMessage = reminderInput ? (reminderInput.value.trim() || '') : '';
        
        const llmEditor = this.shadowRoot.querySelector('llm-config-editor');
        if (!llmEditor) {
            throw new Error('[LlmNodeModal] LLM editor not found');
        }
        const llm = llmEditor.getValue();
        
        const tagsEditor = this.shadowRoot.querySelector('tag-input');
        const tags = tagsEditor ? tagsEditor.getTags() : [];
        
        const inputMappingEditor = this.shadowRoot.querySelector('state-mapping-editor');
        const inputMapping = inputMappingEditor ? inputMappingEditor.getValue() : {};
        
        const config = {
            type: 'llm_node',
            name,
            description: description || undefined,
            prompt,
            llm,
            tags: tags.length > 0 ? tags : undefined,
        };
        
        if (this.structuredOutput) {
            config.structured_output = true;
            config.output_schema = this.outputSchema;
            if (Object.keys(this.outputMapping).length > 0) {
                config.output_mapping = this.outputMapping;
            }
        } else {
            config.tools = this.selectedTools.map(t => t.tool_id);
            
            if (this.loopMode === 'explicit') {
                const exitTool = this.exitTool || (this.selectedTools.length > 0 ? this.selectedTools[0].tool_id : 'finish');
                config.react = {
                    loop_mode: 'explicit',
                    exit_tool: exitTool,
                    strict: this.strictMode,
                };
                if (reminderMessage) {
                    config.react.reminder_message = reminderMessage;
                }
            }
        }
        
        if (Object.keys(inputMapping).length > 0) {
            config.input_mapping = inputMapping;
        }
        
        return this._applyStateSettings(config);
    }

    renderBody() {
        const config = this.nodeConfig;
        const react = config.react || {};
        
        return html`
            <div class="form-layout">
                <div class="form-sidebar">
                    <div class="form-group">
                        <label class="form-label">${this.i18n.t('llm_node.node_id_label')}</label>
                        <input 
                            type="text" 
                            name="node_id"
                            class="form-input ${this.isEdit ? 'readonly' : ''}"
                            .value=${this.nodeId || config.node_id || ''}
                            ?readonly=${this.isEdit}
                            placeholder="my_llm_node"
                            required
                        />
                    </div>
                    
                    <div class="form-group">
                        <label class="form-label">${this.i18n.t('llm_node.field_name_required')}</label>
                        <input 
                            type="text" 
                            name="name"
                            class="form-input"
                            .value=${config.name || ''}
                            placeholder=${this.i18n.t('llm_node.placeholder_agent_name')}
                            required
                        />
                    </div>
                    
                    <div class="form-group">
                        <label class="form-label">${this.i18n.t('llm_node.field_description')}</label>
                        <textarea 
                            name="description"
                            class="form-textarea"
                            rows="2"
                            .value=${config.description || ''}
                            placeholder=${this.i18n.t('llm_node.placeholder_description')}
                        ></textarea>
                    </div>
                    
                    <div class="form-group">
                        <label class="form-label">${this.i18n.t('llm_node.field_tags')}</label>
                        <tag-input .tags=${config.tags || []}></tag-input>
                    </div>
                    
                    <div class="mode-toggle-section">
                        <label class="form-label">${this.i18n.t('llm_node.section_output_mode')}</label>
                        <div class="mode-toggle-row">
                            <label class="mode-option ${!this.structuredOutput ? 'active' : ''}">
                                <input 
                                    type="radio" 
                                    name="output-mode"
                                    .checked=${!this.structuredOutput}
                                    @change=${() => this._onModeChange('tools')}
                                />
                                ${this.i18n.t('llm_node.output_mode_tools')}
                            </label>
                            <label class="mode-option ${this.structuredOutput ? 'active' : ''}">
                                <input 
                                    type="radio" 
                                    name="output-mode"
                                    .checked=${this.structuredOutput}
                                    @change=${() => this._onModeChange('structured')}
                                />
                                ${this.i18n.t('llm_node.output_mode_structured')}
                            </label>
                        </div>
                        <span class="form-hint">${this.i18n.t('llm_node.output_mode_hint')}</span>
                    </div>
                    
                    ${!this.structuredOutput ? html`
                        <div class="form-group tools-section">
                            <div class="tools-header">
                                <label class="form-label">${this.i18n.t('llm_node.section_tools')}</label>
                                <div class="tools-actions">
                                    <button type="button" class="tool-add-btn" @click=${this._addTool}>
                                        ${this.i18n.t('llm_node.add_tool')}
                                    </button>
                                </div>
                            </div>
                            <div class="tools-list">
                                ${this.selectedTools.length > 0 
                                    ? this.selectedTools.map(tool => html`
                                        <span class="tool-tag">
                                            <platform-icon name="tool" size="12"></platform-icon>
                                            ${tool.name}
                                            <button 
                                                type="button" 
                                                class="tool-tag-remove"
                                                @click=${() => this._removeTool(tool.tool_id)}
                                            >×</button>
                                        </span>
                                    `)
                                    : html`<span class="tools-empty">${this.i18n.t('llm_node.empty_tools')}</span>`
                                }
                            </div>
                        </div>
                    ` : html`
                        <div class="form-group output-schema-section">
                            <label class="form-label">${this.i18n.t('llm_node.output_schema_label')}</label>
                            <textarea
                                class="schema-editor"
                                .value=${JSON.stringify(this.outputSchema, null, 2)}
                                @change=${this._onOutputSchemaChange}
                                @blur=${this._onOutputSchemaChange}
                                rows="10"
                            ></textarea>
                            <div class="schema-hint">
                                ${this.i18n.t('llm_node.output_schema_body_hint')}
                            </div>
                        </div>
                        
                        <div class="form-group output-schema-section">
                            <label class="form-label">${this.i18n.t('llm_node.output_mapping_label')}</label>
                            <textarea
                                class="schema-editor"
                                .value=${JSON.stringify(this.outputMapping, null, 2)}
                                @change=${this._onOutputMappingChange}
                                @blur=${this._onOutputMappingChange}
                                rows="4"
                                placeholder='{"result_field": "state_field"}'
                            ></textarea>
                            <div class="schema-hint">
                                ${this.i18n.t('llm_node.output_mapping_body_hint')}
                            </div>
                        </div>
                    `}
                    
                    <div class="form-group">
                        <label class="form-label">${this.i18n.t('llm_node.section_llm')}</label>
                        <llm-config-editor
                            model=${config.llm ? (config.llm.model || 'gpt-4o') : 'gpt-4o'}
                            temperature=${config.llm && config.llm.temperature !== undefined ? config.llm.temperature : 0.2}
                            max-tokens=${config.llm ? (config.llm.max_tokens || '') : ''}
                            provider=${config.llm ? (config.llm.provider || '') : ''}
                            api-key=${config.llm ? (config.llm.api_key || '') : ''}
                            base-url=${config.llm ? (config.llm.base_url || '') : ''}
                        ></llm-config-editor>
                    </div>
                    
                    ${!this.structuredOutput ? html`
                        <div class="react-loop-section">
                            <label class="form-label">${this.i18n.t('llm_node.section_react_loop')}</label>
                            <select 
                                class="form-select"
                                .value=${this.loopMode}
                                @change=${this._onLoopModeChange}
                            >
                                <option value="auto">${this.i18n.t('llm_node.loop_mode_auto')}</option>
                                <option value="explicit">${this.i18n.t('llm_node.loop_mode_explicit')}</option>
                            </select>
                            <span class="form-hint">${this.i18n.t('llm_node.loop_mode_hint')}</span>
                            
                            ${this.loopMode === 'explicit' ? html`
                                <div class="loop-options">
                                    <div class="loop-explicit-row ${this.strictMode ? 'has-reminder' : ''}">
                                        <div class="loop-explicit-left">
                                            <div class="loop-explicit-strict-block">
                                                <platform-switch
                                                    ?checked=${this.strictMode}
                                                    size="sm"
                                                    .label=${this.i18n.t('llm_node.strict_mode_label')}
                                                    @change=${this._onStrictModeSwitchChange}
                                                ></platform-switch>
                                                <span class="form-hint">${this.i18n.t('llm_node.strict_mode_hint')}</span>
                                            </div>
                                            <div class="form-group" style="margin: 0;">
                                                <label class="form-label">${this.i18n.t('llm_node.exit_tool_label')}</label>
                                                <select
                                                    class="form-select"
                                                    .value=${this.exitTool}
                                                    @change=${this._onExitToolChange}
                                                >
                                                    ${this.selectedTools.map(t => html`
                                                        <option value=${t.tool_id}>${t.name}</option>
                                                    `)}
                                                </select>
                                                <span class="form-hint">${this.i18n.t('llm_node.exit_tool_hint')}</span>
                                            </div>
                                        </div>
                                        ${this.strictMode ? html`
                                            <div class="loop-explicit-reminder">
                                                <label class="form-label">${this.i18n.t('llm_node.reminder_text_label')}</label>
                                                <textarea
                                                    name="reminder_message"
                                                    class="form-textarea"
                                                    rows="3"
                                                    .value=${react.reminder_message || ''}
                                                    placeholder=${this.i18n.t('llm_node.reminder_placeholder')}
                                                ></textarea>
                                                <span class="form-hint">${this.i18n.t('llm_node.reminder_hint')}</span>
                                            </div>
                                        ` : ''}
                                    </div>
                                </div>
                            ` : ''}
                        </div>
                    ` : ''}
                    
                    ${this.renderStateSettings()}
                </div>
                
                <div class="form-main">
                    <div class="prompt-section">
                        <div class="form-group" style="flex: 1;">
                            <prompt-editor
                                name="prompt"
                                .value=${config.prompt || ''}
                                .variables=${this.flowVariables || {}}
                                label=${this.i18n.t('llm_node.prompt_label_required')}
                                placeholder=${this.i18n.t('llm_node.prompt_placeholder')}
                                min-height="200"
                                show-ai-button="false"
                            ></prompt-editor>
                        </div>
                    </div>
                    
                    <div class="form-group">
                        <state-mapping-editor
                            mode="input"
                            .mappings=${config.input_mapping || {}}
                            .stateVariables=${Object.keys(this._buildDefaultState())}
                        ></state-mapping-editor>
                    </div>
                    
                    <test-panel
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

customElements.define('llm-node-modal', LlmNodeModal);

