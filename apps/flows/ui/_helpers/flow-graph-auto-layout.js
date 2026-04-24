/**
 * Слой раскладка нод flow-канваса (слева направо) при отсутствии явных pos_x/pos_y.
 * Вызывается при загрузке flow в редакторе — см. canvasNeedsAutoLayout / applyAutoLayoutToSkillsData.
 */

import { isPlainObject, asNumber, getEdgeEndpoints } from './flows-resolvers.js';
import { FLOW_NODE_W, getNodeCanvasHeight } from './flows-viewbox.js';

export const H_GAP = 100;
export const V_GAP = 48;

/**
 * @param {unknown} skillsData
 * @returns {boolean}
 */
export function canvasNeedsAutoLayout(skillsData) {
    if (!isPlainObject(skillsData)) return false;
    const nodes = skillsData.nodes;
    if (!isPlainObject(nodes)) return false;
    const ids = Object.keys(nodes);
    if (ids.length < 2) return false;
    for (const id of ids) {
        const n = nodes[id];
        if (!isPlainObject(n)) return false;
        if (asNumber(n.pos_x) !== 0 || asNumber(n.pos_y) !== 0) {
            return false;
        }
    }
    return true;
}

/**
 * @param {Set<string>} nodeIds
 * @param {Array<{ from: string, to: string }>} directed
 * @param {string | null} entryId
 * @returns {{ reachable: string[], unreachable: string[] }}
 */
function partitionReachable(nodeIds, directed, entryId) {
    if (!entryId || !nodeIds.has(entryId)) {
        return { reachable: [...nodeIds].sort(), unreachable: [] };
    }
    const next = new Map();
    for (const e of directed) {
        if (!nodeIds.has(e.from) || !nodeIds.has(e.to)) continue;
        if (!next.has(e.from)) next.set(e.from, []);
        next.get(e.from).push(e.to);
    }
    const seen = new Set();
    const stack = [entryId];
    while (stack.length > 0) {
        const u = stack.pop();
        if (seen.has(u)) continue;
        seen.add(u);
        const outs = next.get(u);
        if (!outs) continue;
        for (const v of outs) {
            if (!seen.has(v)) stack.push(v);
        }
    }
    const unreachable = [];
    for (const id of nodeIds) {
        if (!seen.has(id)) unreachable.push(id);
    }
    unreachable.sort();
    return { reachable: [...seen].sort(), unreachable };
}

/**
 * @param {string[]} nodeIdsR
 * @param {Array<{ from: string, to: string }>} directedR — только u->v в R
 * @returns {{ order: string[] } | { cycle: true }}
 */
function topologicalOrderOrCycle(nodeIdsR, directedR) {
    const idSet = new Set(nodeIdsR);
    const preds = new Map();
    const indeg = new Map();
    for (const id of nodeIdsR) {
        indeg.set(id, 0);
        preds.set(id, []);
    }
    for (const e of directedR) {
        if (!idSet.has(e.from) || !idSet.has(e.to)) continue;
        indeg.set(e.to, (indeg.get(e.to) || 0) + 1);
        preds.get(e.to).push(e.from);
    }
    const q = [];
    for (const id of nodeIdsR) {
        if (indeg.get(id) === 0) q.push(id);
    }
    const order = [];
    let qi = 0;
    while (qi < q.length) {
        const u = q[qi];
        qi += 1;
        order.push(u);
        for (const e of directedR) {
            if (e.from !== u) continue;
            if (!idSet.has(e.to)) continue;
            const nextD = (indeg.get(e.to) || 0) - 1;
            indeg.set(e.to, nextD);
            if (nextD === 0) q.push(e.to);
        }
    }
    if (order.length !== nodeIdsR.length) {
        return { cycle: true };
    }
    return { order };
}

/**
 * @param {string[]} topoOrder
 * @param {Map<string, string[]>} preds
 * @returns {Map<string, number>}
 */
function assignLayersFromTopo(topoOrder, preds) {
    const layer = new Map();
    for (const v of topoOrder) {
        const pr = preds.get(v) || [];
        let m = -1;
        for (const u of pr) {
            if (!layer.has(u)) continue;
            const l = layer.get(u) + 1;
            if (l > m) m = l;
        }
        layer.set(v, m < 0 ? 0 : m);
    }
    return layer;
}

/**
 * @param {string} id
 * @param {Record<string, unknown>} nodes
 * @returns {number}
 */
function nodeHeightOrThrow(id, nodes) {
    const n = nodes[id];
    if (!isPlainObject(n)) {
        throw new Error(`flow-graph-auto-layout: node ${id} missing`);
    }
    return getNodeCanvasHeight(n);
}

/**
 * @param {unknown} skillsData
 * @returns {typeof skillsData}
 */
export function applyAutoLayoutToSkillsData(skillsData) {
    if (!canvasNeedsAutoLayout(skillsData)) {
        return skillsData;
    }
    if (!isPlainObject(skillsData)) {
        return skillsData;
    }
    const rawNodes = skillsData.nodes;
    if (!isPlainObject(rawNodes)) {
        return skillsData;
    }
    const nodeIds = new Set(Object.keys(rawNodes));
    const edges = Array.isArray(skillsData.edges) ? skillsData.edges : [];
    const directed = [];
    for (const e of edges) {
        const { from, to } = getEdgeEndpoints(e);
        if (from.length === 0 || to.length === 0) continue;
        if (!nodeIds.has(from) || !nodeIds.has(to)) continue;
        directed.push({ from, to });
    }

    const entryRaw = skillsData.entry;
    const entryId = typeof entryRaw === 'string' && entryRaw.length > 0 && nodeIds.has(entryRaw)
        ? entryRaw
        : null;
    const { reachable, unreachable } = partitionReachable(nodeIds, directed, entryId);

    const R = new Set(reachable);
    const directedR = [];
    for (const e of directed) {
        if (R.has(e.from) && R.has(e.to)) {
            directedR.push(e);
        }
    }
    const predsR = new Map();
    for (const id of reachable) {
        predsR.set(id, []);
    }
    for (const e of directedR) {
        predsR.get(e.to).push(e.from);
    }
    const topo = topologicalOrderOrCycle(reachable, directedR);
    if ('cycle' in topo) {
        return skillsData;
    }
    const layer = assignLayersFromTopo(topo.order, predsR);

    const byLayer = new Map();
    let maxLayer = 0;
    for (const id of reachable) {
        const l = layer.get(id) ?? 0;
        if (l > maxLayer) maxLayer = l;
        if (!byLayer.has(l)) byLayer.set(l, []);
        byLayer.get(l).push(id);
    }
    for (const [, arr] of byLayer) {
        arr.sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
    }

    const colW = FLOW_NODE_W + H_GAP;
    const positions = new Map();
    for (let l = 0; l <= maxLayer; l += 1) {
        const col = byLayer.get(l);
        if (!col || col.length === 0) continue;
        const x = l * colW;
        let y = 0;
        for (const id of col) {
            positions.set(id, { x, y });
            y += nodeHeightOrThrow(id, rawNodes) + V_GAP;
        }
    }
    if (unreachable.length > 0) {
        const x = (maxLayer + 1) * colW;
        let y = 0;
        for (const id of unreachable) {
            positions.set(id, { x, y });
            y += nodeHeightOrThrow(id, rawNodes) + V_GAP;
        }
    }

    const nextNodes = { ...rawNodes };
    for (const id of nodeIds) {
        const p = positions.get(id);
        if (!p) continue;
        const old = nextNodes[id];
        if (!isPlainObject(old)) continue;
        nextNodes[id] = { ...old, pos_x: p.x, pos_y: p.y };
    }
    return {
        ...skillsData,
        nodes: nextNodes,
    };
}
