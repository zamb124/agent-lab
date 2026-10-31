import { describe, expect, it } from 'vitest';
import {
    nodeConfigToToolRef,
    replaceToolRefInToolsList,
    toolRefToInitialNode,
} from '../../../../apps/flows/ui/_helpers/flows-tool-ref.js';

describe('flows tool ref helpers', () => {
    it('maps MCP ToolReference fields to MCP node editor fields', () => {
        const node = toolRefToInitialNode(
            {
                tool_id: 'mcp:browser:browser_create_session',
                type: 'mcp',
                code_mode: 'mcp_tool',
                mcp_server_id: 'browser',
                mcp_tool_name: 'browser_create_session',
            },
            'mcp:browser:browser_create_session',
        );

        expect(node.server_id).toBe('browser');
        expect(node.tool_name).toBe('browser_create_session');
    });

    it('infers MCP node fields from mcp-prefixed tool_id', () => {
        const node = toolRefToInitialNode(
            { tool_id: 'mcp:browser:browser_create_session' },
            'mcp:browser:browser_create_session',
        );

        expect(node.type).toBe('mcp');
        expect(node.server_id).toBe('browser');
        expect(node.tool_name).toBe('browser_create_session');
    });

    it('saves MCP node editor fields back as ToolReference MCP fields', () => {
        const ref = nodeConfigToToolRef({
            node_id: 'mcp:browser:browser_create_session',
            type: 'mcp',
            server_id: 'browser',
            tool_name: 'browser_create_session',
            headers: {},
            input_mapping: { query: 'hello' },
            state_mapping: { result: 'out' },
        });

        expect(ref).toMatchObject({
            tool_id: 'mcp:browser:browser_create_session',
            code_mode: 'mcp_tool',
            mcp_server_id: 'browser',
            mcp_tool_name: 'browser_create_session',
            input_mapping: { query: 'hello' },
            state_mapping: { result: 'out' },
        });
        expect(ref.type).toBeUndefined();
        expect(ref.server_id).toBeUndefined();
        expect(ref.tool_name).toBeUndefined();
        expect(ref.headers).toBeUndefined();
    });

    it('round-trips code tool input_mapping through nodeConfigToToolRef without type', () => {
        const node = {
            node_id: 'ask_user',
            type: 'code',
            name: 'ask_user',
            code: 'async def ask_user(args, state):\n    return args\n',
            language: 'python',
            parameters_schema: {
                type: 'object',
                properties: { question: { type: 'string' } },
                required: ['question'],
            },
            input_mapping: { question: 'как дела?' },
        };
        const ref = nodeConfigToToolRef(node);
        expect(ref.tool_id).toBe('ask_user');
        expect(ref.input_mapping).toEqual({ question: 'как дела?' });
        expect(ref.code).toContain('ask_user');
        expect(ref.type).toBeUndefined();
    });

    it('round-trips flow call_type without moving it to the parent LLM node', () => {
        const raw = {
            tool_id: 'coach',
            type: 'flow',
            flow_id: 'coach',
            branch_id: 'vip',
            call_type: 'handoff',
            name: 'Coach',
            description: 'Delegated specialist',
            parameters_schema: {
                type: 'object',
                properties: { request: { type: 'string' } },
                required: ['request'],
                additionalProperties: false,
            },
        };

        const node = toolRefToInitialNode(raw, 'coach');
        const ref = nodeConfigToToolRef(node);

        expect(node.call_type).toBe('handoff');
        expect(ref).toEqual(raw);
    });

    it('maps code ToolReference to GraphNodeConfig-shaped editor node', () => {
        const node = toolRefToInitialNode(
            {
                tool_id: 'ask_user',
                title: 'ask_user',
                description: 'Asks the user a question',
                code: '# platform:tool-capability:ask_user\nasync def ask_user(args, state):\n    return await tools.call("ask_user", **dict(args))\n',
                language: 'python',
                tags: ['misc'],
                params: {},
                code_mode: 'inline_code',
                permission: [],
                react_role: 'standard',
                parameters_schema: {
                    type: 'object',
                    properties: { question: { type: 'string' } },
                    required: ['question'],
                },
                input_mapping: { question: 'hello' },
            },
            'ask_user',
        );

        expect(node).toMatchObject({
            node_id: 'ask_user',
            type: 'code',
            name: 'ask_user',
            description: 'Asks the user a question',
            language: 'python',
            input_mapping: { question: 'hello' },
        });
        expect(typeof node.code).toBe('string');
        expect(String(node.code).length).toBeGreaterThan(0);
        expect(node.tags).toBeUndefined();
        expect(node.title).toBeUndefined();
        expect(node.params).toBeUndefined();
        expect(node.code_mode).toBeUndefined();
        expect(node.permission).toBeUndefined();
        expect(node.react_role).toBeUndefined();
    });

    it('replaceToolRefInToolsList replaces string tool id with full ref', () => {
        const updated = {
            tool_id: 'ask_user',
            code: 'async def ask_user(args, state):\n    return args\n',
            input_mapping: { question: 'как дела?' },
        };
        const next = replaceToolRefInToolsList(['ask_user', 'other'], updated);
        expect(next).toEqual([updated, 'other']);
    });

    it('replaceToolRefInToolsList replaces object tool ref and keeps mapping', () => {
        const updated = {
            tool_id: 'ask_user',
            input_mapping: { question: 'ping' },
        };
        const next = replaceToolRefInToolsList(
            [{ tool_id: 'ask_user', code: 'x = 1' }, { tool_id: 'x' }],
            updated,
        );
        expect(next[0]).toEqual(updated);
        expect(next[1]).toEqual({ tool_id: 'x' });
    });
});
