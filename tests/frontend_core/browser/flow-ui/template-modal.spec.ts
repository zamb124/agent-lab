/**
 * Галерея шаблонов: карточки из ``GET /flow-ui/templates`` (реальная галерея ``templates.json``),
 * фильтр по категории и поиску, детальный просмотр с живым холстом каждого шаблона без ошибок
 * блоков, «Применить» отдаёт документ в ``onApply`` и закрывает модалку.
 */

import { elementUpdated, expect, fixture, fixtureCleanup, html, waitUntil } from '../helpers/render.js';
import { bootstrapTestBus, resetPlatformState } from '../helpers/reset.js';
import { CoreEvents, getPlatformBus } from '@platform/lib/events/index.js';
import { platformWs } from '@platform/lib/events/effects/ws.effect.js';
import { blockElement, pageRenderRoot } from '@platform/lib/flow-ui/editor/selection.js';
import { iterBlocks } from '@platform/lib/flow-ui/runtime/flow-ui-store.js';
import flowsEn from '../../../../core/i18n/translations/en/flows.json' with { type: 'json' };
import templatesPage from '../../../fixtures/flow_ui/templates.json' with { type: 'json' };
import { flowUiTemplatesOp } from '../../../../apps/flows/ui/events/resources/flow-ui.resource.js';
import '@platform/lib/components/platform-modal-stack.js';
import '../../../../apps/flows/ui/modals/flows-interface-template-modal.js';

const TAG = 'flows-interface-template-modal';

async function seedTranslations(bus) {
    await waitUntil(
        () => {
            const i18n = bus.getState().i18n;
            if (i18n.loading) {
                return false;
            }
            const bundle = i18n.translations[i18n.locale];
            return Boolean(bundle && typeof bundle === 'object' && bundle.platform);
        },
        'i18n bootstrap settled',
        { timeout: 15_000 },
    );
    const locale = bus.getState().i18n.locale;
    const previous = bus.getState().i18n.translations[locale] || {};
    bus.dispatch(CoreEvents.I18N_LOCALE_LOADED, { locale, bundle: { ...previous, flows: flowsEn } }, { source: 'system' });
    bus.dispatch(CoreEvents.I18N_LOCALE_CHANGED, { locale, default_namespace: 'flows' }, { source: 'system' });
}

async function openModal(props) {
    const stack = await fixture(html`<platform-modal-stack></platform-modal-stack>`);
    getPlatformBus().dispatch(CoreEvents.UI_MODAL_OPEN, { kind: 'flows.interface_template', props });
    await elementUpdated(stack);
    const modal = [...document.querySelectorAll(TAG)].at(-1);
    expect(modal, 'modal mounted').to.exist;
    await waitUntil(() => modal.renderRoot.querySelectorAll('flows-interface-template-card').length === templatesPage.total, 'gallery did not load', { timeout: 8000 });
    return modal;
}

function cards(modal) {
    return [...modal.renderRoot.querySelectorAll('flows-interface-template-card')].map((card) => card.template.template_id);
}

function chip(modal, category) {
    return [...modal.renderRoot.querySelectorAll('.chips .chip')].find((node) => node.textContent === flowsEn.interface_editor[`template_category_${category}`]);
}

function button(modal, label) {
    return [...modal.renderRoot.querySelectorAll('platform-button')].find((node) => node.textContent.trim() === label);
}

describe('flows-interface-template-modal', function () {
    this.timeout(30_000);

    let originalWsRequest;

    beforeEach(async () => {
        resetPlatformState();
        bootstrapTestBus({ factories: [flowUiTemplatesOp] });
        await seedTranslations(getPlatformBus());
        originalWsRequest = platformWs.request;
        platformWs.request = async (opts) => {
            if (opts.type === 'flows/flow_ui/templates_requested') {
                return templatesPage;
            }
            return originalWsRequest(opts);
        };
    });

    afterEach(() => {
        platformWs.request = originalWsRequest;
        fixtureCleanup();
        for (const leftover of document.querySelectorAll(TAG)) leftover.remove();
    });

    it('lists the whole gallery and filters by category and search', async () => {
        const modal = await openModal({ onApply: () => {} });
        expect(cards(modal)).to.deep.equal(templatesPage.items.map((template) => template.template_id));
        expect(chip(modal, 'all').getAttribute('aria-pressed')).to.equal('true');

        chip(modal, 'forms').click();
        await elementUpdated(modal);
        expect(cards(modal)).to.deep.equal(templatesPage.items.filter((template) => template.category === 'forms').map((template) => template.template_id));

        chip(modal, 'all').dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
        await elementUpdated(modal);
        expect(cards(modal)).to.have.length(templatesPage.total);

        modal._query = '  REQUEST FORM ';
        await elementUpdated(modal);
        expect(cards(modal)).to.deep.equal(['lead_form']);

        modal._query = 'avatar';
        await elementUpdated(modal);
        expect(cards(modal)).to.deep.equal(templatesPage.items.filter((template) => template.description.toLowerCase().includes('avatar')).map((template) => template.template_id));

        modal._query = 'nothing like this';
        await elementUpdated(modal);
        expect(cards(modal)).to.deep.equal([]);
        expect(modal.renderRoot.querySelector('.empty').textContent).to.contain(flowsEn.interface_editor.template_empty);
    });

    it('renders every gallery template on the detail canvas without block errors', async () => {
        const modal = await openModal({ onApply: () => {} });
        for (const template of templatesPage.items) {
            modal._detailId = template.template_id;
            await elementUpdated(modal);
            const canvas = modal.renderRoot.querySelector('.detail-preview platform-flow-ui');
            expect(canvas, template.template_id).to.exist;
            const expected = [...iterBlocks(template.document.pages[0].blocks)].map((block) => block.block_id);
            await waitUntil(
                () => pageRenderRoot(canvas) !== null && expected.every((id) => blockElement(canvas, id) !== null),
                `${template.template_id}: blocks did not render`,
                { timeout: 8000 },
            );
            expect(pageRenderRoot(canvas).querySelectorAll('[data-render-error]'), template.template_id).to.have.length(0);
            expect(modal.renderRoot.querySelector('.detail-title').textContent).to.equal(template.title);
            expect(modal.renderRoot.querySelector('.detail-side .chip').textContent).to.equal(flowsEn.interface_editor[`template_category_${template.category}`]);
            modal._detailId = '';
            await elementUpdated(modal);
        }
    });

    it('opens the detail from a card, goes back, and applies the document once', async () => {
        const applied = [];
        const modal = await openModal({ onApply: (document) => applied.push(document) });
        const card = modal.renderRoot.querySelector('flows-interface-template-card');
        card.dispatchEvent(new CustomEvent('template-select', { detail: { templateId: 'dashboard' }, bubbles: true, composed: true }));
        await elementUpdated(modal);
        expect(modal._detailId).to.equal('dashboard');
        expect(modal.renderRoot.querySelector('.hint').textContent).to.equal(flowsEn.interface_editor.template_replace_hint);

        button(modal, flowsEn.interface_editor.template_back).click();
        await elementUpdated(modal);
        expect(modal._detailId).to.equal('');
        expect(cards(modal)).to.have.length(templatesPage.total);

        modal._detailId = 'dashboard';
        await elementUpdated(modal);
        button(modal, flowsEn.interface_editor.template_apply).click();
        await elementUpdated(modal);
        const dashboard = templatesPage.items.find((template) => template.template_id === 'dashboard');
        expect(applied).to.deep.equal([dashboard.document]);
        await waitUntil(() => getPlatformBus().getState().modals.stack.length === 0, 'modal did not close', { timeout: 4000 });
    });

    it('refuses to apply without an onApply callback', async () => {
        const modal = await openModal({});
        expect(() => modal._apply(templatesPage.items[0])).to.throw(/onApply callback is required/);
    });
});
