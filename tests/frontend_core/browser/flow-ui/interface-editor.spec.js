/**
 * Редактор интерфейса: каталог из ``GET /flow-ui/schema``, вставка блока из палитры на холст,
 * выделение → панель «Свойства», undo/redo, publish gate и событие ``interface-change``.
 */

import { elementUpdated, expect, fixture, fixtureCleanup, html, oneEvent, waitUntil } from '../helpers/render.js';
import { bootstrapTestBus, resetPlatformState } from '../helpers/reset.js';
import { installFetchMock } from '../helpers/fake-fetch.js';
import { CoreEvents, getPlatformBus, platformFileCreateOp } from '@platform/lib/events/index.js';
import { blockElement } from '@platform/lib/flow-ui/editor/selection.js';
import flowsEn from '../../../../core/i18n/translations/en/flows.json' with { type: 'json' };
import schema from '../../../fixtures/flow_ui/schema.json' with { type: 'json' };
import { interfaceEditorSlice } from '../../../../apps/flows/ui/events/resources/interface-editor.resource.js';
import { editorResource } from '../../../../apps/flows/ui/events/resources/editor.resource.js';
import { secretsVariablesResource } from '@platform/lib/events/resources/secrets-variables.resource.js';
import { flowUiAssistOp, flowUiSchemaOp } from '../../../../apps/flows/ui/events/resources/flow-ui.resource.js';
import '../../../../apps/flows/ui/components/interface-editor/flows-interface-editor.js';
import '../../../../apps/flows/ui/components/interface-editor/flows-interface-toolbar.js';

const INTERFACE = {
    start_page_id: 'main',
    pages: [{
        page_id: 'main',
        title: 'Заявка',
        blocks: [{ block_id: 'title', type: 'heading', visible_when: null, text: 'Заявка', level: 2 }],
    }],
};

function seedTranslations(bus) {
    const locale = bus.getState().i18n.locale;
    const previous = bus.getState().i18n.translations[locale] || {};
    bus.dispatch(CoreEvents.I18N_LOCALE_LOADED, { locale, bundle: { ...previous, flows: flowsEn } }, { source: 'system' });
    bus.dispatch(CoreEvents.I18N_LOCALE_CHANGED, { locale, default_namespace: 'flows' }, { source: 'system' });
}

function editorState() {
    return getPlatformBus().getState().flowsInterfaceEditor;
}

function field(blockId, name, label, extra = {}) {
    return {
        block_id: blockId, type: 'text_input', visible_when: null, field: name, label,
        required: false, error_message: '', action: null, placeholder: '', default: '', pattern: '',
        multiline: false, secret: false, ...extra,
    };
}

const FORM = {
    start_page_id: 'main',
    pages: [{
        page_id: 'main',
        title: 'Регистрация',
        blocks: [
            { block_id: 'title', type: 'heading', visible_when: null, text: 'Регистрация', level: 1 },
            { block_id: 'clip', type: 'video', visible_when: null, url: 'https://example.com/intro.mp4' },
            field('name', 'name', 'Имя'),
            field('email', 'email', 'Email'),
            field('phone', 'phone', 'Телефон'),
            { block_id: 'plan', type: 'select', visible_when: null, field: 'plan', label: 'Тариф', required: false, error_message: '', action: null, options: [{ value: 'a', label: 'A' }], multiple: false, default: null },
            field('note', 'note', 'Комментарий', { multiline: true }),
            { block_id: 'send', type: 'button', visible_when: null, label: 'Зарегистрироваться', action: { name: 'submit', payload: {} }, variant: 'primary' },
        ],
    }],
};

async function mountEditor(document = INTERFACE) {
    const element = await fixture(html`<flows-interface-editor
        .interfaceConfig=${structuredClone(document)}
        .flowId=${'flow-1'}
        .branchId=${'default'}
        style="display:block;width:1280px;height:760px"
    ></flows-interface-editor>`);
    await waitUntil(() => element.renderRoot.querySelector('flows-interface-add-panel') !== null, 'editor did not load schema', { timeout: 8000 });
    const canvas = () => element.renderRoot.querySelector('platform-flow-ui');
    await waitUntil(() => canvas() !== null && blockElement(canvas(), 'title') !== null, 'canvas did not render', { timeout: 8000 });
    return element;
}

async function showPalette(element) {
    getPlatformBus().dispatch('flows/interface_editor/sidebar_tab_set', { tab: 'add' });
    await elementUpdated(element);
    await waitUntil(() => element.renderRoot.querySelector('flows-interface-add-panel') !== null, 'palette did not open');
}

function paletteItem(element, type) {
    const panel = element.renderRoot.querySelector('flows-interface-add-panel');
    const label = flowsEn.interface_editor[`block_${type}`];
    return [...panel.renderRoot.querySelectorAll('article.item')].find((item) => item.getAttribute('title') === label);
}

function paletteColumnsItem(element, count) {
    const panel = element.renderRoot.querySelector('flows-interface-add-panel');
    const label = flowsEn.interface_editor.palette_columns.replace('{count}', String(count));
    return [...panel.renderRoot.querySelectorAll('article.item')].find((item) => item.getAttribute('title') === label);
}

describe('flows-interface-editor', () => {
    let fetchMock;

    beforeEach(() => {
        resetPlatformState();
        globalThis.localStorage.clear();
        const bus = bootstrapTestBus({ factories: [interfaceEditorSlice, editorResource, flowUiSchemaOp, flowUiAssistOp, secretsVariablesResource, platformFileCreateOp] });
        seedTranslations(bus);
        fetchMock = installFetchMock();
        fetchMock.respondJson('GET', (url) => url.includes('/flows/api/v1/flow-ui/schema'), schema);
        fetchMock.respondJson('GET', (url) => url.includes('/secrets/api/v1/variables'), { items: [], total: 0, limit: 200, offset: 0 });
        fetchMock.respondJson('POST', (url) => url.endsWith('/api/v1/files/uploads'), {
            upload_id: 'up_identity',
            file_id: 'file-agent',
            chunk_size_bytes: 5 * 1024 * 1024,
        });
        fetchMock.respondJson('PUT', (url) => url.includes('/api/v1/files/uploads/up_identity/parts/'), { part_number: 1, etag: 'etag-1' });
        fetchMock.respondJson('POST', (url) => url.endsWith('/api/v1/files/uploads/up_identity/complete'), {
            file_id: 'file-agent',
            original_name: 'agent.png',
            content_type: 'image/png',
            file_size: 3,
            url: 'https://files.test/agent.png',
            checksum: 'sha256:test',
            is_public: true,
            metadata: {},
            created_at: '2026-01-01T00:00:00Z',
        });
    });

    afterEach(() => {
        fetchMock.uninstall();
        fixtureCleanup();
    });

    it('opens the published document, inserts a palette block on the canvas and selects it', async () => {
        const element = await mountEditor();
        expect(editorState().documentKey).to.equal('flow-1:default');
        expect(editorState().history.present).to.deep.equal(INTERFACE);

        paletteItem(element, 'text_input').click();
        await elementUpdated(element);
        const canvas = element.renderRoot.querySelector('platform-flow-ui');
        await waitUntil(() => blockElement(canvas, 'text-input') !== null, 'inserted block did not render');

        const state = editorState();
        expect(state.selectedBlockId).to.equal('text-input');
        expect(state.sidebarTab).to.equal('properties');
        expect(state.history.present.pages[0].blocks.map((block) => block.block_id)).to.deep.equal(['title', 'text-input']);
        expect(state.history.present.pages[0].blocks[1]).to.include({ type: 'text_input', field: 'text_input' });
        await waitUntil(() => element.renderRoot.querySelector('flows-interface-properties-panel') !== null, 'properties panel did not open');
        expect(element.renderRoot.querySelector('.selection')).to.not.equal(null);
    });

    it('undoes and redoes the draft history and keeps it in local storage', async () => {
        const element = await mountEditor();
        paletteItem(element, 'button').click();
        await elementUpdated(element);
        expect(editorState().history.past).to.have.length(1);

        element.undo();
        await elementUpdated(element);
        expect(editorState().history.present).to.deep.equal(INTERFACE);
        element.redo();
        await elementUpdated(element);
        expect(editorState().history.present.pages[0].blocks).to.have.length(2);

        const drafts = JSON.parse(globalThis.localStorage.getItem(Object.keys(globalThis.localStorage).find((key) => key.includes('interface_drafts'))));
        expect(drafts['flow-1:default'].pages[0].blocks).to.have.length(2);
    });

    it('blocks publish while inputs have no action and publishes a valid draft', async () => {
        const element = await mountEditor();
        paletteItem(element, 'text_input').click();
        await elementUpdated(element);
        await waitUntil(() => element.renderRoot.querySelector('.problems .problem[data-severity="error"]') !== null, 'publish gate did not report');
        expect(element.renderRoot.querySelector('.problems').textContent).to.contain(flowsEn.interface_editor.problem_inputs_without_action);
        expect(element.commitDraft()).to.equal(false);

        await showPalette(element);
        expect(editorState().sidebarTab).to.equal('add');
        paletteItem(element, 'button').click();
        await elementUpdated(element);
        await waitUntil(() => element.renderRoot.querySelector('.problems .ok') !== null, 'problems did not clear');

        const published = oneEvent(element, 'interface-change');
        expect(element.commitDraft()).to.equal(true);
        const { detail } = await published;
        expect(detail.config.pages[0].blocks.map((block) => block.type)).to.deep.equal(['heading', 'text_input', 'button']);
    });

    it('publishes an inserted html block with its source', async () => {
        const element = await mountEditor();
        paletteItem(element, 'html').click();
        await elementUpdated(element);
        const canvas = element.renderRoot.querySelector('platform-flow-ui');
        await waitUntil(() => blockElement(canvas, 'html') !== null, 'html block did not render');
        const published = oneEvent(element, 'interface-change');
        expect(element.commitDraft()).to.equal(true);
        const { detail } = await published;
        const inserted = detail.config.pages[0].blocks.find((block) => block.type === 'html');
        expect(inserted.source).to.equal(flowsEn.interface_editor.default_text_html_source);
        expect(inserted.fields).to.deep.equal(['items']);
    });

    it('opens the html editor from the canvas menu with the block source', async () => {
        const element = await mountEditor();
        paletteItem(element, 'html').click();
        await elementUpdated(element);
        const canvas = element.renderRoot.querySelector('platform-flow-ui');
        await waitUntil(() => blockElement(canvas, 'html') !== null, 'html block did not render');
        await waitUntil(() => element.renderRoot.querySelector('.kebab') !== null, 'selection menu missing');
        const opened = [];
        element.openModal = (kind, props) => { opened.push({ kind, props }); };
        element.renderRoot.querySelector('.kebab').click();
        await elementUpdated(element);
        element.renderRoot.querySelector('platform-menu').dispatchEvent(new CustomEvent('menu-select', { detail: { id: 'edit_html' }, bubbles: true, composed: true }));
        expect(opened[0].kind).to.equal('flows.interface_html_editor');
        expect(opened[0].props.source).to.equal(flowsEn.interface_editor.default_text_html_source);
        opened[0].props.onApply('<p>from-menu</p>');
        await elementUpdated(element);
        expect(editorState().history.present.pages[0].blocks.find((block) => block.type === 'html').source).to.equal('<p>from-menu</p>');
    });

    it('uploads an agent identity icon and writes the file URL into the draft', async () => {
        const element = await mountEditor();
        paletteItem(element, 'agent_identity').click();
        await elementUpdated(element);
        await waitUntil(() => element.renderRoot.querySelector('flows-interface-properties-panel') !== null, 'properties did not open');
        const panel = element.renderRoot.querySelector('flows-interface-properties-panel');
        await waitUntil(() => panel.renderRoot.querySelector('[data-image-input]') !== null, 'image picker missing');
        const input = panel.renderRoot.querySelector('[data-image-input]');
        const file = new File([new Uint8Array([1, 2, 3])], 'agent.png', { type: 'image/png' });
        const transfer = new DataTransfer();
        transfer.items.add(file);
        input.files = transfer.files;
        input.dispatchEvent(new Event('change', { bubbles: true }));
        await waitUntil(() => {
            const identity = editorState().history.present.pages[0].blocks.find((block) => block.type === 'agent_identity');
            return identity !== undefined && identity.image_url === 'https://files.test/agent.png';
        }, 'image_url was not committed');
        const init = fetchMock.calls.find((call) => call.method === 'POST' && call.url.endsWith('/api/v1/files/uploads'));
        expect(init).to.exist;
        const body = JSON.parse(init.init.body);
        expect(body.spec.source_kind).to.equal('flow_asset');
        expect(body.spec.post_create.is_public).to.equal(true);
    });

    it('inserts a palette block into the selected columns cell', async () => {
        const element = await mountEditor();
        paletteColumnsItem(element, 2).click();
        await elementUpdated(element);
        await waitUntil(() => editorState().history.present.pages[0].blocks.some((block) => block.type === 'columns'), 'columns did not insert');
        expect(editorState().selectedBlockId).to.equal('columns');
        expect(editorState().sidebarTab).to.equal('add');
        paletteItem(element, 'heading').click();
        await elementUpdated(element);
        await waitUntil(() => {
            const columns = editorState().history.present.pages[0].blocks.find((block) => block.type === 'columns');
            return columns !== undefined && columns.columns[0].blocks.some((block) => block.type === 'heading');
        }, 'heading did not land in the first column');
        const columns = editorState().history.present.pages[0].blocks.find((block) => block.type === 'columns');
        expect(columns.columns[0].blocks.map((block) => block.block_id)).to.deep.equal(['heading']);
        expect(columns.columns[1].blocks).to.deep.equal([]);
        expect(editorState().history.present.pages[0].blocks.map((block) => block.block_id)).to.deep.equal(['title', 'columns']);
    });

    it('opens a newly added page on the canvas without throwing', async () => {
        const element = await mountEditor();
        element.renderRoot.querySelector('flows-interface-pages-tabs').dispatchEvent(new CustomEvent('page-command', { detail: { command: 'add' } }));
        await elementUpdated(element);
        await waitUntil(() => editorState().pageId === 'page-2', 'editor did not select the new page');
        const canvas = element.renderRoot.querySelector('platform-flow-ui');
        await waitUntil(() => canvas.store.pageId === 'page-2', 'canvas did not follow page-2');
        expect(canvas.getAttribute('page-id')).to.equal('page-2');
        expect(canvas.store.page('page-2')).to.not.equal(null);
        expect(editorState().history.present.pages[1].show_title).to.equal(false);
    });

    it('starts a live test chat with base-url when preview is on', async () => {
        fetchMock.respondJson('GET', (url) => url.includes('/flows/api/v1/flow-1/interface'), {
            flow_id: 'flow-1',
            branch_id: 'default',
            document: INTERFACE,
            viewer: { can_edit_flow: true, can_interact: true, can_share: false, auth_mode: 'platform' },
            look: null,
            capabilities: { cancel: true, files: false, voice: false },
            flow_identity: { title: 'Flow', image_url: null },
        });
        const element = await mountEditor();
        await element.setCanvasPreview(true);
        await elementUpdated(element);
        const canvas = element.renderRoot.querySelector('platform-flow-ui');
        expect(canvas.hasAttribute('editing')).to.equal(false);
        expect(canvas.getAttribute('base-url')).to.equal('/flows');
        expect(canvas.profile).to.equal('editor_test');
        await waitUntil(() => canvas._status === 'ready', 'test chat did not open the interface');
        expect(canvas.client).to.not.equal(null);
        expect(blockElement(canvas, 'title')).to.not.equal(null);
    });

    it('keeps an inserted html block visible in the live test frame', async () => {
        fetchMock.respondJson('GET', (url) => url.includes('/flows/api/v1/flow-1/interface'), {
            flow_id: 'flow-1',
            branch_id: 'default',
            document: INTERFACE,
            viewer: { can_edit_flow: true, can_interact: true, can_share: false, auth_mode: 'platform' },
            look: null,
            capabilities: { cancel: true, files: false, voice: false },
            flow_identity: { title: 'Flow', image_url: null },
        });
        const element = await mountEditor();
        paletteItem(element, 'html').click();
        await elementUpdated(element);
        await waitUntil(() => blockElement(element.renderRoot.querySelector('platform-flow-ui'), 'html') !== null, 'html block did not insert');
        await element.setCanvasPreview(true);
        await elementUpdated(element);
        const canvas = element.renderRoot.querySelector('platform-flow-ui');
        expect(canvas.hasAttribute('editing')).to.equal(false);
        await waitUntil(() => canvas._status === 'ready', 'test chat did not open the interface');
        await waitUntil(() => blockElement(canvas, 'html') !== null, 'html block disappeared in test');
        const host = blockElement(canvas, 'html').querySelector('flow-ui-html-block');
        await waitUntil(() => host.getBoundingClientRect().height > 80, 'html block collapsed in test', { timeout: 4000 });
        const frame = element.renderRoot.querySelector('.frame').getBoundingClientRect();
        const box = host.getBoundingClientRect();
        expect(box.top).to.be.at.least(frame.top - 2);
        expect(box.bottom).to.be.at.most(frame.bottom + 2);
        expect(canvas.store.document.pages[0].blocks.some((block) => block.type === 'html')).to.equal(true);
    });

    it('grows the white frame with the form instead of clipping the last button', async () => {
        const element = await mountEditor(FORM);
        const canvas = element.renderRoot.querySelector('platform-flow-ui');
        await waitUntil(() => blockElement(canvas, 'send') !== null, 'form did not render');
        const frame = element.renderRoot.querySelector('.frame');
        const last = blockElement(canvas, 'send').getBoundingClientRect();
        const card = frame.getBoundingClientRect();
        expect(last.bottom).to.be.at.most(card.bottom + 2);
        expect(card.height).to.be.above(480);
        const video = blockElement(canvas, 'clip').querySelector('video');
        expect(video.getBoundingClientRect().width).to.be.above(520);
    });

    it('aligns the selected block from the selection chrome', async () => {
        const element = await mountEditor();
        const canvas = element.renderRoot.querySelector('platform-flow-ui');
        blockElement(canvas, 'title').click();
        await elementUpdated(element);
        await waitUntil(() => element.renderRoot.querySelector('.selection .align') !== null, 'selection chrome did not render');
        element.renderRoot.querySelector('.selection .align [data-align="center"]').click();
        await waitUntil(() => editorState().history.present.pages[0].blocks[0].align === 'center', 'align did not commit');
        await waitUntil(() => blockElement(canvas, 'title')?.dataset.align === 'center', 'canvas did not apply align');
        expect(element.renderRoot.querySelector('.resize-e')).to.not.equal(null);
    });

    it('selects a narrow centered button by clicking the visible control', async () => {
        const document = {
            start_page_id: 'main',
            pages: [{
                page_id: 'main',
                title: 'Шаг',
                blocks: [
                    { block_id: 'title', type: 'heading', visible_when: null, text: 'Шаг', level: 2 },
                    {
                        block_id: 'next', type: 'button', visible_when: null, label: 'Далее',
                        action: { name: 'submit', payload: {} }, variant: 'secondary',
                        span: 1, align: 'center', valign: 'start',
                    },
                ],
            }],
        };
        const element = await mountEditor(document);
        const canvas = element.renderRoot.querySelector('platform-flow-ui');
        await waitUntil(() => blockElement(canvas, 'next') !== null, 'button did not render');
        const block = blockElement(canvas, 'next');
        const visible = block.querySelector('.fu-button').getBoundingClientRect();
        const hit = block.getRootNode().elementFromPoint(visible.left + visible.width / 2, visible.top + visible.height / 2);
        expect(hit).to.equal(block);
        hit.dispatchEvent(new MouseEvent('click', { bubbles: true, composed: true }));
        await waitUntil(() => editorState().selectedBlockId === 'next', 'button click did not select the block');
        await waitUntil(() => element.renderRoot.querySelector('.selection') !== null, 'selection chrome did not render');
        const frame = element.renderRoot.querySelector('.selection').getBoundingClientRect();
        expect(frame.width).to.be.at.least(visible.width - 2);
    });

    it('does not render a second publish or status chip; contextual toolbar has no primary', async () => {
        const element = await mountEditor();
        expect(element.renderRoot.querySelector('flows-interface-toolbar')).to.equal(null);
        expect(element.renderRoot.querySelector('.status')).to.equal(null);

        const toolbar = await fixture(html`<flows-interface-toolbar></flows-interface-toolbar>`);
        await elementUpdated(toolbar);
        expect(toolbar.renderRoot.querySelector('.status')).to.equal(null);
        expect(toolbar.renderRoot.textContent).to.not.contain(flowsEn.interface_editor.publish);
        expect(toolbar.renderRoot.textContent).to.contain(flowsEn.interface_editor.preview);
    });
});
