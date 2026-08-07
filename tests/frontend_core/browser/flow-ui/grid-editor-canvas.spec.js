/**
 * Browser: the grid editor canvas resolves one geometry from the rendered content
 * box and refuses occupied cells. Loading the host here also links the whole
 * editor module graph (canvas, gesture, geometry, occupancy, overlays).
 */

import { expect } from '../helpers/render.js';
import { createGridGeometry } from '@platform/lib/flow-ui/layout/grid-geometry.js';
import { occupiedAreas } from '@platform/lib/flow-ui/layout/grid-occupancy.js';
import { proposeGridMove } from '@platform/lib/flow-ui/editor/layout-gesture.js';
import { effectiveParentMode, resolveInteractionPolicy } from '@platform/lib/flow-ui/editor/layout-capabilities.js';
import { applyLayoutCommand } from '@platform/lib/flow-ui/editor/layout-domain-commands.js';
import '../../../../apps/flows/ui/components/interface-editor/flows-interface-canvas.js';
import '../../../../apps/flows/ui/components/interface-editor/flows-interface-palette.js';
import '@platform/lib/flow-ui/editor/layout-grid-overlay.js';
import '@platform/lib/flow-ui/editor/selection-overlay.js';

function document12() {
    return {
        revision: 1,
        active_page_id: 'main',
        pages: { main: { root_surface_id: 'main' } },
        surfaces: {
            main: {
                surface_id: 'main',
                root_component_id: 'root',
                components: {
                    root: {
                        component_id: 'root',
                        type: 'PageShell',
                        kind: 'container',
                        children: ['left', 'mover'],
                        container_layout: {
                            mode: 'grid',
                            grid: { columns_by_band: { wide: 12, medium: 8, compact: 4 } },
                        },
                    },
                    left: {
                        component_id: 'left',
                        type: 'Card',
                        kind: 'container',
                        children: [],
                        placement: {
                            base: {
                                column_start: 1, column_span: 6, row_start: 1, row_span: 1,
                            },
                            overrides: {},
                        },
                    },
                    mover: {
                        component_id: 'mover',
                        type: 'Card',
                        kind: 'container',
                        children: [],
                        placement: {
                            base: {
                                column_start: 1, column_span: 6, row_start: 3, row_span: 1,
                            },
                            overrides: {},
                        },
                    },
                },
            },
        },
    };
}

describe('flow-ui grid editor canvas', () => {
    it('registers the editor custom elements', () => {
        expect(customElements.get('flows-interface-canvas')).to.exist;
        expect(customElements.get('flows-interface-palette')).to.exist;
        expect(customElements.get('flow-ui-layout-grid-overlay')).to.exist;
        expect(customElements.get('flow-ui-selection-overlay')).to.exist;
    });

    it('locks children of a conversation PageShell (runtime-owned geometry)', () => {
        const surface = document12().surfaces.main;
        surface.components.root.properties = { presentation: 'conversation' };
        expect(effectiveParentMode(surface.components.root, surface.components)).to.equal('none');
        const policy = resolveInteractionPolicy({
            component: surface.components.mover,
            parent: surface.components.root,
            rootComponentId: 'root',
            components: surface.components,
        });
        expect(policy.canMove).to.equal(false);
        expect(policy.handles).to.deep.equal([]);
    });

    it('locks children of the composer bar', () => {
        const surface = document12().surfaces.main;
        surface.components.root.properties = { presentation: 'composer' };
        expect(effectiveParentMode(surface.components.root)).to.equal('none');
        expect(resolveInteractionPolicy({
            component: surface.components.mover,
            parent: surface.components.root,
            rootComponentId: 'root',
        }).canMove).to.equal(false);
    });

    it('lands in a free cell and refuses an occupied one, end to end', () => {
        const surface = document12().surfaces.main;
        const geometry = createGridGeometry({
            contentRect: { x: 16, y: 16, width: 1200, height: 800 },
            columns: 12,
            columnGap: 16,
            rowGap: 16,
        });
        const occupied = occupiedAreas({
            parent: surface.components.root,
            components: surface.components,
            band: 'wide',
            columns: 12,
            excludeComponentId: 'mover',
        });
        const startRect = geometry.rectOf({
            columnStart: 1, columnSpan: 6, rowStart: 3, rowSpan: 1,
        });
        const base = {
            geometry,
            startRect,
            pointerStart: { x: 400, y: 400 },
            placement: surface.components.mover.placement,
            band: 'wide',
            policy: resolveInteractionPolicy({
                component: surface.components.mover,
                parent: surface.components.root,
                rootComponentId: 'root',
            }),
            occupied,
        };

        const beside = proposeGridMove({
            ...base,
            pointerNow: { x: 400 + geometry.columnStep * 6, y: 400 - geometry.rowStep * 2 },
        });
        expect(beside.valid).to.equal(true);
        const applied = applyLayoutCommand(document12(), {
            kind: 'placement.set',
            surfaceId: 'main',
            componentId: 'mover',
            band: 'wide',
            patch: beside.patch,
        });
        expect(applied.surfaces.main.components.mover.placement.base.column_start).to.equal(7);
        expect(applied.surfaces.main.components.mover.placement.base.row_start).to.equal(1);

        const onTop = proposeGridMove({
            ...base,
            pointerNow: { x: 400, y: 400 - geometry.rowStep * 2 },
        });
        expect(onTop.valid).to.equal(false);
        expect(Object.keys(onTop.patch)).to.have.length(0);
    });
});
