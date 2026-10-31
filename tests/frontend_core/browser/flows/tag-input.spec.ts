/**
 * Smoke: tag-input — Enter добавляет, Backspace удаляет, эмит change.
 */

import { fixture, fixtureCleanup, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import '@platform/lib/components/tag-input.js';

describe('tag-input', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
    });
    afterEach(() => fixtureCleanup());

    it('Enter добавляет тег', async () => {
        const el = await fixture(html`<tag-input .tags=${['foo']}></tag-input>`);
        let last = null;
        el.addEventListener('change', (e) => { last = e.detail; });
        const input = el.shadowRoot.querySelector('.tag-input');
        input.value = 'bar';
        input.dispatchEvent(new Event('input'));
        input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
        expect(last).to.deep.equal({ tags: ['foo', 'bar'] });
    });

    it('Backspace удаляет последний при пустом draft', async () => {
        const el = await fixture(html`<tag-input .tags=${['foo', 'bar']}></tag-input>`);
        let last = null;
        el.addEventListener('change', (e) => { last = e.detail; });
        const input = el.shadowRoot.querySelector('.tag-input');
        input.value = '';
        input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Backspace', bubbles: true }));
        expect(last).to.deep.equal({ tags: ['foo'] });
    });

    it('игнорирует дубль', async () => {
        const el = await fixture(html`<tag-input .tags=${['foo']}></tag-input>`);
        let last = null;
        el.addEventListener('change', (e) => { last = e.detail; });
        const input = el.shadowRoot.querySelector('.tag-input');
        input.value = 'foo';
        input.dispatchEvent(new Event('input'));
        input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
        await elementUpdated(el);
        expect(last).to.equal(null);
    });
});
