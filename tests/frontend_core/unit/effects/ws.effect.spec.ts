/**
 * ws.effect: Centrifugo RPC + publication + connect/disconnect lifecycle.
 *
 * Модуль — singleton. Между тестами: _resetPlatformWsForTests().
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import {
    platformWs,
    createPlatformWsEffect,
    WsTransportError,
    _resetPlatformWsForTests,
    _setCentrifugeForTests,
} from '@platform/lib/events/effects/ws.effect.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
import { installDomShim } from '../../helpers/dom-shim.js';
import { buildCtx, type DispatchedRecord } from '../../helpers/bus-fixtures.js';
import type { PlatformEvent } from '@platform/lib/events/contract.js';
import { prop } from '../../helpers/prop.js';

function sessionJwt(userId: string, companyId: string) {
    const header = Buffer.from(JSON.stringify({ alg: 'HS256', typ: 'JWT' })).toString('base64url');
    const payload = Buffer.from(JSON.stringify({
        user_id: userId,
        company_id: companyId,
        iss: 'platform.session',
        token_type: 'session',
    })).toString('base64url');
    return `${header}.${payload}.sig`;
}

class MockUnauthorizedError extends Error {
    constructor() {
        super('unauthorized');
        this.name = 'UnauthorizedError';
    }
}

type CentrifugeHandler = (data: unknown) => void;

class MockCentrifuge {
    static instances: MockCentrifuge[] = [];

    endpoint: string;
    opts: unknown;
    handlers: Record<string, CentrifugeHandler>;
    state: string;
    rpcCalls: Array<{ method: string; data: Record<string, unknown> }>;

    constructor(endpoint: string, opts: unknown) {
        this.endpoint = endpoint;
        this.opts = opts;
        this.handlers = {};
        this.state = 'disconnected';
        this.rpcCalls = [];
        MockCentrifuge.instances.push(this);
    }

    on(event: string, cb: CentrifugeHandler) {
        this.handlers[event] = cb;
    }

    connect() {
        this.state = 'connected';
        this.handlers.connected?.({});
    }

    disconnect() {
        this.state = 'disconnected';
        this.handlers.disconnected?.({ code: 0, reason: 'client' });
    }

    rpc(method: string, data: Record<string, unknown>) {
        this.rpcCalls.push({ method, data });
        return Promise.resolve({ accepted: true, event_id: data.event_id });
    }

    emitPublication(data: unknown) {
        this.handlers.publication?.({ channel: 'user:u1', data });
    }

    static latest(): MockCentrifuge {
        const inst = MockCentrifuge.instances[MockCentrifuge.instances.length - 1];
        if (!inst) {
            throw new Error('MockCentrifuge: no instances');
        }
        return inst;
    }

    static reset() {
        MockCentrifuge.instances = [];
    }
}

let dom: ReturnType<typeof installDomShim>;

beforeEach(() => {
    dom = installDomShim();
    document.cookie = `auth_token=${sessionJwt('u1', 'c1')}`;
    vi.stubGlobal('fetch', vi.fn(async () => ({
        ok: false,
        status: 404,
        json: async () => ({}),
    })));
    vi.useFakeTimers();
    MockCentrifuge.reset();
    Reflect.apply(_setCentrifugeForTests, null, [MockCentrifuge, MockUnauthorizedError]);
    _resetPlatformWsForTests();
    Reflect.apply(_setCentrifugeForTests, null, [MockCentrifuge, MockUnauthorizedError]);
});
afterEach(() => {
    _resetPlatformWsForTests();
    vi.useRealTimers();
    MockCentrifuge.reset();
    dom.uninstall();
});

const ev = (type: string, payload: unknown = null): PlatformEvent => ({
    id: `id_${type}`,
    type,
    payload,
    meta: { ts: 0, source: 'system', causation_id: null, correlation_id: null, trace_id: null },
});

async function _connect(dispatched: DispatchedRecord[] = []) {
    const effect = createPlatformWsEffect();
    await effect(ev(CoreEvents.AUTH_USER_LOADED), buildCtx(() => ({}), dispatched));
    return { effect, ctx: buildCtx(() => ({}), dispatched), dispatched };
}

describe('platformWs.request: contract', () => {
    it('требует opts', () => {
        expect(() => Reflect.apply(platformWs.request, platformWs, [null])).toThrow(/opts/);
    });

    it('требует type, timeoutMs, expectedSucceeded, expectedFailed', () => {
        expect(() => Reflect.apply(platformWs.request, platformWs, [{}])).toThrow(/type/);
        expect(() => Reflect.apply(platformWs.request, platformWs, [{ type: 'a/b/c' }])).toThrow(/timeoutMs/);
        expect(() => Reflect.apply(platformWs.request, platformWs, [{ type: 'a/b/c', timeoutMs: 100 }])).toThrow(/expectedSucceeded/);
        expect(() => Reflect.apply(platformWs.request, platformWs, [{ type: 'a/b/c', timeoutMs: 100, expectedSucceeded: 'a/b/d' }])).toThrow(/expectedFailed/);
    });

    it('валидирует имена событий', () => {
        expect(() => Reflect.apply(platformWs.request, platformWs, [{ type: 'BadName', timeoutMs: 100, expectedSucceeded: 'a/b/c', expectedFailed: 'a/b/d' }])).toThrow();
    });

    it('до connect фрейм откладывается и reject ws_timeout если соединение не появилось', async () => {
        const promise = Reflect.apply(platformWs.request, platformWs, [{
            type: 'svc/cmd/requested', payload: null, timeoutMs: 100,
            expectedSucceeded: 'svc/cmd/succeeded', expectedFailed: 'svc/cmd/failed',
        }]);
        const expectation = expect(promise).rejects.toMatchObject({ code: 'ws_timeout' });
        await vi.advanceTimersByTimeAsync(5_001);
        await expectation;
    });

    it('после AUTH_LOGGED_OUT pre-connect reject как ws_disconnected', async () => {
        const dispatched: DispatchedRecord[] = [];
        const effect = createPlatformWsEffect();
        const ctx = buildCtx(() => ({}), dispatched);
        await effect(ev(CoreEvents.AUTH_USER_LOADED), ctx);
        await effect(ev(CoreEvents.AUTH_LOGGED_OUT), ctx);
        await expect(Reflect.apply(platformWs.request, platformWs, [{
            type: 'svc/cmd/requested', payload: null, timeoutMs: 100,
            expectedSucceeded: 'svc/cmd/succeeded', expectedFailed: 'svc/cmd/failed',
        }])).rejects.toMatchObject({ code: 'ws_disconnected' });
    });
});

describe('platformWs.request: pre-connect queue', () => {
    it('команда до AUTH_USER_LOADED уходит RPC сразу после connect', async () => {
        const dispatched: DispatchedRecord[] = [];
        const effect = createPlatformWsEffect();
        const ctx = buildCtx(() => ({}), dispatched);

        const promise = platformWs.request({
            type: 'svc/cmd/requested', payload: { x: 1 }, timeoutMs: 1000,
            expectedSucceeded: 'svc/cmd/succeeded', expectedFailed: 'svc/cmd/failed',
        });
        await effect(ev(CoreEvents.AUTH_USER_LOADED), ctx);

        const client = MockCentrifuge.latest();
        expect(client.rpcCalls).toHaveLength(1);
        const sent = client.rpcCalls[0];
        if (sent === undefined) {
            throw new Error('rpcCalls[0] required');
        }
        expect(sent.method).toBe('platform.event');
        expect(sent.data.type).toBe('svc/cmd/requested');
        expect(sent.data.payload).toEqual({ x: 1 });
        expect(sent.data.company_id).toBe('c1');
        expect(prop(sent.data.meta, 'namespace')).toBe('default');
        client.emitPublication({
            event_id: 'e_reply',
            type: 'svc/cmd/succeeded',
            company_id: 'c1',
            payload: { ok: true },
            meta: { ts: 0, source: 'system', causation_id: prop(prop(sent, 'data'), 'event_id') },
        });
        await expect(promise).resolves.toEqual({ ok: true });
    });

    it('несколько pre-connect команд уходят в порядке очереди', async () => {
        const dispatched: DispatchedRecord[] = [];
        const effect = createPlatformWsEffect();
        const ctx = buildCtx(() => ({}), dispatched);

        const p1 = platformWs.request({
            type: 'svc/cmd/requested', payload: { i: 1 }, timeoutMs: 1000,
            expectedSucceeded: 'svc/cmd/succeeded', expectedFailed: 'svc/cmd/failed',
        });
        const p2 = platformWs.request({
            type: 'svc/cmd/requested', payload: { i: 2 }, timeoutMs: 1000,
            expectedSucceeded: 'svc/cmd/succeeded', expectedFailed: 'svc/cmd/failed',
        });
        await effect(ev(CoreEvents.AUTH_USER_LOADED), ctx);

        const client = MockCentrifuge.latest();
        expect(client.rpcCalls).toHaveLength(2);
        expect(prop(client.rpcCalls[0]?.data, 'payload')).toEqual({ i: 1 });
        expect(prop(client.rpcCalls[1]?.data, 'payload')).toEqual({ i: 2 });

        client.emitPublication({
            type: 'svc/cmd/succeeded',
            payload: { n: 1 },
            meta: { causation_id: prop(client.rpcCalls[0]?.data, 'event_id') },
        });
        client.emitPublication({
            type: 'svc/cmd/succeeded',
            payload: { n: 2 },
            meta: { causation_id: prop(client.rpcCalls[1]?.data, 'event_id') },
        });
        await expect(p1).resolves.toEqual({ n: 1 });
        await expect(p2).resolves.toEqual({ n: 2 });
    });
});

describe('platformWs.request: round-trip', () => {
    it('успех → resolve с payload', async () => {
        await _connect();
        const promise = platformWs.request({
            type: 'svc/cmd/requested', payload: { x: 1 }, timeoutMs: 1000,
            expectedSucceeded: 'svc/cmd/succeeded', expectedFailed: 'svc/cmd/failed',
        });
        const client = MockCentrifuge.latest();
        expect(client.rpcCalls).toHaveLength(1);
        const sent = client.rpcCalls[0]?.data;
        if (sent === undefined) {
            throw new Error('rpcCalls[0].data required');
        }
        expect(prop(sent, 'type')).toBe('svc/cmd/requested');
        expect(prop(sent, 'payload')).toEqual({ x: 1 });
        client.emitPublication({
            type: 'svc/cmd/succeeded',
            payload: { ok: true },
            meta: { causation_id: prop(sent, 'event_id') },
        });
        await expect(promise).resolves.toEqual({ ok: true });
    });

    it('failed → reject с WsTransportError', async () => {
        await _connect();
        const promise = Reflect.apply(platformWs.request, platformWs, [{
            type: 'svc/cmd/requested', payload: null, timeoutMs: 1000,
            expectedSucceeded: 'svc/cmd/succeeded', expectedFailed: 'svc/cmd/failed',
        }]);
        const client = MockCentrifuge.latest();
        const sent = client.rpcCalls[0]?.data;
        if (sent === undefined) {
            throw new Error('rpcCalls[0].data required');
        }
        client.emitPublication({
            type: 'svc/cmd/failed',
            payload: { error_code: 'invalid', error_detail: 'bad' },
            meta: { causation_id: prop(sent, 'event_id') },
        });
        await expect(promise).rejects.toMatchObject({ name: 'WsTransportError', code: 'invalid', message: 'invalid' });
    });

    it('таймаут без terminal → reject ws_timeout, не *_failed', async () => {
        await _connect();
        const promise = Reflect.apply(platformWs.request, platformWs, [{
            type: 'svc/cmd/requested', payload: null, timeoutMs: 100,
            expectedSucceeded: 'svc/cmd/succeeded', expectedFailed: 'svc/cmd/failed',
        }]);
        const expectation = expect(promise).rejects.toMatchObject({ code: 'ws_timeout' });
        await vi.advanceTimersByTimeAsync(150);
        await expectation;
        expect(globalThis.fetch).toHaveBeenCalled();
    });

    it('disconnect → reject всех pending как ws_disconnected', async () => {
        await _connect();
        const promise = Reflect.apply(platformWs.request, platformWs, [{
            type: 'svc/cmd/requested', payload: null, timeoutMs: 5000,
            expectedSucceeded: 'svc/cmd/succeeded', expectedFailed: 'svc/cmd/failed',
        }]);
        const client = MockCentrifuge.latest();
        client.disconnect();
        await expect(promise).rejects.toMatchObject({ code: 'ws_disconnected' });
    });

    it('ошибка rpc → reject ws_disconnected, не ждать timeout', async () => {
        await _connect();
        const client = MockCentrifuge.latest();
        client.rpc = () => Promise.reject(new Error('rpc down'));
        await expect(Reflect.apply(platformWs.request, platformWs, [{
            type: 'svc/cmd/requested', payload: null, timeoutMs: 5000,
            expectedSucceeded: 'svc/cmd/succeeded', expectedFailed: 'svc/cmd/failed',
        }])).rejects.toMatchObject({ code: 'ws_disconnected', message: 'rpc down' });
    });
});

describe('ws.effect: push frames', () => {
    it('publication диспатчится в bus', async () => {
        const dispatched: DispatchedRecord[] = [];
        await _connect(dispatched);
        const client = MockCentrifuge.latest();
        client.emitPublication({ type: 'sync/message/created', payload: { id: 'm1' }, meta: {} });
        const pushed = dispatched.find((d) => d.type === 'sync/message/created');
        expect(pushed?.payload).toEqual({ id: 'm1' });
    });

    it('эхо *_requested команды не диспатчится в bus и не дублирует RPC', async () => {
        const dispatched: DispatchedRecord[] = [];
        await _connect(dispatched);
        const promise = platformWs.request({
            type: 'svc/cmd/item_requested', payload: { x: 1 }, timeoutMs: 1000,
            expectedSucceeded: 'svc/cmd/item_succeeded', expectedFailed: 'svc/cmd/item_failed',
        });
        const client = MockCentrifuge.latest();
        const sent = client.rpcCalls[0]?.data;
        if (sent === undefined) {
            throw new Error('rpcCalls[0].data required');
        }
        client.emitPublication({
            event_id: prop(sent, 'event_id'),
            type: 'svc/cmd/item_requested',
            company_id: 'c1',
            payload: prop(sent, 'payload'),
            meta: { ts: 0, source: 'ws', actor_user_id: 'u1', causation_id: prop(sent, 'event_id') },
        });
        expect(dispatched.find((d) => d.type === 'svc/cmd/item_requested')).toBeUndefined();
        expect(client.rpcCalls).toHaveLength(1);
        expect(dispatched.find((d) => d.type === CoreEvents.WS_FRAME_RECEIVED)).toBeDefined();
        client.emitPublication({
            type: 'svc/cmd/item_succeeded',
            payload: { ok: true },
            meta: { causation_id: prop(sent, 'event_id') },
        });
        await expect(promise).resolves.toEqual({ ok: true });
    });

    it('publication с невалидным типом бросает и не попадает в bus', async () => {
        const dispatched: DispatchedRecord[] = [];
        await _connect(dispatched);
        const client = MockCentrifuge.latest();
        expect(() => client.emitPublication({ type: 'NotValid', payload: null })).toThrow(/violates contract/);
        expect(dispatched.find((d) => d.type === 'NotValid')).toBeUndefined();
    });
});

describe('ws.effect: lifecycle', () => {
    it('AUTH_LOGGED_OUT закрывает клиент', async () => {
        const dispatched: DispatchedRecord[] = [];
        const effect = createPlatformWsEffect();
        const ctx = buildCtx(() => ({}), dispatched);
        await effect(ev(CoreEvents.AUTH_USER_LOADED), ctx);
        expect(platformWs.isOpen()).toBe(true);
        await effect(ev(CoreEvents.AUTH_LOGGED_OUT), ctx);
        expect(platformWs.isOpen()).toBe(false);
    });
});
