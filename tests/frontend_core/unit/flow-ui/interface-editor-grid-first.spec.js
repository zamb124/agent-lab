import { describe, expect, it } from 'vitest';

import {
    createColumnsPreset,
    defaultComponent,
    normalizeAuthorContainersToGrid,
} from '../../../../apps/flows/ui/components/interface-editor/interface-editor-domain.js';
import { flowUIPaletteComponentEntries } from '../../../../core/frontend/static/lib/flow-ui/catalog/manifest.js';

describe('interface-editor grid-first defaults', () => {
    it('inserts all containers as grid', () => {
        for (const type of ['Section', 'Grid', 'Row', 'Column', 'List', 'Stack', 'Card', 'Form', 'PageShell']) {
            const component = defaultComponent(type, type.toLowerCase(), 'en');
            expect(component.kind).toBe('container');
            expect(component.container_layout.mode).toBe('grid');
        }
    });

    it('gives Button a compact column_span so horizontal justify is visible', () => {
        const button = defaultComponent('Button', 'btn', 'en');
        expect(button.placement.base.column_span).toBe(3);
        expect(button.placement.base.justify_self).toBe('auto');
    });

    it('builds Columns3 preset with equal spans', () => {
        const surface = { components: {} };
        const { rootId, components } = createColumnsPreset(3, surface, 'en');
        expect(components[rootId].type).toBe('Row');
        expect(components[rootId].container_layout.mode).toBe('grid');
        expect(components[rootId].children).toHaveLength(3);
        for (const childId of components[rootId].children) {
            expect(components[childId].type).toBe('Column');
            expect(components[childId].placement.base.column_span).toBe(4);
        }
    });

    it('normalizes stack/flex containers to grid idempotently', () => {
        const document = {
            surfaces: {
                main: {
                    components: {
                        root: {
                            component_id: 'root',
                            type: 'PageShell',
                            kind: 'container',
                            container_layout: {
                                mode: 'stack',
                                stack: { direction: 'vertical', gap_token: 'space.4', align: 'stretch' },
                                grid: null,
                                flex: null,
                            },
                            children: ['list'],
                        },
                        list: {
                            component_id: 'list',
                            type: 'List',
                            kind: 'container',
                            container_layout: {
                                mode: 'flex',
                                flex: {
                                    direction: 'column',
                                    wrap: false,
                                    gap_token: 'space.4',
                                    align_items: 'stretch',
                                    justify_content: 'start',
                                },
                                grid: null,
                                stack: null,
                            },
                            children: [],
                        },
                    },
                },
            },
        };
        expect(normalizeAuthorContainersToGrid(document)).toBe(true);
        expect(document.surfaces.main.components.root.container_layout.mode).toBe('grid');
        expect(document.surfaces.main.components.list.container_layout.mode).toBe('grid');
        expect(normalizeAuthorContainersToGrid(document)).toBe(false);
    });

    it('hides raw Row/Column/List/Stack/Grid from palette', () => {
        const types = new Set(flowUIPaletteComponentEntries().map((entry) => entry.type));
        for (const hidden of ['Row', 'Column', 'List', 'Stack', 'Grid']) {
            expect(types.has(hidden)).toBe(false);
        }
        expect(types.has('Section')).toBe(true);
        expect(types.has('Card')).toBe(true);
        expect(types.has('Divider')).toBe(true);
    });
});

describe('stretched row span migrate', () => {
    function documentWith(components) {
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
                            children: Object.keys(components),
                            container_layout: {
                                mode: 'grid',
                                grid: { columns_by_band: { wide: 12, medium: 8, compact: 4 } },
                            },
                        },
                        ...components,
                    },
                },
            },
        };
    }

    function child(type, base) {
        return {
            component_id: type.toLowerCase(),
            type,
            kind: type === 'Form' ? 'container' : 'leaf',
            children: [],
            container_layout: type === 'Form'
                ? { mode: 'grid', grid: { columns_by_band: { wide: 12, medium: 8, compact: 4 } } }
                : null,
            placement: { base, overrides: {} },
        };
    }

    it('collapses a span written from a stretched measurement', () => {
        const document = documentWith({
            form: child('Form', {
                column_start: 1, column_span: 'full', row_start: 1, row_span: 6, block_clamp: true,
            }),
        });
        expect(normalizeAuthorContainersToGrid(document)).toBe(true);
        const base = document.surfaces.main.components.form.placement.base;
        expect(base.row_span).toBe(1);
        expect(base.block_clamp).toBeUndefined();
        expect(normalizeAuthorContainersToGrid(document)).toBe(false);
    });

    it('keeps the author size of runtime-owned surfaces', () => {
        const document = documentWith({
            conversationfeed: child('ConversationFeed', {
                column_start: 1, column_span: 'full', row_start: 1, row_span: 9, block_clamp: true,
            }),
        });
        expect(normalizeAuthorContainersToGrid(document)).toBe(true);
        const base = document.surfaces.main.components.conversationfeed.placement.base;
        expect(base.row_span).toBe(9);
        expect(base.block_clamp).toBeUndefined();
    });

    it('leaves a deliberate span without the legacy flag alone', () => {
        const document = documentWith({
            card: child('Card', { column_start: 1, column_span: 6, row_start: 1, row_span: 4 }),
        });
        expect(normalizeAuthorContainersToGrid(document)).toBe(false);
        expect(document.surfaces.main.components.card.placement.base.row_span).toBe(4);
    });
});
