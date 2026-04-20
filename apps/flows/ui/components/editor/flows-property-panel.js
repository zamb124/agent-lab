/**
 * flows-property-panel — слот для активного редактора ноды.
 *
 * Читает selectedNodeId, skillsData, variables, previewExecutionState из
 * useOp('flows/editor'). Маршрутизирует по `node.type` (NodeType enum).
 *
 * Действия от base-node-editor:
 *   - 'change' { nodeId, patch } → updateSkillsData(merge node)
 *   - 'rename-node' { oldId, newId } → renameNodeId(action) + bus event
 *     `flows/editor/node_id_changed` → reducer обновляет nodes/edges/entry
 *   - 'delete-node' { nodeId } → bulk_delete + локальный removeNode
 *   - 'duplicate-node' { nodeId } → клонирует node под новым id
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
import { asArray, asObject, asNumber, asString, isPlainObject, getSkillsData, getSkillsNodes } from '../../_helpers/flows-resolvers.js';

export class FlowsPropertyPanel extends PlatformElement {
    static properties = {
        flowId: { type: String },
        skillId: { type: String },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; height: 100%; min-height: 0; }
            .inherited-banner {
                margin: var(--space-3);
                padding: var(--space-2) var(--space-3);
                background: var(--accent-subtle, var(--info-bg));
                border: 1px dashed var(--accent, var(--info));
                border-radius: var(--radius-sm);
                color: var(--text-secondary);
                font-size: var(--text-sm);
                line-height: 1.4;
                display: flex;
                gap: var(--space-2);
                align-items: flex-start;
            }
            .inherited-banner .badge {
                color: var(--accent, var(--info));
                font-weight: var(--font-semibold);
            }
        `,
    ];

    constructor() {
        super();
        this.flowId = '';
        this.skillId = 'base';
        this._editor = this.useOp('flows/editor');
        this._bulkDelete = this.useOp('flows/editor_bulk_delete');
    }

    _onChange(e) {
        const { nodeId, patch } = isPlainObject(e.detail) ? e.detail : {};
        if (!nodeId || !patch || typeof patch !== 'object') return;
        const state = this._editor.state;
        if (!state) return;
        const skillsData = state.skillsData;
        if (!skillsData || typeof skillsData !== 'object') return;
        const nodes = skillsData.nodes && typeof skillsData.nodes === 'object' ? { ...skillsData.nodes } : {};
        const node = nodes[nodeId];
        if (!node) return;
        nodes[nodeId] = { ...node, ...patch };
        this._editor.updateSkillsData({ data: { ...skillsData, nodes } });
        this._editor.setDirty({ dirty: true });
        this._editor.pushHistory({ snapshot: { ...skillsData, nodes } });
    }

    _onRenameNode(e) {
        const { oldId, newId } = isPlainObject(e.detail) ? e.detail : {};
        if (typeof oldId !== 'string' || typeof newId !== 'string') return;
        const state = this._editor.state;
        const nodes = state?.skillsData?.nodes;
        if (!nodes || !(oldId in nodes)) return;
        if (newId in nodes) {
            this.toast('flows:base_node_editor.rename_collision', { type: 'error' });
            return;
        }
        this._editor.renameNodeId({ oldId, newId });
    }

    async _onDeleteNode(e) {
        const { nodeId } = isPlainObject(e.detail) ? e.detail : {};
        if (typeof nodeId !== 'string' || !nodeId) return;
        if (!this.flowId) return;
        await this._bulkDelete.run({ flow_id: this.flowId, node_ids: [nodeId] });
        this._editor.removeNode({ nodeId });
    }

    _onDuplicateNode(e) {
        const { nodeId } = isPlainObject(e.detail) ? e.detail : {};
        if (typeof nodeId !== 'string' || !nodeId) return;
        const state = this._editor.state;
        const skillsData = state?.skillsData;
        const nodes = skillsData?.nodes;
        if (!nodes || !nodes[nodeId]) return;
        const baseId = `${nodeId}_copy`;
        let newId = baseId;
        let suffix = 1;
        while (newId in nodes) {
            suffix += 1;
            newId = `${baseId}_${suffix}`;
        }
        const source = nodes[nodeId];
        const copy = JSON.parse(JSON.stringify(source));
        copy.node_id = newId;
        if (typeof copy.name === 'string') copy.name = `${copy.name} copy`;
        if (copy.position && typeof copy.position === 'object') {
            copy.position = {
                x: asNumber(copy.position.x) + 40,
                y: asNumber(copy.position.y) + 40,
            };
        }
        const nextNodes = { ...nodes, [newId]: copy };
        const nextData = { ...skillsData, nodes: nextNodes };
        this._editor.updateSkillsData({ data: nextData });
        this._editor.setDirty({ dirty: true });
        this._editor.pushHistory({ snapshot: nextData });
        this._editor.selectNode({ nodeId: newId });
    }

    _renderEditor(node, nodeId) {
        const state = asObject(this._editor.state);
        const skillsData = isPlainObject(state.skillsData) ? state.skillsData : {};
        const flowVariables = skillsData.variables && typeof skillsData.variables === 'object' ? skillsData.variables : {};
        const graphNodes = skillsData.nodes && typeof skillsData.nodes === 'object'
            ? Object.entries(skillsData.nodes).map(([id, n]) => ({ id, name: typeof n?.name === 'string' && n.name.length > 0 ? n.name : id, type: asString(n?.type) }))
            : [];
        const previewExecutionState = state.previewExecutionState;
        const expanded = state.panelExpanded === true;
        const onChange = (e) => this._onChange(e);
        const onRename = (e) => this._onRenameNode(e);
        const onDelete = (e) => this._onDeleteNode(e);
        const onDuplicate = (e) => this._onDuplicateNode(e);
        switch (node.type) {
            case 'llm_node':
                return html`<flows-llm-node-editor
                    .nodeId=${nodeId} .flowId=${this.flowId} .skillId=${this.skillId}
                    .nodeConfig=${node} .nodeType=${node.type}
                    .flowVariables=${flowVariables} .graphNodes=${graphNodes}
                    .previewExecutionState=${previewExecutionState}
                    ?expanded=${expanded}
                    @change=${onChange} @rename-node=${onRename}
                    @delete-node=${onDelete} @duplicate-node=${onDuplicate}
                ></flows-llm-node-editor>`;
            case 'code':
                return html`<flows-code-node-editor
                    .nodeId=${nodeId} .flowId=${this.flowId} .skillId=${this.skillId}
                    .nodeConfig=${node} .nodeType=${node.type}
                    .flowVariables=${flowVariables} .graphNodes=${graphNodes}
                    .previewExecutionState=${previewExecutionState}
                    ?expanded=${expanded}
                    @change=${onChange} @rename-node=${onRename}
                    @delete-node=${onDelete} @duplicate-node=${onDuplicate}
                ></flows-code-node-editor>`;
            case 'channel':
                return html`<flows-channel-node-editor
                    .nodeId=${nodeId} .flowId=${this.flowId} .skillId=${this.skillId}
                    .nodeConfig=${node} .nodeType=${node.type}
                    .flowVariables=${flowVariables} .graphNodes=${graphNodes}
                    .previewExecutionState=${previewExecutionState}
                    ?expanded=${expanded}
                    @change=${onChange} @rename-node=${onRename}
                    @delete-node=${onDelete} @duplicate-node=${onDuplicate}
                ></flows-channel-node-editor>`;
            case 'flow':
                return html`<flows-flow-node-editor
                    .nodeId=${nodeId} .flowId=${this.flowId} .skillId=${this.skillId}
                    .nodeConfig=${node} .nodeType=${node.type}
                    .flowVariables=${flowVariables} .graphNodes=${graphNodes}
                    .previewExecutionState=${previewExecutionState}
                    ?expanded=${expanded}
                    @change=${onChange} @rename-node=${onRename}
                    @delete-node=${onDelete} @duplicate-node=${onDuplicate}
                ></flows-flow-node-editor>`;
            case 'mcp':
                return html`<flows-mcp-node-editor
                    .nodeId=${nodeId} .flowId=${this.flowId} .skillId=${this.skillId}
                    .nodeConfig=${node} .nodeType=${node.type}
                    .flowVariables=${flowVariables} .graphNodes=${graphNodes}
                    .previewExecutionState=${previewExecutionState}
                    ?expanded=${expanded}
                    @change=${onChange} @rename-node=${onRename}
                    @delete-node=${onDelete} @duplicate-node=${onDuplicate}
                ></flows-mcp-node-editor>`;
            case 'hitl_node':
                return html`<flows-hitl-node-editor
                    .nodeId=${nodeId} .flowId=${this.flowId} .skillId=${this.skillId}
                    .nodeConfig=${node} .nodeType=${node.type}
                    .flowVariables=${flowVariables} .graphNodes=${graphNodes}
                    .previewExecutionState=${previewExecutionState}
                    ?expanded=${expanded}
                    @change=${onChange} @rename-node=${onRename}
                    @delete-node=${onDelete} @duplicate-node=${onDuplicate}
                ></flows-hitl-node-editor>`;
            case 'external_api':
                return html`<flows-external-api-editor
                    .nodeId=${nodeId} .flowId=${this.flowId} .skillId=${this.skillId}
                    .nodeConfig=${node} .nodeType=${node.type}
                    .flowVariables=${flowVariables} .graphNodes=${graphNodes}
                    .previewExecutionState=${previewExecutionState}
                    ?expanded=${expanded}
                    @change=${onChange} @rename-node=${onRename}
                    @delete-node=${onDelete} @duplicate-node=${onDuplicate}
                ></flows-external-api-editor>`;
            case 'remote_flow':
                return html`<flows-remote-flow-editor
                    .nodeId=${nodeId} .flowId=${this.flowId} .skillId=${this.skillId}
                    .nodeConfig=${node} .nodeType=${node.type}
                    .flowVariables=${flowVariables} .graphNodes=${graphNodes}
                    .previewExecutionState=${previewExecutionState}
                    ?expanded=${expanded}
                    @change=${onChange} @rename-node=${onRename}
                    @delete-node=${onDelete} @duplicate-node=${onDuplicate}
                ></flows-remote-flow-editor>`;
            default:
                return html`<flows-base-node-editor
                    .nodeId=${nodeId} .flowId=${this.flowId} .skillId=${this.skillId}
                    .nodeConfig=${node} .nodeType=${asString(node.type)}
                    .flowVariables=${flowVariables} .graphNodes=${graphNodes}
                    .previewExecutionState=${previewExecutionState}
                    ?expanded=${expanded}
                    @change=${onChange} @rename-node=${onRename}
                    @delete-node=${onDelete} @duplicate-node=${onDuplicate}
                ></flows-base-node-editor>`;
        }
    }

    render() {
        const state = asObject(this._editor.state);
        const nodeId = state.selectedNodeId;
        if (!nodeId) {
            return html`<div style="padding: var(--space-3); color: var(--text-tertiary)">${this.t('property_panel.select_node')}</div>`;
        }
        const skillsData = isPlainObject(state.skillsData) ? state.skillsData : { nodes: {} };
        const node = skillsData.nodes?.[nodeId];
        if (!node) return html`<div></div>`;
        const isInherited = asArray(state.inheritedNodeIds).includes(nodeId);
        return html`
            ${isInherited ? html`
                <div class="inherited-banner">
                    <span class="badge">↑</span>
                    <span>${this.t('property_panel.inherited_hint')}</span>
                </div>
            ` : ''}
            ${this._renderEditor(node, nodeId)}
        `;
    }
}

customElements.define('flows-property-panel', FlowsPropertyPanel);
