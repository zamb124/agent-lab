/**
 * Grid occupancy derived from the document, never from rendered pixels.
 *
 * `placement.column_start/column_span/row_start/row_span` is the source of truth,
 * so "is this cell free" is a pure question about the FlowUIDocument. Pixel round
 * trips (rect -> cell -> rect) are not used for collision.
 */
import { resolvedPlacement } from './grid-contract.js';

/**
 * @typedef {{ columnStart: number, columnSpan: number, rowStart: number, rowSpan: number }} GridArea
 * @typedef {{ componentId: string, columnStart: number, columnEnd: number, rowStart: number, rowEnd: number }} OccupiedArea
 */

/**
 * Inclusive cell rectangle of a component placement in one band.
 * `column_span: 'full'` (or missing) covers every column; `row_start: 'auto'`
 * (pre-normalize documents) resolves to row 1.
 *
 * @param {object} placement
 * @param {string} band
 * @param {number} columns
 * @returns {OccupiedArea}
 */
export function placementCells(placement, band, columns) {
    if (!Number.isInteger(columns) || columns < 1) {
        throw new Error(`flow-ui grid-occupancy: columns must be a positive integer, got ${JSON.stringify(columns)}`);
    }
    const value = resolvedPlacement(placement || { base: {}, overrides: {} }, band);
    const isFullSpan = value.column_span === 'full' || value.column_span == null;
    const columnStart = isFullSpan || !Number.isInteger(value.column_start) || value.column_start < 1
        ? 1
        : Math.min(value.column_start, columns);
    const columnSpan = isFullSpan
        ? columns - columnStart + 1
        : Math.min(Math.max(value.column_span, 1), columns - columnStart + 1);
    const rowStart = Number.isInteger(value.row_start) && value.row_start >= 1 ? value.row_start : 1;
    const rowSpan = Number.isInteger(value.row_span) && value.row_span >= 1 ? value.row_span : 1;
    return Object.freeze({
        columnStart,
        columnEnd: columnStart + columnSpan - 1,
        rowStart,
        rowEnd: rowStart + rowSpan - 1,
    });
}

/** Inclusive cell rectangle of a proposed area. */
export function areaCells(area) {
    const { columnStart, columnSpan, rowStart, rowSpan } = area || {};
    if (!Number.isInteger(columnStart) || columnStart < 1
        || !Number.isInteger(columnSpan) || columnSpan < 1
        || !Number.isInteger(rowStart) || rowStart < 1
        || !Number.isInteger(rowSpan) || rowSpan < 1) {
        throw new Error(`flow-ui grid-occupancy: area invalid ${JSON.stringify(area)}`);
    }
    return Object.freeze({
        columnStart,
        columnEnd: columnStart + columnSpan - 1,
        rowStart,
        rowEnd: rowStart + rowSpan - 1,
    });
}

/**
 * Cells taken by the siblings of `excludeComponentId` inside a grid parent.
 *
 * @param {{
 *   parent: object,
 *   components: Record<string, object>,
 *   band: string,
 *   columns: number,
 *   excludeComponentId?: string | null,
 * }} args
 * @returns {ReadonlyArray<OccupiedArea>}
 */
export function occupiedAreas({
    parent,
    components,
    band,
    columns,
    excludeComponentId = null,
}) {
    if (!parent || typeof parent !== 'object') {
        throw new Error('flow-ui grid-occupancy: parent required');
    }
    if (!components || typeof components !== 'object') {
        throw new Error('flow-ui grid-occupancy: components map required');
    }
    const areas = [];
    for (const childId of parent.children || []) {
        if (childId === excludeComponentId) continue;
        const child = components[childId];
        if (!child || typeof child !== 'object') continue;
        if (child.visibility?.hidden === true) continue;
        areas.push(Object.freeze({
            componentId: childId,
            ...placementCells(child.placement, band, columns),
        }));
    }
    return Object.freeze(areas);
}

/** Inclusive cell rectangles intersect. */
export function cellsOverlap(left, right) {
    return !(
        left.columnEnd < right.columnStart
        || left.columnStart > right.columnEnd
        || left.rowEnd < right.rowStart
        || left.rowStart > right.rowEnd
    );
}

/**
 * The free-cell invariant: an area is placeable when it stays inside the grid
 * columns and touches no occupied sibling cell.
 *
 * @param {GridArea} area
 * @param {ReadonlyArray<OccupiedArea>} occupied
 * @param {number} columns
 * @returns {boolean}
 */
export function isAreaFree(area, occupied, columns) {
    const cells = areaCells(area);
    if (!Number.isInteger(columns) || columns < 1) {
        throw new Error(`flow-ui grid-occupancy: columns must be a positive integer, got ${JSON.stringify(columns)}`);
    }
    if (cells.columnEnd > columns) return false;
    return !(occupied || []).some((taken) => cellsOverlap(cells, taken));
}

/**
 * Lowest row where the column range of `area` is free. Used when a document
 * still carries `row_start: 'auto'` and needs an explicit row.
 *
 * @param {GridArea} area
 * @param {ReadonlyArray<OccupiedArea>} occupied
 * @param {number} columns
 * @returns {number}
 */
export function firstFreeRow(area, occupied, columns) {
    const cells = areaCells(area);
    const blocking = (occupied || []).filter(
        (taken) => !(cells.columnEnd < taken.columnStart || cells.columnStart > taken.columnEnd),
    );
    let row = 1;
    let moved = true;
    while (moved) {
        moved = false;
        const probe = { ...area, rowStart: row };
        if (!isAreaFree(probe, blocking, columns)) {
            const rowEnd = row + area.rowSpan - 1;
            for (const taken of blocking) {
                if (taken.rowEnd >= row && taken.rowStart <= rowEnd && taken.rowEnd + 1 > row) {
                    row = taken.rowEnd + 1;
                    moved = true;
                }
            }
        }
    }
    return row;
}

/** Row directly below every occupied cell — the append position of a grid. */
export function nextFreeRow(occupied) {
    let row = 1;
    for (const taken of occupied || []) {
        if (taken.rowEnd + 1 > row) row = taken.rowEnd + 1;
    }
    return row;
}
