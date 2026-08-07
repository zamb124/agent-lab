import { describe, expect, it } from 'vitest';
import {
    cloneSubtree,
    collectSubtreeIds,
    defaultComponent,
    findParentId,
    materializeClipboard,
    removeSubtree,
    renameComponent,
    sanitizeClipboard,
    serializeClipboard,
    validateInterfaceDocument,
} from '../../../../apps/flows/ui/components/interface-editor/interface-editor-domain.js';
import { FLOW_UI_PAGE_TEMPLATE_CATEGORIES, FLOW_UI_PAGE_TEMPLATES, filterFlowUIPageTemplates } from '../../../../core/frontend/static/lib/flow-ui/templates/page-templates.js';

function documentWithSurface(components, dataModel = { content: {}, values: {}, system: {} }) {
    return {
        document_id: 'doc-1',
        catalog_id: 'https://linnex.io/a2ui/catalog/platform/v1',
        active_page_id: 'main',
        revision: 1,
        pages: {
            main: { page_id: 'main', title: { default: 'Main' }, route: '/', root_surface_id: 'main' },
        },
        surfaces: {
            main: {
                surface_id: 'main',
                root_component_id: 'root',
                components,
                data_model: dataModel,
            },
        },
        policy: {},
    };
}

function stackContainer(id, children) {
    const component = defaultComponent('Stack', id);
    component.children = children;
    return component;
}

describe('defaultComponent (manifest-driven)', () => {
    it('builds a container with a layout preset and manifest kind', () => {
        const grid = defaultComponent('Grid', 'grid-1');
        expect(grid.kind).toBe('container');
        expect(grid.container_layout.mode).toBe('grid');
        expect(grid.container_layout.grid.columns_by_band).toEqual({ compact: 4, medium: 8, wide: 12 });
        const section = defaultComponent('Section', 'section-1');
        expect(section.container_layout.mode).toBe('grid');
        // Grid-first authoring: every insertable container is a grid, Form included.
        const form = defaultComponent('Form', 'form-1');
        expect(form.container_layout.mode).toBe('grid');
    });

    it('applies manifest defaults with the component id substituted into bindings', () => {
        const field = defaultComponent('TextField', 'text-field-2', 'en');
        expect(field.kind).toBe('leaf');
        expect(field.bindings.value).toBe('/values/text-field-2');
        expect(field.properties.label).toBe('Field');
    });

    it('localizes defaults for ru', () => {
        const heading = defaultComponent('Heading', 'heading', 'ru');
        expect(heading.properties.text).toBe('Новый заголовок');
        expect(heading.properties.level).toBe(2);
    });

    it('materializes Submit as a primary Button wired to platform.ui.submit', () => {
        const submit = defaultComponent('Submit', 'submit');
        expect(submit.type).toBe('Button');
        expect(submit.properties.variant).toBe('primary');
        expect(submit.actions.press).toEqual({
            kind: 'event',
            name: 'platform.ui.submit',
            context: {},
        });
    });

    it('rejects a type outside the catalog', () => {
        expect(() => defaultComponent('Iframe', 'x')).toThrow(/unknown catalog type/);
    });
});

describe('subtree helpers', () => {
    const surface = () => ({
        root_component_id: 'root',
        components: {
            root: stackContainer('root', ['card']),
            card: stackContainer('card', ['label']),
            label: defaultComponent('Text', 'label'),
        },
    });

    it('collects ids depth-first and finds parents', () => {
        const target = surface();
        expect(collectSubtreeIds(target, 'card')).toEqual(['card', 'label']);
        expect(findParentId(target, 'label')).toBe('card');
        expect(findParentId(target, 'root')).toBe(null);
    });

    it('removes a subtree together with parent references', () => {
        const target = surface();
        removeSubtree(target, 'card');
        expect(Object.keys(target.components)).toEqual(['root']);
        expect(target.components.root.children).toEqual([]);
    });

    it('clones a subtree with fresh ids and remapped children', () => {
        const target = surface();
        const { rootId, components } = cloneSubtree(target, 'card');
        expect(rootId).not.toBe('card');
        const copy = components[rootId];
        expect(copy.children).toHaveLength(1);
        expect(copy.children[0]).not.toBe('label');
        expect(components[copy.children[0]].type).toBe('Text');
    });

    it('renames a component and rewires parent references', () => {
        const target = surface();
        renameComponent(target, 'label', 'headline');
        expect(target.components.headline.component_id).toBe('headline');
        expect(target.components.label).toBeUndefined();
        expect(target.components.card.children).toEqual(['headline']);
    });

    it('rejects invalid, duplicate and root renames', () => {
        const target = surface();
        expect(() => renameComponent(target, 'label', 'Bad Id')).toThrow(/invalid component id/);
        expect(() => renameComponent(target, 'label', 'card')).toThrow(/already exists/);
        expect(() => renameComponent(target, 'root', 'shell')).toThrow(/root component cannot be renamed/);
    });
});

describe('clipboard', () => {
    const surface = () => ({
        root_component_id: 'root',
        components: {
            root: stackContainer('root', ['card']),
            card: stackContainer('card', ['label']),
            label: defaultComponent('Text', 'label'),
        },
    });

    it('round-trips a versioned payload and materializes fresh ids', () => {
        const target = surface();
        const payload = serializeClipboard(target, ['card']);
        expect(payload.version).toBe('flow-ui-clipboard@1');
        expect(payload.roots).toEqual(['card']);

        const { roots, components } = materializeClipboard(target, payload);
        expect(roots).toHaveLength(1);
        expect(roots[0]).not.toBe('card');
        const pasted = components[roots[0]];
        expect(components[pasted.children[0]].type).toBe('Text');
    });

    it('rejects unknown versions and non-catalog types', () => {
        expect(() => sanitizeClipboard({ version: 'other', roots: ['a'], components: {} }))
            .toThrow(/unsupported clipboard payload/);
        expect(() => sanitizeClipboard({
            version: 'flow-ui-clipboard@1',
            roots: ['a'],
            components: { a: { component_id: 'a', type: 'Iframe', children: [] } },
        })).toThrow(/is not in the catalog/);
    });
});

describe('validateInterfaceDocument', () => {
    it('accepts a minimal document with a reachable submit', () => {
        const document = documentWithSurface({
            root: stackContainer('root', ['submit']),
            submit: defaultComponent('Submit', 'submit'),
        });
        expect(validateInterfaceDocument(document)).toEqual([]);
    });

    it('blocks a document without any submit', () => {
        const document = documentWithSurface({
            root: stackContainer('root', ['label']),
            label: defaultComponent('Text', 'label'),
        });
        const codes = validateInterfaceDocument(document).map((problem) => problem.code);
        expect(codes).toContain('submit.missing');
    });

    it('reports id mismatch, missing children and leaf children', () => {
        const leafWithChildren = defaultComponent('Text', 'label');
        leafWithChildren.children = ['ghost'];
        const document = documentWithSurface({
            root: stackContainer('root', ['label', 'submit']),
            label: leafWithChildren,
            submit: defaultComponent('Submit', 'submit'),
            stray: { ...defaultComponent('Text', 'other-id'), children: [] },
        });
        const codes = validateInterfaceDocument(document).map((problem) => problem.code);
        expect(codes).toContain('component.child_missing');
        expect(codes).toContain('component.leaf_children');
        expect(codes).toContain('component.id_mismatch');
    });

    it('rejects unknown catalog types and navigation targets that do not exist', () => {
        const link = defaultComponent('PageLink', 'link');
        link.properties = { pageId: 'ghost-page' };
        const document = documentWithSurface({
            root: stackContainer('root', ['link', 'submit', 'alien']),
            link,
            submit: defaultComponent('Submit', 'submit'),
            alien: { component_id: 'alien', type: 'Iframe', kind: 'leaf', children: [], properties: {}, bindings: {}, actions: {} },
        });
        const codes = validateInterfaceDocument(document).map((problem) => problem.code);
        expect(codes).toContain('navigation.target_missing');
        expect(codes).toContain('catalog.unknown_type');
    });

    it('flags grid placement that overflows a band', () => {
        const grid = defaultComponent('Grid', 'grid');
        grid.children = ['wide-card'];
        const card = defaultComponent('Card', 'wide-card');
        card.placement = {
            base: { column_start: 3, column_span: 4 },
            overrides: {},
        };
        const document = documentWithSurface({
            root: stackContainer('root', ['grid', 'submit']),
            grid,
            'wide-card': card,
            submit: defaultComponent('Submit', 'submit'),
        });
        const problems = validateInterfaceDocument(document)
            .filter((problem) => problem.code === 'layout.overflow');
        // compact band has 4 columns: 3 + 4 - 1 = 6 > 4
        expect(problems.length).toBeGreaterThan(0);
        expect(problems[0].componentId).toBe('wide-card');
    });

    it('warns about interactive controls without an accessible label', () => {
        const field = defaultComponent('TextField', 'field');
        field.properties = {};
        const document = documentWithSurface({
            root: stackContainer('root', ['field', 'submit']),
            field,
            submit: defaultComponent('Submit', 'submit'),
        });
        const problem = validateInterfaceDocument(document)
            .find((item) => item.code === 'a11y.label_missing');
        expect(problem?.severity).toBe('warning');
    });

    it('requires a reachable submit when the page has interactive inputs', () => {
        const modal = defaultComponent('Modal', 'modal');
        modal.children = ['submit'];
        const document = documentWithSurface({
            root: stackContainer('root', ['field']),
            field: defaultComponent('TextField', 'field'),
            modal,
            submit: defaultComponent('Submit', 'submit'),
        });
        const codes = validateInterfaceDocument(document).map((problem) => problem.code);
        expect(codes).toContain('submit.unreachable');
    });
});

describe('page templates', () => {
    it('every starter template publishes without blocking problems', () => {
        for (const template of FLOW_UI_PAGE_TEMPLATES) {
            const surface = template.buildSurface('main', 'en');
            const document = documentWithSurface(surface.components, surface.data_model);
            const blocking = validateInterfaceDocument(document)
                .filter((problem) => problem.severity === 'error');
            expect(blocking, `${template.template_id}: ${JSON.stringify(blocking)}`).toEqual([]);
        }
    });

    it('keeps stable template ids, versions and categories', () => {
        expect(FLOW_UI_PAGE_TEMPLATES.map((item) => item.template_id)).toEqual([
            'linnex.page.chat',
            'linnex.page.assistant_context',
            'linnex.page.lead_form',
            'linnex.page.login',
            'linnex.page.contact',
            'linnex.page.validated_form',
            'linnex.page.dashboard',
            'linnex.page.stats_overview',
            'linnex.page.task_list',
            'linnex.page.status_tracker',
            'linnex.page.product_detail',
            'linnex.page.purchase_complete',
            'linnex.page.user_profile',
            'linnex.page.event_detail',
            'linnex.page.notification_center',
            'linnex.page.blank',
        ]);
        for (const template of FLOW_UI_PAGE_TEMPLATES) {
            expect(template.version).toBe('1.0.0');
            expect(FLOW_UI_PAGE_TEMPLATE_CATEGORIES).toContain(template.category);
            expect(template.tags.length).toBeGreaterThan(0);
            expect(template.title.ru.length).toBeGreaterThan(0);
            expect(template.title.en.length).toBeGreaterThan(0);
        }
    });

    it('filters by category and query', () => {
        const forms = filterFlowUIPageTemplates({ category: 'forms', locale: 'en' });
        expect(forms.every((item) => item.category === 'forms')).toBe(true);
        expect(forms.map((item) => item.template_id)).toContain('linnex.page.login');

        const chatHits = filterFlowUIPageTemplates({ query: 'composer', locale: 'en' });
        expect(chatHits.map((item) => item.template_id)).toContain('linnex.page.chat');

        const empty = filterFlowUIPageTemplates({ query: 'zzz-no-such-template', locale: 'en' });
        expect(empty).toEqual([]);
    });
});
