/**
 * Собирает объект metadata.mock (MockConfig) из строк редактора execution-panel.
 * @param {Array<Record<string, unknown>>} rows
 * @param {Record<string, Record<string, unknown>>} flowNodesMap
 * @returns {Record<string, unknown> | null}
 */
export function buildMockConfigFromEditorRows(rows, flowNodesMap) {
    if (!Array.isArray(rows) || rows.length === 0) {
        return null;
    }

    const flowNodes = flowNodesMap && typeof flowNodesMap === 'object' ? flowNodesMap : {};
    const llm = [];
    const tools = {};
    const nodes = {};
    const usedToolIds = new Set();
    const usedNodeMocks = new Set();

    for (let i = 0; i < rows.length; i++) {
        const row = rows[i];
        const nodeId = typeof row.node_id === 'string' ? row.node_id.trim() : '';
        if (!nodeId) {
            throw new Error(`Мок (строка ${i + 1}): выберите ноду`);
        }

        const nodeEntry = flowNodes[nodeId];
        const nodeType = nodeEntry && typeof nodeEntry.type === 'string' ? nodeEntry.type : '';
        if (!nodeType) {
            throw new Error(`Мок: нода "${nodeId}" не найдена в текущем графе`);
        }

        const toolIdRaw = typeof row.tool_id === 'string' ? row.tool_id.trim() : '';
        const rowType = row.type === 'tool_call' || row.type === 'json' || row.type === 'text' ? row.type : 'text';

        if (nodeType === 'llm_node' && toolIdRaw) {
            if (usedToolIds.has(toolIdRaw)) {
                throw new Error(`Мок: инструмент "${toolIdRaw}" указан дважды`);
            }
            usedToolIds.add(toolIdRaw);

            const toolsList = Array.isArray(nodeEntry.tools) ? nodeEntry.tools : [];
            const known = new Set(
                toolsList.map((t) => (t && typeof t.tool_id === 'string' ? t.tool_id : '')).filter(Boolean)
            );
            if (!known.has(toolIdRaw)) {
                throw new Error(`Мок: инструмент "${toolIdRaw}" не принадлежит ноде "${nodeId}"`);
            }

            tools[toolIdRaw] = _toolMockValue(rowType, row);
            continue;
        }

        if (nodeType === 'llm_node') {
            if (rowType === 'text') {
                const content = typeof row.content === 'string' ? row.content : '';
                llm.push({ type: 'text', content });
            } else if (rowType === 'tool_call') {
                const tool = typeof row.tool === 'string' ? row.tool.trim() : '';
                if (!tool) {
                    throw new Error(`Мок (LLM, нода ${nodeId}): укажите имя инструмента для типа tool_call`);
                }
                let args = {};
                const argsRaw = typeof row.args === 'string' ? row.args.trim() : '{}';
                try {
                    const parsed = JSON.parse(argsRaw || '{}');
                    if (parsed !== null && typeof parsed === 'object' && !Array.isArray(parsed)) {
                        args = parsed;
                    } else {
                        throw new Error('args должен быть JSON-объектом');
                    }
                } catch (e) {
                    const cause = e instanceof Error ? e.message : String(e);
                    throw new Error(`Мок (LLM): неверный JSON аргументов: ${cause}`);
                }
                llm.push({ type: 'tool_call', tool, args });
            } else {
                const responseRaw = typeof row.response === 'string' ? row.response.trim() : '{}';
                let parsed;
                try {
                    parsed = JSON.parse(responseRaw || '{}');
                } catch (e) {
                    const cause = e instanceof Error ? e.message : String(e);
                    throw new Error(`Мок (LLM): неверный JSON ответа: ${cause}`);
                }
                llm.push({ type: 'text', content: JSON.stringify(parsed) });
            }
            continue;
        }

        if (usedNodeMocks.has(nodeId)) {
            throw new Error(`Мок: для ноды "${nodeId}" задано несколько строк (объедините в одну)`);
        }
        usedNodeMocks.add(nodeId);

        if (rowType === 'json') {
            const responseRaw = typeof row.response === 'string' ? row.response.trim() : '{}';
            let parsed;
            try {
                parsed = JSON.parse(responseRaw || '{}');
            } catch (e) {
                const cause = e instanceof Error ? e.message : String(e);
                throw new Error(`Мок (нода ${nodeId}): неверный JSON: ${cause}`);
            }
            if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
                throw new Error(`Мок (нода ${nodeId}): JSON должен быть объектом полей state`);
            }
            nodes[nodeId] = parsed;
        } else if (rowType === 'text') {
            const content = typeof row.content === 'string' ? row.content : '';
            nodes[nodeId] = { result: content };
        } else {
            const tool = typeof row.tool === 'string' ? row.tool.trim() : '';
            let args = {};
            const argsRaw = typeof row.args === 'string' ? row.args.trim() : '{}';
            try {
                const p = JSON.parse(argsRaw || '{}');
                if (p !== null && typeof p === 'object' && !Array.isArray(p)) {
                    args = p;
                }
            } catch (e) {
                const cause = e instanceof Error ? e.message : String(e);
                throw new Error(`Мок (нода ${nodeId}): неверный JSON аргументов: ${cause}`);
            }
            nodes[nodeId] = { result: { tool, args } };
        }
    }

    const hasPayload =
        llm.length > 0 || Object.keys(tools).length > 0 || Object.keys(nodes).length > 0;
    if (!hasPayload) {
        return null;
    }

    return {
        enabled: true,
        llm: llm.length > 0 ? llm : undefined,
        tools: Object.keys(tools).length > 0 ? tools : undefined,
        nodes: Object.keys(nodes).length > 0 ? nodes : undefined,
    };
}

function _toolMockValue(rowType, row) {
    if (rowType === 'text') {
        return typeof row.content === 'string' ? row.content : '';
    }
    if (rowType === 'json') {
        const responseRaw = typeof row.response === 'string' ? row.response.trim() : '{}';
        try {
            return JSON.parse(responseRaw || '{}');
        } catch (e) {
            const cause = e instanceof Error ? e.message : String(e);
            throw new Error(`Мок (инструмент): неверный JSON: ${cause}`);
        }
    }
    const tool = typeof row.tool === 'string' ? row.tool.trim() : '';
    let args = {};
    const argsRaw = typeof row.args === 'string' ? row.args.trim() : '{}';
    try {
        const p = JSON.parse(argsRaw || '{}');
        if (p !== null && typeof p === 'object' && !Array.isArray(p)) {
            args = p;
        }
    } catch (e) {
        const cause = e instanceof Error ? e.message : String(e);
        throw new Error(`Мок (инструмент): неверный JSON аргументов: ${cause}`);
    }
    return { tool, args };
}
