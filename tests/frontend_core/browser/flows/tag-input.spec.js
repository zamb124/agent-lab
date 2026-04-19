/**
 * Smoke: flows-tag-input — Enter добавляет, Backspace удаляет, эмит change.
 */

import { fixture, fixtureCleanup, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import '../../../../apps/flows/ui/components/editors/flows-tag-input.js';

describe('flows-tag-input', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
    });
    afterEach(() => fixtureCleanup());

    it('Enter добавляет тег', async () => {
        const el = await fixture(html`<flows-tag-input .tags=${['foo']}></flows-tag-input>`);
        let last = null;
        el.addEventListener('change', (e) => { last = e.detail; });
        const input = el.shadowRoot.querySelector('input');
        input.value = 'bar';
        input.dispatchEvent(new Event('input'));
        input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
        expect(last).to.deep.equal({ tags: ['foo', 'bar'] });
    });

    it('Backspace удаляет последний при пустом draft', async () => {
        const el = await fixture(html`<flows-tag-input .tags=${['foo', 'bar']}></flows-tag-input>`);
        let last = null;
        el.addEventListener('change', (e) => { last = e.detail; });
        const input = el.shadowRoot.querySelector('input');
        input.value = '';
        input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Backspace', bubbles: true }));
        expect(last).to.deep.equal({ tags: ['foo'] });
    });

    it('игнорирует дубль', async () => {
        const el = await fixture(html`<flows-tag-input .tags=${['foo']}></flows-tag-input>`);
        let last = null;
        el.addEventListener('change', (e) => { last = e.detail; });
        const input = el.shadowRoot.querySelector('input');
        input.value = 'foo';
        input.dispatchEvent(new Event('input'));
        input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
        await elementUpdated(el);
        expect(last).to.equal(null);
    });
});
