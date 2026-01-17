/**
 * ReactNodeEditor - редактор для react_node типа
 * LLM агент с инструментами и ReAct loop
 */
import { html, css } from 'lit';
import { BaseNodeEditor } from './base-node-editor.js';
import '@platform/lib/components/prompt-editor.js';
import '../editors/llm-config-editor.js';
import '../editors/tag-input.js';
import '../editors/test-panel.js';
import '../../modals/inline-tool-modal.js';
import '../../modals/tool-picker-modal.js';
import '../editors/json-field-editor.js';

export class ReactNodeEditor extends BaseNodeEditor {
    static styles = [
        BaseNodeEditor.styles,
        css`
            .section {
                margin-bottom: var(--space-4);
            }
            
            .section-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: var(--space-2) 0;
            }
            
            .section-title {
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-secondary);
            }
            
            .section-add-btn {
                font-size: var(--text-xs);
                color: var(--accent);
                background: none;
                border: none;
                cursor: pointer;
                padding: var(--space-1) var(--space-2);
                border-radius: var(--radius-sm);
            }
            
            .section-add-btn:hover {
                background: var(--accent-subtle);
            }
            
            .tools-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }
            
            .tool-item {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                background: var(--glass-tint-subtle);
                border-radius: var(--radius-md);
                font-size: var(--text-sm);
            }
            
            .tool-item-name {
                flex: 1;
                color: var(--text-primary);
            }
            
            .tool-item-remove {
                color: var(--text-tertiary);
                cursor: pointer;
                padding: 2px;
            }
            
            .tool-item-remove:hover {
                color: var(--error);
            }
            
            .empty-tools {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                padding: var(--space-2);
                text-align: center;
            }
            
            .tools-actions {
                display: flex;
                gap: var(--space-2);
                position: relative;
            }
            
            .tools-add-menu {
                position: absolute;
                top: 100%;
                right: 0;
                margin-top: var(--space-1);
                min-width: 180px;
                background: var(--glass-solid-strong);
                border: 1px solid var(--border-default);
                border-radius: var(--radius-md);
                box-shadow: var(--shadow-lg);
                z-index: 100;
                padding: var(--space-2);
            }
            
            .menu-item {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-sm);
                cursor: pointer;
                font-size: var(--text-sm);
                color: var(--text-primary);
                transition: background var(--duration-fast);
            }
            
            .menu-item:hover {
                background: var(--glass-tint-medium);
            }
            
            .menu-divider {
                height: 1px;
                background: var(--border-subtle);
                margin: var(--space-2) 0;
            }
            
            .loop-config {
                margin-top: var(--space-3);
                padding: var(--space-3);
                background: var(--glass-tint-subtle);
                border-radius: var(--radius-md);
            }
            
            .loop-config-row {
                margin-bottom: var(--space-3);
            }
            
            .loop-config-row:last-child {
                margin-bottom: 0;
            }
            
            .checkbox-row {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                margin-top: var(--space-2);
            }
            
            .checkbox-row input[type="checkbox"] {
                width: 16px;
                height: 16px;
                cursor: pointer;
            }
            
            .checkbox-row label {
                cursor: pointer;
                font-size: var(--text-sm);
                color: var(--text-primary);
            }
            
            .tool-item.is-inline {
                background: var(--accent-subtle);
                border: 1px solid var(--accent-light);
            }
            
            .tool-item.is-agent .tool-item-icon {
                color: #9333ea;
            }
            
            .tool-item.is-mcp {
                background: rgba(16, 185, 129, 0.1);
                border: 1px solid rgba(16, 185, 129, 0.3);
            }
            
            .tool-item.is-mcp .tool-item-icon {
                color: #10b981;
            }
            
            .tool-item-name {
                cursor: pointer;
            }
            
            .tool-item-name:hover {
                color: var(--accent);
            }
            
            .mode-toggle-row {
                display: flex;
                gap: var(--space-3);
                margin-bottom: var(--space-2);
            }
            
            .mode-option {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                background: var(--glass-tint-subtle);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                cursor: pointer;
                font-size: var(--text-sm);
                transition: all var(--duration-fast);
            }
            
            .mode-option:hover {
                border-color: var(--accent-light);
            }
            
            .mode-option.active {
                background: var(--accent-subtle);
                border-color: var(--accent);
                color: var(--accent);
            }
            
            .mode-option input[type="radio"] {
                display: none;
            }
        `
    ];

    static properties = {
        ...BaseNodeEditor.properties,
        aiLoading: { type: Boolean },
        inlineTools: { type: Object },
        showAddMenu: { type: Boolean },
        loopMode: { type: String },
        exitTool: { type: String },
        strict: { type: Boolean },
        reminderMessage: { type: String },
        maxIterations: { type: Number },
        structuredOutput: { type: Boolean },
        outputSchema: { type: Object },
    };

    constructor() {
        super();
        this._nodeType = 'react_node';
        this.aiLoading = false;
        this.inlineTools = new Map();
        this.showAddMenu = false;
        this.loopMode = 'auto';
        this.exitTool = 'finish';
        this.strict = true;
        this.reminderMessage = '';
        this.maxIterations = 10;
        this.structuredOutput = false;
        this.outputSchema = this._getDefaultSchema();
    }
    
    _getDefaultSchema() {
        return {
            type: 'object',
            properties: {
                result: { type: 'string', description: 'Результат выполнения' }
            },
            required: ['result']
        };
    }
    
    updated(changedProperties) {
        super.updated(changedProperties);
        
        if (changedProperties.has('nodeConfig') && this.nodeConfig) {
            console.log('[ReactNodeEditor] nodeConfig changed, parsing and re-rendering...');
            this._parseTools();
            this._parseReactConfig();
        }
    }
    
    _parseTools() {
        this.inlineTools.clear();
        const tools = this.nodeConfig?.tools || [];
        for (const tool of tools) {
            if (typeof tool === 'object' && tool.tool_id) {
                this.inlineTools.set(tool.tool_id, tool);
            }
        }
    }
    
    _parseReactConfig() {
        const react = this.nodeConfig?.react || {};
        const newLoopMode = react.loop_mode || 'auto';
        const newExitTool = react.exit_tool || 'finish';
        const newStrict = react.strict !== false;
        const newReminderMessage = react.reminder_message || '';
        const newMaxIterations = react.max_iterations || 10;
        
        // Обновляем только если значения изменились
        if (this.loopMode !== newLoopMode) {
            this.loopMode = newLoopMode;
        }
        if (this.exitTool !== newExitTool) {
            this.exitTool = newExitTool;
        }
        if (this.strict !== newStrict) {
            this.strict = newStrict;
        }
        if (this.reminderMessage !== newReminderMessage) {
            this.reminderMessage = newReminderMessage;
        }
        if (this.maxIterations !== newMaxIterations) {
            this.maxIterations = newMaxIterations;
        }
        
        // Structured Output
        const newStructuredOutput = this.nodeConfig?.structured_output || false;
        const newOutputSchema = this.nodeConfig?.output_schema || this._getDefaultSchema();
        
        if (this.structuredOutput !== newStructuredOutput) {
            this.structuredOutput = newStructuredOutput;
        }
        if (JSON.stringify(this.outputSchema) !== JSON.stringify(newOutputSchema)) {
            this.outputSchema = newOutputSchema;
        }
    }
    
    _onModeChange(mode) {
        this.structuredOutput = mode === 'structured';
        this._updateConfig('structured_output', this.structuredOutput);
        if (this.structuredOutput) {
            this._updateConfig('output_schema', this.outputSchema);
        }
    }
    
    _onOutputSchemaChange(e) {
        try {
            this.outputSchema = JSON.parse(e.target.value);
            this._updateConfig('output_schema', this.outputSchema);
        } catch (err) {
            // Invalid JSON - ignore
        }
    }
    
    _onOutputSchemaJsonChange(e) {
        // json-field-editor отдаёт detail.value и detail.valid
        if (e.detail.valid) {
            try {
                this.outputSchema = JSON.parse(e.detail.value);
                this._updateConfig('output_schema', this.outputSchema);
            } catch (err) {
                // Invalid JSON - ignore
            }
        }
    }

    _onLLMChange(e) {
        this._updateConfig('llm', e.detail.value);
    }
    
    _onInputChange(field, value) {
        this._updateConfig(field, value);
    }
    
    _buildDefaultState() {
        const defaultState = {
            'route': 'default',
            'status': 'success',
            'category': 'default',
            'result': 'default',
            'type': 'default',
        };
        
        if (this.agentVariables && typeof this.agentVariables === 'object') {
            for (const key in this.agentVariables) {
                if (Object.prototype.hasOwnProperty.call(this.agentVariables, key)) {
                    const varData = this.agentVariables[key];
                    if (typeof varData === 'object' && varData !== null && 'value' in varData) {
                        defaultState[key] = varData.value;
                    } else {
                        defaultState[key] = varData;
                    }
                }
            }
        }
        
        return defaultState;
    }
    
    _onLoopModeChange(e) {
        this.loopMode = e.target.value;
        this._updateReactConfig();
    }
    
    _onExitToolChange(e) {
        this.exitTool = e.target.value;
        this._updateReactConfig();
    }
    
    _onStrictChange(e) {
        this.strict = e.target.checked;
        this._updateReactConfig();
    }
    
    _onReminderMessageChange(e) {
        this.reminderMessage = e.target.value;
        this._updateReactConfig();
    }
    
    _onMaxIterationsChange(e) {
        const value = parseInt(e.target.value, 10);
        if (!isNaN(value) && value > 0) {
            this.maxIterations = value;
            this._updateReactConfig();
        }
    }
    
    _updateReactConfig() {
        const reactConfig = {
            loop_mode: this.loopMode,
            exit_tool: this.exitTool,
            strict: this.strict,
            reminder_message: this.reminderMessage,
            max_iterations: this.maxIterations,
        };
        
        this._updateConfig('react', reactConfig);
    }

    async _generatePromptAI() {
        const prompt = this.nodeConfig.prompt || '';
        if (!prompt.trim()) {
            console.warn('Введите начальный промпт');
            return;
        }
        
        this.aiLoading = true;
        
        if (this.a2a) {
            try {
                const improved = await this.a2a.generatePromptAI(prompt, {
                    description: this.nodeConfig.description || '',
                    tools: this.nodeConfig.tools || [],
                    llm_config: this.nodeConfig.llm || {},
                    variables: Object.keys(this.agentVariables)
                });
                
                this._updateConfig('prompt', improved);
            } catch (error) {
                console.error('Ошибка генерации промпта:', error);
            }
        }
        
        this.aiLoading = false;
    }
    
    _onAddTool() {
        console.log('[ReactNodeEditor] _onAddTool called', { nodeConfig: this.nodeConfig });
        const modal = document.createElement('tool-picker-modal');
        const currentTools = (this.nodeConfig.tools || []).map(t => 
            typeof t === 'string' ? t : t.tool_id
        );
        modal.initialSelection = currentTools;
        
        modal.addEventListener('tools-selected', async (e) => {
            const selectedTools = e.detail.tools;
            
            const newTools = [];
            
            for (const toolId of selectedTools) {
                const existingTool = (this.nodeConfig.tools || []).find(t => 
                    (typeof t === 'string' ? t : t.tool_id) === toolId
                );
                
                if (existingTool) {
                    newTools.push(existingTool);
                } else {
                    try {
                        const toolData = await this.a2a.get(`/api/v1/tools/${toolId}`);
                        if (toolData && toolData.code) {
                            newTools.push({
                                tool_id: toolData.tool_id,
                                type: 'tool',
                                name: toolData.title || toolData.tool_id,
                                description: toolData.description || '',
                                code: toolData.code,
                                args_schema: toolData.args_schema || {},
                                tool_type: toolData.tool_type
                            });
                            this.inlineTools.set(toolData.tool_id, newTools[newTools.length - 1]);
                        } else {
                            newTools.push(toolId);
                        }
                    } catch (error) {
                        console.warn(`Не удалось загрузить tool ${toolId}, добавляем как ссылку`);
                        newTools.push(toolId);
                    }
                }
            }
            
            this._updateConfig('tools', newTools);
        });
        
        document.body.appendChild(modal);
        modal.showModal();
        
        modal.addEventListener('close', () => {
            modal.remove();
        }, { once: true });
    }
    
    _onAddInlineTool() {
        console.log('[ReactNodeEditor] _onAddInlineTool called');
        this.showAddMenu = !this.showAddMenu;
    }
    
    _onCreateInline(toolType) {
        this.showAddMenu = false;
        
        const modal = document.createElement('inline-tool-modal');
        modal.mode = 'create';
        modal.toolType = toolType;
        modal.agentVariables = this.agentVariables;
        modal.agentId = this.agentId;
        modal.skillId = this.skillId;
        
        modal.addEventListener('tool-saved', (e) => {
            const { toolId, config: toolConfig } = e.detail;
            const tools = [...(this.nodeConfig.tools || []), toolConfig];
            this.inlineTools.set(toolId, toolConfig);
            this._updateConfig('tools', tools);
        });
        
        document.body.appendChild(modal);
        modal.showModal();
        
        modal.addEventListener('close', () => {
            modal.remove();
        }, { once: true });
    }
    
    _isMCPTool(tool) {
        const toolId = typeof tool === 'string' ? tool : tool.tool_id;
        return toolId?.startsWith('mcp:');
    }
    
    _parseMCPToolId(toolId) {
        const parts = toolId.split(':');
        return {
            server_id: parts[1] || '',
            tool_name: parts[2] || '',
        };
    }
    
    _onEditTool(toolId) {
        // Проверяем MCP инструмент
        if (toolId.startsWith('mcp:')) {
            const { server_id, tool_name } = this._parseMCPToolId(toolId);
            
            const modal = document.createElement('inline-tool-modal');
            modal.mode = 'edit';
            modal.toolType = 'mcp';
            modal.toolConfig = {
                tool_id: toolId,
                type: 'mcp',
                server_id: server_id,
                tool_name: tool_name,
            };
            modal.agentVariables = this.agentVariables;
            modal.agentId = this.agentId;
            modal.skillId = this.skillId;
            
            modal.addEventListener('tool-saved', (e) => {
                const { toolId: savedToolId, config: savedConfig } = e.detail;
                const tools = (this.nodeConfig.tools || []).map(t => {
                    const tid = typeof t === 'string' ? t : t.tool_id;
                    return tid === toolId ? savedConfig : t;
                });
                this._updateConfig('tools', tools);
            });
            
            document.body.appendChild(modal);
            modal.showModal();
            
            modal.addEventListener('close', () => {
                modal.remove();
            }, { once: true });
            return;
        }
        
        const toolConfig = this.inlineTools.get(toolId);
        if (!toolConfig) {
            return;
        }
        
        const toolType = toolConfig.type || 'tool';
        
        const modal = document.createElement('inline-tool-modal');
        modal.mode = 'edit';
        modal.toolType = toolType;
        modal.toolConfig = toolConfig;
        modal.agentVariables = this.agentVariables;
        modal.agentId = this.agentId;
        modal.skillId = this.skillId;
        
        modal.addEventListener('tool-saved', (e) => {
            const { toolId: savedToolId, config: savedConfig } = e.detail;
            const tools = (this.nodeConfig.tools || []).map(t => {
                const tid = typeof t === 'string' ? t : t.tool_id;
                return tid === savedToolId ? savedConfig : t;
            });
            this.inlineTools.set(savedToolId, savedConfig);
            this._updateConfig('tools', tools);
        });
        
        document.body.appendChild(modal);
        modal.showModal();
        
        modal.addEventListener('close', () => {
            modal.remove();
        }, { once: true });
    }
    
    _onRemoveTool(toolId) {
        const tools = (this.config.tools || []).filter(t => {
            const tid = typeof t === 'string' ? t : t.tool_id;
            return tid !== toolId;
        });
        this.inlineTools.delete(toolId);
        this._updateConfig('tools', tools);
    }
    
    _handleOutsideClick(e) {
        if (this.showAddMenu && !e.composedPath().includes(this)) {
            this.showAddMenu = false;
        }
    }
    
    connectedCallback() {
        super.connectedCallback();
        this._handleOutsideClick = this._handleOutsideClick.bind(this);
        document.addEventListener('click', this._handleOutsideClick);
    }
    
    disconnectedCallback() {
        super.disconnectedCallback();
        document.removeEventListener('click', this._handleOutsideClick);
    }
    
    _getToolDisplayName(tool) {
        const toolId = typeof tool === 'string' ? tool : tool.tool_id;
        if (typeof tool === 'object' && tool.name) {
            return tool.name;
        }
        return toolId;
    }
    
    _isInlineTool(tool) {
        if (typeof tool === 'object' && tool.code) {
            return true;
        }
        return false;
    }
    
    _getToolIcon(tool) {
        const toolId = typeof tool === 'string' ? tool : tool.tool_id;
        
        if (toolId?.startsWith('mcp:')) {
            return 'plug';
        }
        
        if (typeof tool === 'object') {
            if (tool.type === 'agent' || tool.type === 'react_node') {
                return 'agent';
            }
        }
        return 'tool';
    }
    
    _isAgentTool(tool) {
        if (typeof tool === 'object') {
            return tool.type === 'agent' || tool.type === 'react_node';
        }
        return false;
    }

    _onToggle(field) {
        console.log('[ReactNodeEditor] _onToggle called', { field, currentValue: this.nodeConfig[field] });
        const currentValue = this.nodeConfig[field];
        this._onInputChange(field, !currentValue);
    }

    _emitDelete() {
        console.log('[ReactNodeEditor] _emitDelete called');
        this._deleteNode();
    }

    renderFields() {
        if (!this.nodeConfig) {
            return html`<div>Загрузка...</div>`;
        }
        
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
                        placeholder="Название агента"
                    />
                </div>
                
                <div class="form-group">
                    <div class="form-label">
                        <span class="form-label-text">Описание</span>
                    </div>
                    <textarea 
                        class="form-input form-textarea"
                        .value=${config.description || ''}
                        @change=${(e) => this._onInputChange('description', e.target.value)}
                        placeholder="Описание назначения"
                        rows="2"
                    ></textarea>
                </div>
                
                <div class="form-group">
                    <div class="form-label">
                        <span class="form-label-text">Теги</span>
                    </div>
                    <tag-input 
                        .tags=${config.tags || []}
                        @change=${(e) => this._onInputChange('tags', e.detail.tags)}
                    ></tag-input>
                </div>
            ` : ''}
                
                <div class="form-group">
                    <prompt-editor
                        .value=${config.prompt || ''}
                        .variables=${this.agentVariables || {}}
                        label="Промпт"
                        placeholder="Ты - полезный ассистент..."
                        min-height="150"
                        .aiLoading=${this.aiLoading}
                        @change=${(e) => this._onInputChange('prompt', e.detail.value)}
                        @ai-improve=${this._generatePromptAI}
                    ></prompt-editor>
                </div>
                
                <div class="form-group">
                    <div class="form-label">
                        <span class="form-label-text">LLM</span>
                    </div>
                    <llm-config-editor
                        model=${config.llm ? (config.llm.model || 'gpt-4o') : 'gpt-4o'}
                        temperature=${config.llm && config.llm.temperature !== undefined ? config.llm.temperature : 0.2}
                        max-tokens=${config.llm ? (config.llm.max_tokens || '') : ''}
                        provider=${config.llm ? (config.llm.provider || '') : ''}
                        api-key=${config.llm ? (config.llm.api_key || '') : ''}
                        base-url=${config.llm ? (config.llm.base_url || '') : ''}
                        @change=${this._onLLMChange}
                    ></llm-config-editor>
                </div>
                
                <div class="section">
                    <div class="section-header">
                        <span class="section-title">Режим вывода</span>
                    </div>
                    <div class="loop-config">
                        <div class="mode-toggle-row">
                            <label class="mode-option ${!this.structuredOutput ? 'active' : ''}">
                                <input 
                                    type="radio" 
                                    name="output-mode"
                                    .checked=${!this.structuredOutput}
                                    @change=${() => this._onModeChange('tools')}
                                />
                                Tools Mode
                            </label>
                            <label class="mode-option ${this.structuredOutput ? 'active' : ''}">
                                <input 
                                    type="radio" 
                                    name="output-mode"
                                    .checked=${this.structuredOutput}
                                    @change=${() => this._onModeChange('structured')}
                                />
                                Structured Output
                            </label>
                        </div>
                        <span class="form-label-hint">Tools Mode: агент использует инструменты. Structured Output: JSON Schema для ответа.</span>
                        
                        ${this.structuredOutput ? html`
                            <div class="loop-config-row" style="margin-top: var(--space-3);">
                                <div class="form-label">
                                    <span class="form-label-text">Output Schema (JSON Schema)</span>
                                </div>
                                <json-field-editor
                                    .value=${JSON.stringify(this.outputSchema, null, 2)}
                                    min-height="150"
                                    hint="JSON Schema для структурированного вывода"
                                    @change=${this._onOutputSchemaJsonChange}
                                ></json-field-editor>
                            </div>
                        ` : ''}
                    </div>
                </div>
                
                ${!this.structuredOutput ? html`
                <div class="section">
                    <div class="section-header">
                        <span class="section-title">React Loop Configuration</span>
                    </div>
                    <div class="loop-config">
                        <div class="loop-config-row">
                            <div class="form-label">
                                <span class="form-label-text">Loop Mode</span>
                            </div>
                            <select 
                                class="form-input form-select"
                                .value=${this.loopMode}
                                @change=${this._onLoopModeChange}
                            >
                                <option value="auto">Auto - текст завершает агента</option>
                                <option value="explicit">Explicit - только через exit tool</option>
                            </select>
                            <span class="form-label-hint">Auto: текстовый ответ = завершение. Explicit: только через finish tool.</span>
                        </div>
                        
                        ${this.loopMode === 'explicit' ? html`
                            <div class="loop-config-row">
                                <div class="form-label">
                                    <span class="form-label-text">Exit Tool</span>
                                </div>
                                <select 
                                    class="form-input form-select"
                                    .value=${this.exitTool}
                                    @change=${this._onExitToolChange}
                                >
                                    ${(config.tools || []).map(tool => {
                                        const toolId = typeof tool === 'string' ? tool : tool.tool_id;
                                        const toolName = this._getToolDisplayName(tool);
                                        return html`<option value="${toolId}">${toolName}</option>`;
                                    })}
                                </select>
                                <span class="form-label-hint">Какой tool завершает цикл агента</span>
                            </div>
                            
                            <div class="checkbox-row">
                                <input 
                                    type="checkbox" 
                                    id="strict-mode"
                                    .checked=${this.strict}
                                    @change=${this._onStrictChange}
                                />
                                <label for="strict-mode">Строгий режим</label>
                            </div>
                            <span class="form-label-hint">Если включен - текст без exit tool вызывает reminder.</span>
                            
                            ${this.strict ? html`
                                <div class="loop-config-row">
                                    <div class="form-label">
                                        <span class="form-label-text">Reminder Message</span>
                                    </div>
                                    <textarea 
                                        class="form-input form-textarea"
                                        rows="2"
                                        .value=${this.reminderMessage}
                                        @change=${this._onReminderMessageChange}
                                        placeholder="Ты не вызвал tool для завершения..."
                                    ></textarea>
                                    <span class="form-label-hint">Кастомное напоминание (опционально)</span>
                                </div>
                            ` : ''}
                        ` : ''}
                        
                        <div class="loop-config-row">
                            <div class="form-label">
                                <span class="form-label-text">Max Iterations</span>
                            </div>
                            <input 
                                type="number" 
                                class="form-input"
                                min="1"
                                max="100"
                                .value=${this.maxIterations}
                                @change=${this._onMaxIterationsChange}
                            />
                            <span class="form-label-hint">Максимум итераций перед принудительным выходом</span>
                        </div>
                    </div>
                </div>
                
                <div class="section">
                    <div class="section-header">
                        <span class="section-title">Инструменты</span>
                        <div class="tools-actions">
                            <button class="section-add-btn" @click=${this._onAddInlineTool}>Inline ▼</button>
                            <button class="section-add-btn" @click=${this._onAddTool}>+ Добавить</button>
                            
                            ${this.showAddMenu ? html`
                                <div class="tools-add-menu" @click=${(e) => e.stopPropagation()}>
                                    <div class="menu-item" @click=${() => this._onCreateInline('tool')}>
                                        <platform-icon name="tool" size="14"></platform-icon>
                                        <span>Tool</span>
                                    </div>
                                    <div class="menu-item" @click=${() => this._onCreateInline('react_node')}>
                                        <platform-icon name="agent" size="14"></platform-icon>
                                        <span>React Agent</span>
                                    </div>
                                    <div class="menu-item" @click=${() => this._onCreateInline('function')}>
                                        <platform-icon name="code" size="14"></platform-icon>
                                        <span>Function</span>
                                    </div>
                                    <div class="menu-divider"></div>
                                    <div class="menu-item" @click=${() => this._onCreateInline('external_api')}>
                                        <platform-icon name="globe" size="14"></platform-icon>
                                        <span>External API</span>
                                    </div>
                                    <div class="menu-item" @click=${() => this._onCreateInline('remote_agent')}>
                                        <platform-icon name="server" size="14"></platform-icon>
                                        <span>Remote Agent</span>
                                    </div>
                                </div>
                            ` : ''}
                        </div>
                    </div>
                    <div class="tools-list">
                        ${(config.tools || []).length > 0 
                            ? (config.tools || []).map(tool => {
                                const toolId = typeof tool === 'string' ? tool : tool.tool_id;
                                const displayName = this._getToolDisplayName(tool);
                                const isInline = this._isInlineTool(tool);
                                const isAgent = this._isAgentTool(tool);
                                const isMCP = this._isMCPTool(tool);
                                const icon = this._getToolIcon(tool);
                                const canEdit = isInline || isAgent || isMCP;
                                return html`
                                    <div class="tool-item ${isInline ? 'is-inline' : ''} ${isAgent ? 'is-agent' : ''} ${isMCP ? 'is-mcp' : ''}">
                                        <platform-icon class="tool-item-icon" name="${icon}" size="14"></platform-icon>
                                        <span 
                                            class="tool-item-name ${canEdit ? '' : 'not-editable'}"
                                            @click=${() => canEdit ? this._onEditTool(toolId) : null}
                                            style="${canEdit ? 'cursor: pointer;' : 'cursor: default;'}"
                                        >${displayName}</span>
                                        <span class="tool-item-remove" @click=${() => this._onRemoveTool(toolId)}>
                                            <platform-icon name="x" size="12"></platform-icon>
                                        </span>
                                    </div>
                                `;
                            })
                            : html`<div class="empty-tools">Нет инструментов</div>`
                        }
                    </div>
                </div>
                ` : ''}
                
                ${this.renderMappingSection()}
                
                <test-panel
                    .inputState=${this._buildDefaultState()}
                    ?expanded=${this.expanded}
                    ?hide-input-state=${this.expanded}
                    @validate=${this._onValidate}
                    @execute=${this._onExecute}
                ></test-panel>
        `;
    }
}

customElements.define('react-node-editor', ReactNodeEditor);

