import { describe, expect, it } from 'vitest';

import { assignExplicitGridRows } from '../../../../core/frontend/static/lib/flow-ui/layout/grid-normalize.js';

function grid(children) {
    const components = {
        root: {
            component_id: 'root',
            type: 'PageShell',
            kind: 'container',
            children: Object.keys(children),
            container_layout: {
                mode: 'grid',
                grid: { columns_by_band: { wide: 12, medium: 8, compact: 4 } },
            },
        },
    };
    for (const [id, base] of Object.entries(children)) {
        components[id] = { component_id: id, type: 'Card', children: [], placement: { base, overrides: {} } };
    }
    return { surface_id: 'main', root_component_id: 'root', components };
}

function rows(surface) {
    return Object.fromEntries(
        Object.entries(surface.components)
            .filter(([id]) => id !== 'root')
            .map(([id, component]) => [id, component.placement.base.row_start]),
    );
}

describe('flow-ui grid normalize', () => {
    it('assigns a row to every child left on auto', () => {
        const surface = grid({
            a: { column_start: 1, column_span: 'full', row_start: 'auto', row_span: 1 },
            b: { column_start: 1, column_span: 'full', row_start: 'auto', row_span: 1 },
            c: { column_start: 1, column_span: 'full', row_start: 'auto', row_span: 1 },
        });
        expect(assignExplicitGridRows(surface)).toBe(true);
        expect(rows(surface)).toEqual({ a: 1, b: 2, c: 3 });
    });

    it('keeps a two-up row side by side', () => {
        const surface = grid({
            left: { column_start: 1, column_span: 6, row_start: 'auto', row_span: 1 },
            right: { column_start: 7, column_span: 6, row_start: 'auto', row_span: 1 },
            below: { column_start: 1, column_span: 'full', row_start: 'auto', row_span: 1 },
        });
        assignExplicitGridRows(surface);
        expect(rows(surface)).toEqual({ left: 1, right: 1, below: 2 });
    });

    it('repairs a legacy pile where every child sits on row 1', () => {
        const surface = grid({
            card: { column_start: 1, column_span: 'full', row_start: 1, row_span: 1 },
            field: { column_start: 1, column_span: 'full', row_start: 1, row_span: 1 },
            area: { column_start: 1, column_span: 'full', row_start: 1, row_span: 2 },
        });
        expect(assignExplicitGridRows(surface)).toBe(true);
        expect(rows(surface)).toEqual({ card: 1, field: 2, area: 3 });
    });

    it('leaves an authored layout untouched and is idempotent', () => {
        const surface = grid({
            head: { column_start: 1, column_span: 'full', row_start: 1, row_span: 1 },
            left: { column_start: 1, column_span: 6, row_start: 2, row_span: 3 },
            right: { column_start: 7, column_span: 6, row_start: 2, row_span: 1 },
            foot: { column_start: 1, column_span: 'full', row_start: 9, row_span: 1 },
        });
        expect(assignExplicitGridRows(surface)).toBe(false);
        expect(rows(surface)).toEqual({ head: 1, left: 2, right: 2, foot: 9 });
    });

    it('settles after one pass even when it had to repair', () => {
        const surface = grid({
            a: { column_start: 1, column_span: 'full', row_start: 1, row_span: 2 },
            b: { column_start: 1, column_span: 6, row_start: 1, row_span: 1 },
            c: { column_start: 1, column_span: 6, row_start: 'auto', row_span: 1 },
        });
        assignExplicitGridRows(surface);
        expect(assignExplicitGridRows(surface)).toBe(false);
    });

    it('ignores non-grid containers', () => {
        const surface = grid({
            a: { column_start: 1, column_span: 'full', row_start: 1, row_span: 1 },
            b: { column_start: 1, column_span: 'full', row_start: 1, row_span: 1 },
        });
        surface.components.root.container_layout = { mode: 'flex', flex: {} };
        expect(assignExplicitGridRows(surface)).toBe(false);
        expect(rows(surface)).toEqual({ a: 1, b: 1 });
    });
});
