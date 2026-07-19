import { describe, it, expect } from 'vitest';
import {
    inputRequiredFieldsFromA2a,
    mapA2aResultToChatRuntimeEvents,
} from '../../../../core/frontend/static/lib/chat/a2a-chat-runtime.js';

describe('flows-chat A2A runtime', () => {
    it('maps artifact chunks to task_started, content, reasoning and terminal events', () => {
        const first = mapA2aResultToChatRuntimeEvents(
            {
                artifactUpdate: {
                    taskId: 't1',
                    contextId: 'ctx1',
                    artifact: {
                        name: 'reasoning',
                        metadata: {
                            author: {
                                kind: 'subagent',
                                flow_id: 'returns_agent',
                                node_id: 'answer',
                            },
                        },
                        parts: [{ text: 'thinking' }],
                    },
                },
            },
            { contextId: 'ctx1', currentTaskId: null, taskPrimed: false },
        );

        expect(first.taskPrimed).toBe(true);
        expect(first.nextTaskId).toBe('t1');
        expect(first.events.map((e) => e.type)).toEqual(['task_started', 'reasoning_chunk']);
        expect(first.events[0].payload.author).toEqual({
            kind: 'subagent',
            flow_id: 'returns_agent',
            node_id: 'answer',
        });
        expect(first.events[1].payload.author).toEqual(first.events[0].payload.author);

        const done = mapA2aResultToChatRuntimeEvents(
            {
                statusUpdate: {
                    taskId: 't1',
                    contextId: 'ctx1',
                    status: {
                        state: 'TASK_STATE_COMPLETED',
                        message: {
                            metadata: {
                                author: {
                                    kind: 'subagent',
                                    flow_id: 'returns_agent',
                                    node_id: 'answer',
                                },
                            },
                            parts: [{ text: 'final answer' }],
                        },
                    },
                },
            },
            { contextId: 'ctx1', currentTaskId: 't1', taskPrimed: first.taskPrimed },
        );

        expect(done.terminal).toBe(true);
        expect(done.events).toEqual([
            {
                type: 'completed',
                payload: {
                    task_id: 't1',
                    context_id: 'ctx1',
                    content: 'final answer',
                    author: {
                        kind: 'subagent',
                        flow_id: 'returns_agent',
                        node_id: 'answer',
                    },
                },
            },
        ]);
    });

    it('maps tool metadata and ui events without embed-specific state patches', () => {
        const mapped = mapA2aResultToChatRuntimeEvents(
            {
                artifactUpdate: {
                    taskId: 't2',
                    contextId: 'ctx2',
                    artifact: {
                        name: 'ui_event',
                        message: {
                            metadata: {
                                tool_calls: [{ id: 'c1', name: 'lookup' }],
                                tool_result: { id: 'c1', result: 'ok' },
                            },
                            parts: [],
                        },
                        parts: [
                            {
                                data: {
                                    id: 'ev1',
                                    type: 'files.created',
                                    payload: { file_id: 'f1' },
                                    timestamp: '2026-05-23T00:00:00Z',
                                },
                            },
                        ],
                    },
                },
            },
            { contextId: 'ctx2', currentTaskId: null, taskPrimed: false },
        );

        expect(mapped.events.map((e) => e.type)).toEqual([
            'task_started',
            'ui_event',
            'files_event',
            'tool_calls',
            'tool_result',
        ]);
        expect(mapped.events[1].payload.event.type).toBe('files.created');
        expect(mapped.events[2].payload.event.payload.file_id).toBe('f1');
    });

    it('normalizes input-required interrupt details for all chat hosts', () => {
        const details = inputRequiredFieldsFromA2a(
            { parts: [{ text: 'Authorize please' }] },
            {
                platform_interrupt: {
                    body: {
                        kind: 'oauth_required',
                        question: 'Connect account',
                        auth_url: 'https://auth.example',
                        provider: 'google',
                        service: 'drive',
                    },
                },
            },
        );

        expect(details).toEqual({
            question: 'Connect account',
            interruptKind: 'oauth_required',
            authUrl: 'https://auth.example',
            provider: 'google',
            service: 'drive',
        });
    });

    it('treats handoff input-required as the terminal stream boundary without final', () => {
        const mapped = mapA2aResultToChatRuntimeEvents(
            {
                statusUpdate: {
                    taskId: 'task-handoff',
                    contextId: 'ctx-handoff',
                    status: {
                        state: 'TASK_STATE_INPUT_REQUIRED',
                        message: {
                            metadata: {
                                platform_handoff_continue: true,
                                platform_interrupt: {
                                    body: {
                                        kind: 'handoff',
                                        target_flow_id: 'returns_agent',
                                        target_name: 'Returns Agent',
                                    },
                                },
                            },
                            parts: [{ text: 'Передаю управление' }],
                        },
                    },
                },
            },
            { contextId: 'ctx-handoff', currentTaskId: null, taskPrimed: false },
        );

        expect(mapped.terminal).toBe(true);
        expect(mapped.events.map((event) => event.type)).toEqual([
            'task_started',
            'input_required',
        ]);
    });

    it('keeps parent conversation context when handoff child emits child context_id', () => {
        const mapped = mapA2aResultToChatRuntimeEvents(
            {
                artifactUpdate: {
                    taskId: 'task-child-turn',
                    contextId: 'ctx-parent:handoff:returns_agent',
                    artifact: {
                        name: 'response',
                        parts: [{ text: 'Я Агент возвратов. Заказ GG-1042 найден.' }],
                    },
                },
            },
            { contextId: 'ctx-parent', currentTaskId: null, taskPrimed: false },
        );

        const started = mapped.events.find((event) => event.type === 'task_started');
        const chunk = mapped.events.find((event) => event.type === 'content_chunk');
        expect(started?.payload?.context_id).toBe('ctx-parent');
        expect(chunk?.payload?.context_id).toBe('ctx-parent');
        expect(chunk?.payload?.text).toContain('GG-1042');
    });
});
