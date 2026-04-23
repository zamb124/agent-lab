/**
 * Визуальная мета для ToolReference на канвасе и в списках (иконка + category как у типов нод).
 */

import { getNodeTypeMeta } from '../constants/node-icons.js';
import { isPlainObject } from './flows-resolvers.js';

/** Макс. число кружков tools на карточке ноды; остальное — «+N». */
export const CANVAS_NODE_TOOLS_MAX_VISIBLE = 6;

const MCP_CODE_MODE = 'mcp_tool';

/**
 * @param {unknown} raw
 * @returns {{ tool_id: string } & Record<string, unknown> | null}
 */
export function normalizeToolRef(raw) {
    if (typeof raw === 'string' && raw.length > 0) {
        return { tool_id: raw };
    }
    if (!isPlainObject(raw)) return null;
    const tid = raw.tool_id;
    if (typeof tid !== 'string' || tid.length === 0) return null;
    return raw;
}

/**
 * @param {unknown} ref — нормализованный tool ref
 * @returns {{ icon: string, category: string }}
 */
export function getToolRefVisualMeta(ref) {
    if (!isPlainObject(ref)) {
        return getNodeTypeMeta('code');
    }
    const t = ref.type;
    if (typeof t === 'string' && t.length > 0) {
        return getNodeTypeMeta(t);
    }
    const codeMode = ref.code_mode;
    if (codeMode === MCP_CODE_MODE || (typeof ref.mcp_server_id === 'string' && ref.mcp_server_id.length > 0)) {
        return getNodeTypeMeta('mcp');
    }
    if (typeof ref.mcp_tool_name === 'string' && ref.mcp_tool_name.length > 0) {
        return getNodeTypeMeta('mcp');
    }
    const code = ref.code;
    if (typeof code === 'string' && code.trim().length > 0) {
        const hasPrompt = typeof ref.prompt === 'string' && ref.prompt.trim().length > 0;
        const isLlmShape = t === 'llm_node' || hasPrompt || (Array.isArray(ref.tools) && ref.tools.length > 0);
        if (!isLlmShape) {
            return getNodeTypeMeta('code');
        }
    }
    return getNodeTypeMeta('code');
}

/**
 * Нормализованный список tools у llm_node для канваса (без structured output).
 *
 * @param {unknown} node
 * @returns {Array<Record<string, unknown>>}
 */
export function normalizedLlmToolsForCanvas(node) {
    if (!isPlainObject(node)) return [];
    if (node.type !== 'llm_node') return [];
    if (node.structured_output === true) return [];
    const raw = node.tools;
    if (!Array.isArray(raw)) return [];
    const out = [];
    for (const item of raw) {
        const n = normalizeToolRef(item);
        if (n) out.push(n);
    }
    return out;
}
