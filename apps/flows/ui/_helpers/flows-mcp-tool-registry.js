/**
 * Классификация записей реестра /tools/all и разбор mcp:server:tool_name для MCP-ноды.
 */

import { isPlainObject } from './flows-resolvers.js';

/**
 * @param {unknown} item — элемент ответа flows/tools_all (объект с tool_id, item_type, …)
 * @returns {boolean}
 */
export function isMcpToolRegistryItem(item) {
    if (!isPlainObject(item) || item.item_type !== 'tool') {
        return false;
    }
    if (typeof item.mcp_server_id === 'string' && item.mcp_server_id.length > 0) {
        return true;
    }
    if (item.code_mode === 'mcp_tool') {
        return true;
    }
    const tid = typeof item.tool_id === 'string' ? item.tool_id : '';
    if (tid.startsWith('mcp:')) {
        return true;
    }
    return false;
}

/**
 * @param {string} toolId — `mcp:{server_id}:{tool_name}` (tool_name может содержать `:`)
 * @returns {{ server_id: string, tool_name: string }}
 */
export function parseMcpToolIdToNodeConfig(toolId) {
    if (typeof toolId !== 'string' || toolId.length === 0) {
        throw new Error('parseMcpToolIdToNodeConfig: tool_id required');
    }
    if (!toolId.startsWith('mcp:')) {
        throw new Error('parseMcpToolIdToNodeConfig: not an mcp tool_id');
    }
    const m = toolId.match(/^mcp:([^:]+):(.+)$/);
    if (!m) {
        throw new Error('parseMcpToolIdToNodeConfig: invalid mcp tool_id format');
    }
    return { server_id: m[1], tool_name: m[2] };
}

/**
 * @param {string} serverId
 * @param {string} shortToolName — имя tool на стороне MCP (не полный mcp:… id)
 * @returns {string}
 */
export function fullMcpToolId(serverId, shortToolName) {
    if (typeof serverId !== 'string' || serverId.length === 0) {
        throw new Error('fullMcpToolId: serverId required');
    }
    if (typeof shortToolName !== 'string' || shortToolName.length === 0) {
        throw new Error('fullMcpToolId: shortToolName required');
    }
    return `mcp:${serverId}:${shortToolName}`;
}

/**
 * Строка из `cached_tools` (полный `mcp:…`) -> короткое имя, если `server_id` в id совпадает с `expectedServerId`.
 * @param {string} entry
 * @param {string} expectedServerId
 * @returns {string | null}
 */
export function shortMcpNameFromCacheEntry(entry, expectedServerId) {
    if (typeof entry !== 'string' || !entry.startsWith('mcp:')) {
        throw new Error('shortMcpNameFromCacheEntry: expected mcp:… string');
    }
    const p = parseMcpToolIdToNodeConfig(entry);
    if (p.server_id !== expectedServerId) {
        return null;
    }
    return p.tool_name;
}

/**
 * Драфт `input_mapping` по записи GET /tools/{id}: ключ = параметр MCP, значение = `@var:{name}`.
 * @param {Record<string, unknown>} tool
 * @returns {Record<string, string>}
 */
export function mcpInputMappingDraftFromToolRecord(tool) {
    if (!isPlainObject(tool)) {
        throw new Error('mcpInputMappingDraftFromToolRecord: tool must be a plain object');
    }
    const out = {};
    if (isPlainObject(tool.args_schema) && Object.keys(tool.args_schema).length > 0) {
        for (const k of Object.keys(tool.args_schema)) {
            if (typeof k === 'string' && k.length > 0) {
                out[k] = `@var:${k}`;
            }
        }
        return out;
    }
    const ps = tool.parameters_schema;
    if (isPlainObject(ps) && isPlainObject(ps.properties) && Object.keys(ps.properties).length > 0) {
        for (const k of Object.keys(ps.properties)) {
            if (typeof k === 'string' && k.length > 0) {
                out[k] = `@var:${k}`;
            }
        }
    }
    return out;
}
