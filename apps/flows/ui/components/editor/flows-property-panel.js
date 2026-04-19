/**
 * flows-property-panel — слот для активного редактора ноды.
 *
 * Читает selectedNodeId + skillsData из useOp('flows/editor'). Применяет
 * патч к ноде и диспатчит обратно в фабрику updateSkillsData.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '../nodes/flows-llm-node-editor.js';
import '../nodes/flows-code-node-editor.js';
import '../nodes/flows-channel-node-editor.js';
import '../nodes/flows-flow-node-editor.js';
import '../nodes/flows-mcp-node-editor.js';
import '../nodes/flows-hitl-node-editor.js';
import '../nodes/flows-external-api-editor.js';
import '../nodes/flows-remote-flow-editor.js';
import '../nodes/flows-base-node-editor.js';

const NODE_TAG_BY_TYPE = {
    llm_node: 'flows-llm-node-editor',
    code: 'flows-code-node-editor',
    channel: 'flows-channel-node-editor',
    flow_node: 'flows-flow-node-editor',
    mcp_node: 'flows-mcp-node-editor',
    hitl_node: 'flows-hitl-node-editor',
    external_api: 'flows-external-api-editor',
    remote_flow: 'flows-remote-flow-editor',
};

export class FlowsPropertyPanel extends PlatformElement {
    static properties = {
        flowId: { type: String },
        skillId: { type: String },
    };

    static styles = [
        PlatformElement.styles,
        css`:host { display: block; }`,
    ];

    constructor() {
        super();
        this.flowId = '';
        this.skillId = 'base';
        this._editor = this.useOp('flows/editor');
    }

    _onChange(e) {
        const { nodeId, patch } = e.detail || {};
        if (!nodeId || !patch) return;
        const state = this._editor.state;
        const skillsData = state?.skillsData || { nodes: {}, edges: [], variables: {}, resources: {} };
        const nodes = { ...skillsData.nodes };
        const node = nodes[nodeId];
        if (!node) return;
        nodes[nodeId] = { ...node, ...patch };
        this._editor.updateSkillsData({ data: { ...skillsData, nodes } });
        this._editor.setDirty({ dirty: true });
    }

    _renderEditor(node, nodeId) {
        const props = {
            nodeId,
            flowId: this.flowId,
            skillId: this.skillId,
            nodeConfig: node,
            nodeType: node.type || '',
        };
        switch (node.type) {
            case 'llm_node':
                return html`<flows-llm-node-editor
                    .nodeId=${props.nodeId} .flowId=${props.flowId} .skillId=${props.skillId}
                    .nodeConfig=${props.nodeConfig} @change=${this._onChange}></flows-llm-node-editor>`;
            case 'code':
                return html`<flows-code-node-editor
                    .nodeId=${props.nodeId} .flowId=${props.flowId} .skillId=${props.skillId}
                    .nodeConfig=${props.nodeConfig} @change=${this._onChange}></flows-code-node-editor>`;
            case 'channel':
                return html`<flows-channel-node-editor
                    .nodeId=${props.nodeId} .flowId=${props.flowId} .skillId=${props.skillId}
                    .nodeConfig=${props.nodeConfig} @change=${this._onChange}></flows-channel-node-editor>`;
            case 'flow_node':
                return html`<flows-flow-node-editor
                    .nodeId=${props.nodeId} .flowId=${props.flowId} .skillId=${props.skillId}
                    .nodeConfig=${props.nodeConfig} @change=${this._onChange}></flows-flow-node-editor>`;
            case 'mcp_node':
                return html`<flows-mcp-node-editor
                    .nodeId=${props.nodeId} .flowId=${props.flowId} .skillId=${props.skillId}
                    .nodeConfig=${props.nodeConfig} @change=${this._onChange}></flows-mcp-node-editor>`;
            case 'hitl_node':
                return html`<flows-hitl-node-editor
                    .nodeId=${props.nodeId} .flowId=${props.flowId} .skillId=${props.skillId}
                    .nodeConfig=${props.nodeConfig} @change=${this._onChange}></flows-hitl-node-editor>`;
            case 'external_api':
                return html`<flows-external-api-editor
                    .nodeId=${props.nodeId} .flowId=${props.flowId} .skillId=${props.skillId}
                    .nodeConfig=${props.nodeConfig} @change=${this._onChange}></flows-external-api-editor>`;
            case 'remote_flow':
                return html`<flows-remote-flow-editor
                    .nodeId=${props.nodeId} .flowId=${props.flowId} .skillId=${props.skillId}
                    .nodeConfig=${props.nodeConfig} @change=${this._onChange}></flows-remote-flow-editor>`;
            default:
                return html`<flows-base-node-editor
                    .nodeId=${props.nodeId} .flowId=${props.flowId} .skillId=${props.skillId}
                    .nodeConfig=${props.nodeConfig} .nodeType=${props.nodeType}
                    @change=${this._onChange}></flows-base-node-editor>`;
        }
    }

    render() {
        const state = this._editor.state || {};
        const nodeId = state.selectedNodeId;
        if (!nodeId) {
            return html`<div style="padding: var(--space-3); color: var(--text-tertiary)">${this.t('property_panel.select_node')}</div>`;
        }
        const skillsData = state.skillsData || { nodes: {} };
        const node = skillsData.nodes?.[nodeId];
        if (!node) return html`<div></div>`;
        return this._renderEditor(node, nodeId);
    }
}

customElements.define('flows-property-panel', FlowsPropertyPanel);
