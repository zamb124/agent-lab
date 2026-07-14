/**
 * Транспорт встроенного чата HITL (operator_handoff): snapshot + POST ask.
 * Live tail — tasks/resubscribe (мокаем fetch: snapshot OK, resubscribe не резолвится).
 */

import { describe, it, expect, vi, afterEach } from 'vitest';
import {
    OperatorConversationTransport,
    turnToBubble,
} from '../../../../core/frontend/static/lib/chat/runtime/operator-conversation-transport.js';

const CONVERSATION = {
    session_id: 'flow1:ctx1',
    context_id: 'ctx1',
    flow_id: 'flow1',
    branch_id: 'default',
    a2a_task_id: 'tsk-hitl-1',
};

function fakeController() {
    const calls = [];
    return {
        calls,
        applyRuntimeVerb(verb, payload) {
            calls.push({ verb, payload });
        },
        relayA2aFrame() {
            return { terminal: false };
        },
    };
}

function jsonResponse(body) {
    return { ok: true, status: 200, json: async () => body };
}

/** Snapshot GET успешен; resubscribe SSE — висящий reader до abort. */
function makeFetch(snapshotBody) {
    return vi.fn(async (url, init) => {
        const u = String(url);
        if (u.includes('/conversation/messages') || (init && init.method === 'POST' && u.includes('/conversation'))) {
            return null;
        }
        if (u.includes('/conversation') && (!init || init.method === 'GET' || init.method == null)) {
            return jsonResponse(snapshotBody);
        }
        // tasks/resubscribe SSE
        const stream = new ReadableStream({
            start() {
                /* держим открытым до abort */
            },
        });
        return {
            ok: true,
            status: 200,
            headers: { get: (name) => (name.toLowerCase() === 'content-type' ? 'text/event-stream' : null) },
            body: stream,
        };
    });
}

afterEach(() => {
    vi.restoreAllMocks();
});

describe('operator-transport: turnToBubble', () => {
    it('agent рисуется как assistant, operator/user сохраняются', () => {
        expect(turnToBubble({ message_id: 'm1', role: 'agent', text: 'a' }).role).toBe('assistant');
        expect(turnToBubble({ message_id: 'm2', role: 'operator', text: 'o' }).role).toBe('operator');
        expect(turnToBubble({ message_id: 'm3', role: 'user', text: 'u' }).role).toBe('user');
    });
});

describe('operator-transport: loadHistory', () => {
    it('снимок -> session_loaded с taskId, system отфильтрован', async () => {
        const controller = fakeController();
        const fetchImpl = makeFetch({
            work_item_id: 'wi1',
            turns: [
                { cursor: 1, message_id: 'm1', role: 'user', text: 'привет' },
                { cursor: 2, message_id: 'm2', role: 'agent', text: 'здравствуйте' },
                { cursor: 3, message_id: 'sys', role: 'system', text: 'internal' },
            ],
            cursor: 3,
            policy: { mode: 'takeover', can_send: true, can_complete: true, conversation: CONVERSATION },
        });
        const transport = new OperatorConversationTransport({
            workItemId: 'wi1',
            conversation: CONVERSATION,
            baseUrl: '/flows',
            fetchImpl,
        });
        transport.attach(controller);
        await transport.loadHistory();
        transport.dispose();

        const loaded = controller.calls.find((c) => c.verb === 'session_loaded');
        expect(loaded).toBeTruthy();
        expect(loaded.payload.contextId).toBe('ctx1');
        expect(loaded.payload.taskId).toBe('tsk-hitl-1');
        expect(loaded.payload.messages.map((m) => m.role)).toEqual(['user', 'assistant']);
    });

    it('без a2a_task_id — throw', () => {
        expect(() => new OperatorConversationTransport({
            workItemId: 'wi1',
            conversation: { ...CONVERSATION, a2a_task_id: '' },
            fetchImpl: vi.fn(),
        })).toThrow(/a2a_task_id/);
    });
});

describe('operator-transport: send', () => {
    it('POST текста, эхо turn -> user_message_added (operator)', async () => {
        const controller = fakeController();
        const fetchImpl = vi.fn(async (url, init) => {
            if (String(url).includes('/conversation/messages')) {
                const body = JSON.parse(init.body);
                expect(body.text).toBe('ответ оператора');
                return jsonResponse({ cursor: 1, message_id: 'op1', role: 'operator', text: body.text });
            }
            if (String(url).includes('/conversation')) {
                return jsonResponse({ work_item_id: 'wi1', turns: [], cursor: 0, policy: {} });
            }
            const stream = new ReadableStream({ start() {} });
            return {
                ok: true,
                status: 200,
                headers: { get: () => 'text/event-stream' },
                body: stream,
            };
        });
        const transport = new OperatorConversationTransport({
            workItemId: 'wi1',
            conversation: CONVERSATION,
            fetchImpl,
        });
        transport.attach(controller);
        await transport.loadHistory();
        await transport.send({ message: '  ответ оператора  ' });
        transport.dispose();

        const appended = controller.calls.filter((c) => c.verb === 'user_message_added');
        expect(appended.length).toBe(1);
        expect(appended[0].payload.message.role).toBe('operator');
        expect(appended[0].payload.message.content).toBe('ответ оператора');
    });

    it('пустой текст не шлёт запрос', async () => {
        const controller = fakeController();
        const fetchImpl = makeFetch({ work_item_id: 'wi1', turns: [], cursor: 0, policy: {} });
        const transport = new OperatorConversationTransport({
            workItemId: 'wi1',
            conversation: CONVERSATION,
            fetchImpl,
        });
        transport.attach(controller);
        await transport.loadHistory();
        fetchImpl.mockClear();
        await transport.send({ message: '   ' });
        expect(fetchImpl).not.toHaveBeenCalled();
        transport.dispose();
    });
});

describe('operator-transport: dispose', () => {
    it('останавливает live tail без ошибок', async () => {
        const controller = fakeController();
        const fetchImpl = makeFetch({ work_item_id: 'wi1', turns: [], cursor: 0, policy: {} });
        const transport = new OperatorConversationTransport({
            workItemId: 'wi1',
            conversation: CONVERSATION,
            fetchImpl,
        });
        transport.attach(controller);
        await transport.loadHistory();
        transport.dispose();
        expect(true).toBe(true);
    });
});
