/**
 * platform-timezone-picker — список IANA, фильтр, события; util iana-timezones.
 */

import { fixture, html, expect, oneEvent, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { getSortedIanaTimeZones } from '@platform/lib/utils/iana-timezones.js';
import '@platform/lib/components/platform-timezone-picker.js';

describe('iana-timezones', () => {
    it('getSortedIanaTimeZones: непусто, содержит UTC, отсортировано', () => {
        const z = getSortedIanaTimeZones();
        expect(z.length).to.be.above(0);
        expect(z.includes('UTC')).to.be.true;
        for (let i = 1; i < z.length; i += 1) {
            expect(z[i - 1].localeCompare(z[i], 'en')).to.be.below(0);
        }
    });
});

describe('platform-timezone-picker', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
    });

    it('value=Europe/Moscow отображается в поле', async () => {
        const el = await fixture(
            html`<platform-timezone-picker .value=${'Europe/Moscow'}></platform-timezone-picker>`,
        );
        const inp = el.shadowRoot.querySelector('input');
        expect(inp.value).to.equal('Europe/Moscow');
    });

    it('ввод сужает список', async () => {
        const el = await fixture(html`<platform-timezone-picker .value=${''}></platform-timezone-picker>`);
        const inp = el.shadowRoot.querySelector('input');
        const allN = getSortedIanaTimeZones().length;
        inp.value = 'Europe/Amster';
        inp.dispatchEvent(new Event('input', { bubbles: true }));
        await elementUpdated(el);
        const opts = el.shadowRoot.querySelectorAll('li.opt');
        expect(opts.length).to.be.below(allN);
        expect(opts.length).to.be.above(0);
    });

    it('клик по пункту эмитит change с ожидаемым detail.value', async () => {
        const el = await fixture(html`<platform-timezone-picker .value=${''}></platform-timezone-picker>`);
        const inp = el.shadowRoot.querySelector('input');
        inp.focus();
        inp.value = 'Moscow';
        inp.dispatchEvent(new Event('input', { bubbles: true }));
        await elementUpdated(el);
        const firstOpt = el.shadowRoot.querySelector('li.opt');
        if (!firstOpt) {
            expect.fail('ожидался вариант Europe/Moscow в списке');
        }
        const p = oneEvent(el, 'change');
        firstOpt.click();
        const ev = await p;
        expect(ev.detail.value).to.equal('Europe/Moscow');
    });

    it('disabled блокирует input', async () => {
        const el = await fixture(
            html`<platform-timezone-picker .value=${'UTC'} disabled></platform-timezone-picker>`,
        );
        const inp = el.shadowRoot.querySelector('input');
        expect(inp.disabled).to.be.true;
    });

    it('значение вне списка остаётся в поле', async () => {
        const el = await fixture(
            html`<platform-timezone-picker .value=${'Custom/LegacyOnly'}></platform-timezone-picker>`,
        );
        const inp = el.shadowRoot.querySelector('input');
        expect(inp.value).to.equal('Custom/LegacyOnly');
    });
});
