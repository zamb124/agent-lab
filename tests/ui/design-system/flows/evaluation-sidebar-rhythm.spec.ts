/**
 * L3 consumer scenario: evaluation sidebar uses flows side-panel tokens.
 */
import { fixture, html, expect, elementUpdated } from '../../../frontend_core/browser/helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../../../frontend_core/browser/helpers/reset.js';
import '../../../../apps/flows/ui/components/evaluation/flows-evaluation-suite-sidebar.js';
import { shadowQuery, shadowQueryAll } from '../helpers/shadow-dom.js';
import type { TestEl } from '../../../frontend_core/browser/helpers/dom.js';

describe('flows consumer: evaluation sidebar rhythm', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
    });

    it('rail width resolves from --flows-side-panel-width', async () => {
        const wrap = await fixture<TestEl>(html`
            <div style="width: 1440px; --flows-side-panel-width: 324px; --flows-side-panel-min-width: 320px;">
                <flows-evaluation-suite-sidebar
                    .suites=${[]}
                    .cases=${[]}
                    .catalog=${[]}
                ></flows-evaluation-suite-sidebar>
            </div>
        `);
        await elementUpdated(wrap);

        const sidebar = wrap.querySelector('flows-evaluation-suite-sidebar');
        const rail = shadowQuery(sidebar!, '.rail');
        const width = rail.getBoundingClientRect().width;
        expect(width).to.be.closeTo(324, 4);
    });
});
