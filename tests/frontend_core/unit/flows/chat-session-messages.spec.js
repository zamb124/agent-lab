/**
 * Нормализация A2A messages при восстановлении сессии.
 */

import { describe, it, expect } from 'vitest';
import { a2aStateMessagesToChatMessages } from '../../../../apps/flows/ui/_helpers/chat-session-messages.js';

describe('a2aStateMessagesToChatMessages', () => {
    it('user, assistant+tool_calls, tool result, финальный agent без tools — одна ветка с merge', () => {
        const raw = [
            {
                messageId: 'u1',
                role: 'user',
                parts: [{ kind: 'text', text: 'привет' }],
                taskId: 't1',
            },
            {
                messageId: 'a1',
                role: 'agent',
                taskId: 't1',
                metadata: {
                    node_id: 'n1',
                    tool_calls: [
                        { id: 'c1', name: 'get_weather', arguments: { city: 'Moscow' } },
                    ],
                },
                parts: [{ kind: 'text', text: 'Смотрю погоду…' }],
            },
            {
                messageId: 'r1',
                role: 'agent',
                taskId: 't1',
                metadata: { tool_call_id: 'c1', node_id: 'n1' },
                parts: [{ kind: 'text', text: '{"temp":1}' }],
            },
            {
                messageId: 'a2',
                role: 'agent',
                taskId: 't1',
                metadata: { node_id: 'n1' },
                parts: [{ kind: 'text', text: 'Итог: ясно.' }],
            },
        ];
        const out = a2aStateMessagesToChatMessages(raw, 't1');
        expect(out).toHaveLength(2);
        expect(out[0].role).toBe('user');
        expect(out[0].content).toBe('привет');
        const asst = out[1];
        expect(asst.role).toBe('assistant');
        expect(asst.toolCalls).toHaveLength(1);
        expect(asst.toolCalls[0].id).toBe('c1');
        expect(asst.toolCalls[0].name).toBe('get_weather');
        expect(asst.toolCalls[0].args).toEqual({ city: 'Moscow' });
        expect(asst.toolResults).toHaveLength(1);
        expect(asst.toolResults[0].id).toBe('c1');
        expect(asst.toolResults[0].result).toBe('{"temp":1}');
        expect(asst.content).toBe('Смотрю погоду…\n\nИтог: ясно.');
    });
});

describe('OpenAI-формат tool_calls в A2A', () => {
    it('нормализуется в { id, name, args }', () => {
        const raw = [
            {
                messageId: 'a1',
                role: 'agent',
                taskId: 't1',
                metadata: {
                    tool_calls: [
                        {
                            id: 'call_abc',
                            type: 'function',
                            function: { name: 'create_document', arguments: '{"title":"D"}' },
                        },
                    ],
                },
                parts: [{ kind: 'text', text: 'ok' }],
            },
        ];
        const out = a2aStateMessagesToChatMessages(raw, 't1');
        expect(out).toHaveLength(1);
        const tc0 = out[0].toolCalls[0];
        expect(tc0.id).toBe('call_abc');
        expect(tc0.name).toBe('create_document');
        expect(tc0.args).toEqual({ title: 'D' });
    });
});
