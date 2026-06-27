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
    relayA2aVoiceStreamRpcFrame,
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
        expect(s.runTraceByContextId.ctx1).toEqual([]);
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

    it('chat_send/succeeded после полного стрима привязывает task_id, streaming false', () => {
        const { bus, getState } = build();
        bus.dispatch('flows/chat/session_init', { flowId: 'demo', contextId: 'ctx1' });
        bus.dispatch('flows/chat_send/succeeded', { result: { task_id: 'tsk1', context_id: 'ctx1' } });
        const s = getState().flowsChat;
        expect(s.currentTaskId).toBe('tsk1');
        expect(s.streaming).toBe(false);
        expect(s.messagesByContextId.ctx1.taskId).toBe('tsk1');
    });
});

describe('flows/chat extraReducer: task_started placeholder', () => {
    it('task_started создаёт плейсхолдер ассистента со streaming', () => {
        const { bus, getState } = build();
        bus.dispatch('flows/chat/session_init', { flowId: 'demo', contextId: 'ctx1' });
        bus.dispatch('flows/chat/user_message_added', {
            contextId: 'ctx1',
            message: { id: 'u1', role: 'user', content: 'hello' },
        });
        bus.dispatch('flows/chat/task_started', { task_id: 'tsk1', context_id: 'ctx1' });
        const s = getState().flowsChat;
        expect(s.streaming).toBe(true);
        const msgs = s.messagesByContextId.ctx1.messages;
        const assistant = msgs.find((m) => m.role === 'assistant' && m.taskId === 'tsk1');
        expect(assistant).toBeDefined();
        expect(assistant.id).toBe('assistant_tsk1');
        expect(assistant.streaming).toBe(true);
        expect(assistant.content).toBe('');
        expect(assistant.activity).toBe('');
    });

    it('reasoning_chunk после task_started накапливается в том же сообщении', () => {
        const { bus, getState } = build();
        bus.dispatch('flows/chat/session_init', { flowId: 'demo', contextId: 'ctx1' });
        bus.dispatch('flows/chat/user_message_added', {
            contextId: 'ctx1',
            message: { id: 'u1', role: 'user', content: 'hello' },
        });
        bus.dispatch('flows/chat/task_started', { task_id: 'tsk1', context_id: 'ctx1' });
        bus.dispatch('flows/chat/reasoning_chunk', { task_id: 'tsk1', text: 'a' });
        const assistants = getState().flowsChat.messagesByContextId.ctx1.messages.filter(
            (m) => m && m.role === 'assistant' && m.taskId === 'tsk1',
        );
        expect(assistants.length).toBe(1);
        expect(assistants[0].reasoning).toBe('a');
    });

    it('activity обновляет поле ассистента', () => {
        const { bus, getState } = build();
        bus.dispatch('flows/chat/session_init', { flowId: 'demo', contextId: 'ctx1' });
        bus.dispatch('flows/chat/task_started', { task_id: 'tsk1', context_id: 'ctx1' });
        bus.dispatch('flows/chat/activity', { task_id: 'tsk1', text: 'Status line' });
        const assistant = getState().flowsChat.messagesByContextId.ctx1.messages.find(
            (m) => m.role === 'assistant' && m.taskId === 'tsk1',
        );
        expect(assistant.activity).toBe('Status line');
    });

    it('reasoning_chunk без task_started и со streaming false не пишет в messages', () => {
        const { bus, getState } = build();
        bus.dispatch('flows/chat/session_init', { flowId: 'demo', contextId: 'ctx1' });
        bus.dispatch('flows/chat/user_message_added', {
            contextId: 'ctx1',
            message: { id: 'u1', role: 'user', content: 'hi' },
        });
        bus.dispatch('flows/chat/reasoning_chunk', { task_id: 'tsk1', text: 'x' });
        const msgs = getState().flowsChat.messagesByContextId.ctx1.messages;
        expect(msgs.find((m) => m && m.role === 'assistant')).toBeUndefined();
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

    it('повторный completed для того же task_id не создаёт второго ассистента', () => {
        const { bus, getState } = setup();
        bus.dispatch('flows/chat/content_chunk', { task_id: 'tsk1', text: 'done' });
        bus.dispatch('flows/chat/completed', { task_id: 'tsk1', content: 'done' });
        bus.dispatch('flows/chat/completed', { task_id: 'tsk1', content: 'done' });
        const msgs = getState().flowsChat.messagesByContextId.ctx1.messages;
        const assistants = msgs.filter(
            (m) => m && m.role === 'assistant' && m.taskId === 'tsk1',
        );
        expect(assistants.length).toBe(1);
        expect(assistants[0].content).toBe('done');
    });

    it('failed выставляет error и снимает streaming', () => {
        const { bus, getState } = setup();
        bus.dispatch('flows/chat/failed', { task_id: 'tsk1', error: 'bad' });
        const s = getState().flowsChat;
        expect(s.streaming).toBe(false);
        const assistant = s.messagesByContextId.ctx1.messages.find((m) => m.role === 'assistant');
        expect(assistant.error).toBe('bad');
    });

    it('failed до chat_send/succeeded с task_id: при context_id пишет assistant.error', () => {
        const { bus, getState } = build();
        bus.dispatch('flows/chat/session_init', { flowId: 'demo', contextId: 'ctx1' });
        bus.dispatch('flows/chat/user_message_added', {
            contextId: 'ctx1',
            message: { id: 'u1', role: 'user', content: 'hi' },
        });
        expect(getState().flowsChat.messagesByContextId.ctx1.taskId).toBeNull();
        bus.dispatch('flows/chat/failed', {
            task_id: 'tsk1',
            context_id: 'ctx1',
            error: '403 Forbidden',
        });
        const s = getState().flowsChat;
        expect(s.streaming).toBe(false);
        const assistant = s.messagesByContextId.ctx1.messages.find((m) => m.role === 'assistant');
        expect(assistant).toBeDefined();
        expect(assistant.error).toBe('403 Forbidden');
        expect(s.messagesByContextId.ctx1.taskId).toBe('tsk1');
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

    it('resume после input_required с тем же task_id пишет ответ в новый bubble', () => {
        const { bus, getState } = setup();
        bus.dispatch('flows/chat/input_required', {
            task_id: 'tsk1',
            context_id: 'ctx1',
            result_metadata: { platform_interrupt: { question: 'Name?' } },
        });
        bus.dispatch('flows/chat/user_message_added', {
            contextId: 'ctx1',
            message: { id: 'u2', role: 'user', content: 'John' },
        });
        bus.dispatch('flows/chat/task_started', { task_id: 'tsk1', context_id: 'ctx1' });
        bus.dispatch('flows/chat/content_chunk', { task_id: 'tsk1', text: 'Hello John' });
        bus.dispatch('flows/chat/completed', { task_id: 'tsk1', context_id: 'ctx1', content: 'Hello John' });

        const msgs = getState().flowsChat.messagesByContextId.ctx1.messages;
        const assistants = msgs.filter((m) => m && m.role === 'assistant' && m.taskId === 'tsk1');
        expect(assistants.length).toBe(2);
        expect(assistants[0].inputRequired).toBeTruthy();
        expect(assistants[0].content).toBe('');
        expect(assistants[1].inputRequired).toBeNull();
        expect(assistants[1].content).toBe('Hello John');
        expect(assistants[1].id).not.toBe(assistants[0].id);
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

    it('voice relay использует тот же A2A runtime mapper', () => {
        const { bus, getState } = build();
        bus.dispatch('flows/chat/session_init', { flowId: 'demo', contextId: 'ctx_voice' });
        const streamState = { contextId: 'ctx_voice', taskId: null, taskPrimed: false };

        relayA2aVoiceStreamRpcFrame(
            { dispatch: bus.dispatch.bind(bus) },
            streamState,
            {
                jsonrpc: '2.0',
                id: 'voice-1',
                result: {
                    kind: 'artifact-update',
                    taskId: 'voice_t1',
                    contextId: 'ctx_voice',
                    artifact: {
                        parts: [{ kind: 'text', text: 'voice answer' }],
                    },
                    final: false,
                },
            },
            'voice-cause',
        );

        expect(streamState.taskPrimed).toBe(true);
        expect(streamState.taskId).toBe('voice_t1');
        const msgs = getState().flowsChat.messagesByContextId.ctx_voice.messages;
        const assistant = msgs.find((m) => m.role === 'assistant' && m.taskId === 'voice_t1');
        expect(assistant.content).toBe('voice answer');
    });
});

describe('flows/chat extraReducer: run trace', () => {
    function buildFresh() {
        const built = build();
        built.bus.dispatch('flows/chat/session_init', { flowId: 'demo', contextId: 'ctx1' });
        return built;
    }

    it('trace_append добавляет запись в runTraceByContextId', () => {
        const { bus, getState } = buildFresh();
        bus.dispatch('flows/chat/trace_append', {
            context_id: 'ctx1',
            entry: { id: 'e1', kind: 'node_start', ts: 10_000, node_id: 'n1', node_type: 'code' },
        });
        const rows = getState().flowsChat.runTraceByContextId.ctx1;
        expect(rows.length).toBe(1);
        expect(rows[0].kind).toBe('node_start');
        expect(rows[0].node_id).toBe('n1');
    });

    it('task_started очищает ленту для контекста', () => {
        const { bus, getState } = buildFresh();
        bus.dispatch('flows/chat/trace_append', {
            context_id: 'ctx1',
            entry: { id: 'e1', kind: 'tool_call', ts: 10_000, tool: 'x', tool_call_id: 'c1' },
        });
        expect(getState().flowsChat.runTraceByContextId.ctx1.length).toBe(1);
        bus.dispatch('flows/chat/task_started', { task_id: 'tsk_new', context_id: 'ctx1' });
        expect(getState().flowsChat.runTraceByContextId.ctx1).toEqual([]);
    });
});

describe('flows/chat extraReducer: handoff', () => {
    function setupHandoff() {
        const built = build();
        built.bus.dispatch('flows/chat/session_init', { flowId: 'parent', contextId: 'ctx1' });
        built.bus.dispatch('flows/chat/task_started', { task_id: 'tsk1', context_id: 'ctx1' });
        built.bus.dispatch('flows/chat/input_required', {
            task_id: 'tsk1',
            context_id: 'ctx1',
            result_metadata: { platform_interrupt: { body: { kind: 'handoff' } } },
        });
        return built;
    }

    it('handoff_initiated добавляет handoff card и обновляет assistant', () => {
        const { bus, getState } = setupHandoff();
        bus.dispatch('flows/chat/handoff_initiated', {
            task_id: 'tsk1',
            context_id: 'ctx1',
            target_flow_id: 'child_flow',
            target_flow_name: 'Child Agent',
            handoff_reason: 'need specialist',
            handoff_depth: 1,
        });
        const msgs = getState().flowsChat.messagesByContextId.ctx1.messages;
        const assistant = msgs.find((m) => m.role === 'assistant' && m.taskId === 'tsk1');
        expect(assistant.handoff).toBeTruthy();
        expect(assistant.handoff.targetFlowId).toBe('child_flow');
        expect(assistant.handoff.status).toBe('active');
        const handoffMsg = msgs.find((m) => m.role === 'handoff');
        expect(handoffMsg).toBeTruthy();
        expect(handoffMsg.targetFlowName).toBe('Child Agent');
    });

    it('handback_completed помечает handoff returned и добавляет handback card', () => {
        const { bus, getState } = setupHandoff();
        bus.dispatch('flows/chat/handoff_initiated', {
            task_id: 'tsk1',
            context_id: 'ctx1',
            target_flow_id: 'child_flow',
            target_flow_name: 'Child Agent',
            handoff_depth: 1,
        });
        bus.dispatch('flows/chat/handback_completed', {
            task_id: 'tsk1',
            context_id: 'ctx1',
            response: 'resolved by child',
            parent_flow_name: 'Parent Agent',
            handoff_depth: 0,
        });
        const msgs = getState().flowsChat.messagesByContextId.ctx1.messages;
        const assistant = msgs.find((m) => m.role === 'assistant' && m.taskId === 'tsk1');
        expect(assistant.handoff.status).toBe('returned');
        const handbackMsg = msgs.find((m) => m.role === 'handback');
        expect(handbackMsg).toBeTruthy();
        expect(handbackMsg.response).toBe('resolved by child');
    });
});
