/**
 * Where a dropped element lands and how the grid rearranges around it.
 *
 * Insertion is not a move: a new element has no cell yet, so a taken row must not
 * refuse the drop. The row opens up instead — siblings from that row down shift by
 * the height of the new element — which is what the author is shown while dragging.
 */
import { areaCells, cellsOverlap } from './grid-occupancy.js';

/**
 * @typedef {{ componentId: string, columnStart: number, columnEnd: number, rowStart: number, rowEnd: number }} OccupiedArea
 * @typedef {{ componentId: string, rowStart: number }} RowShift
 */

/**
 * Row the pointer aims at, and the siblings that make room for it.
 *
 * Free row → nothing moves. Taken row → the element takes it and everything from
 * that row down slides by `rowSpan`, so nothing ends up overlapping.
 *
 * @param {{
 *   geometry: object,
 *   point: { x: number, y: number },
 *   columnSpan: number | 'full',
 *   rowSpan?: number,
 *   occupied: ReadonlyArray<OccupiedArea>,
 * }} args
 * @returns {{ area: object, shifted: ReadonlyArray<RowShift> }}
 */
export function proposeGridInsert({ geometry, point, columnSpan, rowSpan = 1, occupied }) {
    if (!geometry || typeof geometry.cellAt !== 'function') {
        throw new Error('flow-ui grid-insert: grid geometry required');
    }
    if (!Number.isInteger(rowSpan) || rowSpan < 1) {
        throw new Error(`flow-ui grid-insert: rowSpan invalid ${JSON.stringify(rowSpan)}`);
    }
    const columns = geometry.columns;
    const span = columnSpan === 'full' || columnSpan == null
        ? columns
        : Math.min(Math.max(columnSpan, 1), columns);
    const cell = geometry.cellAt(point);
    const area = Object.freeze({
        columnStart: Math.min(cell.column, columns - span + 1),
        columnSpan: span,
        rowStart: cell.row,
        rowSpan,
    });
    const cells = areaCells(area);
    const blocking = (occupied || []).filter((taken) => cellsOverlap(cells, taken));
    if (blocking.length === 0) {
        return Object.freeze({ area, shifted: Object.freeze([]) });
    }
    // Everything on the insertion row and below slides down together, so relative
    // order and side-by-side pairs survive the insert.
    const shifted = (occupied || [])
        .filter((taken) => taken.rowEnd >= area.rowStart)
        .map((taken) => Object.freeze({
            componentId: taken.componentId,
            rowStart: taken.rowStart + rowSpan,
        }));
    return Object.freeze({ area, shifted: Object.freeze(shifted) });
}

/**
 * Cells every sibling occupies once the insert is applied — what the drag preview
 * draws so the author sees the resulting layout before dropping.
 *
 * @param {{
 *   occupied: ReadonlyArray<OccupiedArea>,
 *   shifted: ReadonlyArray<RowShift>,
 * }} args
 * @returns {ReadonlyArray<{ componentId: string, columnStart: number, columnSpan: number, rowStart: number, rowSpan: number }>}
 */
export function projectInsertPreview({ occupied, shifted }) {
    const byId = new Map((shifted || []).map((item) => [item.componentId, item.rowStart]));
    return Object.freeze((occupied || []).map((taken) => {
        const rowStart = byId.has(taken.componentId) ? byId.get(taken.componentId) : taken.rowStart;
        return Object.freeze({
            componentId: taken.componentId,
            columnStart: taken.columnStart,
            columnSpan: taken.columnEnd - taken.columnStart + 1,
            rowStart,
            rowSpan: taken.rowEnd - taken.rowStart + 1,
        });
    }));
}
