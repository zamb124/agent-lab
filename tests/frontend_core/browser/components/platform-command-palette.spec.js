/**
 * platform-command-palette — Cmd+K, поиск, клавиатура, выбор.
 */

import { fixture, html, expect, oneEvent, elementUpdated, aTimeout } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import '@platform/lib/components/platform-command-palette.js';

const ITEMS = [
    { id: 'p1', label: 'Онбординг', group: 'Страницы', icon: 'file' },
    { id: 'p2', label: 'Регламент отпусков', group: 'Страницы' },
    { id: 'a1', label: 'Создать страницу', group: 'Действия', hint: 'N' },
];

async function mountPalette(provider) {
    const el = await fixture(html`
        <platform-command-palette .provider=${provider ?? (async () => ITEMS)}></platform-command-palette>
    `);
    await elementUpdated(el);
    return el;
}

function itemsOf(el) {
    return Array.from(el.shadowRoot.querySelectorAll('.item'));
}

async function openPalette(el) {
    el.show();
    await elementUpdated(el);
    await aTimeout(0);
    await elementUpdated(el);
}

describe('platform-command-palette', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
    });

    it('закрыта по умолчанию', async () => {
        const el = await mountPalette();

        expect(el.open).to.be.false;
        expect(el.shadowRoot.querySelector('.panel')).to.be.null;
    });

    it('Cmd+K открывает палитру', async () => {
        const el = await mountPalette();

        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', metaKey: true, bubbles: true }));
        await elementUpdated(el);

        expect(el.open).to.be.true;
    });

    it('Ctrl+K тоже открывает палитру', async () => {
        const el = await mountPalette();

        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', ctrlKey: true, bubbles: true }));
        await elementUpdated(el);

        expect(el.open).to.be.true;
    });

    it('повторное нажатие закрывает палитру', async () => {
        const el = await mountPalette();

        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', metaKey: true, bubbles: true }));
        await elementUpdated(el);
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', metaKey: true, bubbles: true }));
        await elementUpdated(el);

        expect(el.open).to.be.false;
    });

    it('при открытии показывает результаты пустого запроса', async () => {
        const el = await mountPalette();

        await openPalette(el);

        expect(itemsOf(el).length).to.equal(3);
    });

    it('группирует результаты по секциям', async () => {
        const el = await mountPalette();
        await openPalette(el);

        const groups = Array.from(el.shadowRoot.querySelectorAll('.group')).map((n) => n.textContent.trim());
        expect(groups).to.deep.equal(['Страницы', 'Действия']);
    });

    it('ввод запускает поиск через провайдер', async () => {
        const queries = [];
        const el = await mountPalette(async (query) => {
            queries.push(query);
            return ITEMS.filter((item) => item.label.toLowerCase().includes(query.toLowerCase()));
        });
        await openPalette(el);

        const input = el.shadowRoot.querySelector('input');
        input.value = 'онб';
        input.dispatchEvent(new Event('input', { bubbles: true }));
        await aTimeout(200);
        await elementUpdated(el);

        expect(queries).to.include('онб');
        expect(itemsOf(el).length).to.equal(1);
    });

    it('поздний ответ на устаревший запрос не затирает актуальные результаты', async () => {
        let call = 0;
        const el = await mountPalette(async (query) => {
            call += 1;
            if (call === 2) {
                // Первый набранный префикс отвечает медленно.
                await aTimeout(120);
                return [{ id: 'stale', label: 'Устаревший результат' }];
            }
            return [{ id: 'fresh', label: `Актуальный ${query}` }];
        });
        await openPalette(el);

        const input = el.shadowRoot.querySelector('input');
        input.value = 'о';
        input.dispatchEvent(new Event('input', { bubbles: true }));
        await aTimeout(140);
        input.value = 'он';
        input.dispatchEvent(new Event('input', { bubbles: true }));
        await aTimeout(300);
        await elementUpdated(el);

        const labels = itemsOf(el).map((node) => node.textContent.trim());
        expect(labels.some((label) => label.includes('Устаревший'))).to.be.false;
    });

    it('стрелки двигают активный пункт по кругу', async () => {
        const el = await mountPalette();
        await openPalette(el);
        const input = el.shadowRoot.querySelector('input');

        input.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
        await elementUpdated(el);
        expect(el.shadowRoot.querySelector('.item.is-active').dataset.paletteItem).to.equal('p2');

        input.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowUp', bubbles: true }));
        await elementUpdated(el);
        expect(el.shadowRoot.querySelector('.item.is-active').dataset.paletteItem).to.equal('p1');

        input.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowUp', bubbles: true }));
        await elementUpdated(el);
        expect(el.shadowRoot.querySelector('.item.is-active').dataset.paletteItem).to.equal('a1');
    });

    it('Enter выбирает активный пункт и закрывает палитру', async () => {
        const el = await mountPalette();
        await openPalette(el);

        const selected = oneEvent(el, 'palette-select');
        el.shadowRoot.querySelector('input')
            .dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
        const event = await selected;
        await elementUpdated(el);

        expect(event.detail.id).to.equal('p1');
        expect(el.open).to.be.false;
    });

    it('клик по пункту выбирает его', async () => {
        const el = await mountPalette();
        await openPalette(el);

        const selected = oneEvent(el, 'palette-select');
        el.shadowRoot.querySelector('[data-palette-item="a1"]').click();
        const event = await selected;

        expect(event.detail.item.label).to.equal('Создать страницу');
    });

    it('Escape закрывает палитру', async () => {
        const el = await mountPalette();
        await openPalette(el);

        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
        await elementUpdated(el);

        expect(el.open).to.be.false;
    });

    it('клик по затемнению закрывает палитру', async () => {
        const el = await mountPalette();
        await openPalette(el);

        el.shadowRoot.querySelector('.scrim').click();
        await elementUpdated(el);

        expect(el.open).to.be.false;
    });

    it('пустая выдача показывает заглушку', async () => {
        const el = await mountPalette(async () => []);
        await openPalette(el);

        expect(el.shadowRoot.querySelector('.status')).to.exist;
        expect(itemsOf(el).length).to.equal(0);
    });

    it('без провайдера падает, а не молчит', async () => {
        const el = await fixture(html`<platform-command-palette></platform-command-palette>`);
        let raised = null;
        try {
            await el._runSearch('');
        } catch (error) {
            raised = error;
        }

        expect(raised).to.not.equal(null);
    });
});
