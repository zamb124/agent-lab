/**
 * Pure helpers для dataflow-визуализации на канве и в header.
 * Используются flows-flow-canvas и flows-editor-header.
 */

import { getEdgeEndpoints } from './flows-resolvers.js';

export const DATAFLOW_CHIP_W = 132;
export const DATAFLOW_CHIP_H = 24;
export const DATAFLOW_CHIP_H_EXPANDED = 30;
export const DATAFLOW_CHIP_GAP = 4;
export const DATAFLOW_CHIP_INSET = 8;
export const DATAFLOW_CHIP_ZONE_W = 144;
export const DATAFLOW_CHIP_HOST_W = 136;

/** Левый край входного чипа (точка прихода wire с upstream). */
export function dataflowInputChipAnchorX(nodeX) {
    return nodeX - DATAFLOW_CHIP_ZONE_W + (DATAFLOW_CHIP_HOST_W - DATAFLOW_CHIP_W);
}

/** Правый край выходного чипа (точка ухода wire к downstream). */
export function dataflowOutputChipAnchorX(nodeX, nodeWidth) {
    return nodeX + nodeWidth + DATAFLOW_CHIP_INSET + DATAFLOW_CHIP_W;
}

/**
 * Bezier для chip-to-chip: касательные выходят из стороны порта, а не «в ноду».
 * @param {number} srcX
 * @param {number} srcY
 * @param {number} dstX
 * @param {number} dstY
 * @returns {string}
 */
export function dataWirePathFor(srcX, srcY, dstX, dstY) {
    const dx = Math.max(48, Math.abs(dstX - srcX) * 0.45);
    const sign = dstX >= srcX ? 1 : -1;
    const c1x = srcX + sign * dx;
    const c2x = dstX - sign * dx;
    return `M ${srcX} ${srcY} C ${c1x} ${srcY} ${c2x} ${dstY} ${dstX} ${dstY}`;
}

/**
 * @param {unknown} chip
 * @returns {string}
 */
export function dataflowChipLabel(chip) {
    if (chip && typeof chip.label === 'string' && chip.label.length > 0) {
        return chip.label;
    }
    if (chip && typeof chip.target === 'string' && chip.target.length > 0) {
        return chip.target;
    }
    return 'state';
}

/**
 * @param {unknown} chip
 * @param {'in' | 'out'} side
 * @returns {number}
 */
export function dataflowChipRowHeight(chip, side) {
    const hasProducer = side === 'in'
        && chip
        && typeof chip.producer_node === 'string'
        && chip.producer_node.length > 0;
    return hasProducer ? DATAFLOW_CHIP_H_EXPANDED : DATAFLOW_CHIP_H;
}

/**
 * @param {number[]} heights
 * @returns {number}
 */
export function dataflowStackContentHeight(heights) {
    if (!heights.length) return DATAFLOW_CHIP_H;
    return heights.reduce((sum, rowHeight) => sum + rowHeight, 0)
        + (heights.length - 1) * DATAFLOW_CHIP_GAP;
}

/**
 * @param {unknown[]} inputs
 * @param {unknown[]} outputs
 * @param {number} nodeHeight
 * @returns {{
 *   stackY: number,
 *   chipHostHeight: number,
 *   inputHeights: number[],
 *   outputHeights: number[],
 * }}
 */
export function dataflowNodeChipLayout(nodeHeight, inputs, outputs) {
    const inputList = Array.isArray(inputs) ? inputs : [];
    const outputList = Array.isArray(outputs) ? outputs : [];
    const inputHeights = inputList.map((chip) => dataflowChipRowHeight(chip, 'in'));
    const outputHeights = outputList.map((chip) => dataflowChipRowHeight(chip, 'out'));
    const contentHeight = Math.max(
        dataflowStackContentHeight(inputHeights),
        dataflowStackContentHeight(outputHeights),
        0,
    );
    const chipHostHeight = contentHeight > 0 ? contentHeight : DATAFLOW_CHIP_H;
    const stackY = Math.max(-12, (nodeHeight - chipHostHeight) / 2);
    return { stackY, chipHostHeight, inputHeights, outputHeights };
}

/**
 * @param {number} stackY
 * @param {number[]} heights
 * @param {number} chipIndex
 * @returns {number}
 */
export function dataflowChipOffsetInStack(heights, chipIndex) {
    if (!heights.length) return 0;
    const idx = Math.max(0, Math.min(chipIndex, heights.length - 1));
    let offset = 0;
    for (let row = 0; row < idx; row += 1) {
        offset += heights[row] + DATAFLOW_CHIP_GAP;
    }
    offset += heights[idx] / 2;
    return offset;
}

/**
 * @param {number} stackY
 * @param {number[]} heights
 * @param {number} chipIndex
 * @returns {number}
 */
export function dataflowChipCenterY(stackY, heights, chipIndex) {
    if (!heights.length) {
        return stackY + DATAFLOW_CHIP_H / 2;
    }
    return stackY + dataflowChipOffsetInStack(heights, chipIndex);
}

/**
 * @param {number} stackY
 * @param {number[]} heights
 * @param {number} chipIndex
 * @returns {{ y: number, height: number }}
 */
export function dataflowChipRect(stackY, heights, chipIndex) {
    const rowHeight = heights[chipIndex] || DATAFLOW_CHIP_H;
    const centerY = dataflowChipCenterY(stackY, heights, chipIndex);
    return { y: centerY - rowHeight / 2, height: rowHeight };
}

/**
 * @param {number} nodeX
 * @param {number} nodeY
 * @param {number} nodeHeight
 * @param {number} nodeWidth
 * @param {'in' | 'out'} side
 * @param {number} chipIndex
 * @param {unknown[]} inputs
 * @param {unknown[]} outputs
 * @returns {{ x: number, y: number }}
 */
export function dataflowChipAnchor(nodeX, nodeY, nodeHeight, nodeWidth, side, chipIndex, inputs, outputs) {
    const layout = dataflowNodeChipLayout(nodeHeight, inputs, outputs);
    const heights = side === 'out' ? layout.outputHeights : layout.inputHeights;
    const rect = dataflowChipRect(layout.stackY, heights, chipIndex);
    const cy = nodeY + rect.y + rect.height / 2;
    if (side === 'out') {
        return { x: dataflowOutputChipAnchorX(nodeX, nodeWidth), y: cy };
    }
    return { x: dataflowInputChipAnchorX(nodeX), y: cy };
}

/**
 * @param {unknown[]} chips
 * @param {string} sourceLabel
 * @returns {number}
 */
export function findOutputChipIndex(chips, sourceLabel) {
    if (!Array.isArray(chips) || chips.length === 0) return -1;
    return chips.findIndex((chip) => dataflowChipLabel(chip) === sourceLabel);
}

/**
 * @param {unknown[]} chips
 * @param {string} targetParam
 * @param {string} sourceLabel
 * @param {string} [fromProducerId]
 * @returns {number}
 */
export function findInputChipIndex(chips, targetParam, sourceLabel, fromProducerId) {
    if (!Array.isArray(chips) || chips.length === 0) return -1;
    if (typeof fromProducerId === 'string' && fromProducerId.length > 0) {
        const byProducer = chips.findIndex((chip) => chip
            && typeof chip.producer_node === 'string'
            && chip.producer_node === fromProducerId
            && (
                (typeof chip.target === 'string' && chip.target === targetParam)
                || dataflowChipLabel(chip) === sourceLabel
            ));
        if (byProducer >= 0) return byProducer;
    }
    let idx = chips.findIndex((chip) => chip && typeof chip.target === 'string' && chip.target === targetParam);
    if (idx >= 0) return idx;
    idx = chips.findIndex((chip) => dataflowChipLabel(chip) === sourceLabel);
    if (idx >= 0) return idx;
    return chips.findIndex((chip) => dataflowChipLabel(chip) === targetParam);
}

/**
 * @param {unknown} nodeInfo
 * @returns {unknown[]}
 */
function canvasOutputsFromNodeInfo(nodeInfo) {
    const canvas = nodeInfo && typeof nodeInfo === 'object' && typeof nodeInfo.canvas === 'object'
        ? nodeInfo.canvas
        : null;
    if (canvas && Array.isArray(canvas.outputs) && canvas.outputs.length > 0) {
        return canvas.outputs;
    }
    const writes = nodeInfo && typeof nodeInfo === 'object' && Array.isArray(nodeInfo.writes)
        ? nodeInfo.writes
        : [];
    return writes
        .filter((write) => write && typeof write.path === 'string' && write.path.length > 0)
        .map((write) => ({
            label: write.path,
            type: typeof write.type === 'string' ? write.type : 'any',
        }));
}

/**
 * @param {unknown} nodeInfo
 * @returns {unknown[]}
 */
function canvasInputsFromNodeInfo(nodeInfo) {
    const canvas = nodeInfo && typeof nodeInfo === 'object' && typeof nodeInfo.canvas === 'object'
        ? nodeInfo.canvas
        : null;
    if (canvas && Array.isArray(canvas.inputs) && canvas.inputs.length > 0) {
        return canvas.inputs;
    }
    const rows = nodeInfo && typeof nodeInfo === 'object' && Array.isArray(nodeInfo.input_mapping)
        ? nodeInfo.input_mapping
        : [];
    return rows
        .filter((row) => row && row.source_kind === 'state')
        .map((row) => ({
            label: typeof row.source_path === 'string' && row.source_path.length > 0
                ? row.source_path
                : (typeof row.source === 'string' ? row.source : row.target),
            target: row.target,
            producer_node: Array.isArray(row.producers) && row.producers.length > 0 ? row.producers[0] : null,
        }));
}

/**
 * @param {number} chipIndex
 * @param {number} chipCount
 * @returns {number}
 */
function resolveChipIndex(chipIndex, chipCount) {
    if (chipCount <= 0) return 0;
    if (chipIndex >= 0) return Math.min(chipIndex, chipCount - 1);
    if (chipCount === 1) return 0;
    return -1;
}

/**
 * @param {{
 *   from: string,
 *   to: string,
 *   label: string,
 *   sourceLabel?: string,
 *   targetParam?: string,
 * }} wire
 * @param {Record<string, unknown>} fromNode
 * @param {Record<string, unknown>} toNode
 * @param {Record<string, unknown> | null | undefined} dataflowNodes
 * @param {number} nodeWidth
 * @param {(node: Record<string, unknown>) => number} nodeHeightOf
 * @returns {{ start: { x: number, y: number }, end: { x: number, y: number } } | null}
 */
export function resolveDataWireEndpoints(wire, fromNode, toNode, dataflowNodes, nodeWidth, nodeHeightOf) {
    const fromX = typeof fromNode.pos_x === 'number' ? fromNode.pos_x : Number(fromNode.pos_x) || 0;
    const fromY = typeof fromNode.pos_y === 'number' ? fromNode.pos_y : Number(fromNode.pos_y) || 0;
    const toX = typeof toNode.pos_x === 'number' ? toNode.pos_x : Number(toNode.pos_x) || 0;
    const toY = typeof toNode.pos_y === 'number' ? toNode.pos_y : Number(toNode.pos_y) || 0;
    const fromHeight = nodeHeightOf(fromNode);
    const toHeight = nodeHeightOf(toNode);
    const sourceLabel = typeof wire.sourceLabel === 'string' && wire.sourceLabel.length > 0
        ? wire.sourceLabel
        : wire.label;
    const targetParam = typeof wire.targetParam === 'string' && wire.targetParam.length > 0
        ? wire.targetParam
        : wire.label;
    const fromInfo = dataflowNodes && typeof dataflowNodes === 'object' ? dataflowNodes[wire.from] : null;
    const toInfo = dataflowNodes && typeof dataflowNodes === 'object' ? dataflowNodes[wire.to] : null;
    const fromInputs = fromInfo && typeof fromInfo.canvas === 'object' && Array.isArray(fromInfo.canvas.inputs)
        ? fromInfo.canvas.inputs
        : [];
    const fromOutputs = canvasOutputsFromNodeInfo(fromInfo);
    const toInputs = canvasInputsFromNodeInfo(toInfo);
    const toOutputs = toInfo && typeof toInfo.canvas === 'object' && Array.isArray(toInfo.canvas.outputs)
        ? toInfo.canvas.outputs
        : [];
    const outIdx = resolveChipIndex(findOutputChipIndex(fromOutputs, sourceLabel), fromOutputs.length);
    const inIdx = resolveChipIndex(
        findInputChipIndex(toInputs, targetParam, sourceLabel, wire.from),
        toInputs.length,
    );
    if (outIdx < 0 || inIdx < 0) {
        return null;
    }
    return {
        start: dataflowChipAnchor(fromX, fromY, fromHeight, nodeWidth, 'out', outIdx, fromInputs, fromOutputs),
        end: dataflowChipAnchor(toX, toY, toHeight, nodeWidth, 'in', inIdx, toInputs, toOutputs),
    };
}

/**
 * @param {string} fromId
 * @param {string} toId
 * @param {unknown[]} edges
 * @returns {boolean}
 */
export function hasControlPath(fromId, toId, edges) {
    if (fromId === toId) return true;
    const adj = new Map();
    for (const edge of edges) {
        const { from_node, to_node } = getEdgeEndpoints(edge);
        if (typeof from_node !== 'string' || typeof to_node !== 'string') continue;
        if (!adj.has(from_node)) adj.set(from_node, []);
        adj.get(from_node).push(to_node);
    }
    const seen = new Set([fromId]);
    const queue = [fromId];
    while (queue.length > 0) {
        const cur = queue.shift();
        for (const nxt of adj.get(cur) || []) {
            if (nxt === toId) return true;
            if (!seen.has(nxt)) {
                seen.add(nxt);
                queue.push(nxt);
            }
        }
    }
    return false;
}

/**
 * @param {Record<string, unknown> | null | undefined} dataflowNodes
 * @param {Record<string, unknown> | null | undefined} graphNodes
 * @returns {Array<{ from: string, to: string, label: string, sourceLabel: string, targetParam: string }>}
 */
export function buildDataWires(dataflowNodes, graphNodes) {
    if (!dataflowNodes || typeof dataflowNodes !== 'object') return [];
    if (!graphNodes || typeof graphNodes !== 'object') return [];
    const wires = [];
    const seen = new Set();

    const pushWire = (fromId, toId, sourceLabel, targetParam) => {
        if (!fromId || !toId || fromId === toId || !graphNodes[fromId] || !graphNodes[toId]) return;
        const label = sourceLabel;
        const key = `${fromId}\u0000${toId}\u0000${label}\u0000${targetParam}`;
        if (seen.has(key)) return;
        seen.add(key);
        wires.push({ from: fromId, to: toId, label, sourceLabel, targetParam });
    };

    for (const [toId, info] of Object.entries(dataflowNodes)) {
        if (!graphNodes[toId]) continue;
        const incomingByPath = new Map();
        const incomingList = info && Array.isArray(info.incoming_state) ? info.incoming_state : [];
        for (const desc of incomingList) {
            if (!desc || typeof desc.path !== 'string' || desc.path.length === 0) continue;
            incomingByPath.set(desc.path, desc);
        }

        const rows = info && Array.isArray(info.input_mapping) ? info.input_mapping : [];
        for (const row of rows) {
            if (!row || row.source_kind !== 'state') continue;
            const producers = Array.isArray(row.producers) ? row.producers : [];
            const targetParam = typeof row.target === 'string' ? row.target : '';
            const sourceLabel = typeof row.source_path === 'string' && row.source_path.length > 0
                ? row.source_path
                : (typeof row.source === 'string' ? row.source : targetParam);
            for (const fromId of producers) {
                pushWire(fromId, toId, sourceLabel, targetParam);
            }
        }

        const reads = info && Array.isArray(info.reads) ? info.reads : [];
        for (const read of reads) {
            if (!read || read.source_kind !== 'state') continue;
            const sourceLabel = typeof read.source_path === 'string' ? read.source_path : '';
            if (!sourceLabel) continue;
            const targetParam = typeof read.config_path === 'string' && read.config_path.length > 0
                ? read.config_path
                : sourceLabel;
            const desc = incomingByPath.get(sourceLabel);
            const producers = desc && Array.isArray(desc.producers) ? desc.producers : [];
            for (const fromId of producers) {
                pushWire(fromId, toId, sourceLabel, targetParam);
            }
        }
    }
    return wires;
}

/**
 * @param {string | null} hoverNodeId
 * @param {Array<{ from: string, to: string }>} wires
 * @returns {Set<string> | null}
 */
export function buildLineageSet(hoverNodeId, wires) {
    if (!hoverNodeId) return null;
    const lineage = new Set([hoverNodeId]);
    for (const wire of wires) {
        if (wire.from === hoverNodeId || wire.to === hoverNodeId) {
            lineage.add(wire.from);
            lineage.add(wire.to);
        }
    }
    return lineage;
}

/**
 * @param {{ from: string, to: string, label: string, sourceLabel?: string, targetParam?: string }} wire
 * @returns {string}
 */
export function dataWireKey(wire) {
    const sourceLabel = typeof wire.sourceLabel === 'string' && wire.sourceLabel.length > 0
        ? wire.sourceLabel
        : wire.label;
    const targetParam = typeof wire.targetParam === 'string' && wire.targetParam.length > 0
        ? wire.targetParam
        : wire.label;
    return `${wire.from}\u0000${wire.to}\u0000${sourceLabel}\u0000${targetParam}`;
}

/**
 * @param {{ nodeId: string, side: 'in' | 'out', index: number }} ref
 * @returns {string}
 */
export function chipRefKey(ref) {
    return `${ref.nodeId}\u0000${ref.side}\u0000${ref.index}`;
}

/**
 * @param {{ from: string, to: string, label: string, sourceLabel?: string, targetParam?: string }} wire
 * @returns {string}
 */
function wireSourceLabel(wire) {
    return typeof wire.sourceLabel === 'string' && wire.sourceLabel.length > 0
        ? wire.sourceLabel
        : wire.label;
}

/**
 * Wires, напрямую подключённые к конкретному chip endpoint (node + side + index).
 *
 * @param {Array<{ from: string, to: string, label: string, sourceLabel?: string, targetParam?: string }>} allWires
 * @param {{ nodeId: string, side: 'in' | 'out', index: number }} chipRef
 * @param {Record<string, unknown> | null | undefined} dataflowNodes
 * @returns {Set<string>}
 */
function wiresForChipEndpoint(allWires, chipRef, dataflowNodes) {
    const keys = new Set();
    if (!chipRef || typeof chipRef.nodeId !== 'string' || chipRef.nodeId.length === 0) return keys;
    if (chipRef.side !== 'in' && chipRef.side !== 'out') return keys;
    if (typeof chipRef.index !== 'number' || chipRef.index < 0) return keys;
    if (!dataflowNodes || typeof dataflowNodes !== 'object') return keys;

    if (chipRef.side === 'out') {
        const fromInfo = dataflowNodes[chipRef.nodeId];
        const outputs = canvasOutputsFromNodeInfo(fromInfo);
        for (const wire of allWires) {
            if (wire.from !== chipRef.nodeId) continue;
            const sourceLabel = wireSourceLabel(wire);
            const outIdx = findOutputChipIndex(outputs, sourceLabel);
            if (outIdx === chipRef.index) {
                keys.add(dataWireKey(wire));
            }
        }
        return keys;
    }

    const toInfo = dataflowNodes[chipRef.nodeId];
    const inputs = canvasInputsFromNodeInfo(toInfo);
    for (const wire of allWires) {
        if (wire.to !== chipRef.nodeId) continue;
        const sourceLabel = wireSourceLabel(wire);
        const targetParam = typeof wire.targetParam === 'string' && wire.targetParam.length > 0
            ? wire.targetParam
            : wire.label;
        const inIdx = findInputChipIndex(inputs, targetParam, sourceLabel, wire.from);
        if (inIdx === chipRef.index) {
            keys.add(dataWireKey(wire));
        }
    }
    return keys;
}

/**
 * State path(и) переменной, которую представляет hovered chip.
 *
 * @param {{ nodeId: string, side: 'in' | 'out', index: number }} chipRef
 * @param {Record<string, unknown> | null | undefined} dataflowNodes
 * @param {Array<{ from: string, to: string, label: string, sourceLabel?: string, targetParam?: string }>} allWires
 * @returns {Set<string>}
 */
export function resolveChipStatePaths(chipRef, dataflowNodes, allWires) {
    const paths = new Set();
    if (!chipRef || typeof chipRef.nodeId !== 'string' || chipRef.nodeId.length === 0) return paths;
    if (chipRef.side !== 'in' && chipRef.side !== 'out') return paths;
    if (typeof chipRef.index !== 'number' || chipRef.index < 0) return paths;
    if (!dataflowNodes || typeof dataflowNodes !== 'object') return paths;

    if (chipRef.side === 'out') {
        const fromInfo = dataflowNodes[chipRef.nodeId];
        const outputs = canvasOutputsFromNodeInfo(fromInfo);
        const chip = outputs[chipRef.index];
        const label = dataflowChipLabel(chip);
        if (label.length > 0) {
            paths.add(label);
        }
        return paths;
    }

    const endpointKeys = wiresForChipEndpoint(allWires, chipRef, dataflowNodes);
    for (const wire of allWires) {
        if (!endpointKeys.has(dataWireKey(wire))) continue;
        paths.add(wireSourceLabel(wire));
    }
    if (paths.size === 0) {
        const toInfo = dataflowNodes[chipRef.nodeId];
        const inputs = canvasInputsFromNodeInfo(toInfo);
        const chip = inputs[chipRef.index];
        const label = dataflowChipLabel(chip);
        if (label.length > 0) {
            paths.add(label);
        }
    }
    return paths;
}

/**
 * @param {Array<{ from: string, to: string, label: string, sourceLabel?: string, targetParam?: string }>} allWires
 * @param {{ nodeId: string, side: 'in' | 'out', index: number }} chipRef
 * @param {Record<string, unknown> | null | undefined} dataflowNodes
 * @returns {Set<string>}
 */
export function wiresForChipHover(allWires, chipRef, dataflowNodes) {
    const keys = new Set();
    const statePaths = resolveChipStatePaths(chipRef, dataflowNodes, allWires);
    if (statePaths.size === 0) return keys;
    for (const wire of allWires) {
        if (statePaths.has(wireSourceLabel(wire))) {
            keys.add(dataWireKey(wire));
        }
    }
    return keys;
}

/**
 * @param {{ from: string, to: string, label: string, sourceLabel?: string, targetParam?: string }} wire
 * @param {Record<string, unknown> | null | undefined} dataflowNodes
 * @returns {Array<{ nodeId: string, side: 'in' | 'out', index: number }>}
 */
export function chipRefsForWire(wire, dataflowNodes) {
    if (!wire || !dataflowNodes || typeof dataflowNodes !== 'object') return [];
    const sourceLabel = typeof wire.sourceLabel === 'string' && wire.sourceLabel.length > 0
        ? wire.sourceLabel
        : wire.label;
    const targetParam = typeof wire.targetParam === 'string' && wire.targetParam.length > 0
        ? wire.targetParam
        : wire.label;
    const fromInfo = dataflowNodes[wire.from];
    const toInfo = dataflowNodes[wire.to];
    const fromOutputs = canvasOutputsFromNodeInfo(fromInfo);
    const toInputs = canvasInputsFromNodeInfo(toInfo);
    const outIdx = findOutputChipIndex(fromOutputs, sourceLabel);
    const inIdx = findInputChipIndex(toInputs, targetParam, sourceLabel, wire.from);
    const refs = [];
    if (outIdx >= 0) {
        refs.push({ nodeId: wire.from, side: 'out', index: outIdx });
    }
    if (inIdx >= 0) {
        refs.push({ nodeId: wire.to, side: 'in', index: inIdx });
    }
    return refs;
}

/**
 * @param {Set<string>} wireKeys
 * @param {Array<{ from: string, to: string, label: string, sourceLabel?: string, targetParam?: string }>} wires
 * @returns {Set<string> | null}
 */
export function buildLineageSetFromWireKeys(wireKeys, wires) {
    if (!wireKeys || wireKeys.size === 0) return null;
    const lineage = new Set();
    for (const wire of wires) {
        if (!wireKeys.has(dataWireKey(wire))) continue;
        lineage.add(wire.from);
        lineage.add(wire.to);
    }
    return lineage.size > 0 ? lineage : null;
}

/**
 * @param {Set<string>} wireKeys
 * @param {Array<{ from: string, to: string, label: string, sourceLabel?: string, targetParam?: string }>} allWires
 * @param {Record<string, unknown> | null | undefined} dataflowNodes
 * @returns {Set<string>}
 */
export function chipRefKeysForWireKeys(wireKeys, allWires, dataflowNodes) {
    const chipKeys = new Set();
    if (!wireKeys || wireKeys.size === 0) return chipKeys;
    for (const wire of allWires) {
        if (!wireKeys.has(dataWireKey(wire))) continue;
        for (const ref of chipRefsForWire(wire, dataflowNodes)) {
            chipKeys.add(chipRefKey(ref));
        }
    }
    return chipKeys;
}
/**
 * @param {unknown} canvas
 * @returns {{ errors: number, warnings: number, total: number }}
 */
export function countNodeDataflowProblems(canvas) {
    const canvasObj = canvas && typeof canvas === 'object' ? canvas : null;
    const errors = canvasObj && typeof canvasObj.error_count === 'number' ? canvasObj.error_count : 0;
    const warnings = canvasObj && typeof canvasObj.warning_count === 'number' ? canvasObj.warning_count : 0;
    return { errors, warnings, total: errors + warnings };
}

/**
 * @param {Record<string, unknown> | null | undefined} dataflowNodes
 * @param {Record<string, unknown> | null | undefined} branchNodes
 * @returns {Array<{ nodeId: string, nodeName: string, severity: string, message: string }>}
 */
export function aggregateDataflowIssues(dataflowNodes, branchNodes) {
    if (!dataflowNodes || typeof dataflowNodes !== 'object') return [];
    const out = [];
    for (const [nodeId, info] of Object.entries(dataflowNodes)) {
        const issues = info && Array.isArray(info.issues) ? info.issues : [];
        for (const issue of issues) {
            if (!issue || (issue.severity !== 'error' && issue.severity !== 'warning')) continue;
            const node = branchNodes && typeof branchNodes === 'object' ? branchNodes[nodeId] : null;
            const nodeName = node && typeof node.name === 'string' && node.name.length > 0 ? node.name : nodeId;
            out.push({
                nodeId,
                nodeName,
                severity: issue.severity,
                message: String(issue.message || issue.code || ''),
            });
        }
    }
    out.sort((a, b) => (a.severity === b.severity ? 0 : a.severity === 'error' ? -1 : 1));
    return out;
}
