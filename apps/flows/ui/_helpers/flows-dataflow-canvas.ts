/**
 * Pure helpers для dataflow-визуализации на канве и в header.
 * Используются flows-flow-canvas и flows-editor-header.
 */

import { getEdgeEndpoints, isPlainObject } from './flows-resolvers.js';

type ChipSide = 'in' | 'out';
type ChipKind = 'content' | 'files' | 'variable' | 'trigger' | 'interface';

interface DataWire {
    from: string;
    to: string;
    label: string;
    sourceLabel: string;
    targetParam: string;
    sourceKind: string;
    [key: string]: unknown;
}

interface ChipRef {
    nodeId: string;
    side: string;
    index: number;
}

function readDataWire(value: unknown): DataWire | null {
    if (!isPlainObject(value)) return null;
    if (typeof value.from !== 'string' || typeof value.to !== 'string') return null;
    const label = typeof value.label === 'string' ? value.label : '';
    const sourceLabel = typeof value.sourceLabel === 'string' && value.sourceLabel.length > 0
        ? value.sourceLabel
        : label;
    const targetParam = typeof value.targetParam === 'string' && value.targetParam.length > 0
        ? value.targetParam
        : label;
    const sourceKind = typeof value.sourceKind === 'string' ? value.sourceKind : 'state';
    return { from: value.from, to: value.to, label, sourceLabel, targetParam, sourceKind };
}

function isChipKind(value: string): value is ChipKind {
    return value === 'content'
        || value === 'files'
        || value === 'variable'
        || value === 'trigger'
        || value === 'interface';
}

function requireStackHeight(heights: readonly number[], index: number): number {
    const rowHeight = heights[index];
    if (rowHeight === undefined) throw new Error('flows-dataflow-canvas: chip height required');
    return rowHeight;
}

export const DATAFLOW_CHIP_W = 132;
export const DATAFLOW_CHIP_H = 24;
export const DATAFLOW_CHIP_H_EXPANDED = 30;
export const DATAFLOW_CHIP_GAP = 4;
export const DATAFLOW_CHIP_INSET = 8;
export const DATAFLOW_CHIP_ZONE_W = 144;
export const DATAFLOW_CHIP_HOST_W = 136;

/** Левый край входного чипа (точка прихода wire с upstream). */
export function dataflowInputChipAnchorX(nodeX: number) {
    return nodeX - DATAFLOW_CHIP_ZONE_W + (DATAFLOW_CHIP_HOST_W - DATAFLOW_CHIP_W);
}

/** Правый край выходного чипа (точка ухода wire к downstream). */
export function dataflowOutputChipAnchorX(nodeX: number, nodeWidth: number) {
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
export function dataWirePathFor(srcX: number, srcY: number, dstX: number, dstY: number) {
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
export function dataflowChipLabel(chip: unknown) {
    if (!isPlainObject(chip)) return 'state';
    if (typeof chip.label === 'string' && chip.label.length > 0) return chip.label;
    if (typeof chip.target === 'string' && chip.target.length > 0) return chip.target;
    return 'state';
}

/**
 * Вид чипа по пути state; поля интерфейса — обычные пути, их вид (``interface``) задаёт
 * backend в ``DataflowCanvasChip.kind`` и в ``source`` дескриптора.
 * @param {string | null | undefined} path
 * @returns {'content' | 'files' | 'variable' | 'trigger'}
 */
export function dataflowPathChipKind(path: string) {
    if (typeof path !== 'string' || path.length === 0) return 'content';
    if (path === 'files') return 'files';
    if (path.startsWith('variables.')) return 'variable';
    if (path.startsWith('triggers.')) return 'trigger';
    return 'content';
}

/**
 * @param {unknown} chip
 * @returns {'content' | 'files' | 'variable' | 'trigger' | 'interface'}
 */
export function dataflowChipKind(chip: unknown): ChipKind {
    if (isPlainObject(chip) && typeof chip.kind === 'string' && isChipKind(chip.kind)) {
        return chip.kind;
    }
    return dataflowPathChipKind(dataflowChipLabel(chip));
}

/**
 * @param {{ label?: string, sourceLabel?: string, sourceKind?: string }} wire
 * @returns {'content' | 'files' | 'variable' | 'trigger' | 'interface'}
 */
export function dataWireChipKind(wire: unknown): ChipKind {
    if (!isPlainObject(wire)) return dataflowPathChipKind('');
    if (wire.sourceKind === 'interface') return 'interface';
    const sourceLabel = typeof wire.sourceLabel === 'string' && wire.sourceLabel.length > 0
        ? wire.sourceLabel
        : (typeof wire.label === 'string' ? wire.label : '');
    return dataflowPathChipKind(sourceLabel);
}

/**
 * @param {unknown} chip
 * @param {'in' | 'out'} side
 * @returns {number}
 */
export function dataflowChipRowHeight(chip: unknown, side: ChipSide) {
    const hasProducer = side === 'in'
        && isPlainObject(chip)
        && typeof chip.producer_node === 'string'
        && chip.producer_node.length > 0;
    return hasProducer ? DATAFLOW_CHIP_H_EXPANDED : DATAFLOW_CHIP_H;
}

/**
 * @param {number[]} heights
 * @returns {number}
 */
export function dataflowStackContentHeight(heights: readonly number[]) {
    if (heights.length === 0) return DATAFLOW_CHIP_H;
    return heights.reduce((sum: number, rowHeight: number) => sum + rowHeight, 0)
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
export function dataflowNodeChipLayout(nodeHeight: number, inputs: unknown, outputs: unknown) {
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
export function dataflowChipOffsetInStack(heights: readonly number[], chipIndex: number) {
    if (heights.length === 0) return 0;
    const idx = Math.max(0, Math.min(chipIndex, heights.length - 1));
    let offset = 0;
    for (let row = 0; row < idx; row += 1) {
        offset += requireStackHeight(heights, row) + DATAFLOW_CHIP_GAP;
    }
    offset += requireStackHeight(heights, idx) / 2;
    return offset;
}

/**
 * @param {number} stackY
 * @param {number[]} heights
 * @param {number} chipIndex
 * @returns {number}
 */
export function dataflowChipCenterY(stackY: number, heights: readonly number[], chipIndex: number) {
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
export function dataflowChipRect(stackY: number, heights: readonly number[], chipIndex: number) {
    const rawHeight = heights[chipIndex];
    const rowHeight = rawHeight === undefined || rawHeight === 0 ? DATAFLOW_CHIP_H : rawHeight;
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
export function dataflowChipAnchor(
    nodeX: number,
    nodeY: number,
    nodeHeight: number,
    nodeWidth: number,
    side: ChipSide,
    chipIndex: number,
    inputs: unknown,
    outputs: unknown,
) {
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
export function findOutputChipIndex(chips: unknown, sourceLabel: unknown) {
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
export function findInputChipIndex(chips: unknown, targetParam: unknown, sourceLabel: unknown, fromProducerId: unknown) {
    if (!Array.isArray(chips) || chips.length === 0) return -1;
    if (typeof fromProducerId === 'string' && fromProducerId.length > 0) {
        const byProducer = chips.findIndex((chip) => isPlainObject(chip)
            && typeof chip.producer_node === 'string'
            && chip.producer_node === fromProducerId
            && (
                (typeof chip.target === 'string' && chip.target === targetParam)
                || dataflowChipLabel(chip) === sourceLabel
            ));
        if (byProducer >= 0) return byProducer;
    }
    let idx = chips.findIndex((chip) => isPlainObject(chip) && typeof chip.target === 'string' && chip.target === targetParam);
    if (idx >= 0) return idx;
    idx = chips.findIndex((chip) => dataflowChipLabel(chip) === sourceLabel);
    if (idx >= 0) return idx;
    return chips.findIndex((chip) => dataflowChipLabel(chip) === targetParam);
}

/**
 * @param {unknown} nodeInfo
 * @returns {unknown[]}
 */
function canvasOutputsFromNodeInfo(nodeInfo: unknown): unknown[] {
    const info = isPlainObject(nodeInfo) ? nodeInfo : null;
    const canvas = info !== null && isPlainObject(info.canvas) ? info.canvas : null;
    if (canvas !== null && Array.isArray(canvas.outputs) && canvas.outputs.length > 0) {
        return canvas.outputs;
    }
    const writes = info !== null && Array.isArray(info.writes) ? info.writes : [];
    const outputs: { label: string; type: string }[] = [];
    for (const write of writes) {
        if (!isPlainObject(write) || typeof write.path !== 'string' || write.path.length === 0) continue;
        outputs.push({
            label: write.path,
            type: typeof write.type === 'string' ? write.type : 'any',
        });
    }
    return outputs;
}

/**
 * @param {unknown} nodeInfo
 * @returns {unknown[]}
 */
function canvasInputsFromNodeInfo(nodeInfo: unknown): unknown[] {
    const info = isPlainObject(nodeInfo) ? nodeInfo : null;
    const canvas = info !== null && isPlainObject(info.canvas) ? info.canvas : null;
    if (canvas !== null && Array.isArray(canvas.inputs) && canvas.inputs.length > 0) {
        return canvas.inputs;
    }
    const rows = info !== null && Array.isArray(info.input_mapping) ? info.input_mapping : [];
    const inputs: { label: unknown; target: unknown; producer_node: unknown }[] = [];
    for (const row of rows) {
        if (!isPlainObject(row) || row.source_kind !== 'state') continue;
        const sourcePath = typeof row.source_path === 'string' && row.source_path.length > 0 ? row.source_path : null;
        const source = typeof row.source === 'string' ? row.source : null;
        inputs.push({
            label: sourcePath !== null ? sourcePath : (source !== null ? source : row.target),
            target: row.target,
            producer_node: Array.isArray(row.producers) && row.producers.length > 0 ? row.producers[0] : null,
        });
    }
    return inputs;
}

/**
 * @param {number} chipIndex
 * @param {number} chipCount
 * @returns {number}
 */
function resolveChipIndex(chipIndex: number, chipCount: number) {
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
function axis(value: unknown): number {
    if (typeof value === 'number') return value;
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
}

export function resolveDataWireEndpoints(
    wire: unknown,
    fromNode: Record<string, unknown>,
    toNode: Record<string, unknown>,
    dataflowNodes: unknown,
    nodeWidth: number,
    nodeHeightOf: (node: Record<string, unknown>) => number,
) {
    const parsedWire = readDataWire(wire);
    if (parsedWire === null) return null;
    const fromX = axis(fromNode.pos_x);
    const fromY = axis(fromNode.pos_y);
    const toX = axis(toNode.pos_x);
    const toY = axis(toNode.pos_y);
    const fromHeight = nodeHeightOf(fromNode);
    const toHeight = nodeHeightOf(toNode);
    const sourceLabel = parsedWire.sourceLabel;
    const targetParam = parsedWire.targetParam;
    const nodes = isPlainObject(dataflowNodes) ? dataflowNodes : null;
    const fromInfo = nodes === null ? null : nodes[parsedWire.from];
    const toInfo = nodes === null ? null : nodes[parsedWire.to];
    const fromCanvas = isPlainObject(fromInfo) && isPlainObject(fromInfo.canvas) ? fromInfo.canvas : null;
    const fromInputs = fromCanvas !== null && Array.isArray(fromCanvas.inputs) ? fromCanvas.inputs : [];
    const fromOutputs = canvasOutputsFromNodeInfo(fromInfo);
    const toInputs = canvasInputsFromNodeInfo(toInfo);
    const toCanvas = isPlainObject(toInfo) && isPlainObject(toInfo.canvas) ? toInfo.canvas : null;
    const toOutputs = toCanvas !== null && Array.isArray(toCanvas.outputs) ? toCanvas.outputs : [];
    const outIdx = resolveChipIndex(findOutputChipIndex(fromOutputs, sourceLabel), fromOutputs.length);
    const inIdx = resolveChipIndex(
        findInputChipIndex(toInputs, targetParam, sourceLabel, parsedWire.from),
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
export function hasControlPath(fromId: string, toId: string, edges: readonly unknown[]) {
    if (fromId === toId) return true;
    const adj = new Map<string, string[]>();
    for (const edge of edges) {
        const { from_node, to_node } = getEdgeEndpoints(edge);
        if (typeof from_node !== 'string' || typeof to_node !== 'string') continue;
        const nextList = adj.get(from_node);
        if (nextList === undefined) adj.set(from_node, [to_node]);
        else nextList.push(to_node);
    }
    const seen = new Set([fromId]);
    const queue = [fromId];
    while (queue.length > 0) {
        const cur = queue.shift();
        if (cur === undefined) break;
        const nextNodes = adj.get(cur);
        for (const nxt of nextNodes === undefined ? [] : nextNodes) {
            if (nxt === toId) return true;
            if (!seen.has(nxt)) {
                seen.add(nxt);
                queue.push(nxt);
            }
        }
    }
    return false;
}

function recordArray(value: unknown, field: string) {
    if (!isPlainObject(value)) return [];
    const items = value[field];
    return Array.isArray(items) ? items : [];
}

/**
 * @param {Record<string, unknown> | null | undefined} dataflowNodes
 * @param {Record<string, unknown> | null | undefined} graphNodes
 * @returns {Array<{ from: string, to: string, label: string, sourceLabel: string, targetParam: string }>}
 */
export function buildDataWires(dataflowNodes: unknown, graphNodes: unknown): DataWire[] {
    if (!isPlainObject(dataflowNodes) || !isPlainObject(graphNodes)) return [];
    const wires: DataWire[] = [];
    const seen = new Set<string>();

    const pushWire = (fromId: string, toId: string, sourceLabel: string, targetParam: string, sourceKind: string) => {
        if (fromId.length === 0 || toId.length === 0 || fromId === toId) return;
        if (graphNodes[fromId] === undefined || graphNodes[toId] === undefined) return;
        const key = `${fromId}\u0000${toId}\u0000${sourceLabel}\u0000${targetParam}`;
        if (seen.has(key)) return;
        seen.add(key);
        wires.push({
            from: fromId,
            to: toId,
            label: sourceLabel,
            sourceLabel,
            targetParam,
            sourceKind,
        });
    };
    const descriptorKind = (desc: unknown) => {
        if (!isPlainObject(desc)) return 'state';
        if (desc.source === 'interface') return 'interface';
        if (Array.isArray(desc.source) && desc.source.includes('interface')) return 'interface';
        return 'state';
    };
    const producerIds = (value: unknown): string[] => {
        if (!Array.isArray(value)) return [];
        const ids: string[] = [];
        for (const item of value) {
            if (typeof item === 'string' && item.length > 0) ids.push(item);
        }
        return ids;
    };

    for (const [toId, info] of Object.entries(dataflowNodes)) {
        if (graphNodes[toId] === undefined) continue;
        const incomingByPath = new Map<string, unknown>();
        for (const desc of recordArray(info, 'incoming_state')) {
            if (!isPlainObject(desc) || typeof desc.path !== 'string' || desc.path.length === 0) continue;
            incomingByPath.set(desc.path, desc);
        }

        for (const row of recordArray(info, 'input_mapping')) {
            if (!isPlainObject(row) || row.source_kind !== 'state') continue;
            const targetParam = typeof row.target === 'string' ? row.target : '';
            const sourceLabel = typeof row.source_path === 'string' && row.source_path.length > 0
                ? row.source_path
                : (typeof row.source === 'string' ? row.source : targetParam);
            const sourceKind = descriptorKind(incomingByPath.get(sourceLabel));
            for (const fromId of producerIds(row.producers)) {
                pushWire(fromId, toId, sourceLabel, targetParam, sourceKind);
            }
        }

        for (const read of recordArray(info, 'reads')) {
            if (!isPlainObject(read) || read.source_kind !== 'state') continue;
            const sourceLabel = typeof read.source_path === 'string' ? read.source_path : '';
            if (sourceLabel.length === 0) continue;
            const targetParam = typeof read.config_path === 'string' && read.config_path.length > 0
                ? read.config_path
                : sourceLabel;
            const desc = incomingByPath.get(sourceLabel);
            const producers = isPlainObject(desc) ? producerIds(desc.producers) : [];
            for (const fromId of producers) {
                pushWire(fromId, toId, sourceLabel, targetParam, descriptorKind(desc));
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
export function buildLineageSet(hoverNodeId: string | null, wires: readonly DataWire[]) {
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
export function dataWireKey(wire: unknown) {
    const parsed = readDataWire(wire);
    if (parsed === null) throw new Error('flows-dataflow-canvas: wire required');
    return `${parsed.from}\u0000${parsed.to}\u0000${parsed.sourceLabel}\u0000${parsed.targetParam}`;
}

/**
 * @param {{ nodeId: string, side: 'in' | 'out', index: number }} ref
 * @returns {string}
 */
export function chipRefKey(ref: ChipRef) {
    return `${ref.nodeId}\u0000${ref.side}\u0000${ref.index}`;
}

/**
 * @param {{ from: string, to: string, label: string, sourceLabel?: string, targetParam?: string }} wire
 * @returns {string}
 */
function wireSourceLabel(wire: DataWire) {
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
function wiresForChipEndpoint(allWires: readonly DataWire[], chipRef: ChipRef, dataflowNodes: unknown) {
    const keys = new Set<string>();
    if (!isPlainObject(dataflowNodes)) return keys;

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
export function resolveChipStatePaths(chipRef: ChipRef, dataflowNodes: unknown, allWires: readonly DataWire[]) {
    const paths = new Set<string>();
    if (!isPlainObject(dataflowNodes)) return paths;

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
export function wiresForChipHover(allWires: readonly DataWire[], chipRef: ChipRef, dataflowNodes: unknown) {
    const keys = new Set<string>();
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
export function chipRefsForWire(wire: DataWire, dataflowNodes: unknown): ChipRef[] {
    if (!isPlainObject(dataflowNodes)) return [];
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
    const refs: ChipRef[] = [];
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
export function buildLineageSetFromWireKeys(wireKeys: ReadonlySet<string> | null, wires: readonly DataWire[]) {
    if (wireKeys === null || wireKeys.size === 0) return null;
    const lineage = new Set<string>();
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
export function chipRefKeysForWireKeys(
    wireKeys: ReadonlySet<string> | null,
    allWires: readonly DataWire[],
    dataflowNodes: unknown,
) {
    const chipKeys = new Set<string>();
    if (wireKeys === null || wireKeys.size === 0) return chipKeys;
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
export function countNodeDataflowProblems(canvas: unknown) {
    const canvasObj = isPlainObject(canvas) ? canvas : null;
    const errors = canvasObj && typeof canvasObj.error_count === 'number' ? canvasObj.error_count : 0;
    const warnings = canvasObj && typeof canvasObj.warning_count === 'number' ? canvasObj.warning_count : 0;
    return { errors, warnings, total: errors + warnings };
}

/**
 * @param {Record<string, unknown> | null | undefined} dataflowNodes
 * @param {Record<string, unknown> | null | undefined} branchNodes
 * @returns {Array<{ nodeId: string, nodeName: string, severity: string, message: string }>}
 */
export function aggregateDataflowIssues(dataflowNodes: unknown, branchNodes: unknown) {
    if (!isPlainObject(dataflowNodes)) return [];
    const branches = isPlainObject(branchNodes) ? branchNodes : null;
    const out: { nodeId: string; nodeName: string; severity: 'error' | 'warning'; message: string }[] = [];
    for (const [nodeId, info] of Object.entries(dataflowNodes)) {
        const issues = recordArray(info, 'issues');
        for (const issue of issues) {
            if (!isPlainObject(issue)) continue;
            const severity = issue.severity;
            if (severity !== 'error' && severity !== 'warning') continue;
            const node = branches === null ? null : branches[nodeId];
            const nodeRecord = isPlainObject(node) ? node : null;
            const nodeName = nodeRecord !== null && typeof nodeRecord.name === 'string' && nodeRecord.name.length > 0
                ? nodeRecord.name
                : nodeId;
            const messageText = issue.message;
            const codeText = issue.code;
            const message = messageText === undefined || messageText === null || messageText === ''
                ? (codeText === undefined || codeText === null || codeText === '' ? '' : String(codeText))
                : String(messageText);
            out.push({ nodeId, nodeName, severity, message });
        }
    }
    out.sort((a, b) => (a.severity === b.severity ? 0 : a.severity === 'error' ? -1 : 1));
    return out;
}
