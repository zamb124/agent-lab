/**
 * SPA minimal chrome (Share overlay): absolute topbar must not leave viewport at 0px.
 */

import { fixture, fixtureCleanup, html, expect, elementUpdated } from '../helpers/render.js';
import { buildDefaultChatDocument } from '@platform/lib/flow-ui/templates/chat-template.js';
import '@platform/lib/flow-ui/components/platform-flow-ui.js';

describe('flow-ui minimal chrome viewport height', () => {
    afterEach(() => fixtureCleanup());

    it('keeps viewport tall when absolute share topbar is present', async () => {
        const document = buildDefaultChatDocument({ greetingMessage: '' });
        const host = await fixture(html`
            <div style="height:640px;width:480px;display:flex;flex-direction:column;overflow:hidden">
                <platform-flow-ui
                    style="flex:1 1 0;min-height:0;height:100%"
                    display="page"
                    profile="spa"
                    theme="dark"
                    locale="ru"
                    .initialDocument=${document}
                ></platform-flow-ui>
            </div>
        `);
        const flowUi = host.querySelector('platform-flow-ui');
        await new Promise((resolve) => setTimeout(resolve, 80));
        await elementUpdated(flowUi);

        // Live SPA with can_share uses minimal chrome; local preview uses none.
        // Force the minimal DOM/CSS contract that blanked production chat.
        flowUi.setAttribute('data-chrome', 'minimal');
        const shell = flowUi.shadowRoot.querySelector('.shell');
        shell.setAttribute('data-chrome', 'minimal');
        if (!shell.querySelector('header.topbar')) {
            const topbar = flowUi.ownerDocument.createElement('header');
            topbar.className = 'topbar';
            topbar.innerHTML = '<div class="top-actions"><details class="share"><summary>Share</summary></details></div>';
            shell.insertBefore(topbar, shell.firstChild);
        }
        await elementUpdated(flowUi);

        const viewport = flowUi.shadowRoot.querySelector('.viewport');
        expect(viewport).to.exist;
        expect(viewport.clientHeight).to.be.greaterThan(400);
        expect(getComputedStyle(shell).gridTemplateRows.split(' ').length).to.equal(1);

        const surface = flowUi.shadowRoot.querySelector('flow-ui-surface');
        await elementUpdated(surface);
        const composer = surface.shadowRoot.querySelector('.field-group--composer');
        expect(composer).to.exist;
        expect(composer.clientHeight).to.be.greaterThan(20);
        const composerBottom = composer.getBoundingClientRect().bottom;
        const viewportBottom = viewport.getBoundingClientRect().bottom;
        expect(composerBottom).to.be.lessThanOrEqual(viewportBottom + 2);
        expect(composer.getBoundingClientRect().top)
            .to.be.greaterThan(viewport.getBoundingClientRect().top + 120);
    });
});
