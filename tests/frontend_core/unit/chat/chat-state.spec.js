/**
 * Pure reducer единого чат-компонента (`core/lib/chat/runtime/chat-state.js`).
 *
 * Проверяет, что verbs runtime-событий корректно обновляют
 * messagesByContextId / runTraceByContextId / streaming.
 */

import { describe, it, expect } from 'vitest';
import {
    applyChatRuntimeEvent,
    createInitialChatRuntimeState,
} from '../../../../core/frontend/static/lib/chat/runtime/chat-state.js';

function reduce(...steps) {
    let state = createInitialChatRuntimeState();
    for (const [verb, payload] of steps) {
        state = applyChatRuntimeEvent(state, verb, payload);
    }
    return state;
}

describe('chat-state: session lifecycle', () => {
    it('session_init создаёт пустой контекст', () => {
        const s = reduce(['session_init', { flowId: 'demo', contextId: 'ctx1' }]);
        expect(s.currentContextId).toBe('ctx1');
        expect(s.messagesByContextId.ctx1.messages).toEqual([]);
        expect(s.runTraceByContextId.ctx1).toEqual([]);
        expect(s.streaming).toBe(false);
    });

    it('user_message_added добавляет сообщение в текущий контекст', () => {
        const s = reduce(
            ['session_init', { flowId: 'demo', contextId: 'ctx1' }],
            ['user_message_added', { contextId: 'ctx1', message: { id: 'u1', role: 'user', content: 'hello' } }],
        );
        expect(s.messagesByContextId.ctx1.messages.length).toBe(1);
        expect(s.messagesByContextId.ctx1.messages[0].content).toBe('hello');
    });

    it('send_succeeded после полного стрима привязывает task_id, streaming false', () => {
        const s = reduce(
            ['session_init', { flowId: 'demo', contextId: 'ctx1' }],
            ['send_succeeded', { task_id: 'tsk1', context_id: 'ctx1' }],
        );
        expect(s.currentTaskId).toBe('tsk1');
        expect(s.streaming).toBe(false);
        expect(s.messagesByContextId.ctx1.taskId).toBe('tsk1');
    });
});

describe('chat-state: task_started placeholder', () => {
    it('task_started создаёт плейсхолдер ассистента со streaming', () => {
        const s = reduce(
            ['session_init', { flowId: 'demo', contextId: 'ctx1' }],
            ['user_message_added', { contextId: 'ctx1', message: { id: 'u1', role: 'user', content: 'hello' } }],
            ['task_started', { task_id: 'tsk1', context_id: 'ctx1' }],
        );
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
        const s = reduce(
            ['session_init', { flowId: 'demo', contextId: 'ctx1' }],
            ['user_message_added', { contextId: 'ctx1', message: { id: 'u1', role: 'user', content: 'hello' } }],
            ['task_started', { task_id: 'tsk1', context_id: 'ctx1' }],
            ['reasoning_chunk', { task_id: 'tsk1', text: 'a' }],
        );
        const assistants = s.messagesByContextId.ctx1.messages.filter(
            (m) => m && m.role === 'assistant' && m.taskId === 'tsk1',
        );
        expect(assistants.length).toBe(1);
        expect(assistants[0].reasoning).toBe('a');
    });

    it('activity обновляет поле ассистента', () => {
        const s = reduce(
            ['session_init', { flowId: 'demo', contextId: 'ctx1' }],
            ['task_started', { task_id: 'tsk1', context_id: 'ctx1' }],
            ['activity', { task_id: 'tsk1', text: 'Status line' }],
        );
        const assistant = s.messagesByContextId.ctx1.messages.find(
            (m) => m.role === 'assistant' && m.taskId === 'tsk1',
        );
        expect(assistant.activity).toBe('Status line');
    });

    it('reasoning_chunk без task_started и со streaming false не пишет в messages', () => {
        const s = reduce(
            ['session_init', { flowId: 'demo', contextId: 'ctx1' }],
            ['user_message_added', { contextId: 'ctx1', message: { id: 'u1', role: 'user', content: 'hi' } }],
            ['reasoning_chunk', { task_id: 'tsk1', text: 'x' }],
        );
        const msgs = s.messagesByContextId.ctx1.messages;
        expect(msgs.find((m) => m && m.role === 'assistant')).toBeUndefined();
    });
});

describe('chat-state: streaming события', () => {
    const base = [
        ['session_init', { flowId: 'demo', contextId: 'ctx1' }],
        ['send_succeeded', { task_id: 'tsk1', context_id: 'ctx1' }],
    ];

    it('content_chunk накапливает текст ассистента', () => {
        const s = reduce(
            ...base,
            ['content_chunk', { task_id: 'tsk1', text: 'Hello ' }],
            ['content_chunk', { task_id: 'tsk1', text: 'world' }],
        );
        const assistant = s.messagesByContextId.ctx1.messages.find((m) => m.role === 'assistant');
        expect(assistant).toBeDefined();
        expect(assistant.content).toBe('Hello world');
    });

    it('reasoning_chunk накапливает текст в reasoning', () => {
        const s = reduce(...base, ['reasoning_chunk', { task_id: 'tsk1', text: 'thinking…' }]);
        const assistant = s.messagesByContextId.ctx1.messages.find((m) => m.role === 'assistant');
        expect(assistant.reasoning).toBe('thinking…');
    });

    it('tool_calls добавляются без дублей', () => {
        const s = reduce(
            ...base,
            ['tool_calls', { task_id: 'tsk1', tool_calls: [{ id: 'tc1', name: 'foo' }] }],
            ['tool_calls', { task_id: 'tsk1', tool_calls: [{ id: 'tc1', name: 'foo' }, { id: 'tc2', name: 'bar' }] }],
        );
        const assistant = s.messagesByContextId.ctx1.messages.find((m) => m.role === 'assistant');
        expect(assistant.toolCalls.length).toBe(2);
    });

    it('tool_result добавляется один раз', () => {
        const s = reduce(
            ...base,
            ['tool_result', { task_id: 'tsk1', tool_result: { id: 'tr1', value: 42 } }],
            ['tool_result', { task_id: 'tsk1', tool_result: { id: 'tr1', value: 42 } }],
        );
        const assistant = s.messagesByContextId.ctx1.messages.find((m) => m.role === 'assistant');
        expect(assistant.toolResults.length).toBe(1);
    });

    it('completed снимает streaming и закрывает task', () => {
        const s = reduce(
            ...base,
            ['content_chunk', { task_id: 'tsk1', text: 'done' }],
            ['completed', { task_id: 'tsk1', content: 'done' }],
        );
        expect(s.streaming).toBe(false);
        const assistant = s.messagesByContextId.ctx1.messages.find((m) => m.role === 'assistant');
        expect(assistant.streaming).toBe(false);
        expect(typeof assistant.timestamp).toBe('string');
        expect(assistant.timestamp.length).toBeGreaterThan(0);
    });

    it('повторный completed для того же task_id не создаёт второго ассистента', () => {
        const s = reduce(
            ...base,
            ['content_chunk', { task_id: 'tsk1', text: 'done' }],
            ['completed', { task_id: 'tsk1', content: 'done' }],
            ['completed', { task_id: 'tsk1', content: 'done' }],
        );
        const assistants = s.messagesByContextId.ctx1.messages.filter(
            (m) => m && m.role === 'assistant' && m.taskId === 'tsk1',
        );
        expect(assistants.length).toBe(1);
        expect(assistants[0].content).toBe('done');
    });

    it('failed выставляет error и снимает streaming', () => {
        const s = reduce(...base, ['failed', { task_id: 'tsk1', error: 'bad' }]);
        expect(s.streaming).toBe(false);
        const assistant = s.messagesByContextId.ctx1.messages.find((m) => m.role === 'assistant');
        expect(assistant.error).toBe('bad');
    });

    it('failed до send_succeeded с task_id: при context_id пишет assistant.error', () => {
        const s = reduce(
            ['session_init', { flowId: 'demo', contextId: 'ctx1' }],
            ['user_message_added', { contextId: 'ctx1', message: { id: 'u1', role: 'user', content: 'hi' } }],
            ['failed', { task_id: 'tsk1', context_id: 'ctx1', error: '403 Forbidden' }],
        );
        expect(s.streaming).toBe(false);
        const assistant = s.messagesByContextId.ctx1.messages.find((m) => m.role === 'assistant');
        expect(assistant).toBeDefined();
        expect(assistant.error).toBe('403 Forbidden');
        expect(s.messagesByContextId.ctx1.taskId).toBe('tsk1');
    });

    it('breakpoint снимает streaming и сохраняет breakpoint', () => {
        const s = reduce(
            ...base,
            ['breakpoint', { task_id: 'tsk1', breakpoint: { node_id: 'n1', state: { foo: 1 } } }],
        );
        expect(s.streaming).toBe(false);
        const assistant = s.messagesByContextId.ctx1.messages.find((m) => m.role === 'assistant');
        expect(assistant.breakpoint.node_id).toBe('n1');
    });

    it('input_required выставляет inputRequired', () => {
        const s = reduce(
            ...base,
            ['input_required', {
                task_id: 'tsk1',
                result_metadata: { handoff: true },
                message_metadata: { hint: 'fill form' },
            }],
        );
        const assistant = s.messagesByContextId.ctx1.messages.find((m) => m.role === 'assistant');
        expect(assistant.inputRequired).toBeTruthy();
        expect(assistant.inputRequired.resultMetadata.handoff).toBe(true);
    });

    it('resume после input_required с тем же task_id пишет ответ в новый bubble', () => {
        const s = reduce(
            ...base,
            ['input_required', {
                task_id: 'tsk1',
                context_id: 'ctx1',
                result_metadata: { platform_interrupt: { question: 'Name?' } },
            }],
            ['user_message_added', { contextId: 'ctx1', message: { id: 'u2', role: 'user', content: 'John' } }],
            ['task_started', { task_id: 'tsk1', context_id: 'ctx1' }],
            ['content_chunk', { task_id: 'tsk1', text: 'Hello John' }],
            ['completed', { task_id: 'tsk1', context_id: 'ctx1', content: 'Hello John' }],
        );
        const assistants = s.messagesByContextId.ctx1.messages.filter(
            (m) => m && m.role === 'assistant' && m.taskId === 'tsk1',
        );
        expect(assistants.length).toBe(2);
        expect(assistants[0].inputRequired).toBeTruthy();
        expect(assistants[0].content).toBe('');
        expect(assistants[1].inputRequired).toBeNull();
        expect(assistants[1].content).toBe('Hello John');
        expect(assistants[1].id).not.toBe(assistants[0].id);
    });

    it('HITL live: content_chunk без task_started после input_required — новый bubble, без concat', () => {
        const s = reduce(
            ...base,
            ['content_chunk', { task_id: 'tsk1', text: 'Mock LLM ответ' }],
            ['input_required', {
                task_id: 'tsk1',
                context_id: 'ctx1',
                result_metadata: { platform_interrupt: { question: 'operator?' } },
            }],
            ['content_chunk', { task_id: 'tsk1', text: 'Mock LLM ответ' }],
        );
        const assistants = s.messagesByContextId.ctx1.messages.filter(
            (m) => m && m.role === 'assistant' && m.taskId === 'tsk1',
        );
        expect(assistants.length).toBe(2);
        expect(assistants[0].content).toBe('Mock LLM ответ');
        expect(assistants[1].content).toBe('Mock LLM ответ');
        expect(assistants.every((m) => m.content !== 'Mock LLM ответMock LLM ответ')).toBe(true);
    });

    it('operator_reply добавляет отдельное сообщение operator', () => {
        const s = reduce(...base, ['operator_reply', { task_id: 'tsk1', text: 'hi from op' }]);
        const op = s.messagesByContextId.ctx1.messages.find((m) => m.role === 'operator');
        expect(op).toBeDefined();
        expect(op.content).toBe('hi from op');
    });

    it('operator_files прикрепляет к последнему operator-сообщению', () => {
        const s = reduce(
            ...base,
            ['operator_reply', { task_id: 'tsk1', text: 'see attached' }],
            ['operator_files', { task_id: 'tsk1', file_ids: ['f1', 'f2'] }],
        );
        const op = s.messagesByContextId.ctx1.messages.filter((m) => m.role === 'operator');
        expect(op.length).toBe(1);
        expect(op[0].fileIds).toEqual(['f1', 'f2']);
    });

    it('operator_files затем operator_reply затем completed — один пузырь с файлами', () => {
        const s = reduce(
            ...base,
            ['operator_files', { task_id: 'tsk1', file_ids: ['f1'] }],
            ['operator_reply', { task_id: 'tsk1', text: 'вот держи' }],
            ['completed', { task_id: 'tsk1', context_id: 'ctx1', content: 'вот держи' }],
        );
        const msgs = s.messagesByContextId.ctx1.messages.filter(
            (m) => m.role === 'operator' || m.role === 'assistant',
        );
        expect(msgs.length).toBe(1);
        expect(msgs[0].content).toBe('вот держи');
        expect(msgs[0].fileIds).toEqual(['f1']);
    });

    it('completed затем operator_reply затем operator_files — один пузырь', () => {
        const s = reduce(
            ...base,
            ['completed', { task_id: 'tsk1', context_id: 'ctx1', content: 'вот держи' }],
            ['operator_reply', { task_id: 'tsk1', text: 'вот держи' }],
            ['operator_files', { task_id: 'tsk1', file_ids: ['f1'] }],
        );
        const msgs = s.messagesByContextId.ctx1.messages.filter(
            (m) => m.role === 'operator' || m.role === 'assistant',
        );
        expect(msgs.length).toBe(1);
        expect(msgs[0].content).toBe('вот держи');
        expect(msgs[0].fileIds).toEqual(['f1']);
    });

    it('operator_reply затем operator_files затем completed — один пузырь', () => {
        const s = reduce(
            ...base,
            ['operator_reply', { task_id: 'tsk1', text: 'вот держи' }],
            ['operator_files', { task_id: 'tsk1', file_ids: ['f1'] }],
            ['completed', { task_id: 'tsk1', context_id: 'ctx1', content: 'вот держи' }],
        );
        const msgs = s.messagesByContextId.ctx1.messages.filter(
            (m) => m.role === 'operator' || m.role === 'assistant',
        );
        expect(msgs.length).toBe(1);
        expect(msgs[0].role).toBe('operator');
        expect(msgs[0].content).toBe('вот держи');
        expect(msgs[0].fileIds).toEqual(['f1']);
    });

    it('operator_reply затем completed с тем же текстом — один пузырь', () => {
        const s = reduce(
            ...base,
            ['operator_reply', { task_id: 'tsk1', text: 'кака' }],
            ['completed', { task_id: 'tsk1', context_id: 'ctx1', content: 'кака' }],
        );
        const msgs = s.messagesByContextId.ctx1.messages.filter(
            (m) => m.role === 'operator' || m.role === 'assistant',
        );
        expect(msgs.length).toBe(1);
        expect(msgs[0].role).toBe('operator');
        expect(msgs[0].content).toBe('кака');
        expect(s.streaming).toBe(false);
    });

    it('completed затем operator_reply с тем же текстом — один пузырь', () => {
        const s = reduce(
            ...base,
            ['completed', { task_id: 'tsk1', context_id: 'ctx1', content: 'кака' }],
            ['operator_reply', { task_id: 'tsk1', text: 'кака' }],
        );
        const msgs = s.messagesByContextId.ctx1.messages.filter(
            (m) => m.role === 'operator' || m.role === 'assistant',
        );
        expect(msgs.length).toBe(1);
        expect(msgs[0].content).toBe('кака');
    });
});

describe('chat-state: run trace', () => {
    it('trace_append добавляет запись в runTraceByContextId', () => {
        const s = reduce(
            ['session_init', { flowId: 'demo', contextId: 'ctx1' }],
            ['trace_append', {
                context_id: 'ctx1',
                entry: { id: 'e1', kind: 'node_start', ts: 10_000, node_id: 'n1', node_type: 'code' },
            }],
        );
        const rows = s.runTraceByContextId.ctx1;
        expect(rows.length).toBe(1);
        expect(rows[0].kind).toBe('node_start');
        expect(rows[0].node_id).toBe('n1');
    });

    it('task_started очищает ленту для контекста', () => {
        const afterTrace = reduce(
            ['session_init', { flowId: 'demo', contextId: 'ctx1' }],
            ['trace_append', {
                context_id: 'ctx1',
                entry: { id: 'e1', kind: 'tool_call', ts: 10_000, tool: 'x', tool_call_id: 'c1' },
            }],
        );
        expect(afterTrace.runTraceByContextId.ctx1.length).toBe(1);
        const s = applyChatRuntimeEvent(afterTrace, 'task_started', { task_id: 'tsk_new', context_id: 'ctx1' });
        expect(s.runTraceByContextId.ctx1).toEqual([]);
    });
});

describe('chat-state: handoff', () => {
    const handoffBase = [
        ['session_init', { flowId: 'parent', contextId: 'ctx1' }],
        ['task_started', { task_id: 'tsk1', context_id: 'ctx1' }],
        ['input_required', {
            task_id: 'tsk1',
            context_id: 'ctx1',
            result_metadata: { platform_interrupt: { body: { kind: 'handoff' } } },
        }],
    ];

    it('handoff_initiated добавляет handoff card и обновляет assistant', () => {
        const s = reduce(
            ...handoffBase,
            ['handoff_initiated', {
                task_id: 'tsk1',
                context_id: 'ctx1',
                target_flow_id: 'child_flow',
                target_flow_name: 'Child Agent',
                handoff_reason: 'need specialist',
                handoff_depth: 1,
            }],
        );
        const msgs = s.messagesByContextId.ctx1.messages;
        const assistant = msgs.find((m) => m.role === 'assistant' && m.taskId === 'tsk1');
        expect(assistant.handoff).toBeTruthy();
        expect(assistant.handoff.targetFlowId).toBe('child_flow');
        expect(assistant.handoff.status).toBe('active');
        const handoffMsg = msgs.find((m) => m.role === 'handoff');
        expect(handoffMsg).toBeTruthy();
        expect(handoffMsg.targetFlowName).toBe('Child Agent');
    });

    it('handback_completed помечает handoff returned и добавляет handback card', () => {
        const s = reduce(
            ...handoffBase,
            ['handoff_initiated', {
                task_id: 'tsk1',
                context_id: 'ctx1',
                target_flow_id: 'child_flow',
                target_flow_name: 'Child Agent',
                handoff_depth: 1,
            }],
            ['handback_completed', {
                task_id: 'tsk1',
                context_id: 'ctx1',
                response: 'resolved by child',
                parent_flow_name: 'Parent Agent',
                handoff_depth: 0,
            }],
        );
        const msgs = s.messagesByContextId.ctx1.messages;
        const assistant = msgs.find((m) => m.role === 'assistant' && m.taskId === 'tsk1');
        expect(assistant.handoff.status).toBe('returned');
        const handbackMsg = msgs.find((m) => m.role === 'handback');
        expect(handbackMsg).toBeTruthy();
        expect(handbackMsg.response).toBe('resolved by child');
    });
});
