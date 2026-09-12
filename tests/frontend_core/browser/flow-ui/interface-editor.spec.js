/**
 * Редактор интерфейса: каталог из ``GET /flow-ui/schema``, вставка блока из палитры на холст,
 * выделение → панель «Свойства», undo/redo, publish gate и событие ``interface-change``.
 */

import { elementUpdated, expect, fixture, fixtureCleanup, html, oneEvent, waitUntil } from '../helpers/render.js';
import { bootstrapTestBus, resetPlatformState } from '../helpers/reset.js';
import { installFetchMock } from '../helpers/fake-fetch.js';
import { CoreEvents, getPlatformBus } from '@platform/lib/events/index.js';
import { blockElement } from '@platform/lib/flow-ui/editor/selection.js';
import flowsEn from '../../../../core/i18n/translations/en/flows.json' with { type: 'json' };
import schema from '../../../fixtures/flow_ui/schema.json' with { type: 'json' };
import { interfaceEditorSlice } from '../../../../apps/flows/ui/events/resources/interface-editor.resource.js';
import { editorResource } from '../../../../apps/flows/ui/events/resources/editor.resource.js';
import { secretsVariablesResource } from '@platform/lib/events/resources/secrets-variables.resource.js';
import { flowUiAssistOp, flowUiSchemaOp } from '../../../../apps/flows/ui/events/resources/flow-ui.resource.js';
import '../../../../apps/flows/ui/components/interface-editor/flows-interface-editor.js';

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

async function mountEditor() {
    const element = await fixture(html`<flows-interface-editor
        .interfaceConfig=${structuredClone(INTERFACE)}
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

describe('flows-interface-editor', () => {
    let fetchMock;

    beforeEach(() => {
        resetPlatformState();
        globalThis.localStorage.clear();
        const bus = bootstrapTestBus({ factories: [interfaceEditorSlice, editorResource, flowUiSchemaOp, flowUiAssistOp, secretsVariablesResource] });
        seedTranslations(bus);
        fetchMock = installFetchMock();
        fetchMock.respondJson('GET', (url) => url.includes('/flows/api/v1/flow-ui/schema'), schema);
        fetchMock.respondJson('GET', (url) => url.includes('/secrets/api/v1/variables'), { items: [], total: 0, limit: 200, offset: 0 });
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

    it('undoes and redoes through the toolbar events and keeps the draft in local storage', async () => {
        const element = await mountEditor();
        paletteItem(element, 'button').click();
        await elementUpdated(element);
        expect(editorState().history.past).to.have.length(1);

        element.renderRoot.querySelector('flows-interface-toolbar').dispatchEvent(new CustomEvent('editor-undo'));
        await elementUpdated(element);
        expect(editorState().history.present).to.deep.equal(INTERFACE);
        element.renderRoot.querySelector('flows-interface-toolbar').dispatchEvent(new CustomEvent('editor-redo'));
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

        await showPalette(element);
        expect(editorState().sidebarTab).to.equal('add');
        paletteItem(element, 'button').click();
        await elementUpdated(element);
        await waitUntil(() => element.renderRoot.querySelector('.problems .ok') !== null, 'problems did not clear');

        const published = oneEvent(element, 'interface-change');
        element.renderRoot.querySelector('flows-interface-toolbar').dispatchEvent(new CustomEvent('editor-publish'));
        const { detail } = await published;
        expect(detail.config.pages[0].blocks.map((block) => block.type)).to.deep.equal(['heading', 'text_input', 'button']);
    });
});
