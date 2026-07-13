/**
 * Транспорт встроенного чата HITL-задачи (operator_handoff).
 *
 * Проверяет, что снимок/push/эхо POST маппятся в chat-reducer verbs, дедуп идёт
 * по message_id, `agent` рисуется как `assistant`, а `system` в чат не попадает.
 */

import { describe, it, expect, vi } from 'vitest';
import {
    OperatorConversationTransport,
    turnToBubble,
    HITL_CONVERSATION_TURN_APPENDED,
} from '../../../../core/frontend/static/lib/chat/runtime/operator-conversation-transport.js';

const CONVERSATION = {
    session_id: 'flow1:ctx1',
    context_id: 'ctx1',
    flow_id: 'flow1',
    branch_id: 'default',
};

function fakeController() {
    const calls = [];
    return {
        calls,
        applyRuntimeVerb(verb, payload) {
            calls.push({ verb, payload });
        },
    };
}

function fakeBus() {
    let handler = null;
    return {
        subscribeType(type, cb) {
            if (type !== HITL_CONVERSATION_TURN_APPENDED) {
                throw new Error(`unexpected type ${type}`);
            }
            handler = cb;
            return () => {
                handler = null;
            };
        },
        emit(payload) {
            if (handler) {
                handler({ type: HITL_CONVERSATION_TURN_APPENDED, payload });
            }
        },
        get subscribed() {
            return handler !== null;
        },
    };
}

function jsonResponse(body) {
    return { ok: true, status: 200, json: async () => body };
}

describe('operator-transport: turnToBubble', () => {
    it('agent рисуется как assistant, operator/user сохраняются', () => {
        expect(turnToBubble({ message_id: 'm1', role: 'agent', text: 'a' }).role).toBe('assistant');
        expect(turnToBubble({ message_id: 'm2', role: 'operator', text: 'o' }).role).toBe('operator');
        expect(turnToBubble({ message_id: 'm3', role: 'user', text: 'u' }).role).toBe('user');
    });
});

describe('operator-transport: loadHistory', () => {
    it('снимок -> session_loaded, system отфильтрован, подписка на push поднята', async () => {
        const controller = fakeController();
        const bus = fakeBus();
        const fetchImpl = vi.fn(async () => jsonResponse({
            work_item_id: 'wi1',
            turns: [
                { cursor: 1, message_id: 'm1', role: 'user', text: 'привет' },
                { cursor: 2, message_id: 'm2', role: 'agent', text: 'здравствуйте' },
                { cursor: 3, message_id: 'sys', role: 'system', text: 'internal' },
            ],
            cursor: 3,
            policy: { mode: 'takeover', can_send: true, can_complete: true, conversation: CONVERSATION },
        }));
        const transport = new OperatorConversationTransport({
            workItemId: 'wi1',
            conversation: CONVERSATION,
            baseUrl: '/flows',
            bus,
            fetchImpl,
        });
        transport.attach(controller);
        await transport.loadHistory();

        expect(fetchImpl).toHaveBeenCalledOnce();
        const loaded = controller.calls.find((c) => c.verb === 'session_loaded');
        expect(loaded).toBeTruthy();
        expect(loaded.payload.contextId).toBe('ctx1');
        expect(loaded.payload.messages.map((m) => m.role)).toEqual(['user', 'assistant']);
        expect(bus.subscribed).toBe(true);
    });
});

describe('operator-transport: realtime + dedup', () => {
    it('push добавляет user_message_added; эхо снимка/повтор дедупятся', async () => {
        const controller = fakeController();
        const bus = fakeBus();
        const fetchImpl = vi.fn(async () => jsonResponse({
            work_item_id: 'wi1',
            turns: [{ cursor: 1, message_id: 'm1', role: 'user', text: 'привет' }],
            cursor: 1,
            policy: { mode: 'takeover', can_send: true, can_complete: true, conversation: CONVERSATION },
        }));
        const transport = new OperatorConversationTransport({
            workItemId: 'wi1',
            conversation: CONVERSATION,
            bus,
            fetchImpl,
        });
        transport.attach(controller);
        await transport.loadHistory();

        // Повтор уже загруженного turn (m1) должен быть отброшен.
        bus.emit({ work_item_id: 'wi1', turn: { cursor: 1, message_id: 'm1', role: 'user', text: 'привет' } });
        // Новый turn от пользователя во время takeover.
        bus.emit({ work_item_id: 'wi1', turn: { cursor: 2, message_id: 'm2', role: 'user', text: 'ещё' } });
        // Дубликат нового turn.
        bus.emit({ work_item_id: 'wi1', turn: { cursor: 2, message_id: 'm2', role: 'user', text: 'ещё' } });
        // Чужой work_item — игнор.
        bus.emit({ work_item_id: 'other', turn: { cursor: 5, message_id: 'x', role: 'user', text: 'skip' } });

        const appended = controller.calls.filter((c) => c.verb === 'user_message_added');
        expect(appended.length).toBe(1);
        expect(appended[0].payload.message.id).toBe('m2');
        expect(appended[0].payload.contextId).toBe('ctx1');
    });
});

describe('operator-transport: send', () => {
    it('POST текста, эхо turn -> user_message_added (operator)', async () => {
        const controller = fakeController();
        const bus = fakeBus();
        const fetchImpl = vi.fn(async (url, init) => {
            if (String(url).endsWith('/conversation')) {
                return jsonResponse({ work_item_id: 'wi1', turns: [], cursor: 0, policy: {} });
            }
            const body = JSON.parse(init.body);
            expect(body.text).toBe('ответ оператора');
            expect(typeof body.idempotency_key).toBe('string');
            return jsonResponse({ cursor: 1, message_id: 'op1', role: 'operator', text: body.text });
        });
        const transport = new OperatorConversationTransport({
            workItemId: 'wi1',
            conversation: CONVERSATION,
            bus,
            fetchImpl,
        });
        transport.attach(controller);
        await transport.loadHistory();
        await transport.send({ message: '  ответ оператора  ' });

        const appended = controller.calls.filter((c) => c.verb === 'user_message_added');
        expect(appended.length).toBe(1);
        expect(appended[0].payload.message.role).toBe('operator');
        expect(appended[0].payload.message.content).toBe('ответ оператора');
    });

    it('пустой текст не шлёт запрос', async () => {
        const controller = fakeController();
        const bus = fakeBus();
        const fetchImpl = vi.fn(async () => jsonResponse({ work_item_id: 'wi1', turns: [], cursor: 0, policy: {} }));
        const transport = new OperatorConversationTransport({
            workItemId: 'wi1',
            conversation: CONVERSATION,
            bus,
            fetchImpl,
        });
        transport.attach(controller);
        await transport.loadHistory();
        fetchImpl.mockClear();
        await transport.send({ message: '   ' });
        expect(fetchImpl).not.toHaveBeenCalled();
    });
});

describe('operator-transport: dispose', () => {
    it('снимает подписку на шину', async () => {
        const controller = fakeController();
        const bus = fakeBus();
        const fetchImpl = vi.fn(async () => jsonResponse({ work_item_id: 'wi1', turns: [], cursor: 0, policy: {} }));
        const transport = new OperatorConversationTransport({
            workItemId: 'wi1',
            conversation: CONVERSATION,
            bus,
            fetchImpl,
        });
        transport.attach(controller);
        await transport.loadHistory();
        expect(bus.subscribed).toBe(true);
        transport.dispose();
        expect(bus.subscribed).toBe(false);
    });
});
