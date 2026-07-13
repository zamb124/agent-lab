import { fixture, fixtureCleanup, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import '../../../../core/frontend/static/lib/chat/platform-chat.js';

const CONVERSATION = {
    session_id: 'flow1:ctx1',
    context_id: 'ctx1',
    flow_id: 'flow1',
    branch_id: 'default',
};

const HITL_CONVERSATION_TURN_APPENDED = 'flows/hitl_conversation/turn_appended';

function snapshotResponse(turns) {
    return new Response(JSON.stringify({
        work_item_id: 'wi1',
        turns,
        cursor: turns.length,
        policy: { mode: 'takeover', can_send: true, can_complete: true, conversation: CONVERSATION },
    }), { status: 200, headers: { 'content-type': 'application/json; charset=utf-8' } });
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

describe('platform-chat operator_handoff', () => {
    /** @type {ReturnType<typeof bootstrapTestBus>} */
    let bus;
    let restoreFetch;
    let sentBodies;

    beforeEach(() => {
        resetPlatformState();
        bus = bootstrapTestBus();
        sentBodies = [];
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
    });

    it('takeover: push flows/hitl_conversation/turn_appended добавляет новый баббл', async () => {
        const el = await mount(takeoverPolicy);
        await waitFor(() => el.renderRoot.querySelectorAll('flows-chat-message').length >= 2);
        bus.dispatch(HITL_CONVERSATION_TURN_APPENDED, {
            work_item_id: 'wi1',
            session_id: CONVERSATION.session_id,
            turn: { cursor: 3, message_id: 'm3', role: 'user', text: 'спасибо, жду' },
        });
        await waitFor(() => el.renderRoot.querySelectorAll('flows-chat-message').length >= 3);
        expect(el.renderRoot.querySelectorAll('flows-chat-message').length).to.equal(3);
    });

    it('takeover: дубликат push по message_id не создаёт второй баббл', async () => {
        const el = await mount(takeoverPolicy);
        await waitFor(() => el.renderRoot.querySelectorAll('flows-chat-message').length >= 2);
        const dup = {
            work_item_id: 'wi1',
            session_id: CONVERSATION.session_id,
            turn: { cursor: 1, message_id: 'm1', role: 'user', text: 'у меня проблема' },
        };
        bus.dispatch(HITL_CONVERSATION_TURN_APPENDED, dup);
        bus.dispatch(HITL_CONVERSATION_TURN_APPENDED, dup);
        await new Promise((r) => setTimeout(r, 100));
        expect(el.renderRoot.querySelectorAll('flows-chat-message').length).to.equal(2);
    });

    it('single_reply: композер скрыт (read-only диалог)', async () => {
        const el = await mount(singleReplyPolicy);
        await waitFor(() => el.renderRoot.querySelectorAll('flows-chat-message').length >= 2);
        expect(el.renderRoot.querySelector('flows-chat-input')).to.equal(null);
    });
});
