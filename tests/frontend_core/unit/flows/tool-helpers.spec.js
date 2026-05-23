import { describe, it, expect } from 'vitest';
import {
    pairFlowChatToolCallsAndResults,
    flowChatToolRowDisplayName,
    flowChatToolRowId,
    formatFlowChatToolPairHintText,
    toolCallIconName,
} from '../../../../core/frontend/static/lib/flows-chat/tool-helpers.js';

describe('flows-chat tool helpers', () => {
    it('pairs tool calls and results by id, name, then index for every chat host', () => {
        const calls = [
            { id: 'call-1', name: 'search_docs', arguments: { q: 'x' } },
            { id: 'call-2', name: 'write_file' },
            { name: 'calendar_lookup' },
        ];
        const results = [
            { tool_call_id: 'call-1', result: 'found' },
            { tool: 'calendar_lookup', output: { ok: true } },
            { value: 'fallback-index' },
        ];

        const paired = pairFlowChatToolCallsAndResults(calls, results);

        expect(paired).toEqual([
            { call: calls[0], result: results[0] },
            { call: calls[1], result: results[2] },
            { call: calls[2], result: results[1] },
        ]);
    });

    it('formats shared tool hints and row metadata', () => {
        const call = { id: 'c1', name: 'read_file', args: { path: '/tmp/a.txt' } };
        const result = { tool_call_id: 'c1', data: { bytes: 12 } };
        const strings = {
            tool_hint_tool_name: (name) => `Tool: ${name}`,
            tool_hint_args_label: 'Arguments:',
            tool_hint_result_label: 'Result:',
        };

        expect(flowChatToolRowDisplayName(call, result, 'tool')).toBe('read_file');
        expect(flowChatToolRowId(call, result)).toBe('c1');
        expect(toolCallIconName('read_file')).toBe('file');
        expect(formatFlowChatToolPairHintText(call, result, strings, 'tool')).toContain('"bytes": 12');
        expect(
            formatFlowChatToolPairHintText(call, result, { ...strings, tool_hint_tool_name: 'Tool: {name}' }, 'tool'),
        ).toContain('Tool: read_file');
    });
});
