/**
 * Handoff / handback cards в едином flows-chat-message surface.
 */

import { fixture, fixtureCleanup, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import '../../../../core/frontend/static/lib/chat/chat-message.js';

const LABELS = {
    role_user: 'You',
    role_assistant: 'Assistant',
    chat_handoff: {
        handoff_initiated: 'Transferred to {targetName}',
        handoff_returned: 'Returned from {targetName}',
        handoff_reason_label: 'Reason',
        handoff_chain_depth: 'Depth {depth}',
        open_trace: 'Open trace',
    },
};

describe('flows-chat-message handoff cards', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
    });

    afterEach(() => {
        fixtureCleanup();
    });

    it('renders active handoff card with target and reason', async () => {
        const el = await fixture(html`
            <flows-chat-message
                role="handoff"
                .labels=${LABELS}
                .handoff=${{
                    targetFlowId: 'child_flow',
                    targetFlowName: 'Child Agent',
                    reason: 'need specialist',
                    depth: 1,
                    status: 'active',
                }}
                .showHeader=${false}
            ></flows-chat-message>
        `);
        await elementUpdated(el);

        const card = el.shadowRoot.querySelector('.handoff-card');
        expect(card).to.not.equal(null);
        expect(card.textContent).to.include('Child Agent');
        expect(card.textContent).to.include('need specialist');
    });

    it('renders handback returned card', async () => {
        const el = await fixture(html`
            <flows-chat-message
                role="handback"
                .labels=${LABELS}
                .handback=${{
                    parentFlowName: 'Parent Agent',
                    status: 'returned',
                }}
                .showHeader=${false}
            ></flows-chat-message>
        `);
        await elementUpdated(el);

        const card = el.shadowRoot.querySelector('.handback-card');
        expect(card).to.not.equal(null);
        expect(card.textContent).to.include('Parent Agent');
    });
});
