/**
 * Pointer and keyboard gestures translated into grid placement proposals.
 *
 * Authoring is grid-only: every proposal is an area of whole cells plus the
 * `valid` verdict of the free-cell invariant. Move keeps the grab offset (the
 * dragged box travels with the pointer, the pointer is not the anchor) and
 * refuses when the target cells are taken. Resize clamps to the last free cell
 * instead of refusing, so dragging a handle always feels alive.
 */
import { resolvedPlacement } from '../layout/grid-contract.js';
import { isAreaFree } from '../layout/grid-occupancy.js';

const MIN_GESTURE_SIZE_PX = 8;

export const FLOW_UI_RESIZE_KINDS = Object.freeze(['e', 'w', 'n', 's', 'ne', 'nw', 'se', 'sw']);

function assertRect(rect, name) {
    if (rect == null || typeof rect !== 'object') {
        throw new Error(`flow-ui gesture: ${name} required`);
    }
    for (const key of ['x', 'y', 'width', 'height']) {
        if (!Number.isFinite(rect[key])) {
            throw new Error(`flow-ui gesture: ${name}.${key} must be finite`);
        }
    }
}

function assertPoint(point, name) {
    if (point == null || !Number.isFinite(point.x) || !Number.isFinite(point.y)) {
        throw new Error(`flow-ui gesture: ${name} must be a finite point`);
    }
}

/** Column span clamped by the type policy and the parent grid. */
export function clampColumnSpan(span, { minColumnSpan, maxColumnSpan, columns }) {
    if (!Number.isInteger(columns) || columns < 1) {
        throw new Error(`flow-ui gesture: columns invalid ${JSON.stringify(columns)}`);
    }
    const max = maxColumnSpan === 'full' ? columns : Math.min(maxColumnSpan, columns);
    const value = span === 'full' || span == null ? columns : span;
    if (!Number.isInteger(value)) {
        throw new Error(`flow-ui gesture: column_span must be integer or full, got ${JSON.stringify(span)}`);
    }
    return Math.min(Math.max(value, minColumnSpan, 1), Math.max(max, minColumnSpan, 1));
}

/** Row span clamped by the type policy. */
export function clampRowSpan(span, { minRowSpan, maxRowSpan }) {
    const value = Number.isInteger(span) && span >= 1 ? span : 1;
    const min = Number.isInteger(minRowSpan) ? minRowSpan : 1;
    const bounded = Math.max(value, min);
    return Number.isInteger(maxRowSpan) ? Math.min(bounded, maxRowSpan) : bounded;
}

/**
 * Current placement of the dragged component as whole cells.
 *
 * @param {{ placement: object, band: string, columns: number, policy: object }} args
 * @returns {{ columnStart: number, columnSpan: number, rowStart: number, rowSpan: number, fullWidth: boolean }}
 */
export function currentArea({ placement, band, columns, policy }) {
    const value = resolvedPlacement(placement || { base: {}, overrides: {} }, band);
    const fullWidth = value.column_span === 'full' || value.column_span == null;
    const columnSpan = clampColumnSpan(value.column_span, { ...policy, columns });
    const columnStart = fullWidth || !Number.isInteger(value.column_start) || value.column_start < 1
        ? 1
        : Math.min(value.column_start, columns - columnSpan + 1);
    return Object.freeze({
        columnStart: Math.max(1, columnStart),
        columnSpan,
        rowStart: Number.isInteger(value.row_start) && value.row_start >= 1 ? value.row_start : 1,
        rowSpan: clampRowSpan(value.row_span, policy),
        fullWidth,
    });
}

/**
 * Placement patch that turns `current` into `area`, or an empty patch when the
 * area did not change. `column_span` keeps the `full` form while it covers the
 * whole grid so responsive bands stay elastic.
 */
function placementPatch(current, area, columns) {
    const patch = {};
    const nextSpan = area.columnSpan >= columns ? 'full' : area.columnSpan;
    const currentSpan = current.fullWidth ? 'full' : current.columnSpan;
    if (nextSpan !== currentSpan) patch.column_span = nextSpan;
    if (area.columnStart !== current.columnStart || current.fullWidth !== (nextSpan === 'full')) {
        patch.column_start = area.columnStart;
    }
    if (area.rowStart !== current.rowStart) patch.row_start = area.rowStart;
    if (area.rowSpan !== current.rowSpan) patch.row_span = area.rowSpan;
    return patch;
}

function proposal({ area, geometry, patch, valid }) {
    return Object.freeze({
        area: Object.freeze({ ...area }),
        targetCell: geometry.rectOf(area),
        patch: Object.freeze(patch),
        valid,
    });
}

/**
 * Move gesture: the dragged box follows the pointer delta, snaps to the nearest
 * cell and only commits when those cells are free.
 *
 * @param {{
 *   geometry: object,
 *   startRect: { x: number, y: number, width: number, height: number },
 *   pointerStart: { x: number, y: number },
 *   pointerNow: { x: number, y: number },
 *   placement: object,
 *   band: string,
 *   policy: object,
 *   occupied: ReadonlyArray<object>,
 * }} session
 */
export function proposeGridMove(session) {
    const {
        geometry, startRect, pointerStart, pointerNow, placement, band, policy, occupied,
    } = session;
    if (!geometry || typeof geometry.rectOf !== 'function') {
        throw new Error('flow-ui gesture: grid geometry required');
    }
    assertRect(startRect, 'startRect');
    assertPoint(pointerStart, 'pointerStart');
    assertPoint(pointerNow, 'pointerNow');

    const columns = geometry.columns;
    const current = currentArea({ placement, band, columns, policy });
    const ghostRect = {
        x: startRect.x + (pointerNow.x - pointerStart.x),
        y: startRect.y + (pointerNow.y - pointerStart.y),
        width: startRect.width,
        height: startRect.height,
    };
    const area = geometry.areaFor(ghostRect, {
        columnSpan: current.columnSpan,
        rowSpan: current.rowSpan,
    });
    const valid = isAreaFree(area, occupied, columns);
    const patch = valid ? placementPatch(current, area, columns) : {};
    return Object.freeze({
        ...proposal({ area, geometry, patch, valid }),
        ghostRect: Object.freeze(ghostRect),
    });
}

/**
 * Resize gesture: edge handles change spans (and the start cell for N/W), each
 * span growing only as far as the next occupied cell.
 *
 * @param {{
 *   kind: string,
 *   geometry: object,
 *   startRect: object,
 *   pointerStart: object,
 *   pointerNow: object,
 *   placement: object,
 *   band: string,
 *   policy: object,
 *   occupied: ReadonlyArray<object>,
 * }} session
 */
export function proposeGridResize(session) {
    const {
        kind, geometry, startRect, pointerStart, pointerNow, placement, band, policy, occupied,
    } = session;
    if (!FLOW_UI_RESIZE_KINDS.includes(kind)) {
        throw new Error(`flow-ui gesture: unknown resize kind ${JSON.stringify(kind)}`);
    }
    if (!geometry || typeof geometry.rectOf !== 'function') {
        throw new Error('flow-ui gesture: grid geometry required');
    }
    assertRect(startRect, 'startRect');
    assertPoint(pointerStart, 'pointerStart');
    assertPoint(pointerNow, 'pointerNow');

    const columns = geometry.columns;
    const current = currentArea({ placement, band, columns, policy });
    const dx = pointerNow.x - pointerStart.x;
    const dy = pointerNow.y - pointerStart.y;

    const ghostRect = { ...startRect };
    if (kind.includes('e')) {
        ghostRect.width = Math.max(MIN_GESTURE_SIZE_PX, startRect.width + dx);
    }
    if (kind.includes('w')) {
        ghostRect.width = Math.max(MIN_GESTURE_SIZE_PX, startRect.width - dx);
        ghostRect.x = startRect.x + (startRect.width - ghostRect.width);
    }
    if (kind.includes('s')) {
        ghostRect.height = Math.max(MIN_GESTURE_SIZE_PX, startRect.height + dy);
    }
    if (kind.includes('n')) {
        ghostRect.height = Math.max(MIN_GESTURE_SIZE_PX, startRect.height - dy);
        ghostRect.y = startRect.y + (startRect.height - ghostRect.height);
    }

    const inline = policy.canResizeInline && (kind.includes('e') || kind.includes('w'));
    const block = policy.canResizeBlock && (kind.includes('n') || kind.includes('s'));

    let columnStart = current.columnStart;
    let columnSpan = current.columnSpan;
    if (inline) {
        const wanted = clampColumnSpan(geometry.columnSpanOfWidth(ghostRect.width), { ...policy, columns });
        if (kind.includes('w')) {
            const right = current.columnStart + current.columnSpan - 1;
            columnStart = Math.min(Math.max(right - wanted + 1, 1), right);
            columnSpan = right - columnStart + 1;
        } else {
            columnSpan = Math.min(wanted, columns - columnStart + 1);
        }
    }

    let rowStart = current.rowStart;
    let rowSpan = current.rowSpan;
    if (block) {
        const anchorRow = kind.includes('n') ? current.rowStart + current.rowSpan - 1 : current.rowStart;
        const wanted = clampRowSpan(geometry.rowSpanOfHeight(ghostRect.height, anchorRow), policy);
        if (kind.includes('n')) {
            const bottom = current.rowStart + current.rowSpan - 1;
            rowStart = Math.min(Math.max(bottom - wanted + 1, 1), bottom);
            rowSpan = bottom - rowStart + 1;
        } else {
            rowSpan = wanted;
        }
    }

    const area = shrinkToFree(
        { columnStart, columnSpan, rowStart, rowSpan },
        current,
        occupied,
        columns,
        policy,
    );
    const valid = isAreaFree(area, occupied, columns);
    const patch = valid ? placementPatch(current, area, columns) : {};
    return Object.freeze({
        ...proposal({ area, geometry, patch, valid }),
        ghostRect: Object.freeze(ghostRect),
    });
}

/**
 * Pull a resized area back until it stops overlapping siblings, one cell at a
 * time, never below the current area (which is free by construction).
 */
function shrinkToFree(area, current, occupied, columns, policy) {
    const minColumnSpan = Math.max(1, policy.minColumnSpan);
    const minRowSpan = Math.max(1, Number.isInteger(policy.minRowSpan) ? policy.minRowSpan : 1);
    let next = { ...area };
    while (!isAreaFree(next, occupied, columns)) {
        const grewRight = next.columnStart + next.columnSpan > current.columnStart + current.columnSpan;
        const grewLeft = next.columnStart < current.columnStart;
        const grewDown = next.rowStart + next.rowSpan > current.rowStart + current.rowSpan;
        const grewUp = next.rowStart < current.rowStart;
        if (grewRight && next.columnSpan > minColumnSpan) {
            next = { ...next, columnSpan: next.columnSpan - 1 };
        } else if (grewLeft && next.columnSpan > minColumnSpan) {
            next = { ...next, columnStart: next.columnStart + 1, columnSpan: next.columnSpan - 1 };
        } else if (grewDown && next.rowSpan > minRowSpan) {
            next = { ...next, rowSpan: next.rowSpan - 1 };
        } else if (grewUp && next.rowSpan > minRowSpan) {
            next = { ...next, rowStart: next.rowStart + 1, rowSpan: next.rowSpan - 1 };
        } else {
            return {
                columnStart: current.columnStart,
                columnSpan: current.columnSpan,
                rowStart: current.rowStart,
                rowSpan: current.rowSpan,
            };
        }
    }
    return next;
}

/**
 * Area for a palette drop: the pointer cell, pulled to the first free row of its
 * column range when that exact cell is taken.
 *
 * @param {{
 *   geometry: object,
 *   point: { x: number, y: number },
 *   columnSpan: number | 'full',
 *   rowSpan?: number,
 *   occupied: ReadonlyArray<object>,
 * }} args
 */
export function proposeGridDrop({ geometry, point, columnSpan, rowSpan = 1, occupied }) {
    if (!geometry || typeof geometry.cellAt !== 'function') {
        throw new Error('flow-ui gesture: grid geometry required for drop');
    }
    assertPoint(point, 'point');
    const columns = geometry.columns;
    const span = columnSpan === 'full' || columnSpan == null
        ? columns
        : Math.min(Math.max(columnSpan, 1), columns);
    const cell = geometry.cellAt(point);
    const columnStart = Math.min(cell.column, columns - span + 1);
    const area = { columnStart, columnSpan: span, rowStart: cell.row, rowSpan };
    const valid = isAreaFree(area, occupied, columns);
    return Object.freeze({
        area: Object.freeze(area),
        targetCell: geometry.rectOf(area),
        valid,
    });
}

/**
 * Keyboard step: arrows move by one cell, shift+arrows resize by one cell.
 * A step onto occupied cells is a no-op, exactly like a refused drag.
 *
 * @returns {{ patch: object } | null}
 */
export function proposeKeyboardStep({
    key,
    shift,
    policy,
    placement,
    band,
    columns,
    occupied,
}) {
    if (!Number.isInteger(columns) || columns < 1) {
        throw new Error(`flow-ui gesture: columns invalid ${JSON.stringify(columns)}`);
    }
    const current = currentArea({ placement, band, columns, policy });
    let area = null;

    if (!shift && policy.canMove) {
        if (key === 'ArrowLeft' || key === 'ArrowRight') {
            const delta = key === 'ArrowRight' ? 1 : -1;
            const columnStart = current.columnStart + delta;
            if (columnStart < 1 || columnStart + current.columnSpan - 1 > columns) return null;
            area = { ...current, columnStart };
        } else if (key === 'ArrowUp' || key === 'ArrowDown') {
            const rowStart = current.rowStart + (key === 'ArrowDown' ? 1 : -1);
            if (rowStart < 1) return null;
            area = { ...current, rowStart };
        }
    } else if (shift) {
        if (policy.canResizeInline && (key === 'ArrowLeft' || key === 'ArrowRight')) {
            const columnSpan = clampColumnSpan(
                current.columnSpan + (key === 'ArrowRight' ? 1 : -1),
                { ...policy, columns },
            );
            if (current.columnStart + columnSpan - 1 > columns) return null;
            area = { ...current, columnSpan };
        } else if (policy.canResizeBlock && (key === 'ArrowUp' || key === 'ArrowDown')) {
            area = {
                ...current,
                rowSpan: clampRowSpan(current.rowSpan + (key === 'ArrowDown' ? 1 : -1), policy),
            };
        }
    }

    if (area == null) return null;
    const next = {
        columnStart: area.columnStart,
        columnSpan: area.columnSpan,
        rowStart: area.rowStart,
        rowSpan: area.rowSpan,
    };
    if (!isAreaFree(next, occupied, columns)) return null;
    const patch = placementPatch(current, next, columns);
    if (Object.keys(patch).length === 0) return null;
    return Object.freeze({ patch: Object.freeze(patch) });
}
