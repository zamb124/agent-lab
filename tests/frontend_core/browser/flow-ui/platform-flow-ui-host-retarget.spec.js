/**
 * SPA host reuses <platform-flow-ui>; flowId / explicit contextId changes must
 * restart the session (sidebar open-chat / deep-link), not keep the old controller.
 */
import { fixture, fixtureCleanup, html, expect, elementUpdated } from '../helpers/render.js';
import { buildDefaultChatDocument } from '@platform/lib/flow-ui/templates/chat-template.js';
import '@platform/lib/flow-ui/components/platform-flow-ui.js';

describe('platform-flow-ui host session retarget', () => {
    afterEach(() => {
        fixtureCleanup();
    });

    it('restarts controller when host flowId changes', async () => {
        const document = buildDefaultChatDocument({ greetingMessage: 'hi' });
        const el = await fixture(html`
            <platform-flow-ui
                flow-id="flow-a"
                branch-id="default"
                display="page"
                profile="editor_test"
                .initialDocument=${document}
            ></platform-flow-ui>
        `);
        await elementUpdated(el);
        await el.updateComplete;
        // Local initialDocument connect is sync after microtask.
        await new Promise((resolve) => queueMicrotask(resolve));
        await elementUpdated(el);

        const firstController = el.controller;
        expect(firstController).to.not.equal(null);
        expect(firstController.target.flowId).to.equal('flow-a');

        el.flowId = 'flow-b';
        await elementUpdated(el);
        await new Promise((resolve) => queueMicrotask(resolve));
        await elementUpdated(el);

        expect(el.controller).to.not.equal(null);
        expect(el.controller).to.not.equal(firstController);
        expect(el.controller.target.flowId).to.equal('flow-b');
    });

    it('restarts controller when host sets a different non-empty contextId', async () => {
        const document = buildDefaultChatDocument({ greetingMessage: 'hi' });
        const el = await fixture(html`
            <platform-flow-ui
                flow-id="flow-a"
                branch-id="default"
                context-id="ctx-one"
                display="page"
                profile="editor_test"
                .initialDocument=${document}
            ></platform-flow-ui>
        `);
        await elementUpdated(el);
        await new Promise((resolve) => queueMicrotask(resolve));
        await elementUpdated(el);

        const firstController = el.controller;
        expect(firstController).to.not.equal(null);
        expect(firstController.contextId).to.equal('ctx-one');

        el.contextId = 'ctx-two';
        await elementUpdated(el);
        await new Promise((resolve) => queueMicrotask(resolve));
        await elementUpdated(el);

        expect(el.controller).to.not.equal(null);
        expect(el.controller).to.not.equal(firstController);
        expect(el.controller.contextId).to.equal('ctx-two');
    });
});
