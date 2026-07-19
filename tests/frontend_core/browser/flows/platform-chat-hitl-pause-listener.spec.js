/**
 * User-surface HITL: после operator_task паузы ChatController поднимает live tail.
 * Доставка реплик — A2A SubscribeToTask (не company WS).
 */

import { fixture, fixtureCleanup, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { registerFactory } from '@platform/lib/events/factory-registry.js';
import {
    platformWorkItemGetOp,
    platformWorkItemFactories,
} from '@platform/lib/events/resources/platform-work-item.resource.js';
import '../../../../core/frontend/static/lib/chat/platform-chat.js';
import { findActiveHitlPause } from '../../../../core/frontend/static/lib/chat/runtime/hitl-pause-listener.js';
import { installChatProfileFetchStub } from '../helpers/chat-profile-stub.js';

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

describe('platform-chat HITL live resubscribe (user surface)', () => {
    let restoreChatFetch;
    let restoreFlowFetch;

    beforeEach(() => {
        resetPlatformState();
        restoreChatFetch = installChatProfileFetchStub({ flowId: 'flow1' });
        const previousFetch = window.fetch;
        restoreFlowFetch = () => { window.fetch = previousFetch; };
        window.fetch = async (rawUrl, init = {}) => {
            const method = (init.method || 'GET').toUpperCase();
            const url = new URL(String(rawUrl), window.location.href);
            if (method === 'POST' && url.pathname === '/flows/api/v1/flow1') {
                return new Response('', {
                    status: 200,
                    headers: { 'content-type': 'text/event-stream' },
                });
            }
            return previousFetch(rawUrl, init);
        };
        for (const factory of platformWorkItemFactories) {
            registerFactory(factory);
        }
        bootstrapTestBus({
            slices: {
                [platformWorkItemGetOp.sliceKey]: platformWorkItemGetOp.slice,
            },
        });
    });

    afterEach(() => {
        restoreFlowFetch();
        restoreChatFetch();
        fixtureCleanup();
    });

    async function mountPausedChat() {
        const el = await fixture(html`
            <platform-chat
                profile="spa"
                display="page"
                flow-id="flow1"
                .flowsBaseUrl=${'/flows'}
            ></platform-chat>
        `);
        await elementUpdated(el);
        el.loadSession({
            sessionId: 'flow1:ctx1',
            flowId: 'flow1',
            contextId: 'ctx1',
            taskId: 'tsk1',
            messages: [
                {
                    id: 'u1',
                    role: 'user',
                    content: 'перехват',
                    timestamp: new Date().toISOString(),
                    taskId: 'tsk1',
                },
            ],
        });
        el._controller.applyRuntimeVerb('input_required', {
            task_id: 'tsk1',
            context_id: 'ctx1',
            message: { parts: [{ text: 'Диалог на паузе' }] },
            result_metadata: {
                platform_interrupt: {
                    question: 'Диалог на паузе',
                    body: {
                        kind: 'operator_task',
                        question: 'Диалог на паузе',
                        task_title: 'HITL',
                        assignee_queue: 'example_hitl',
                        handoff_mode: 'takeover',
                        work_item_id: 'wi_pause_1',
                    },
                },
            },
        });
        await elementUpdated(el);
        await waitFor(() => {
            const state = el.runtimeState;
            const bucket = state.messagesByContextId.ctx1;
            return Boolean(bucket && bucket.messages.some((m) => m && m.inputRequired));
        });
        return el;
    }

    it('после operator_task находит pause и стартует live tail taskId', async () => {
        const el = await mountPausedChat();
        const pause = findActiveHitlPause(el.runtimeState);
        expect(pause).to.not.equal(null);
        expect(pause.workItemId).to.equal('wi_pause_1');
        expect(pause.taskId).to.equal('tsk1');
        el._controller.syncHitlLiveTail();
        expect(el._controller._hitlLiveTaskId).to.equal('tsk1');
        el._controller.stopHitlLiveTail();
        expect(el._controller._hitlLiveTaskId).to.equal(null);
    });

    it('operator_reply verb рисует bubble (как кадр из resubscribe)', async () => {
        const el = await mountPausedChat();
        el._controller.applyRuntimeVerb('operator_reply', {
            task_id: 'tsk1',
            text: 'Здравствуйте, я оператор',
        });
        await elementUpdated(el);
        const bucket = el.runtimeState.messagesByContextId.ctx1;
        expect(
            bucket.messages.some((m) => m.role === 'operator' && m.content === 'Здравствуйте, я оператор'),
        ).to.equal(true);
    });
});
