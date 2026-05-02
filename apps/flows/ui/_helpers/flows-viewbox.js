/**
 * Единый расчёт viewBox для канваса редактора flow (fit / авто-центр при смене skill).
 */

import { asNumber } from './flows-resolvers.js';
import { normalizedLlmToolsForCanvas, CHIPS_PER_ROW, MAX_CHIPS_SHOWN } from './flows-tool-visual.js';

export const FLOW_NODE_W = 200;
export const FLOW_NODE_H = 72;

/** Высота одного ряда chip'ов (chip 28px + padding top 8px). */
export const CHIP_ROW_H = 36;

/**
 * Вычисляет высоту полосы инструментов в зависимости от количества чипов.
 *
 * @param {unknown[] | number} toolsOrCount — массив tools или их количество
 * @returns {number}
 */
export function getToolsStripH(toolsOrCount) {
    const count = Array.isArray(toolsOrCount) ? toolsOrCount.length : (typeof toolsOrCount === 'number' ? toolsOrCount : 0);
    if (count === 0) return 0;
    const shown = Math.min(count, MAX_CHIPS_SHOWN);
    const rows = Math.ceil(shown / CHIPS_PER_ROW);
    return rows * CHIP_ROW_H;
}

/**
 * @param {unknown} node — нода из skillsData
 * @returns {number}
 */
export function getNodeCanvasHeight(node) {
    const tools = normalizedLlmToolsForCanvas(node);
    return FLOW_NODE_H + getToolsStripH(tools);
}

export const FIT_VIEW_PADDING = 80;

/** Множитель размера кадра по bbox (меньше 1 — сильнее «приближает» контент). */
export const FIT_VIEW_FRAME_FACTOR = 1;

/**
 * Нижняя граница размера viewBox в координатах канваса: при 1–2 нодах bbox маленький,
 * без минимума SVG растягивает ноду на весь экран.
 */
export const FIT_VIEW_MIN_W = 1100;
export const FIT_VIEW_MIN_H = 680;

export const FLOWS_EDITOR_DEFAULT_VIEWBOX = Object.freeze({ x: 0, y: 0, w: 1600, h: 1000 });

/**
 * @param {unknown[]} nodes — массив нод skillsData (pos_x, pos_y)
 * @returns {{ x: number, y: number, w: number, h: number } | null} null если нод нет
 */
export function computeFitViewBox(nodes) {
    if (!Array.isArray(nodes) || nodes.length === 0) {
        return null;
    }
    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;
    for (const n of nodes) {
        const x = asNumber(n.pos_x);
        const y = asNumber(n.pos_y);
        if (x < minX) minX = x;
        if (y < minY) minY = y;
        const nh = getNodeCanvasHeight(n);
        if (x + FLOW_NODE_W > maxX) maxX = x + FLOW_NODE_W;
        if (y + nh > maxY) maxY = y + nh;
    }
    const pad = FIT_VIEW_PADDING;
    const w0 = (maxX - minX) + pad * 2;
    const h0 = (maxY - minY) + pad * 2;
    const cx = minX - pad + w0 / 2;
    const cy = minY - pad + h0 / 2;
    let w = w0 * FIT_VIEW_FRAME_FACTOR;
    let h = h0 * FIT_VIEW_FRAME_FACTOR;
    if (w < FIT_VIEW_MIN_W) w = FIT_VIEW_MIN_W;
    if (h < FIT_VIEW_MIN_H) h = FIT_VIEW_MIN_H;
    return {
        x: cx - w / 2,
        y: cy - h / 2,
        w,
        h,
    };
}
