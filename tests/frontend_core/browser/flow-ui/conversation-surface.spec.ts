/**
 * Лента conversation / hero / identity на холсте ``<platform-flow-ui editing>``.
 */

import { elementUpdated, expect, fixture, fixtureCleanup, html, waitUntil } from '../helpers/render.js';
import '@platform/lib/flow-ui/components/platform-flow-ui.js';
import { blockElement, pageRenderRoot } from '@platform/lib/flow-ui/editor/selection.js';
import {q, qs, shadow, type TestEl} from '../helpers/dom.js';

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

function conversationEl(host: any) {
    return blockElement(host, 'conversation')?.querySelector('flow-ui-conversation') ?? null;
}

describe('flow-ui conversation surface', () => {
    afterEach(() => fixtureCleanup());

    it('centers identity, greeting hero and composer on the editing canvas', async () => {
        const element = await fixture<TestEl>(html`<platform-flow-ui editing locale="en" .initialDocument=${CHAT_DOCUMENT}></platform-flow-ui>`);
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
        expect(qs(identity!, 'img').getAttribute('src')).to.contain('linnex_spinner_logo.png');
        const identityPad = parseFloat(getComputedStyle(identity!).paddingLeft);
        expect(identityPad).to.be.at.least(16);

        const page = qs(pageRenderRoot(element)!, '.page');
        expect(page.getAttribute('data-fill')).to.equal('true');

        const conversation = conversationEl(element);
        const root = shadow(conversation!);
        const greeting = qs(root!, '.greeting');
        expect(getComputedStyle(greeting).justifyItems).to.equal('center');
        expect(getComputedStyle(greeting).textAlign).to.equal('center');
        expect(qs(root!, '.greeting-mark').getAttribute('src')).to.contain('linnex_spinner_logo.png');
        expect(qs(root!, '.greeting-title').textContent).to.equal('Lara');
        expect(qs(greeting!, 'p').textContent).to.equal('Hello! How can I help?');
        expect(qs(root!, '.fu-prompts button').textContent).to.equal('What can you do?');
        expect(q(root!, 'textarea[data-canon="composer"]')).to.not.equal(null);
        expect(qs(root!, 'button.icon-btn.send').getAttribute('aria-label')).to.equal('Send');
        expect(q(root!, 'button.composer-voice-session')).to.not.equal(null);
        expect(conversation!.hasAttribute('editing')).to.equal(true);
        expect(getComputedStyle(qs(root!, '.task-feed')).overflow).to.equal('visible');
        expect(conversation!.scrollHeight).to.be.at.most(conversation!.clientHeight + 2);
        const convBox = conversation!.getBoundingClientRect();
        const markBox = qs(root!, '.greeting-mark').getBoundingClientRect();
        const composerBox = qs(root!, '.composer').getBoundingClientRect();
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
                ...CHAT_DOCUMENT.pages[0]!,
                blocks: [
                    CHAT_DOCUMENT!.pages[0]!.blocks[0]!,
                    { block_id: 'intro', type: 'video', visible_when: null, url: 'https://example.com/intro.mp4' },
                    CHAT_DOCUMENT!.pages[0]!.blocks[1]!,
                ],
            }],
        };
        const element = await fixture<TestEl>(html`<platform-flow-ui editing locale="en" .initialDocument=${document}></platform-flow-ui>`);
        await waitUntil(() => conversationEl(element)?.shadowRoot?.querySelector('.composer') !== null, 'conversation did not render');
        const identity = blockElement(element, 'agent-identity');
        const video = blockElement(element, 'intro');
        const conversation = blockElement(element, 'conversation');
        expect(identity!.getBoundingClientRect().bottom).to.be.at.most(video!.getBoundingClientRect().top + 1);
        expect(video!.getBoundingClientRect().bottom).to.be.at.most(conversation!.getBoundingClientRect().top + 1);
        const feed = qs(shadow(conversationEl(element)!), '.task-feed');
        expect(getComputedStyle(feed).overflow).to.equal('visible');
        expect(conversation!.scrollHeight).to.be.at.most(conversation!.clientHeight + 2);
    });

    it('does not fill the viewport when a conversation page has an html sibling', async () => {
        const document = {
            ...CHAT_DOCUMENT,
            pages: [{
                ...CHAT_DOCUMENT.pages[0]!,
                blocks: [
                    ...CHAT_DOCUMENT!.pages[0]!.blocks,
                    { block_id: 'card', type: 'html', visible_when: null, source: '<p>hello</p>', height: 'auto', fields: [], field: 'card' },
                ],
            }],
        };
        const element = await fixture<TestEl>(html`<platform-flow-ui editing locale="en" .initialDocument=${document}></platform-flow-ui>`);
        await waitUntil(() => conversationEl(element) !== null && pageRenderRoot(element)?.querySelector('.page') !== null, 'page did not render');
        expect(qs(pageRenderRoot(element)!, '.page').getAttribute('data-fill')).to.equal('false');
        expect(blockElement(element, 'card')).to.not.equal(null);
    });

    it('keeps the user bubble on the right after a local pending turn', async () => {
        const element = await fixture<TestEl>(html`<platform-flow-ui editing locale="en" .initialDocument=${CHAT_DOCUMENT}></platform-flow-ui>`);
        await waitUntil(() => conversationEl(element)?.shadowRoot?.querySelector('.task-feed') !== null, 'feed did not render');
        element.store.setPending({ text: 'pending-hello', files: [] });
        const conversation = conversationEl(element);
        await waitUntil(() => q(shadow(conversation!), '.bubble.user') !== null, 'user bubble did not appear');
        const bubble = qs(shadow(conversation!), '.bubble.user');
        expect(bubble!.textContent).to.equal('pending-hello');
        expect(getComputedStyle(bubble).alignSelf).to.equal('flex-end')!;
        expect(q(shadow(conversation!), '.greeting')).to.equal(null);
        expect(conversation!.hasAttribute('data-empty')).to.equal(false);
        expect(q(shadow(conversation!), '.typing')).to.not.equal(null);
    });

    it('shows icon-only copy, tracing and logs actions on a settled assistant turn', async () => {
        const document = {
            ...CHAT_DOCUMENT,
            pages: [{
                ...CHAT_DOCUMENT.pages[0]!,
                blocks: [
                    CHAT_DOCUMENT!.pages[0]!.blocks[0]!,
                    {
                        ...CHAT_DOCUMENT!.pages[0]!.blocks[1]!,
                        settings: { ...CHAT_DOCUMENT!.pages[0]!.blocks[1]!.settings, show_trace_actions: true },
                    },
                ],
            }],
        };
        const element = await fixture<TestEl>(html`<platform-flow-ui editing locale="en" .initialDocument=${document}></platform-flow-ui>`);
        await waitUntil(() => conversationEl(element)?.shadowRoot?.querySelector('.task-feed') !== null, 'feed did not render');
        element.store.resetContext('c1');
        element.store.applyFrame({
            result: {
                task: {
                    id: 't1',
                    contextId: 'c1',
                    status: { state: 'TASK_STATE_COMPLETED' },
                    artifacts: [{ artifactId: 'response', name: 'response', parts: [{ text: 'Hello there' }] }],
                    history: [{ role: 'ROLE_USER', taskId: 't1', parts: [{ text: 'hi' }] }],
                },
            },
        });
        await elementUpdated(element);
        const root = shadow(conversationEl(element)!);
        const copy = qs(root!, '.copy-btn');
        const tracing = qs(root!, '.tracing-btn[data-kind="tracing"]');
        const logs = qs(root!, '.tracing-btn[data-kind="logs"]');
        expect(copy, 'copy action').to.exist;
        expect(copy.getAttribute('aria-label')).to.equal('Copy');
        expect(qs(copy!, 'svg.fu-glyph path, svg.fu-glyph rect'), 'copy stroke icon').to.exist;
        expect(copy.textContent.trim()).to.equal('');
        expect(tracing.getAttribute('aria-label')).to.equal('Tracing');
        expect(qs(tracing!, 'svg.fu-glyph path, svg.fu-glyph circle, svg.fu-glyph line'), 'tracing stroke icon').to.exist;
        expect(logs.getAttribute('aria-label')).to.equal('Logs');
        expect(qs(logs!, 'svg.fu-glyph path'), 'logs stroke icon').to.exist;
        expect(getComputedStyle(copy).width).to.equal('32px');
        expect(getComputedStyle(copy).borderRadius).to.equal('8px');
    });
});
