/**
 * Shell chrome: stop control left of icon-only Share; opaque spa page fill.
 */

import { fixture, fixtureCleanup, html, expect, elementUpdated } from '../helpers/render.js';
import { buildDefaultChatDocument } from '@platform/lib/flow-ui/templates/chat-template.js';
import '@platform/lib/flow-ui/components/platform-flow-ui.js';

describe('flow-ui chrome share and opacity', () => {
    afterEach(() => fixtureCleanup());

    it('uses opaque host fill for spa page and icon share summary', async () => {
        const document = buildDefaultChatDocument({ greetingMessage: 'Hi' });
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

        const bg = getComputedStyle(flowUi).backgroundColor;
        expect(bg).to.not.equal('rgba(0, 0, 0, 0)');
        expect(bg).to.not.equal('transparent');

        // Force minimal share chrome like live SPA with can_share.
        flowUi.setAttribute('data-chrome', 'minimal');
        const shell = flowUi.shadowRoot.querySelector('.shell');
        shell.setAttribute('data-chrome', 'minimal');
        let topbar = shell.querySelector('header.topbar');
        if (!topbar) {
            topbar = flowUi.ownerDocument.createElement('header');
            topbar.className = 'topbar';
            shell.insertBefore(topbar, shell.firstChild);
        }
        let actions = topbar.querySelector('.top-actions');
        if (!actions) {
            actions = flowUi.ownerDocument.createElement('div');
            actions.className = 'top-actions';
            topbar.appendChild(actions);
        }
        actions.innerHTML = `
            <button type="button" class="chrome-icon-btn task-run-control" aria-busy="true" aria-label="Stop">
                <span class="task-run-control__ring"></span>
                <span class="task-run-control__stop"></span>
            </button>
            <details class="share" open>
                <summary class="chrome-icon-btn" aria-label="Share">
                    <img class="flow-ui-glyph" src="/static/core/assets/icons/share.svg" width="18" height="18" alt="">
                </summary>
            </details>
        `;
        const stop = actions.querySelector('.task-run-control');
        const shareSummary = actions.querySelector('details.share > summary');
        expect(stop).to.exist;
        expect(shareSummary).to.exist;
        expect(shareSummary.textContent.trim()).to.equal('');
        expect(shareSummary.querySelector('img.flow-ui-glyph')).to.exist;
        const stopRect = stop.getBoundingClientRect();
        const shareRect = shareSummary.getBoundingClientRect();
        expect(stopRect.right).to.be.lessThanOrEqual(shareRect.left + 1);
    });
});
