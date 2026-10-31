/**
 * L3 consumer scenario: library picker cards use platform-picker-card.
 */
import { fixture, html, expect, oneEvent } from '../../../frontend_core/browser/helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../../../frontend_core/browser/helpers/reset.js';
import '@platform/lib/components/platform-picker-card.js';
import '@platform/lib/components/platform-icon.js';

describe('flows consumer: library picker cards', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
    });

    it('library card supports icon slot + select', async () => {
        const el = await fixture(html`
            <platform-picker-card title="HTTP tool" value="http_tool">
                <div slot="icon"><platform-icon name="globe" size="22"></platform-icon></div>
            </platform-picker-card>
        `);
        expect(el.shadowRoot.querySelector('.picker-title').textContent).to.include('HTTP tool');
        setTimeout(() => el.shadowRoot.querySelector('.picker-card').click());
        const ev = await oneEvent(el, 'select');
        expect(ev.detail.value).to.equal('http_tool');
    });
});
