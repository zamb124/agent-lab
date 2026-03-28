/**
 * InlineToolModal - универсальная модалка для редактирования inline инструментов
 * Поддерживает все типы: tool, flow, llm_node, function, external_api, remote_flow
 */
import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import '../components/nodes/index.js';

export class InlineToolModal extends PlatformModal {
    static styles = [
        PlatformModal.styles,
        css`
            :host {
                --modal-max-width: 900px;
            }
            
            .modal-content-wrapper {
                position: relative;
                min-height: 400px;
            }

            .action-row {
                display: flex;
                gap: var(--space-3);
                padding-top: var(--space-2);
            }
            
            .btn {
                padding: var(--space-2) var(--space-4);
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                border-radius: var(--radius-md);
                border: 1px solid var(--border-default);
                cursor: pointer;
                transition: all var(--duration-fast) var(--easing-default);
            }
            
            .btn-primary {
                color: white;
                background: var(--accent);
                border-color: var(--accent);
            }
            
            .btn-primary:hover {
                background: var(--accent-hover);
            }
            
            .btn-secondary {
                color: var(--text-primary);
                background: var(--glass-tint-medium);
            }
            
            .btn-secondary:hover {
                background: var(--glass-tint-strong);
            }
        `
    ];

    static properties = {
        toolConfig: { type: Object },
        toolType: { type: String },
        mode: { type: String },
        flowVariables: { type: Object },
        flowId: { type: String },
        skillId: { type: String },
        previewExecutionState: { type: Object },
    };

    constructor() {
        super();
        this.toolConfig = {};
        this.toolType = 'tool';
        this.mode = 'create';
        this.flowVariables = {};
        this.flowId = '';
        this.skillId = 'base';
        this.previewExecutionState = null;
        this._updateModalTitle();
    }

    connectedCallback() {
        super.connectedCallback();
        this._updateModalTitle();
    }

    updated(changedProperties) {
        super.updated(changedProperties);
        if (changedProperties.has('toolType') || changedProperties.has('mode')) {
            this._updateModalTitle();
        }
    }

    _updateModalTitle() {
        const typeLabels = {
            'tool': 'Tool',
            'llm_node': 'LLM Node',
            'flow': 'Flow',
            'function': 'Function',
            'external_api': 'External API',
            'remote_flow': 'Remote A2A flow',
            'mcp': 'MCP Tool'
        };
        
        const label = typeLabels[this.toolType] || 'Инструмент';
        this.title = this.mode === 'create' ? `Создать ${label}` : `Редактировать ${label}`;
    }

    _onConfigChanged(e) {
        this.toolConfig = { ...this.toolConfig, ...e.detail.config };
    }

    _onSave() {
        const editor = this.shadowRoot.querySelector('[data-editor]');
        if (!editor) {
            this.error('Редактор не найден');
            return;
        }

        const config = editor.nodeConfig;
        
        // Валидация в зависимости от типа
        if (this.toolType === 'tool' && (!config.code || !config.code.trim())) {
            this.error('Код обязателен для tool');
            return;
        }
        
        if (this.toolType === 'llm_node' && (!config.prompt || !config.prompt.trim())) {
            this.error('Промпт обязателен для llm_node');
            return;
        }
        
        if (!config.name || !config.name.trim()) {
            this.error('Название обязательно');
            return;
        }
        
        // Генерируем tool_id если его нет
        const toolId = this.toolConfig.tool_id || this._generateToolId(config.name);
        
        const finalConfig = {
            ...config,
            tool_id: toolId,
            type: this.toolType,
        };
        
        this.emit('tool-saved', { toolId, config: finalConfig });
        this.close();
    }

    _generateToolId(name) {
        return name
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, '_')
            .replace(/^_+|_+$/g, '');
    }

    _renderEditor() {
        const config = this.toolConfig;
        
        switch (this.toolType) {
            case 'tool':
                return html`
                    <tool-node-editor
                        data-editor
                        .nodeConfig=${config}
                        .flowId=${this.flowId}
                        .skillId=${this.skillId}
                        .flowVariables=${this.flowVariables}
                        .previewExecutionState=${this.previewExecutionState}
                        @config-change=${this._onConfigChanged}
                    ></tool-node-editor>
                `;
            
            case 'llm_node':
            case 'flow':
                return html`
                    <llm-node-editor
                        data-editor
                        .nodeConfig=${config}
                        .flowId=${this.flowId}
                        .skillId=${this.skillId}
                        .flowVariables=${this.flowVariables}
                        .previewExecutionState=${this.previewExecutionState}
                        @config-change=${this._onConfigChanged}
                    ></llm-node-editor>
                `;
            
            case 'function':
                return html`
                    <function-node-editor
                        data-editor
                        .nodeConfig=${config}
                        .flowId=${this.flowId}
                        .skillId=${this.skillId}
                        .flowVariables=${this.flowVariables}
                        .previewExecutionState=${this.previewExecutionState}
                        @config-change=${this._onConfigChanged}
                    ></function-node-editor>
                `;
            
            case 'external_api':
                return html`
                    <external-api-editor
                        data-editor
                        .nodeConfig=${config}
                        .flowId=${this.flowId}
                        .skillId=${this.skillId}
                        .flowVariables=${this.flowVariables}
                        .previewExecutionState=${this.previewExecutionState}
                        @config-change=${this._onConfigChanged}
                    ></external-api-editor>
                `;
            
            case 'remote_flow':
                return html`
                    <remote-flow-editor
                        data-editor
                        .nodeConfig=${config}
                        .flowId=${this.flowId}
                        .skillId=${this.skillId}
                        .flowVariables=${this.flowVariables}
                        .previewExecutionState=${this.previewExecutionState}
                        @config-change=${this._onConfigChanged}
                    ></remote-flow-editor>
                `;
            
            case 'mcp':
                return html`
                    <mcp-node-editor
                        data-editor
                        .nodeConfig=${config}
                        .flowId=${this.flowId}
                        .skillId=${this.skillId}
                        .flowVariables=${this.flowVariables}
                        .previewExecutionState=${this.previewExecutionState}
                        @config-change=${this._onConfigChanged}
                    ></mcp-node-editor>
                `;
            
            default:
                return html`<div>Неизвестный тип инструмента: ${this.toolType}</div>`;
        }
    }

    renderBody() {
        return html`
            <div class="modal-content-wrapper">
                ${this._renderEditor()}
            </div>
        `;
    }

    renderFooter() {
        return html`
            <div class="action-row">
                <button type="button" class="btn btn-secondary" @click=${this.close}>
                    Отмена
                </button>
                <button type="button" class="btn btn-primary" @click=${this._onSave}>
                    ${this.mode === 'create' ? 'Создать' : 'Сохранить'}
                </button>
            </div>
        `;
    }
}

customElements.define('inline-tool-modal', InlineToolModal);

