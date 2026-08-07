/**
 * The single bijection between grid cells and CSS pixels.
 *
 * `contentRect` is the parent grid's content box (border box minus padding) —
 * the real track area. Column tracks are equal `minmax(0, 1fr)`, row tracks are
 * uniform `FLOW_UI_ROW_HEIGHT_PX`, both separated by their gaps. Every editor
 * consumer (gesture, target-cell highlight, grid overlay, palette drop) resolves
 * geometry here, so the highlighted cell and the committed cell are the same by
 * construction.
 */

/** Uniform grid row track height (css px). */
export const FLOW_UI_ROW_HEIGHT_PX = 48;

function assertFiniteRect(rect) {
    if (rect == null || typeof rect !== 'object') {
        throw new Error('flow-ui grid-geometry: contentRect required');
    }
    for (const key of ['x', 'y', 'width', 'height']) {
        if (!Number.isFinite(rect[key])) {
            throw new Error(`flow-ui grid-geometry: contentRect.${key} must be finite`);
        }
    }
    if (rect.width <= 0) {
        throw new Error('flow-ui grid-geometry: contentRect.width must be positive');
    }
}

function assertGap(value, name) {
    if (!Number.isFinite(value) || value < 0) {
        throw new Error(`flow-ui grid-geometry: ${name} must be a non-negative number`);
    }
}

/**
 * @typedef {{ column: number, row: number }} GridCell
 * @typedef {{ columnStart: number, columnSpan: number, rowStart: number, rowSpan: number }} GridArea
 * @typedef {{ x: number, y: number, width: number, height: number }} Rect
 */

/**
 * `rowTracks` are the used pixel heights of the parent's rows. A row is one
 * baseline tall and grows with its content, so tracks are not uniform; rows past
 * the known tracks fall back to the baseline height.
 *
 * @param {{
 *   contentRect: Rect,
 *   columns: number,
 *   columnGap: number,
 *   rowGap: number,
 *   rowTracks?: readonly number[],
 *   rowHeight?: number,
 * }} args
 */
export function createGridGeometry({
    contentRect,
    columns,
    columnGap,
    rowGap,
    rowTracks = [],
    rowHeight = FLOW_UI_ROW_HEIGHT_PX,
}) {
    assertFiniteRect(contentRect);
    if (!Number.isInteger(columns) || columns < 1) {
        throw new Error(`flow-ui grid-geometry: columns must be a positive integer, got ${JSON.stringify(columns)}`);
    }
    assertGap(columnGap, 'columnGap');
    assertGap(rowGap, 'rowGap');
    if (!Number.isFinite(rowHeight) || rowHeight <= 0) {
        throw new Error(`flow-ui grid-geometry: rowHeight must be positive, got ${JSON.stringify(rowHeight)}`);
    }

    const columnWidth = (contentRect.width - columnGap * (columns - 1)) / columns;
    if (!(columnWidth > 0)) {
        throw new Error('flow-ui grid-geometry: column track width must be positive');
    }
    const columnStep = columnWidth + columnGap;
    const rowStep = rowHeight + rowGap;
    const tracks = (rowTracks || []).map((size) => {
        if (!Number.isFinite(size) || size <= 0) {
            throw new Error(`flow-ui grid-geometry: row track invalid ${JSON.stringify(size)}`);
        }
        return size;
    });

    const clampColumn = (value) => Math.min(Math.max(value, 1), columns);
    // Fractional track sizes make an exact track line land on 10.999...; nudge
    // before flooring so `cellAt(rectOf(area))` returns that very cell.
    const trackIndex = (offset, step) => Math.floor(offset / step + 1e-6);

    /** Distance from the content top to the start line of a 1-based row. */
    const rowOffset = (row) => {
        let offset = 0;
        for (let index = 1; index < row; index += 1) {
            offset += (index <= tracks.length ? tracks[index - 1] : rowHeight) + rowGap;
        }
        return offset;
    };

    /** Height of `rowSpan` rows starting at `rowStart`, gaps between them included. */
    const rowExtent = (rowStart, rowSpan) => {
        let height = 0;
        for (let index = rowStart; index < rowStart + rowSpan; index += 1) {
            height += index <= tracks.length ? tracks[index - 1] : rowHeight;
        }
        return height + rowGap * (rowSpan - 1);
    };

    /** 1-based row containing a local Y offset. */
    const rowAtOffset = (offset) => {
        if (offset <= 0) return 1;
        let cursor = 0;
        for (let row = 1; row <= tracks.length; row += 1) {
            cursor += tracks[row - 1] + rowGap;
            if (offset < cursor - 1e-6) return row;
        }
        return tracks.length + Math.max(1, trackIndex(offset - cursor, rowStep) + 1);
    };

    /** Row whose start line is nearest to a local Y offset (move snapping). */
    const nearestRowLine = (offset) => {
        let best = 1;
        let bestDistance = Number.POSITIVE_INFINITY;
        const limit = tracks.length + 2;
        for (let row = 1; row <= limit; row += 1) {
            const distance = Math.abs(rowOffset(row) - offset);
            if (distance < bestDistance) {
                bestDistance = distance;
                best = row;
            }
        }
        if (offset <= rowOffset(limit)) return best;
        // Past the last known track the grid is uniform again.
        return limit + Math.max(0, Math.round((offset - rowOffset(limit)) / rowStep));
    };

    /** Cell containing a point (floor semantics: the cell the pointer is inside). */
    const cellAt = (point) => {
        if (!Number.isFinite(point?.x) || !Number.isFinite(point?.y)) {
            throw new Error('flow-ui grid-geometry: cellAt requires a finite point');
        }
        return Object.freeze({
            column: clampColumn(trackIndex(point.x - contentRect.x, columnStep) + 1),
            row: rowAtOffset(point.y - contentRect.y),
        });
    };

    /**
     * Start cell for a moved rectangle: rounds to the nearest track line, so a
     * drag of half a track already commits one step.
     */
    const areaFor = (rect, span) => {
        if (!Number.isFinite(rect?.x) || !Number.isFinite(rect?.y)) {
            throw new Error('flow-ui grid-geometry: areaFor requires a finite rect');
        }
        const columnSpan = span?.columnSpan;
        const rowSpan = span?.rowSpan;
        if (!Number.isInteger(columnSpan) || columnSpan < 1) {
            throw new Error(`flow-ui grid-geometry: columnSpan invalid ${JSON.stringify(columnSpan)}`);
        }
        if (!Number.isInteger(rowSpan) || rowSpan < 1) {
            throw new Error(`flow-ui grid-geometry: rowSpan invalid ${JSON.stringify(rowSpan)}`);
        }
        const maxColumnStart = Math.max(1, columns - columnSpan + 1);
        const columnStart = Math.min(
            Math.max(Math.round((rect.x - contentRect.x) / columnStep) + 1, 1),
            maxColumnStart,
        );
        const rowStart = Math.max(nearestRowLine(rect.y - contentRect.y), 1);
        return Object.freeze({ columnStart, columnSpan, rowStart, rowSpan });
    };

    /** Exact inverse of `areaFor` / `cellAt` for a whole area. */
    const rectOf = (area) => {
        const { columnStart, columnSpan, rowStart, rowSpan } = area || {};
        if (!Number.isInteger(columnStart) || columnStart < 1) {
            throw new Error(`flow-ui grid-geometry: columnStart invalid ${JSON.stringify(columnStart)}`);
        }
        if (!Number.isInteger(columnSpan) || columnSpan < 1) {
            throw new Error(`flow-ui grid-geometry: columnSpan invalid ${JSON.stringify(columnSpan)}`);
        }
        if (!Number.isInteger(rowStart) || rowStart < 1) {
            throw new Error(`flow-ui grid-geometry: rowStart invalid ${JSON.stringify(rowStart)}`);
        }
        if (!Number.isInteger(rowSpan) || rowSpan < 1) {
            throw new Error(`flow-ui grid-geometry: rowSpan invalid ${JSON.stringify(rowSpan)}`);
        }
        const span = Math.min(columnSpan, columns - columnStart + 1);
        return Object.freeze({
            x: contentRect.x + (columnStart - 1) * columnStep,
            y: contentRect.y + rowOffset(rowStart),
            width: span * columnWidth + (span - 1) * columnGap,
            height: rowExtent(rowStart, rowSpan),
        });
    };

    /** Column count a pixel width covers (resize E/W). */
    const columnSpanOfWidth = (width) => {
        if (!Number.isFinite(width)) {
            throw new Error('flow-ui grid-geometry: columnSpanOfWidth requires a finite width');
        }
        return Math.min(columns, Math.max(1, Math.round((width + columnGap) / columnStep)));
    };

    /** Row count a pixel height covers from `rowStart` (resize N/S). */
    const rowSpanOfHeight = (height, rowStart = 1) => {
        if (!Number.isFinite(height)) {
            throw new Error('flow-ui grid-geometry: rowSpanOfHeight requires a finite height');
        }
        let span = 1;
        while (rowExtent(rowStart, span + 1) - (height + rowGap / 2) <= 0) {
            span += 1;
            if (span > 512) break;
        }
        return span;
    };

    return Object.freeze({
        columns,
        columnWidth,
        columnStep,
        rowHeight,
        rowStep,
        rowTracks: Object.freeze([...tracks]),
        contentRect: Object.freeze({ ...contentRect }),
        cellAt,
        areaFor,
        rectOf,
        rowOffset,
        columnSpanOfWidth,
        rowSpanOfHeight,
    });
}
