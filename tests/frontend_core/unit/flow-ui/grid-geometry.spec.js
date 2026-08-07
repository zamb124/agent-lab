import { describe, expect, it } from 'vitest';

import {
    FLOW_UI_ROW_HEIGHT_PX,
    createGridGeometry,
} from '../../../../core/frontend/static/lib/flow-ui/layout/grid-geometry.js';

/** Real authoring grid: 12 columns, 16px gaps, 16px padding inside a 1440px page. */
function pageGeometry(columns = 12) {
    return createGridGeometry({
        contentRect: { x: 16, y: 16, width: 1440 - 32, height: 900 - 32 },
        columns,
        columnGap: 16,
        rowGap: 16,
    });
}

describe('flow-ui grid geometry', () => {
    it('accounts for content padding and gaps when mapping a point to a cell', () => {
        const geometry = pageGeometry();
        // Row step is rowHeight + rowGap, not rowHeight: row 3 starts at 16 + 2 * 64.
        expect(geometry.rowStep).toBe(FLOW_UI_ROW_HEIGHT_PX + 16);
        expect(geometry.cellAt({ x: 16, y: 16 })).toEqual({ column: 1, row: 1 });
        expect(geometry.cellAt({ x: 16, y: 16 + 2 * 64 })).toEqual({ column: 1, row: 3 });
        expect(geometry.cellAt({ x: 16, y: 16 + 2 * 64 + 63 })).toEqual({ column: 1, row: 3 });
        expect(geometry.cellAt({ x: 16 + geometry.columnStep * 4, y: 16 })).toEqual({ column: 5, row: 1 });
    });

    it('clamps cells into the grid', () => {
        const geometry = pageGeometry();
        expect(geometry.cellAt({ x: -400, y: -400 })).toEqual({ column: 1, row: 1 });
        expect(geometry.cellAt({ x: 9000, y: 16 }).column).toBe(12);
    });

    it('round-trips area -> rect -> area for every cell and span', () => {
        for (const columns of [4, 8, 12]) {
            for (const columnGap of [0, 8, 16]) {
                for (const rowGap of [0, 16]) {
                    const geometry = createGridGeometry({
                        contentRect: { x: 24, y: 40, width: 1200, height: 800 },
                        columns,
                        columnGap,
                        rowGap,
                    });
                    for (let columnSpan = 1; columnSpan <= columns; columnSpan += 1) {
                        for (let columnStart = 1; columnStart <= columns - columnSpan + 1; columnStart += 1) {
                            for (const rowSpan of [1, 2, 5]) {
                                for (const rowStart of [1, 2, 7]) {
                                    const area = { columnStart, columnSpan, rowStart, rowSpan };
                                    const rect = geometry.rectOf(area);
                                    expect(geometry.areaFor(rect, { columnSpan, rowSpan })).toEqual(area);
                                    expect(geometry.cellAt(rect)).toEqual({ column: columnStart, row: rowStart });
                                }
                            }
                        }
                    }
                }
            }
        }
    });

    it('commits a step once the drag passes half a track', () => {
        const geometry = pageGeometry();
        const span = { columnSpan: 4, rowSpan: 1 };
        const start = geometry.rectOf({ columnStart: 5, columnSpan: 4, rowStart: 3, rowSpan: 1 });

        const nudgedUp = { ...start, y: start.y - geometry.rowStep * 0.6 };
        expect(geometry.areaFor(nudgedUp, span).rowStart).toBe(2);

        const barelyMoved = { ...start, y: start.y - geometry.rowStep * 0.2 };
        expect(geometry.areaFor(barelyMoved, span).rowStart).toBe(3);

        const nudgedLeft = { ...start, x: start.x - geometry.columnStep * 0.6 };
        expect(geometry.areaFor(nudgedLeft, span).columnStart).toBe(4);
    });

    it('keeps the moved area inside the grid when spans reach the edge', () => {
        const geometry = pageGeometry();
        const rect = geometry.rectOf({ columnStart: 9, columnSpan: 4, rowStart: 1, rowSpan: 1 });
        const pushedRight = { ...rect, x: rect.x + geometry.columnStep * 6 };
        expect(geometry.areaFor(pushedRight, { columnSpan: 4, rowSpan: 1 }).columnStart).toBe(9);
        expect(geometry.areaFor({ ...rect, y: rect.y - 500 }, { columnSpan: 4, rowSpan: 1 }).rowStart).toBe(1);
    });

    it('derives spans from pixel sizes', () => {
        const geometry = pageGeometry();
        expect(geometry.columnSpanOfWidth(geometry.rectOf({
            columnStart: 1, columnSpan: 3, rowStart: 1, rowSpan: 1,
        }).width)).toBe(3);
        expect(geometry.rowSpanOfHeight(geometry.rectOf({
            columnStart: 1, columnSpan: 1, rowStart: 1, rowSpan: 4,
        }).height)).toBe(4);
        expect(geometry.columnSpanOfWidth(2)).toBe(1);
    });

    it('rejects impossible grids instead of guessing', () => {
        expect(() => createGridGeometry({
            contentRect: { x: 0, y: 0, width: 100, height: 100 },
            columns: 0,
            columnGap: 0,
            rowGap: 0,
        })).toThrow(/columns/);
        expect(() => createGridGeometry({
            contentRect: { x: 0, y: 0, width: 100, height: 100 },
            columns: 12,
            columnGap: 40,
            rowGap: 0,
        })).toThrow(/track width/);
        expect(() => pageGeometry().cellAt({ x: Number.NaN, y: 0 })).toThrow(/finite point/);
    });

    it('uses the real row tracks when rows grew with their content', () => {
        // Rows: 48 (baseline), 160 (a card), 48 — separated by a 16px gap.
        const geometry = createGridGeometry({
            contentRect: { x: 0, y: 0, width: 1200, height: 800 },
            columns: 12,
            columnGap: 16,
            rowGap: 16,
            rowTracks: [48, 160, 48],
        });
        expect(geometry.rowOffset(1)).toBe(0);
        expect(geometry.rowOffset(2)).toBe(64);
        expect(geometry.rowOffset(3)).toBe(240);
        // Past the known tracks the grid is uniform again.
        expect(geometry.rowOffset(4)).toBe(304);

        expect(geometry.cellAt({ x: 0, y: 0 }).row).toBe(1);
        expect(geometry.cellAt({ x: 0, y: 100 }).row).toBe(2);
        expect(geometry.cellAt({ x: 0, y: 239 }).row).toBe(2);
        expect(geometry.cellAt({ x: 0, y: 240 }).row).toBe(3);

        const tall = geometry.rectOf({ columnStart: 1, columnSpan: 4, rowStart: 2, rowSpan: 2 });
        expect(tall.y).toBe(64);
        expect(tall.height).toBe(160 + 16 + 48);
        expect(geometry.areaFor(tall, { columnSpan: 4, rowSpan: 2 }).rowStart).toBe(2);
    });

    it('round-trips areas over non-uniform tracks', () => {
        const geometry = createGridGeometry({
            contentRect: { x: 12, y: 20, width: 960, height: 800 },
            columns: 8,
            columnGap: 8,
            rowGap: 16,
            rowTracks: [48, 96, 200, 48, 72],
        });
        for (let rowStart = 1; rowStart <= 7; rowStart += 1) {
            for (const rowSpan of [1, 2, 3]) {
                const area = { columnStart: 2, columnSpan: 3, rowStart, rowSpan };
                const rect = geometry.rectOf(area);
                expect(geometry.areaFor(rect, { columnSpan: 3, rowSpan })).toEqual(area);
                expect(geometry.cellAt(rect).row).toBe(rowStart);
            }
        }
    });

    it('derives a row span that covers a dragged height over real tracks', () => {
        const geometry = createGridGeometry({
            contentRect: { x: 0, y: 0, width: 1200, height: 800 },
            columns: 12,
            columnGap: 16,
            rowGap: 16,
            rowTracks: [48, 160, 48],
        });
        expect(geometry.rowSpanOfHeight(48, 1)).toBe(1);
        expect(geometry.rowSpanOfHeight(48 + 16 + 160, 1)).toBe(2);
        expect(geometry.rowSpanOfHeight(160, 2)).toBe(1);
    });
});
