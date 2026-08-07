import { describe, expect, it } from 'vitest';

import {
    FLOW_UI_DEFAULT_COLUMNS,
    resolvedPlacement,
    validateGridPlacement,
} from '../../../../core/frontend/static/lib/flow-ui/layout/grid-contract.js';
import {
    containerLayoutStyle,
    gridRowCount,
    placementStyle,
    tokenValue,
} from '../../../../core/frontend/static/lib/flow-ui/layout/layout-resolver.js';

describe('flow-ui layout resolver', () => {
    it('resolves placement overrides per band without inventing missing values', () => {
        const placement = {
            base: { column_start: 1, column_span: 4, row_span: 1 },
            overrides: {
                compact: { column_span: 2 },
                wide: { column_start: 3, column_span: 'full' },
            },
        };
        expect(resolvedPlacement(placement, 'compact')).toEqual({
            column_start: 1,
            column_span: 2,
            row_span: 1,
        });
        expect(resolvedPlacement(placement, 'medium')).toEqual({
            column_start: 1,
            column_span: 4,
            row_span: 1,
        });
        expect(resolvedPlacement(placement, 'wide')).toEqual({
            column_start: 3,
            column_span: 'full',
            row_span: 1,
        });
    });

    it('rejects invalid column span and start against band columns', () => {
        expect(validateGridPlacement({ column_span: 13 }, 12)).toMatch(/exceeds 12 columns/);
        expect(validateGridPlacement({ column_span: 2, column_start: 0 }, 8)).toMatch(
            /outside 8 columns/
        );
        expect(validateGridPlacement({ column_span: 'full', column_start: 'auto' }, 4)).toBeNull();
        expect(FLOW_UI_DEFAULT_COLUMNS).toEqual({ compact: 4, medium: 8, wide: 12 });
    });

    it('emits CSS variables for grid container and placement bands', () => {
        const gridStyle = containerLayoutStyle({
            mode: 'grid',
            grid: {
                columns_by_band: FLOW_UI_DEFAULT_COLUMNS,
                column_gap_token: 'space.4',
                row_gap_token: 'space.4',
                outer_padding_inline_token: 'space.4',
                outer_padding_block_token: 'space.4',
                max_content_width_token: 'content.wide',
                align_items: 'stretch',
                justify_items: 'stretch',
            },
        });
        expect(gridStyle).toContain('display:grid');
        expect(gridStyle).toContain('width:100%');
        expect(gridStyle).toContain('grid-template-columns:repeat(12,minmax(0,1fr))');
        expect(gridStyle).toContain('--flow-ui-cols-compact:4');
        expect(gridStyle).toContain('--flow-ui-cols-medium:8');
        expect(gridStyle).toContain('--flow-ui-cols-wide:12');
        expect(gridStyle).toContain(`column-gap:${tokenValue('space.4')}`);
        // A row is one baseline tall and grows with its content: a card can never
        // spill over the row below it.
        expect(gridStyle).toContain('grid-template-rows:repeat(1,minmax(48px,auto))');
        expect(gridStyle).toContain('grid-auto-rows:minmax(48px,auto)');
        expect(gridStyle).not.toContain('grid-auto-rows:48px');
        // A container taller than its rows must not stretch them: an element occupies
        // exactly its content height and stays shrinkable.
        expect(gridStyle).toContain('align-content:start');
        expect(containerLayoutStyle({
            mode: 'grid',
            grid: { columns_by_band: FLOW_UI_DEFAULT_COLUMNS },
        }, 5)).toContain('grid-template-rows:repeat(5,minmax(48px,auto))');

        const flexStyle = containerLayoutStyle({
            mode: 'flex',
            flex: { direction: 'column', gap_token: 'space.0' },
        });
        expect(flexStyle).toContain('display:flex');
        expect(flexStyle).toContain('width:100%');
        expect(flexStyle).toContain('flex-direction:column');

        const style = placementStyle({
            base: { column_start: 2, column_span: 3, row_span: 2, order: 1 },
            overrides: { compact: { column_span: 'full' }, wide: { row_span: 2 } },
        });
        expect(style).toContain('--flow-ui-column-compact:1 / -1');
        expect(style).toContain('--flow-ui-column-wide:2 / span 3');
        expect(style).toContain('--flow-ui-row-wide:auto');
        expect(style).toContain('--flow-ui-max-block-wide:96px');
        expect(style).toContain('--flow-ui-order-wide:1');
    });

    it('does not emit max-block for template default row_span without override', () => {
        const style = placementStyle({
            base: { column_span: 'full', row_span: 1 },
            overrides: {},
        });
        expect(style).toContain('--flow-ui-max-block-wide:none');
        expect(style).toContain('--flow-ui-row-wide:auto');
    });

    it('emits grid-row span only when row_start is explicit', () => {
        const style = placementStyle({
            base: { row_start: 2, row_span: 3 },
            overrides: {},
        });
        expect(style).toContain('--flow-ui-row-wide:2 / span 3');
    });
});

describe('flow-ui grid row count', () => {
    it('covers the last row a child occupies', () => {
        const components = {
            grid: { component_id: 'grid', container_layout: { mode: 'grid' }, children: ['a', 'b'] },
            a: { component_id: 'a', placement: { base: { row_start: 1, row_span: 2 }, overrides: {} } },
            b: { component_id: 'b', placement: { base: { row_start: 4, row_span: 3 }, overrides: {} } },
        };
        expect(gridRowCount(components.grid, components)).toBe(6);
    });

    it('is one for an empty grid and for non-grid containers', () => {
        const empty = { container_layout: { mode: 'grid' }, children: [] };
        expect(gridRowCount(empty, {})).toBe(1);
        expect(gridRowCount({ container_layout: { mode: 'flex' }, children: ['a'] }, {})).toBe(1);
    });
});
