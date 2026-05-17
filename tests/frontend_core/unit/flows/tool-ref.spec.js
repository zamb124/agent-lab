import { describe, expect, it } from 'vitest';
import {
    nodeConfigToToolRef,
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
            input_mapping: {},
            state_mapping: {},
        });

        expect(ref).toMatchObject({
            tool_id: 'mcp:browser:browser_create_session',
            type: 'mcp',
            code_mode: 'mcp_tool',
            mcp_server_id: 'browser',
            mcp_tool_name: 'browser_create_session',
        });
        expect(ref.server_id).toBeUndefined();
        expect(ref.tool_name).toBeUndefined();
    });
});
