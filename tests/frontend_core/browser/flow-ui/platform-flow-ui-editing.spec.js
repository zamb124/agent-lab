/**
 * Холст редактора: ``<platform-flow-ui editing>`` рендерит документ грамматики без сети,
 * подставляет тестовый state в шаблоны, помечает контейнеры и выделение, переключает страницы.
 */

import { elementUpdated, expect, fixture, fixtureCleanup, html, waitUntil } from '../helpers/render.js';
import '@platform/lib/flow-ui/components/platform-flow-ui.js';
import { blockElement, pageRenderRoot } from '@platform/lib/flow-ui/editor/selection.js';

const DOCUMENT = {
    start_page_id: 'main',
    pages: [
        {
            page_id: 'main',
            title: 'Заявка',
            blocks: [
                { block_id: 'title', type: 'heading', visible_when: null, text: 'Заявка {customer.name}', level: 2 },
                {
                    block_id: 'form',
                    type: 'section',
                    visible_when: null,
                    title: 'Контакты',
                    blocks: [
                        { block_id: 'email', type: 'text_input', visible_when: null, field: 'email', label: 'Email', required: true, error_message: '', action: null, placeholder: '', default: '', pattern: '', multiline: false, secret: false },
                    ],
                },
                { block_id: 'hidden', type: 'text', visible_when: { path: 'never', equals: null }, markdown: 'скрытый в рантайме' },
                { block_id: 'send', type: 'button', visible_when: null, label: 'Отправить', action: { name: 'submit', payload: {} }, variant: 'primary' },
            ],
        },
        { page_id: 'done', title: 'Готово', blocks: [{ block_id: 'thanks', type: 'text', visible_when: null, markdown: 'Спасибо, {email}' }] },
    ],
};

async function mountEditing(sampleState = {}) {
    const element = await fixture(html`<platform-flow-ui editing .initialDocument=${DOCUMENT} .sampleState=${sampleState}></platform-flow-ui>`);
    await waitUntil(() => pageRenderRoot(element) !== null && blockElement(element, 'title') !== null, 'page did not render');
    return element;
}

describe('platform-flow-ui editing canvas', () => {
    afterEach(() => fixtureCleanup());

    it('renders grammar blocks with sample state and keeps hidden blocks visible for the author', async () => {
        const element = await mountEditing({ customer: { name: 'Анна' } });
        expect(blockElement(element, 'title').textContent).to.contain('Заявка Анна');
        expect(blockElement(element, 'hidden')).to.not.equal(null);
        expect(blockElement(element, 'form').querySelector('[data-container-key="form"]')).to.not.equal(null);
        expect(blockElement(element, 'email')).to.not.equal(null);
        expect(element.store.document).to.equal(DOCUMENT);
        expect(element.store.state).to.deep.equal({ customer: { name: 'Анна' } });
    });

    it('shows unresolved template paths as-is on the canvas', async () => {
        const element = await mountEditing({});
        expect(blockElement(element, 'title').textContent).to.contain('Заявка {customer.name}');
    });

    it('marks the selected block and navigates between pages', async () => {
        const element = await mountEditing({});
        element.selectedBlockId = 'send';
        await elementUpdated(element);
        await waitUntil(() => blockElement(element, 'send')?.dataset.selected === 'true', 'selection did not render');
        element.navigate('done');
        await waitUntil(() => blockElement(element, 'thanks') !== null, 'second page did not render');
        expect(element.store.pageId).to.equal('done');
        expect(blockElement(element, 'title')).to.equal(null);
        expect(() => element.navigate('missing')).to.throw(/unknown page_id/);
    });
});
