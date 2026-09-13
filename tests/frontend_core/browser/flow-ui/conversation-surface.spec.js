/**
 * Лента conversation / hero / identity на холсте ``<platform-flow-ui editing>``.
 */

import { elementUpdated, expect, fixture, fixtureCleanup, html, waitUntil } from '../helpers/render.js';
import '@platform/lib/flow-ui/components/platform-flow-ui.js';
import { blockElement, pageRenderRoot } from '@platform/lib/flow-ui/editor/selection.js';

const CHAT_DOCUMENT = {
    start_page_id: 'main',
    pages: [
        {
            page_id: 'main',
            title: 'Chat',
            blocks: [
                { block_id: 'agent-identity', type: 'agent_identity', visible_when: null, title: '', image_url: '' },
                {
                    block_id: 'conversation',
                    type: 'conversation',
                    visible_when: null,
                    settings: {
                        greeting: 'Hello! How can I help?',
                        suggested_prompts: ['What can you do?'],
                        placeholder: 'Ask anything…',
                        show_reasoning: false,
                        tool_calls: 'compact',
                        show_activity: true,
                        show_skill_loads: true,
                        show_reflection: true,
                        errors: 'generic',
                        show_run_trace: false,
                        show_trace_actions: false,
                        show_browser_previews: true,
                        show_files_panel: true,
                        allow_cancel: true,
                        allow_voice: true,
                    },
                },
            ],
        },
    ],
};

function conversationEl(host) {
    return blockElement(host, 'conversation')?.querySelector('flow-ui-conversation') ?? null;
}

describe('flow-ui conversation surface', () => {
    afterEach(() => fixtureCleanup());

    it('centers identity, greeting hero and composer on the editing canvas', async () => {
        const element = await fixture(html`<platform-flow-ui editing locale="en" .initialDocument=${CHAT_DOCUMENT}></platform-flow-ui>`);
        await waitUntil(() => conversationEl(element)?.shadowRoot?.querySelector('.greeting') !== null, 'conversation did not render');
        element.store.setInterface({
            document: CHAT_DOCUMENT,
            flow_identity: { title: 'Lara', image_url: null },
            viewer: { can_edit_flow: true, can_interact: true, can_share: false, auth_mode: 'platform' },
            capabilities: { cancel: false, files: false, voice: false },
            look: null,
            flow_id: 'flow-1',
            branch_id: 'default',
        });
        await elementUpdated(element);
        await waitUntil(() => {
            const identity = blockElement(element, 'agent-identity');
            return identity?.querySelector('.fu-identity .title')?.textContent === 'Lara';
        }, 'identity title fallback did not render');

        const identity = blockElement(element, 'agent-identity');
        expect(identity.querySelector('img').getAttribute('src')).to.contain('linnex_spinner_logo.png');
        const identityPad = parseFloat(getComputedStyle(identity).paddingLeft);
        expect(identityPad).to.be.at.least(16);

        const page = pageRenderRoot(element).querySelector('.page');
        expect(page.getAttribute('data-fill')).to.equal('true');

        const conversation = conversationEl(element);
        const root = conversation.shadowRoot;
        const greeting = root.querySelector('.greeting');
        expect(getComputedStyle(greeting).justifyItems).to.equal('center');
        expect(getComputedStyle(greeting).textAlign).to.equal('center');
        expect(root.querySelector('.greeting-mark').getAttribute('src')).to.contain('linnex_spinner_logo.png');
        expect(root.querySelector('.greeting-title').textContent).to.equal('Lara');
        expect(greeting.querySelector('p').textContent).to.equal('Hello! How can I help?');
        expect(root.querySelector('.fu-prompts button').textContent).to.equal('What can you do?');
        expect(root.querySelector('textarea[data-canon="composer"]')).to.not.equal(null);
        expect(root.querySelector('button.icon-btn.send').getAttribute('aria-label')).to.equal('Send');
        expect(root.querySelector('button.composer-voice-session')).to.not.equal(null);
        expect(conversation.hasAttribute('editing')).to.equal(true);
        expect(getComputedStyle(root.querySelector('.task-feed')).overflow).to.equal('visible');
        expect(conversation.scrollHeight).to.be.at.most(conversation.clientHeight + 2);
        const convBox = conversation.getBoundingClientRect();
        const markBox = root.querySelector('.greeting-mark').getBoundingClientRect();
        const composerBox = root.querySelector('.composer').getBoundingClientRect();
        expect(markBox.height).to.be.at.least(48);
        expect(markBox.top).to.be.at.least(convBox.top - 1);
        expect(markBox.bottom).to.be.at.most(convBox.bottom + 1);
        expect(composerBox.height).to.be.greaterThan(24);
        expect(composerBox.bottom).to.be.at.most(convBox.bottom + 1);
    });

    it('keeps video, identity and conversation stacked without clipping on the editing canvas', async () => {
        const document = {
            ...CHAT_DOCUMENT,
            pages: [{
                ...CHAT_DOCUMENT.pages[0],
                blocks: [
                    CHAT_DOCUMENT.pages[0].blocks[0],
                    { block_id: 'intro', type: 'video', visible_when: null, url: 'https://example.com/intro.mp4' },
                    CHAT_DOCUMENT.pages[0].blocks[1],
                ],
            }],
        };
        const element = await fixture(html`<platform-flow-ui editing locale="en" .initialDocument=${document}></platform-flow-ui>`);
        await waitUntil(() => conversationEl(element)?.shadowRoot?.querySelector('.composer') !== null, 'conversation did not render');
        const identity = blockElement(element, 'agent-identity');
        const video = blockElement(element, 'intro');
        const conversation = blockElement(element, 'conversation');
        expect(identity.getBoundingClientRect().bottom).to.be.at.most(video.getBoundingClientRect().top + 1);
        expect(video.getBoundingClientRect().bottom).to.be.at.most(conversation.getBoundingClientRect().top + 1);
        const feed = conversationEl(element).shadowRoot.querySelector('.task-feed');
        expect(getComputedStyle(feed).overflow).to.equal('visible');
        expect(conversation.scrollHeight).to.be.at.most(conversation.clientHeight + 2);
    });

    it('does not fill the viewport when a conversation page has an html sibling', async () => {
        const document = {
            ...CHAT_DOCUMENT,
            pages: [{
                ...CHAT_DOCUMENT.pages[0],
                blocks: [
                    ...CHAT_DOCUMENT.pages[0].blocks,
                    { block_id: 'card', type: 'html', visible_when: null, source: '<p>hello</p>', height: 'auto', fields: [], field: 'card' },
                ],
            }],
        };
        const element = await fixture(html`<platform-flow-ui editing locale="en" .initialDocument=${document}></platform-flow-ui>`);
        await waitUntil(() => conversationEl(element) !== null && pageRenderRoot(element)?.querySelector('.page') !== null, 'page did not render');
        expect(pageRenderRoot(element).querySelector('.page').getAttribute('data-fill')).to.equal('false');
        expect(blockElement(element, 'card')).to.not.equal(null);
    });

    it('keeps the user bubble on the right after a local pending turn', async () => {
        const element = await fixture(html`<platform-flow-ui editing locale="en" .initialDocument=${CHAT_DOCUMENT}></platform-flow-ui>`);
        await waitUntil(() => conversationEl(element)?.shadowRoot?.querySelector('.task-feed') !== null, 'feed did not render');
        element.store.setPending({ text: 'pending-hello', files: [] });
        const conversation = conversationEl(element);
        await waitUntil(() => conversation.shadowRoot.querySelector('.bubble.user') !== null, 'user bubble did not appear');
        const bubble = conversation.shadowRoot.querySelector('.bubble.user');
        expect(bubble.textContent).to.equal('pending-hello');
        expect(getComputedStyle(bubble).alignSelf).to.equal('flex-end');
        expect(conversation.shadowRoot.querySelector('.greeting')).to.equal(null);
        expect(conversation.hasAttribute('data-empty')).to.equal(false);
        expect(conversation.shadowRoot.querySelector('.typing')).to.not.equal(null);
    });
});
