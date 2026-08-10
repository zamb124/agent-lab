/**
 * Short first turns must align to the sides immediately (user right, assistant left),
 * not sit visually centered until later longer content arrives.
 */

import { fixture, fixtureCleanup, html, expect, elementUpdated } from '../helpers/render.js';
import { buildDefaultChatDocument } from '@platform/lib/flow-ui/templates/chat-template.js';
import '@platform/lib/flow-ui/components/flow-ui-surface.js';

function shortWorkingTask() {
    return {
        id: 't-short',
        status: { state: 'TASK_STATE_WORKING', message: { parts: [] } },
        history: [],
        artifacts: [
            {
                name: 'user_message',
                parts: [{ text: 'привет' }],
                metadata: { mutation_id: 'mut-short' },
            },
        ],
    };
}

describe('flow-ui conversation message alignment', () => {
    afterEach(() => {
        fixtureCleanup();
    });

    it('aligns short user bubble to the right and typing row to the left', async () => {
        const document = buildDefaultChatDocument({ greetingMessage: '' });
        const surface = document.surfaces.main;
        const host = await fixture(html`
            <div style="height:480px;width:420px;display:flex;flex-direction:column;overflow:hidden">
                <flow-ui-surface
                    style="flex:1 1 0;min-height:0;height:100%"
                    .surface=${surface}
                    .tasks=${[shortWorkingTask()]}
                    locale="ru"
                ></flow-ui-surface>
            </div>
        `);
        await elementUpdated(host);
        const surfaceEl = host.querySelector('flow-ui-surface');
        await elementUpdated(surfaceEl);
        const root = surfaceEl.shadowRoot;
        const feed = root.querySelector('.flow-node[data-flow-ui-type="ConversationFeed"]');
        const userRow = root.querySelector('.message-row.user');
        const assistantRow = root.querySelector('.message-row.assistant');
        expect(feed).to.exist;
        expect(userRow).to.exist;
        expect(assistantRow).to.exist;

        const feedBox = feed.getBoundingClientRect();
        const userBox = userRow.getBoundingClientRect();
        const assistantBox = assistantRow.getBoundingClientRect();
        const taskFeed = root.querySelector('.task-feed');
        expect(taskFeed).to.exist;
        // Feed must own the full ConversationFeed width (minus padding), not shrink-wrap.
        expect(taskFeed.getBoundingClientRect().width).to.be.greaterThan(feedBox.width * 0.85);

        const userLeftGap = userBox.left - feedBox.left;
        const userRightGap = feedBox.right - userBox.right;
        const assistantLeftGap = assistantBox.left - feedBox.left;
        const assistantRightGap = feedBox.right - assistantBox.right;

        // User must sit on the right half; assistant on the left half.
        expect(userRightGap).to.be.lessThan(userLeftGap);
        expect(assistantLeftGap).to.be.lessThan(assistantRightGap);
        // Short bubbles must not look centered as a group.
        expect(Math.abs(userLeftGap - userRightGap)).to.be.greaterThan(40);
        expect(Math.abs(assistantLeftGap - assistantRightGap)).to.be.greaterThan(40);
    });
});
