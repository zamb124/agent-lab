/**
 * Effective llm_node list and FlowConfig patch helpers for Evaluation Lab.
 * Judge/tester bodies live in flow JSON; cases store only node ids.
 */

function isPlainObject(value: unknown) {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function asString(value: unknown) {
    return typeof value === 'string' ? value : '';
}

/**
 * @param {unknown} flow
 * @param {string} branchId
 * @returns {Record<string, object>}
 */
export function effectiveFlowNodesMap(flow: any, branchId: any) {
    if (!isPlainObject(flow)) {
        throw new Error('effectiveFlowNodesMap: flow object required');
    }
    const baseNodes = isPlainObject(flow.nodes) ? flow.nodes : {};
    const normalizedBranch = typeof branchId === 'string' ? branchId.trim() : '';
    if (normalizedBranch.length === 0 || normalizedBranch === 'default' || normalizedBranch === 'base') {
        return { ...baseNodes };
    }
    const branches = isPlainObject(flow.branches) ? flow.branches : {};
    const branch = isPlainObject(branches[normalizedBranch]) ? branches[normalizedBranch] : null;
    if (!branch) {
        return { ...baseNodes };
    }
    const nodesMode = branch.nodes_mode === 'merge' || branch.nodes_mode === 'replace'
        ? branch.nodes_mode
        : 'replace';
    const branchNodes = isPlainObject(branch.nodes) ? branch.nodes : null;
    if (branchNodes === null) {
        return { ...baseNodes };
    }
    if (nodesMode === 'merge') {
        return { ...baseNodes, ...branchNodes };
    }
    return { ...branchNodes };
}

/**
 * @param {unknown} node
 * @returns {string}
 */
export function evaluationRoleFromNode(node: any) {
    if (!isPlainObject(node)) {
        return '';
    }
    const store = isPlainObject(node.store) ? node.store : null;
    if (!store) {
        return '';
    }
    const role = store.evaluation_role;
    return typeof role === 'string' ? role : '';
}

/**
 * Tester/judge orphan llm_node — не часть execution-графа на канве.
 * @param {unknown} node
 * @returns {boolean}
 */
export function isEvaluationRoleNode(node: any) {
    const role = evaluationRoleFromNode(node);
    return role === 'judge' || role === 'tester';
}

/**
 * Нода без портов/рёбер исполнения: resource или evaluation tester/judge.
 * @param {unknown} node
 * @returns {boolean}
 */
export function isPortlessCanvasNode(node: any) {
    if (!isPlainObject(node)) {
        return false;
    }
    if (asString(node.type) === 'resource') {
        return true;
    }
    return isEvaluationRoleNode(node);
}

/**
 * Подпись типа на карточке канвы: роль evaluation или node.type.
 * @param {unknown} node
 * @returns {string}
 */
export function canvasNodeTypeSubtitle(node: any) {
    if (!isPlainObject(node)) {
        return '';
    }
    const role = evaluationRoleFromNode(node);
    if (role === 'judge' || role === 'tester') {
        return role;
    }
    return asString(node.type);
}

/**
 * @param {unknown} flow
 * @param {string} branchId
 * @returns {{ node_id: string, name: string, evaluation_role: string, prompt: string }[]}
 */
export function listEffectiveLlmNodes(flow: any, branchId: any) {
    const nodes = effectiveFlowNodesMap(flow, branchId);
    const items = [];
    for (const [nodeId, raw] of Object.entries(nodes)) {
        if (!isPlainObject(raw)) {
            continue;
        }
        if (asString((raw as any).type) !== 'llm_node') {
            continue;
        }
        const name = asString((raw as any).name);
        items.push({
            node_id: nodeId,
            name: name.length > 0 ? name : nodeId,
            evaluation_role: evaluationRoleFromNode(raw),
            prompt: asString((raw as any).prompt),
        });
    }
    items.sort((left, right) => left.name.localeCompare(right.name));
    return items;
}

/**
 * @param {object} flow
 * @param {string} branchId
 * @param {string} nodeId
 * @param {object} nodeConfig
 * @returns {object}
 */
/**
 * @param {unknown} flow
 * @returns {object}
 */
function flowUpdateBodyBase(flow: any) {
    if (!isPlainObject(flow)) {
        throw new Error('flowUpdateBodyBase: flow object required');
    }
    const flowId = asString(flow.flow_id);
    const name = asString(flow.name);
    const entry = asString(flow.entry);
    if (flowId.length === 0 || name.length === 0 || entry.length === 0) {
        throw new Error('flowUpdateBodyBase: flow_id, name and entry required');
    }
    return {
        flow_id: flowId,
        name,
        description: typeof flow.description === 'string' ? flow.description : '',
        entry,
        nodes: isPlainObject(flow.nodes) ? { ...flow.nodes } : {},
        edges: Array.isArray(flow.edges) ? [...flow.edges] : [],
        variables: isPlainObject(flow.variables) ? flow.variables : {},
        tags: Array.isArray(flow.tags) ? flow.tags : [],
        branches: isPlainObject(flow.branches) ? { ...flow.branches } : {},
        triggers: isPlainObject(flow.triggers) ? flow.triggers : {},
        resources: isPlainObject(flow.resources) ? flow.resources : {},
        store_card_image_url: typeof flow.store_card_image_url === 'string'
            ? flow.store_card_image_url
            : null,
        speech: isPlainObject(flow.speech) ? flow.speech : null,
        chat: isPlainObject(flow.chat) ? flow.chat : null,
        employee: isPlainObject(flow.employee) ? flow.employee : undefined,
        agent_toolkit_ids: Array.isArray(flow.agent_toolkit_ids) ? flow.agent_toolkit_ids : [],
    };
}

/**
 * @param {object} flow
 * @param {string} branchId
 * @param {string} nodeId
 * @param {object} nodeConfig
 * @returns {object}
 */
export function flowBodyWithNode(flow: any, branchId: any, nodeId: string, nodeConfig: any) {
    if (typeof nodeId !== 'string' || nodeId.length === 0) {
        throw new Error('flowBodyWithNode: nodeId required');
    }
    if (!isPlainObject(nodeConfig)) {
        throw new Error('flowBodyWithNode: nodeConfig object required');
    }
    const body = flowUpdateBodyBase(flow);
    body.nodes[nodeId] = { ...nodeConfig, type: 'llm_node' };
    const normalizedBranch = typeof branchId === 'string' ? branchId.trim() : '';
    if (normalizedBranch.length > 0 && normalizedBranch !== 'default' && normalizedBranch !== 'base') {
        const branches = isPlainObject(body.branches) ? { ...body.branches } : {};
        const existing = isPlainObject(branches[normalizedBranch])
            ? branches[normalizedBranch]
            : { name: normalizedBranch };
        const branchNodes = isPlainObject(existing.nodes) ? { ...existing.nodes } : {};
        branchNodes[nodeId] = { ...nodeConfig, type: 'llm_node' };
        branches[normalizedBranch] = {
            ...existing,
            nodes: branchNodes,
        };
        body.branches = branches;
    }
    return body;
}

/**
 * @param {object} flow
 * @param {string} branchId
 * @param {string} nodeId
 * @returns {object}
 */
export function flowBodyWithoutNode(flow: any, branchId: any, nodeId: string) {
    if (typeof nodeId !== 'string' || nodeId.length === 0) {
        throw new Error('flowBodyWithoutNode: nodeId required');
    }
    const body = flowUpdateBodyBase(flow);
    if (asString(body.entry) === nodeId) {
        throw new Error('flowBodyWithoutNode: cannot remove flow entry node');
    }
    if (!Object.prototype.hasOwnProperty.call(body.nodes, nodeId)) {
        const normalizedBranch = typeof branchId === 'string' ? branchId.trim() : '';
        const branches = isPlainObject(body.branches) ? body.branches : {};
        const branch = normalizedBranch.length > 0 && isPlainObject(branches[normalizedBranch])
            ? branches[normalizedBranch]
            : null;
        const branchNodes = branch && isPlainObject(branch.nodes) ? branch.nodes : null;
        if (branchNodes === null || !Object.prototype.hasOwnProperty.call(branchNodes, nodeId)) {
            throw new Error(`flowBodyWithoutNode: node not found: ${nodeId}`);
        }
    }
    delete body.nodes[nodeId];
    body.edges = body.edges.filter((edge) => {
        if (!isPlainObject(edge)) {
            return false;
        }
        return asString(edge.from) !== nodeId && asString(edge.to) !== nodeId;
    });
    const normalizedBranch = typeof branchId === 'string' ? branchId.trim() : '';
    if (normalizedBranch.length > 0 && normalizedBranch !== 'default' && normalizedBranch !== 'base') {
        const branches = isPlainObject(body.branches) ? { ...body.branches } : {};
        const existing = isPlainObject(branches[normalizedBranch])
            ? branches[normalizedBranch]
            : null;
        if (existing !== null) {
            const branchNodes = isPlainObject(existing.nodes) ? { ...existing.nodes } : {};
            delete branchNodes[nodeId];
            const branchEdges = Array.isArray(existing.edges)
                ? existing.edges.filter((edge: any) => {
                    if (!isPlainObject(edge)) {
                        return false;
                    }
                    return asString(edge.from) !== nodeId && asString(edge.to) !== nodeId;
                })
                : existing.edges;
            branches[normalizedBranch] = {
                ...existing,
                nodes: branchNodes,
                edges: branchEdges,
            };
            body.branches = branches;
        }
    }
    return body;
}

/**
 * @param {string} role
 * @returns {'judge'|'tester'}
 */
export function requireEvaluationRole(role: string) {
    if (role === 'judge' || role === 'tester') {
        return role;
    }
    throw new Error(`requireEvaluationRole: unsupported role ${role}`);
}

/**
 * @returns {string}
 */
export function newEvaluationNodeId(prefix: string) {
    if (typeof prefix !== 'string' || prefix.length === 0) {
        throw new Error('newEvaluationNodeId: prefix required');
    }
    const suffix = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
        ? crypto.randomUUID().replace(/-/g, '').slice(0, 10)
        : `${Date.now()}`;
    return `${prefix}_${suffix}`;
}
