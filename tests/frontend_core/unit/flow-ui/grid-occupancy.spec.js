import { describe, expect, it } from 'vitest';

import {
    cellsOverlap,
    firstFreeRow,
    isAreaFree,
    nextFreeRow,
    occupiedAreas,
    placementCells,
} from '../../../../core/frontend/static/lib/flow-ui/layout/grid-occupancy.js';

function placed(columnStart, columnSpan, rowStart, rowSpan = 1) {
    return {
        placement: {
            base: {
                column_start: columnStart,
                column_span: columnSpan,
                row_start: rowStart,
                row_span: rowSpan,
            },
            overrides: {},
        },
    };
}

describe('flow-ui grid occupancy', () => {
    it('resolves placement cells including full span and band overrides', () => {
        expect(placementCells(placed(3, 4, 2, 2).placement, 'wide', 12)).toEqual({
            columnStart: 3, columnEnd: 6, rowStart: 2, rowEnd: 3,
        });
        expect(placementCells({ base: { column_span: 'full', row_start: 5 }, overrides: {} }, 'wide', 12)).toEqual({
            columnStart: 1, columnEnd: 12, rowStart: 5, rowEnd: 5,
        });
        expect(placementCells({
            base: { column_start: 7, column_span: 6, row_start: 1 },
            overrides: { compact: { column_start: 1, column_span: 'full' } },
        }, 'compact', 4)).toEqual({
            columnStart: 1, columnEnd: 4, rowStart: 1, rowEnd: 1,
        });
    });

    it('treats missing span/row as full width on row 1', () => {
        expect(placementCells({ base: {}, overrides: {} }, 'wide', 8)).toEqual({
            columnStart: 1, columnEnd: 8, rowStart: 1, rowEnd: 1,
        });
    });

    it('clamps a span that would leave the grid', () => {
        expect(placementCells(placed(11, 6, 1).placement, 'wide', 12)).toEqual({
            columnStart: 11, columnEnd: 12, rowStart: 1, rowEnd: 1,
        });
    });

    it('collects sibling cells from the document and skips self and hidden', () => {
        const components = {
            root: { component_id: 'root', children: ['a', 'b', 'c'] },
            a: { component_id: 'a', ...placed(1, 6, 1) },
            b: { component_id: 'b', ...placed(7, 6, 1) },
            c: { component_id: 'c', ...placed(1, 12, 2), visibility: { hidden: true } },
        };
        const areas = occupiedAreas({
            parent: components.root,
            components,
            band: 'wide',
            columns: 12,
            excludeComponentId: 'a',
        });
        expect(areas.map((area) => area.componentId)).toEqual(['b']);
        expect(Object.isFrozen(areas)).toBe(true);
    });

    it('answers the free-cell invariant: free next to occupied, blocked on overlap', () => {
        const components = {
            root: { component_id: 'root', children: ['left', 'moving'] },
            left: { component_id: 'left', ...placed(1, 6, 1) },
            moving: { component_id: 'moving', ...placed(1, 6, 4) },
        };
        const occupied = occupiedAreas({
            parent: components.root,
            components,
            band: 'wide',
            columns: 12,
            excludeComponentId: 'moving',
        });
        const beside = { columnStart: 7, columnSpan: 6, rowStart: 1, rowSpan: 1 };
        const onTop = { columnStart: 4, columnSpan: 6, rowStart: 1, rowSpan: 1 };
        expect(isAreaFree(beside, occupied, 12)).toBe(true);
        expect(isAreaFree(onTop, occupied, 12)).toBe(false);
        expect(isAreaFree({ ...beside, columnStart: 10 }, occupied, 12)).toBe(false);
    });

    it('detects inclusive cell overlap on both axes', () => {
        const base = { columnStart: 3, columnEnd: 6, rowStart: 2, rowEnd: 4 };
        expect(cellsOverlap(base, { columnStart: 6, columnEnd: 8, rowStart: 4, rowEnd: 9 })).toBe(true);
        expect(cellsOverlap(base, { columnStart: 7, columnEnd: 8, rowStart: 2, rowEnd: 4 })).toBe(false);
        expect(cellsOverlap(base, { columnStart: 3, columnEnd: 6, rowStart: 5, rowEnd: 6 })).toBe(false);
    });

    it('finds the first free row for a column range, ignoring other columns', () => {
        const occupied = [
            { componentId: 'a', columnStart: 1, columnEnd: 6, rowStart: 1, rowEnd: 2 },
            { componentId: 'b', columnStart: 7, columnEnd: 12, rowStart: 1, rowEnd: 8 },
        ];
        expect(firstFreeRow({ columnStart: 1, columnSpan: 6, rowStart: 1, rowSpan: 1 }, occupied, 12)).toBe(3);
        expect(firstFreeRow({ columnStart: 7, columnSpan: 6, rowStart: 1, rowSpan: 1 }, occupied, 12)).toBe(9);
        expect(firstFreeRow({ columnStart: 1, columnSpan: 12, rowStart: 1, rowSpan: 1 }, occupied, 12)).toBe(9);
        expect(firstFreeRow({ columnStart: 1, columnSpan: 6, rowStart: 1, rowSpan: 1 }, [], 12)).toBe(1);
    });

    it('appends below every occupied cell', () => {
        expect(nextFreeRow([])).toBe(1);
        expect(nextFreeRow([
            { columnStart: 1, columnEnd: 4, rowStart: 1, rowEnd: 1 },
            { columnStart: 1, columnEnd: 4, rowStart: 3, rowEnd: 5 },
        ])).toBe(6);
    });

    it('rejects malformed areas instead of guessing', () => {
        expect(() => isAreaFree({ columnStart: 0, columnSpan: 1, rowStart: 1, rowSpan: 1 }, [], 12))
            .toThrow(/area invalid/);
        expect(() => placementCells({ base: {}, overrides: {} }, 'wide', 0)).toThrow(/columns/);
    });
});
