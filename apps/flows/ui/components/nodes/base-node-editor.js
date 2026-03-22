/**
 * BaseNodeEditor - базовый класс для редакторов нод
 * Использует shared form стили (DRY)
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { formStyles } from '@platform/lib/styles/shared/form.styles.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import '../editors/tag-input.js';
import '../editors/json-field-editor.js';
import '../editors/state-mapping-editor.js';

export class BaseNodeEditor extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        formStyles,
        buttonStyles,
        css`
            .panel-body {
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
            }
            
            .panel-layout {
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
            }
            
            :host([expanded]) .panel-layout {
                flex-direction: row;
                gap: var(--space-6);
            }
            
            .panel-sidebar {
                display: none;
            }
            
            :host([expanded]) .panel-sidebar {
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
                width: 280px;
                flex-shrink: 0;
                padding-right: var(--space-6);
                border-right: 1px solid var(--border-subtle);
            }
            
            .panel-main {
                flex: 1;
                min-width: 0;
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
            }
            
            .sidebar-section {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }
            
            .sidebar-section-title {
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                color: var(--text-tertiary);
                text-transform: uppercase;
                letter-spacing: 0.05em;
            }
            
            .code-mode-row {
                display: flex;
                gap: var(--space-2);
                margin-bottom: var(--space-3);
            }
            
            .code-mode-btn {
                flex: 1;
                padding: var(--space-2) var(--space-3);
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
                color: var(--text-secondary);
                background: var(--glass-tint-subtle);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                cursor: pointer;
                transition: all var(--duration-fast) var(--easing-default);
            }
            
            .code-mode-btn:hover {
                color: var(--text-primary);
                background: var(--glass-tint-medium);
                border-color: var(--border-medium);
            }
            
            .code-mode-btn.active {
                color: var(--accent-text);
                background: var(--accent-bg);
                border-color: var(--accent);
                box-shadow: 0 0 0 3px var(--accent-glow);
            }
        `
    ];

    static properties = {
        nodeId: { type: String },
        nodeConfig: { type: Object },
        flowId: { type: String },
        skillId: { type: String },
        flowVariables: { type: Object },
        expanded: { type: Boolean },
    };

    constructor() {
        super();
        this.nodeId = '';
        this.nodeConfig = {};
        this.flowId = '';
        this.skillId = '';
        this.flowVariables = {};
        this.expanded = false;
    }

    _updateConfig(field, value) {
        console.log('[BaseNodeEditor] _updateConfig called:', { 
            nodeId: this.nodeId, 
            field, 
            value,
            oldNodeConfig: this.nodeConfig
        });
        
        this.nodeConfig = {
            ...this.nodeConfig,
            [field]: value
        };
        
        console.log('[BaseNodeEditor] New nodeConfig:', this.nodeConfig);
        
        this.emit('config-change', { field, value, config: this.nodeConfig });
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
            'variables': {},
        };
        
        // flowVariables кладём в state.variables, извлекая только value
        if (this.flowVariables) {
            if (Array.isArray(this.flowVariables)) {
                for (const varObj of this.flowVariables) {
                    if (varObj && varObj.key) {
                        const val = varObj.value;
                        defaultState.variables[varObj.key] = (val && typeof val === 'object' && 'value' in val) ? val.value : val;
                    }
                }
            } else if (typeof this.flowVariables === 'object') {
                for (const [key, val] of Object.entries(this.flowVariables)) {
                    defaultState.variables[key] = (val && typeof val === 'object' && 'value' in val) ? val.value : val;
                }
            }
        }
        
        return defaultState;
    }

    async _onValidate(e) {
        const nodeType = this.nodeConfig?.type || this._nodeType;
        
        console.log('[BaseNodeEditor] _onValidate called', {
            nodeId: this.nodeId,
            nodeConfigNodeId: this.nodeConfig?.nodeId,
            nodeConfigType: this.nodeConfig?.type,
            _nodeType: this._nodeType,
            finalNodeType: nodeType,
            flowId: this.flowId,
            skillId: this.skillId
        });
        
        if (!nodeType) {
            this.error('type ноды отсутствует');
            return;
        }

        const state = e.detail.state;
        const testPanel = e.target;
        
        testPanel.setLoading(true);

        try {
            const result = await this.a2a.validateNode(nodeType, this.nodeConfig, state, this.flowId, this.skillId);
            
            testPanel.setResult(result);
            
            if (result.valid || result.success) {
                this.success('Валидация успешна');
            } else {
                this.error(result.error || 'Ошибка валидации');
            }
        } catch (err) {
            console.error('[BaseNodeEditor] Validate error:', err);
            testPanel.setResult({ success: false, error: err.message });
            this.error('Ошибка валидации: ' + err.message);
        }
    }

    async _onExecute(e) {
        const nodeType = this.nodeConfig?.type || this._nodeType;
        
        console.log('[BaseNodeEditor] _onExecute called', {
            nodeId: this.nodeId,
            nodeConfigNodeId: this.nodeConfig?.nodeId,
            nodeConfigType: this.nodeConfig?.type,
            _nodeType: this._nodeType,
            finalNodeType: nodeType,
            flowId: this.flowId,
            skillId: this.skillId,
            fullNodeConfig: this.nodeConfig
        });
        
        if (!nodeType) {
            this.error('type ноды отсутствует');
            console.error('[BaseNodeEditor] nodeConfig:', this.nodeConfig);
            return;
        }

        const state = e.detail.state;
        const testPanel = e.target;
        
        testPanel.setLoading(true);

        try {
            console.log('[BaseNodeEditor] Calling executeNode with:', {
                nodeType: nodeType,
                nodeConfig: this.nodeConfig,
                state,
                flowId: this.flowId,
                skillId: this.skillId
            });
            
            const result = await this.a2a.executeNode(nodeType, this.nodeConfig, state, this.flowId, this.skillId);
            
            testPanel.setResult(result);
            
            if (result.success) {
                this.success('Выполнение успешно');
            } else {
                this.error(result.error || 'Ошибка выполнения');
            }
        } catch (err) {
            console.error('[BaseNodeEditor] Execute error:', err);
            testPanel.setResult({ success: false, error: err.message });
            this.error('Ошибка выполнения: ' + err.message);
        }
    }

    _deleteNode() {
        this.emit('node-delete', { nodeId: this.nodeId });
    }

    /**
     * Обработчик изменения Node ID
     * Валидирует формат и эмитит событие для обновления
     */
    _onNodeIdChange(e) {
        const newId = e.target.value.trim();
        
        if (!newId) {
            this.error('Node ID не может быть пустым');
            e.target.value = this.nodeId;
            return;
        }
        
        if (!/^[a-zA-Z][a-zA-Z0-9_]*$/.test(newId)) {
            this.error('Node ID должен начинаться с буквы и содержать только буквы, цифры и _');
            e.target.value = this.nodeId;
            return;
        }
        
        if (newId !== this.nodeId) {
            this.emit('node-id-changed', {
                oldId: this.nodeId,
                newId: newId
            });
        }
    }

    /**
     * Рендер поля для редактирования Node ID
     * Унифицированный компонент для всех типов нод
     */
    renderNodeIdField() {
        return html`
            <div class="form-group">
                <div class="form-label">
                    <span class="form-label-text">Node ID</span>
                </div>
                <input 
                    type="text" 
                    class="form-input"
                    .value=${this.nodeId}
                    @change=${this._onNodeIdChange}
                    placeholder="my_node_id"
                />
                <span class="form-label-hint">Уникальный идентификатор ноды (латиница, цифры, _)</span>
            </div>
        `;
    }

    renderDescription() {
        return '';
    }

    /**
     * Общие поля для sidebar в expanded режиме
     * Переопределяется в subclasses для добавления специфичных полей
     */
    renderCommonFields() {
        const config = this.nodeConfig;
        return html`
            <div class="sidebar-section">
                <div class="sidebar-section-title">Основное</div>
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
                        placeholder="Название ноды"
                    />
                </div>
                
                <div class="form-group">
                    <div class="form-label">
                        <span class="form-label-text">Описание</span>
                    </div>
                    <textarea 
                        class="form-input form-textarea"
                        rows="3"
                        .value=${config.description || ''}
                        @change=${(e) => this._onInputChange('description', e.target.value)}
                        placeholder="Описание назначения"
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
            </div>
            
            ${this.renderInputStateSection()}
        `;
    }

    /**
     * Секция Input State для sidebar при expanded режиме
     */
    renderInputStateSection() {
        return html`
            <div class="sidebar-section">
                <div class="sidebar-section-title">Input State (JSON)</div>
                <div class="form-group">
                    <json-field-editor
                        id="sidebar-input-state"
                        .value=${JSON.stringify(this._buildDefaultState(), null, 2)}
                        min-height="150"
                        placeholder='{"content": "", "messages": []}'
                        @change=${this._onInputStateChange}
                    ></json-field-editor>
                    <button 
                        type="button" 
                        class="form-hint" 
                        style="cursor: pointer; border: none; background: none; text-decoration: underline;"
                        @click=${this._onResetInputState}
                    >↺ Сбросить</button>
                </div>
            </div>
        `;
    }

    _onInputStateChange(e) {
        const testPanel = this.shadowRoot?.querySelector('test-panel');
        if (testPanel && e.target.isValid()) {
            testPanel.setInputState(e.target.getParsedValue());
        }
    }

    _onResetInputState() {
        const editor = this.shadowRoot?.querySelector('#sidebar-input-state');
        const testPanel = this.shadowRoot?.querySelector('test-panel');
        const defaultState = this._buildDefaultState();
        if (editor) {
            editor.setValue(defaultState);
        }
        if (testPanel) {
            testPanel.resetInputState();
        }
    }

    renderFields() {
        return html`<p>Override renderFields() in subclass</p>`;
    }

    /**
     * Рендер секции input/output маппингов с табами
     * Унифицированный компонент для всех типов нод
     */
    renderMappingSection(options = {}) {
        const { showInput = true, showOutput = true } = options;
        const config = this.nodeConfig;
        
        if (showInput && showOutput) {
            return html`
                <div class="form-group">
                    <state-mapping-editor
                        mode="both"
                        .inputMappings=${config.input_mapping || {}}
                        .outputMappings=${config.output_mapping || {}}
                        .stateVariables=${Object.keys(this._buildDefaultState())}
                        @input-change=${(e) => this._onInputChange('input_mapping', e.detail.value)}
                        @output-change=${(e) => this._onInputChange('output_mapping', e.detail.value)}
                    ></state-mapping-editor>
                </div>
            `;
        }
        
        if (showInput) {
            return html`
                <div class="form-group">
                    <state-mapping-editor
                        mode="input"
                        .mappings=${config.input_mapping || {}}
                        .stateVariables=${Object.keys(this._buildDefaultState())}
                        @change=${(e) => this._onInputChange('input_mapping', e.detail.value)}
                    ></state-mapping-editor>
                </div>
            `;
        }
        
        if (showOutput) {
            return html`
                <div class="form-group">
                    <state-mapping-editor
                        mode="output"
                        .mappings=${config.output_mapping || {}}
                        @change=${(e) => this._onInputChange('output_mapping', e.detail.value)}
                    ></state-mapping-editor>
                </div>
            `;
        }
        
        return '';
    }

    renderActions() {
        return html`
            <div class="form-actions">
                <platform-button variant="danger" size="sm" @click=${this._deleteNode}>
                    <platform-icon name="trash" size="16"></platform-icon>
                    Удалить ноду
                </platform-button>
            </div>
        `;
    }

    renderResourcesSection() {
        const nodeResources = this.nodeConfig?.resources || [];
        
        if (nodeResources.length === 0) {
            return html`
                <div class="form-group">
                    <div class="form-label">
                        <span class="form-label-text">Resources</span>
                    </div>
                    <div class="form-hint" style="padding: var(--space-3); border: 1px dashed var(--border-subtle); border-radius: var(--radius-md); text-align: center;">
                        Перетащите ресурсы на эту ноду или добавьте глобальные ресурсы на canvas
                    </div>
                </div>
            `;
        }
        
        return html`
            <div class="form-group">
                <div class="form-label">
                    <span class="form-label-text">Resources</span>
                </div>
                <div class="resources-list" style="display: flex; flex-direction: column; gap: var(--space-2);">
                    ${nodeResources.map(res => this._renderResourceBadge(res))}
                </div>
            </div>
        `;
    }

    _renderResourceBadge(resource) {
        const colors = {
            'code': '#8b5cf6',
            'rag': '#3b82f6',
            'files': '#f59e0b',
            'prompt': '#10b981',
            'llm': '#ec4899',
            'secret': '#ef4444',
            'http': '#06b6d4',
            'cache': '#14b8a6',
        };
        const icons = {
            'code': 'code',
            'rag': 'search',
            'files': 'folder',
            'prompt': 'chat',
            'llm': 'bot',
            'secret': 'key',
            'http': 'globe',
            'cache': 'database',
        };
        
        const color = colors[resource.type] || '#6b7280';
        const icon = icons[resource.type] || 'box';
        const bgColor = color + '20';
        
        return html`
            <div class="resource-badge" style="
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2);
                background: ${bgColor};
                border: 1px solid ${color}40;
                border-radius: var(--radius-md);
            ">
                <platform-icon name="${icon}" size="14" style="color: ${color};"></platform-icon>
                <span style="font-size: var(--text-sm); flex: 1;">${resource.resource_id || resource.resourceId}</span>
                <button 
                    class="remove-resource-btn"
                    style="background: none; border: none; padding: 2px; cursor: pointer; color: var(--text-tertiary);"
                    @click=${() => this._removeResource(resource.resource_id || resource.resourceId)}
                    title="Удалить ресурс"
                >
                    <platform-icon name="x" size="12"></platform-icon>
                </button>
            </div>
        `;
    }

    _removeResource(resourceId) {
        const nodeResources = this.nodeConfig?.resources || [];
        const updated = nodeResources.filter(r => (r.resource_id || r.resourceId) !== resourceId);
        this._updateConfig('resources', updated);
    }

    updated(changedProperties) {
        super.updated?.(changedProperties);
        if (changedProperties.has('expanded')) {
            if (this.expanded) {
                this.setAttribute('expanded', '');
            } else {
                this.removeAttribute('expanded');
            }
        }
    }

    render() {
        if (this.expanded) {
            return html`
                <div class="panel-body">
                    ${this.renderDescription()}
                    <div class="panel-layout">
                        <div class="panel-sidebar">
                            ${this.renderCommonFields()}
                        </div>
                        <div class="panel-main">
                            ${this.renderFields()}
                            ${this.renderActions()}
                        </div>
                    </div>
                </div>
            `;
        }
        
        return html`
            <div class="panel-body">
                ${this.renderDescription()}
                ${this.renderFields()}
                ${this.renderActions()}
            </div>
        `;
    }
}

customElements.define('base-node-editor', BaseNodeEditor);
