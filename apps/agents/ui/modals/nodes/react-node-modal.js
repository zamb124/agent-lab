/**
 * ReactNodeModal - модалка редактирования React Node (LLM агент с tools)
 */
import { html, css } from 'lit';
import { BaseNodeModal } from './base-node-modal.js';
import '@platform/lib/components/prompt-editor.js';

export class ReactNodeModal extends BaseNodeModal {
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
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                margin-top: var(--space-3);
            }
            
            .checkbox-row {
                display: flex;
                align-items: center;
                gap: var(--space-2);
            }
            
            .checkbox-row input[type="checkbox"] {
                width: 16px;
                height: 16px;
                cursor: pointer;
            }
            
            .prompt-section {
                flex: 1;
                display: flex;
                flex-direction: column;
            }
        `
    ];

    static properties = {
        ...BaseNodeModal.properties,
        selectedTools: { type: Array },
        loopMode: { type: String },
        exitTool: { type: String },
        strictMode: { type: Boolean },
    };

    constructor() {
        super();
        this.selectedTools = [];
        this.loopMode = 'auto';
        this.exitTool = '';
        this.strictMode = true;
    }

    getNodeType() {
        return 'react_node';
    }

    getModalTitle() {
        return 'ReactNode';
    }

    showModal(nodeId = '', config = {}) {
        super.showModal(nodeId, config);
        
        this.selectedTools = this._parseTools(config.tools || []);
        
        const react = config.react || {};
        this.loopMode = react.loop_mode || 'auto';
        this.exitTool = react.exit_tool || '';
        this.strictMode = react.strict !== false;
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
        const toolId = prompt('Введите ID инструмента:');
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

    _onStrictModeChange(e) {
        this.strictMode = e.target.checked;
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
            throw new Error('[ReactNodeModal] LLM editor not found');
        }
        const llm = llmEditor.getValue();
        
        const tagsEditor = this.shadowRoot.querySelector('tag-input');
        const tags = tagsEditor ? tagsEditor.getTags() : [];
        
        const inputMappingEditor = this.shadowRoot.querySelector('input-mapping-editor');
        const inputMapping = inputMappingEditor ? inputMappingEditor.getValue() : {};
        
        const config = {
            type: 'react_node',
            name,
            description: description || undefined,
            prompt,
            tools: this.selectedTools.map(t => t.tool_id),
            llm,
            tags: tags.length > 0 ? tags : undefined,
        };
        
        if (Object.keys(inputMapping).length > 0) {
            config.input_mapping = inputMapping;
        }
        
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
        
        return config;
    }

    _buildDefaultState() {
        return {
            content: 'Текст запроса пользователя',
            messages: [],
            variables: this.agentVariables || {},
            user_query: 'Пример значения',
        };
    }

    renderBody() {
        const config = this.nodeConfig;
        const react = config.react || {};
        
        return html`
            <div class="form-layout">
                <div class="form-sidebar">
                    <div class="form-group">
                        <label class="form-label">Node ID *</label>
                        <input 
                            type="text" 
                            name="node_id"
                            class="form-input ${this.isEdit ? 'readonly' : ''}"
                            .value=${this.nodeId || config.node_id || ''}
                            ?readonly=${this.isEdit}
                            placeholder="my_react_node"
                            required
                        />
                    </div>
                    
                    <div class="form-group">
                        <label class="form-label">Название *</label>
                        <input 
                            type="text" 
                            name="name"
                            class="form-input"
                            .value=${config.name || ''}
                            placeholder="Название агента"
                            required
                        />
                    </div>
                    
                    <div class="form-group">
                        <label class="form-label">Описание</label>
                        <textarea 
                            name="description"
                            class="form-textarea"
                            rows="2"
                            .value=${config.description || ''}
                            placeholder="Описание назначения агента"
                        ></textarea>
                    </div>
                    
                    <div class="form-group">
                        <label class="form-label">Теги</label>
                        <tag-input .tags=${config.tags || []}></tag-input>
                    </div>
                    
                    <div class="form-group tools-section">
                        <div class="tools-header">
                            <label class="form-label">Инструменты</label>
                            <div class="tools-actions">
                                <button type="button" class="tool-add-btn" @click=${this._addTool}>
                                    + Добавить
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
                                : html`<span class="tools-empty">Нет инструментов</span>`
                            }
                        </div>
                    </div>
                    
                    <div class="form-group">
                        <label class="form-label">LLM</label>
                        <llm-config-editor
                            model=${config.llm ? (config.llm.model || 'gpt-4o') : 'gpt-4o'}
                            temperature=${config.llm && config.llm.temperature !== undefined ? config.llm.temperature : 0.2}
                            max-tokens=${config.llm ? (config.llm.max_tokens || '') : ''}
                        ></llm-config-editor>
                    </div>
                    
                    <div class="react-loop-section">
                        <label class="form-label">Режим ReAct Loop</label>
                        <select 
                            class="form-select"
                            .value=${this.loopMode}
                            @change=${this._onLoopModeChange}
                        >
                            <option value="auto">Auto - текст завершает агента</option>
                            <option value="explicit">Explicit - только через exit tool</option>
                        </select>
                        <span class="form-hint">Auto: текстовый ответ = завершение. Explicit: только через finish tool.</span>
                        
                        ${this.loopMode === 'explicit' ? html`
                            <div class="loop-options">
                                <div class="form-group">
                                    <label class="form-label">Exit Tool</label>
                                    <select 
                                        class="form-select"
                                        .value=${this.exitTool}
                                        @change=${this._onExitToolChange}
                                    >
                                        ${this.selectedTools.map(t => html`
                                            <option value=${t.tool_id}>${t.name}</option>
                                        `)}
                                    </select>
                                </div>
                                
                                <div class="checkbox-row">
                                    <input 
                                        type="checkbox" 
                                        id="strict-mode"
                                        .checked=${this.strictMode}
                                        @change=${this._onStrictModeChange}
                                    />
                                    <label for="strict-mode">Строгий режим</label>
                                </div>
                                <span class="form-hint">Если включен - текст без exit tool вызывает reminder.</span>
                                
                                ${this.strictMode ? html`
                                    <div class="form-group">
                                        <label class="form-label">Текст reminder</label>
                                        <textarea 
                                            name="reminder_message"
                                            class="form-textarea"
                                            rows="2"
                                            .value=${react.reminder_message || ''}
                                            placeholder="Ты не вызвал tool X для завершения..."
                                        ></textarea>
                                    </div>
                                ` : ''}
                            </div>
                        ` : ''}
                    </div>
                </div>
                
                <div class="form-main">
                    <div class="prompt-section">
                        <div class="form-group" style="flex: 1;">
                            <prompt-editor
                                name="prompt"
                                .value=${config.prompt || ''}
                                .variables=${this.agentVariables || {}}
                                label="Промпт *"
                                placeholder="Ты - полезный ассистент. Твоя задача..."
                                min-height="200"
                                show-ai-button="false"
                            ></prompt-editor>
                        </div>
                    </div>
                    
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

customElements.define('react-node-modal', ReactNodeModal);

