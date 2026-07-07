/**
 * L3 consumer scenario: incoming-policy modal uses platform-picker-card.
 */
import { fixture, html, expect, oneEvent } from '../../../frontend_core/browser/helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../../../frontend_core/browser/helpers/reset.js';
import '@platform/lib/components/platform-picker-card.js';

describe('flows consumer: incoming-policy picker cards', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
    });

    it('platform-picker-card select event carries policy value', async () => {
        const el = await fixture(html`
            <platform-picker-card title="Any" value="any"></platform-picker-card>
        `);
        setTimeout(() => el.shadowRoot.querySelector('.picker-card').click());
        const ev = await oneEvent(el, 'select');
        expect(ev.detail.value).to.equal('any');
    });
});
