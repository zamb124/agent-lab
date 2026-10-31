/**
 * platform-menu — пункты, выбор, клавиатура, доступность.
 */

import { fixture, html, expect, oneEvent, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import '@platform/lib/components/platform-menu.js';
import { qs, qsa, shadow, type TestEl } from '../helpers/dom.js';
import type { PlatformMenuItem } from '@platform/lib/components/platform-menu.js';

const ITEMS: PlatformMenuItem[] = [
    { id: 'section', kind: 'section', label: 'Действия' },
    { id: 'rename', label: 'Переименовать', icon: 'edit', hint: 'F2' },
    { id: 'duplicate', label: 'Дублировать', icon: 'copy' },
    { id: 'sep', kind: 'separator' },
    { id: 'archive', label: 'В архив', disabled: true },
    { id: 'delete', label: 'Удалить', icon: 'trash', danger: true },
];

async function mountMenu(items: PlatformMenuItem[] = ITEMS) {
    const el = await fixture<TestEl>(html`<platform-menu .items=${items}></platform-menu>`);
    await elementUpdated(el);
    return el;
}

function itemButtons(el: any) {
    return Array.from(qsa(shadow(el), '.item'));
}

describe('platform-menu', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
    });

    it('рендерит пункты, разделители и заголовки секций', async () => {
        const el = await mountMenu();

        expect(itemButtons(el).length).to.equal(4);
        expect(qsa(shadow(el), '.separator').length).to.equal(1);
        expect(qs(shadow(el), '.section').textContent.trim()).to.equal('Действия');
    });

    it('показывает подпись, иконку и горячую клавишу', async () => {
        const el = await mountMenu();
        const rename = qs(shadow(el), '[data-menu-item="rename"]');

        expect(qs(rename!, '.label').textContent.trim()).to.equal('Переименовать');
        expect(qs(rename!, '.hint').textContent.trim()).to.equal('F2');
        expect(qs(rename!, 'platform-icon')).to.exist;
    });

    it('клик по пункту эмитит menu-select с id', async () => {
        const el = await mountMenu();

        const selected = oneEvent(el, 'menu-select');
        qs(shadow(el), '[data-menu-item="duplicate"]').click();
        const event = await selected;

        expect((event as CustomEvent).detail.id).to.equal('duplicate');
        expect((event as CustomEvent).detail.item.label).to.equal('Дублировать');
    });

    it('отключённый пункт не выбирается', async () => {
        const el = await mountMenu();
        let fired = false;
        el.addEventListener('menu-select', () => {
            fired = true;
        });

        qs(shadow(el), '[data-menu-item="archive"]').click();
        await elementUpdated(el);

        expect(fired).to.be.false;
    });

    it('разрушающее действие помечено отдельным классом', async () => {
        const el = await mountMenu();

        expect(
            qs(shadow(el), '[data-menu-item="delete"]').classList.contains('is-danger'),
        ).to.be.true;
    });

    it('focusFirstItem встаёт на первый доступный пункт', async () => {
        const el = await mountMenu();

        el.focusFirstItem();
        await elementUpdated(el);

        const active = qs(shadow(el), '.item.is-active');
        expect((active as TestEl).dataset.menuItem).to.equal('rename');
    });

    it('стрелка вниз идёт по пунктам, пропуская разделители и отключённые', async () => {
        const el = await mountMenu();
        el.focusFirstItem();
        await elementUpdated(el);

        const menu = qs(shadow(el), '[role="menu"]');
        menu.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
        await elementUpdated(el);
        expect(qs(shadow(el), '.item.is-active').dataset.menuItem).to.equal('duplicate');

        menu.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
        await elementUpdated(el);
        // archive отключён, поэтому следующий доступный — delete
        expect(qs(shadow(el), '.item.is-active').dataset.menuItem).to.equal('delete');
    });

    it('стрелка вниз с последнего пункта возвращается к первому', async () => {
        const el = await mountMenu();
        const menu = qs(shadow(el), '[role="menu"]');
        el.focusFirstItem();
        await elementUpdated(el);

        for (let step = 0; step < 3; step += 1) {
            menu.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
            await elementUpdated(el);
        }

        expect(qs(shadow(el), '.item.is-active').dataset.menuItem).to.equal('rename');
    });

    it('стрелка вверх идёт в обратном порядке', async () => {
        const el = await mountMenu();
        const menu = qs(shadow(el), '[role="menu"]');
        el.focusFirstItem();
        await elementUpdated(el);

        menu.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowUp', bubbles: true }));
        await elementUpdated(el);

        expect(qs(shadow(el), '.item.is-active').dataset.menuItem).to.equal('delete');
    });

    it('Home и End переходят к краям списка', async () => {
        const el = await mountMenu();
        const menu = qs(shadow(el), '[role="menu"]');
        el.focusFirstItem();
        await elementUpdated(el);

        menu.dispatchEvent(new KeyboardEvent('keydown', { key: 'End', bubbles: true }));
        await elementUpdated(el);
        expect(qs(shadow(el), '.item.is-active').dataset.menuItem).to.equal('delete');

        menu.dispatchEvent(new KeyboardEvent('keydown', { key: 'Home', bubbles: true }));
        await elementUpdated(el);
        expect(qs(shadow(el), '.item.is-active').dataset.menuItem).to.equal('rename');
    });

    it('Enter выбирает активный пункт', async () => {
        const el = await mountMenu();
        const menu = qs(shadow(el), '[role="menu"]');
        el.focusFirstItem();
        await elementUpdated(el);

        const selected = oneEvent(el, 'menu-select');
        menu.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
        const event = await selected;

        expect((event as CustomEvent).detail.id).to.equal('rename');
    });

    it('набор букв переводит фокус на подходящий пункт', async () => {
        const el = await mountMenu();
        const menu = qs(shadow(el), '[role="menu"]');
        el.focusFirstItem();
        await elementUpdated(el);

        menu.dispatchEvent(new KeyboardEvent('keydown', { key: 'у', bubbles: true }));
        await elementUpdated(el);

        expect(qs(shadow(el), '.item.is-active').dataset.menuItem).to.equal('delete');
    });

    it('роли и tabindex соответствуют меню', async () => {
        const el = await mountMenu();
        el.focusFirstItem();
        await elementUpdated(el);

        expect(qs(shadow(el), '[role="menu"]')).to.exist;
        expect(itemButtons(el).every((node) => node.getAttribute('role') === 'menuitem')).to.be.true;
        const active = qs(shadow(el), '.item.is-active');
        expect(active.getAttribute('tabindex')).to.equal('0');
        const others = itemButtons(el).filter((node) => node !== active);
        expect(others.every((node) => node.getAttribute('tabindex') === '-1')).to.be.true;
    });

    it('отключённый пункт помечен aria-disabled', async () => {
        const el = await mountMenu();

        expect(
            qs(shadow(el), '[data-menu-item="archive"]').getAttribute('aria-disabled'),
        ).to.equal('true');
    });

    it('отмеченный пункт показывает галочку', async () => {
        const el = await mountMenu([{ id: 'ru', label: 'Русский', selected: true }]);

        expect(qs(shadow(el), '.check')).to.exist;
    });

    it('пустой список показывает слот вместо пунктов', async () => {
        const el = await mountMenu([]);

        expect(qs(shadow(el), '.empty')).to.exist;
        expect(itemButtons(el).length).to.equal(0);
    });
});
