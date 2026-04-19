/**
 * flows/chat — extraReducer для push-событий чата.
 *
 * Тесты проверяют, что push-события flows/chat/* корректно обновляют
 * messagesByContextId.
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { collectFactories } from '@platform/lib/events/factories/register.js';
import {
    chatResource,
    chatSendOp,
    chatCancelOp,
} from '../../../../apps/flows/ui/events/resources/chat.resource.js';
import { resetFactories } from '../../helpers/factory-fixtures.js';
import { buildBus } from '../../helpers/bus-fixtures.js';
import { registerFactory } from '@platform/lib/events/factory-registry.js';

beforeEach(() => resetFactories());
afterEach(() => resetFactories());

function build() {
    registerFactory(chatResource);
    registerFactory(chatSendOp);
    registerFactory(chatCancelOp);
    const collected = collectFactories([chatResource, chatSendOp, chatCancelOp]);
    return buildBus({ slices: collected.slices });
}

describe('flows/chat extraReducer: session lifecycle', () => {
    it('session_init создаёт пустой контекст', () => {
        const { bus, getState } = build();
        bus.dispatch('flows/chat/session_init', { flowId: 'demo', contextId: 'ctx1' });
        const s = getState().flowsChat;
        expect(s.currentContextId).toBe('ctx1');
        expect(s.messagesByContextId.ctx1.messages).toEqual([]);
        expect(s.streaming).toBe(false);
    });

    it('user_message_added добавляет сообщение в текущий контекст', () => {
        const { bus, getState } = build();
        bus.dispatch('flows/chat/session_init', { flowId: 'demo', contextId: 'ctx1' });
        bus.dispatch('flows/chat/user_message_added', {
            contextId: 'ctx1',
            message: { id: 'u1', role: 'user', content: 'hello' },
        });
        const s = getState().flowsChat;
        expect(s.messagesByContextId.ctx1.messages.length).toBe(1);
        expect(s.messagesByContextId.ctx1.messages[0].content).toBe('hello');
    });

    it('chat_send/succeeded ack привязывает task_id к bucket', () => {
        const { bus, getState } = build();
        bus.dispatch('flows/chat/session_init', { flowId: 'demo', contextId: 'ctx1' });
        bus.dispatch('flows/chat_send/succeeded', { result: { task_id: 'tsk1', context_id: 'ctx1' } });
        const s = getState().flowsChat;
        expect(s.currentTaskId).toBe('tsk1');
        expect(s.streaming).toBe(true);
        expect(s.messagesByContextId.ctx1.taskId).toBe('tsk1');
    });
});

describe('flows/chat extraReducer: push-события', () => {
    function setup() {
        const built = build();
        built.bus.dispatch('flows/chat/session_init', { flowId: 'demo', contextId: 'ctx1' });
        built.bus.dispatch('flows/chat_send/succeeded', { result: { task_id: 'tsk1', context_id: 'ctx1' } });
        return built;
    }

    it('content_chunk накапливает текст ассистента', () => {
        const { bus, getState } = setup();
        bus.dispatch('flows/chat/content_chunk', { task_id: 'tsk1', text: 'Hello ' });
        bus.dispatch('flows/chat/content_chunk', { task_id: 'tsk1', text: 'world' });
        const msgs = getState().flowsChat.messagesByContextId.ctx1.messages;
        const assistant = msgs.find((m) => m.role === 'assistant');
        expect(assistant).toBeDefined();
        expect(assistant.content).toBe('Hello world');
    });

    it('reasoning_chunk накапливает текст в reasoning', () => {
        const { bus, getState } = setup();
        bus.dispatch('flows/chat/reasoning_chunk', { task_id: 'tsk1', text: 'thinking…' });
        const msgs = getState().flowsChat.messagesByContextId.ctx1.messages;
        const assistant = msgs.find((m) => m.role === 'assistant');
        expect(assistant.reasoning).toBe('thinking…');
    });

    it('tool_calls добавляются без дублей', () => {
        const { bus, getState } = setup();
        bus.dispatch('flows/chat/tool_calls', {
            task_id: 'tsk1',
            tool_calls: [{ id: 'tc1', name: 'foo' }],
        });
        bus.dispatch('flows/chat/tool_calls', {
            task_id: 'tsk1',
            tool_calls: [{ id: 'tc1', name: 'foo' }, { id: 'tc2', name: 'bar' }],
        });
        const msgs = getState().flowsChat.messagesByContextId.ctx1.messages;
        const assistant = msgs.find((m) => m.role === 'assistant');
        expect(assistant.toolCalls.length).toBe(2);
    });

    it('tool_result добавляется один раз', () => {
        const { bus, getState } = setup();
        bus.dispatch('flows/chat/tool_result', {
            task_id: 'tsk1',
            tool_result: { id: 'tr1', value: 42 },
        });
        bus.dispatch('flows/chat/tool_result', {
            task_id: 'tsk1',
            tool_result: { id: 'tr1', value: 42 },
        });
        const msgs = getState().flowsChat.messagesByContextId.ctx1.messages;
        const assistant = msgs.find((m) => m.role === 'assistant');
        expect(assistant.toolResults.length).toBe(1);
    });

    it('completed снимает streaming и закрывает task', () => {
        const { bus, getState } = setup();
        bus.dispatch('flows/chat/content_chunk', { task_id: 'tsk1', text: 'done' });
        bus.dispatch('flows/chat/completed', { task_id: 'tsk1', content: 'done' });
        const s = getState().flowsChat;
        expect(s.streaming).toBe(false);
        const assistant = s.messagesByContextId.ctx1.messages.find((m) => m.role === 'assistant');
        expect(assistant.streaming).toBe(false);
    });

    it('failed выставляет error и снимает streaming', () => {
        const { bus, getState } = setup();
        bus.dispatch('flows/chat/failed', { task_id: 'tsk1', error: 'bad' });
        const s = getState().flowsChat;
        expect(s.streaming).toBe(false);
        const assistant = s.messagesByContextId.ctx1.messages.find((m) => m.role === 'assistant');
        expect(assistant.error).toBe('bad');
    });

    it('breakpoint снимает streaming и сохраняет breakpoint', () => {
        const { bus, getState } = setup();
        bus.dispatch('flows/chat/breakpoint', {
            task_id: 'tsk1',
            breakpoint: { node_id: 'n1', state: { foo: 1 } },
        });
        const s = getState().flowsChat;
        expect(s.streaming).toBe(false);
        const assistant = s.messagesByContextId.ctx1.messages.find((m) => m.role === 'assistant');
        expect(assistant.breakpoint.node_id).toBe('n1');
    });

    it('input_required выставляет inputRequired', () => {
        const { bus, getState } = setup();
        bus.dispatch('flows/chat/input_required', {
            task_id: 'tsk1',
            result_metadata: { handoff: true },
            message_metadata: { hint: 'fill form' },
        });
        const s = getState().flowsChat;
        const assistant = s.messagesByContextId.ctx1.messages.find((m) => m.role === 'assistant');
        expect(assistant.inputRequired).toBeTruthy();
        expect(assistant.inputRequired.resultMetadata.handoff).toBe(true);
    });

    it('operator_reply добавляет отдельное сообщение operator', () => {
        const { bus, getState } = setup();
        bus.dispatch('flows/chat/operator_reply', { task_id: 'tsk1', text: 'hi from op' });
        const msgs = getState().flowsChat.messagesByContextId.ctx1.messages;
        const op = msgs.find((m) => m.role === 'operator');
        expect(op).toBeDefined();
        expect(op.content).toBe('hi from op');
    });

    it('operator_files прикрепляет к последнему operator-сообщению', () => {
        const { bus, getState } = setup();
        bus.dispatch('flows/chat/operator_reply', { task_id: 'tsk1', text: 'see attached' });
        bus.dispatch('flows/chat/operator_files', { task_id: 'tsk1', file_ids: ['f1', 'f2'] });
        const msgs = getState().flowsChat.messagesByContextId.ctx1.messages;
        const op = msgs.filter((m) => m.role === 'operator');
        expect(op.length).toBe(1);
        expect(op[0].fileIds).toEqual(['f1', 'f2']);
    });
});
