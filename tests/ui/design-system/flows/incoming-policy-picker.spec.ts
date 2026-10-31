/**
 * L3 consumer scenario: incoming-policy modal uses platform-picker-card.
 */
import { fixture, html, expect, oneEvent } from '../../../frontend_core/browser/helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../../../frontend_core/browser/helpers/reset.js';
import '@platform/lib/components/platform-picker-card.js';
import { shadowQuery, shadowQueryAll } from '../helpers/shadow-dom.js';
import type { TestEl } from '../../../frontend_core/browser/helpers/dom.js';

describe('flows consumer: incoming-policy picker cards', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
    });

    it('platform-picker-card select event carries policy value', async () => {
        const el = await fixture<TestEl>(html`
            <platform-picker-card title="Any" value="any"></platform-picker-card>
        `);
        setTimeout(() => shadowQuery(el, '.picker-card').click());
        const ev = await oneEvent(el, 'select');
        expect(ev.detail.value).to.equal('any');
    });
});
