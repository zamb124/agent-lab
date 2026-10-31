/**
 * L3 consumer scenario: flow-create preset cards use platform-picker-card.
 */
import { fixture, html, expect, oneEvent } from '../../../frontend_core/browser/helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../../../frontend_core/browser/helpers/reset.js';
import '@platform/lib/components/platform-picker-card.js';
import { shadowQuery, shadowQueryAll } from '../helpers/shadow-dom.js';
import type { TestEl } from '../../../frontend_core/browser/helpers/dom.js';

describe('flows consumer: flow-create preset cards', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
    });

    it('preset card emits value on select', async () => {
        const el = await fixture<TestEl>(html`
            <platform-picker-card
                title="Graph agent"
                subtitle="Multi-node graph"
                value="graph"
            ></platform-picker-card>
        `);
        setTimeout(() => shadowQuery(el, '.picker-card').click());
        const ev = await oneEvent(el, 'select');
        expect(ev.detail.value).to.equal('graph');
    });
});
