import { describe, expect, it } from 'vitest';

import { createGridGeometry } from '../../../../core/frontend/static/lib/flow-ui/layout/grid-geometry.js';
import { occupiedAreas } from '../../../../core/frontend/static/lib/flow-ui/layout/grid-occupancy.js';
import {
    clampColumnSpan,
    clampRowSpan,
    currentArea,
    proposeGridDrop,
    proposeGridMove,
    proposeGridResize,
    proposeKeyboardStep,
} from '../../../../core/frontend/static/lib/flow-ui/editor/layout-gesture.js';

const POLICY = Object.freeze({
    move: 'grid',
    resizeInline: 'span',
    resizeBlock: 'row_span',
    minColumnSpan: 1,
    maxColumnSpan: 'full',
    minRowSpan: 1,
    maxRowSpan: null,
    canMove: true,
    canResizeInline: true,
    canResizeBlock: true,
});

function geometry(columns = 12) {
    return createGridGeometry({
        contentRect: { x: 16, y: 16, width: 1200, height: 800 },
        columns,
        columnGap: 16,
        rowGap: 16,
    });
}

function placement(base) {
    return { base, overrides: {} };
}

/** Siblings taken straight from a document, the way the canvas builds them. */
function occupied(children) {
    const components = { parent: { component_id: 'parent', children: Object.keys(children) } };
    for (const [id, base] of Object.entries(children)) {
        components[id] = { component_id: id, placement: placement(base) };
    }
    return occupiedAreas({
        parent: components.parent,
        components,
        band: 'wide',
        columns: 12,
        excludeComponentId: null,
    });
}

function moveBy(session, dx, dy) {
    return proposeGridMove({
        geometry: session.geometry,
        startRect: session.startRect,
        pointerStart: { x: 500, y: 500 },
        pointerNow: { x: 500 + dx, y: 500 + dy },
        placement: session.placement,
        band: 'wide',
        policy: POLICY,
        occupied: session.occupied,
    });
}

function session({ base, siblings = {} }) {
    const geo = geometry();
    const cells = {
        columnStart: base.column_start,
        columnSpan: base.column_span === 'full' ? 12 : base.column_span,
        rowStart: base.row_start,
        rowSpan: base.row_span ?? 1,
    };
    return {
        geometry: geo,
        placement: placement(base),
        startRect: geo.rectOf(cells),
        occupied: occupied(siblings),
    };
}

describe('flow-ui grid move gesture', () => {
    it('moves exactly one row up when dragged just over half a row', () => {
        const state = session({ base: { column_start: 1, column_span: 4, row_start: 3, row_span: 1 } });
        const proposal = moveBy(state, 0, -state.geometry.rowStep * 0.6);
        expect(proposal.valid).toBe(true);
        expect(proposal.area).toEqual({ columnStart: 1, columnSpan: 4, rowStart: 2, rowSpan: 1 });
        expect(proposal.patch).toEqual({ row_start: 2 });
    });

    it('keeps the grab offset: a small drag does not jump the box under the pointer', () => {
        const state = session({ base: { column_start: 5, column_span: 4, row_start: 3, row_span: 1 } });
        const proposal = moveBy(state, 4, 4);
        expect(proposal.area).toEqual({ columnStart: 5, columnSpan: 4, rowStart: 3, rowSpan: 1 });
        expect(proposal.patch).toEqual({});
        expect(proposal.ghostRect.x).toBe(state.startRect.x + 4);
        expect(proposal.ghostRect.y).toBe(state.startRect.y + 4);
    });

    it('drops into a free cell beside an occupied sibling', () => {
        const state = session({
            base: { column_start: 1, column_span: 6, row_start: 3, row_span: 1 },
            siblings: { left: { column_start: 1, column_span: 6, row_start: 1, row_span: 1 } },
        });
        const proposal = moveBy(state, state.geometry.columnStep * 6, -state.geometry.rowStep * 2);
        expect(proposal.valid).toBe(true);
        expect(proposal.area).toEqual({ columnStart: 7, columnSpan: 6, rowStart: 1, rowSpan: 1 });
        expect(proposal.patch).toEqual({ column_start: 7, row_start: 1 });
    });

    it('refuses an occupied cell without patching or moving the sibling', () => {
        const state = session({
            base: { column_start: 1, column_span: 6, row_start: 3, row_span: 1 },
            siblings: { taken: { column_start: 1, column_span: 6, row_start: 1, row_span: 1 } },
        });
        const proposal = moveBy(state, 0, -state.geometry.rowStep * 2);
        expect(proposal.valid).toBe(false);
        expect(proposal.patch).toEqual({});
        expect(proposal.area).toEqual({ columnStart: 1, columnSpan: 6, rowStart: 1, rowSpan: 1 });
    });

    it('targets the cell it reports, so the highlight equals the landing cell', () => {
        const state = session({ base: { column_start: 2, column_span: 3, row_start: 2, row_span: 2 } });
        const proposal = moveBy(state, state.geometry.columnStep * 2, state.geometry.rowStep);
        expect(proposal.targetCell).toEqual(state.geometry.rectOf(proposal.area));
    });

    it('never leaves the grid when dragged past the right edge', () => {
        const state = session({ base: { column_start: 9, column_span: 4, row_start: 1, row_span: 1 } });
        const proposal = moveBy(state, state.geometry.columnStep * 8, 0);
        expect(proposal.area.columnStart).toBe(9);
        expect(proposal.valid).toBe(true);
    });

    it('keeps a full-width component full width while changing rows', () => {
        const state = session({ base: { column_start: 1, column_span: 'full', row_start: 1, row_span: 1 } });
        const proposal = moveBy(state, 0, state.geometry.rowStep * 2);
        expect(proposal.area).toEqual({ columnStart: 1, columnSpan: 12, rowStart: 3, rowSpan: 1 });
        expect(proposal.patch).toEqual({ row_start: 3 });
    });
});

describe('flow-ui grid resize gesture', () => {
    it('grows the column span from the east handle', () => {
        const state = session({ base: { column_start: 1, column_span: 3, row_start: 1, row_span: 1 } });
        const proposal = proposeGridResize({
            kind: 'e',
            geometry: state.geometry,
            startRect: state.startRect,
            pointerStart: { x: 0, y: 0 },
            pointerNow: { x: state.geometry.columnStep * 2, y: 0 },
            placement: state.placement,
            band: 'wide',
            policy: POLICY,
            occupied: state.occupied,
        });
        expect(proposal.area.columnSpan).toBe(5);
        expect(proposal.patch).toEqual({ column_span: 5 });
    });

    it('moves the start cell when resizing from the west handle', () => {
        const state = session({ base: { column_start: 5, column_span: 3, row_start: 1, row_span: 1 } });
        const proposal = proposeGridResize({
            kind: 'w',
            geometry: state.geometry,
            startRect: state.startRect,
            pointerStart: { x: 0, y: 0 },
            pointerNow: { x: -state.geometry.columnStep * 2, y: 0 },
            placement: state.placement,
            band: 'wide',
            policy: POLICY,
            occupied: state.occupied,
        });
        expect(proposal.area).toEqual({ columnStart: 3, columnSpan: 5, rowStart: 1, rowSpan: 1 });
    });

    it('stops at the last free cell instead of refusing the whole resize', () => {
        const state = session({
            base: { column_start: 1, column_span: 3, row_start: 1, row_span: 1 },
            siblings: { wall: { column_start: 6, column_span: 4, row_start: 1, row_span: 1 } },
        });
        const proposal = proposeGridResize({
            kind: 'e',
            geometry: state.geometry,
            startRect: state.startRect,
            pointerStart: { x: 0, y: 0 },
            pointerNow: { x: state.geometry.columnStep * 6, y: 0 },
            placement: state.placement,
            band: 'wide',
            policy: POLICY,
            occupied: state.occupied,
        });
        expect(proposal.valid).toBe(true);
        expect(proposal.area.columnSpan).toBe(5);
    });

    it('grows row span from the south handle', () => {
        const state = session({ base: { column_start: 1, column_span: 4, row_start: 1, row_span: 1 } });
        const proposal = proposeGridResize({
            kind: 's',
            geometry: state.geometry,
            startRect: state.startRect,
            pointerStart: { x: 0, y: 0 },
            pointerNow: { x: 0, y: state.geometry.rowStep * 3 },
            placement: state.placement,
            band: 'wide',
            policy: POLICY,
            occupied: state.occupied,
        });
        expect(proposal.area.rowSpan).toBe(4);
        expect(proposal.patch).toEqual({ row_span: 4 });
    });

    it('rejects an unknown handle instead of guessing', () => {
        const state = session({ base: { column_start: 1, column_span: 4, row_start: 1, row_span: 1 } });
        expect(() => proposeGridResize({
            kind: 'middle',
            geometry: state.geometry,
            startRect: state.startRect,
            pointerStart: { x: 0, y: 0 },
            pointerNow: { x: 0, y: 0 },
            placement: state.placement,
            band: 'wide',
            policy: POLICY,
            occupied: state.occupied,
        })).toThrow(/unknown resize kind/);
    });
});

describe('flow-ui palette drop', () => {
    it('proposes the cell under the pointer', () => {
        const geo = geometry();
        const proposal = proposeGridDrop({
            geometry: geo,
            point: geo.rectOf({ columnStart: 4, columnSpan: 1, rowStart: 5, rowSpan: 1 }),
            columnSpan: 3,
            occupied: [],
        });
        expect(proposal.valid).toBe(true);
        expect(proposal.area).toEqual({ columnStart: 4, columnSpan: 3, rowStart: 5, rowSpan: 1 });
        expect(proposal.targetCell).toEqual(geo.rectOf(proposal.area));
    });

    it('marks a taken cell invalid', () => {
        const geo = geometry();
        const proposal = proposeGridDrop({
            geometry: geo,
            point: geo.rectOf({ columnStart: 1, columnSpan: 1, rowStart: 1, rowSpan: 1 }),
            columnSpan: 'full',
            occupied: occupied({ taken: { column_start: 1, column_span: 6, row_start: 1, row_span: 1 } }),
        });
        expect(proposal.valid).toBe(false);
    });

    it('pulls a wide drop back so the span stays inside the grid', () => {
        const geo = geometry();
        const proposal = proposeGridDrop({
            geometry: geo,
            point: geo.rectOf({ columnStart: 11, columnSpan: 1, rowStart: 1, rowSpan: 1 }),
            columnSpan: 4,
            occupied: [],
        });
        expect(proposal.area.columnStart).toBe(9);
    });
});

describe('flow-ui keyboard step', () => {
    it('moves one cell per arrow press', () => {
        const step = proposeKeyboardStep({
            key: 'ArrowUp',
            shift: false,
            policy: POLICY,
            placement: placement({ column_start: 2, column_span: 3, row_start: 4, row_span: 1 }),
            band: 'wide',
            columns: 12,
            occupied: [],
        });
        expect(step.patch).toEqual({ row_start: 3 });
    });

    it('resizes one cell with shift', () => {
        const step = proposeKeyboardStep({
            key: 'ArrowRight',
            shift: true,
            policy: POLICY,
            placement: placement({ column_start: 2, column_span: 3, row_start: 1, row_span: 1 }),
            band: 'wide',
            columns: 12,
            occupied: [],
        });
        expect(step.patch).toEqual({ column_span: 4 });
    });

    it('is a no-op onto an occupied cell, exactly like a refused drag', () => {
        const step = proposeKeyboardStep({
            key: 'ArrowUp',
            shift: false,
            policy: POLICY,
            placement: placement({ column_start: 1, column_span: 6, row_start: 2, row_span: 1 }),
            band: 'wide',
            columns: 12,
            occupied: occupied({ taken: { column_start: 1, column_span: 6, row_start: 1, row_span: 1 } }),
        });
        expect(step).toBeNull();
    });

    it('is a no-op at the grid edge', () => {
        expect(proposeKeyboardStep({
            key: 'ArrowUp',
            shift: false,
            policy: POLICY,
            placement: placement({ column_start: 1, column_span: 4, row_start: 1, row_span: 1 }),
            band: 'wide',
            columns: 12,
            occupied: [],
        })).toBeNull();
        expect(proposeKeyboardStep({
            key: 'ArrowRight',
            shift: false,
            policy: POLICY,
            placement: placement({ column_start: 9, column_span: 4, row_start: 1, row_span: 1 }),
            band: 'wide',
            columns: 12,
            occupied: [],
        })).toBeNull();
    });
});

describe('flow-ui gesture policy clamps', () => {
    it('clamps column span between policy min and grid columns', () => {
        expect(clampColumnSpan('full', { minColumnSpan: 1, maxColumnSpan: 'full', columns: 8 })).toBe(8);
        expect(clampColumnSpan(9, { minColumnSpan: 1, maxColumnSpan: 6, columns: 12 })).toBe(6);
        expect(clampColumnSpan(0, { minColumnSpan: 2, maxColumnSpan: 'full', columns: 12 })).toBe(2);
    });

    it('clamps row span by policy bounds', () => {
        expect(clampRowSpan(5, { minRowSpan: 1, maxRowSpan: 2 })).toBe(2);
        expect(clampRowSpan(0, { minRowSpan: 1, maxRowSpan: null })).toBe(1);
    });

    it('reads the current area from a band-resolved placement', () => {
        expect(currentArea({
            placement: {
                base: { column_start: 1, column_span: 'full', row_start: 2, row_span: 3 },
                overrides: { compact: { column_start: 1, column_span: 4 } },
            },
            band: 'compact',
            columns: 4,
            policy: POLICY,
        })).toEqual({
            columnStart: 1, columnSpan: 4, rowStart: 2, rowSpan: 3, fullWidth: false,
        });
    });
});
