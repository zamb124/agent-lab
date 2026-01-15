/**
 * PropertyPanel - контент панели свойств выбранной ноды
 * Оркестратор для node-editors компонентов
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { AgentsStore } from '../../store/agents.store.js';
import '../../components/nodes/index.js';

export class PropertyPanel extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                height: 100%;
            }
        `
    ];

    static properties = {
        node: { type: Object },
        agentId: { type: String, attribute: 'agent-id' },
        skillId: { type: String, attribute: 'skill-id' },
        agentConfig: { type: Object },
        agentVariables: { type: Object },
        expanded: { type: Boolean },
        config: { type: Object },
    };

    constructor() {
        super();
        this.node = null;
        this.agentId = '';
        this.skillId = 'base';
        this.agentConfig = null;
        this.agentVariables = {};
        this.expanded = false;
        this.config = null;
    }

    updated(changedProperties) {
        if ((changedProperties.has('node') || changedProperties.has('skillId') || changedProperties.has('agentConfig')) && this.node) {
            this._loadNodeConfig();
        }
    }

    _loadNodeConfig() {
        console.log('[PropertyPanel] Loading node config:', {
            node: this.node,
            hasConfig: !!this.node?.config,
            nodeKeys: this.node ? Object.keys(this.node) : []
        });
        
        const { position, id, color, ...config } = this.node;
        
        // ВАЖНО: type должен быть всегда
        if (!config.type) {
            console.error('[PropertyPanel] Нет type в ноде!', this.node);
            this.config = null;
            return;
        }
        
        // Если это новая нода (нет code/prompt), добавляем дефолтные значения
        if (!config.code && !config.prompt && !config.name) {
            const DEFAULT_CODE = `async def run(state):
    """
    Обработка state.
    
    Args:
        state: Текущее состояние
    
    Returns:
        Измененный state
    """
    return state
`;
            
            const defaults = {
                'react_node': { name: 'Новый агент', prompt: '', code: null },
                'function': { name: 'Новая функция', code: DEFAULT_CODE },
                'tool': { name: 'Новый инструмент', code: DEFAULT_CODE },
                'agent': { name: 'Новый суб-агент', agent_id: '' },
                'external_api': { name: 'Новый API', url: '', method: 'GET' },
                'remote_agent': { name: 'Новый удалённый агент', agent_url: '' },
                'mcp': { name: 'MCP Tool', server_id: '', tool_name: '' },
            };
            
            const typeDefaults = defaults[config.type] || {};
            Object.assign(config, typeDefaults);
        }
        
        this.config = config;
        
        console.log('[PropertyPanel] Extracted config:', this.config);
    }

    _onConfigChanged(e) {
        console.log('[PropertyPanel] _onConfigChanged called:', {
            nodeId: this.node?.id || this.node?.nodeId,
            field: e.detail.field,
            value: e.detail.value,
            config: e.detail.config
        });
        
        this.config = e.detail.config;
        this.emit('node-updated', {
            nodeId: this.node.id || this.node.nodeId,
            nodeConfig: this.config,
        });
        
        console.log('[PropertyPanel] Emitted node-updated:', {
            nodeId: this.node.id || this.node.nodeId,
            nodeConfig: this.config
        });
    }

    _onNodeDeleted() {
        this.emit('node-deleted', { nodeId: this.node.id || this.node.nodeId });
    }

    _onNodeIdChanged(e) {
        this.emit('node-id-changed', e.detail);
    }

    _renderDefaultPanel() {
        return html`
            <div style="padding: var(--space-4); text-align: center; color: var(--text-tertiary);">
                Выберите ноду для редактирования
            </div>
        `;
    }

    render() {
        if (!this.node) {
            return this._renderDefaultPanel();
        }
        
        // Инициализируем _config до первого рендера если он пустой
        if (!this.config || Object.keys(this.config).length === 0) {
            this._loadNodeConfig();
        }
        
        if (!this.node.type) {
            throw new Error('[PropertyPanel] Node type is missing');
        }

        const nodeType = this.node.type;
        
        switch (nodeType) {
            case 'react_node':
                return html`<react-node-editor
                    .nodeConfig=${this.config}
                    .nodeId=${this.node.id || this.node.nodeId}
                    .agentId=${this.agentId}
                    .skillId=${this.skillId}
                    .agentVariables=${this.agentVariables}
                    ?expanded=${this.expanded}
                    @config-change=${this._onConfigChanged}
                    @node-delete=${this._onNodeDeleted}
                    @node-id-changed=${this._onNodeIdChanged}
                ></react-node-editor>`;
            case 'function':
                return html`<function-node-editor
                    .nodeConfig=${this.config}
                    .nodeId=${this.node.id || this.node.nodeId}
                    .agentId=${this.agentId}
                    .skillId=${this.skillId}
                    .agentVariables=${this.agentVariables}
                    ?expanded=${this.expanded}
                    @config-change=${this._onConfigChanged}
                    @node-delete=${this._onNodeDeleted}
                    @node-id-changed=${this._onNodeIdChanged}
                ></function-node-editor>`;
            case 'tool':
                return html`<tool-node-editor
                    .nodeConfig=${this.config}
                    .nodeId=${this.node.id || this.node.nodeId}
                    .agentId=${this.agentId}
                    .skillId=${this.skillId}
                    .agentVariables=${this.agentVariables}
                    ?expanded=${this.expanded}
                    @config-change=${this._onConfigChanged}
                    @node-delete=${this._onNodeDeleted}
                    @node-id-changed=${this._onNodeIdChanged}
                ></tool-node-editor>`;
            case 'external_api':
                return html`<external-api-editor
                    .nodeConfig=${this.config}
                    .nodeId=${this.node.id || this.node.nodeId}
                    .agentId=${this.agentId}
                    .skillId=${this.skillId}
                    .agentVariables=${this.agentVariables}
                    ?expanded=${this.expanded}
                    @config-change=${this._onConfigChanged}
                    @node-delete=${this._onNodeDeleted}
                    @node-id-changed=${this._onNodeIdChanged}
                ></external-api-editor>`;
            case 'remote_agent':
                return html`<remote-agent-editor
                    .nodeConfig=${this.config}
                    .nodeId=${this.node.id || this.node.nodeId}
                    .agentId=${this.agentId}
                    .skillId=${this.skillId}
                    .agentVariables=${this.agentVariables}
                    ?expanded=${this.expanded}
                    @config-change=${this._onConfigChanged}
                    @node-delete=${this._onNodeDeleted}
                    @node-id-changed=${this._onNodeIdChanged}
                ></remote-agent-editor>`;
            case 'agent':
                return html`<agent-node-editor
                    .nodeConfig=${this.config}
                    .nodeId=${this.node.id || this.node.nodeId}
                    .agentId=${this.agentId}
                    .skillId=${this.skillId}
                    .agentVariables=${this.agentVariables}
                    ?expanded=${this.expanded}
                    @config-change=${this._onConfigChanged}
                    @node-delete=${this._onNodeDeleted}
                    @node-id-changed=${this._onNodeIdChanged}
                ></agent-node-editor>`;
            case 'mcp':
                return html`<mcp-node-editor
                    .nodeConfig=${this.config}
                    .nodeId=${this.node.id || this.node.nodeId}
                    .agentId=${this.agentId}
                    .skillId=${this.skillId}
                    .agentVariables=${this.agentVariables}
                    ?expanded=${this.expanded}
                    @config-change=${this._onConfigChanged}
                    @node-delete=${this._onNodeDeleted}
                    @node-id-changed=${this._onNodeIdChanged}
                ></mcp-node-editor>`;
            default:
                return this._renderDefaultPanel();
        }
    }
}

customElements.define('property-panel', PropertyPanel);
