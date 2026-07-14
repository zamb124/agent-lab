/**
 * Operator handoff surface: REST conversation snapshot + live tasks/resubscribe.
 * Company WS turn_appended не канал пузырей чата.
 */

import { fixture, fixtureCleanup, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import '../../../../core/frontend/static/lib/chat/platform-chat.js';

const CONVERSATION = {
    session_id: 'flow1:ctx1',
    context_id: 'ctx1',
    flow_id: 'flow1',
    branch_id: 'default',
    a2a_task_id: 'tsk-hitl-op-1',
};

function snapshotResponse(turns) {
    return new Response(JSON.stringify({
        work_item_id: 'wi1',
        turns,
        cursor: turns.length,
        policy: { mode: 'takeover', can_send: true, can_complete: true, conversation: CONVERSATION },
    }), { status: 200, headers: { 'content-type': 'application/json; charset=utf-8' } });
}

function hangingSseResponse() {
    const stream = new ReadableStream({
        start() {
            /* держим open до abort (live resubscribe) */
        },
    });
    return new Response(stream, {
        status: 200,
        headers: { 'content-type': 'text/event-stream' },
    });
}

async function waitFor(predicate, { timeout = 2000 } = {}) {
    const start = Date.now();
    while (Date.now() - start < timeout) {
        if (predicate()) {
            return;
        }
        await new Promise((r) => setTimeout(r, 20));
    }
    throw new Error('waitFor: timeout');
}

describe('platform-chat operator_handoff', function () {
    this.timeout(8000);

    let restoreFetch;
    let sentBodies;
    let resubscribeCalls;

    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
        sentBodies = [];
        resubscribeCalls = 0;
        const previousFetch = window.fetch;
        restoreFetch = () => { window.fetch = previousFetch; };
        window.fetch = async (rawUrl, init = {}) => {
            const method = (init.method || 'GET').toUpperCase();
            const url = new URL(String(rawUrl), window.location.href);
            if (method === 'GET' && /\/flows\/api\/v1\/hitl\/wi1\/conversation$/.test(url.pathname)) {
                return snapshotResponse([
                    { cursor: 1, message_id: 'm1', role: 'user', text: 'у меня проблема' },
                    { cursor: 2, message_id: 'm2', role: 'agent', text: 'секунду, зову оператора' },
                ]);
            }
            if (method === 'POST' && /\/conversation\/messages$/.test(url.pathname)) {
                sentBodies.push(JSON.parse(init.body));
                return new Response(
                    JSON.stringify({ cursor: 3, message_id: 'op1', role: 'operator', text: 'здравствуйте, помогу' }),
                    { status: 200, headers: { 'content-type': 'application/json; charset=utf-8' } },
                );
            }
            if (method === 'POST' && /\/flows\/api\/v1\/flow1$/.test(url.pathname)) {
                const body = typeof init.body === 'string' ? JSON.parse(init.body) : {};
                if (body.method === 'tasks/resubscribe') {
                    resubscribeCalls += 1;
                    return hangingSseResponse();
                }
            }
            return previousFetch(rawUrl, init);
        };
    });

    afterEach(() => {
        if (restoreFetch) {
            restoreFetch();
            restoreFetch = null;
        }
        fixtureCleanup();
    });

    async function mount(policy) {
        const el = await fixture(html`
            <platform-chat
                profile="operator_handoff"
                display="page"
                hide-header
                work-item-id="wi1"
                .interactionPolicy=${policy}
                .flowsBaseUrl=${'/flows'}
            ></platform-chat>
        `);
        await elementUpdated(el);
        return el;
    }

    const takeoverPolicy = { mode: 'takeover', can_send: true, can_complete: true, conversation: CONVERSATION };
    const singleReplyPolicy = { mode: 'single_reply', can_send: false, can_complete: true, conversation: CONVERSATION };

    it('takeover: рендерит историю снимка теми же бабблами и показывает композер', async () => {
        const el = await mount(takeoverPolicy);
        await waitFor(() => el.renderRoot.querySelectorAll('flows-chat-message').length >= 2);
        const bubbles = el.renderRoot.querySelectorAll('flows-chat-message');
        expect(bubbles.length).to.equal(2);
        expect(el.renderRoot.querySelector('flows-chat-input')).to.not.equal(null);
        await waitFor(() => resubscribeCalls >= 1);
    });

    it('takeover: runtime verb operator_reply (кадр resubscribe) добавляет баббл', async () => {
        const el = await mount(takeoverPolicy);
        await waitFor(() => el.renderRoot.querySelectorAll('flows-chat-message').length >= 2);
        el._controller.applyRuntimeVerb('operator_reply', {
            task_id: CONVERSATION.a2a_task_id,
            text: 'спасибо, жду',
        });
        await waitFor(() => el.renderRoot.querySelectorAll('flows-chat-message').length >= 3);
        expect(el.renderRoot.querySelectorAll('flows-chat-message').length).to.equal(3);
    });

    it('takeover: повтор того же operator_reply текста не дублирует баббл', async () => {
        const el = await mount(takeoverPolicy);
        await waitFor(() => el.renderRoot.querySelectorAll('flows-chat-message').length >= 2);
        const payload = {
            task_id: CONVERSATION.a2a_task_id,
            text: 'один ответ',
        };
        el._controller.applyRuntimeVerb('operator_reply', payload);
        el._controller.applyRuntimeVerb('operator_reply', payload);
        await waitFor(() => el.renderRoot.querySelectorAll('flows-chat-message').length >= 3);
        await new Promise((r) => setTimeout(r, 80));
        expect(el.renderRoot.querySelectorAll('flows-chat-message').length).to.equal(3);
    });

    it('single_reply: композер виден при can_complete (Send = complete)', async () => {
        const el = await mount(singleReplyPolicy);
        await waitFor(() => el.renderRoot.querySelectorAll('flows-chat-message').length >= 2);
        const input = el.renderRoot.querySelector('flows-chat-input');
        expect(input).to.not.equal(null);
        expect(input.shadowRoot.querySelector('.attach-btn')).to.not.equal(null);
    });
});
