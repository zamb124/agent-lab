/**
 * platform-flow-ui with hydrated local document must show conversation chrome + composer.
 */

import { fixture, fixtureCleanup, html, expect, elementUpdated } from '../helpers/render.js';
import { buildDefaultChatDocument } from '@platform/lib/flow-ui/templates/chat-template.js';
import { createLocalFlowUIProfile } from '@platform/lib/flow-ui/runtime/flow-ui-profile.js';
import '@platform/lib/flow-ui/components/platform-flow-ui.js';

describe('platform-flow-ui local document render', () => {
    afterEach(() => {
        fixtureCleanup();
    });

    it('shows composer inside spa panel after local hydrate', async () => {
        const document = buildDefaultChatDocument({ greetingMessage: '' });
        const el = await fixture(html`
            <div style="height:640px;width:480px;display:flex;flex-direction:column;overflow:hidden">
                <platform-flow-ui
                    style="flex:1 1 0;min-height:0;height:100%"
                    display="page"
                    profile="spa"
                    theme="auto"
                    locale="ru"
                    .initialDocument=${document}
                ></platform-flow-ui>
            </div>
        `);
        const flowUi = el.querySelector('platform-flow-ui');
        await elementUpdated(flowUi);
        // local profile path connects synchronously via microtask
        await new Promise((resolve) => setTimeout(resolve, 50));
        await elementUpdated(flowUi);

        const surface = flowUi.shadowRoot.querySelector('flow-ui-surface');
        expect(surface).to.exist;
        await elementUpdated(surface);
        const composer = surface.shadowRoot.querySelector('.field-group--composer');
        expect(composer).to.exist;
        expect(composer.clientHeight).to.be.greaterThan(20);
        expect(flowUi.shadowRoot.querySelector('.viewport').clientHeight).to.be.greaterThan(100);
    });
});
