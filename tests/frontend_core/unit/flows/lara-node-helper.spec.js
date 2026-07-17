import { describe, expect, it } from 'vitest';
import {
    LARA_CODE_HELPER_BRANCH_ID,
    buildLaraFlowsContext,
    flattenLaraFlowsContext,
    laraNodeHelperBranchId,
    laraNodeHelperConversationKey,
} from '../../../../apps/flows/ui/_helpers/lara-node-helper.js';

describe('lara node helper context', () => {
    it('maps node types to dedicated helper branches', () => {
        expect(laraNodeHelperBranchId('code')).toBe('code_helper');
        expect(laraNodeHelperBranchId('llm_node')).toBe('llm_node_helper');
        expect(laraNodeHelperBranchId('external_api')).toBe('external_api_node_helper');
        expect(laraNodeHelperBranchId('unknown')).toBe('node_helper');
    });

    it('builds ID-only context for selected code node without payloads', () => {
        const editorState = {
            flowId: 'demo_flow',
            currentBranchId: 'fast',
            selectedNodeId: 'calc',
            isDirty: true,
            flowConfig: { flow_id: 'demo_flow', name: 'Demo', nodes: { calc: { prompt: 'huge' } } },
            branchData: {
                entry: 'calc',
                variables: { api_key: 'secret', limit: 3 },
                edges: [{ from_node: 'calc', to_node: null }],
                nodes: {
                    calc: {
                        type: 'code',
                        name: 'Calc',
                        language: 'python',
                        code: 'async def run(args, state):\n    return {"ok": True}',
                    },
                    helper: {
                        type: 'code',
                        language: 'python',
                        code: 'def normalize(value):\n    return value',
                    },
                    talk: { type: 'llm_node', prompt: 'hi' },
                },
            },
        };

        const context = buildLaraFlowsContext(editorState, {}, {
            assistant_branch_id: LARA_CODE_HELPER_BRANCH_ID,
            request_kind: 'node_ai_helper',
            selection_source: 'node_header_ai',
        });

        expect(context.flow_id).toBe('demo_flow');
        expect(context.node_id).toBe('calc');
        expect(context.node_type).toBe('code');
        expect(context.branch_node_count).toBe(3);
        expect(context.branch_edge_count).toBe(1);
        expect(context.editor_dirty).toBe(true);
        expect(context).not.toHaveProperty('node_payload');
        expect(context).not.toHaveProperty('flow_payload');
        expect(context).not.toHaveProperty('branch_node_payload');
        expect(context).not.toHaveProperty('branch_code_payload');

        const flat = flattenLaraFlowsContext(context);
        expect(flat.assistant_branch_id).toBe('code_helper');
        expect(flat.target_branch_id).toBe('fast');
        expect(flat.api_branch_id).toBe('fast');
        expect(flat.editor_dirty).toBe(true);
        expect(flat).not.toHaveProperty('lara_ui_context_json');
        expect(flat).not.toHaveProperty('node_payload_json');
        expect(flat).not.toHaveProperty('flow_payload_json');
        expect(flat).not.toHaveProperty('branch_node_payload_json');
        expect(flat).not.toHaveProperty('selected_code_node_code');
        expect(JSON.stringify(flat)).not.toContain('async def run');
        expect(JSON.stringify(flat)).not.toContain('secret');
    });

    it('uses default API branch for base and stable conversation key', () => {
        const editorState = {
            flowId: 'demo_flow',
            currentBranchId: 'base',
            selectedNodeId: 'talk',
            isDirty: false,
            branchData: {
                nodes: {
                    talk: { type: 'llm_node', prompt: 'hello' },
                },
            },
        };
        const context = buildLaraFlowsContext(editorState, {}, {
            assistant_branch_id: laraNodeHelperBranchId('llm_node'),
            request_kind: 'node_ai_helper',
        });
        const flat = flattenLaraFlowsContext(context);

        expect(flat.api_branch_id).toBe('default');
        expect(flat.editor_dirty).toBe(false);
        expect(laraNodeHelperConversationKey(context)).toBe('llm_node_helper:demo_flow:base:talk');
    });
});
