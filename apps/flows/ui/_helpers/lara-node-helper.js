import { asString, isPlainObject } from './flows-resolvers.js';

export const LARA_FLOWS_BRANCH_ID = 'flows';
export const LARA_CODE_HELPER_BRANCH_ID = 'code_helper';
export const LARA_GENERIC_NODE_HELPER_BRANCH_ID = 'node_helper';

export const LARA_NODE_HELPER_BRANCH_BY_TYPE = Object.freeze({
    code: LARA_CODE_HELPER_BRANCH_ID,
    llm_node: 'llm_node_helper',
    flow: 'flow_node_helper',
    remote_flow: 'remote_flow_node_helper',
    external_api: 'external_api_node_helper',
    mcp: 'mcp_node_helper',
    channel: 'channel_node_helper',
    hitl_node: 'hitl_node_helper',
    resource: 'resource_node_helper',
});

export function laraNodeHelperBranchId(nodeType) {
    const key = typeof nodeType === 'string' ? nodeType.trim() : '';
    return LARA_NODE_HELPER_BRANCH_BY_TYPE[key] || LARA_GENERIC_NODE_HELPER_BRANCH_ID;
}

export function stableLaraContextStringify(value) {
    if (value === null || typeof value !== 'object') return JSON.stringify(value);
    if (Array.isArray(value)) return `[${value.map(stableLaraContextStringify).join(',')}]`;
    const keys = Object.keys(value).sort();
    return `{${keys.map((key) => `${JSON.stringify(key)}:${stableLaraContextStringify(value[key])}`).join(',')}}`;
}

function _pickString(...candidates) {
    for (const candidate of candidates) {
        if (typeof candidate === 'string' && candidate.length > 0) {
            return candidate;
        }
    }
    return null;
}

function _normalizeEditorBranchId(rawBranchId) {
    if (typeof rawBranchId !== 'string' || rawBranchId.length === 0) {
        return 'base';
    }
    return rawBranchId;
}

function _normalizeApiBranchId(rawBranchId) {
    const branchId = _normalizeEditorBranchId(rawBranchId);
    return branchId === 'base' ? 'default' : branchId;
}

function _codeNodeSummary(nodeId, node) {
    return {
        node_id: nodeId,
        name: asString(node.name),
        type: asString(node.type),
        language: asString(node.language),
        code: asString(node.code),
        parameters_schema: isPlainObject(node.parameters_schema) ? node.parameters_schema : null,
        input_mapping: isPlainObject(node.input_mapping) ? node.input_mapping : {},
        output_mapping: isPlainObject(node.output_mapping) ? node.output_mapping : {},
    };
}

function _nodeSummary(nodeId, node) {
    if (!isPlainObject(node)) {
        return { node_id: nodeId };
    }
    return {
        node_id: nodeId,
        name: asString(node.name),
        type: asString(node.type),
        description: asString(node.description),
        incoming_policy: asString(node.incoming_policy),
        input_mapping: isPlainObject(node.input_mapping) ? node.input_mapping : {},
        output_mapping: isPlainObject(node.output_mapping) ? node.output_mapping : {},
        tools: Array.isArray(node.tools) ? node.tools : [],
    };
}

function _collectBranchNodeSummaries(nodes) {
    const out = [];
    if (!isPlainObject(nodes)) {
        return out;
    }
    for (const [nodeId, node] of Object.entries(nodes)) {
        out.push(_nodeSummary(nodeId, node));
    }
    return out;
}

function _collectBranchCodeNodes(nodes) {
    const out = [];
    if (!isPlainObject(nodes)) {
        return out;
    }
    for (const [nodeId, node] of Object.entries(nodes)) {
        if (!isPlainObject(node)) {
            continue;
        }
        if (node.type !== 'code') {
            continue;
        }
        out.push(_codeNodeSummary(nodeId, node));
    }
    return out;
}

function _resourceType(resource) {
    if (!isPlainObject(resource)) {
        return '';
    }
    if (typeof resource.type === 'string' && resource.type.length > 0) {
        return resource.type;
    }
    if (typeof resource.resource_type === 'string' && resource.resource_type.length > 0) {
        return resource.resource_type;
    }
    if (isPlainObject(resource.config) && typeof resource.config.type === 'string') {
        return resource.config.type;
    }
    return '';
}

function _resourceCode(resource) {
    if (!isPlainObject(resource)) {
        return '';
    }
    if (typeof resource.code === 'string') {
        return resource.code;
    }
    if (typeof resource.source === 'string') {
        return resource.source;
    }
    if (isPlainObject(resource.config)) {
        if (typeof resource.config.code === 'string') {
            return resource.config.code;
        }
        if (typeof resource.config.source === 'string') {
            return resource.config.source;
        }
    }
    return '';
}

function _resourceSummary(resourceId, resource) {
    return {
        resource_id: resourceId,
        name: isPlainObject(resource) ? asString(resource.name) : '',
        type: _resourceType(resource),
    };
}

function _collectBranchResources(resources) {
    const out = [];
    if (!isPlainObject(resources)) {
        return out;
    }
    for (const [resourceId, resource] of Object.entries(resources)) {
        out.push(_resourceSummary(resourceId, resource));
    }
    return out;
}

function _collectBranchCodeResources(resources) {
    const out = [];
    if (!isPlainObject(resources)) {
        return out;
    }
    for (const [resourceId, resource] of Object.entries(resources)) {
        if (!isPlainObject(resource)) {
            continue;
        }
        if (_resourceType(resource) !== 'code') {
            continue;
        }
        out.push({
            resource_id: resourceId,
            name: asString(resource.name),
            type: _resourceType(resource),
            code: _resourceCode(resource),
        });
    }
    return out;
}

function _selectedDataflowNode(editorState, nodeId) {
    const dataflow = isPlainObject(editorState.dataflow) ? editorState.dataflow : {};
    const nodes = isPlainObject(dataflow.nodes) ? dataflow.nodes : {};
    return nodeId && isPlainObject(nodes[nodeId]) ? nodes[nodeId] : null;
}

function _branchCodePayload(editorState, branchId, nodeId) {
    const branchData = isPlainObject(editorState.branchData) ? editorState.branchData : {};
    const nodes = isPlainObject(branchData.nodes) ? branchData.nodes : {};
    const resources = isPlainObject(branchData.resources) ? branchData.resources : {};
    const selectedNode = nodeId && isPlainObject(nodes[nodeId]) ? nodes[nodeId] : null;
    return {
        branch_id: _normalizeEditorBranchId(branchId),
        api_branch_id: _normalizeApiBranchId(branchId),
        entry: asString(branchData.entry),
        selected_node_id: asString(nodeId),
        selected_node: selectedNode && selectedNode.type === 'code' ? _codeNodeSummary(nodeId, selectedNode) : null,
        code_nodes: _collectBranchCodeNodes(nodes),
        code_resources: _collectBranchCodeResources(resources),
        edges: Array.isArray(branchData.edges) ? branchData.edges : [],
        variables_keys: isPlainObject(branchData.variables) ? Object.keys(branchData.variables).sort() : [],
    };
}

function _branchNodePayload(editorState, branchId, nodeId) {
    const branchData = isPlainObject(editorState.branchData) ? editorState.branchData : {};
    const nodes = isPlainObject(branchData.nodes) ? branchData.nodes : {};
    const resources = isPlainObject(branchData.resources) ? branchData.resources : {};
    const selectedNode = nodeId && isPlainObject(nodes[nodeId]) ? nodes[nodeId] : null;
    return {
        branch_id: _normalizeEditorBranchId(branchId),
        api_branch_id: _normalizeApiBranchId(branchId),
        entry: asString(branchData.entry),
        selected_node_id: asString(nodeId),
        selected_node: selectedNode,
        nodes: _collectBranchNodeSummaries(nodes),
        resources: _collectBranchResources(resources),
        edges: Array.isArray(branchData.edges) ? branchData.edges : [],
        variables_keys: isPlainObject(branchData.variables) ? Object.keys(branchData.variables).sort() : [],
    };
}

export function buildLaraFlowsContext(editorStateRaw, routerParamsRaw = {}, options = {}) {
    const editorState = isPlainObject(editorStateRaw) ? editorStateRaw : {};
    const params = isPlainObject(routerParamsRaw) ? routerParamsRaw : {};
    const flowId = _pickString(editorState.flowId, params.flowId, options.flow_id);
    const branchId = _normalizeEditorBranchId(_pickString(editorState.currentBranchId, params.branchId, options.branch_id, 'base'));
    const nodeId = _pickString(options.node_id, editorState.selectedNodeId);
    const branchData = isPlainObject(editorState.branchData) ? editorState.branchData : { nodes: {} };
    const nodes = isPlainObject(branchData.nodes) ? branchData.nodes : {};
    const node = nodeId && isPlainObject(nodes[nodeId]) ? nodes[nodeId] : null;
    const nodeType = node && typeof node.type === 'string' ? node.type : null;
    const requestKind = asString(options.request_kind || options.requestKind || 'chat');
    const assistantBranchId = asString(options.assistant_branch_id || options.assistantBranchId || LARA_FLOWS_BRANCH_ID);
    const dataflowNode = _selectedDataflowNode(editorState, nodeId);
    return {
        app_surface: 'flows',
        flow_id: flowId,
        target_branch_id: branchId,
        api_branch_id: _normalizeApiBranchId(branchId),
        assistant_branch_id: assistantBranchId,
        lara_request_kind: requestKind,
        selection_source: asString(options.selection_source || options.selectionSource),
        node_id: nodeId,
        node_type: nodeType,
        node_payload: node,
        flow_payload: isPlainObject(editorState.flowConfig) ? editorState.flowConfig : null,
        branch_node_payload: _branchNodePayload(editorState, branchId, nodeId),
        branch_code_payload: _branchCodePayload(editorState, branchId, nodeId),
        dataflow_node: dataflowNode,
        screen: asString(options.screen) || (nodeId ? 'flow_editor_node' : (flowId ? 'flow_editor' : 'flow_list')),
    };
}

export function flattenLaraFlowsContext(contextRaw) {
    const context = isPlainObject(contextRaw) ? contextRaw : {};
    const targetBranchId =
        typeof context.target_branch_id === 'string' && context.target_branch_id.length > 0
            ? context.target_branch_id
            : 'base';
    const assistantBranchId =
        typeof context.assistant_branch_id === 'string' && context.assistant_branch_id.length > 0
            ? context.assistant_branch_id
            : LARA_FLOWS_BRANCH_ID;
    const branchNodePayload = isPlainObject(context.branch_node_payload) ? context.branch_node_payload : {};
    const branchCodePayload = isPlainObject(context.branch_code_payload) ? context.branch_code_payload : {};
    const dataflowNode = isPlainObject(context.dataflow_node) ? context.dataflow_node : null;
    const nodePayload = isPlainObject(context.node_payload) ? context.node_payload : null;
    const flowPayload = isPlainObject(context.flow_payload) ? context.flow_payload : null;
    const selectedCodeNode = isPlainObject(branchCodePayload.selected_node) ? branchCodePayload.selected_node : {};
    return {
        lara_ui_context: context,
        lara_ui_context_json: JSON.stringify(context),
        app_surface: asString(context.app_surface),
        screen: asString(context.screen),
        selection_source: asString(context.selection_source),
        flow_id: asString(context.flow_id),
        target_branch_id: targetBranchId,
        branch_id: targetBranchId,
        api_branch_id: asString(context.api_branch_id),
        assistant_branch_id: assistantBranchId,
        lara_request_kind: asString(context.lara_request_kind),
        node_id: asString(context.node_id),
        node_type: asString(context.node_type),
        node_payload_json: nodePayload ? JSON.stringify(nodePayload) : '',
        flow_payload_json: flowPayload ? JSON.stringify(flowPayload) : '',
        branch_node_payload: branchNodePayload,
        branch_node_payload_json: JSON.stringify(branchNodePayload),
        branch_code_payload: branchCodePayload,
        branch_code_payload_json: JSON.stringify(branchCodePayload),
        dataflow_node_json: dataflowNode ? JSON.stringify(dataflowNode) : '',
        selected_code_node_code: asString(selectedCodeNode.code),
        selected_code_node_language: asString(selectedCodeNode.language),
    };
}

export function laraNodeHelperConversationKey(contextRaw) {
    const context = isPlainObject(contextRaw) ? contextRaw : {};
    return [
        asString(context.assistant_branch_id) || LARA_GENERIC_NODE_HELPER_BRANCH_ID,
        asString(context.flow_id),
        asString(context.target_branch_id) || 'base',
        asString(context.node_id),
    ].join(':');
}
