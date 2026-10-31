import { describe, expect, it } from 'vitest';

import {
    a2aEndpointUrl,
    a2aRequestHeaders,
    buildCancelTaskBody,
    buildListTasksBody,
    buildSendMessageBody,
    buildSubscribeTaskBody,
    buildUserMessage,
    flowUIShareCollectionUrl,
    interfaceUrl,
    normalizeFlowUIBranchId,
} from '../../../../core/frontend/static/lib/a2a/a2a-codec.js';
import { A2A_PROTOCOL_VERSION, FLOW_UI_ACTION_MEDIA_TYPE } from '../../../../core/frontend/static/lib/a2a/constants.js';

describe('flow-ui a2a codec', () => {
    it('builds flow, embed, interface and share endpoints without inventing ids', () => {
        expect(a2aEndpointUrl({ baseUrl: '/flows/', flowId: 'demo' })).toBe('/flows/api/v1/demo');
        expect(a2aEndpointUrl({ baseUrl: 'https://api.example/flows', embedId: 'emb-1' })).toBe(
            'https://api.example/flows/api/v1/embed/emb-1',
        );
        expect(() => a2aEndpointUrl({ baseUrl: '/flows' })).toThrow(/flowId or embedId is required/);
        expect(() => a2aEndpointUrl({ flowId: 'demo' })).toThrow(/baseUrl is required/);
        expect(interfaceUrl({ baseUrl: '/flows', flowId: 'demo' })).toBe('/flows/api/v1/demo/interface');
        expect(interfaceUrl({ baseUrl: '/flows', flowId: 'demo', branchId: 'sales' })).toBe(
            '/flows/api/v1/demo/interface?branch_id=sales',
        );
        expect(flowUIShareCollectionUrl({ baseUrl: '/flows' })).toBe('/flows/api/v1/flow-ui/shares');
    });

    it('treats base and default as the same branch', () => {
        expect(normalizeFlowUIBranchId('base')).toBe('default');
        expect(normalizeFlowUIBranchId('  ')).toBe('default');
        expect(normalizeFlowUIBranchId('sales')).toBe('sales');
    });

    it('builds a text turn with file parts and context binding', () => {
        const message = buildUserMessage({
            contextId: 'ctx-1',
            taskId: 'task-1',
            text: 'hello',
            files: [{ url: '/flows/api/v1/files/download/f1', content_type: 'image/png', original_name: 'a.png' }],
        });
        expect(message.role).toBe('ROLE_USER');
        expect(message.messageId).toMatch(/^message:/);
        expect(message.contextId).toBe('ctx-1');
        expect(message.taskId).toBe('task-1');
        expect(message.parts[0]).toEqual({ text: 'hello' });
        expect(message.parts[1]).toMatchObject({ url: '/flows/api/v1/files/download/f1', mediaType: 'image/png', filename: 'a.png' });
    });

    it('builds a ui-action turn as a single typed data part', () => {
        const message = buildUserMessage({ action: { action: 'submit', source: 'btn', fields: { email: 'a@b.c' } } });
        expect(message.parts).toEqual([{
            data: { action: 'submit', source: 'btn', fields: { email: 'a@b.c' }, payload: {} },
            mediaType: FLOW_UI_ACTION_MEDIA_TYPE,
        }]);
        expect(() => buildUserMessage({ action: { action: '', source: 'btn' } })).toThrow(/requires action name/);
        expect(() => buildUserMessage({ action: { action: 'submit', source: '' } })).toThrow(/requires source block_id/);
    });

    it('copies branch and standing variables into params.metadata on SendMessage bodies', () => {
        const message = buildUserMessage({ text: 'hi' });
        const streaming = buildSendMessageBody(message, { branchId: 'base', variables: {} });
        expect(streaming.method).toBe('SendStreamingMessage');
        expect(streaming.params).toEqual({ message });
        const plain = buildSendMessageBody(message, { streaming: false, branchId: 'sales', variables: { plan: 'pro' } });
        expect(plain.method).toBe('SendMessage');
        expect(plain.params.metadata).toEqual({ branch: 'sales', variables: { plan: 'pro' } });
        expect(() => Reflect.apply(buildSendMessageBody, null, [message, { variables: ['x'] }])).toThrow(/plain object/);
    });

    it('builds ListTasks, SubscribeToTask and CancelTask bodies fail-closed', () => {
        const list = buildListTasksBody({ contextId: 'ctx-1', pageSize: 10 });
        expect(list.method).toBe('ListTasks');
        expect(list.params).toEqual({ contextId: 'ctx-1', pageSize: 10, pageToken: '', includeArtifacts: true });
        expect(() => buildListTasksBody({ contextId: '' })).toThrow(/contextId is required/);
        expect(() => buildListTasksBody({ contextId: 'ctx-1', pageSize: 0 })).toThrow(/positive int/);
        expect(buildSubscribeTaskBody('task-1').params).toEqual({ id: 'task-1' });
        expect(buildCancelTaskBody('task-1').method).toBe('CancelTask');
        expect(() => buildSubscribeTaskBody('')).toThrow(/taskId is required/);
    });

    it('pins protocol version and negotiates SSE only for streams', () => {
        expect(a2aRequestHeaders({}, { stream: true })).toEqual({
            'Content-Type': 'application/json',
            Accept: 'text/event-stream',
            'A2A-Version': A2A_PROTOCOL_VERSION,
        });
        expect(a2aRequestHeaders({ Authorization: 'Bearer x' }).Accept).toBe('application/json');
        expect(A2A_PROTOCOL_VERSION).toBe('1.0');
    });
});
