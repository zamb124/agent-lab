/**
 * Тот же выбор type-specific редактора, что в flows-property-panel.
 */

import { html } from 'lit';
import { asString, isPlainObject } from '../../_helpers/flows-resolvers.js';

import '../nodes/flows-llm-node-editor.js';
import '../nodes/flows-code-node-editor.js';
import '../nodes/flows-channel-node-editor.js';
import '../nodes/flows-flow-node-editor.js';
import '../nodes/flows-mcp-node-editor.js';
import '../nodes/flows-hitl-node-editor.js';
import '../nodes/flows-external-api-editor.js';
import '../nodes/flows-remote-flow-editor.js';
import '../nodes/flows-base-node-editor.js';

/**
 * @param {object} ctx
 * @param {object} ctx.node
 * @param {string} ctx.nodeId
 * @param {string} ctx.flowId
 * @param {string} ctx.branchId
 * @param {object} ctx.flowVariables
 * @param {Array<{id:string,name:string,type:string}>} ctx.graphNodes
 * @param {object} ctx.previewExecutionState
 * @param {boolean} ctx.expanded
 * @param {boolean} [ctx.embedded]
 * @param {(e: CustomEvent) => void} ctx.onChange
 * @param {(e: CustomEvent) => void} ctx.onRename
 * @param {(e: CustomEvent) => void} ctx.onDelete
 * @param {(e: CustomEvent) => void} ctx.onDuplicate
 */
export function renderFlowsNodeEditorSurface(ctx) {
    const node = isPlainObject(ctx.node) ? ctx.node : null;
    if (node === null) {
        throw new Error('flows-node-editor-surface: node is required');
    }
    const nodeId = asString(ctx.nodeId);
    if (nodeId.length === 0) {
        throw new Error('flows-node-editor-surface: nodeId is required');
    }
    const flowId = asString(ctx.flowId);
    const branchId = asString(ctx.branchId);
    const flowVariables = isPlainObject(ctx.flowVariables) ? ctx.flowVariables : {};
    const graphNodes = Array.isArray(ctx.graphNodes) ? ctx.graphNodes : [];
    const preview = ctx.previewExecutionState;
    const expanded = ctx.expanded === true;
    const embedded = ctx.embedded === true;
    const onChange = ctx.onChange;
    const onRename = ctx.onRename;
    const onDelete = ctx.onDelete;
    const onDuplicate = ctx.onDuplicate;
    if (typeof onChange !== 'function') {
        throw new Error('flows-node-editor-surface: onChange is required');
    }
    if (typeof onRename !== 'function') {
        throw new Error('flows-node-editor-surface: onRename is required');
    }
    if (typeof onDelete !== 'function') {
        throw new Error('flows-node-editor-surface: onDelete is required');
    }
    if (typeof onDuplicate !== 'function') {
        throw new Error('flows-node-editor-surface: onDuplicate is required');
    }

    switch (node.type) {
        case 'llm_node':
            return html`<flows-llm-node-editor
                .nodeId=${nodeId} .flowId=${flowId} .branchId=${branchId}
                .nodeConfig=${node} .nodeType=${node.type}
                .flowVariables=${flowVariables} .graphNodes=${graphNodes}
                .previewExecutionState=${preview}
                ?expanded=${expanded} ?embedded=${embedded}
                @change=${onChange} @rename-node=${onRename}
                @delete-node=${onDelete} @duplicate-node=${onDuplicate}
            ></flows-llm-node-editor>`;
        case 'code':
            return html`<flows-code-node-editor
                .nodeId=${nodeId} .flowId=${flowId} .branchId=${branchId}
                .nodeConfig=${node} .nodeType=${node.type}
                .flowVariables=${flowVariables} .graphNodes=${graphNodes}
                .previewExecutionState=${preview}
                ?expanded=${expanded} ?embedded=${embedded}
                @change=${onChange} @rename-node=${onRename}
                @delete-node=${onDelete} @duplicate-node=${onDuplicate}
            ></flows-code-node-editor>`;
        case 'channel':
            return html`<flows-channel-node-editor
                .nodeId=${nodeId} .flowId=${flowId} .branchId=${branchId}
                .nodeConfig=${node} .nodeType=${node.type}
                .flowVariables=${flowVariables} .graphNodes=${graphNodes}
                .previewExecutionState=${preview}
                ?expanded=${expanded} ?embedded=${embedded}
                @change=${onChange} @rename-node=${onRename}
                @delete-node=${onDelete} @duplicate-node=${onDuplicate}
            ></flows-channel-node-editor>`;
        case 'flow':
            return html`<flows-flow-node-editor
                .nodeId=${nodeId} .flowId=${flowId} .branchId=${branchId}
                .nodeConfig=${node} .nodeType=${node.type}
                .flowVariables=${flowVariables} .graphNodes=${graphNodes}
                .previewExecutionState=${preview}
                ?expanded=${expanded} ?embedded=${embedded}
                @change=${onChange} @rename-node=${onRename}
                @delete-node=${onDelete} @duplicate-node=${onDuplicate}
            ></flows-flow-node-editor>`;
        case 'mcp':
            return html`<flows-mcp-node-editor
                .nodeId=${nodeId} .flowId=${flowId} .branchId=${branchId}
                .nodeConfig=${node} .nodeType=${node.type}
                .flowVariables=${flowVariables} .graphNodes=${graphNodes}
                .previewExecutionState=${preview}
                ?expanded=${expanded} ?embedded=${embedded}
                @change=${onChange} @rename-node=${onRename}
                @delete-node=${onDelete} @duplicate-node=${onDuplicate}
            ></flows-mcp-node-editor>`;
        case 'hitl_node':
            return html`<flows-hitl-node-editor
                .nodeId=${nodeId} .flowId=${flowId} .branchId=${branchId}
                .nodeConfig=${node} .nodeType=${node.type}
                .flowVariables=${flowVariables} .graphNodes=${graphNodes}
                .previewExecutionState=${preview}
                ?expanded=${expanded} ?embedded=${embedded}
                @change=${onChange} @rename-node=${onRename}
                @delete-node=${onDelete} @duplicate-node=${onDuplicate}
            ></flows-hitl-node-editor>`;
        case 'external_api':
            return html`<flows-external-api-editor
                .nodeId=${nodeId} .flowId=${flowId} .branchId=${branchId}
                .nodeConfig=${node} .nodeType=${node.type}
                .flowVariables=${flowVariables} .graphNodes=${graphNodes}
                .previewExecutionState=${preview}
                ?expanded=${expanded} ?embedded=${embedded}
                @change=${onChange} @rename-node=${onRename}
                @delete-node=${onDelete} @duplicate-node=${onDuplicate}
            ></flows-external-api-editor>`;
        case 'remote_flow':
            return html`<flows-remote-flow-editor
                .nodeId=${nodeId} .flowId=${flowId} .branchId=${branchId}
                .nodeConfig=${node} .nodeType=${node.type}
                .flowVariables=${flowVariables} .graphNodes=${graphNodes}
                .previewExecutionState=${preview}
                ?expanded=${expanded} ?embedded=${embedded}
                @change=${onChange} @rename-node=${onRename}
                @delete-node=${onDelete} @duplicate-node=${onDuplicate}
            ></flows-remote-flow-editor>`;
        default:
            return html`<flows-base-node-editor
                .nodeId=${nodeId} .flowId=${flowId} .branchId=${branchId}
                .nodeConfig=${node} .nodeType=${asString(node.type)}
                .flowVariables=${flowVariables} .graphNodes=${graphNodes}
                .previewExecutionState=${preview}
                ?expanded=${expanded} ?embedded=${embedded}
                @change=${onChange} @rename-node=${onRename}
                @delete-node=${onDelete} @duplicate-node=${onDuplicate}
            ></flows-base-node-editor>`;
    }
}
