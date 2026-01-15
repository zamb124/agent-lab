/**
 * BaseNodeEditor - базовый класс для редакторов нод
 * Использует shared form стили (DRY)
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { formStyles } from '@platform/lib/styles/shared/form.styles.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';

export class BaseNodeEditor extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        formStyles,
        buttonStyles,
        css`
            .panel-body {
                /* padding управляется через .modal-content в glass-modal.js */
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
        agentId: { type: String },
        skillId: { type: String },
        agentVariables: { type: Object },
    };

    constructor() {
        super();
        this.nodeId = '';
        this.nodeConfig = {};
        this.agentId = '';
        this.skillId = '';
        this.agentVariables = {};
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
        };
        
        // agentVariables может быть Object или Array
        if (this.agentVariables) {
            if (Array.isArray(this.agentVariables)) {
                // Если массив [{key: 'name', value: 'John'}, ...]
                for (const varObj of this.agentVariables) {
                    if (varObj && varObj.key) {
                        defaultState[varObj.key] = varObj.value || '';
                    }
                }
            } else if (typeof this.agentVariables === 'object') {
                // Если объект {name: 'John', age: 30, ...}
                Object.assign(defaultState, this.agentVariables);
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
            agentId: this.agentId,
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
            const result = await this.a2a.validateNode(nodeType, this.nodeConfig, state, this.agentId, this.skillId);
            
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
            agentId: this.agentId,
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
                agentId: this.agentId,
                skillId: this.skillId
            });
            
            const result = await this.a2a.executeNode(nodeType, this.nodeConfig, state, this.agentId, this.skillId);
            
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
        return html`<p class="panel-description">Настройки ноды</p>`;
    }

    renderFields() {
        return html`<p>Override renderFields() in subclass</p>`;
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

    render() {
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
