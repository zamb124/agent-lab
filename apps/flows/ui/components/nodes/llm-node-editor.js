/**
 * LlmNodeEditor - редактор для llm_node типа
 * LLM агент с инструментами и ReAct loop
 */
import { html, css } from 'lit';
import { BaseNodeEditor } from './base-node-editor.js';
import '@platform/lib/components/prompt-editor.js';
import '../editors/llm-config-editor.js';
import '../editors/tag-input.js';
import '../../modals/tool-picker-modal.js';
import { openInlineToolModal } from '../../utils/open-inline-tool-modal.js';
import {
    getLlmToolChipAccentHex,
    getLlmToolChipIconName,
} from '../../utils/llm-tool-chips.js';
import '../editors/json-field-editor.js';
import '@platform/lib/components/platform-switch.js';

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
            
            .tools-inline-list {
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                gap: 6px;
            }

            .tool-chip {
                --tool-accent: #64748b;
                display: inline-flex;
                align-items: center;
                gap: 6px;
                max-width: 100%;
                min-width: 0;
                padding: 4px 8px 4px 6px;
                border-radius: 999px;
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
                border: 1px solid color-mix(in srgb, var(--tool-accent) 42%, transparent);
                background: color-mix(in srgb, var(--tool-accent) 12%, transparent);
                color: var(--text-primary);
                box-sizing: border-box;
            }

            .tool-chip-icon-wrap {
                flex-shrink: 0;
                display: flex;
                align-items: center;
                justify-content: center;
                line-height: 0;
                color: var(--tool-accent);
            }

            .tool-chip-label {
                min-width: 0;
                max-width: min(200px, 100%);
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            .tool-chip-label.is-editable {
                cursor: pointer;
            }

            .tool-chip-label.is-editable:hover {
                color: var(--accent);
            }

            .tool-chip-remove {
                flex-shrink: 0;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 0;
                margin: 0;
                border: none;
                background: transparent;
                color: var(--text-tertiary);
                cursor: pointer;
                border-radius: var(--radius-sm);
                line-height: 0;
            }

            .tool-chip-remove:hover {
                color: var(--error);
            }

            :host([expanded]) .tool-chip-label {
                max-width: min(140px, 100%);
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

            .loop-mode-iter-row {
                display: flex;
                flex-direction: row;
                align-items: flex-start;
                gap: var(--space-3);
                margin-bottom: var(--space-2);
            }

            .loop-mode-iter-row .loop-mode-field {
                flex: 1;
                min-width: 0;
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
            }

            .loop-mode-iter-row .max-iter-field {
                flex: 0 0 7.5rem;
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
            }

            .loop-mode-iter-row .max-iter-field .form-input {
                width: 100%;
                box-sizing: border-box;
            }

            .loop-explicit-row {
                display: grid;
                grid-template-columns: 1fr;
                gap: var(--space-3);
                align-items: start;
                margin-top: var(--space-2);
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

            .loop-config-hints {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-1) var(--space-3);
                margin-top: var(--space-1);
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
            queueMicrotask(() => {
                const editor = this.shadowRoot?.querySelector('llm-config-editor');
                if (editor) {
                    editor.setValue(this.nodeConfig.llm && typeof this.nodeConfig.llm === 'object' ? this.nodeConfig.llm : {});
                }
            });
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
    
    _onStrictSwitchChange(e) {
        this.strict = e.detail.value;
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
                                type: 'code',
                                name: toolData.title || toolData.tool_id,
                                description: toolData.description || '',
                                code: toolData.code,
                                args_schema: toolData.args_schema || {},
                                parameters_schema: toolData.parameters_schema,
                                react_role: toolData.react_role || 'standard',
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

        openInlineToolModal({
            mode: 'create',
            toolType,
            flowVariables: this.flowVariables,
            flowId: this.flowId,
            skillId: this.skillId,
            previewExecutionState: this.previewExecutionState,
            onToolSaved: (detail) => {
                const { toolId, config: toolConfig } = detail;
                const tools = [...(this.nodeConfig.tools || []), toolConfig];
                this.inlineTools.set(toolId, toolConfig);
                this._updateConfig('tools', tools);
            },
        });
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
        if (toolId.startsWith('mcp:')) {
            const { server_id, tool_name } = this._parseMCPToolId(toolId);

            openInlineToolModal({
                mode: 'edit',
                toolType: 'mcp',
                toolConfig: {
                    tool_id: toolId,
                    type: 'mcp',
                    server_id: server_id,
                    tool_name: tool_name,
                },
                flowVariables: this.flowVariables,
                flowId: this.flowId,
                skillId: this.skillId,
                previewExecutionState: this.previewExecutionState,
                onToolSaved: (detail) => {
                    const { config: savedConfig } = detail;
                    const tools = (this.nodeConfig.tools || []).map((t) => {
                        const tid = typeof t === 'string' ? t : t.tool_id;
                        return tid === toolId ? savedConfig : t;
                    });
                    this._updateConfig('tools', tools);
                },
            });
            return;
        }

        const toolConfig = this.inlineTools.get(toolId);
        if (!toolConfig) {
            return;
        }

        const toolType = toolConfig.type || 'code';

        openInlineToolModal({
            mode: 'edit',
            toolType,
            toolConfig,
            flowVariables: this.flowVariables,
            flowId: this.flowId,
            skillId: this.skillId,
            previewExecutionState: this.previewExecutionState,
            onToolSaved: (detail) => {
                const { toolId: savedToolId, config: savedConfig } = detail;
                const tools = (this.nodeConfig.tools || []).map((t) => {
                    const tid = typeof t === 'string' ? t : t.tool_id;
                    return tid === savedToolId ? savedConfig : t;
                });
                this.inlineTools.set(savedToolId, savedConfig);
                this._updateConfig('tools', tools);
            },
        });
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

    /**
     * Для строковой ссылки на tool подставляет объект из inlineTools (если есть),
     * чтобы иконка и тон совпадали с inline-конфигом.
     */
    _graphHintForToolId(toolId) {
        if (typeof toolId !== 'string' || toolId.length === 0) {
            return null;
        }
        const nodes = this.graphNodes || [];
        const hit = nodes.find((n) => n.id === toolId);
        if (!hit?.type) {
            return null;
        }
        const graphTypes = new Set([
            'llm_node',
            'flow',
            'code',
            'external_api',
            'remote_flow',
            'channel',
        ]);
        const effectiveType = hit.type;
        if (!graphTypes.has(effectiveType)) {
            return null;
        }
        return { tool_id: toolId, type: effectiveType };
    }

    _effectiveToolForUi(tool) {
        if (typeof tool === 'object' && tool !== null) {
            return tool;
        }
        if (typeof tool !== 'string') {
            return tool;
        }
        const fromMap = this.inlineTools.get(tool);
        if (fromMap) {
            return fromMap;
        }
        const fromGraph = this._graphHintForToolId(tool);
        if (fromGraph) {
            return fromGraph;
        }
        return tool;
    }
    
    _isInlineTool(tool) {
        if (typeof tool === 'object' && tool.code) {
            return true;
        }
        return false;
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
                    <span class="form-label-hint">${this.i18n.t('llm_node.prompt_file_drop_hint')}</span>
                    <prompt-editor
                        .value=${config.prompt || ''}
                        .variables=${this.flowVariables || {}}
                        label=${this.i18n.t('llm_node.prompt_label')}
                        placeholder=${this.i18n.t('llm_node.prompt_placeholder')}
                        min-height="150"
                        .aiLoading=${this.aiLoading}
                        accept-file-drop
                        @change=${(e) => this._onInputChange('prompt', e.detail.value)}
                        @ai-improve=${this._generatePromptAI}
                    ></prompt-editor>
                </div>
                
                <div class="form-group">
                    <div class="form-label">
                        <span class="form-label-text">${this.i18n.t('llm_node.section_llm')}</span>
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
                    <div class="section-header">
                        <span class="section-title">${this.i18n.t('llm_node.section_output_mode')}</span>
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
                                ${this.i18n.t('llm_node.tools_mode_label')}
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
                        <span class="form-label-hint">${this.i18n.t('llm_node.output_mode_hint')}</span>
                        
                        ${this.structuredOutput ? html`
                            <div class="loop-config-row" style="margin-top: var(--space-3);">
                                <div class="form-label">
                                    <span class="form-label-text">${this.i18n.t('llm_node.output_schema_label')}</span>
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
                        <span class="section-title">${this.i18n.t('llm_node.section_react_loop')}</span>
                    </div>
                    <div class="loop-config">
                        <div class="loop-mode-iter-row">
                            <div class="loop-mode-field">
                                <span class="form-label-text">${this.i18n.t('llm_node.loop_mode_label')}</span>
                                <select
                                    class="form-input form-select"
                                    .value=${this.loopMode}
                                    @change=${this._onLoopModeChange}
                                >
                                    <option value="auto">${this.i18n.t('llm_node.loop_mode_auto')}</option>
                                    <option value="explicit">${this.i18n.t('llm_node.loop_mode_explicit')}</option>
                                </select>
                            </div>
                            <div class="max-iter-field">
                                <span class="form-label-text">${this.i18n.t('llm_node.max_iterations_label')}</span>
                                <input
                                    type="number"
                                    class="form-input"
                                    min="1"
                                    max="100"
                                    .value=${this.maxIterations}
                                    @change=${this._onMaxIterationsChange}
                                />
                            </div>
                        </div>
                        <div class="loop-config-hints">
                            <span class="form-label-hint">${this.i18n.t('llm_node.loop_mode_hint')}</span>
                            <span class="form-label-hint">${this.i18n.t('llm_node.max_iterations_hint')}</span>
                        </div>

                        ${this.loopMode === 'explicit' ? html`
                            <div class="loop-explicit-row ${this.strict ? 'has-reminder' : ''}">
                                <div class="loop-explicit-left">
                                    <div class="loop-explicit-strict-block">
                                        <platform-switch
                                            ?checked=${this.strict}
                                            size="sm"
                                            .label=${this.i18n.t('llm_node.strict_mode_label')}
                                            @change=${this._onStrictSwitchChange}
                                        ></platform-switch>
                                        <span class="form-label-hint">${this.i18n.t('llm_node.strict_mode_hint')}</span>
                                    </div>
                                    <div>
                                        <span class="form-label-text">${this.i18n.t('llm_node.exit_tool_label')}</span>
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
                                </div>
                                ${this.strict ? html`
                                    <div class="loop-explicit-reminder">
                                        <span class="form-label-text">${this.i18n.t('llm_node.reminder_text_label')}</span>
                                        <textarea
                                            class="form-input form-textarea"
                                            rows="3"
                                            .value=${this.reminderMessage}
                                            @change=${this._onReminderMessageChange}
                                            placeholder=${this.i18n.t('llm_node.reminder_placeholder')}
                                        ></textarea>
                                        <span class="form-label-hint">${this.i18n.t('llm_node.reminder_hint')}</span>
                                    </div>
                                ` : ''}
                            </div>
                        ` : ''}
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
                                    <div class="menu-item" @click=${() => this._onCreateInline('code')}>
                                        <platform-icon name="code" size="14"></platform-icon>
                                        <span>${this.i18n.t('llm_node.inline_add_tool')}</span>
                                    </div>
                                    <div class="menu-item" @click=${() => this._onCreateInline('llm_node')}>
                                        <platform-icon name="llm_node" size="14"></platform-icon>
                                        <span>${this.i18n.t('llm_node.inline_add_react_flow')}</span>
                                    </div>
                                    <div class="menu-divider"></div>
                                    <div class="menu-item" @click=${() => this._onCreateInline('external_api')}>
                                        <platform-icon name="globe" size="14"></platform-icon>
                                        <span>${this.i18n.t('llm_node.inline_add_external_api')}</span>
                                    </div>
                                    <div class="menu-item" @click=${() => this._onCreateInline('remote_flow')}>
                                        <platform-icon name="server" size="14"></platform-icon>
                                        <span>${this.i18n.t('llm_node.inline_add_remote_flow')}</span>
                                    </div>
                                </div>
                            ` : ''}
                        </div>
                    </div>
                    <div class="tools-inline-list">
                        ${(config.tools || []).length > 0 
                            ? (config.tools || []).map(tool => {
                                const toolId = typeof tool === 'string' ? tool : tool.tool_id;
                                const displayName = this._getToolDisplayName(tool);
                                const effective = this._effectiveToolForUi(tool);
                                const icon = getLlmToolChipIconName(effective);
                                const accent = getLlmToolChipAccentHex(effective);
                                const canEdit =
                                    this._isInlineTool(effective) ||
                                    this._isSubflowTool(effective) ||
                                    this._isMCPTool(effective);
                                const removeAria = this.i18n.t('llm_node.tool_chip_remove_aria', {
                                    id: String(toolId),
                                });
                                return html`
                                    <div class="tool-chip" style="--tool-accent: ${accent}">
                                        <span class="tool-chip-icon-wrap" aria-hidden="true">
                                            <platform-icon name="${icon}" size="14"></platform-icon>
                                        </span>
                                        <span
                                            class="tool-chip-label ${canEdit ? 'is-editable' : ''}"
                                            title=${displayName}
                                            role=${canEdit ? 'button' : undefined}
                                            tabindex=${canEdit ? '0' : undefined}
                                            @click=${() => (canEdit ? this._onEditTool(toolId) : undefined)}
                                            @keydown=${(e) => {
                                                if (
                                                    canEdit &&
                                                    (e.key === 'Enter' || e.key === ' ')
                                                ) {
                                                    e.preventDefault();
                                                    this._onEditTool(toolId);
                                                }
                                            }}
                                        >${displayName}</span>
                                        <button
                                            type="button"
                                            class="tool-chip-remove"
                                            aria-label=${removeAria}
                                            @click=${() => this._onRemoveTool(toolId)}
                                        >
                                            <platform-icon name="x" size="12"></platform-icon>
                                        </button>
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

