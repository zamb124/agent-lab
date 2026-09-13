/**
 * Редактор блока ``html``: preview-first (кадр + исходник), inspector State/Events/Help,
 * last-good при битом JSON, сниппеты в курсор, Apply disabled на пустом source.
 */

import { elementUpdated, expect, fixture, fixtureCleanup, html, waitUntil } from '../helpers/render.js';
import { bootstrapTestBus, resetPlatformState } from '../helpers/reset.js';
import { CoreEvents, getPlatformBus } from '@platform/lib/events/index.js';
import { FLOW_UI_HTML_MIN_HEIGHT, FLOW_UI_HTML_THEME_TOKENS } from '@platform/lib/flow-ui/runtime/html-sandbox.js';
import { HTML_EDITOR_VIEWPORTS } from '@platform/lib/flow-ui/editor/html-editor-api.js';
import flowsEn from '../../../../core/i18n/translations/en/flows.json' with { type: 'json' };
import '@platform/lib/components/platform-modal-stack.js';
import '../../../../apps/flows/ui/modals/flows-interface-html-editor-modal.js';

const BLOCK = {
    block_id: 'card',
    type: 'html',
    visible_when: null,
    source: '<b data-bind="title"></b><i data-show="order.total"></i>',
    height: 'auto',
    fields: ['items'],
    field: 'card',
};

const SAMPLE_STATE = { title: 'Hello', order: { total: 42, currency: 'RUB' }, task_id: 'system-only' };
const LAYOUT_KEY = 'platform:flows:html_editor_layout';

function seedTranslations(bus) {
    const locale = bus.getState().i18n.locale;
    const previous = bus.getState().i18n.translations[locale] || {};
    bus.dispatch(CoreEvents.I18N_LOCALE_LOADED, { locale, bundle: { ...previous, flows: flowsEn } }, { source: 'system' });
    bus.dispatch(CoreEvents.I18N_LOCALE_CHANGED, { locale, default_namespace: 'flows' }, { source: 'system' });
}

async function openModal(props) {
    const stack = await fixture(html`<platform-modal-stack></platform-modal-stack>`);
    getPlatformBus().dispatch(CoreEvents.UI_MODAL_OPEN, { kind: 'flows.interface_html_editor', props });
    await elementUpdated(stack);
    const modal = [...document.querySelectorAll('flows-interface-html-editor-modal')].at(-1);
    expect(modal, 'modal mounted').to.exist;
    await waitUntil(() => modal.renderRoot.querySelector('.workspace') !== null, 'modal body did not render');
    return modal;
}

async function openHelp(modal) {
    modal._tab = 'help';
    await elementUpdated(modal);
    return modal.renderRoot.querySelector('.sheet');
}

describe('flows-interface-html-editor-modal', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus({ factories: [] });
        seedTranslations(getPlatformBus());
        localStorage.removeItem(LAYOUT_KEY);
    });

    afterEach(() => {
        fixtureCleanup();
        for (const leftover of document.querySelectorAll('flows-interface-html-editor-modal')) leftover.remove();
    });

    it('opens the test state as the block projection with null placeholders for missing paths', async () => {
        const modal = await openModal({ source: BLOCK.source, block: BLOCK, sampleState: SAMPLE_STATE, statePaths: ['title'], onApply: () => {} });
        expect(JSON.parse(modal._stateText)).to.deep.equal({ items: null, title: 'Hello', order: { total: 42 } });
        const sheet = await openHelp(modal);
        const sections = [...sheet.querySelectorAll('section')];
        const chips = sections.map((section) => [...section.querySelectorAll('.chips code')].map((code) => code.textContent));
        expect(chips[0]).to.deep.equal(['items', 'title', 'order.total']);
        expect(chips[1]).to.deep.equal(['card']);
        expect([...sections[3].querySelectorAll('.chips button')].map((button) => button.textContent)).to.deep.equal([...FLOW_UI_HTML_THEME_TOKENS]);
        const api = [...sheet.querySelectorAll('.api code')].map((code) => code.textContent);
        expect(api).to.include('flowUi.send(\'action\', { ... })');
        expect(api).to.include('data-bind="path"');
        expect(sheet.textContent).to.contain(flowsEn.interface_editor.html_api_send);
    });

    it('replace-all writes the starter example; apply hands the draft back', async () => {
        let applied = null;
        const modal = await openModal({ source: BLOCK.source, block: BLOCK, sampleState: {}, statePaths: [], onApply: (source) => { applied = source; } });
        modal._snippetsOpen = true;
        await elementUpdated(modal);
        modal.renderRoot.querySelector('[data-replace]').click();
        await elementUpdated(modal);
        expect(modal._draft).to.equal(flowsEn.interface_editor.default_text_html_source);
        expect(modal._draft).to.contain('flowUi.onChange(').and.contain('flowUi.send(').and.contain('flowUi.setValue(').and.contain('data-bind=').and.contain('data-show=');
        expect(JSON.parse(modal._stateText)).to.deep.equal(JSON.parse(flowsEn.interface_editor.html_example_state));
        modal._apply();
        expect(applied).to.equal(flowsEn.interface_editor.default_text_html_source);
    });

    it('renders the starter example in the sandbox with a visible card', async () => {
        const source = flowsEn.interface_editor.default_text_html_source;
        const modal = await openModal({
            source,
            block: { ...BLOCK, source, fields: ['items'] },
            sampleState: JSON.parse(flowsEn.interface_editor.html_example_state),
            statePaths: ['title'],
            onApply: () => {},
        });
        const preview = modal.renderRoot.querySelector('flow-ui-html-block');
        expect(preview, 'preview block').to.exist;
        await waitUntil(() => preview._bridge !== null, 'sandbox bridge missing');
        await waitUntil(() => preview._height > FLOW_UI_HTML_MIN_HEIGHT, 'preview iframe did not size itself', { timeout: 4000 });
        expect(preview.renderRoot.querySelector('iframe').srcdoc).to.contain('class="card"');
    });

    it('sizes the sandbox preview after the modal portals to document.body', async () => {
        const source = '<p data-bind="title"></p><div style="height:80px">pad</div>';
        const modal = await openModal({
            source,
            block: { ...BLOCK, source },
            sampleState: SAMPLE_STATE,
            statePaths: ['title'],
            onApply: () => {},
        });
        const preview = modal.renderRoot.querySelector('flow-ui-html-block');
        expect(preview, 'preview block').to.exist;
        await waitUntil(() => preview._bridge !== null, 'sandbox bridge missing');
        await waitUntil(() => preview._height > FLOW_UI_HTML_MIN_HEIGHT, 'preview iframe did not size itself', { timeout: 4000 });
        expect(preview.renderRoot.querySelector('iframe').srcdoc).to.contain('data-bind="title"');
    });

    it('keeps the last-good preview when the test state JSON is invalid', async () => {
        const modal = await openModal({ source: BLOCK.source, block: BLOCK, sampleState: SAMPLE_STATE, statePaths: [], onApply: () => {} });
        const preview = modal.renderRoot.querySelector('.stage flow-ui-html-block');
        expect(preview, 'preview before invalid JSON').to.exist;
        modal._setStateText('{ not json');
        await elementUpdated(modal);
        expect(modal.renderRoot.querySelector('.stage flow-ui-html-block'), 'preview stays mounted').to.equal(preview);
        expect(modal._stateError).to.not.equal('');
        expect(modal.renderRoot.querySelector('.badge').textContent).to.contain(flowsEn.interface_editor.html_state_invalid);
        expect(modal._lastGoodState).to.deep.equal({ items: null, title: 'Hello', order: { total: 42 } });
    });

    it('disables Apply when the source is empty', async () => {
        const modal = await openModal({ source: BLOCK.source, block: BLOCK, sampleState: {}, statePaths: [], onApply: () => {} });
        modal._setDraft('', true);
        await elementUpdated(modal);
        const apply = modal.renderRoot.querySelector('.modal-actions platform-button[primary]');
        expect(apply.hasAttribute('disabled')).to.equal(true);
        expect(apply.getAttribute('title')).to.equal(flowsEn.interface_editor.html_apply_empty);
    });

    it('sets the canvas frame width from the viewport control', async () => {
        const modal = await openModal({ source: BLOCK.source, block: BLOCK, sampleState: SAMPLE_STATE, statePaths: [], onApply: () => {} });
        modal._viewport = 'mobile';
        await elementUpdated(modal);
        const stage = modal.renderRoot.querySelector('.stage');
        expect(stage.getAttribute('style')).to.contain(`${HTML_EDITOR_VIEWPORTS.mobile}px`);
        modal._previewTheme = 'light';
        await elementUpdated(modal);
        expect(modal.renderRoot.querySelector('.stage').getAttribute('data-theme')).to.equal('light');
    });

    it('inserts a snippet at the caret and merges test-state without wiping the draft', async () => {
        const modal = await openModal({ source: BLOCK.source, block: BLOCK, sampleState: SAMPLE_STATE, statePaths: [], onApply: () => {} });
        const before = modal._draft;
        modal._insertSnippet('bind');
        await elementUpdated(modal);
        expect(modal._draft).to.contain(before);
        expect(modal._draft).to.contain('data-bind="title"');
        expect(JSON.parse(modal._stateText).title).to.equal('Order #1042');
        expect(JSON.parse(modal._stateText).order).to.deep.equal({ total: 42 });
    });

    it('asks before replace-all when the draft is dirty', async () => {
        const modal = await openModal({ source: BLOCK.source, block: BLOCK, sampleState: {}, statePaths: [], onApply: () => {} });
        modal._setDraft(`${BLOCK.source}\n<!-- dirty -->`, true);
        modal._snippetsOpen = true;
        await elementUpdated(modal);
        modal.renderRoot.querySelector('[data-replace]').click();
        await elementUpdated(modal);
        expect(modal._replaceConfirm).to.equal(true);
        expect(modal._draft).to.contain('<!-- dirty -->');
        modal.renderRoot.querySelector('[data-replace-yes]').click();
        await elementUpdated(modal);
        expect(modal._draft).to.equal(flowsEn.interface_editor.default_text_html_source);
    });

    it('keeps the source and JSON editors writable', async () => {
        const modal = await openModal({ source: BLOCK.source, block: BLOCK, sampleState: SAMPLE_STATE, statePaths: [], onApply: () => {} });
        const source = modal.renderRoot.querySelector('platform-code-editor[data-html-source]');
        expect(source.readonly, 'html source editor must be writable').to.equal(false);
        modal._stateMode = 'json';
        await elementUpdated(modal);
        const json = modal.renderRoot.querySelector('.inspector platform-code-editor');
        expect(json, 'json editor').to.exist;
        expect(json.readonly, 'json state editor must be writable').to.equal(false);
        source.insertAtCursor('<!-- typed -->');
        await elementUpdated(modal);
        expect(modal._draft).to.contain('<!-- typed -->');
    });
});
