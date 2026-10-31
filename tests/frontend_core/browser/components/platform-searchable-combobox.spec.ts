/**
 * platform-searchable-combobox — фильтрация, выбор, создание, слой списка.
 */

import { fixture, html, expect, oneEvent, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import '@platform/lib/components/platform-searchable-combobox.js';
import { qs, qsa, shadow, type TestEl } from '../helpers/dom.js';

const OPTIONS = [
    { value: 'alpha', label: 'Альфа' },
    { value: 'beta', label: 'Бета' },
    { value: 'gamma', label: 'Гамма' },
];

async function mountCombobox(props: any = {}) {
    const el = await fixture<TestEl>(html`
        <platform-searchable-combobox
            .options=${props.options ?? OPTIONS}
            .value=${(props as TestEl).value ?? ''}
            createLabel=${props.createLabel ?? ''}
            placeholder="Выберите"
        ></platform-searchable-combobox>
    `);
    await elementUpdated(el);
    return el;
}

function inputOf(el: any) {
    return qs(shadow(el), 'input.field-pill-input');
}

function optionsOf(el: any) {
    return Array.from(qsa(shadow(el), 'li.item'));
}

describe('platform-searchable-combobox', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
    });

    it('список закрыт до фокуса', async () => {
        const el = await mountCombobox();

        expect(optionsOf(el).length).to.equal(0);
    });

    it('фокус открывает список со всеми опциями', async () => {
        const el = await mountCombobox();

        inputOf(el).focus();
        await elementUpdated(el);

        expect(optionsOf(el).length).to.equal(3);
    });

    it('список показывается в top layer, а не обрезается родителем', async () => {
        const el = await mountCombobox();
        inputOf(el).focus();
        await elementUpdated(el);

        const popover = qs(shadow(el), 'platform-popover');
        expect(popover.matches(':popover-open')).to.be.true;
    });

    it('ввод фильтрует опции по подписи', async () => {
        const el = await mountCombobox();
        const input = inputOf(el);
        input.focus();
        await elementUpdated(el);

        (input as TestEl).value = 'Бет';
        input.dispatchEvent(new Event('input', { bubbles: true }));
        await elementUpdated(el);

        const labels = optionsOf(el).map((node) => node.textContent.trim());
        expect(labels.length).to.equal(1);
        expect(labels[0]).to.contain('Бета');
    });

    it('выбор опции эмитит change со значением', async () => {
        const el = await mountCombobox();
        inputOf(el).focus();
        await elementUpdated(el);

        const changed = oneEvent(el, 'change');
        optionsOf(el)[1]!.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, composed: true }));
        const event = await changed;

        expect((event as CustomEvent).detail.value).to.equal('beta');
    });

    it('строка создания появляется при заданной подписи', async () => {
        const el = await mountCombobox({ createLabel: 'Создать…' });
        inputOf(el).focus();
        await elementUpdated(el);

        const createRow = qs(shadow(el), 'li[data-create="true"]');
        expect(createRow).to.exist;
        expect(createRow.textContent.trim()).to.equal('Создать…');
    });

    it('строка создания эмитит create с запросом', async () => {
        const el = await mountCombobox({ createLabel: 'Создать…' });
        inputOf(el).focus();
        await elementUpdated(el);

        const created = oneEvent(el, 'create');
        qs(shadow(el), 'li[data-create="true"]')
            .dispatchEvent(new MouseEvent('mousedown', { bubbles: true, composed: true }));
        const event = await created;

        expect((event as CustomEvent).detail).to.have.property('query');
    });

    it('Escape закрывает список через попап', async () => {
        const el = await mountCombobox();
        inputOf(el).focus();
        await elementUpdated(el);

        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
        await elementUpdated(el);

        expect(optionsOf(el).length).to.equal(0);
    });

    it('ширина списка повторяет ширину поля', async () => {
        const el = await mountCombobox();
        inputOf(el).focus();
        await elementUpdated(el);

        const field = qs(shadow(el), '.field-pill');
        const surface = qs(shadow(qs(shadow(el), 'platform-popover')), '.surface');

        expect(Math.round(surface.getBoundingClientRect().width)).to.equal(
            Math.round(field.getBoundingClientRect().width),
        );
    });
});
