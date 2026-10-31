/**
 * platform-menu — пункты, выбор, клавиатура, доступность.
 */

import { fixture, html, expect, oneEvent, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import '@platform/lib/components/platform-menu.js';

const ITEMS = [
    { id: 'section', kind: 'section', label: 'Действия' },
    { id: 'rename', label: 'Переименовать', icon: 'edit', hint: 'F2' },
    { id: 'duplicate', label: 'Дублировать', icon: 'copy' },
    { id: 'sep', kind: 'separator' },
    { id: 'archive', label: 'В архив', disabled: true },
    { id: 'delete', label: 'Удалить', icon: 'trash', danger: true },
];

async function mountMenu(items = ITEMS) {
    const el = await fixture(html`<platform-menu .items=${items}></platform-menu>`);
    await elementUpdated(el);
    return el;
}

function itemButtons(el) {
    return Array.from(el.shadowRoot.querySelectorAll('.item'));
}

describe('platform-menu', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
    });

    it('рендерит пункты, разделители и заголовки секций', async () => {
        const el = await mountMenu();

        expect(itemButtons(el).length).to.equal(4);
        expect(el.shadowRoot.querySelectorAll('.separator').length).to.equal(1);
        expect(el.shadowRoot.querySelector('.section').textContent.trim()).to.equal('Действия');
    });

    it('показывает подпись, иконку и горячую клавишу', async () => {
        const el = await mountMenu();
        const rename = el.shadowRoot.querySelector('[data-menu-item="rename"]');

        expect(rename.querySelector('.label').textContent.trim()).to.equal('Переименовать');
        expect(rename.querySelector('.hint').textContent.trim()).to.equal('F2');
        expect(rename.querySelector('platform-icon')).to.exist;
    });

    it('клик по пункту эмитит menu-select с id', async () => {
        const el = await mountMenu();

        const selected = oneEvent(el, 'menu-select');
        el.shadowRoot.querySelector('[data-menu-item="duplicate"]').click();
        const event = await selected;

        expect(event.detail.id).to.equal('duplicate');
        expect(event.detail.item.label).to.equal('Дублировать');
    });

    it('отключённый пункт не выбирается', async () => {
        const el = await mountMenu();
        let fired = false;
        el.addEventListener('menu-select', () => {
            fired = true;
        });

        el.shadowRoot.querySelector('[data-menu-item="archive"]').click();
        await elementUpdated(el);

        expect(fired).to.be.false;
    });

    it('разрушающее действие помечено отдельным классом', async () => {
        const el = await mountMenu();

        expect(
            el.shadowRoot.querySelector('[data-menu-item="delete"]').classList.contains('is-danger'),
        ).to.be.true;
    });

    it('focusFirstItem встаёт на первый доступный пункт', async () => {
        const el = await mountMenu();

        el.focusFirstItem();
        await elementUpdated(el);

        const active = el.shadowRoot.querySelector('.item.is-active');
        expect(active.dataset.menuItem).to.equal('rename');
    });

    it('стрелка вниз идёт по пунктам, пропуская разделители и отключённые', async () => {
        const el = await mountMenu();
        el.focusFirstItem();
        await elementUpdated(el);

        const menu = el.shadowRoot.querySelector('[role="menu"]');
        menu.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
        await elementUpdated(el);
        expect(el.shadowRoot.querySelector('.item.is-active').dataset.menuItem).to.equal('duplicate');

        menu.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
        await elementUpdated(el);
        // archive отключён, поэтому следующий доступный — delete
        expect(el.shadowRoot.querySelector('.item.is-active').dataset.menuItem).to.equal('delete');
    });

    it('стрелка вниз с последнего пункта возвращается к первому', async () => {
        const el = await mountMenu();
        const menu = el.shadowRoot.querySelector('[role="menu"]');
        el.focusFirstItem();
        await elementUpdated(el);

        for (let step = 0; step < 3; step += 1) {
            menu.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
            await elementUpdated(el);
        }

        expect(el.shadowRoot.querySelector('.item.is-active').dataset.menuItem).to.equal('rename');
    });

    it('стрелка вверх идёт в обратном порядке', async () => {
        const el = await mountMenu();
        const menu = el.shadowRoot.querySelector('[role="menu"]');
        el.focusFirstItem();
        await elementUpdated(el);

        menu.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowUp', bubbles: true }));
        await elementUpdated(el);

        expect(el.shadowRoot.querySelector('.item.is-active').dataset.menuItem).to.equal('delete');
    });

    it('Home и End переходят к краям списка', async () => {
        const el = await mountMenu();
        const menu = el.shadowRoot.querySelector('[role="menu"]');
        el.focusFirstItem();
        await elementUpdated(el);

        menu.dispatchEvent(new KeyboardEvent('keydown', { key: 'End', bubbles: true }));
        await elementUpdated(el);
        expect(el.shadowRoot.querySelector('.item.is-active').dataset.menuItem).to.equal('delete');

        menu.dispatchEvent(new KeyboardEvent('keydown', { key: 'Home', bubbles: true }));
        await elementUpdated(el);
        expect(el.shadowRoot.querySelector('.item.is-active').dataset.menuItem).to.equal('rename');
    });

    it('Enter выбирает активный пункт', async () => {
        const el = await mountMenu();
        const menu = el.shadowRoot.querySelector('[role="menu"]');
        el.focusFirstItem();
        await elementUpdated(el);

        const selected = oneEvent(el, 'menu-select');
        menu.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
        const event = await selected;

        expect(event.detail.id).to.equal('rename');
    });

    it('набор букв переводит фокус на подходящий пункт', async () => {
        const el = await mountMenu();
        const menu = el.shadowRoot.querySelector('[role="menu"]');
        el.focusFirstItem();
        await elementUpdated(el);

        menu.dispatchEvent(new KeyboardEvent('keydown', { key: 'у', bubbles: true }));
        await elementUpdated(el);

        expect(el.shadowRoot.querySelector('.item.is-active').dataset.menuItem).to.equal('delete');
    });

    it('роли и tabindex соответствуют меню', async () => {
        const el = await mountMenu();
        el.focusFirstItem();
        await elementUpdated(el);

        expect(el.shadowRoot.querySelector('[role="menu"]')).to.exist;
        expect(itemButtons(el).every((node) => node.getAttribute('role') === 'menuitem')).to.be.true;
        const active = el.shadowRoot.querySelector('.item.is-active');
        expect(active.getAttribute('tabindex')).to.equal('0');
        const others = itemButtons(el).filter((node) => node !== active);
        expect(others.every((node) => node.getAttribute('tabindex') === '-1')).to.be.true;
    });

    it('отключённый пункт помечен aria-disabled', async () => {
        const el = await mountMenu();

        expect(
            el.shadowRoot.querySelector('[data-menu-item="archive"]').getAttribute('aria-disabled'),
        ).to.equal('true');
    });

    it('отмеченный пункт показывает галочку', async () => {
        const el = await mountMenu([{ id: 'ru', label: 'Русский', selected: true }]);

        expect(el.shadowRoot.querySelector('.check')).to.exist;
    });

    it('пустой список показывает слот вместо пунктов', async () => {
        const el = await mountMenu([]);

        expect(el.shadowRoot.querySelector('.empty')).to.exist;
        expect(itemButtons(el).length).to.equal(0);
    });
});
