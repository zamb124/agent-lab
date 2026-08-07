/**
 * Dropping from the palette must always land, and the drag must show the layout the
 * author is about to get: the aimed cell plus where every sibling ends up.
 */

import { elementUpdated, expect, fixture, fixtureCleanup, html } from '../helpers/render.js';
import { createGridGeometry } from '@platform/lib/flow-ui/layout/grid-geometry.js';
import { occupiedAreas } from '@platform/lib/flow-ui/layout/grid-occupancy.js';
import {
    projectInsertPreview,
    proposeGridInsert,
} from '@platform/lib/flow-ui/layout/grid-insert.js';
import '@platform/lib/flow-ui/editor/selection-overlay.js';

function geometry() {
    return createGridGeometry({
        contentRect: { x: 16, y: 16, width: 1200, height: 800 },
        columns: 12,
        columnGap: 16,
        rowGap: 16,
    });
}

function stackedSurface() {
    const components = {
        root: { component_id: 'root', children: ['head', 'body'] },
        head: {
            component_id: 'head',
            placement: {
                base: { column_start: 1, column_span: 'full', row_start: 1, row_span: 1 },
                overrides: {},
            },
        },
        body: {
            component_id: 'body',
            placement: {
                base: { column_start: 1, column_span: 'full', row_start: 2, row_span: 1 },
                overrides: {},
            },
        },
    };
    return occupiedAreas({
        parent: components.root,
        components,
        band: 'wide',
        columns: 12,
        excludeComponentId: null,
    });
}

describe('flow-ui palette insert preview', () => {
    afterEach(() => fixtureCleanup());

    it('lands on a taken row and previews the siblings sliding down', () => {
        const geo = geometry();
        const occupied = stackedSurface();
        const aimed = geo.rectOf({ columnStart: 1, columnSpan: 1, rowStart: 1, rowSpan: 1 });
        const proposal = proposeGridInsert({
            geometry: geo,
            point: { x: aimed.x + 4, y: aimed.y + 4 },
            columnSpan: 'full',
            occupied,
        });

        expect(proposal.area.rowStart).to.equal(1);
        expect(proposal.shifted).to.deep.equal([
            { componentId: 'head', rowStart: 2 },
            { componentId: 'body', rowStart: 3 },
        ]);

        const preview = projectInsertPreview({ occupied, shifted: proposal.shifted });
        const headPreview = preview.find((item) => item.componentId === 'head');
        // The preview rect sits one row lower than where `head` renders today.
        expect(geo.rectOf(headPreview).y).to.equal(geo.rowOffset(2) + geo.contentRect.y);
    });

    it('renders the aimed cell and one preview outline per sibling', async () => {
        const geo = geometry();
        const occupied = stackedSurface();
        const proposal = proposeGridInsert({
            geometry: geo,
            point: { x: 20, y: 20 },
            columnSpan: 'full',
            occupied,
        });
        const previewRects = projectInsertPreview({ occupied, shifted: proposal.shifted })
            .map((item) => ({ componentId: item.componentId, rect: geo.rectOf(item) }));

        const overlay = await fixture(html`
            <flow-ui-selection-overlay
                .targetCell=${geo.rectOf(proposal.area)}
                .previewRects=${previewRects}
                interactive
            ></flow-ui-selection-overlay>
        `);
        await elementUpdated(overlay);
        expect(overlay.shadowRoot.querySelectorAll('.preview-cell')).to.have.length(2);
        const target = overlay.shadowRoot.querySelector('.target-cell');
        expect(target).to.exist;
        expect(target.dataset.valid).to.equal('true');
    });

    it('shows no preview outlines when the aimed row is free', async () => {
        const geo = geometry();
        const occupied = stackedSurface();
        const free = geo.rectOf({ columnStart: 1, columnSpan: 1, rowStart: 6, rowSpan: 1 });
        const proposal = proposeGridInsert({
            geometry: geo,
            point: { x: free.x + 4, y: free.y + 4 },
            columnSpan: 'full',
            occupied,
        });
        expect(proposal.shifted).to.deep.equal([]);

        const overlay = await fixture(html`
            <flow-ui-selection-overlay
                .targetCell=${geo.rectOf(proposal.area)}
                .previewRects=${[]}
                interactive
            ></flow-ui-selection-overlay>
        `);
        await elementUpdated(overlay);
        expect(overlay.shadowRoot.querySelectorAll('.preview-cell')).to.have.length(0);
    });
});
