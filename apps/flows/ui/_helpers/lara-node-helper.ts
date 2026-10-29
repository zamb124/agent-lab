import { asString, isPlainObject } from './flows-resolvers.js';

export const LARA_FLOWS_BRANCH_ID = 'flows';
export const LARA_CODE_HELPER_BRANCH_ID = 'code_helper';
export const LARA_GENERIC_NODE_HELPER_BRANCH_ID = 'node_helper';

export const LARA_NODE_HELPER_BRANCH_BY_TYPE = Object.freeze({
    code: LARA_CODE_HELPER_BRANCH_ID,
    llm_node: 'llm_node_helper',
    flow: 'flow_node_helper',
    remote_flow: 'remote_flow_node_helper',
    code_agent: 'code_agent_node_helper',
    external_api: 'external_api_node_helper',
    mcp: 'mcp_node_helper',
    datasource: 'datasource_node_helper',
    channel: 'channel_node_helper',
    hitl_node: 'hitl_node_helper',
    reflection: 'reflection_node_helper',
    resource: 'resource_node_helper',
});

export function laraNodeHelperBranchId(nodeType: any) {
    const key = typeof nodeType === 'string' ? nodeType.trim() : '';
    return (LARA_NODE_HELPER_BRANCH_BY_TYPE as any)[key] || LARA_GENERIC_NODE_HELPER_BRANCH_ID;
}

export function stableLaraContextStringify(value: unknown): string {
    if (value === null || typeof value !== 'object') return JSON.stringify(value);
    if (Array.isArray(value)) return `[${value.map(stableLaraContextStringify).join(',')}]`;
    const keys = Object.keys(value).sort();
    return `{${keys.map((key) => `${JSON.stringify(key)}:${stableLaraContextStringify((value as any)[key])}`).join(',')}}`;
}

function _pickString(...candidates: unknown[]) {
    for (const candidate of candidates) {
        if (typeof candidate === 'string' && candidate.length > 0) {
            return candidate;
        }
    }
    return null;
}

function _optionString(options: Record<string, unknown>, keys: readonly string[], fallback: string): string {
    for (const key of keys) {
        const value = options[key];
        if (typeof value === 'string' && value.length > 0) {
            return value;
        }
    }
    return fallback;
}

function _normalizeEditorBranchId(rawBranchId: any) {
    if (typeof rawBranchId !== 'string' || rawBranchId.length === 0) {
        return 'base';
    }
    return rawBranchId;
}

function _normalizeApiBranchId(rawBranchId: any) {
    const branchId = _normalizeEditorBranchId(rawBranchId);
    return branchId === 'base' ? 'default' : branchId;
}

/**
 * Standing Lara metadata for Flows editor: IDs and scalars only.
 * Full node/flow bodies are fetched via tools (flows_get_node / flows_list_nodes).
 */
export function buildLaraFlowsContext(editorStateRaw: unknown, routerParamsRaw: unknown = {}, optionsRaw: unknown = {}) {
    const editorState = isPlainObject(editorStateRaw) ? editorStateRaw : {};
    const params = isPlainObject(routerParamsRaw) ? routerParamsRaw : {};
    const options = isPlainObject(optionsRaw) ? optionsRaw : {};
    const flowId = _pickString(editorState.flowId, params.flowId, options.flow_id);
    const branchId = _normalizeEditorBranchId(
        _pickString(editorState.currentBranchId, params.branchId, options.branch_id, 'base'),
    );
    const nodeId = _pickString(options.node_id, editorState.selectedNodeId);
    const branchData = isPlainObject(editorState.branchData) ? editorState.branchData : { nodes: {} };
    const nodes = isPlainObject(branchData.nodes) ? branchData.nodes : {};
    const edges = Array.isArray(branchData.edges) ? branchData.edges : [];
    const node = nodeId && isPlainObject(nodes[nodeId]) ? nodes[nodeId] : null;
    const nodeType = node && typeof node.type === 'string' ? node.type : null;
    const requestKind = _optionString(options, ['request_kind', 'requestKind'], 'chat');
    const assistantBranchId = _optionString(options, ['assistant_branch_id', 'assistantBranchId'], LARA_FLOWS_BRANCH_ID);
    const editorDirty = Boolean(editorState.isDirty);
    return {
        app_surface: 'flows',
        service: 'flows',
        route_key: flowId ? 'flow_editor' : 'flows_list',
        flow_id: flowId,
        target_branch_id: branchId,
        api_branch_id: _normalizeApiBranchId(branchId),
        assistant_branch_id: assistantBranchId,
        lara_request_kind: requestKind,
        selection_source: _optionString(options, ['selection_source', 'selectionSource'], ''),
        node_id: nodeId,
        node_type: nodeType,
        branch_node_count: Object.keys(nodes).length,
        branch_edge_count: edges.length,
        editor_dirty: editorDirty,
        screen: _optionString(options, ['screen'], '') || (nodeId ? 'flow_editor_node' : (flowId ? 'flow_editor' : 'flow_list')),
    };
}

export function flattenLaraFlowsContext(contextRaw: any) {
    const context = isPlainObject(contextRaw) ? contextRaw : {};
    const targetBranchId =
        typeof context.target_branch_id === 'string' && context.target_branch_id.length > 0
            ? context.target_branch_id
            : 'base';
    const assistantBranchId =
        typeof context.assistant_branch_id === 'string' && context.assistant_branch_id.length > 0
            ? context.assistant_branch_id
            : LARA_FLOWS_BRANCH_ID;
    return {
        app_surface: asString(context.app_surface) || 'flows',
        service: asString(context.service) || 'flows',
        route_key: asString(context.route_key),
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
        branch_node_count: Number.isFinite(context.branch_node_count)
            ? context.branch_node_count
            : 0,
        branch_edge_count: Number.isFinite(context.branch_edge_count)
            ? context.branch_edge_count
            : 0,
        editor_dirty: Boolean(context.editor_dirty),
    };
}

export function laraNodeHelperConversationKey(contextRaw: any) {
    const context = isPlainObject(contextRaw) ? contextRaw : {};
    return [
        asString(context.assistant_branch_id) || LARA_GENERIC_NODE_HELPER_BRANCH_ID,
        asString(context.flow_id),
        asString(context.target_branch_id) || 'base',
        asString(context.node_id),
    ].join(':');
}
