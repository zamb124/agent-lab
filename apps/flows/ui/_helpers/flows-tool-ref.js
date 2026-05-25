/**
 * Нормализация tool ref (строка или объект) и перевод в node-конфиг для тех же
 * редакторов, что и у standalone-ноды на канве.
 */

import { asString, isPlainObject } from './flows-resolvers.js';
import { isMcpToolRegistryItem, parseMcpToolIdToNodeConfig } from './flows-mcp-tool-registry.js';
import { normalizeFlowCodeLanguage } from './flows-code-languages.js';

function _mcpFieldsFromRef(raw, toolId) {
    let serverId = asString(raw.server_id);
    if (serverId.length === 0) {
        serverId = asString(raw.mcp_server_id);
    }
    let toolName = asString(raw.tool_name);
    if (toolName.length === 0) {
        toolName = asString(raw.mcp_tool_name);
    }
    if ((serverId.length === 0 || toolName.length === 0) && toolId.startsWith('mcp:')) {
        const parsed = parseMcpToolIdToNodeConfig(toolId);
        if (serverId.length === 0) {
            serverId = parsed.server_id;
        }
        if (toolName.length === 0) {
            toolName = parsed.tool_name;
        }
    }
    return { serverId, toolName };
}

/**
 * @param {unknown} ref
 * @returns {{ tool_id: string, raw: Record<string, unknown> }}
 */
export function normalizeToolRef(ref) {
    if (typeof ref === 'string' && ref.length > 0) {
        return { tool_id: ref, raw: { tool_id: ref } };
    }
    if (!isPlainObject(ref)) {
        throw new Error('flows-tool-ref: tool ref must be a string or object');
    }
    const toolId = asString(ref.tool_id);
    if (toolId.length === 0) {
        throw new Error('flows-tool-ref: tool_id is required');
    }
    return { tool_id: toolId, raw: { ...ref } };
}

/**
 * true — в ref нет inline-тела, нужен GET /flows/api/v1/tools/{tool_id}.
 */
export function toolRefNeedsRegistryFetch(raw) {
    if (typeof raw === 'string' && raw.length > 0) {
        return true;
    }
    if (!isPlainObject(raw)) {
        return true;
    }
    if (raw.prompt) {
        return false;
    }
    if (raw.type === 'llm_node') {
        return false;
    }
    if (raw.mcp_server_id) {
        return false;
    }
    if (asString(raw.tool_id).startsWith('mcp:')) {
        return false;
    }
    const t = asString(raw.type);
    if (t === 'mcp' || t === 'channel' || t === 'flow' || t === 'external_api' || t === 'remote_flow' || t === 'hitl_node') {
        return false;
    }
    if (t === 'code' && typeof raw.code === 'string' && raw.code.length > 0) {
        return false;
    }
    if (typeof raw.code === 'string' && raw.code.length > 0) {
        return false;
    }
    return true;
}

/**
 * @param {Record<string, unknown>} raw
 * @param {string} toolId
 * @returns {Record<string, unknown>}
 */
export function toolRefToInitialNode(raw, toolId) {
    if (toolRefNeedsRegistryFetch(raw)) {
        throw new Error('flows-tool-ref: use registry path for this ref');
    }
    if (!isPlainObject(raw)) {
        throw new Error('flows-tool-ref: raw must be an object');
    }
    const rid = asString(raw.tool_id).length > 0 ? asString(raw.tool_id) : toolId;

    if (raw.prompt || raw.type === 'llm_node') {
        return { ...raw, node_id: rid, type: 'llm_node' };
    }

    const explicitType = asString(raw.type);
    if (
        explicitType === 'mcp'
        || rid.startsWith('mcp:')
        || raw.code_mode === 'mcp_tool'
        || asString(raw.mcp_server_id).length > 0
        || asString(raw.mcp_tool_name).length > 0
    ) {
        const { serverId, toolName } = _mcpFieldsFromRef(raw, rid);
        return {
            ...raw,
            node_id: rid,
            type: 'mcp',
            server_id: serverId,
            tool_name: toolName,
        };
    }
    if (explicitType === 'flow') {
        const base = { ...raw, node_id: rid, type: 'flow' };
        const fid = asString(base.flow_id);
        const outFlowId = fid.length > 0 ? fid : toolId;
        const sid = asString(base.branch_id);
        const outSkill = sid.length > 0 ? sid : 'default';
        return { ...base, flow_id: outFlowId, branch_id: outSkill };
    }
    if (explicitType === 'channel') {
        return { ...raw, node_id: rid, type: 'channel' };
    }
    if (explicitType === 'external_api') {
        return { ...raw, node_id: rid, type: 'external_api' };
    }
    if (explicitType === 'remote_flow') {
        return { ...raw, node_id: rid, type: 'remote_flow' };
    }
    if (explicitType === 'hitl_node') {
        return { ...raw, node_id: rid, type: 'hitl_node' };
    }
    if (explicitType === 'code' || (typeof raw.code === 'string' && raw.code.length > 0)) {
        return { ...raw, node_id: rid, type: 'code' };
    }
    throw new Error('flows-tool-ref: cannot build inline node from ref');
}

/**
 * Ответ GET /tools/{id} (элемент) -> node для code-редактора.
 * @param {Record<string, unknown>} t
 * @returns {Record<string, unknown>}
 */
export function registryToolItemToNode(t) {
    if (!isPlainObject(t)) {
        throw new Error('flows-tool-ref: tool item must be an object');
    }
    const toolId = asString(t.tool_id);
    if (toolId.length === 0) {
        throw new Error('flows-tool-ref: tool item missing tool_id');
    }
    const displayTitle = asString(t.title).length > 0 ? t.title : toolId;
    const itemType = asString(t.item_type);
    if (itemType === 'flow') {
        return {
            node_id: toolId,
            type: 'flow',
            name: displayTitle,
            description: typeof t.description === 'string' ? t.description : '',
            flow_id: toolId,
            branch_id: 'default',
        };
    }
    if (isMcpToolRegistryItem(t)) {
        let serverId = typeof t.mcp_server_id === 'string' && t.mcp_server_id.length > 0 ? t.mcp_server_id : '';
        let toolName =
            typeof t.mcp_tool_name === 'string' && t.mcp_tool_name.length > 0 ? t.mcp_tool_name : '';
        if (toolId.startsWith('mcp:')) {
            const parsed = parseMcpToolIdToNodeConfig(toolId);
            if (serverId.length === 0) {
                serverId = parsed.server_id;
            }
            if (toolName.length === 0) {
                toolName = parsed.tool_name;
            }
        }
        if (serverId.length === 0 || toolName.length === 0) {
            throw new Error('flows-tool-ref: MCP tool item missing server_id or tool_name');
        }
        return {
            node_id: toolId,
            type: 'mcp',
            name: displayTitle,
            description: typeof t.description === 'string' ? t.description : '',
            server_id: serverId,
            tool_name: toolName,
            headers: {},
            input_mapping: {},
            state_mapping: {},
        };
    }
    const out = {
        node_id: toolId,
        type: 'code',
        name: displayTitle,
        description: typeof t.description === 'string' ? t.description : '',
        code: typeof t.code === 'string' ? t.code : '',
        tool_id: '',
        language: normalizeFlowCodeLanguage(t.language),
        parameters_schema: isPlainObject(t.parameters_schema)
            ? t.parameters_schema
            : { type: 'object', properties: {}, required: [] },
    };
    if (typeof t.entrypoint === 'string' && t.entrypoint.length > 0) {
        out.entrypoint = t.entrypoint;
    }
    return out;
}

const STRIP_NODE_KEYS = new Set(['position', 'layout']);

/**
 * @param {Record<string, unknown>} node
 * @returns {Record<string, unknown>}
 */
export function nodeConfigToToolRef(node) {
    if (!isPlainObject(node)) {
        throw new Error('flows-tool-ref: node must be an object');
    }
    const nid = asString(node.node_id);
    if (nid.length === 0) {
        throw new Error('flows-tool-ref: node_id is required to save tool ref');
    }
    if (asString(node.type) === 'mcp') {
        const { serverId, toolName } = _mcpFieldsFromRef(node, nid);
        const out = {};
        for (const [k, v] of Object.entries(node)) {
            if (
                k === 'node_id'
                || k === 'tool_id'
                || k === 'server_id'
                || k === 'tool_name'
                || k === 'headers'
                || k === 'state_mapping'
                || k === 'input_mapping'
            ) {
                continue;
            }
            if (STRIP_NODE_KEYS.has(k)) continue;
            out[k] = v;
        }
        out.tool_id = nid;
        out.type = 'mcp';
        out.code_mode = 'mcp_tool';
        out.mcp_server_id = serverId;
        out.mcp_tool_name = toolName;
        return out;
    }
    const out = {};
    for (const [k, v] of Object.entries(node)) {
        if (k === 'node_id' || k === 'tool_id') {
            continue;
        }
        if (STRIP_NODE_KEYS.has(k)) continue;
        out[k] = v;
    }
    out.tool_id = nid;
    return out;
}
