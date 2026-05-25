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

    it('builds full branch context for selected code node', () => {
        const editorState = {
            flowId: 'demo_flow',
            currentBranchId: 'fast',
            selectedNodeId: 'calc',
            flowConfig: { flow_id: 'demo_flow', name: 'Demo' },
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
                        parameters_schema: {
                            type: 'object',
                            properties: { value: { type: 'number' } },
                            required: ['value'],
                        },
                        output_mapping: { result: 'answer' },
                    },
                    helper: {
                        type: 'code',
                        language: 'python',
                        code: 'def normalize(value):\n    return value',
                    },
                    talk: { type: 'llm_node', prompt: 'hi' },
                },
                resources: {
                    shared: {
                        type: 'code',
                        name: 'Shared',
                        code: 'def shared():\n    return 1',
                    },
                },
            },
            dataflow: {
                nodes: {
                    calc: { inputs: ['value'], outputs: ['answer'] },
                },
            },
        };

        const context = buildLaraFlowsContext(editorState, {}, {
            assistant_branch_id: LARA_CODE_HELPER_BRANCH_ID,
            request_kind: 'node_ai_helper',
            selection_source: 'node_header_ai',
        });

        expect(context.branch_node_payload.nodes.map((node) => node.node_id)).toEqual(['calc', 'helper', 'talk']);
        expect(context.branch_code_payload.code_nodes.map((node) => node.node_id)).toEqual(['calc', 'helper']);
        expect(context.branch_code_payload.code_resources[0]).toMatchObject({
            resource_id: 'shared',
            code: 'def shared():\n    return 1',
        });
        expect(context.dataflow_node).toEqual({ inputs: ['value'], outputs: ['answer'] });

        const flat = flattenLaraFlowsContext(context);
        expect(flat.assistant_branch_id).toBe('code_helper');
        expect(flat.target_branch_id).toBe('fast');
        expect(flat.api_branch_id).toBe('fast');
        expect(flat.selected_code_node_code).toContain('async def run');
        expect(JSON.parse(flat.branch_node_payload_json).nodes).toHaveLength(3);
        expect(JSON.parse(flat.branch_code_payload_json).code_nodes).toHaveLength(2);
    });

    it('uses default API branch for base and stable conversation key', () => {
        const editorState = {
            flowId: 'demo_flow',
            currentBranchId: 'base',
            selectedNodeId: 'talk',
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
        expect(laraNodeHelperConversationKey(context)).toBe('llm_node_helper:demo_flow:base:talk');
    });
});
