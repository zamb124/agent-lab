/**
 * Нормализация A2A 1.0 messages при восстановлении сессии (ProtoJSON ROLE_* / Part.url).
 */

import { describe, it, expect } from 'vitest';
import { a2aStateMessagesToChatMessages } from '../../../../apps/flows/ui/_helpers/chat-session-messages.js';

describe('a2aStateMessagesToChatMessages', () => {
    it('ROLE_USER / ROLE_AGENT + tool_calls merge (ProtoJSON wire)', () => {
        const raw = [
            {
                messageId: 'u1',
                role: 'ROLE_USER',
                parts: [{ text: 'привет' }],
                taskId: 't1',
            },
            {
                messageId: 'a1',
                role: 'ROLE_AGENT',
                taskId: 't1',
                metadata: {
                    node_id: 'n1',
                    author: {
                        kind: 'subagent',
                        flow_id: 'weather_agent',
                        node_id: 'n1',
                    },
                    tool_calls: [
                        { id: 'c1', name: 'get_weather', arguments: { city: 'Moscow' } },
                    ],
                },
                parts: [{ text: 'Смотрю погоду…' }],
            },
            {
                messageId: 'r1',
                role: 'ROLE_AGENT',
                taskId: 't1',
                metadata: { tool_call_id: 'c1', node_id: 'n1' },
                parts: [{ text: '{"temp":1}' }],
            },
            {
                messageId: 'a2',
                role: 'ROLE_AGENT',
                taskId: 't1',
                metadata: { node_id: 'n1' },
                parts: [{ text: 'Итог: ясно.' }],
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
        expect(asst.author).toEqual({
            kind: 'subagent',
            name: '',
            flowId: 'weather_agent',
            nodeId: 'n1',
        });
    });

    it('short role aliases user/agent still hydrate (legacy fixtures)', () => {
        const raw = [
            {
                messageId: 'u1',
                role: 'user',
                parts: [{ text: 'hi' }],
                taskId: 't1',
            },
            {
                messageId: 'a1',
                role: 'agent',
                taskId: 't1',
                parts: [{ text: 'ok' }],
            },
        ];
        const out = a2aStateMessagesToChatMessages(raw, 't1');
        expect(out).toHaveLength(2);
        expect(out[0].role).toBe('user');
        expect(out[1].role).toBe('assistant');
        expect(out[1].content).toBe('ok');
    });

    it('Part.url → files on user message', () => {
        const raw = [
            {
                messageId: 'u1',
                role: 'ROLE_USER',
                taskId: 't1',
                parts: [
                    { text: 'см файл' },
                    {
                        url: '/frontend/api/v1/files/download/file_xyz',
                        filename: 'doc.pdf',
                        mediaType: 'application/pdf',
                    },
                ],
            },
        ];
        const out = a2aStateMessagesToChatMessages(raw, 't1');
        expect(out).toHaveLength(1);
        expect(out[0].role).toBe('user');
        expect(out[0].files).toEqual([
            {
                file_id: 'file_xyz',
                original_name: 'doc.pdf',
                url: '/frontend/api/v1/files/download/file_xyz',
                content_type: 'application/pdf',
                file_size: 0,
            },
        ]);
    });

    it('HITL ROLE_AGENT с hitl_role=operator и hitl_file_ids → operator bubble + fileIds', () => {
        const raw = [
            {
                messageId: 'hitl-op-close:complete:wi1',
                role: 'ROLE_AGENT',
                taskId: 't1',
                metadata: {
                    node_id: 'hitl_conversation',
                    hitl_role: 'operator',
                    hitl_file_ids: ['file_abc'],
                    operator_user_id: 'user_1',
                },
                parts: [{ text: 'вот держи' }],
            },
        ];
        const out = a2aStateMessagesToChatMessages(raw, 't1');
        expect(out).toHaveLength(1);
        expect(out[0].role).toBe('operator');
        expect(out[0].author.kind).toBe('operator');
        expect(out[0].content).toBe('вот держи');
        expect(out[0].fileIds).toEqual(['file_abc']);
    });

    it('unknown role → throw', () => {
        expect(() =>
            a2aStateMessagesToChatMessages(
                [{ messageId: 'x', role: 'ROLE_UNKNOWN', parts: [{ text: 'x' }] }],
                't1',
            ),
        ).toThrow(/unknown message.role/);
    });
});

describe('OpenAI-формат tool_calls в A2A', () => {
    it('нормализуется в { id, name, args }', () => {
        const raw = [
            {
                messageId: 'a1',
                role: 'ROLE_AGENT',
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
                parts: [{ text: 'ok' }],
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
