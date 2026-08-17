/**
 * AgentIdentity.image_url renders in the chat header and assistant bubbles.
 */

import { fixture, fixtureCleanup, html, expect, elementUpdated } from '../helpers/render.js';
import { buildDefaultChatDocument } from '@platform/lib/flow-ui/templates/chat-template.js';
import { BRAND_LOGO_PATH } from '@platform/lib/flow-ui/shell/brand-logo.js';
import '@platform/lib/flow-ui/components/flow-ui-surface.js';

function withIdentityImage(document, imageUrl) {
    const clone = structuredClone(document);
    const identity = clone.surfaces.main.components['agent-identity'];
    identity.properties = {
        ...(identity.properties && typeof identity.properties === 'object' ? identity.properties : {}),
        image_url: imageUrl,
    };
    return clone;
}

function shortWorkingTask() {
    return {
        id: 't-identity',
        status: { state: 'TASK_STATE_WORKING', message: { parts: [] } },
        history: [],
        artifacts: [
            {
                name: 'user_message',
                parts: [{ text: 'привет' }],
                metadata: { mutation_id: 'mut-identity' },
            },
        ],
    };
}

describe('flow-ui AgentIdentity image', () => {
    afterEach(() => {
        fixtureCleanup();
    });

    it('uses the brand mark when image_url is empty', async () => {
        const document = buildDefaultChatDocument({ greetingMessage: '' });
        const host = await fixture(html`
            <div style="height:480px;width:420px;display:flex;flex-direction:column;overflow:hidden">
                <flow-ui-surface
                    style="flex:1 1 0;min-height:0;height:100%"
                    .surface=${document.surfaces.main}
                    .tasks=${[]}
                    locale="ru"
                ></flow-ui-surface>
            </div>
        `);
        const surfaceEl = host.querySelector('flow-ui-surface');
        await elementUpdated(surfaceEl);
        const img = surfaceEl.shadowRoot.querySelector('[data-flow-ui-type="AgentIdentity"] img');
        expect(img).to.exist;
        expect(img.getAttribute('src')).to.equal(BRAND_LOGO_PATH);
    });

    it('renders image_url in the header and assistant bubble', async () => {
        const imageUrl = '/flows/api/v1/files/download/agent-identity';
        const document = withIdentityImage(
            buildDefaultChatDocument({ greetingMessage: '' }),
            imageUrl,
        );
        const host = await fixture(html`
            <div style="height:480px;width:420px;display:flex;flex-direction:column;overflow:hidden">
                <flow-ui-surface
                    style="flex:1 1 0;min-height:0;height:100%"
                    .surface=${document.surfaces.main}
                    .tasks=${[shortWorkingTask()]}
                    locale="ru"
                ></flow-ui-surface>
            </div>
        `);
        const surfaceEl = host.querySelector('flow-ui-surface');
        await elementUpdated(surfaceEl);
        const headerImg = surfaceEl.shadowRoot.querySelector('[data-flow-ui-type="AgentIdentity"] img');
        const bubbleImg = surfaceEl.shadowRoot.querySelector('.message-row.assistant .avatar img');
        expect(headerImg).to.exist;
        expect(bubbleImg).to.exist;
        expect(headerImg.getAttribute('src')).to.equal(imageUrl);
        expect(bubbleImg.getAttribute('src')).to.equal(imageUrl);
    });
});
