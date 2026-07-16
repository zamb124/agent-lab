import { describe, expect, it } from 'vitest';
import { buildFrontendAssistantContext } from '../../../apps/frontend/ui/_helpers/platform-assistant-context.js';
import { buildSyncAssistantContext } from '../../../apps/sync/ui/_helpers/platform-assistant-context.js';
import { buildRagAssistantContext } from '../../../apps/rag/ui/_helpers/platform-assistant-context.js';
import { buildOfficeAssistantContext } from '../../../apps/office/ui/_helpers/platform-assistant-context.js';
import { buildWorktrackerAssistantContext } from '../../../apps/worktracker/ui/_helpers/platform-assistant-context.js';
import { buildLitserveAssistantContext } from '../../../apps/provider_litserve/ui/_helpers/platform-assistant-context.js';
import {
    buildLaraFlowsContext,
    flattenLaraFlowsContext,
} from '../../../apps/flows/ui/_helpers/lara-node-helper.js';

describe('service platform assistant contexts', () => {
    it('builds compact frontend and provider contexts', () => {
        expect(buildFrontendAssistantContext('api-keys')).toEqual({
            service: 'frontend',
            route_key: 'api-keys',
            screen: 'api_keys',
        });
        expect(buildLitserveAssistantContext('models')).toEqual({
            service: 'provider_litserve',
            route_key: 'models',
            screen: 'models',
        });
    });

    it('prefers sync route ids and includes selected runtime ids', () => {
        const context = buildSyncAssistantContext(
            'channel',
            { channelId: 'channel-route' },
            { selectedChannelId: 'channel-state', items: [{ secret: 'not exposed' }] },
            { selectedThreadId: 'thread-1', items: [{ body: 'not exposed' }] },
            { activeCall: { call_id: 'call-1', livekit_token: 'not exposed' } },
        );
        expect(context).toEqual({
            service: 'sync',
            route_key: 'channel',
            screen: 'channel',
            channel_id: 'channel-route',
            thread_id: 'thread-1',
            call_id: 'call-1',
        });
    });

    it('extracts only canonical RAG and Office ids', () => {
        expect(buildRagAssistantContext('namespace_detail', { namespaceId: 'namespace-1' })).toEqual({
            service: 'rag',
            route_key: 'namespace_detail',
            screen: 'namespace_detail',
            namespace_id: 'namespace-1',
        });
        expect(buildOfficeAssistantContext(
            'document_editor',
            { bindingId: 'binding-route' },
            {
                activeCatalogId: 'catalog-1',
                selectedBindingId: 'binding-state',
                items: [{ title: 'not exposed' }],
            },
        )).toEqual({
            service: 'office',
            route_key: 'document_editor',
            screen: 'document_editor',
            binding_id: 'binding-route',
            catalog_id: 'catalog-1',
        });
    });

    it('extracts work item and queue ids without domain payloads', () => {
        expect(buildWorktrackerAssistantContext(
            'queue_detail',
            { workQueueId: 'queue-1' },
            'work-item-panel',
        )).toEqual({
            service: 'worktracker',
            route_key: 'queue_detail',
            screen: 'queue_detail',
            work_item_id: 'work-item-panel',
            work_queue_id: 'queue-1',
        });
    });

    it('flattens Flows editor context with selected node ids', () => {
        const context = buildLaraFlowsContext(
            {
                flowId: 'flow-1',
                currentBranchId: 'draft',
                selectedNodeId: 'node-1',
                branchData: {
                    nodes: {
                        'node-1': {
                            type: 'llm_node',
                            name: 'Node',
                            prompt: 'Initial prompt',
                        },
                    },
                },
                flowConfig: {
                    flow_id: 'ignored-flow-config-id',
                },
            },
            { flowId: 'route-flow', branchId: 'route-branch' },
            {
                assistant_branch_id: 'flows',
                request_kind: 'chat',
            },
        );
        const flattened = flattenLaraFlowsContext(context);
        expect(flattened.flow_id).toBe('flow-1');
        expect(flattened.target_branch_id).toBe('draft');
        expect(flattened.node_id).toBe('node-1');
        expect(flattened.node_type).toBe('llm_node');
        expect(flattened.assistant_branch_id).toBe('flows');
        expect(flattened.lara_request_kind).toBe('chat');
        expect(typeof flattened.lara_ui_context_json).toBe('string');
        expect(flattened.node_payload_json).toContain('Initial prompt');
    });
});
