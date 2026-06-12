import { fixture, fixtureCleanup, html, expect, elementUpdated, aTimeout, waitUntil } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { CoreEvents, FILES_EVENTS } from '@platform/lib/events/index.js';
import '../../../../core/frontend/static/lib/flows-chat/flows-chat-message.js';
import '../../../../core/frontend/static/lib/embed-chat/platform-embed-chat.js';
import '../../../../apps/flows/ui/components/chat/chat-message.js';
import '../../../../apps/flows/ui/components/chat/chat-files-panel.js';
import '../../../../apps/flows/ui/modals/flows-browser-preview-modal.js';

const LABELS = {
    role_user: 'You',
    role_assistant: 'Assistant',
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

    beforeEach(() => {
        cleanupEditorPortals();
        resetPlatformState();
        bus = bootstrapTestBus();
        restoreFetch = installDocumentEditorConfigStub();
    });

    afterEach(() => {
        restoreFetch();
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

    it('app chat-message adapter dispatches compose_edit through the platform bus', async () => {
        const events = [];
        bus.subscribeType('flows/chat/compose_edit', (event) => events.push(event));

        const el = await fixture(html`
            <chat-message role="user" content="Draft from app"></chat-message>
        `);
        await elementUpdated(el);
        const surface = el.shadowRoot.querySelector('flows-chat-message');
        await elementUpdated(surface);
        const actions = surface.shadowRoot.querySelector('platform-assistant-message-actions');
        await elementUpdated(actions);
        actions.shadowRoot.querySelectorAll('button')[1].click();

        expect(events).to.have.length(1);
        expect(events[0].payload).to.deep.equal({ text: 'Draft from app' });
    });

    it('app chat-message adapter opens browser preview through the platform modal stack', async () => {
        const events = [];
        bus.subscribeType(CoreEvents.UI_MODAL_OPEN, (event) => events.push(event));

        const el = await fixture(html`
            <chat-message
                role="assistant"
                content="Browser ready"
                .toolCalls=${[{ id: 'tc-browser', name: 'browser.open', arguments: { url: 'https://example.test' } }]}
                .toolResults=${[{ tool_call_id: 'tc-browser', name: 'browser.open', content: 'ok' }]}
                .browserPreviews=${[{
                    parentToolCallId: 'tc-browser',
                    status: 'open',
                    viewerUrl: 'https://browser.example.test/session/tc-browser',
                    currentUrl: 'https://example.test',
                    sessionId: 'tc-browser',
                }]}
            ></chat-message>
        `);
        await elementUpdated(el);
        const surface = el.shadowRoot.querySelector('flows-chat-message');
        await elementUpdated(surface);
        surface.shadowRoot.querySelector('.tool-orb-button').click();

        expect(events).to.have.length(1);
        expect(events[0].payload.kind).to.equal('flows.browser_preview');
        expect(events[0].payload.props.viewerUrl).to.equal('https://browser.example.test/session/tc-browser');
        expect(events[0].payload.props.sessionId).to.equal('tc-browser');
    });

    it('embed chat host renders messages through flows-chat-message only', async () => {
        const el = await fixture(html`
            <platform-embed-chat
                flows-base-url="/flows"
                flow-id="lara"
                .labels=${{ greeting: 'Hi from embed', new_chat: 'New chat' }}
            ></platform-embed-chat>
        `);
        await elementUpdated(el);
        await aTimeout(80);

        expect(el.shadowRoot.querySelector('flows-chat-message')).to.not.equal(null);
        expect(el.shadowRoot.querySelector('.msg')).to.equal(null);
    });

    it('app files panel opens existing document capability through the global file viewer event', async () => {
        const events = [];
        bus.subscribeType(FILES_EVENTS.OPEN_REQUESTED, (event) => events.push(event));
        const el = await fixture(html`
            <chat-files-panel
                inline
                .files=${[{
                    file_id: 'file-docx-1',
                    original_name: 'Contract.docx',
                    content_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    capabilities: {
                        document: {
                            binding_id: 'binding-docx-1',
                            file_id: 'file-docx-1',
                            editor_url: 'about:blank#binding-docx-1',
                        },
                    },
                }]}
            ></chat-files-panel>
        `);
        await elementUpdated(el);

        el.shadowRoot.querySelector('.trigger').click();
        await elementUpdated(el);
        el.shadowRoot.querySelector('.file-row').click();
        await elementUpdated(el);
        await waitUntil(() => events.length === 1, 'file open requested');

        expect(events[0].payload.file.file_id).to.equal('file-docx-1');
        expect(events[0].payload.file.original_name).to.equal('Contract.docx');
        expect(events[0].payload.source).to.equal('flows_chat_files_panel');
    });

    it('embed host exposes document file blocks through the same files panel and global file viewer event', async () => {
        const events = [];
        bus.subscribeType(FILES_EVENTS.OPEN_REQUESTED, (event) => events.push(event));
        const el = await fixture(html`
            <platform-embed-chat
                flows-base-url="https://flows.example/flows"
                platform-ui-origin="https://platform.example"
                flow-id="lara"
                .labels=${{ greeting: 'Hi from embed', new_chat: 'New chat' }}
            ></platform-embed-chat>
        `);
        el._messages = [{
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
        }];
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

    it('embed host merges A2A files events into the shared files panel', async () => {
        const el = await fixture(html`
            <platform-embed-chat
                flows-base-url="/flows"
                flow-id="lara"
                .labels=${{ greeting: 'Hi from embed', new_chat: 'New chat' }}
            ></platform-embed-chat>
        `);
        el._messages = [{
            id: 'assistant-files-event',
            role: 'assistant',
            content: '',
            files: [],
        }];
        el._applyRuntimeEvent({
            type: 'files_event',
            payload: {
                event: {
                    payload: {
                        files: [{
                            file_id: 'file-event-1',
                            original_name: 'Generated.txt',
                            content_type: 'text/plain',
                            url: '/flows/api/v1/files/download/file-event-1',
                        }],
                    },
                },
            },
        }, 'assistant-files-event');
        await elementUpdated(el);

        const panel = el.shadowRoot.querySelector('flows-chat-files-panel');
        expect(panel).to.not.equal(null);
        expect(panel.files.map((file) => file.file_id)).to.deep.equal(['file-event-1']);
    });
});
