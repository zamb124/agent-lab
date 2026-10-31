/**
 * platform-island: glass surface отделён от scrollable content.
 */

import { fixture, html, expect } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import '@platform/lib/components/layout/platform-island.js';
import {q, qs, shadow, type TestEl} from '../helpers/dom.js';

describe('platform-island', () => {
    beforeEach(() => { resetPlatformState(); bootstrapTestBus(); });

    it('рендерит island-surface и island-content', async () => {
        const el = await fixture<TestEl>(html`
            <platform-island>
                <div id="slot-child">content</div>
            </platform-island>
        `);
        expect(qs(shadow(el), '.island-surface')).to.exist;
        expect(qs(shadow(el), '.island-content')).to.exist;
        expect(qs(el!, '#slot-child')).to.exist;
    });

    it('не ставит is-scrolling при scroll (solid surface, без blur-toggle)', async () => {
        const el = await fixture<TestEl>(html`
            <platform-island style="display:block;height:120px;">
                <div style="height:400px;">tall</div>
            </platform-island>
        `);
        const content = q(shadow(el), '.island-content');
        content!.scrollTop = 40;
        content!.dispatchEvent(new Event('scroll', { bubbles: false }));
        expect(q(shadow(el), '.island.is-scrolling')).to.not.exist;
    });
});
