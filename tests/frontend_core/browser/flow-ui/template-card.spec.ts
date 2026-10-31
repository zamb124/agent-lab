/**
 * Карточка шаблона галереи: живой уменьшенный рендер ``<platform-flow-ui editing>`` появляется
 * при попадании во viewport, выбор — событие ``template-select {templateId}``.
 */

import { elementUpdated, expect, fixture, fixtureCleanup, html, oneEvent, waitUntil } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { blockElement } from '@platform/lib/flow-ui/editor/selection.js';
import '../../../../apps/flows/ui/components/interface-editor/flows-interface-template-card.js';
import {q, qs, type TestEl} from '../helpers/dom.js';

const TEMPLATE = {
    template_id: 'lead_form',
    title: 'Форма заявки',
    description: 'Имя, email и кнопка отправки',
    icon: 'file-text',
    document: {
        start_page_id: 'main',
        pages: [{
            page_id: 'main',
            title: 'Заявка',
            blocks: [
                { block_id: 'title', type: 'heading', visible_when: null, text: 'Оставьте заявку', level: 2 },
                { block_id: 'send', type: 'button', visible_when: null, label: 'Отправить', action: { name: 'submit', payload: {} }, variant: 'primary' },
            ],
        }],
    },
};

describe('flows-interface-template-card', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus({ factories: [] });
    });

    afterEach(() => fixtureCleanup());

    it('mounts the live preview once visible and renders title and description', async () => {
        const element = await fixture<TestEl>(html`<flows-interface-template-card .template=${TEMPLATE} style="display:block;width:320px"></flows-interface-template-card>`);
        await waitUntil(() => q(element.renderRoot, 'platform-flow-ui') !== null, 'preview did not mount');
        const preview = q(element.renderRoot, 'platform-flow-ui');
        expect(preview!.editing).to.equal(true);
        await waitUntil(() => blockElement(preview, 'title') !== null, 'preview page did not render');
        expect(blockElement(preview, 'title')!.textContent).to.contain('Оставьте заявку');
        expect(qs(element.renderRoot, '.title').textContent).to.contain('Форма заявки');
        expect(qs(element.renderRoot, '.description').textContent).to.equal('Имя, email и кнопка отправки');
    });

    it('emits template-select with the template id on click and keyboard', async () => {
        const element = await fixture<TestEl>(html`<flows-interface-template-card .template=${TEMPLATE}></flows-interface-template-card>`);
        const card = qs(element.renderRoot, '.card');
        const clicked = oneEvent(element, 'template-select');
        (card as TestEl).click();
        expect((await clicked).detail).to.deep.equal({ templateId: 'lead_form' });

        const pressed = oneEvent(element, 'template-select');
        card.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
        expect((await pressed).detail).to.deep.equal({ templateId: 'lead_form' });

        element.selected = true;
        await elementUpdated(element);
        expect(element.hasAttribute('selected')).to.equal(true);
    });
});
