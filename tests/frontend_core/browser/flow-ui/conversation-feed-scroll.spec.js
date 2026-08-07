/**
 * ConversationFeed must become a real scrollport inside a height-bounded host.
 * Bare CSS Grid `1fr` (= minmax(auto,1fr)) used to grow with content and clip.
 */

import { fixture, fixtureCleanup, html, expect, elementUpdated } from '../helpers/render.js';
import { buildDefaultChatDocument } from '@platform/lib/flow-ui/templates/chat-template.js';
import '@platform/lib/flow-ui/components/flow-ui-surface.js';
import '@platform/lib/flow-ui/components/platform-flow-ui.js';

function tallAssistantTask(taskId, lines) {
    const text = Array.from({ length: lines }, (_, index) => `Line ${index + 1} of ${taskId}`).join('\n');
    return {
        id: taskId,
        status: {
            state: 'TASK_STATE_COMPLETED',
            message: { parts: [{ text }] },
        },
        history: [],
        artifacts: [
            {
                name: 'user_message',
                parts: [{ text: `user ${taskId}` }],
                metadata: { mutation_id: `mut-${taskId}` },
            },
            {
                name: 'response',
                parts: [{ text }],
            },
        ],
    };
}

describe('flow-ui conversation feed scroll', () => {
    afterEach(() => {
        fixtureCleanup();
    });

    it('platform-flow-ui shell viewport row uses minmax(0, 1fr)', async () => {
        const el = await fixture(html`
            <platform-flow-ui display="panel" profile="spa"></platform-flow-ui>
        `);
        await elementUpdated(el);
        const sheetText = [...el.shadowRoot.adoptedStyleSheets]
            .map((sheet) => [...sheet.cssRules].map((rule) => rule.cssText).join('\n'))
            .join('\n');
        expect(sheetText).to.match(/grid-template-rows:\s*auto minmax\(0(?:px)?, 1fr\)/);
        expect(sheetText).to.match(/minmax\(0(?:px)?, 1fr\)/);
        expect(sheetText).to.not.match(/grid-template-rows:\s*auto 1fr(?:;|\s|$)/);
        // Minimal/none must be a single track — absolute Share topbar must not own a row.
        expect(sheetText).to.match(
            /:host\(\[data-chrome="minimal"\]\)[\s\S]*?\.shell[\s\S]*?grid-template-rows:\s*minmax\(0(?:px)?, 1fr\)/,
        );
    });

    it('ConversationFeed scrolls inside a fixed-height host with long history', async () => {
        const document = buildDefaultChatDocument({ greetingMessage: '' });
        const surface = document.surfaces.main;
        const tasks = [
            tallAssistantTask('t1', 40),
            tallAssistantTask('t2', 40),
            tallAssistantTask('t3', 40),
        ];
        const host = await fixture(html`
            <div style="height:420px;width:420px;display:flex;flex-direction:column;overflow:hidden">
                <flow-ui-surface
                    style="flex:1 1 0;min-height:0;height:100%"
                    .surface=${surface}
                    .tasks=${tasks}
                    locale="en"
                ></flow-ui-surface>
            </div>
        `);
        await elementUpdated(host);
        const surfaceEl = host.querySelector('flow-ui-surface');
        await elementUpdated(surfaceEl);

        const feed = surfaceEl.shadowRoot.querySelector(
            '.flow-node[data-flow-ui-type="ConversationFeed"]',
        );
        expect(feed).to.exist;
        expect(feed.clientHeight).to.be.greaterThan(0);
        expect(feed.clientHeight).to.be.lessThan(420);
        expect(feed.scrollHeight).to.be.greaterThan(feed.clientHeight);

        feed.scrollTop = feed.scrollHeight;
        expect(feed.scrollTop).to.be.greaterThan(0);
    });
});
