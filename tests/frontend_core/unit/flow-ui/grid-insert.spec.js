import { describe, expect, it } from 'vitest';

import { createGridGeometry } from '../../../../core/frontend/static/lib/flow-ui/layout/grid-geometry.js';
import {
    projectInsertPreview,
    proposeGridInsert,
} from '../../../../core/frontend/static/lib/flow-ui/layout/grid-insert.js';

function geometry() {
    return createGridGeometry({
        contentRect: { x: 16, y: 16, width: 1200, height: 800 },
        columns: 12,
        columnGap: 16,
        rowGap: 16,
    });
}

function taken(componentId, columnStart, columnEnd, rowStart, rowEnd) {
    return { componentId, columnStart, columnEnd, rowStart, rowEnd };
}

/** Point inside a given cell of the grid. */
function pointIn(geo, column, row) {
    const rect = geo.rectOf({ columnStart: column, columnSpan: 1, rowStart: row, rowSpan: 1 });
    return { x: rect.x + 4, y: rect.y + 4 };
}

describe('flow-ui grid insert', () => {
    it('drops into a free row without moving anything', () => {
        const geo = geometry();
        const proposal = proposeGridInsert({
            geometry: geo,
            point: pointIn(geo, 1, 3),
            columnSpan: 'full',
            occupied: [taken('head', 1, 12, 1, 1)],
        });
        expect(proposal.area).toEqual({ columnStart: 1, columnSpan: 12, rowStart: 3, rowSpan: 1 });
        expect(proposal.shifted).toEqual([]);
    });

    it('opens the row up instead of refusing a taken one', () => {
        const geo = geometry();
        const proposal = proposeGridInsert({
            geometry: geo,
            point: pointIn(geo, 1, 2),
            columnSpan: 'full',
            occupied: [
                taken('head', 1, 12, 1, 1),
                taken('body', 1, 12, 2, 2),
                taken('foot', 1, 12, 3, 3),
            ],
        });
        expect(proposal.area.rowStart).toBe(2);
        expect(proposal.shifted).toEqual([
            { componentId: 'body', rowStart: 3 },
            { componentId: 'foot', rowStart: 4 },
        ]);
    });

    it('slides a whole two-up row together', () => {
        const geo = geometry();
        const proposal = proposeGridInsert({
            geometry: geo,
            point: pointIn(geo, 1, 1),
            columnSpan: 'full',
            occupied: [taken('left', 1, 6, 1, 1), taken('right', 7, 12, 1, 1)],
        });
        expect(proposal.shifted).toEqual([
            { componentId: 'left', rowStart: 2 },
            { componentId: 'right', rowStart: 2 },
        ]);
    });

    it('slides by the height of the inserted element', () => {
        const geo = geometry();
        const proposal = proposeGridInsert({
            geometry: geo,
            point: pointIn(geo, 1, 1),
            columnSpan: 'full',
            rowSpan: 3,
            occupied: [taken('body', 1, 12, 1, 2)],
        });
        expect(proposal.area.rowSpan).toBe(3);
        expect(proposal.shifted).toEqual([{ componentId: 'body', rowStart: 4 }]);
    });

    it('leaves a sibling beside the insertion column alone when the row is free there', () => {
        const geo = geometry();
        const proposal = proposeGridInsert({
            geometry: geo,
            point: pointIn(geo, 7, 1),
            columnSpan: 4,
            occupied: [taken('left', 1, 6, 1, 1)],
        });
        expect(proposal.area).toEqual({ columnStart: 7, columnSpan: 4, rowStart: 1, rowSpan: 1 });
        expect(proposal.shifted).toEqual([]);
    });

    it('pulls a wide drop back so the span stays inside the grid', () => {
        const geo = geometry();
        const proposal = proposeGridInsert({
            geometry: geo,
            point: pointIn(geo, 11, 1),
            columnSpan: 4,
            occupied: [],
        });
        expect(proposal.area.columnStart).toBe(9);
    });

    it('projects the layout the author will get', () => {
        const occupied = [taken('head', 1, 12, 1, 1), taken('body', 1, 12, 2, 2)];
        const preview = projectInsertPreview({
            occupied,
            shifted: [{ componentId: 'body', rowStart: 3 }],
        });
        expect(preview).toEqual([
            { componentId: 'head', columnStart: 1, columnSpan: 12, rowStart: 1, rowSpan: 1 },
            { componentId: 'body', columnStart: 1, columnSpan: 12, rowStart: 3, rowSpan: 1 },
        ]);
    });

    it('rejects a malformed row span instead of guessing', () => {
        expect(() => proposeGridInsert({
            geometry: geometry(),
            point: { x: 20, y: 20 },
            columnSpan: 'full',
            rowSpan: 0,
            occupied: [],
        })).toThrow(/rowSpan invalid/);
    });
});
