import { fixture, fixtureCleanup, html, expect, elementUpdated, aTimeout, waitUntil } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { FILES_EVENTS } from '@platform/lib/events/index.js';
import '../../../../core/frontend/static/lib/chat/chat-message.js';
import '../../../../core/frontend/static/lib/chat/platform-chat.js';
import '../../../../apps/flows/ui/modals/flows-browser-preview-modal.js';
import { installChatProfileFetchStub } from '../helpers/chat-profile-stub.js';

const LABELS = {
    role_user: 'You',
    role_assistant: 'Assistant',
    role_agent: 'Agent',
    role_subagent: 'Sub-agent',
    role_operator: 'Operator',
    operator_files: 'Attached files',
    tool_default_name: 'tool',
    tool_stack_aria: 'Tool calls: {names}',
    tool_hint_tool_name: 'Tool: {name}',
    tool_hint_args_label: 'Arguments:',
    tool_hint_result_label: 'Result:',
    interrupt_oauth_banner: 'Authorization required',
    interrupt_oauth_button: 'Authorize',
    streaming_placeholder: 'Generating...',
    operator_reply_heading: 'Operator',
};

function cleanupEditorPortals() {
    document.body.querySelectorAll('.flows-file-editor-portal').forEach((node) => node.remove());
}

function installDocumentEditorConfigStub() {
    const previousFetch = window.fetch;
    window.fetch = async (rawUrl, init = {}) => {
        const method = (init.method || 'GET').toUpperCase();
        const url = new URL(String(rawUrl), window.location.href);
        if (method === 'GET' && /^\/documents\/api\/v1\/files\/[^/]+\/editor-config$/.test(url.pathname)) {
            return new Response(JSON.stringify({ document_server_url: 'https://docs.example.test', token: 'e30.e30.sig' }), {
                status: 200,
                headers: { 'content-type': 'application/json; charset=utf-8' },
            });
        }
        return previousFetch(rawUrl, init);
    };
    return () => {
        window.fetch = previousFetch;
    };
}

describe('flows-chat-message shared surface', () => {
    let bus;
    let restoreFetch;
    let restoreChatFetch;

    beforeEach(() => {
        cleanupEditorPortals();
        resetPlatformState();
        bus = bootstrapTestBus();
        restoreChatFetch = installChatProfileFetchStub({ flowId: 'lara' });
        restoreFetch = installDocumentEditorConfigStub();
    });

    afterEach(() => {
        restoreFetch();
        restoreChatFetch();
        fixtureCleanup();
        cleanupEditorPortals();
    });

    it('renders assistant markdown, tool rows, oauth input and flow UI blocks in one component', async () => {
        const el = await fixture(html`
            <flows-chat-message
                variant="embed"
                role="assistant"
                flow-root="/flows"
                .labels=${LABELS}
                .content=${'**Done**'}
                .toolCalls=${[{ id: 'tc1', name: 'read_file', arguments: { file_id: 'f1' } }]}
                .toolResults=${[{ id: 'tc1', name: 'read_file', content: 'ok' }]}
                .inputRequired=${{
                    interruptKind: 'oauth_required',
                    question: 'Authorize *Google*',
                    authUrl: '/login',
                }}
                .blocks=${[{ type: 'text', text: 'Block text' }]}
                .showAvatar=${false}
                .showHeader=${false}
            ></flows-chat-message>
        `);
        await elementUpdated(el);
        await aTimeout(0);

        expect(el.shadowRoot.querySelector('.markdown').innerHTML).to.include('<strong>Done</strong>');
        expect(el.shadowRoot.querySelector('.tool-stack')).to.not.equal(null);
        expect(el.shadowRoot.querySelector('.oauth-auth-link').getAttribute('href')).to.equal('/login');

        const renderer = el.shadowRoot.querySelector('flows-chat-block-renderer');
        expect(renderer).to.not.equal(null);
        await elementUpdated(renderer);
        expect(renderer.shadowRoot.querySelector('flows-chat-ui-text')).to.not.equal(null);
    });

    it('anchors the browser preview status dot to the tool orb corner', async () => {
        const el = await fixture(html`
            <flows-chat-message
                role="assistant"
                flow-root="/flows"
                .labels=${LABELS}
                .content=${'Browser tool finished'}
                .toolCalls=${[{
                    id: 'tc-browser',
                    name: 'browser.open',
                    arguments: { url: 'https://example.test' },
                }]}
                .toolResults=${[{
                    tool_call_id: 'tc-browser',
                    name: 'browser.open',
                    content: 'ok',
                }]}
                .browserPreviews=${[{
                    parentToolCallId: 'tc-browser',
                    status: 'open',
                    viewerUrl: 'https://browser.example.test/session/tc-browser',
                    currentUrl: 'https://example.test',
                    sessionId: 'tc-browser',
                }]}
                .showAvatar=${false}
                .showHeader=${false}
            ></flows-chat-message>
        `);
        await elementUpdated(el);
        await aTimeout(0);

        const orb = el.shadowRoot.querySelector('.tool-orb.browser-preview');
        const hint = orb.querySelector('platform-help-hint');
        const button = orb.querySelector('.tool-orb-button');
        const dot = orb.querySelector('.browser-preview-dot');
        expect(hint.hasAttribute('fill')).to.equal(true);

        const orbRect = orb.getBoundingClientRect();
        const hintRect = hint.getBoundingClientRect();
        const buttonRect = button.getBoundingClientRect();
        const dotRect = dot.getBoundingClientRect();
        const dotCenterX = dotRect.left + dotRect.width / 2;
        const dotCenterY = dotRect.top + dotRect.height / 2;

        expect(hintRect.width).to.be.greaterThan(26);
        expect(hintRect.height).to.be.greaterThan(26);
        expect(buttonRect.width).to.be.greaterThan(26);
        expect(buttonRect.height).to.be.greaterThan(26);
        expect(dotCenterX).to.be.greaterThan(orbRect.right - 8);
        expect(dotCenterY).to.be.lessThan(orbRect.top + 8);

        const previousOpen = window.open;
        let opened = false;
        let eventDetail = null;
        window.open = () => {
            opened = true;
            return null;
        };
        try {
            el.addEventListener('browser-preview-open', (event) => {
                event.preventDefault();
                eventDetail = event.detail;
            });
            button.click();
            await elementUpdated(el);
            expect(opened).to.equal(false);
            expect(eventDetail.viewerUrl).to.equal('https://browser.example.test/session/tc-browser');
            expect(eventDetail.sessionId).to.equal('tc-browser');
        } finally {
            window.open = previousOpen;
        }
    });

    it('emits compose-edit from the real user action button', async () => {
        const el = await fixture(html`
            <flows-chat-message
                role="user"
                .labels=${LABELS}
                .content=${'Rewrite me'}
                .showAvatar=${false}
                .showHeader=${false}
            ></flows-chat-message>
        `);
        await elementUpdated(el);

        expect(el.shadowRoot.querySelector('.text').textContent).to.equal('Rewrite me');
        expect(el.shadowRoot.querySelector('.markdown')).to.equal(null);

        let detail = null;
        el.addEventListener('compose-edit', (event) => {
            detail = event.detail;
        });
        const actions = el.shadowRoot.querySelector('platform-assistant-message-actions');
        await elementUpdated(actions);
        actions.shadowRoot.querySelectorAll('button')[1].click();

        expect(detail).to.deep.equal({ text: 'Rewrite me' });
    });

    it('dispatches flows-chat-block-action from a real action block button', async () => {
        const el = await fixture(html`
            <flows-chat-message
                role="assistant"
                .labels=${LABELS}
                .blocks=${[{
                    type: 'actions',
                    buttons: [{
                        label: 'Apply',
                        action_id: 'crm.note.create.apply',
                        action_kind: 'apply',
                        pending_action_id: 'pending-1',
                        arguments: { entity_id: 'e1' },
                        context: { entity_type: 'note' },
                    }],
                }]}
                .showAvatar=${false}
                .showHeader=${false}
            ></flows-chat-message>
        `);
        await elementUpdated(el);
        const renderer = el.shadowRoot.querySelector('flows-chat-block-renderer');
        await elementUpdated(renderer);
        const actions = renderer.shadowRoot.querySelector('flows-chat-ui-actions');
        await elementUpdated(actions);

        let detail = null;
        el.addEventListener('flows-chat-block-action', (event) => {
            detail = event.detail;
        });
        actions.shadowRoot.querySelector('button').click();

        expect(detail).to.deep.equal({
            action_id: 'crm.note.create.apply',
            action_kind: 'apply',
            pending_action_id: 'pending-1',
            arguments: { entity_id: 'e1' },
            context: { entity_type: 'note' },
        });
    });

    it('platform-chat host renders messages through flows-chat-message only', async () => {
        const el = await fixture(html`
            <platform-chat
                flows-base-url="/flows"
                flow-id="lara"
                .labels=${{ greeting: 'Hi from embed', new_chat: 'New chat' }}
            ></platform-chat>
        `);
        el._controller.applyRuntimeVerb('user_message_added', {
            contextId: el._controller.state.currentContextId,
            message: {
                id: 'user-compact-1',
                role: 'user',
                content: 'Hello',
                timestamp: '2026-05-15T10:00:00.000Z',
            },
        });
        await elementUpdated(el);
        await aTimeout(80);

        const bubble = el.shadowRoot.querySelector('flows-chat-message[data-role="user"]');
        expect(bubble).to.not.equal(null);
        expect(bubble.headerCompact).to.equal(true);
        expect(bubble.shadowRoot.querySelector('.header .role')).to.equal(null);
        expect(el.shadowRoot.querySelector('.msg')).to.equal(null);
    });

    it('platform-chat host exposes document file blocks through the same files panel and global file viewer event', async () => {
        const events = [];
        bus.subscribeType(FILES_EVENTS.OPEN_REQUESTED, (event) => events.push(event));
        const el = await fixture(html`
            <platform-chat
                flows-base-url="https://flows.example/flows"
                platform-ui-origin="https://platform.example"
                flow-id="lara"
                .labels=${{ greeting: 'Hi from embed', new_chat: 'New chat' }}
            ></platform-chat>
        `);
        el._controller.applyRuntimeVerb('user_message_added', {
            contextId: el._controller.state.currentContextId,
            message: {
                id: 'assistant-doc',
                role: 'assistant',
                content: 'Document ready',
                blocks: [{
                    type: 'file_card',
                    file_id: 'file-docx-2',
                    name: 'Offer.docx',
                    mime_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    document: {
                        binding_id: 'binding-docx-2',
                        file_id: 'file-docx-2',
                        editor_url: '/documents/embed/edit/binding-docx-2?namespace=system',
                    },
                }],
            },
        });
        el.requestUpdate();
        await elementUpdated(el);
        await aTimeout(0);

        const panel = el.shadowRoot.querySelector('flows-chat-files-panel');
        expect(panel).to.not.equal(null);
        expect(panel.documentBaseUrl).to.equal('https://platform.example');
        panel.shadowRoot.querySelector('.trigger').click();
        await elementUpdated(panel);
        panel.shadowRoot.querySelector('.file-row').click();
        await elementUpdated(panel);
        await waitUntil(() => events.length === 1, 'embed file open requested');

        expect(events[0].payload.file.file_id).to.equal('file-docx-2');
        expect(events[0].payload.file.original_name).to.equal('Offer.docx');
        expect(events[0].payload.source).to.equal('flows_chat_files_panel');
    });

    it('platform-chat host merges A2A files events into the shared files panel', async () => {
        const el = await fixture(html`
            <platform-chat
                flows-base-url="/flows"
                flow-id="lara"
                .labels=${{ greeting: 'Hi from embed', new_chat: 'New chat' }}
            ></platform-chat>
        `);
        const contextId = el._controller.state.currentContextId;
        el._controller.applyRuntimeVerb('task_started', {
            task_id: 'task-files-event',
            context_id: contextId,
        });
        el._controller.applyRuntimeVerb('files_event', {
            task_id: 'task-files-event',
            context_id: contextId,
            event: {
                payload: {
                    files: [{
                        file_id: 'file-event-1',
                        original_name: 'Generated.txt',
                        content_type: 'text/plain',
                        file_size: 12,
                        url: '/frontend/api/v1/files/download/file-event-1',
                    }],
                },
            },
        });
        await elementUpdated(el);

        const panel = el.shadowRoot.querySelector('flows-chat-files-panel');
        expect(panel).to.not.equal(null);
        expect(panel.files.map((file) => file.file_id)).to.deep.equal(['file-event-1']);
    });

    it('compact meta shows timestamp and observability actions scoped to taskId', async () => {
        const el = await fixture(html`
            <flows-chat-message
                role="assistant"
                .showHeader=${true}
                .headerCompact=${true}
                .showTraceControls=${true}
                .showLogsAction=${true}
                .showDurableHistoryAction=${true}
                session-id="flow-1:ctx-1"
                .taskId=${'task-42'}
                .timestamp=${'2026-05-15T10:00:00.000Z'}
                locale="en"
                .content=${'Done'}
                .labels=${LABELS}
            ></flows-chat-message>
        `);
        await elementUpdated(el);

        expect(el.shadowRoot.querySelector('.bubble-meta')).to.not.equal(null);
        expect(el.shadowRoot.querySelector('.bubble-meta .timestamp')).to.not.equal(null);
        expect(el.shadowRoot.querySelector('.bubble-observability-actions')).to.not.equal(null);

        let tracingDetail = null;
        let logsDetail = null;
        let historyDetail = null;
        el.addEventListener('show-tracing', (event) => { tracingDetail = event.detail; });
        el.addEventListener('show-logs', (event) => { logsDetail = event.detail; });
        el.addEventListener('show-durable-history', (event) => { historyDetail = event.detail; });

        const buttons = el.shadowRoot.querySelectorAll('.bubble-observability-actions .tracing-btn');
        expect(buttons.length).to.equal(3);
        buttons[0].click();
        buttons[1].click();
        buttons[2].click();

        expect(tracingDetail).to.deep.equal({ taskId: 'task-42' });
        expect(logsDetail).to.deep.equal({ sessionId: 'flow-1:ctx-1', taskId: 'task-42' });
        expect(historyDetail).to.deep.equal({ sessionId: 'flow-1:ctx-1' });
    });

    it('compact bubbles visibly distinguish user, agent, sub-agent and operator', async () => {
        const host = await fixture(html`
            <div>
                <flows-chat-message
                    role="user"
                    .showHeader=${true}
                    .headerCompact=${true}
                    .author=${{ kind: 'user' }}
                    .content=${'Нужен возврат'}
                    .labels=${LABELS}
                ></flows-chat-message>
                <flows-chat-message
                    role="assistant"
                    .showHeader=${true}
                    .headerCompact=${true}
                    .author=${{ kind: 'agent', name: 'Основной агент' }}
                    .content=${'Передаю специалисту'}
                    .labels=${LABELS}
                ></flows-chat-message>
                <flows-chat-message
                    role="assistant"
                    .showHeader=${true}
                    .headerCompact=${true}
                    .author=${{ kind: 'subagent', name: 'Агент возвратов' }}
                    .content=${'Возврат оформлен'}
                    .labels=${LABELS}
                ></flows-chat-message>
                <flows-chat-message
                    role="operator"
                    .showHeader=${true}
                    .headerCompact=${true}
                    .author=${{ kind: 'operator' }}
                    .content=${'Подтверждаю вручную'}
                    .labels=${LABELS}
                ></flows-chat-message>
            </div>
        `);
        const bubbles = [...host.querySelectorAll('flows-chat-message')];
        await Promise.all(bubbles.map((bubble) => bubble.updateComplete));

        const identities = bubbles.map((bubble) => bubble.shadowRoot.querySelector('.author-identity'));
        expect(identities.map((identity) => identity.dataset.authorKind)).to.deep.equal([
            'user',
            'agent',
            'subagent',
            'operator',
        ]);
        expect(identities.map((identity) => identity.querySelector('.author-name').textContent.trim())).to.deep.equal([
            'You',
            'Основной агент',
            'Агент возвратов',
            'Operator',
        ]);
        expect(identities[1].querySelector('.author-kind').textContent.trim()).to.equal('Agent');
        expect(identities[2].querySelector('.author-kind').textContent.trim()).to.equal('Sub-agent');
        expect(identities.every((identity) => identity.querySelector('.author-mark platform-icon'))).to.equal(true);
    });

    it('platform-chat labels the first response after handoff with the active sub-agent', async () => {
        const el = await fixture(html`
            <platform-chat
                flows-base-url="/flows"
                flow-id="lara"
                .labels=${{ ...LABELS, greeting: 'Привет', new_chat: 'Новый чат' }}
            ></platform-chat>
        `);
        const contextId = el._controller.state.currentContextId;
        el._controller.applyRuntimeVerb('task_started', {
            task_id: 'task-parent',
            context_id: contextId,
        });
        el._controller.applyRuntimeVerb('handoff_initiated', {
            task_id: 'task-parent',
            context_id: contextId,
            target_flow_id: 'returns_agent',
            target_flow_name: 'Агент возвратов',
            depth: 1,
        });
        el._controller.applyRuntimeVerb('task_started', {
            task_id: 'task-child',
            context_id: contextId,
        });
        el._controller.applyRuntimeVerb('content_chunk', {
            task_id: 'task-child',
            context_id: contextId,
            text: 'Возврат оформлен.',
        });
        await elementUpdated(el);

        const childBubble = [...el.shadowRoot.querySelectorAll('flows-chat-message')]
            .find((bubble) => bubble.taskId === 'task-child');
        expect(childBubble).to.not.equal(undefined);
        await childBubble.updateComplete;
        expect(childBubble.author).to.deep.equal({
            kind: 'subagent',
            name: 'Агент возвратов',
            flowId: 'returns_agent',
            nodeId: '',
        });
        const identity = childBubble.shadowRoot.querySelector('.author-identity');
        expect(identity.dataset.authorKind).to.equal('subagent');
        expect(identity.textContent).to.include('Агент возвратов');
        expect(identity.textContent).to.include('Sub-agent');
    });

    it('platform-chat renders handoff and handback runtime cards as visible feed items', async () => {
        const el = await fixture(html`
            <platform-chat
                flows-base-url="/flows"
                flow-id="lara"
                .labels=${{ ...LABELS, greeting: 'Привет', new_chat: 'Новый чат' }}
            ></platform-chat>
        `);
        const contextId = el._controller.state.currentContextId;
        el._controller.applyRuntimeVerb('task_started', {
            task_id: 'task-handoff-card',
            context_id: contextId,
        });
        el._controller.applyRuntimeVerb('handoff_initiated', {
            task_id: 'task-handoff-card',
            context_id: contextId,
            target_flow_id: 'returns_agent',
            target_flow_name: 'Агент возвратов',
            depth: 1,
        });
        await elementUpdated(el);

        const handoffBubble = el.shadowRoot.querySelector('flows-chat-message[data-role="handoff"]');
        expect(handoffBubble).to.not.equal(null);
        await handoffBubble.updateComplete;
        const handoffCard = handoffBubble.shadowRoot.querySelector('.handoff-card');
        expect(handoffCard).to.not.equal(null);
        expect(handoffCard.textContent).to.include('Агент возвратов');

        el._controller.applyRuntimeVerb('handback_completed', {
            task_id: 'task-handoff-card',
            context_id: contextId,
            child_flow_name: 'Агент возвратов',
            parent_flow_name: 'Основной агент',
            response: 'Возврат оформлен',
            handoff_depth: 0,
        });
        await elementUpdated(el);

        const handbackBubble = el.shadowRoot.querySelector('flows-chat-message[data-role="handback"]');
        expect(handbackBubble).to.not.equal(null);
        await handbackBubble.updateComplete;
        const handbackCard = handbackBubble.shadowRoot.querySelector('.handback-card');
        expect(handbackCard).to.not.equal(null);
        expect(handbackCard.textContent).to.include('Возврат оформлен');
    });

    it('breakpoint card shows node_id and dispatches continue-breakpoint', async () => {
        let continueDetail = null;
        let viewStateDetail = null;
        const el = await fixture(html`
            <flows-chat-message
                role="assistant"
                .breakpoint=${{ node_id: 'build_search_query', state: { foo: 1 } }}
                .labels=${{
                    ...LABELS,
                    breakpoint_continue: 'Continue',
                    breakpoint_view_state: 'View state',
                }}
            ></flows-chat-message>
        `);
        el.addEventListener('continue-breakpoint', (event) => {
            continueDetail = event.detail;
        });
        el.addEventListener('view-breakpoint-state', (event) => {
            viewStateDetail = event.detail;
        });
        await elementUpdated(el);

        const title = el.shadowRoot.querySelector('.breakpoint-title');
        expect(title).to.not.equal(null);
        expect(title.textContent).to.include('build_search_query');

        const buttons = el.shadowRoot.querySelectorAll('.breakpoint-actions button');
        expect(buttons.length).to.equal(2);
        buttons[0].click();
        buttons[1].click();
        expect(continueDetail.breakpoint.node_id).to.equal('build_search_query');
        expect(viewStateDetail.breakpoint.state).to.deep.equal({ foo: 1 });
    });

    it('durable history action shows without taskId when sessionId is set', async () => {
        const el = await fixture(html`
            <flows-chat-message
                role="assistant"
                .showHeader=${true}
                .headerCompact=${true}
                .showTraceControls=${false}
                .showLogsAction=${false}
                .showDurableHistoryAction=${true}
                session-id="flow-1:ctx-1"
                .content=${'Done'}
                .labels=${LABELS}
            ></flows-chat-message>
        `);
        await elementUpdated(el);

        expect(el.shadowRoot.querySelector('.bubble-observability-actions')).to.not.equal(null);
        expect(el.shadowRoot.querySelectorAll('.bubble-observability-actions .tracing-btn').length).to.equal(1);
    });

    it('user short text stays on one line in compact bubble', async () => {
        const el = await fixture(html`
            <flows-chat-message
                variant="embed"
                role="user"
                .showHeader=${true}
                .headerCompact=${true}
                .content=${'привет'}
                .labels=${LABELS}
            ></flows-chat-message>
        `);
        await elementUpdated(el);

        const text = el.shadowRoot.querySelector('.text');
        expect(text).to.not.equal(null);
        expect(text.textContent).to.equal('привет');
        const style = getComputedStyle(text);
        expect(style.wordBreak).to.equal('normal');
        expect(style.overflowWrap).to.equal('break-word');
    });

    it('user embed bubble uses readable meta and file colors on light palette', async () => {
        const el = await fixture(html`
            <flows-chat-message
                variant="embed"
                role="user"
                .showHeader=${true}
                .headerCompact=${true}
                .timestamp=${'2026-07-09T17:54:00.000Z'}
                locale="ru"
                .content=${'fd'}
                .files=${[{
                    file_id: 'file-docx-1',
                    original_name: '2607 - Bibligami Proposition - RU (1).docx',
                    content_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    file_size: 1024,
                }]}
                .labels=${LABELS}
                style="--flows-chat-text: #1c1f2e; --flows-chat-muted: rgba(28, 31, 46, 0.52); --flows-chat-accent-muted: rgba(109, 98, 232, 0.2);"
            ></flows-chat-message>
        `);
        await elementUpdated(el);

        const timestamp = el.shadowRoot.querySelector('.bubble-meta .timestamp');
        const fileName = el.shadowRoot.querySelector('.file-name');
        expect(timestamp).to.not.equal(null);
        expect(fileName).to.not.equal(null);

        const timestampColor = getComputedStyle(timestamp).color;
        const fileNameColor = getComputedStyle(fileName).color;
        expect(timestampColor).to.not.equal('rgb(255, 255, 255)');
        expect(fileNameColor).to.not.equal('rgb(255, 255, 255)');
        expect(timestampColor).to.equal('rgba(28, 31, 46, 0.52)');
        expect(fileNameColor).to.equal('rgb(28, 31, 46)');
    });
});
