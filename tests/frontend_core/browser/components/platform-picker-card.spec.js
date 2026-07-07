/**
 * platform-picker-card — selectable glass card smoke tests.
 */

import { fixture, html, expect, oneEvent } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import '@platform/lib/components/platform-picker-card.js';

describe('platform-picker-card', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
    });

    it('renders title, subtitle, and selected state', async () => {
        const el = await fixture(html`
            <platform-picker-card
                selected
                icon="shield"
                title="Any sender"
                subtitle="Accept messages from any source"
                value="any"
            ></platform-picker-card>
        `);
        const card = el.shadowRoot.querySelector('.picker-card');
        expect(card).to.exist;
        expect(card.getAttribute('aria-pressed')).to.equal('true');
        expect(el.shadowRoot.textContent).to.include('Any sender');
        expect(el.shadowRoot.textContent).to.include('Accept messages from any source');
    });

    it('emits select with value on click', async () => {
        const el = await fixture(html`
            <platform-picker-card
                title="Preset"
                value="preset-a"
            ></platform-picker-card>
        `);
        const card = el.shadowRoot.querySelector('.picker-card');
        setTimeout(() => card.click());
        const ev = await oneEvent(el, 'select');
        expect(ev.detail.value).to.equal('preset-a');
    });

    it('does not emit select when disabled', async () => {
        const el = await fixture(html`
            <platform-picker-card
                disabled
                title="Locked"
                value="locked"
            ></platform-picker-card>
        `);
        let fired = false;
        el.addEventListener('select', () => {
            fired = true;
        });
        const card = el.shadowRoot.querySelector('.picker-card');
        card.click();
        await new Promise((resolve) => setTimeout(resolve, 0));
        expect(fired).to.equal(false);
    });
});
