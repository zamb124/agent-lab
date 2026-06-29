/**
 * platform-island: glass surface отделён от scrollable content.
 */

import { fixture, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import '@platform/lib/components/layout/platform-island.js';

describe('platform-island', () => {
    beforeEach(() => { resetPlatformState(); bootstrapTestBus(); });

    it('рендерит island-surface и island-content', async () => {
        const el = await fixture(html`
            <platform-island>
                <div id="slot-child">content</div>
            </platform-island>
        `);
        expect(el.shadowRoot.querySelector('.island-surface')).to.exist;
        expect(el.shadowRoot.querySelector('.island-content')).to.exist;
        expect(el.querySelector('#slot-child')).to.exist;
    });

    it('scroll внутри island-content включает is-scrolling', async () => {
        const el = await fixture(html`
            <platform-island style="display:block;height:120px;">
                <div style="height:400px;">tall</div>
            </platform-island>
        `);
        const content = el.shadowRoot.querySelector('.island-content');
        content.scrollTop = 40;
        content.dispatchEvent(new Event('scroll', { bubbles: false }));
        await elementUpdated(el);
        expect(el.shadowRoot.querySelector('.island.is-scrolling')).to.exist;
    });
});
