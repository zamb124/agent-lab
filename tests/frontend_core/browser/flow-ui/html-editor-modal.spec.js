/**
 * Редактор блока ``html``: тестовый state открывается как проекция блока (fields + data-bind/data-show,
 * отсутствующие пути — ``null``), шпаргалка показывает пути чтения/записи, API ``flowUi`` и токены темы,
 * «Стартовый пример» подставляет исходник и подходящий state, «Применить» отдаёт исходник в ``onApply``.
 */

import { elementUpdated, expect, fixture, fixtureCleanup, html, waitUntil } from '../helpers/render.js';
import { bootstrapTestBus, resetPlatformState } from '../helpers/reset.js';
import { CoreEvents, getPlatformBus } from '@platform/lib/events/index.js';
import { FLOW_UI_HTML_THEME_TOKENS } from '@platform/lib/flow-ui/runtime/html-sandbox.js';
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
    await waitUntil(() => modal.renderRoot.querySelector('.sheet') !== null, 'modal body did not render');
    return modal;
}

describe('flows-interface-html-editor-modal', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus({ factories: [] });
        seedTranslations(getPlatformBus());
    });

    afterEach(() => {
        fixtureCleanup();
        // Открытая модалка переезжает в document.body и не убирается вместе с fixture.
        for (const leftover of document.querySelectorAll('flows-interface-html-editor-modal')) leftover.remove();
    });

    it('opens the test state as the block projection with null placeholders for missing paths', async () => {
        const modal = await openModal({ source: BLOCK.source, block: BLOCK, sampleState: SAMPLE_STATE, statePaths: ['title'], onApply: () => {} });
        expect(JSON.parse(modal._stateText)).to.deep.equal({ items: null, title: 'Hello', order: { total: 42 } });
        const sheet = modal.renderRoot.querySelector('.sheet');
        const chips = [...sheet.querySelectorAll('section')].map((section) => [...section.querySelectorAll('.chips code')].map((code) => code.textContent));
        expect(chips[0]).to.deep.equal(['items', 'title', 'order.total']);
        expect(chips[1]).to.deep.equal(['card']);
        expect(chips[3]).to.deep.equal([...FLOW_UI_HTML_THEME_TOKENS]);
        const api = [...sheet.querySelectorAll('.api code')].map((code) => code.textContent);
        expect(api).to.include('flowUi.send(\'action\', { ... })');
        expect(api).to.include('data-bind="path"');
        expect(sheet.textContent).to.contain(flowsEn.interface_editor.html_api_send);
    });

    it('starter example replaces the draft and the test state; apply hands the draft back', async () => {
        let applied = null;
        const modal = await openModal({ source: BLOCK.source, block: BLOCK, sampleState: {}, statePaths: [], onApply: (source) => { applied = source; } });
        const starter = [...modal.renderRoot.querySelectorAll('platform-button')].find((button) => button.textContent.includes(flowsEn.interface_editor.html_insert_example));
        expect(starter, 'starter button').to.exist;
        starter.click();
        await elementUpdated(modal);
        expect(modal._draft).to.equal(flowsEn.interface_editor.default_text_html_source);
        expect(modal._draft).to.contain('flowUi.onChange(').and.contain('flowUi.send(').and.contain('flowUi.setValue(').and.contain('data-bind=').and.contain('data-show=');
        expect(JSON.parse(modal._stateText)).to.deep.equal(JSON.parse(flowsEn.interface_editor.html_example_state));
        modal._apply();
        expect(applied).to.equal(flowsEn.interface_editor.default_text_html_source);
    });

    it('shows a JSON error instead of the preview while the test state is invalid', async () => {
        const modal = await openModal({ source: BLOCK.source, block: BLOCK, sampleState: SAMPLE_STATE, statePaths: [], onApply: () => {} });
        modal._stateText = '{ not json';
        await elementUpdated(modal);
        expect(modal.renderRoot.querySelector('.stage flow-ui-html-block')).to.equal(null);
        expect(modal.renderRoot.querySelector('.log .entry[data-kind="error"]')).to.exist;
    });
});
