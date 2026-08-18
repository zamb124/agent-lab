/**
 * A grid element is exactly as tall as its content.
 *
 * The page shell fills the artboard, so without `align-content: start` the grid
 * would hand its free height to the rows and every card, form and field would look
 * stretched — and could not be made smaller, because shrinking `row_span` just
 * hands the space to the remaining rows.
 */

import { elementUpdated, expect, fixture, fixtureCleanup, html } from '../helpers/render.js';
import { collectFlowUIInspection } from '@platform/lib/flow-ui/rendering/renderer-inspection-bridge.js';
import '@platform/lib/flow-ui/components/platform-flow-ui.js';

const GRID_LAYOUT = Object.freeze({
    mode: 'grid',
    grid: Object.freeze({
        columns_by_band: Object.freeze({ compact: 4, medium: 8, wide: 12 }),
        column_gap_token: 'space.4',
        row_gap_token: 'space.4',
        outer_padding_inline_token: 'space.4',
        outer_padding_block_token: 'space.4',
        max_content_width_token: null,
        auto_rows: 'content',
        auto_flow: 'row',
        align_items: 'stretch',
        justify_items: 'stretch',
        baseline_step_token: 'space.1',
    }),
    stack: null,
    flex: null,
});

function cell(column, span, row, rowSpan = 1) {
    return {
        base: {
            column_start: column,
            column_span: span,
            row_start: row,
            row_span: rowSpan,
            order: 0,
            align_self: 'auto',
            justify_self: 'auto',
        },
        overrides: {},
    };
}

function component(spec) {
    return {
        component_id: spec.component_id,
        type: spec.type,
        kind: spec.kind || 'leaf',
        children: spec.children || [],
        bindings: spec.bindings || {},
        properties: spec.properties || {},
        actions: {},
        container_layout: spec.container_layout || null,
        placement: spec.placement || cell(1, 'full', 1),
        visibility: null,
        checks: [],
        provenance: null,
    };
}

/** Page shell (fills the frame) with a form of two fields and a submit button. */
function formDocument() {
    return {
        document_id: 'doc-grid-height',
        context_id: 'ctx-grid-height',
        revision: 1,
        active_page_id: 'main',
        pages: { main: { page_id: 'main', title: 'Main', root_surface_id: 'main' } },
        surfaces: {
            main: {
                surface_id: 'main',
                root_component_id: 'root',
                components: {
                    root: component({
                        component_id: 'root',
                        type: 'PageShell',
                        kind: 'container',
                        children: ['login-form'],
                        container_layout: GRID_LAYOUT,
                    }),
                    'login-form': component({
                        component_id: 'login-form',
                        type: 'Form',
                        kind: 'container',
                        children: ['field-email', 'field-password', 'form-submit'],
                        container_layout: GRID_LAYOUT,
                        properties: { formId: 'login-form' },
                        placement: cell(1, 'full', 1),
                    }),
                    'field-email': component({
                        component_id: 'field-email',
                        type: 'TextField',
                        properties: { label: 'Email' },
                        bindings: { value: '/values/email' },
                        placement: cell(1, 'full', 1),
                    }),
                    'field-password': component({
                        component_id: 'field-password',
                        type: 'TextField',
                        properties: { label: 'Password' },
                        bindings: { value: '/values/password' },
                        placement: cell(1, 'full', 2),
                    }),
                    'form-submit': component({
                        component_id: 'form-submit',
                        type: 'Button',
                        properties: { label: 'Sign in', variant: 'primary' },
                        placement: cell(1, 3, 3),
                    }),
                },
                data_model: { content: {}, values: { email: '', password: '' }, system: {} },
                owner: 'platform',
                send_data_model: true,
            },
        },
        values: {},
    };
}

async function mount(uiDocument) {
    const host = await fixture(html`
        <div style="height:900px;width:1200px;display:flex;flex-direction:column;overflow:hidden">
            <platform-flow-ui
                style="flex:1 1 0;min-height:0;height:100%"
                display="page"
                profile="editor_test"
                theme="dark"
                locale="en"
                .initialDocument=${uiDocument}
            ></platform-flow-ui>
        </div>
    `);
    const flowUi = host.querySelector('platform-flow-ui');
    await new Promise((resolve) => setTimeout(resolve, 120));
    await elementUpdated(flowUi);
    const surface = flowUi.shadowRoot.querySelector('flow-ui-surface');
    await elementUpdated(surface);
    const find = (componentId) => surface.shadowRoot
        .querySelector(`[data-flow-ui-component="${componentId}"]`);
    find.inspect = (componentId) => collectFlowUIInspection(surface.shadowRoot)
        .find((entry) => entry.componentId === componentId);
    return find;
}

describe('flow-ui grid content height', () => {
    afterEach(() => fixtureCleanup());

    it('keeps a form as tall as the elements inside it', async () => {
        const find = await mount(formDocument());
        const shell = find('root');
        const form = find('login-form');
        expect(shell).to.exist;
        expect(form).to.exist;
        expect(getComputedStyle(shell).alignContent).to.equal('start');

        const shellHeight = shell.getBoundingClientRect().height;
        const formHeight = form.getBoundingClientRect().height;
        const contentHeight = ['field-email', 'field-password', 'form-submit']
            .reduce((total, id) => total + find(id).getBoundingClientRect().height, 0);
        // Two 16px row gaps between three rows, plus the form's 16px block padding.
        const expected = contentHeight + 2 * 16 + 2 * 16;

        expect(formHeight).to.be.closeTo(expected, 2);
        expect(formHeight).to.be.lessThan(shellHeight - 200);
    });

    it('a taller row_span reserves rows and a smaller one gives them back', async () => {
        const uiDocument = formDocument();
        uiDocument.surfaces.main.components['form-submit'].placement = cell(1, 3, 3, 4);
        const findTall = await mount(uiDocument);
        const tall = findTall('form-submit').getBoundingClientRect().height;
        fixtureCleanup();

        const findShort = await mount(formDocument());
        const short = findShort('form-submit').getBoundingClientRect().height;
        expect(tall).to.be.greaterThan(short);
        // Four baseline rows with three gaps between them.
        expect(tall).to.be.closeTo(4 * 48 + 3 * 16, 2);
    });

    it('reports the grid surface geometry to the editor', async () => {
        const find = await mount(formDocument());
        const form = find('login-form');
        const inspected = find.inspect('login-form');
        const grid = form.querySelector('.flow-grid');
        const surfaceRect = grid.getBoundingClientRect();
        const gridStyle = getComputedStyle(grid);
        const paddingLeft = Number.parseFloat(gridStyle.paddingLeft);
        const paddingRight = Number.parseFloat(gridStyle.paddingRight);
        const borderLeft = Number.parseFloat(gridStyle.borderLeftWidth);
        const borderRight = Number.parseFloat(gridStyle.borderRightWidth);
        // Tracks live in the CSS content box of the form surface, not the border box.
        expect(inspected.contentRect.x).to.be.closeTo(surfaceRect.x + borderLeft + paddingLeft, 1);
        expect(inspected.contentRect.width).to.be.closeTo(
            surfaceRect.width - borderLeft - borderRight - paddingLeft - paddingRight,
            1,
        );
        expect(inspected.rowGap).to.equal(16);
        expect(inspected.rowTracks.length).to.equal(3);
    });
});
