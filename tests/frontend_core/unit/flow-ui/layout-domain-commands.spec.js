import { describe, expect, it } from 'vitest';

import { applyLayoutCommand } from '../../../../core/frontend/static/lib/flow-ui/editor/layout-domain-commands.js';

function gridLayout() {
    return {
        mode: 'grid',
        grid: { columns_by_band: { wide: 12, medium: 8, compact: 4 } },
    };
}

function placed(columnStart, columnSpan, rowStart, rowSpan = 1) {
    return {
        base: {
            column_start: columnStart,
            column_span: columnSpan,
            row_start: rowStart,
            row_span: rowSpan,
        },
        overrides: {},
    };
}

function gridDocument() {
    return {
        revision: 1,
        active_page_id: 'main',
        pages: { main: { root_surface_id: 's1' } },
        surfaces: {
            s1: {
                surface_id: 's1',
                root_component_id: 'root',
                components: {
                    root: {
                        component_id: 'root',
                        type: 'PageShell',
                        kind: 'container',
                        children: ['grid'],
                        container_layout: gridLayout(),
                    },
                    grid: {
                        component_id: 'grid',
                        type: 'Grid',
                        kind: 'container',
                        children: ['card', 'btn'],
                        container_layout: gridLayout(),
                        placement: placed(1, 'full', 1),
                    },
                    card: {
                        component_id: 'card',
                        type: 'Card',
                        kind: 'container',
                        children: [],
                        container_layout: gridLayout(),
                        placement: placed(1, 4, 1),
                    },
                    btn: {
                        component_id: 'btn',
                        type: 'Button',
                        kind: 'leaf',
                        children: [],
                        placement: placed(5, 2, 1),
                    },
                },
            },
        },
    };
}

describe('flow-ui applyLayoutCommand placement.set', () => {
    it('writes wide band into base and bumps the revision', () => {
        const next = applyLayoutCommand(gridDocument(), {
            kind: 'placement.set',
            surfaceId: 's1',
            componentId: 'card',
            band: 'wide',
            patch: { column_start: 7, column_span: 4 },
        });
        expect(next.revision).toBe(2);
        expect(next.surfaces.s1.components.card.placement.base).toMatchObject({
            column_start: 7,
            column_span: 4,
        });
        expect(next.surfaces.s1.components.card.placement.overrides.wide).toBeUndefined();
    });

    it('writes narrower bands into overrides', () => {
        const next = applyLayoutCommand(gridDocument(), {
            kind: 'placement.set',
            surfaceId: 's1',
            componentId: 'card',
            band: 'medium',
            patch: { column_span: 3 },
        });
        expect(next.surfaces.s1.components.card.placement.overrides.medium).toEqual({
            column_span: 3,
        });
    });

    it('writes row_span as real grid tracks, without the legacy clamp flag', () => {
        const next = applyLayoutCommand(gridDocument(), {
            kind: 'placement.set',
            surfaceId: 's1',
            componentId: 'card',
            band: 'wide',
            patch: { row_span: 2 },
        });
        expect(next.surfaces.s1.components.card.placement.base.row_span).toBe(2);
        expect(next.surfaces.s1.components.card.placement.base.block_clamp).toBeUndefined();
    });

    it('clears shadowing overrides.wide keys when writing wide into base', () => {
        const document = gridDocument();
        document.surfaces.s1.components.btn.placement = placed(1, 2, 8);
        document.surfaces.s1.components.card.placement.overrides.wide = {
            column_span: 2,
            row_span: 5,
        };
        const next = applyLayoutCommand(document, {
            kind: 'placement.set',
            surfaceId: 's1',
            componentId: 'card',
            band: 'wide',
            patch: { column_span: 6 },
        });
        expect(next.surfaces.s1.components.card.placement.overrides.wide).toEqual({ row_span: 5 });
        expect(next.surfaces.s1.components.card.placement.base.column_span).toBe(6);
    });

    it('clamps narrow bands so start+span cannot overflow their column count', () => {
        const next = applyLayoutCommand(gridDocument(), {
            kind: 'placement.set',
            surfaceId: 's1',
            componentId: 'card',
            band: 'wide',
            patch: { column_start: 9, column_span: 4 },
        });
        expect(next.surfaces.s1.components.card.placement.overrides.medium).toEqual({
            column_start: 1,
            column_span: 'full',
        });
        expect(next.surfaces.s1.components.card.placement.overrides.compact).toEqual({
            column_start: 1,
            column_span: 'full',
        });
    });

    it('accepts a free cell next to an occupied sibling', () => {
        const next = applyLayoutCommand(gridDocument(), {
            kind: 'placement.set',
            surfaceId: 's1',
            componentId: 'card',
            band: 'wide',
            patch: { column_start: 7, column_span: 4, row_start: 1 },
        });
        expect(next.surfaces.s1.components.card.placement.base.column_start).toBe(7);
    });

    it('refuses cells taken by a sibling and leaves the document untouched', () => {
        const document = gridDocument();
        expect(() => applyLayoutCommand(document, {
            kind: 'placement.set',
            surfaceId: 's1',
            componentId: 'card',
            band: 'wide',
            patch: { column_start: 5, column_span: 4, row_start: 1 },
        })).toThrow(/are taken by btn/);
        expect(document.surfaces.s1.components.card.placement.base.column_start).toBe(1);
    });

    it('refuses a placement outside the parent grid', () => {
        expect(() => applyLayoutCommand(gridDocument(), {
            kind: 'placement.set',
            surfaceId: 's1',
            componentId: 'card',
            band: 'wide',
            patch: { column_start: 11, column_span: 4 },
        })).toThrow(/exceeds/);
    });

    it('refuses a non-integer row_start instead of guessing', () => {
        expect(() => applyLayoutCommand(gridDocument(), {
            kind: 'placement.set',
            surfaceId: 's1',
            componentId: 'card',
            band: 'wide',
            patch: { row_start: 'auto' },
        })).toThrow(/row_start must be an integer/);
    });

    it('locks the root surface component', () => {
        expect(() => applyLayoutCommand(gridDocument(), {
            kind: 'placement.set',
            surfaceId: 's1',
            componentId: 'root',
            band: 'wide',
            patch: { column_start: 2 },
        })).toThrow(/root placement cannot be changed/);
    });

    it('refuses children of a non-grid parent', () => {
        const document = gridDocument();
        document.surfaces.s1.components.grid.container_layout = { mode: 'flex', flex: {} };
        expect(() => applyLayoutCommand(document, {
            kind: 'placement.set',
            surfaceId: 's1',
            componentId: 'card',
            band: 'wide',
            patch: { column_start: 2 },
        })).toThrow(/not an authorable grid/);
    });

    it('refuses components the catalog does not let the author place', () => {
        const document = gridDocument();
        document.surfaces.s1.components.card.type = 'Modal';
        expect(() => applyLayoutCommand(document, {
            kind: 'placement.set',
            surfaceId: 's1',
            componentId: 'card',
            band: 'wide',
            patch: { column_start: 2 },
        })).toThrow(/rejects placement gestures/);
    });

    it('respects the per-type max column span from the catalog', () => {
        expect(() => applyLayoutCommand(gridDocument(), {
            kind: 'placement.set',
            surfaceId: 's1',
            componentId: 'btn',
            band: 'wide',
            patch: { column_span: 8 },
        })).toThrow(/column_span above max/);
    });
});

describe('flow-ui applyLayoutCommand children.move', () => {
    it('reparents into a container at the given index', () => {
        const next = applyLayoutCommand(gridDocument(), {
            kind: 'children.move',
            surfaceId: 's1',
            componentId: 'btn',
            targetParentId: 'card',
            index: 0,
        });
        expect(next.surfaces.s1.components.card.children).toEqual(['btn']);
        expect(next.surfaces.s1.components.grid.children).toEqual(['card']);
    });

    it('applies the drop cell in the new parent', () => {
        const next = applyLayoutCommand(gridDocument(), {
            kind: 'children.move',
            surfaceId: 's1',
            componentId: 'btn',
            targetParentId: 'card',
            index: 0,
            band: 'wide',
            patch: { column_start: 3, column_span: 2, row_start: 4, row_span: 1 },
        });
        expect(next.surfaces.s1.components.btn.placement.base).toMatchObject({
            column_start: 3,
            column_span: 2,
            row_start: 4,
        });
    });

    it('drops the moved component onto a free row of the new parent', () => {
        const document = gridDocument();
        document.surfaces.s1.components.card.children = ['inner'];
        document.surfaces.s1.components.inner = {
            component_id: 'inner',
            type: 'Text',
            kind: 'leaf',
            children: [],
            placement: placed(1, 'full', 1),
        };
        const next = applyLayoutCommand(document, {
            kind: 'children.move',
            surfaceId: 's1',
            componentId: 'btn',
            targetParentId: 'card',
            index: 1,
        });
        // `inner` holds row 1 full width, so the arriving button lands on row 2.
        expect(next.surfaces.s1.components.btn.placement.base.row_start).toBe(2);
    });

    it('refuses a cycle, a leaf target and the root', () => {
        expect(() => applyLayoutCommand(gridDocument(), {
            kind: 'children.move',
            surfaceId: 's1',
            componentId: 'grid',
            targetParentId: 'card',
            index: 0,
        })).toThrow(/cycle/);
        expect(() => applyLayoutCommand(gridDocument(), {
            kind: 'children.move',
            surfaceId: 's1',
            componentId: 'card',
            targetParentId: 'btn',
            index: 0,
        })).toThrow(/cannot receive children/);
        expect(() => applyLayoutCommand(gridDocument(), {
            kind: 'children.move',
            surfaceId: 's1',
            componentId: 'root',
            targetParentId: 'card',
            index: 0,
        })).toThrow(/root cannot be reparented/);
    });

    it('refuses a negative or non-integer index', () => {
        expect(() => applyLayoutCommand(gridDocument(), {
            kind: 'children.move',
            surfaceId: 's1',
            componentId: 'btn',
            targetParentId: 'card',
            index: -1,
        })).toThrow(/non-negative integer index/);
    });
});

describe('flow-ui applyLayoutCommand guards', () => {
    it('sets a container layout', () => {
        const next = applyLayoutCommand(gridDocument(), {
            kind: 'layout.set',
            surfaceId: 's1',
            componentId: 'card',
            layout: gridLayout(),
        });
        expect(next.surfaces.s1.components.card.container_layout.mode).toBe('grid');
    });

    it('rejects unknown commands, surfaces and targets', () => {
        expect(() => applyLayoutCommand(gridDocument(), {
            kind: 'children.reorder',
            surfaceId: 's1',
            componentId: 'card',
        })).toThrow(/unknown layout command/);
        expect(() => applyLayoutCommand(gridDocument(), {
            kind: 'placement.set',
            surfaceId: 'missing',
            componentId: 'card',
            patch: {},
        })).toThrow(/surface missing not found/);
        expect(() => applyLayoutCommand(gridDocument(), {
            kind: 'placement.set',
            surfaceId: 's1',
            componentId: 'ghost',
            patch: {},
        })).toThrow(/command target not found/);
    });

    it('never mutates the input document', () => {
        const document = gridDocument();
        const before = JSON.stringify(document);
        applyLayoutCommand(document, {
            kind: 'placement.set',
            surfaceId: 's1',
            componentId: 'card',
            band: 'wide',
            patch: { column_span: 3 },
        });
        expect(JSON.stringify(document)).toBe(before);
    });
});
