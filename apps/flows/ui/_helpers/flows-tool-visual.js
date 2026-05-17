/**
 * Визуальная мета для ToolReference на канвасе и в списках (иконка + category как у типов нод).
 */

import { getNodeTypeMeta } from '../constants/node-icons.js';
import { isPlainObject } from './flows-resolvers.js';
import { isFlowCodeLanguage, normalizeFlowCodeLanguage } from './flows-code-languages.js';

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
const CODE_NODE_META = getNodeTypeMeta('code');
const DEFAULT_TOOL_META = Object.freeze({ icon: 'tool', category: 'core' });
const LANGUAGE_PATTERNS = Object.freeze([
    ['python', /(^|[_:\-\s])(python|py)(?=$|[_:\-\s])/],
    ['javascript', /(^|[_:\-\s])(javascript|js)(?=$|[_:\-\s])/],
    ['typescript', /(^|[_:\-\s])(typescript|ts)(?=$|[_:\-\s])/],
    ['go', /(^|[_:\-\s])(golang|go)(?=$|[_:\-\s])/],
    ['csharp', /(^|[_:\-\s])(csharp|c_sharp|c-sharp|cs)(?=$|[_:\-\s])/],
]);

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
        return DEFAULT_TOOL_META;
    }
    const t = ref.type;
    if (typeof t === 'string' && t.length > 0) {
        if (t === 'tool') {
            return DEFAULT_TOOL_META;
        }
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
            return CODE_NODE_META;
        }
    }
    return DEFAULT_TOOL_META;
}

export function isCodeToolVisualMeta(meta) {
    return isPlainObject(meta)
        && meta.icon === CODE_NODE_META.icon
        && meta.category === CODE_NODE_META.category;
}

export function inferToolRefLanguage(ref) {
    if (!isPlainObject(ref)) return '';
    if (typeof ref.language === 'string' && isFlowCodeLanguage(ref.language)) {
        return normalizeFlowCodeLanguage(ref.language);
    }
    if (typeof ref.code === 'string' && ref.code.trim().length > 0) {
        return 'python';
    }
    const pieces = [];
    for (const key of ['tool_id', 'name', 'title']) {
        const value = ref[key];
        if (typeof value === 'string' && value.length > 0) {
            pieces.push(value.toLowerCase());
        }
    }
    if (Array.isArray(ref.tags)) {
        for (const tag of ref.tags) {
            if (typeof tag === 'string' && tag.length > 0) {
                pieces.push(tag.toLowerCase());
            }
        }
    }
    const joined = pieces.join(' ');
    for (const [language, pattern] of LANGUAGE_PATTERNS) {
        if (pattern.test(joined)) {
            return language;
        }
    }
    return '';
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
