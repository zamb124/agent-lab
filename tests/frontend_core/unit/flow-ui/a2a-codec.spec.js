import { describe, expect, it } from 'vitest';

import {
    a2aEndpointUrl,
    a2uiCapabilities,
    buildFlowUIMessage,
    buildListTasksBody,
    buildSendMessageBody,
    flowUIShareCollectionUrl,
    interfaceProfileUrl,
} from '../../../../core/frontend/static/lib/flow-ui/protocol/a2a-codec.js';
import {
    A2UI_VERSION,
    FLOW_UI_ACTIONS,
    LINNEX_CATALOG_ID,
} from '../../../../core/frontend/static/lib/flow-ui/protocol/constants.js';

function documentStub(revision = 2) {
    return {
        document_id: 'flow-ui:ctx-1',
        revision,
        active_page_id: 'main',
        session_view_state: {},
        surfaces: {
            main: {
                data_model: { values: { message: 'hello', files: [] } },
            },
        },
    };
}

describe('flow-ui a2a codec', () => {
    it('builds flow and embed endpoints without inventing ids', () => {
        expect(a2aEndpointUrl({ baseUrl: '/flows/', flowId: 'demo' })).toBe(
            '/flows/api/v1/demo'
        );
        expect(a2aEndpointUrl({ baseUrl: 'https://api.example/flows', embedId: 'emb-1' })).toBe(
            'https://api.example/flows/api/v1/embed/emb-1'
        );
        expect(() => a2aEndpointUrl({ baseUrl: '/flows' })).toThrow(
            /flowId or embedId is required/
        );
        expect(() => a2aEndpointUrl({ flowId: 'demo' })).toThrow(/baseUrl is required/);
        expect(() => flowUIShareCollectionUrl({})).toThrow(/baseUrl is required/);
        expect(interfaceProfileUrl({ baseUrl: '/flows', flowId: 'demo', branchId: 'canary' })).toBe(
            '/flows/api/v1/demo/interface-profile?branch_id=canary'
        );
        expect(flowUIShareCollectionUrl({ baseUrl: '/flows/' })).toBe(
            '/flows/api/v1/flow-ui/shares'
        );
    });

    it('pins A2UI catalog identity and Flow UI action names', () => {
        const caps = a2uiCapabilities();
        expect(caps[A2UI_VERSION].supportedCatalogIds).toEqual([LINNEX_CATALOG_ID]);
        expect(LINNEX_CATALOG_ID).toBe('https://linnex.io/a2ui/catalog/platform/v1');
        expect(FLOW_UI_ACTIONS.bootstrap).toBe('platform.ui.bootstrap');
        expect(FLOW_UI_ACTIONS.sync).toBe('platform.ui.sync');
        expect(FLOW_UI_ACTIONS.submit).toBe('platform.ui.submit');
    });

    it('builds typed Flow UI message payloads for sync and submit', () => {
        const sync = buildFlowUIMessage({
            kind: 'sync',
            contextId: 'ctx-1',
            document: documentStub(2),
            surfaceId: 'main',
            sourceComponentId: 'message-input',
            actionContext: {
                mutation_id: 'm1',
                base_revision: 2,
                values: { message: 'hello', files: [] },
            },
        });
        expect(sync.message.role).toBe('ROLE_USER');
        expect(sync.message.contextId).toBe('ctx-1');
        expect(sync.message.parts[0].data[0].action.name).toBe(FLOW_UI_ACTIONS.sync);
        expect(sync.message.parts[0].data[0].action.context.base_revision).toBe(2);
        expect(sync.message.metadata.platformUi.revision).toBe(2);

        const submit = buildFlowUIMessage({
            kind: 'submit',
            contextId: 'ctx-1',
            document: documentStub(3),
            actionContext: {
                mutation_id: 'm2',
                base_revision: 3,
                values: { message: 'go', files: [] },
            },
        });
        expect(submit.message.parts[0].data[0].action.name).toBe(FLOW_UI_ACTIONS.submit);

        expect(() => buildFlowUIMessage({ kind: 'sync', contextId: 'ctx-1' })).toThrow(
            /requires an authoritative document/
        );
    });

    it('copies standing variables into params.metadata on SendMessage body', () => {
        const command = buildFlowUIMessage({
            kind: 'submit',
            contextId: 'ctx-1',
            document: documentStub(1),
            branchId: 'code_helper',
            metadata: {
                variables: {
                    flow_id: 'flow_real',
                    node_id: 'main',
                    target_branch_id: 'base',
                },
            },
            actionContext: {
                mutation_id: 'm3',
                base_revision: 1,
                values: { message: 'hi', files: [] },
            },
        });
        expect(command.message.metadata.variables).toEqual({
            flow_id: 'flow_real',
            node_id: 'main',
            target_branch_id: 'base',
        });
        const body = buildSendMessageBody(command, { streaming: true });
        expect(body.method).toBe('SendStreamingMessage');
        expect(body.params.metadata).toEqual({
            branch: 'code_helper',
            variables: {
                flow_id: 'flow_real',
                node_id: 'main',
                target_branch_id: 'base',
            },
        });
    });

    it('builds ListTasks body for context hydration', () => {
        const body = buildListTasksBody({ contextId: 'ctx-1', pageSize: 25 });
        expect(body.method).toBe('ListTasks');
        expect(body.params).toEqual({
            contextId: 'ctx-1',
            pageSize: 25,
            pageToken: '',
            includeArtifacts: true,
        });
        expect(() => buildListTasksBody({})).toThrow(/contextId is required/);
    });
});
