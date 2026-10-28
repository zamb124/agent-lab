/**
 * FlowUIClient поверх фейкового A2A-сервера: open/hydrate с пагинацией ListTasks, хвост
 * незавершённого Task (SubscribeToTask с переподключением), ход пользователя (текст и ui-action,
 * очистка правок по первому state-артефакту), отмена, новый контекст, share, dispose.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';

import { FlowUIClient } from '@platform/lib/flow-ui/runtime/flow-ui-client.js';
import { FlowUIStore } from '@platform/lib/flow-ui/runtime/flow-ui-store.js';

const CTX = 'context:existing';

const DOCUMENT = {
    start_page_id: 'main',
    pages: [{ page_id: 'main', title: 'Main', blocks: [
        { block_id: 'name', type: 'text_input', field: 'name', label: 'Name', required: true },
        { block_id: 'note', type: 'text_input', field: 'note', label: 'Note', required: false },
    ] }],
};

function interfaceResponse(document = DOCUMENT) {
    return {
        flow_id: 'flow-1',
        branch_id: 'default',
        document,
        viewer: { can_edit_flow: false, can_interact: true, can_share: true, auth_mode: 'platform' },
        look: null,
        capabilities: { cancel: true, files: false, voice: false },
        flow_identity: { title: 'Flow', image_url: null },
    };
}

function jsonResponse(body, status = 200) {
    return {
        ok: status >= 200 && status < 300,
        status,
        headers: { get: (name) => (name.toLowerCase() === 'content-type' ? 'application/json' : null) },
        json: async () => body,
        text: async () => JSON.stringify(body),
    };
}

/** SSE-ответ из кадров; ``hang`` держит соединение открытым до abort — как живой стрим. */
function sseResponse(frames, signal, { hang = false } = {}) {
    const encoder = new TextEncoder();
    const queue = frames.map((frame) => encoder.encode(`data: ${JSON.stringify(frame)}\n\n`));
    const reader = {
        read: () => new Promise((resolve, reject) => {
            if (queue.length > 0) { resolve({ done: false, value: queue.shift() }); return; }
            if (!hang) { resolve({ done: true, value: undefined }); return; }
            if (signal.aborted) { reject(new DOMException('Aborted', 'AbortError')); return; }
            signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true });
        }),
        cancel: async () => {},
    };
    return {
        ok: true,
        status: 200,
        headers: { get: (name) => (name.toLowerCase() === 'content-type' ? 'text/event-stream' : null) },
        body: { getReader: () => reader },
    };
}

function statusFrame(taskId, state, { message = null, contextId = CTX } = {}) {
    const status = { state };
    if (message !== null) status.message = message;
    return { result: { statusUpdate: { taskId, contextId, status } } };
}

function stateFrame(taskId, state, contextId = CTX) {
    return { result: { artifactUpdate: { taskId, contextId, append: true, lastChunk: false, artifact: { artifactId: 'state', name: 'state', parts: [{ data: state, mediaType: 'application/json' }] } } } };
}

function uiFrame(taskId, event, contextId = CTX) {
    return { result: { artifactUpdate: { taskId, contextId, append: true, lastChunk: false, artifact: { artifactId: 'ui', name: 'ui', parts: [{ data: event, mediaType: 'application/vnd.platform.ui+json' }] } } } };
}

function responseFrame(taskId, text, contextId = CTX) {
    return { result: { artifactUpdate: { taskId, contextId, append: true, lastChunk: false, artifact: { artifactId: `${taskId}:response`, name: 'response', parts: [{ text }] } } } };
}

function taskSnapshot(taskId, state, { artifacts = [], metadata = undefined, contextId = CTX, history = [] } = {}) {
    const task = { id: taskId, contextId, status: { state }, artifacts, history };
    if (metadata !== undefined) task.metadata = metadata;
    return task;
}

/** Первый кадр SendStreamingMessage: SUBMITTED Task с ходом пользователя в history. */
function submittedTaskFrame(taskId, message) {
    const history = [{ messageId: message.messageId, role: 'ROLE_USER', taskId, contextId: message.contextId, parts: message.parts }];
    return { result: { task: taskSnapshot(taskId, 'TASK_STATE_SUBMITTED', { contextId: message.contextId, history }) } };
}

/** Фейковый A2A-сервер: маршрутизация по JSON-RPC method, журнал вызовов. */
function fakeServer() {
    const calls = [];
    const handlers = {
        interface: () => jsonResponse(interfaceResponse()),
        ListTasks: () => jsonResponse({ result: { tasks: [], nextPageToken: '' } }),
        SendStreamingMessage: (params, signal) => sseResponse([], signal),
        SubscribeToTask: (params, signal) => sseResponse([], signal),
        CancelTask: () => jsonResponse({ result: {} }),
        share: () => jsonResponse({}),
    };
    vi.stubGlobal('fetch', vi.fn(async (url, init = {}) => {
        const method = init.method || 'GET';
        const body = typeof init.body === 'string' ? JSON.parse(init.body) : null;
        const rpc = body && typeof body.method === 'string' ? body.method : null;
        calls.push({ url, method, body, rpc, headers: init.headers, credentials: init.credentials });
        if (rpc !== null) return handlers[rpc](body.params, init.signal, body);
        if (method === 'GET') return handlers.interface(url, init);
        return handlers.share(url, init, body);
    }));
    return { calls, handlers, rpcCalls: (name) => calls.filter((call) => call.rpc === name) };
}

function flush(rounds = 5) {
    let chain = Promise.resolve();
    for (let index = 0; index < rounds; index += 1) chain = chain.then(() => new Promise((resolve) => setTimeout(resolve, 0)));
    return chain;
}

/** Клиенты теста: хвосты Tasks живут в фоне, поэтому каждый клиент гасится после теста. */
const clients = [];

function createClient(options = {}) {
    const client = new FlowUIClient({ baseUrl: 'https://p/flows', flowId: 'flow-1', ...options });
    clients.push(client);
    return client;
}

afterEach(() => {
    for (const client of clients.splice(0)) client.dispose();
    vi.unstubAllGlobals();
});

describe('FlowUIClient construction and subscriptions', () => {

    it('derives the A2A endpoint from flow or embed target and normalizes the branch', () => {
        expect(() => new FlowUIClient()).toThrow(/client options required/);
        expect(() => new FlowUIClient({ baseUrl: 'https://p/flows' })).toThrow(/flowId or embedId is required/);
        const byFlow = new FlowUIClient({ baseUrl: 'https://p/flows/', flowId: 'flow-1', branchId: 'base' });
        expect(byFlow.endpoint).toBe('https://p/flows/api/v1/flow-1');
        expect(byFlow.target.branchId).toBe('default');
        expect(byFlow.credentials).toBe('include');
        const byEmbed = new FlowUIClient({ baseUrl: 'https://p/flows', embedId: 'emb 1', branchId: ' sales ', credentials: 'omit' });
        expect(byEmbed.endpoint).toBe('https://p/flows/api/v1/embed/emb%201');
        expect(byEmbed.target.branchId).toBe('sales');
        expect(byEmbed.credentials).toBe('omit');
        const store = new FlowUIStore();
        expect(new FlowUIClient({ baseUrl: 'https://p/flows', flowId: 'f', store }).store).toBe(store);
        expect(new FlowUIClient({ baseUrl: 'https://p/flows', flowId: 'f', store: {} }).store).toBeInstanceOf(FlowUIStore);
    });

    it('validates event subscriptions and returns an unsubscribe function', () => {
        const client = new FlowUIClient({ baseUrl: 'https://p/flows', flowId: 'f' });
        expect(() => client.on('turn', () => {})).toThrow(/unknown client event "turn"/);
        expect(() => client.on('frame', null)).toThrow(/handler must be a function/);
        const seen = [];
        const off = client.on('state', (state) => seen.push(state));
        client._emit('state', { a: 1 });
        off();
        client._emit('state', { a: 2 });
        expect(seen).toEqual([{ a: 1 }]);
    });

    it('fails closed when getHeaders does not resolve to an object', async () => {
        fakeServer();
        const client = new FlowUIClient({ baseUrl: 'https://p/flows', flowId: 'f', getHeaders: async () => 'Bearer x' });
        await expect(client.open()).rejects.toThrow(/getHeaders must resolve to a headers object/);
        const arrayHeaders = new FlowUIClient({ baseUrl: 'https://p/flows', flowId: 'f', getHeaders: () => [] });
        await expect(arrayHeaders.open()).rejects.toThrow(/getHeaders must resolve to a headers object/);
    });
});

describe('FlowUIClient.open and hydrate', () => {

    it('creates a fresh context, loads the interface with auth headers and applies a local document', async () => {
        const server = fakeServer();
        const client = createClient({ credentials: 'omit', getHeaders: () => ({ Authorization: 'Bearer t' }) });
        const local = { start_page_id: 'other', pages: [{ page_id: 'other', title: 'Other', blocks: [] }] };
        const store = await client.open({ document: local });
        expect(store).toBe(client.store);
        expect(client.contextId).toMatch(/^context:/);
        expect(store.interface.flow_id).toBe('flow-1');
        expect(store.document).toBe(local);
        expect(store.pageId).toBe('other');
        expect(server.calls).toHaveLength(1);
        expect(server.calls[0]).toMatchObject({ url: 'https://p/flows/api/v1/flow-1/interface', method: 'GET', credentials: 'omit', headers: { Accept: 'application/json', Authorization: 'Bearer t' } });
    });

    it('surfaces interface HTTP errors with status', async () => {
        const server = fakeServer();
        server.handlers.interface = () => jsonResponse({ detail: 'nope' }, 403);
        const client = createClient();
        await expect(client.open()).rejects.toMatchObject({ message: 'flow-ui: interface HTTP 403', status: 403 });
    });

    it('replays an existing context through paginated ListTasks and folds state from every task', async () => {
        const server = fakeServer();
        const pages = {
            '': { tasks: [taskSnapshot('t1', 'TASK_STATE_COMPLETED', { artifacts: [{ artifactId: 'state', name: 'state', parts: [{ data: { a: 1, b: 1 }, mediaType: 'application/json' }] }] })], nextPageToken: 'p2' },
            p2: { tasks: [taskSnapshot('t2', 'TASK_STATE_COMPLETED', { artifacts: [{ artifactId: 'state', name: 'state', parts: [{ data: [{ op: 'replace', path: '/b', value: 2 }], mediaType: 'application/json-patch+json' }] }] })], nextPageToken: '' },
        };
        server.handlers.ListTasks = (params) => jsonResponse({ result: pages[params.pageToken] });
        const client = createClient();
        const tasks = [];
        client.on('task', (task) => tasks.push(task.id));
        await client.open({ contextId: CTX });
        expect(client.contextId).toBe(CTX);
        expect(server.rpcCalls('ListTasks').map((call) => call.body.params)).toEqual([
            { contextId: CTX, pageSize: 50, pageToken: '', includeArtifacts: true },
            { contextId: CTX, pageSize: 50, pageToken: 'p2', includeArtifacts: true },
        ]);
        expect(client.store.state).toEqual({ a: 1, b: 2 });
        expect(client.store.activeTaskId).toBe('t2');
        expect(tasks).toEqual(['t1', 't2']);
        expect(server.rpcCalls('SubscribeToTask')).toHaveLength(0);
        expect(client.store.taskRunning).toBe(false);
    });

    it('tails an unfinished last task through SubscribeToTask until it settles', async () => {
        const server = fakeServer();
        server.handlers.ListTasks = () => jsonResponse({ result: { tasks: [taskSnapshot('t1', 'TASK_STATE_WORKING')], nextPageToken: '' } });
        server.handlers.SubscribeToTask = (params, signal) => sseResponse([
            responseFrame(params.id, 'done'),
            statusFrame(params.id, 'TASK_STATE_COMPLETED'),
        ], signal);
        const client = createClient();
        await client.open({ contextId: CTX });
        expect(client.store.taskRunning).toBe(true);
        await flush();
        expect(server.rpcCalls('SubscribeToTask').map((call) => call.body.params)).toEqual([{ id: 't1' }]);
        expect(client.store.task('t1').status.state).toBe('TASK_STATE_COMPLETED');
        expect(client._tailAbort).toBeNull();
        expect(client.store.taskRunning).toBe(false);
    });

    it('does not tail a task waiting for the user, but keeps following operator/oauth/handoff interrupts', async () => {
        const server = fakeServer();
        const waitingForUser = taskSnapshot('t1', 'TASK_STATE_INPUT_REQUIRED');
        server.handlers.ListTasks = () => jsonResponse({ result: { tasks: [waitingForUser], nextPageToken: '' } });
        const client = createClient();
        await client.open({ contextId: CTX });
        await flush();
        expect(server.rpcCalls('SubscribeToTask')).toHaveLength(0);

        const operatorTask = taskSnapshot('t2', 'TASK_STATE_INPUT_REQUIRED', {
            metadata: { platform_interrupt: { question: 'Operator, please', body: { kind: 'operator_task', handoff_mode: 'single_reply', work_item_id: 'wi-1' } } },
        });
        server.handlers.ListTasks = () => jsonResponse({ result: { tasks: [operatorTask], nextPageToken: '' } });
        server.handlers.SubscribeToTask = (params, signal) => sseResponse([
            statusFrame(params.id, 'TASK_STATE_WORKING'),
            statusFrame(params.id, 'TASK_STATE_COMPLETED'),
        ], signal);
        const following = createClient();
        await following.open({ contextId: CTX });
        await flush();
        expect(server.rpcCalls('SubscribeToTask').map((call) => call.body.params)).toEqual([{ id: 't2' }]);
        expect(following.store.task('t2').status.state).toBe('TASK_STATE_COMPLETED');
    });

    it('hydrate requires a context', async () => {
        fakeServer();
        const client = createClient();
        await expect(client.hydrate()).rejects.toThrow(/hydrate requires contextId/);
    });
});

describe('FlowUIClient.send', () => {

    async function openClient(server, options = {}) {
        const client = createClient(options);
        await client.open();
        return client;
    }

    it('streams a text turn, emits frame/state/ui/task events and clears the pending turn', async () => {
        const server = fakeServer();
        server.handlers.SendStreamingMessage = (params, signal) => sseResponse([
            submittedTaskFrame('t1', params.message),
            statusFrame('t1', 'TASK_STATE_WORKING', { contextId: params.message.contextId }),
            stateFrame('t1', { greeting: 'hi' }, params.message.contextId),
            uiFrame('t1', { kind: 'render', slot_id: 'summary', blocks: [{ block_id: 'r1', type: 'text', text: 'Hello' }] }, params.message.contextId),
            responseFrame('t1', 'Hello there', params.message.contextId),
            statusFrame('t1', 'TASK_STATE_COMPLETED', { contextId: params.message.contextId }),
        ], signal);
        const client = await openClient(server, { branchId: 'sales', getVariables: () => ({ lang: 'ru' }) });
        const events = { frame: 0, state: [], ui: [], task: [], error: [] };
        client.on('frame', () => { events.frame += 1; });
        client.on('state', (state) => events.state.push(state));
        client.on('ui', (event) => events.ui.push(event.kind));
        client.on('task', (task) => events.task.push(task.status.state));
        client.on('error', (error) => events.error.push(error));
        const pendingSeen = [];
        client.store.subscribe(() => pendingSeen.push(client.store.pending !== null));

        const task = await client.send({ text: 'hello' });
        expect(task.id).toBe('t1');
        expect(task.status.state).toBe('TASK_STATE_COMPLETED');
        const sent = server.rpcCalls('SendStreamingMessage')[0].body;
        expect(sent.method).toBe('SendStreamingMessage');
        expect(sent.params.message).toMatchObject({ role: 'ROLE_USER', contextId: client.contextId, parts: [{ text: 'hello' }] });
        expect(sent.params.metadata).toEqual({ branch: 'sales', variables: { lang: 'ru' } });
        expect(server.rpcCalls('SendStreamingMessage')[0].headers.Accept).toBe('text/event-stream');
        expect(events).toMatchObject({ frame: 6, state: [{ greeting: 'hi' }], ui: ['render'], task: ['TASK_STATE_SUBMITTED', 'TASK_STATE_WORKING', 'TASK_STATE_WORKING', 'TASK_STATE_WORKING', 'TASK_STATE_WORKING', 'TASK_STATE_COMPLETED'], error: [] });
        expect(client.store.state).toEqual({ greeting: 'hi' });
        expect(client.store.slots.summary.map((block) => block.block_id)).toEqual(['r1']);
        expect(client.store.pending).toBeNull();
        expect(client.store.streaming).toBe(false);
        expect(client.streaming).toBe(false);
        // Ход был локальным до первого кадра Task, затем pending снят кадром
        expect(pendingSeen).toContain(true);
        expect(server.rpcCalls('SubscribeToTask')).toHaveLength(0);
        // Сообщение пользователя пришло в history Task-снимка: лента не теряет его после отправки
        expect(client.store.task('t1').history).toEqual([
            expect.objectContaining({ role: 'ROLE_USER', messageId: sent.params.message.messageId, parts: [{ text: 'hello' }] }),
        ]);
    });

    it('sends a ui action, clears only the acted fields after the first state artifact, and keeps edits when no state arrives', async () => {
        const server = fakeServer();
        server.handlers.SendStreamingMessage = (params, signal) => sseResponse([
            statusFrame('t1', 'TASK_STATE_WORKING', { contextId: params.message.contextId }),
            stateFrame('t1', { name: 'Ann' }, params.message.contextId),
            statusFrame('t1', 'TASK_STATE_COMPLETED', { contextId: params.message.contextId }),
        ], signal);
        const client = await openClient(server);
        client.store.setEdit('name', 'Ann');
        client.store.setEdit('note', 'keep me');
        await client.send({ action: { action: 'submit', source: 'btn', fields: { name: 'Ann' }, payload: {} } });
        const sent = server.rpcCalls('SendStreamingMessage')[0].body.params;
        expect(sent.message.parts).toEqual([{ data: { action: 'submit', source: 'btn', fields: { name: 'Ann' }, payload: {} }, mediaType: 'application/vnd.platform.ui-action+json' }]);
        expect(sent.metadata).toBeUndefined();
        expect(client.store.edits).toEqual({ note: 'keep me' });
        expect(client.store.state).toEqual({ name: 'Ann' });

        server.handlers.SendStreamingMessage = (params, signal) => sseResponse([
            statusFrame('t2', 'TASK_STATE_WORKING', { contextId: params.message.contextId }),
            statusFrame('t2', 'TASK_STATE_COMPLETED', { contextId: params.message.contextId }),
        ], signal);
        client.store.setEdit('name', 'Bob');
        await client.send({ action: { action: 'submit', source: 'btn', fields: { name: 'Bob' } } });
        // Flow не подтвердил state — локальная правка остаётся, пользователь не теряет ввод
        expect(client.store.edits).toEqual({ note: 'keep me', name: 'Bob' });
        await expect(client.send({ text: 'x', action: { action: 'a', source: 'b' } })).rejects.toThrow(/cannot be combined/);
        expect(client.streaming).toBe(false);
    });

    it('rejects a second turn while the first is streaming and lets abortStream end it silently', async () => {
        const server = fakeServer();
        server.handlers.SendStreamingMessage = (params, signal) => sseResponse([
            statusFrame('t1', 'TASK_STATE_WORKING', { contextId: params.message.contextId }),
        ], signal, { hang: true });
        const client = await openClient(server);
        const turn = client.send({ text: 'slow' });
        await flush();
        expect(client.streaming).toBe(true);
        expect(client.store.streaming).toBe(true);
        expect(client.store.taskRunning).toBe(true);
        await expect(client.send({ text: 'again' })).rejects.toThrow(/a turn is already streaming/);
        client.abortStream();
        const task = await turn;
        expect(task.id).toBe('t1');
        expect(client.streaming).toBe(false);
        expect(client.store.error).toBeNull();
        expect(client.store.pending).toBeNull();
        // Task всё ещё выполняется на сервере — клиент дочитывает его хвостом
        await flush();
        expect(server.rpcCalls('SubscribeToTask').map((call) => call.body.params)).toEqual([{ id: 't1' }]);
        client.dispose();
    });

    it('records transport failures on the store, emits error and rethrows', async () => {
        const server = fakeServer();
        server.handlers.SendStreamingMessage = () => jsonResponse({ detail: 'Insufficient balance' }, 402);
        const client = await openClient(server);
        const errors = [];
        client.on('error', (error) => errors.push(error.message));
        await expect(client.send({ text: 'pay' })).rejects.toMatchObject({ message: 'Insufficient balance', status: 402 });
        expect(errors).toEqual(['Insufficient balance']);
        expect(client.store.error.message).toBe('Insufficient balance');
        expect(client.store.pending).toBeNull();
        expect(client.store.streaming).toBe(false);
        expect(client.streaming).toBe(false);
    });

    it('continues an interrupted task with taskId and tails a task that is still working after the stream closed', async () => {
        const server = fakeServer();
        server.handlers.SendStreamingMessage = (params, signal) => sseResponse([
            statusFrame('t1', 'TASK_STATE_WORKING', { contextId: params.message.contextId }),
        ], signal);
        const client = await openClient(server);
        server.handlers.SubscribeToTask = (params, signal) => sseResponse([
            statusFrame(params.id, 'TASK_STATE_INPUT_REQUIRED', { contextId: client.contextId, message: { messageId: 'q', role: 'ROLE_AGENT', parts: [{ text: 'Your name?' }] } }),
        ], signal);
        await client.send({ text: 'start' });
        await flush();
        expect(server.rpcCalls('SubscribeToTask')).toHaveLength(1);
        expect(client.store.task('t1').status.state).toBe('TASK_STATE_INPUT_REQUIRED');
        expect(client.store.taskRunning).toBe(false);

        server.handlers.SendStreamingMessage = (params, signal) => sseResponse([
            statusFrame(params.message.taskId, 'TASK_STATE_COMPLETED', { contextId: params.message.contextId }),
        ], signal);
        await client.send({ text: 'Ann', taskId: 't1' });
        expect(server.rpcCalls('SendStreamingMessage')[1].body.params.message.taskId).toBe('t1');
        expect(client.store.task('t1').status.state).toBe('TASK_STATE_COMPLETED');
        expect(client.store.orderedTasks().map((task) => task.id)).toEqual(['t1']);
    });
});

describe('FlowUIClient tail, cancel, context and share', () => {

    it('reconnects the tail after a transport error and stops once the task settles', async () => {
        const server = fakeServer();
        let attempt = 0;
        server.handlers.SubscribeToTask = (params, signal) => {
            attempt += 1;
            if (attempt === 1) return jsonResponse({ detail: 'gateway hiccup' }, 502);
            return sseResponse([statusFrame(params.id, 'TASK_STATE_FAILED')], signal);
        };
        server.handlers.ListTasks = () => jsonResponse({ result: { tasks: [taskSnapshot('t1', 'TASK_STATE_WORKING')], nextPageToken: '' } });
        const client = createClient();
        const errors = [];
        client.on('error', (error) => errors.push(error.message));
        await client.open({ contextId: CTX });
        // Хвост уже поднят hydrate: повторный tail того же Task не открывает второй стрим
        client.tail('t1');
        expect(client._tailTaskId).toBe('t1');
        await flush();
        expect(errors).toEqual(['gateway hiccup']);
        expect(attempt).toBe(1);
        expect(client._tailAbort).not.toBeNull();
        await new Promise((resolve) => setTimeout(resolve, 900));
        expect(attempt).toBe(2);
        expect(client.store.task('t1').status.state).toBe('TASK_STATE_FAILED');
        // Task завершён — хвост отпущен сразу, без паузы переподключения
        expect(client._tailAbort).toBeNull();
        expect(client._tailTaskId).toBe('');
    });

    it('stopTail aborts the subscription and applyFrame is a no-op after dispose', async () => {
        const server = fakeServer();
        server.handlers.ListTasks = () => jsonResponse({ result: { tasks: [taskSnapshot('t1', 'TASK_STATE_WORKING')], nextPageToken: '' } });
        server.handlers.SubscribeToTask = (params, signal) => sseResponse([], signal, { hang: true });
        const client = createClient();
        await client.open({ contextId: CTX });
        await flush();
        expect(client._tailAbort).not.toBeNull();
        client.tail('t1');
        expect(server.rpcCalls('SubscribeToTask')).toHaveLength(1);
        client.stopTail();
        expect(client._tailAbort).toBeNull();
        await flush();
        expect(server.rpcCalls('SubscribeToTask')).toHaveLength(1);
        client.dispose();
        expect(client.disposed).toBe(true);
        expect(client.applyFrame(statusFrame('t1', 'TASK_STATE_COMPLETED'))).toBeNull();
        expect(client.store.task('t1').status.state).toBe('TASK_STATE_WORKING');
    });

    it('cancels only a running task and folds the CancelTask reply into the store', async () => {
        const server = fakeServer();
        server.handlers.SendStreamingMessage = (params, signal) => sseResponse([
            statusFrame('t1', 'TASK_STATE_WORKING', { contextId: params.message.contextId }),
        ], signal);
        server.handlers.SubscribeToTask = (params, signal) => sseResponse([], signal, { hang: true });
        const client = createClient();
        await client.open();
        server.handlers.CancelTask = (params) => jsonResponse({ result: { id: params.id, contextId: client.contextId, status: { state: 'TASK_STATE_CANCELED' }, artifacts: [], history: [] } });
        await expect(client.cancel()).rejects.toThrow(/no running task to cancel/);
        await client.send({ text: 'go' });
        expect(client.store.taskRunning).toBe(true);
        await client.cancel();
        expect(server.rpcCalls('CancelTask')[0].body.params).toEqual({ id: 't1' });
        expect(client.store.task('t1').status.state).toBe('TASK_STATE_CANCELED');
        expect(client.store.taskRunning).toBe(false);
        client.dispose();
    });

    it('newContext aborts the stream, drops tasks and edits, and issues a different context id', async () => {
        const server = fakeServer();
        server.handlers.SendStreamingMessage = (params, signal) => sseResponse([
            statusFrame('t1', 'TASK_STATE_WORKING', { contextId: params.message.contextId }),
            stateFrame('t1', { a: 1 }, params.message.contextId),
        ], signal, { hang: true });
        const client = createClient();
        await client.open();
        const first = client.contextId;
        const turn = client.send({ text: 'x' });
        await flush();
        client.store.setEdit('name', 'draft');
        const second = client.newContext();
        await turn;
        expect(second).not.toBe(first);
        expect(client.contextId).toBe(second);
        expect(client.store.orderedTasks()).toEqual([]);
        expect(client.store.state).toEqual({});
        expect(client.store.edits).toEqual({});
        expect(client.store.document).toBe(client.store.interface.document);
        expect(client.streaming).toBe(false);
    });

    it('creates and revokes shares through the flow share collection', async () => {
        const server = fakeServer();
        server.handlers.share = (url, init) => (init.method === 'POST' ? jsonResponse({ grant_id: 'g1', url: 'https://p/s/g1' }) : jsonResponse({ status: 'deleted', grant_id: 'g1' }));
        const client = createClient({ getHeaders: () => ({ Authorization: 'Bearer t' }) });
        await expect(client.createShare()).rejects.toThrow(/share requires an open context/);
        await client.open();
        const grant = await client.createShare({ permission: 'editor', redactedPaths: ['secret'], expiresInSeconds: 60 });
        expect(grant).toEqual({ grant_id: 'g1', url: 'https://p/s/g1' });
        const created = server.calls.at(-1);
        expect(created.method).toBe('POST');
        expect(created.url).toBe('https://p/flows/api/v1/flow-ui/shares');
        expect(created.body).toEqual({ flow_id: 'flow-1', context_id: client.contextId, permission: 'editor', redacted_paths: ['secret'], expires_in_seconds: 60 });
        expect(created.headers).toMatchObject({ 'Content-Type': 'application/json', Authorization: 'Bearer t' });

        await client.revokeShare('g/1');
        expect(server.calls.at(-1)).toMatchObject({ method: 'DELETE', url: 'https://p/flows/api/v1/flow-ui/shares/g%2F1' });
        server.handlers.share = () => jsonResponse({}, 404);
        await expect(client.revokeShare('gone')).resolves.toBeUndefined();
        server.handlers.share = () => jsonResponse({}, 500);
        await expect(client.revokeShare('g1')).rejects.toThrow(/share revoke HTTP 500/);
        await expect(client.createShare()).rejects.toThrow(/share create HTTP 500/);
        await expect(client.revokeShare('')).rejects.toThrow(/grant_id is required/);

        const embed = new FlowUIClient({ baseUrl: 'https://p/flows', embedId: 'e1' });
        await embed.open();
        await expect(embed.createShare()).rejects.toThrow(/share requires flowId/);
    });
});
