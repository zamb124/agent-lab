/**
 * PropertyPanel - контент панели свойств выбранной ноды
 * Оркестратор для node-editors компонентов
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { FlowsStore } from '../../store/flows.store.js';
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
        flowId: { type: String, attribute: 'flow-id' },
        skillId: { type: String, attribute: 'skill-id' },
        flowConfig: { type: Object },
        flowVariables: { type: Object },
        previewExecutionState: { type: Object },
        expanded: { type: Boolean },
        config: { type: Object },
    };

    constructor() {
        super();
        this.node = null;
        this.flowId = '';
        this.skillId = 'base';
        this.flowConfig = null;
        this.flowVariables = {};
        this.previewExecutionState = null;
        this.expanded = false;
        this.config = null;
    }

    updated(changedProperties) {
        if ((changedProperties.has('node') || changedProperties.has('skillId') || changedProperties.has('flowConfig')) && this.node) {
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
            console.error('[PropertyPanel] Node has no type', this.node);
            this.config = null;
            return;
        }

        // Если это новая нода (нет code/prompt), добавляем дефолтные значения
        if (!config.code && !config.prompt && !config.name) {
            const defaultCode = this.i18n.t('node_defaults.python_stub');
            
            const defaults = {
                'llm_node': { name: this.i18n.t('node_defaults.name_llm_node'), prompt: '', code: null },
                'code': { name: this.i18n.t('node_defaults.name_function'), code: defaultCode },
                'flow': { name: this.i18n.t('node_defaults.name_flow'), flow_id: '' },
                'external_api': { name: this.i18n.t('node_defaults.name_api'), url: '', method: 'GET' },
                'remote_flow': { name: this.i18n.t('node_defaults.name_remote_flow'), url: '' },
                'mcp': { name: this.i18n.t('node_defaults.name_mcp'), server_id: '', tool_name: '' },
                'channel': { name: this.i18n.t('node_defaults.name_channel'), channel: 'telegram', action: 'send_message', channel_config: {} },
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
        
        const next = e.detail.config;
        this.config = next;
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

    _graphNodesFromFlow() {
        const raw = this.flowConfig?.nodes;
        if (!raw || typeof raw !== 'object') {
            return [];
        }
        return Object.keys(raw).map((id) => ({
            id,
            name: raw[id]?.name || id,
            type: raw[id]?.type || '',
        }));
    }

    _renderDefaultPanel() {
        return html`
            <div style="padding: var(--space-4); text-align: center; color: var(--text-tertiary);">
                ${this.i18n.t('property_panel.select_node')}
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
        const allowNodeIdRenameOnce = this.node.allowNodeIdRenameOnce === true;

        switch (nodeType) {
            case 'llm_node':
                return html`<llm-node-editor
                    .nodeConfig=${this.config}
                    .nodeId=${this.node.id || this.node.nodeId}
                    .flowId=${this.flowId}
                    .skillId=${this.skillId}
                    .flowVariables=${this.flowVariables}
                    .previewExecutionState=${this.previewExecutionState}
                    .graphNodes=${this._graphNodesFromFlow()}
                    ?expanded=${this.expanded}
                    .allowNodeIdRenameOnce=${allowNodeIdRenameOnce}
                    @config-change=${this._onConfigChanged}
                    @node-delete=${this._onNodeDeleted}
                    @node-id-changed=${this._onNodeIdChanged}
                ></llm-node-editor>`;
            case 'code':
                return html`<code-node-editor
                    .nodeConfig=${this.config}
                    .nodeId=${this.node.id || this.node.nodeId}
                    .flowId=${this.flowId}
                    .skillId=${this.skillId}
                    .flowVariables=${this.flowVariables}
                    .previewExecutionState=${this.previewExecutionState}
                    ?expanded=${this.expanded}
                    .allowNodeIdRenameOnce=${allowNodeIdRenameOnce}
                    @config-change=${this._onConfigChanged}
                    @node-delete=${this._onNodeDeleted}
                    @node-id-changed=${this._onNodeIdChanged}
                ></code-node-editor>`;
            case 'external_api':
                return html`<external-api-editor
                    .nodeConfig=${this.config}
                    .nodeId=${this.node.id || this.node.nodeId}
                    .flowId=${this.flowId}
                    .skillId=${this.skillId}
                    .flowVariables=${this.flowVariables}
                    .previewExecutionState=${this.previewExecutionState}
                    ?expanded=${this.expanded}
                    .allowNodeIdRenameOnce=${allowNodeIdRenameOnce}
                    @config-change=${this._onConfigChanged}
                    @node-delete=${this._onNodeDeleted}
                    @node-id-changed=${this._onNodeIdChanged}
                ></external-api-editor>`;
            case 'remote_flow':
                return html`<remote-flow-editor
                    .nodeConfig=${this.config}
                    .nodeId=${this.node.id || this.node.nodeId}
                    .flowId=${this.flowId}
                    .skillId=${this.skillId}
                    .flowVariables=${this.flowVariables}
                    .previewExecutionState=${this.previewExecutionState}
                    ?expanded=${this.expanded}
                    .allowNodeIdRenameOnce=${allowNodeIdRenameOnce}
                    @config-change=${this._onConfigChanged}
                    @node-delete=${this._onNodeDeleted}
                    @node-id-changed=${this._onNodeIdChanged}
                ></remote-flow-editor>`;
            case 'flow':
                return html`<flow-node-editor
                    .nodeConfig=${this.config}
                    .nodeId=${this.node.id || this.node.nodeId}
                    .flowId=${this.flowId}
                    .skillId=${this.skillId}
                    .flowVariables=${this.flowVariables}
                    .previewExecutionState=${this.previewExecutionState}
                    ?expanded=${this.expanded}
                    .allowNodeIdRenameOnce=${allowNodeIdRenameOnce}
                    @config-change=${this._onConfigChanged}
                    @node-delete=${this._onNodeDeleted}
                    @node-id-changed=${this._onNodeIdChanged}
                ></flow-node-editor>`;
            case 'mcp':
                return html`<mcp-node-editor
                    .nodeConfig=${this.config}
                    .nodeId=${this.node.id || this.node.nodeId}
                    .flowId=${this.flowId}
                    .skillId=${this.skillId}
                    .flowVariables=${this.flowVariables}
                    .previewExecutionState=${this.previewExecutionState}
                    ?expanded=${this.expanded}
                    .allowNodeIdRenameOnce=${allowNodeIdRenameOnce}
                    @config-change=${this._onConfigChanged}
                    @node-delete=${this._onNodeDeleted}
                    @node-id-changed=${this._onNodeIdChanged}
                ></mcp-node-editor>`;
            case 'channel':
                return html`<channel-node-editor
                    .nodeConfig=${this.config}
                    .nodeId=${this.node.id || this.node.nodeId}
                    .flowId=${this.flowId}
                    .skillId=${this.skillId}
                    .flowVariables=${this.flowVariables}
                    .previewExecutionState=${this.previewExecutionState}
                    ?expanded=${this.expanded}
                    .allowNodeIdRenameOnce=${allowNodeIdRenameOnce}
                    @config-change=${this._onConfigChanged}
                    @node-delete=${this._onNodeDeleted}
                    @node-id-changed=${this._onNodeIdChanged}
                ></channel-node-editor>`;
            default:
                return this._renderDefaultPanel();
        }
    }
}

customElements.define('property-panel', PropertyPanel);
