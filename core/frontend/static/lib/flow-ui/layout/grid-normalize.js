/**
 * Give every grid child a free cell.
 *
 * Authoring and rendering both need explicit cells: the author drags whole cells
 * and the free-cell invariant is a question about cells, so "let CSS place it"
 * cannot survive into the document. A template declares spans (and columns where
 * it wants a two-up row); the row is derived once, deterministically, row-major
 * in child order.
 *
 * Documents written before placement became explicit have every child on row 1,
 * which renders as a pile. Those collisions are repaired here — a child that
 * overlaps an already placed sibling drops to the first free row of its columns.
 */
import { firstFreeRow, isAreaFree, placementCells } from './grid-occupancy.js';

function areaOf(cells) {
    return {
        columnStart: cells.columnStart,
        columnSpan: cells.columnEnd - cells.columnStart + 1,
        rowStart: cells.rowStart,
        rowSpan: cells.rowEnd - cells.rowStart + 1,
    };
}

/**
 * @param {object} surface
 * @returns {boolean} true when anything changed
 */
export function assignExplicitGridRows(surface) {
    if (!surface?.components || typeof surface.components !== 'object') {
        return false;
    }
    let changed = false;
    for (const parent of Object.values(surface.components)) {
        if (!parent || parent.container_layout?.mode !== 'grid') continue;
        const children = parent.children || [];
        if (children.length === 0) continue;
        const columns = parent.container_layout.grid?.columns_by_band?.wide ?? 12;
        const taken = [];
        const explicit = [];
        const pending = [];
        for (const childId of children) {
            const child = surface.components[childId];
            if (!child || typeof child !== 'object') continue;
            child.placement ||= { base: {}, overrides: {} };
            child.placement.base ||= {};
            const base = child.placement.base;
            if (!Number.isInteger(base.row_span) || base.row_span < 1) {
                base.row_span = 1;
                changed = true;
            }
            if (base.column_start === 'auto' || base.column_start == null) {
                base.column_start = 1;
                changed = true;
            }
            if (Number.isInteger(base.row_start) && base.row_start >= 1) {
                explicit.push(child);
                continue;
            }
            pending.push(child);
        }
        // Explicit cells win in child order; a collision moves the later child down.
        for (const child of [...explicit, ...pending]) {
            const cells = placementCells(child.placement, 'wide', columns);
            const area = areaOf(cells);
            const isPending = pending.includes(child);
            if (!isPending && isAreaFree(area, taken, columns)) {
                taken.push({ componentId: child.component_id, ...cells });
                continue;
            }
            const row = firstFreeRow({ ...area, rowStart: 1 }, taken, columns);
            if (child.placement.base.row_start !== row) {
                child.placement.base.row_start = row;
                changed = true;
            }
            taken.push({
                componentId: child.component_id,
                ...placementCells(child.placement, 'wide', columns),
            });
        }
    }
    return changed;
}
