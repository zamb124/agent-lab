/**
 * Нормализация tool ref (строка или объект) и перевод в node-конфиг для тех же
 * редакторов, что и у standalone-ноды на канве.
 */

import { asString, isPlainObject } from './flows-resolvers.js';

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
    if (explicitType === 'mcp') {
        return { ...raw, node_id: rid, type: 'mcp' };
    }
    if (explicitType === 'flow') {
        return { ...raw, node_id: rid, type: 'flow' };
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
    return {
        node_id: toolId,
        type: 'code',
        name: asString(t.title).length > 0 ? t.title : toolId,
        description: typeof t.description === 'string' ? t.description : '',
        code: typeof t.code === 'string' ? t.code : '',
        tool_id: '',
        args_schema: isPlainObject(t.args_schema) ? t.args_schema : {},
    };
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
