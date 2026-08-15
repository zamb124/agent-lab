import { afterEach, describe, expect, it, vi } from 'vitest';

import { interfaceProfileUrl } from '../../../../core/frontend/static/lib/flow-ui/protocol/a2a-codec.js';
import { FlowUIController } from '../../../../core/frontend/static/lib/flow-ui/runtime/flow-ui-controller.js';
import { createLocalFlowUIProfile } from '../../../../core/frontend/static/lib/flow-ui/runtime/flow-ui-profile.js';

function documentSnapshot(revision = 7) {
    const surface = (id, text) => ({
        surface_id: id,
        root_component_id: 'root',
        components: {
            root: {
                component_id: 'root', type: 'PageShell', kind: 'container',
                properties: {}, children: ['field'], container_layout: null,
                placement: { base: {}, overrides: {} }, bindings: {}, actions: {},
            },
            field: {
                component_id: 'field', type: 'TextField', kind: 'leaf',
                properties: { label: text }, children: [], container_layout: null,
                placement: { base: {}, overrides: {} },
                bindings: { value: '/values/message' }, actions: {},
            },
        },
        data_model: { content: {}, values: { message: '' }, system: {} },
    });
    return {
        schema_version: 1,
        document_id: 'flow-ui:context-1',
        revision,
        template_version: '1.0.0',
        catalog_id: 'https://linnex.io/a2ui/catalog/platform/v1',
        active_page_id: 'main',
        session_view_state: {},
        pages: {
            main: { page_id: 'main', title: { default: 'Main' }, root_surface_id: 'main' },
            details: { page_id: 'details', title: { default: 'Details' }, root_surface_id: 'details' },
        },
        surfaces: { main: surface('main', 'Message'), details: surface('details', 'Details') },
        global_data_model: { content: {}, values: {}, system: {} },
        policy: {},
    };
}

function profile({ interact = true, share = false, autosync = true } = {}) {
    return Object.freeze({
        flow_id: 'flow-1', branch_id: 'release',
        viewer: Object.freeze({
            can_edit_flow: false,
            can_interact: interact,
            can_share: share,
            auth_mode: share ? 'platform' : 'share',
        }),
        look: null,
        catalog: Object.freeze({
            platform_catalog_id: 'https://linnex.io/a2ui/catalog/platform/v1',
            version: 'v0.9.1',
        }),
        capabilities: Object.freeze({
            bootstrap: true, autosync, cancel: interact, files: interact, voice: false,
        }),
        flow_identity: Object.freeze({ title: 'Test flow', image_url: null }),
    });
}

function bootstrapResponse(body, sequence) {
    const contextId = body.params.message.contextId;
    return new Response(JSON.stringify({
        jsonrpc: '2.0', id: body.id,
        result: {
            id: `task-bootstrap-${sequence}`,
            contextId,
            status: { state: 'TASK_STATE_COMPLETED' },
            artifacts: [{
                artifactId: `ui-${sequence}`,
                name: 'ui.document',
                parts: [{ data: { flowUi: documentSnapshot() } }],
            }],
        },
    }), { status: 200, headers: { 'Content-Type': 'application/json' } });
}

function listTasksResponse(body) {
    return new Response(JSON.stringify({
        jsonrpc: '2.0',
        id: body.id,
        result: {
            tasks: [],
            nextPageToken: '',
            pageSize: 50,
            totalSize: 0,
        },
    }), { status: 200, headers: { 'Content-Type': 'application/json' } });
}

function rpcResponse(body, sequence) {
    if (body.method === 'ListTasks') {
        return listTasksResponse(body);
    }
    return bootstrapResponse(body, sequence);
}

afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
});

describe('Flow UI runtime invariants', () => {
    it('uses a fresh A2A bootstrap Task identity on every reopen', async () => {
        const commands = [];
        const fetchMock = vi.fn(async (_url, options) => {
            const body = JSON.parse(options.body);
            if (body.method === 'ListTasks') {
                return listTasksResponse(body);
            }
            commands.push(body.params.message.metadata.platformUi);
            return bootstrapResponse(body, commands.length);
        });
        vi.stubGlobal('fetch', fetchMock);
        const controller = new FlowUIController({
            flowId: 'flow-1', branchId: 'release', contextId: 'context-1',
            baseUrl: '/flows',
            profile: profile({ interact: false, autosync: false }),
        });

        await controller.connect();
        await controller.bootstrap();

        expect(commands).toHaveLength(2);
        expect(commands[0].actionId).not.toBe(commands[1].actionId);
        expect(commands[0].clientMutationId).not.toBe(commands[1].clientMutationId);
        expect(controller.document.revision).toBe(7);
        expect(controller.activeContext.taskOrder).toHaveLength(2);
        expect(fetchMock.mock.calls.some(([_, options]) => (
            JSON.parse(options.body).method === 'ListTasks'
        ))).toBe(true);
        controller.dispose();
    });

    it('enforces read-only mutations while allowing non-persistent page navigation', async () => {
        const fetchMock = vi.fn(async (_url, options) => {
            const body = JSON.parse(options.body);
            return rpcResponse(body, 1);
        });
        vi.stubGlobal('fetch', fetchMock);
        const controller = new FlowUIController({
            flowId: 'flow-1', branchId: 'release', contextId: 'context-1',
            baseUrl: '/flows',
            profile: profile({ interact: false, autosync: false }),
        });
        await controller.connect();

        expect(() => controller.setValue('main', '/values/message', 'forbidden')).toThrow(/read-only/);
        await expect(controller.submit('main', 'submit')).rejects.toThrow(/read-only/);
        controller.navigate('details');

        expect(controller.document.active_page_id).toBe('details');
        expect(controller.activeContext.pendingMutations).toEqual([]);
        expect(fetchMock).toHaveBeenCalledTimes(2);
        controller.dispose();
    });

    it('keeps editor preview local and emits submit as a preview event', async () => {
        const fetchMock = vi.fn();
        vi.stubGlobal('fetch', fetchMock);
        const controller = new FlowUIController({
            initialDocument: documentSnapshot(),
            profile: createLocalFlowUIProfile(),
            contextId: 'preview-context',
        });
        let preview = null;
        controller.addEventListener('flow-ui-preview-submit', (event) => { preview = event.detail; });
        await controller.connect();

        controller.setValue('main', '/values/message', 'local draft');
        const result = await controller.submit('main', 'submit', { intent: 'test' });

        expect(fetchMock).not.toHaveBeenCalled();
        expect(controller.document.surfaces.main.data_model.values.message).toBe('');
        expect(controller.activeContext.pendingMutations).toEqual([]);
        expect(result.preview).toBe(true);
        expect(preview.document.surfaces.main.data_model.values.message).toBe('local draft');
        controller.dispose();
    });

    it('appends uploaded files when append=true and clears composer values after submit', async () => {
        const fetchMock = vi.fn();
        vi.stubGlobal('fetch', fetchMock);
        const controller = new FlowUIController({
            initialDocument: documentSnapshot(),
            profile: createLocalFlowUIProfile(),
            contextId: 'preview-upload',
        });
        await controller.connect();
        controller.setValue('main', '/values/files', []);

        const first = new File(['a'], 'a.txt', { type: 'text/plain' });
        const second = new File(['b'], 'b.txt', { type: 'text/plain' });
        await controller.uploadFiles('main', 'file-upload', '/values/files', [first], { append: true });
        await controller.uploadFiles('main', 'file-upload', '/values/files', [second], { append: true });

        const files = controller.document.surfaces.main.data_model.values.files;
        expect(Array.isArray(files)).toBe(true);
        expect(files).toHaveLength(2);
        expect(files[0].original_name).toBe('a.txt');
        expect(files[1].original_name).toBe('b.txt');

        controller.setValue('main', '/values/message', 'with files');
        await controller.submit('main', 'submit');
        expect(controller.document.surfaces.main.data_model.values.message).toBe('');
        expect(controller.document.surfaces.main.data_model.values.files).toEqual([]);
        controller.dispose();
    });

    it('creates a share only from the acknowledged document identity', async () => {
        const bodies = [];
        const fetchMock = vi.fn(async (url, options) => {
            const body = JSON.parse(options.body);
            bodies.push({ url: String(url), body });
            if (String(url).endsWith('/api/v1/flow-ui/shares')) {
                return new Response(JSON.stringify({
                    share_url: 'https://linnex.io/l/share123',
                    grant: { grant_id: 'grant-123' },
                }), { status: 200, headers: { 'Content-Type': 'application/json' } });
            }
            return rpcResponse(body, 1);
        });
        vi.stubGlobal('fetch', fetchMock);
        const controller = new FlowUIController({
            flowId: 'flow-1', branchId: 'release', contextId: 'context-1',
            baseUrl: '/flows', profile: profile({ share: true }),
        });
        await controller.connect();
        const result = await controller.createShare({ permission: 'viewer' });

        expect(result.share_url).toBe('https://linnex.io/l/share123');
        const shareRequest = bodies.at(-1);
        expect(shareRequest.url).toBe('/flows/api/v1/flow-ui/shares');
        expect(shareRequest.body).toMatchObject({
            flow_id: 'flow-1', context_id: 'context-1',
            document_id: 'flow-ui:context-1', minimum_revision: 7,
            permission: 'viewer',
        });
        controller.dispose();
    });

    it('revokes a share grant over DELETE', async () => {
        const fetchMock = vi.fn(async (url, options = {}) => {
            const method = options.method || 'GET';
            if (method === 'DELETE' && String(url).endsWith('/api/v1/flow-ui/shares/grant-123')) {
                return new Response(null, { status: 204 });
            }
            if (method === 'POST' && String(url).endsWith('/api/v1/flow-ui/shares')) {
                return new Response(JSON.stringify({
                    share_url: 'https://linnex.io/l/share123',
                    grant: { grant_id: 'grant-123' },
                }), { status: 200, headers: { 'Content-Type': 'application/json' } });
            }
            const body = JSON.parse(options.body);
            return rpcResponse(body, 1);
        });
        vi.stubGlobal('fetch', fetchMock);
        const controller = new FlowUIController({
            flowId: 'flow-1', branchId: 'release', contextId: 'context-1',
            baseUrl: '/flows', profile: profile({ share: true }),
        });
        await controller.connect();
        await controller.createShare({ permission: 'viewer' });
        let revoked = null;
        controller.addEventListener('flow-ui-share-revoked', (event) => { revoked = event.detail; });
        await controller.revokeShare('grant-123');
        expect(revoked).toEqual({ grantId: 'grant-123' });
        expect(fetchMock.mock.calls.some(([url, options]) => (
            String(url) === '/flows/api/v1/flow-ui/shares/grant-123'
            && options?.method === 'DELETE'
        ))).toBe(true);
        controller.dispose();
    });

    it('includes the non-default branch in the profile control-plane URL', () => {
        expect(interfaceProfileUrl({
            baseUrl: '/flows', flowId: 'flow/one', branchId: 'release candidate',
        })).toBe('/flows/api/v1/flow%2Fone/interface-profile?branch_id=release%20candidate');
    });

    it('hydrates durable ListTasks projections after bootstrap', async () => {
        const fetchMock = vi.fn(async (_url, options) => {
            const body = JSON.parse(options.body);
            if (body.method === 'ListTasks') {
                return new Response(JSON.stringify({
                    jsonrpc: '2.0',
                    id: body.id,
                    result: {
                        tasks: [{
                            id: 'task-echo-1',
                            contextId: 'context-1',
                            status: {
                                state: 'TASK_STATE_COMPLETED',
                                message: { parts: [{ text: 'chat-ok:reopen' }] },
                            },
                            artifacts: [
                                { artifactId: 'response', name: 'response', parts: [{ text: 'chat-ok:reopen' }] },
                            ],
                        }],
                        nextPageToken: '',
                        pageSize: 50,
                        totalSize: 1,
                    },
                }), { status: 200, headers: { 'Content-Type': 'application/json' } });
            }
            return bootstrapResponse(body, 1);
        });
        vi.stubGlobal('fetch', fetchMock);
        const controller = new FlowUIController({
            flowId: 'flow-1', branchId: 'release', contextId: 'context-1',
            baseUrl: '/flows',
            profile: profile({ interact: false, autosync: false }),
        });
        await controller.connect();
        expect(controller.activeContext.tasksById['task-echo-1'].status.message.parts[0].text)
            .toBe('chat-ok:reopen');
        expect(controller.activeContext.taskOrder).toContain('task-echo-1');
        controller.dispose();
    });

    it('dispose aborts in-flight connect without treating AbortError as context failure', async () => {
        let signal;
        const fetchMock = vi.fn((_url, options) => new Promise((resolve, reject) => {
            signal = options.signal;
            options.signal.addEventListener('abort', () => {
                reject(new DOMException('The operation was aborted.', 'AbortError'));
            });
        }));
        vi.stubGlobal('fetch', fetchMock);
        const controller = new FlowUIController({
            flowId: 'flow-1', branchId: 'release', contextId: 'context-1',
            baseUrl: '/flows',
            profile: profile({ interact: false, autosync: false }),
        });
        const errors = [];
        controller.addEventListener('flow-ui-error', (event) => { errors.push(event.detail); });
        const connectPromise = controller.connect();
        await Promise.resolve();
        expect(signal).toBeTruthy();
        controller.dispose();
        await expect(connectPromise).rejects.toMatchObject({ name: 'AbortError' });
        expect(errors).toEqual([]);
        expect(controller.abortController).toBeNull();
    });

    it('sets submitting before flush and ignores concurrent submit', async () => {
        const fetchMock = vi.fn(async (_url, options) => {
            const body = JSON.parse(options.body);
            return rpcResponse(body, 1);
        });
        vi.stubGlobal('fetch', fetchMock);
        const controller = new FlowUIController({
            flowId: 'flow-1', branchId: 'release', contextId: 'context-1',
            baseUrl: '/flows',
            profile: profile({ interact: true, autosync: false }),
        });
        await controller.connect();

        let releaseSend;
        const sendGate = new Promise((resolve) => { releaseSend = resolve; });
        const flushOrder = [];
        vi.spyOn(controller.autosync, 'flushNow').mockImplementation(async () => {
            flushOrder.push('flush');
            expect(controller.activeContext.submitting).toBe(true);
        });
        const sendSpy = vi.spyOn(controller, '_sendControl').mockImplementation(async () => {
            flushOrder.push('send');
            await sendGate;
        });

        const first = controller.submit('main', 'submit');
        await Promise.resolve();
        expect(controller.activeContext.submitting).toBe(true);
        expect(flushOrder[0]).toBe('flush');

        const concurrent = await controller.submit('main', 'submit');
        expect(concurrent).toBeUndefined();
        expect(sendSpy).toHaveBeenCalledTimes(1);

        releaseSend();
        await first;
        expect(controller.activeContext.submitting).toBe(false);
        controller.dispose();
    });

    it('submit swallows AbortError when dispose cancels in-flight stream', async () => {
        const fetchMock = vi.fn(async (_url, options) => {
            const body = JSON.parse(options.body);
            return rpcResponse(body, 1);
        });
        vi.stubGlobal('fetch', fetchMock);
        const controller = new FlowUIController({
            flowId: 'flow-1', branchId: 'release', contextId: 'context-1',
            baseUrl: '/flows',
            profile: profile({ interact: true, autosync: false }),
        });
        await controller.connect();
        vi.spyOn(controller.autosync, 'flushNow').mockResolvedValue(undefined);
        vi.spyOn(controller, '_sendControl').mockImplementation(async () => {
            throw new DOMException('BodyStreamBuffer was aborted', 'AbortError');
        });
        await expect(controller.submit('main', 'submit')).resolves.toBeUndefined();
        expect(controller.activeContext.submitting).toBe(false);
        controller.dispose();
    });
});
