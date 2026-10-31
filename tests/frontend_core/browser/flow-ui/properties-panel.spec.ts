/**
 * Панель «Свойства»: у каждого блока грамматики есть редактор для каждого свойства (виды из JSON
 * Schema), изменения уходят событием ``property-change`` в форме, которую ждёт документ
 * (``null`` для пустых необязательных путей, типизированные enum, JSON-литералы условий),
 * проблемы блока показываются у своего свойства, кнопки блока шлют ``block-action``.
 */

import { elementUpdated, expect, fixture, fixtureCleanup, html, oneEvent } from '../helpers/render.js';
import { bootstrapTestBus, resetPlatformState } from '../helpers/reset.js';
import { installFetchMock } from '../helpers/fake-fetch.js';
import { CoreEvents, getPlatformBus } from '@platform/lib/events/index.js';
import { secretsVariablesResource } from '@platform/lib/events/resources/secrets-variables.resource.js';
import flowsEn from '../../../../core/i18n/translations/en/flows.json' with { type: 'json' };
import schema from '../../../fixtures/flow_ui/schema.json' with { type: 'json' };
import {
    blockCatalog,
    catalogEntry,
    defaultBlock,
    frozenStateFields,
} from '../../../../apps/flows/ui/_helpers/interface-editor-domain.js';
import '../../../../apps/flows/ui/components/interface-editor/flows-interface-properties-panel.js';
import {q, qs, qsa, type TestEl} from '../helpers/dom.js';
import type { FlowUiBlock, FlowUiPage } from '../../../../apps/flows/ui/_helpers/interface-editor-domain.js';

const catalog = blockCatalog(schema);
const frozen = frozenStateFields(schema);
const labels = {
    tab: flowsEn.interface_editor.default_tab,
    option: flowsEn.interface_editor.default_option,
    text: (type: string, property: string): string => (flowsEn.interface_editor as Record<string, string>)[`default_text_${type}_${property}`] ?? '',
};
const T = flowsEn.interface_editor;

function seedTranslations(bus: any) {
    const locale = bus.getState().i18n.locale;
    const previous = bus.getState().i18n.translations[locale] || {};
    bus.dispatch(CoreEvents.I18N_LOCALE_LOADED, { locale, bundle: { ...previous, flows: flowsEn } }, { source: 'system' });
    bus.dispatch(CoreEvents.I18N_LOCALE_CHANGED, { locale, default_namespace: 'flows' }, { source: 'system' });
}

function pageWith(blocks: any) {
    return { page_id: 'main', title: 'Main', blocks };
}

async function mountPanel(block: FlowUiBlock | null, { page = null, pages = null, problems = [], statePaths = [], sampleState = {}, width = 360 }: { page?: FlowUiPage | null; pages?: FlowUiPage[] | null; problems?: unknown[]; statePaths?: Array<{ path: string; protected: boolean }>; sampleState?: Record<string, unknown>; width?: number } = {}) {
    const resolvedPage = page ?? pageWith(block === null ? [] : [block]);
    const document = { start_page_id: 'main', pages: pages ?? [resolvedPage] };
    const element = await fixture<TestEl>(html`<flows-interface-properties-panel
        .block=${block} .page=${resolvedPage} .document=${document} .catalog=${catalog} .schema=${schema}
        .frozen=${frozen} .statePaths=${statePaths} .sampleState=${sampleState} .problems=${problems}
        style=${`display:block;width:${width}px`}
    ></flows-interface-properties-panel>`);
    await elementUpdated(element);
    return element;
}

function fields(element: any) {
    return [...qsa(element.renderRoot, 'platform-field, platform-variable-input')];
}

function fieldByLabel(element: any, label: any) {
    const match = fields(element).find((field) => field.label === label);
    if (!match) throw new Error(`no field labelled ${JSON.stringify(label)}`);
    return match;
}

function fieldChanged(element: any, field: any, value: any) {
    const listened = oneEvent(element, 'property-change');
    field.dispatchEvent(new CustomEvent('change', { detail: { value }, bubbles: true, composed: true }));
    return listened.then((event) => (event as CustomEvent).detail);
}

function buttonByText(element: any, text: any) {
    const match = [...qsa(element.renderRoot, 'platform-button')].find((button) => button.textContent.trim() === text);
    if (!match) throw new Error(`no button ${JSON.stringify(text)}`);
    return match;
}

describe('flows-interface-properties-panel', function () {
    this.timeout(20_000);

    let fetchMock: any;

    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus({ factories: [secretsVariablesResource] });
        seedTranslations(getPlatformBus());
        fetchMock = installFetchMock();
        fetchMock.respondJson('GET', (url: string) => url.includes('/secrets/api/v1/variables'), { items: [], total: 0, limit: 200, offset: 0 });
    });

    afterEach(() => {
        fetchMock.uninstall();
        fixtureCleanup();
    });

    it('has an editor for every property of every grammar block', async () => {
        for (const entry of catalog) {
            const block = defaultBlock(entry, `b-${entry.type}`, labels);
            const element = await mountPanel(block);
            expect(qs(element.renderRoot, '.head .type').textContent, entry.type).to.equal((T as Record<string, string>)[`block_${entry.type}`]);
            const visible = entry.properties.filter((property) => !['type', 'blocks', 'block_id'].includes(property.name) && property.kind !== 'const' && property.kind !== 'blocks');
            const folded = entry.type === 'button' ? ['action', 'page_id', 'url'] : entry.type === 'link' ? ['page_id', 'url'] : [];
            const foldedVisible = visible.filter((property) => folded.includes(property.name)).length;
            const rendered = qs(element.renderRoot, '.fields').children.length;
            expect(rendered, `${entry.type}: editors`).to.be.greaterThanOrEqual(1 + visible.length - Math.max(0, foldedVisible - 1));
            expect(fieldByLabel(element, T.prop_block_id)!.value).to.equal(`b-${entry.type}`);
            fixtureCleanup();
        }
    });

    it('shows the empty state and the page contract without a selected block', async () => {
        const page = pageWith([
            { block_id: 'email', type: 'text_input', visible_when: null, field: 'email', label: 'Email', required: true, error_message: '', action: { name: 'quick', payload: {} }, placeholder: '', default: '', pattern: '', multiline: false, secret: false },
            { block_id: 'send', type: 'button', visible_when: null, label: 'Send', action: { name: 'submit', payload: {} }, variant: 'primary' },
            { block_id: 'rows', type: 'data_table', visible_when: null, rows: 'items', file_id: '', columns: [], row_action: { name: 'open_row', payload: {} } },
        ]);
        const element = await mountPanel(null, { page });
        expect(qs(element.renderRoot, '.head .type').textContent).to.equal(T.page_properties);
        expect(fieldByLabel(element, T.page_title)!.value).to.equal('Main');
        expect(fieldByLabel(element, T.page_show_title)!.value).to.equal(true);
        const hidden = oneEvent(element, 'page-property-change');
        fieldByLabel(element, T.page_show_title)!.dispatchEvent(new CustomEvent('change', { detail: { value: false }, bubbles: true, composed: true }));
        expect((await hidden).detail).to.deep.equal({ property: 'show_title', value: false });
        const contract = qs(element.renderRoot, '.contract');
        expect([...qsa(contract!, 'code')].map((code) => code.textContent)).to.deep.equal(['email', 'quick', 'submit', 'open_row']);
    });

    it('emits typed property changes for templates, paths, enums, numbers and lists', async () => {
        const block = { ...defaultBlock(catalogEntry(catalog, 'text_input'), 'name', labels), field: 'name', label: 'Name', required: false };
        const element = await mountPanel(block, { statePaths: [{ path: 'customer.name', protected: false }, { path: 'task_id', protected: true }] });
        expect(await fieldChanged(element, fieldByLabel(element, T.prop_label), 'Hi {customer.name}')).to.deep.equal({ blockId: 'name', property: 'label', value: 'Hi {customer.name}' });
        expect(fieldByLabel(element, T.prop_label)!.statePaths).to.deep.equal(['customer.name']);
        // Обязательный path остаётся строкой, необязательный пустой становится null
        expect(await fieldChanged(element, fieldByLabel(element, T.prop_field), '')).to.deep.equal({ blockId: 'name', property: 'field', value: '' });
        expect(await fieldChanged(element, fieldByLabel(element, T.prop_required), true)).to.deep.equal({ blockId: 'name', property: 'required', value: true });
        expect(fieldByLabel(element, T.prop_field)!.hint).to.equal(T.field_hint.replaceAll('{path}', 'name'));

        const heading = await mountPanel(defaultBlock(catalogEntry(catalog, 'heading'), 'h', labels));
        expect(await fieldChanged(heading, fieldByLabel(heading, T.prop_level), '3')).to.deep.equal({ blockId: 'h', property: 'level', value: 3 });

        const select = { ...defaultBlock(catalogEntry(catalog, 'select'), 'plan', labels), multiple: false };
        const selectPanel = await mountPanel(select);
        expect(await fieldChanged(selectPanel, fieldByLabel(selectPanel, T.prop_default), '')).to.deep.equal({ blockId: 'plan', property: 'default', value: null });
        expect(await fieldChanged(selectPanel, fieldByLabel(selectPanel, T.prop_default), 'pro')).to.deep.equal({ blockId: 'plan', property: 'default', value: 'pro' });

        const upload = { ...defaultBlock(catalogEntry(catalog, 'file_upload'), 'docs', labels) };
        const uploadPanel = await mountPanel(upload);
        expect(await fieldChanged(uploadPanel, fieldByLabel(uploadPanel, T.prop_accept), ['.pdf', 'image/*'])).to.deep.equal({ blockId: 'docs', property: 'accept', value: ['.pdf', 'image/*'] });

        const media = await mountPanel(defaultBlock(catalogEntry(catalog, 'image'), 'img', labels));
        expect(await fieldChanged(media, fieldByLabel(media, T.prop_url), 'https://x/{id}.png')).to.deep.equal({ blockId: 'img', property: 'url', value: 'https://x/{id}.png' });
    });

    it('toggles actions and conditions and parses condition literals', async () => {
        const block = { ...defaultBlock(catalogEntry(catalog, 'text_input'), 'q', labels), action: null, visible_when: null };
        const element = await mountPanel(block);
        const toggles = [...qsa(element.renderRoot, '.sub-title platform-field[type="boolean"]')];
        expect(toggles.length).to.be.greaterThanOrEqual(2);
        const actionToggle = toggles.find((toggle) => qs(toggle!.closest('.sub')!, '.sub-title span').textContent === T.prop_action);
        expect(await fieldChanged(element, actionToggle, true)).to.deep.equal({ blockId: 'q', property: 'action', value: { name: 'submit', payload: {} } });

        element.block = { ...block, action: { name: 'submit', payload: {} } };
        await elementUpdated(element);
        expect(await fieldChanged(element, fieldByLabel(element, T.action_name), 'search')).to.deep.equal({ blockId: 'q', property: 'action', value: { name: 'search', payload: {} } });
        expect(await fieldChanged(element, fieldByLabel(element, T.action_payload), { limit: 5 })).to.deep.equal({ blockId: 'q', property: 'action', value: { name: 'submit', payload: { limit: 5 } } });

        const conditionToggle = [...qsa(element.renderRoot, '.sub-title platform-field[type="boolean"]')]
            .find((toggle) => qs(toggle!.closest('.sub')!, '.sub-title span').textContent === T.prop_visible_when);
        expect(await fieldChanged(element, conditionToggle, true)).to.deep.equal({ blockId: 'q', property: 'visible_when', value: { path: 'status' } });
        expect(await fieldChanged(element, conditionToggle, false)).to.deep.equal({ blockId: 'q', property: 'visible_when', value: null });

        element.block = { ...block, visible_when: { path: 'status', equals: 'done' } };
        await elementUpdated(element);
        expect(fieldByLabel(element, T.condition_equals)!.value).to.equal('done');
        const cases = [
            ['42', 42], ['-1.5', -1.5], ['true', true], ['null', null], ['{"a":1}', { a: 1 }], ['[1,2]', [1, 2]], [' done ', 'done'],
        ];
        for (const [typed, parsed] of cases) {
            expect(await fieldChanged(element, fieldByLabel(element, T.condition_equals), typed), String(typed)).to.deep.equal({ blockId: 'q', property: 'visible_when', value: { path: 'status', equals: parsed } });
        }
        expect(await fieldChanged(element, fieldByLabel(element, T.condition_equals), '   ')).to.deep.equal({ blockId: 'q', property: 'visible_when', value: { path: 'status' } });
        expect(await fieldChanged(element, fieldByLabel(element, T.condition_path), 'order.paid')).to.deep.equal({ blockId: 'q', property: 'visible_when', value: { path: 'order.paid', equals: 'done' } });
    });

    it('edits options, columns, tabs and html height with the container guards', async () => {
        const select = defaultBlock(catalogEntry(catalog, 'select'), 'plan', labels);
        const element = await mountPanel(select);
        const optionsBox = [...qsa(element.renderRoot, '.sub')].find((box) => qs(box!, '.sub-title span').textContent === T.prop_options);
        const addListened = oneEvent(element, 'property-change');
        qs(optionsBox!, 'platform-button').click();
        expect((await addListened).detail.value).to.deep.equal([...(select.options as Array<{ value: string; label: string }>), { value: 'value_3', label: '' }]);
        const rows = qsa(optionsBox!, '.row');
        expect(rows).to.have.length(2);
        const removeListened = oneEvent(element, 'property-change');
        qs(rows[0]!, 'platform-button').click();
        expect((await removeListened).detail.value).to.deep.equal([(select.options as Array<{ value: string; label: string }>)[1]]);
        const [valueField] = qsa(rows[1]!, 'platform-field');
        const opts = select.options as Array<{ value: string; label: string }>;
        expect(await fieldChanged(element, valueField, 'enterprise')).to.deep.equal({ blockId: 'plan', property: 'options', value: [opts[0], { ...opts[1], value: 'enterprise' }] });

        const columns = { ...defaultBlock(catalogEntry(catalog, 'columns'), 'cols', labels), columns: [{ width: 8, blocks: [{ block_id: 'x', type: 'divider', visible_when: null }] }, { width: 4, blocks: [] }] };
        const columnsPanel = await mountPanel(columns);
        const columnRows = qsa(columnsPanel.renderRoot, '.row');
        expect(qs(columnRows[0]!, 'platform-button').hasAttribute('disabled'), 'column with blocks cannot be removed').to.equal(true);
        expect(qs(columnRows[1]!, 'platform-button').hasAttribute('disabled')).to.equal(false);
        expect(qs(columnRows[0]!, '.hint').textContent).to.equal(T.column_blocks.replace('{count}', '1'));
        expect(await fieldChanged(columnsPanel, qs(columnRows[1]!, 'platform-field'), 6)).to.deep.equal({ blockId: 'cols', property: 'columns', value: [columns.columns[0], { width: 6, blocks: [] }] });

        const four = { ...columns, columns: [1, 2, 3, 4].map(() => ({ width: 3, blocks: [] })) };
        const fourPanel = await mountPanel(four);
        expect(qs(fourPanel.renderRoot, '.sub-title platform-button').hasAttribute('disabled'), 'max four columns').to.equal(true);

        const tabs = defaultBlock(catalogEntry(catalog, 'tabs'), 'tabs', labels);
        const tabsPanel = await mountPanel(tabs);
        const addTab = oneEvent(tabsPanel, 'property-change');
        qs(tabsPanel.renderRoot, '.sub-title platform-button').click();
        expect((await addTab).detail.value).to.deep.equal([...(tabs.tabs as unknown[]), { title: T.default_tab, blocks: [] }]);

        const htmlBlock = defaultBlock(catalogEntry(catalog, 'html'), 'card', labels);
        const htmlPanel = await mountPanel(htmlBlock);
        const heightBox = [...qsa(htmlPanel.renderRoot, '.sub')].find((box) => qs(box!, '.sub-title span').textContent === T.prop_height);
        expect(await fieldChanged(htmlPanel, qs(heightBox!, 'platform-field'), false)).to.deep.equal({ blockId: 'card', property: 'height', value: 320 });
        htmlPanel.block = { ...htmlBlock, height: 320 };
        await elementUpdated(htmlPanel);
        const heightBoxFixed = [...qsa(htmlPanel.renderRoot, '.sub')].find((box) => qs(box!, '.sub-title span').textContent === T.prop_height);
        expect(await fieldChanged(htmlPanel, qsa(heightBoxFixed!, 'platform-field')[1], 480)).to.deep.equal({ blockId: 'card', property: 'height', value: 480 });
        expect(q(htmlPanel.renderRoot, '.html-preview')).to.exist;
        expect(q(htmlPanel.renderRoot, '.html-source platform-code-editor')).to.equal(null);
        expect(q(htmlPanel.renderRoot, '.html-open')).to.exist;
        expect(qs(htmlPanel.renderRoot, '.html-open').textContent).to.contain(T.html_open_editor);
        expect(qs(htmlPanel.renderRoot, '.head').nextElementSibling!.classList.contains('html-open')).to.equal(true);
        expect(q(htmlPanel.renderRoot, '.html-source platform-button')).to.equal(null);
    });

    it('opens the html editor from the top control for the selected block', async () => {
        const htmlBlock = defaultBlock(catalogEntry(catalog, 'html'), 'card', labels);
        const element = await mountPanel(htmlBlock);
        const listened = oneEvent(element, 'block-action');
        qs(element.renderRoot, '.html-open').click();
        expect((await listened).detail).to.deep.equal({ blockId: 'card', action: 'edit_html' });
    });

    it('renders block problems next to their property and emits block actions', async () => {
        const block = { ...defaultBlock(catalogEntry(catalog, 'text_input'), 'f', labels), field: 'task_id' };
        const element = await mountPanel(block, {
            problems: [
                { code: 'state_path_frozen', severity: 'error', pageId: 'main', blockId: 'f', property: 'field', params: { value: 'task_id' } },
                { code: 'template_unbalanced', severity: 'error', pageId: 'main', blockId: 'f', property: 'label', params: { value: '{open' } },
                { code: 'inputs_without_action', severity: 'warning', pageId: 'main', blockId: null, property: null, params: {} },
            ],
        });
        const problems = [...qsa(element.renderRoot, '.problem')].map((node) => [(node as TestEl).dataset.severity, node.textContent.trim()]);
        // Проблема страницы без property к блоку не относится
        expect(problems).to.deep.equal([
            ['error', T.problem_state_path_frozen.replace('{value}', 'task_id')],
            ['error', T.problem_template_unbalanced.replace('{value}', '{open')],
        ]);
        for (const action of ['duplicate', 'wrap', 'remove']) {
            const listened = oneEvent(element, 'block-action');
            const button = qs(element.renderRoot, `[data-action="${action}"]`);
            expect(button, action).to.exist;
            expect(button.tagName).to.equal('PLATFORM-BUTTON');
            (button as TestEl).click();
            expect((await listened).detail).to.deep.equal({ blockId: 'f', action });
        }
        expect(qs(element.renderRoot, '[data-action="remove"]').hasAttribute('danger')).to.equal(true);
    });

    it('keeps block action buttons in separate columns in a narrow sidebar', async () => {
        const block = defaultBlock(catalogEntry(catalog, 'text_input'), 'name', labels);
        const element = await mountPanel(block, { width: 280 });
        await elementUpdated(element);
        const buttons = [...qsa(element.renderRoot, '.actions platform-button')];
        expect(buttons).to.have.length(3);
        const boxes = buttons.map((button) => qs(button.renderRoot, 'button').getBoundingClientRect());
        expect(boxes[0]!.right, 'duplicate overlaps wrap').to.be.at.most(boxes[1]!.left + 1);
        expect(boxes[1]!.right, 'wrap overlaps remove').to.be.at.most(boxes[2]!.left + 1);
    });

    it('picks an agent identity image by file instead of a string field', async () => {
        const block = defaultBlock(catalogEntry(catalog, 'agent_identity'), 'agent-identity', labels);
        const element = await mountPanel(block);
        const field = q(element.renderRoot, '.image-field');
        expect(field, 'image picker').to.exist;
        expect(q(field!, 'platform-field')).to.equal(null);
        expect(qs(field!, '.sub-title span').textContent).to.equal(T.prop_image_url);
        expect(q(field!, 'img')).to.equal(null);
        expect(buttonByText(element, T.image_upload)).to.exist;
        const input = qs(element.renderRoot, '[data-image-input]');
        expect(input.getAttribute('accept')).to.equal('image/*');

        const png = new File([new Uint8Array([1, 2, 3])], 'logo.png', { type: 'image/png' });
        const uploaded = oneEvent(element, 'image-upload');
        const transfer = new DataTransfer();
        transfer.items.add(png);
        input.files = transfer.files;
        input.dispatchEvent(new Event('change', { bubbles: true }));
        expect((await uploaded).detail).to.deep.equal({ blockId: 'agent-identity', property: 'image_url', file: png });

        element.block = { ...block, image_url: 'https://files.test/logo.png' };
        await elementUpdated(element);
        expect(qs(element.renderRoot, '.image-preview img').getAttribute('src')).to.equal('https://files.test/logo.png');
        const cleared = oneEvent(element, 'property-change');
        buttonByText(element, T.image_clear)!.click();
        expect((await cleared).detail).to.deep.equal({ blockId: 'agent-identity', property: 'image_url', value: '' });

        let emitted = false;
        element.addEventListener('image-upload', () => { emitted = true; });
        const toasts: any[] = [];
        getPlatformBus().subscribeType(CoreEvents.UI_TOAST_SHOW, (event) => { toasts.push(event.payload); });
        const txt = new File(['nope'], 'note.txt', { type: 'text/plain' });
        const bad = new DataTransfer();
        bad.items.add(txt);
        const nextInput = qs(element.renderRoot, '[data-image-input]');
        nextInput.files = bad.files;
        nextInput.dispatchEvent(new Event('change', { bubbles: true }));
        expect(emitted).to.equal(false);
        expect(toasts.some((payload) => typeof payload.i18n_key === 'string' && payload.i18n_key.endsWith('interface_editor.toast_image_type'))).to.equal(true);
    });

    it('picks horizontal and vertical align from icon buttons', async () => {
        const element = await mountPanel(defaultBlock(catalogEntry(catalog, 'heading'), 'h', labels));
        const horizontal = q(element.renderRoot, '[data-align-axis="align"]');
        const vertical = q(element.renderRoot, '[data-align-axis="valign"]');
        expect(horizontal).to.not.equal(null);
        expect(vertical).to.not.equal(null);
        expect(qsa(horizontal!, '.align-glyph i').length).to.equal(9);
        const changed = oneEvent(element, 'property-change');
        qs(horizontal!, '[data-value="center"]').click();
        expect((await changed).detail).to.deep.equal({ blockId: 'h', property: 'align', value: 'center' });
        const valign = oneEvent(element, 'property-change');
        qs(vertical!, '[data-value="end"]').click();
        expect((await valign).detail).to.deep.equal({ blockId: 'h', property: 'valign', value: 'end' });
    });

    it('switches a button from a flow action to another page', async () => {
        const block = defaultBlock(catalogEntry(catalog, 'button'), 'next', labels);
        const main = pageWith([block]);
        const done = { page_id: 'done', title: 'Done', blocks: [] };
        const element = await mountPanel(block, { page: main, pages: [main, done] });
        expect(q(element.renderRoot, '[data-click-target="action"]')).to.not.equal(null);
        expect(await fieldChanged(element, fieldByLabel(element, T.click_target), 'page')).to.deep.equal({
            blockId: 'next',
            property: 'click_target',
            value: { action: null, page_id: 'done', url: '' },
        });
        element.block = { ...block, action: null, page_id: 'done', url: '' };
        await elementUpdated(element);
        expect(q(element.renderRoot, '[data-click-target="page"]')).to.not.equal(null);
        expect(fieldByLabel(element, T.prop_page_id)!.value).to.equal('done');
        expect(await fieldChanged(element, fieldByLabel(element, T.prop_page_id), 'main')).to.deep.equal({
            blockId: 'next',
            property: 'click_target',
            value: { action: null, page_id: 'main', url: '' },
        });
    });
});
