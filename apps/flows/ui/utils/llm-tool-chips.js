/**
 * Шарики инструментов на карточке llm_node на канве Drawflow.
 */

/**
 * @param {string} text
 * @returns {string}
 */
export function escapeHtml(text) {
    const s = String(text);
    return s
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

/**
 * @param {string | Record<string, unknown>} tool
 * @returns {string}
 */
export function getLlmToolDisplayName(tool) {
    if (typeof tool === 'object' && tool !== null && tool.name) {
        return String(tool.name);
    }
    if (typeof tool === 'string') {
        return tool;
    }
    if (typeof tool === 'object' && tool !== null && tool.tool_id) {
        return String(tool.tool_id);
    }
    return '';
}

/**
 * Совпадает с правилом клика по ту в панели: inline (есть code), subflow, MCP.
 *
 * @param {string | Record<string, unknown>} tool
 * @returns {boolean}
 */
export function isLlmToolChipEditable(tool) {
    const toolId = typeof tool === 'string' ? tool : tool?.tool_id;
    if (typeof toolId === 'string' && toolId.startsWith('mcp:')) {
        return true;
    }
    if (typeof tool === 'object' && tool !== null) {
        if (tool.code) {
            return true;
        }
        if (tool.type === 'flow' || tool.type === 'llm_node') {
            return true;
        }
    }
    return false;
}

/**
 * Имя иконки из ICON_MAP (как в LlmNodeEditor._getToolIcon), плюс типы inline-модалки.
 *
 * @param {string | Record<string, unknown>} tool
 * @returns {string}
 */
export function getLlmToolChipIconName(tool) {
    const toolId = typeof tool === 'string' ? tool : tool?.tool_id;
    if (typeof toolId === 'string' && toolId.startsWith('mcp:')) {
        return 'plug';
    }
    if (typeof tool === 'object' && tool !== null) {
        const ty = tool.type;
        if (ty === 'flow') {
            return 'workflow';
        }
        if (ty === 'llm_node') {
            return 'llm_node';
        }
        if (ty === 'external_api') {
            return 'globe';
        }
        if (ty === 'remote_flow') {
            return 'cloud';
        }
        if (ty === 'channel') {
            return 'message-circle';
        }
        if (ty === 'code') {
            return 'code';
        }
        if (tool.code) {
            return 'code';
        }
    }
    return 'tool';
}

/** Совпадает с палитрой `_getNodeColor` на канве + ссылка на инструмент из реестра. */
const CANVAS_NODE_HEX_BY_TYPE = {
    llm_node: '#f59e0b',
    code: '#8b5cf6',
    external_api: '#06b6d4',
    remote_flow: '#3b82f6',
    flow: '#ec4899',
    mcp: '#14b8a6',
    channel: '#99A6F9',
};

const TOOL_REF_HEX = '#64748b';

/**
 * @param {string | Record<string, unknown>} tool
 * @returns {string} #RRGGBB
 */
export function getLlmToolChipAccentHex(tool) {
    const toolId = typeof tool === 'string' ? tool : tool?.tool_id;
    if (typeof toolId === 'string' && toolId.startsWith('mcp:')) {
        return CANVAS_NODE_HEX_BY_TYPE.mcp;
    }
    if (typeof tool === 'string') {
        return TOOL_REF_HEX;
    }
    if (typeof tool === 'object' && tool !== null) {
        const ty = tool.type;
        if (ty === 'flow') {
            return CANVAS_NODE_HEX_BY_TYPE.flow;
        }
        if (ty === 'llm_node') {
            return CANVAS_NODE_HEX_BY_TYPE.llm_node;
        }
        if (ty === 'external_api') {
            return CANVAS_NODE_HEX_BY_TYPE.external_api;
        }
        if (ty === 'remote_flow') {
            return CANVAS_NODE_HEX_BY_TYPE.remote_flow;
        }
        if (ty === 'mcp') {
            return CANVAS_NODE_HEX_BY_TYPE.mcp;
        }
        if (ty === 'channel') {
            return CANVAS_NODE_HEX_BY_TYPE.channel;
        }
        if (ty === 'code') {
            return CANVAS_NODE_HEX_BY_TYPE.code;
        }
        if (tool.code) {
            return CANVAS_NODE_HEX_BY_TYPE.code;
        }
    }
    return TOOL_REF_HEX;
}

/**
 * @param {string} drawflowId
 * @param {Array<string | Record<string, unknown>>} tools
 * @param {(key: string) => string} t
 * @returns {string}
 */
export function buildLlmToolChipsHtml(drawflowId, tools, t) {
    if (!Array.isArray(tools) || tools.length === 0) {
        return '';
    }
    const chips = tools
        .map((tool, index) => {
            const displayName = getLlmToolDisplayName(tool);
            const label = escapeHtml(displayName);
            const iconName = escapeHtml(getLlmToolChipIconName(tool));
            const accent = getLlmToolChipAccentHex(tool);
            if (!/^#[0-9A-Fa-f]{6}$/.test(accent)) {
                throw new Error(`Invalid tool chip accent: ${accent}`);
            }
            const style = `--tool-chip-accent:${accent}`;
            const editable = isLlmToolChipEditable(tool);
            const iconHtml = `<platform-icon name="${iconName}" size="14"></platform-icon>`;
            if (editable) {
                return `<button type="button" class="agent-node-tool-chip agent-node-tool-chip--editable" style="${style}" data-drawflow-id="${escapeHtml(drawflowId)}" data-tool-index="${index}" title="${label}" aria-label="${label}">${iconHtml}</button>`;
            }
            const readonlyFull = `${displayName} — ${t('flow_canvas.tool_chip_readonly_title')}`;
            return `<span class="agent-node-tool-chip agent-node-tool-chip--readonly" style="${style}" title="${escapeHtml(readonlyFull)}" aria-label="${label}">${iconHtml}</span>`;
        })
        .join('');
    return `<div class="agent-node-tools" role="list">${chips}</div>`;
}
