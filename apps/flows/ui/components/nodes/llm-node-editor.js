/**
 * LlmNodeEditor - редактор для llm_node типа
 * LLM агент с инструментами и ReAct loop
 */
import { html, css } from 'lit';
import { BaseNodeEditor } from './base-node-editor.js';
import '@platform/lib/components/prompt-editor.js';
import '../editors/llm-config-editor.js';
import '../editors/tag-input.js';
import '../../modals/inline-tool-modal.js';
import '../../modals/tool-picker-modal.js';
import { confirm } from '../../modals/confirm-modal.js';
import '../editors/json-field-editor.js';

export class LlmNodeEditor extends BaseNodeEditor {
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
            
            .tool-item.is-subflow-tool .tool-item-icon {
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
            
            .mode-toggle-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
                margin-bottom: var(--space-2);
            }

            .mode-toggle-header .section-title {
                margin: 0;
            }

            .reload-from-bundle-btn {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                padding: var(--space-2);
                border: none;
                background: transparent;
                color: var(--text-secondary);
                border-radius: var(--radius-sm);
                cursor: pointer;
                flex-shrink: 0;
            }

            .reload-from-bundle-btn:hover:not(:disabled) {
                color: var(--accent);
                background: var(--glass-tint-subtle);
            }

            .reload-from-bundle-btn:disabled {
                opacity: 0.35;
                cursor: not-allowed;
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

            .messages-filter-nodes {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                margin-top: var(--space-2);
                max-height: 200px;
                overflow-y: auto;
                padding: var(--space-2);
                background: var(--glass-tint-subtle);
                border-radius: var(--radius-md);
                border: 1px solid var(--border-subtle);
            }

            .messages-filter-node-label {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                font-size: var(--text-sm);
                color: var(--text-primary);
                cursor: pointer;
                padding: var(--space-1) 0;
                border-radius: var(--radius-sm);
            }

            .messages-filter-node-label:hover .messages-filter-box {
                border-color: var(--accent-light);
            }

            .messages-filter-control {
                position: relative;
                width: 18px;
                height: 18px;
                flex-shrink: 0;
            }

            .messages-filter-input {
                position: absolute;
                inset: 0;
                width: 18px;
                height: 18px;
                margin: 0;
                opacity: 0;
                cursor: pointer;
                z-index: 1;
            }

            .messages-filter-box {
                position: absolute;
                inset: 0;
                box-sizing: border-box;
                border: 1.5px solid var(--border-default);
                border-radius: var(--radius-sm);
                background: var(--glass-tint-subtle);
                pointer-events: none;
                display: flex;
                align-items: center;
                justify-content: center;
                transition:
                    background var(--duration-fast) ease,
                    border-color var(--duration-fast) ease;
            }

            .messages-filter-control:has(.messages-filter-input:checked) .messages-filter-box {
                background: var(--accent, #10b981);
                border-color: var(--accent, #10b981);
            }

            .messages-filter-input:focus-visible + .messages-filter-box {
                outline: 2px solid var(--accent, #10b981);
                outline-offset: 2px;
            }

            .messages-filter-control:has(.messages-filter-input:checked) .messages-filter-box::after {
                content: '';
                width: 4px;
                height: 8px;
                margin-bottom: 2px;
                border: solid white;
                border-width: 0 2px 2px 0;
                transform: rotate(45deg);
            }

            .messages-filter-text {
                flex: 1;
                min-width: 0;
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
        graphNodes: { type: Array },
        messagesFilterMode: { type: String },
        messagesFilterCustomIds: { type: Array },
        flowSource: { type: String },
        reloadFromBundleLoading: { type: Boolean },
    };

    constructor() {
        super();
        this._nodeType = 'llm_node';
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
        this.graphNodes = [];
        this.messagesFilterMode = 'all';
        this.messagesFilterCustomIds = [];
        this.flowSource = '';
        this.reloadFromBundleLoading = false;
    }

    _canReloadFromBundle() {
        return this.flowSource === 'file' && !!this.flowId;
    }

    async _onReloadFromBundle() {
        if (!this._canReloadFromBundle() || this.reloadFromBundleLoading) {
            return;
        }
        const agreed = await confirm(
            this.i18n.t('editor.reinit_confirm_message'),
            {
                title: this.i18n.t('editor.reinit_confirm_title'),
                variant: 'warning',
                confirmText: this.i18n.t('editor.reinit_confirm_ok'),
                cancelText: this.i18n.t('editor.cancel'),
            },
        );
        if (!agreed) {
            return;
        }
        this.reloadFromBundleLoading = true;
        try {
            await this.a2a.reloadFlowFromBundle(this.flowId);
            this.emit('flow-reload-from-bundle', { flowId: this.flowId });
        } catch (err) {
            this.error(err.message || String(err));
        } finally {
            this.reloadFromBundleLoading = false;
        }
    }
    
    _getDefaultSchema() {
        return {
            type: 'object',
            properties: {
                result: { type: 'string', description: this.i18n.t('llm_node.schema_result_description') }
            },
            required: ['result']
        };
    }
    
    updated(changedProperties) {
        super.updated(changedProperties);
        
        if (changedProperties.has('nodeConfig') && this.nodeConfig) {
            console.log('[LlmNodeEditor] nodeConfig changed, parsing and re-rendering...');
            this._parseTools();
            this._parseReactConfig();
            this._parseMessagesFilter();
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

    _parseMessagesFilter() {
        const mf = this.nodeConfig?.messages_filter;
        if (mf === 'own') {
            this.messagesFilterMode = 'own';
            this.messagesFilterCustomIds = [];
        } else if (Array.isArray(mf)) {
            this.messagesFilterMode = 'custom';
            this.messagesFilterCustomIds = [...mf];
        } else {
            this.messagesFilterMode = 'all';
            this.messagesFilterCustomIds = [];
        }
    }

    _onMessagesFilterPresetChange(e) {
        const v = e.target.value;
        if (v === 'all' || v === 'own') {
            this.messagesFilterMode = v;
            this.messagesFilterCustomIds = [];
            this._updateConfig('messages_filter', v);
            return;
        }
        this.messagesFilterMode = 'custom';
        const fallbackId = this.nodeId || this.nodeConfig?.node_id || 'main';
        const next =
            this.messagesFilterCustomIds && this.messagesFilterCustomIds.length > 0
                ? [...this.messagesFilterCustomIds]
                : [fallbackId];
        this.messagesFilterCustomIds = next;
        this._updateConfig('messages_filter', next);
    }

    _onMessagesFilterNodeToggle(e, graphNodeId) {
        const checked = e.target.checked;
        const set = new Set(this.messagesFilterCustomIds || []);
        if (checked) {
            set.add(graphNodeId);
        } else {
            set.delete(graphNodeId);
        }
        let arr = [...set];
        const fallbackId = this.nodeId || this.nodeConfig?.node_id || 'main';
        if (arr.length === 0) {
            arr = [fallbackId];
        }
        this.messagesFilterCustomIds = arr;
        this._updateConfig('messages_filter', arr);
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
            console.warn('[LlmNodeEditor] Enter an initial prompt first');
            return;
        }
        
        this.aiLoading = true;
        
        if (this.a2a) {
            try {
                const improved = await this.a2a.generatePromptAI(prompt, {
                    description: this.nodeConfig.description || '',
                    tools: this.nodeConfig.tools || [],
                    llm_config: this.nodeConfig.llm || {},
                    variables: Object.keys(this.flowVariables)
                });
                
                this._updateConfig('prompt', improved);
            } catch (error) {
                console.error('[LlmNodeEditor] Prompt generation failed:', error);
            }
        }
        
        this.aiLoading = false;
    }
    
    _onAddTool() {
        console.log('[LlmNodeEditor] _onAddTool called', { nodeConfig: this.nodeConfig });
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
                        console.warn(`[LlmNodeEditor] Could not load tool ${toolId}, using reference`);
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
        console.log('[LlmNodeEditor] _onAddInlineTool called');
        this.showAddMenu = !this.showAddMenu;
    }
    
    _onCreateInline(toolType) {
        this.showAddMenu = false;
        
        const modal = document.createElement('inline-tool-modal');
        modal.mode = 'create';
        modal.toolType = toolType;
        modal.flowVariables = this.flowVariables;
        modal.flowId = this.flowId;
        modal.skillId = this.skillId;
        modal.previewExecutionState = this.previewExecutionState;
        
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
            modal.flowVariables = this.flowVariables;
            modal.flowId = this.flowId;
            modal.skillId = this.skillId;
            modal.previewExecutionState = this.previewExecutionState;
            
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
        modal.flowVariables = this.flowVariables;
        modal.flowId = this.flowId;
        modal.skillId = this.skillId;
        modal.previewExecutionState = this.previewExecutionState;
        
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
            if (tool.type === 'flow') {
                return 'workflow';
            }
            if (tool.type === 'llm_node') {
                return 'llm_node';
            }
        }
        return 'tool';
    }
    
    _isSubflowTool(tool) {
        if (typeof tool === 'object') {
            return tool.type === 'flow' || tool.type === 'llm_node';
        }
        return false;
    }

    _onToggle(field) {
        console.log('[LlmNodeEditor] _onToggle called', { field, currentValue: this.nodeConfig[field] });
        const currentValue = this.nodeConfig[field];
        this._onInputChange(field, !currentValue);
    }

    renderFields() {
        if (!this.nodeConfig) {
            return html`<div>${this.i18n.t('llm_node.loading')}</div>`;
        }
        
        const config = this.nodeConfig;
        const showCommonFields = !this.expanded;
        
        return html`
            ${showCommonFields ? html`
                ${this.renderNodeIdField()}
                
                <div class="form-group">
                    <div class="form-label">
                        <span class="form-label-text">${this.i18n.t('llm_node.field_name')}</span>
                    </div>
                    <input 
                        type="text" 
                        class="form-input"
                        .value=${config.name || ''}
                        @change=${(e) => this._onInputChange('name', e.target.value)}
                        placeholder=${this.i18n.t('llm_node.placeholder_agent_name')}
                    />
                </div>
                
                <div class="form-group">
                    <div class="form-label">
                        <span class="form-label-text">${this.i18n.t('llm_node.field_description')}</span>
                    </div>
                    <textarea 
                        class="form-input form-textarea"
                        .value=${config.description || ''}
                        @change=${(e) => this._onInputChange('description', e.target.value)}
                        placeholder=${this.i18n.t('llm_node.placeholder_description')}
                        rows="2"
                    ></textarea>
                </div>
                
                <div class="form-group">
                    <div class="form-label">
                        <span class="form-label-text">${this.i18n.t('llm_node.field_tags')}</span>
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
                        .variables=${this.flowVariables || {}}
                        label=${this.i18n.t('llm_node.prompt_label')}
                        placeholder=${this.i18n.t('llm_node.prompt_placeholder')}
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
                        <span class="section-title">${this.i18n.t('llm_node.section_messages_history')}</span>
                    </div>
                    <div class="loop-config">
                        <span class="form-label-hint">
                            ${this.i18n.t('llm_node.messages_history_hint')}
                        </span>
                        <div class="loop-config-row" style="margin-top: var(--space-2);">
                            <div class="form-label">
                                <span class="form-label-text">${this.i18n.t('llm_node.messages_filter_label')}</span>
                            </div>
                            <select
                                class="form-input form-select"
                                .value=${this.messagesFilterMode === 'custom' ? 'custom' : this.messagesFilterMode}
                                @change=${this._onMessagesFilterPresetChange}
                            >
                                <option value="all">${this.i18n.t('llm_node.messages_filter_all')}</option>
                                <option value="own">${this.i18n.t('llm_node.messages_filter_own')}</option>
                                <option value="custom">${this.i18n.t('llm_node.messages_filter_custom')}</option>
                            </select>
                        </div>
                        ${this.messagesFilterMode === 'custom'
                            ? html`
                                  <div class="messages-filter-nodes">
                                      ${(this.graphNodes || []).length === 0
                                          ? html`<span class="form-label-hint">${this.i18n.t('llm_node.messages_filter_no_nodes')}</span>`
                                          : (this.graphNodes || []).map(
                                                (n) => html`
                                                    <label class="messages-filter-node-label">
                                                        <span class="messages-filter-control">
                                                            <input
                                                                type="checkbox"
                                                                class="messages-filter-input"
                                                                .checked=${(
                                                                    this.messagesFilterCustomIds || []
                                                                ).includes(n.id)}
                                                                @change=${(ev) =>
                                                                    this._onMessagesFilterNodeToggle(ev, n.id)}
                                                            />
                                                            <span class="messages-filter-box" aria-hidden="true"></span>
                                                        </span>
                                                        <span class="messages-filter-text">${n.name} (${n.id})</span>
                                                    </label>
                                                `
                                            )}
                                  </div>
                              `
                            : ''}
                    </div>
                </div>
                
                <div class="section">
                    <div class="section-header mode-toggle-header">
                        <span class="section-title">${this.i18n.t('llm_node.section_output_mode')}</span>
                        <button
                            type="button"
                            class="reload-from-bundle-btn"
                            title=${this.i18n.t('llm_node.reload_from_bundle_title')}
                            ?disabled=${!this._canReloadFromBundle() || this.reloadFromBundleLoading}
                            @click=${this._onReloadFromBundle}
                        >
                            <platform-icon name="refresh" size="16"></platform-icon>
                        </button>
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
                        <span class="form-label-hint">${this.i18n.t('llm_node.output_mode_hint')}</span>
                        
                        ${this.structuredOutput ? html`
                            <div class="loop-config-row" style="margin-top: var(--space-3);">
                                <div class="form-label">
                                    <span class="form-label-text">Output Schema (JSON Schema)</span>
                                </div>
                                <json-field-editor
                                    bounded
                                    .value=${JSON.stringify(this.outputSchema, null, 2)}
                                    min-height="120"
                                    hint=${this.i18n.t('llm_node.structured_schema_hint')}
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
                                <option value="auto">${this.i18n.t('llm_node.loop_mode_auto')}</option>
                                <option value="explicit">${this.i18n.t('llm_node.loop_mode_explicit')}</option>
                            </select>
                            <span class="form-label-hint">${this.i18n.t('llm_node.loop_mode_hint')}</span>
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
                                <span class="form-label-hint">${this.i18n.t('llm_node.exit_tool_hint')}</span>
                            </div>
                            
                            <div class="checkbox-row">
                                <input 
                                    type="checkbox" 
                                    id="strict-mode"
                                    .checked=${this.strict}
                                    @change=${this._onStrictChange}
                                />
                                <label for="strict-mode">${this.i18n.t('llm_node.strict_mode_label')}</label>
                            </div>
                            <span class="form-label-hint">${this.i18n.t('llm_node.strict_mode_hint')}</span>
                            
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
                                        placeholder=${this.i18n.t('llm_node.reminder_placeholder')}
                                    ></textarea>
                                    <span class="form-label-hint">${this.i18n.t('llm_node.reminder_hint')}</span>
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
                            <span class="form-label-hint">${this.i18n.t('llm_node.max_iterations_hint')}</span>
                        </div>
                    </div>
                </div>
                
                <div class="section">
                    <div class="section-header">
                        <span class="section-title">${this.i18n.t('llm_node.section_tools')}</span>
                        <div class="tools-actions">
                            <button class="section-add-btn" @click=${this._onAddInlineTool}>${this.i18n.t('llm_node.inline_menu')}</button>
                            <button class="section-add-btn" @click=${this._onAddTool}>${this.i18n.t('llm_node.add_tool')}</button>
                            
                            ${this.showAddMenu ? html`
                                <div class="tools-add-menu" @click=${(e) => e.stopPropagation()}>
                                    <div class="menu-item" @click=${() => this._onCreateInline('tool')}>
                                        <platform-icon name="tool" size="14"></platform-icon>
                                        <span>Tool</span>
                                    </div>
                                    <div class="menu-item" @click=${() => this._onCreateInline('llm_node')}>
                                        <platform-icon name="llm_node" size="14"></platform-icon>
                                        <span>React flow</span>
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
                                    <div class="menu-item" @click=${() => this._onCreateInline('remote_flow')}>
                                        <platform-icon name="server" size="14"></platform-icon>
                                        <span>Remote flow</span>
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
                                const isSubflow = this._isSubflowTool(tool);
                                const isMCP = this._isMCPTool(tool);
                                const icon = this._getToolIcon(tool);
                                const canEdit = isInline || isSubflow || isMCP;
                                return html`
                                    <div class="tool-item ${isInline ? 'is-inline' : ''} ${isSubflow ? 'is-subflow-tool' : ''} ${isMCP ? 'is-mcp' : ''}">
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
                            : html`<div class="empty-tools">${this.i18n.t('llm_node.empty_tools')}</div>`
                        }
                    </div>
                </div>
                ` : ''}
                
                ${this.renderMappingSection()}
                
                ${this._renderTestPanel()}
        `;
    }
}

customElements.define('llm-node-editor', LlmNodeEditor);

