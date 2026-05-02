/**
 * Визуальная мета для ToolReference на канвасе и в списках (иконка + category как у типов нод).
 */

import { getNodeTypeMeta } from '../constants/node-icons.js';
import { isPlainObject } from './flows-resolvers.js';

/**
 * Число чипов в одном ряду карточки ноды (ширина карточки 200px,
 * chip 28px + gap 6px даёт ~5 штук в ряд).
 */
export const CHIPS_PER_ROW = 5;

/** Макс. число рядов чипов (чтобы карточка не росла бесконечно). */
export const MAX_CHIP_ROWS = 3;

/** Макс. чипов на карточке; остальное — «+N». */
export const MAX_CHIPS_SHOWN = CHIPS_PER_ROW * MAX_CHIP_ROWS;

const MCP_CODE_MODE = 'mcp_tool';

/**
 * Читаемое имя тула из ToolReference (name > title > tool_id).
 *
 * @param {unknown} ref — сырой tool ref
 * @returns {string}
 */
export function getToolLabel(ref) {
    if (typeof ref === 'string' && ref.length > 0) {
        return ref;
    }
    if (!isPlainObject(ref)) {
        return '';
    }
    if (typeof ref.name === 'string' && ref.name.length > 0) return ref.name;
    if (typeof ref.title === 'string' && ref.title.length > 0) return ref.title;
    const tid = ref.tool_id;
    if (typeof tid === 'string' && tid.length > 0) return tid;
    return '';
}

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
    const toolIdForVisual = ref.tool_id;
    if (typeof toolIdForVisual === 'string' && toolIdForVisual.startsWith('mcp:')) {
        return getNodeTypeMeta('mcp');
    }
    if (typeof ref.prompt === 'string' && ref.prompt.trim().length > 0) {
        const c = ref.code;
        if (!(typeof c === 'string' && c.trim().length > 0)) {
            return getNodeTypeMeta('llm_node');
        }
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
