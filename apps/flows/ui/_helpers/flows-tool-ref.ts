/**
 * Нормализация tool ref (строка или объект) и перевод в node-конфиг для тех же
 * редакторов, что и у standalone-ноды на канве.
 */

import { asString, isPlainObject } from './flows-resolvers.js';
import { isMcpToolRegistryItem, parseMcpToolIdToNodeConfig } from './flows-mcp-tool-registry.js';
import { normalizeFlowCodeLanguage } from './flows-code-languages.js';

function _mcpFieldsFromRef(raw: any, toolId: string) {
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
export function normalizeToolRef(ref: unknown) {
    if (typeof ref === 'string' && ref.length > 0) {
        return { tool_id: ref, raw: { tool_id: ref } };
    }
    if (!isPlainObject(ref)) {
        throw new Error('flows-tool-ref: tool ref must be a string or object');
    }
    const toolId = asString((ref as any).tool_id);
    if (toolId.length === 0) {
        throw new Error('flows-tool-ref: tool_id is required');
    }
    return { tool_id: toolId, raw: { ...(ref as Record<string, any>) } };
}

/**
 * true — в ref нет inline-тела, нужен GET /flows/api/v1/tools/{tool_id}.
 */
export function toolRefNeedsRegistryFetch(raw: unknown) {
    if (typeof raw === 'string' && raw.length > 0) {
        return true;
    }
    if (!isPlainObject(raw)) {
        return true;
    }
    if ((raw as any).prompt) {
        return false;
    }
    if ((raw as any).type === 'llm_node') {
        return false;
    }
    if ((raw as any).mcp_server_id) {
        return false;
    }
    if (asString((raw as any).tool_id).startsWith('mcp:')) {
        return false;
    }
    const t = asString((raw as any).type);
    if (t === 'mcp' || t === 'channel' || t === 'flow' || t === 'external_api' || t === 'remote_flow' || t === 'hitl_node') {
        return false;
    }
    if (t === 'code' && typeof (raw as any).code === 'string' && (raw as any).code.length > 0) {
        return false;
    }
    if (typeof (raw as any).code === 'string' && (raw as any).code.length > 0) {
        return false;
    }
    return true;
}

/**
 * @param {Record<string, unknown>} raw
 * @param {string} toolId
 * @returns {Record<string, unknown>}
 */
export function toolRefToInitialNode(raw: any, toolId: string) {
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
        const base: any = { ...raw, node_id: rid, type: 'flow' };
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
        const nameFromName = asString(raw.name);
        const nameFromTitle = asString(raw.title);
        const displayName =
            nameFromName.length > 0
                ? nameFromName
                : nameFromTitle.length > 0
                    ? nameFromTitle
                    : rid;
        const out: any = {
            node_id: rid,
            type: 'code',
            name: displayName,
            description: typeof raw.description === 'string' ? raw.description : '',
            code: typeof raw.code === 'string' ? raw.code : '',
            language: normalizeFlowCodeLanguage(raw.language),
            parameters_schema: isPlainObject(raw.parameters_schema)
                ? raw.parameters_schema
                : { type: 'object', properties: {}, required: [] },
        };
        if (typeof raw.entrypoint === 'string' && raw.entrypoint.length > 0) {
            out.entrypoint = raw.entrypoint;
        }
        if (isPlainObject(raw.input_mapping)) {
            out.input_mapping = raw.input_mapping;
        }
        if (isPlainObject(raw.output_mapping)) {
            out.output_mapping = raw.output_mapping;
        }
        if (isPlainObject(raw.state_mapping)) {
            out.state_mapping = raw.state_mapping;
        }
        if (Array.isArray(raw.files)) {
            out.files = raw.files;
        }
        if (isPlainObject(raw.resources)) {
            out.resources = raw.resources;
        }
        return out;
    }
    throw new Error('flows-tool-ref: cannot build inline node from ref');
}

/**
 * Ответ GET /tools/{id} (элемент) -> node для code-редактора.
 * @param {Record<string, unknown>} t
 * @returns {Record<string, unknown>}
 */
export function registryToolItemToNode(t: any) {
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
    if (t.builtin === true) {
        const effects = Array.isArray(t.effects)
            ? t.effects.filter((effect: any) => typeof effect === 'string')
            : [];
        const confirmationFloor =
            typeof t.confirmation_floor === 'string' && t.confirmation_floor.length > 0
                ? t.confirmation_floor
                : 'none';
        return {
            node_id: toolId,
            type: 'builtin',
            builtin: true,
            tool_id: toolId,
            name: displayTitle,
            description: typeof t.description === 'string' ? t.description : '',
            parameters_schema: isPlainObject(t.parameters_schema)
                ? t.parameters_schema
                : { type: 'object', properties: {}, required: [] },
            output_schema: isPlainObject(t.output_schema) ? t.output_schema : null,
            effects,
            confirmation_floor: confirmationFloor,
        };
    }
    const out: any = {
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

/**
 * Заменяет tool в llm_node.tools по tool_id (строка или object-ref).
 * @param {unknown} tools
 * @param {Record<string, unknown>} updated
 * @returns {unknown[]}
 */
export function replaceToolRefInToolsList(tools: any, updated: any) {
    if (!isPlainObject(updated)) {
        throw new Error('flows-tool-ref: updated tool ref must be an object');
    }
    const updatedId = asString(updated.tool_id);
    if (updatedId.length === 0) {
        throw new Error('flows-tool-ref: updated.tool_id required');
    }
    const current = Array.isArray(tools) ? tools : [];
    let replaced = false;
    const next = current.map((entry) => {
        const id = typeof entry === 'string' ? entry : (isPlainObject(entry) ? asString(entry.tool_id) : '');
        if (id === updatedId) {
            replaced = true;
            return updated;
        }
        return entry;
    });
    if (!replaced) {
        next.push(updated);
    }
    return next;
}

const STRIP_NODE_KEYS = new Set(['position', 'layout']);

/** Поля ToolReference (+ mapping) для code/inline tool; type=code — GraphNodeConfig, не ToolReference. */
const CODE_TOOL_REF_KEYS = new Set([
    'name',
    'title',
    'description',
    'parameters_schema',
    'params',
    'resources',
    'language',
    'entrypoint',
    'code',
    'permission',
    'tags',
    'react_role',
    'public_fields',
    'code_mode',
    'mcp_server_id',
    'mcp_tool_name',
    'mcp_schema_hash',
    'mcp_schema_version',
    'mcp_output_schema',
    'mcp_annotations',
    'mcp_execution',
    'input_mapping',
    'output_mapping',
    'state_mapping',
]);

/**
 * @param {Record<string, unknown>} node
 * @returns {Record<string, unknown>}
 */
export function nodeConfigToToolRef(node: any) {
    if (!isPlainObject(node)) {
        throw new Error('flows-tool-ref: node must be an object');
    }
    const nid = asString(node.node_id);
    if (nid.length === 0) {
        throw new Error('flows-tool-ref: node_id is required to save tool ref');
    }
    if (asString(node.type) === 'mcp') {
        const { serverId, toolName } = _mcpFieldsFromRef(node, nid);
        const out: any = {};
        for (const [k, v] of Object.entries(node)) {
            if (
                k === 'node_id'
                || k === 'tool_id'
                || k === 'server_id'
                || k === 'tool_name'
                || k === 'headers'
                || k === 'type'
            ) {
                continue;
            }
            if (STRIP_NODE_KEYS.has(k)) continue;
            out[k] = v;
        }
        out.tool_id = nid;
        out.code_mode = 'mcp_tool';
        out.mcp_server_id = serverId;
        out.mcp_tool_name = toolName;
        return out;
    }
    const nodeType = asString(node.type);
    if (nodeType === 'builtin' || node.builtin === true) {
        return { tool_id: nid };
    }
    if (nodeType === 'code' || (typeof node.code === 'string' && node.code.length > 0 && nodeType.length === 0)) {
        const out: any = { tool_id: nid };
        for (const key of CODE_TOOL_REF_KEYS) {
            if (!(key in node)) continue;
            out[key] = node[key];
        }
        return out;
    }
    const out: any = {};
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
