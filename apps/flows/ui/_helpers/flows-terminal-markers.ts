/**
 * Геометрия виртуальных START/END маркеров на flows canvas.
 * Не ноды графа — только декоратив + wire от entry/orphan портов.
 */

import { asArray, isPlainObject, getEdgeEndpoints } from './flows-resolvers.js';
import {
    listReflectionExits,
    inferReflectionExitPortFromCondition,
} from './flows-reflection-defaults.js';

/** Wire от порта до края outer badge. */
export const FLOW_TERMINAL_GAP = 96;

export const FLOW_TERMINAL_OUTER_R = 20;
export const FLOW_TERMINAL_INNER_R = 14;

/** Вылет маркера за край ноды (gap + диаметр) — для fit viewBox. */
export const FLOW_TERMINAL_EXTENT = FLOW_TERMINAL_GAP + 2 * FLOW_TERMINAL_OUTER_R;

/**
 * @param {{ x: number, y: number }} portXY — координаты in-порта entry-ноды
 * @returns {{ cx: number, cy: number }}
 */
export function terminalStartCenter(portXY: any) {
    if (!isPlainObject(portXY)) {
        throw new Error('terminalStartCenter: portXY object required');
    }
    if (typeof portXY.x !== 'number' || !Number.isFinite(portXY.x)) {
        throw new Error('terminalStartCenter: portXY.x must be a finite number');
    }
    if (typeof portXY.y !== 'number' || !Number.isFinite(portXY.y)) {
        throw new Error('terminalStartCenter: portXY.y must be a finite number');
    }
    return {
        cx: portXY.x - FLOW_TERMINAL_GAP - FLOW_TERMINAL_OUTER_R,
        cy: portXY.y,
    };
}

/**
 * @param {{ x: number, y: number }} portXY — координаты out-порта
 * @returns {{ cx: number, cy: number }}
 */
export function terminalEndCenter(portXY: any) {
    if (!isPlainObject(portXY)) {
        throw new Error('terminalEndCenter: portXY object required');
    }
    if (typeof portXY.x !== 'number' || !Number.isFinite(portXY.x)) {
        throw new Error('terminalEndCenter: portXY.x must be a finite number');
    }
    if (typeof portXY.y !== 'number' || !Number.isFinite(portXY.y)) {
        throw new Error('terminalEndCenter: portXY.y must be a finite number');
    }
    return {
        cx: portXY.x + FLOW_TERMINAL_GAP + FLOW_TERMINAL_OUTER_R,
        cy: portXY.y,
    };
}

/**
 * Исходящее ребро учитывается только если оба конца валидны и to_node есть в графе
 * (как старый orphan-filter: битое ребро не прячет END и не рисуется на canvas).
 *
 * @param {unknown} edge
 * @param {string} nodeId
 * @param {Record<string, unknown>|null|undefined} nodes
 * @returns {boolean}
 */
function isRenderableOutgoingEdge(edge: any, nodeId: string, nodes: any) {
    const { from_node, to_node } = getEdgeEndpoints(edge);
    if (from_node !== nodeId || !to_node) {
        return false;
    }
    if (!isPlainObject(nodes)) {
        return true;
    }
    return isPlainObject(nodes[to_node]);
}

/**
 * Out-порты ноды, на которых нужно нарисовать виртуальный END.
 * Обычная нода без исходящих рёбер → `[null]` (единый out).
 * Reflection → id каждого exit без покрывающего ребра.
 *
 * @param {string} nodeId
 * @param {unknown} node
 * @param {unknown[]} edges
 * @param {Record<string, unknown>|null|undefined} [nodes] — карта нод ветки; без неё to_node не проверяется
 * @returns {(string|null)[]}
 */
export function listTerminalEndPorts(nodeId: string, node: any, edges: any, nodes: any = null) {
    if (typeof nodeId !== 'string' || nodeId.length === 0) {
        throw new Error('listTerminalEndPorts: nodeId required');
    }
    if (!isPlainObject(node)) {
        throw new Error('listTerminalEndPorts: node object required');
    }
    const outgoing = asArray(edges).filter((edge) => isRenderableOutgoingEdge(edge, nodeId, nodes));

    if (node.type === 'reflection') {
        const policy = isPlainObject(node.critic_policy) ? node.critic_policy : null;
        const exits = listReflectionExits(policy);
        const exitIds = exits.map((item: any) => item.id);
        const covered = new Set();
        for (const edge of outgoing) {
            if (!isPlainObject(edge)) {
                continue;
            }
            const port = typeof edge.from_port === 'string' && edge.from_port.length > 0
                ? edge.from_port
                : null;
            if (port !== null && exitIds.includes(port)) {
                covered.add(port);
                continue;
            }
            if (port === null && exits.length === 1) {
                const onlyExit = exits[0];
                if (onlyExit === undefined) {
                    throw new Error('flows-terminal-markers: reflection exit required');
                }
                covered.add(onlyExit.id);
                continue;
            }
            if (port === null) {
                const inferred = inferReflectionExitPortFromCondition(edge.condition, exitIds);
                if (typeof inferred === 'string' && inferred.length > 0) {
                    covered.add(inferred);
                }
            }
        }
        return exits.filter((item: any) => !covered.has(item.id)).map((item: any) => item.id);
    }

    return outgoing.length === 0 ? [null] : [];
}
