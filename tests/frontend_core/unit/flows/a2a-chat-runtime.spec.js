import { describe, it, expect } from 'vitest';
import {
    inputRequiredFieldsFromA2a,
    mapA2aResultToChatRuntimeEvents,
} from '../../../../core/frontend/static/lib/flows-chat/a2a-chat-runtime.js';

describe('flows-chat A2A runtime', () => {
    it('maps artifact chunks to task_started, content, reasoning and terminal events', () => {
        const first = mapA2aResultToChatRuntimeEvents(
            {
                kind: 'artifact-update',
                taskId: 't1',
                contextId: 'ctx1',
                artifact: {
                    name: 'reasoning',
                    parts: [{ kind: 'text', text: 'thinking' }],
                },
                final: false,
            },
            { contextId: 'ctx1', currentTaskId: null, taskPrimed: false },
        );

        expect(first.taskPrimed).toBe(true);
        expect(first.nextTaskId).toBe('t1');
        expect(first.events.map((e) => e.type)).toEqual(['task_started', 'reasoning_chunk']);

        const done = mapA2aResultToChatRuntimeEvents(
            {
                kind: 'status-update',
                taskId: 't1',
                contextId: 'ctx1',
                status: {
                    state: 'completed',
                    message: {
                        parts: [{ kind: 'text', text: 'final answer' }],
                    },
                },
                final: true,
            },
            { contextId: 'ctx1', currentTaskId: 't1', taskPrimed: first.taskPrimed },
        );

        expect(done.terminal).toBe(true);
        expect(done.events).toEqual([
            {
                type: 'completed',
                payload: { task_id: 't1', context_id: 'ctx1', content: 'final answer' },
            },
        ]);
    });

    it('maps tool metadata and ui events without embed-specific state patches', () => {
        const mapped = mapA2aResultToChatRuntimeEvents(
            {
                kind: 'artifact-update',
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
                            kind: 'data',
                            data: {
                                id: 'ev1',
                                type: 'files.created',
                                payload: { file_id: 'f1' },
                                timestamp: '2026-05-23T00:00:00Z',
                            },
                        },
                    ],
                },
                final: false,
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
            { parts: [{ kind: 'text', text: 'Authorize please' }] },
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
});
