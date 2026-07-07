/**
 * L3 consumer scenario: MCP server header presets use platform-picker-card.
 */
import { fixture, html, expect, oneEvent } from '../../../frontend_core/browser/helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../../../frontend_core/browser/helpers/reset.js';
import '@platform/lib/components/platform-picker-card.js';
import '@platform/lib/components/platform-icon.js';

describe('flows consumer: mcp-servers header presets', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
    });

    it('header preset card emits preset id on select', async () => {
        const el = await fixture(html`
            <platform-picker-card title="Bearer" value="bearer">
                <div slot="icon"><platform-icon name="key" size="22"></platform-icon></div>
            </platform-picker-card>
        `);
        setTimeout(() => el.shadowRoot.querySelector('.picker-card').click());
        const ev = await oneEvent(el, 'select');
        expect(ev.detail.value).to.equal('bearer');
    });
});
