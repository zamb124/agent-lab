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
import { buildCtx } from '../../helpers/bus-fixtures.js';

function sessionJwt(userId, companyId) {
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

class MockCentrifuge {
    static instances = [];

    constructor(endpoint, opts) {
        this.endpoint = endpoint;
        this.opts = opts;
        this.handlers = {};
        this.state = 'disconnected';
        this.rpcCalls = [];
        MockCentrifuge.instances.push(this);
    }

    on(event, cb) {
        this.handlers[event] = cb;
    }

    connect() {
        this.state = 'connected';
        if (this.handlers.connected) {
            this.handlers.connected({});
        }
    }

    disconnect() {
        this.state = 'disconnected';
        if (this.handlers.disconnected) {
            this.handlers.disconnected({ code: 0, reason: 'client' });
        }
    }

    rpc(method, data) {
        this.rpcCalls.push({ method, data });
        return Promise.resolve({ accepted: true, event_id: data.event_id });
    }

    emitPublication(data) {
        if (this.handlers.publication) {
            this.handlers.publication({ channel: 'user:u1', data });
        }
    }

    static latest() {
        return this.instances[this.instances.length - 1];
    }

    static reset() {
        this.instances = [];
    }
}

let dom;

beforeEach(() => {
    dom = installDomShim();
    document.cookie = `auth_token=${sessionJwt('u1', 'c1')}`;
    globalThis.fetch = vi.fn(async () => ({
        ok: false,
        status: 404,
        json: async () => ({}),
    }));
    vi.useFakeTimers();
    MockCentrifuge.reset();
    _setCentrifugeForTests(MockCentrifuge, MockUnauthorizedError);
    _resetPlatformWsForTests();
    _setCentrifugeForTests(MockCentrifuge, MockUnauthorizedError);
});
afterEach(() => {
    _resetPlatformWsForTests();
    vi.useRealTimers();
    MockCentrifuge.reset();
    dom.uninstall();
});

const ev = (type, payload = null) => ({ id: `id_${type}`, type, payload, meta: { ts: 0, source: 'system' } });

async function _connect(dispatched = []) {
    const effect = createPlatformWsEffect();
    await effect(ev(CoreEvents.AUTH_USER_LOADED), buildCtx(() => ({}), dispatched));
    return { effect, ctx: buildCtx(() => ({}), dispatched), dispatched };
}

describe('platformWs.request: contract', () => {
    it('требует opts', () => {
        expect(() => platformWs.request(null)).toThrow(/opts/);
    });

    it('требует type, timeoutMs, expectedSucceeded, expectedFailed', () => {
        expect(() => platformWs.request({})).toThrow(/type/);
        expect(() => platformWs.request({ type: 'a/b/c' })).toThrow(/timeoutMs/);
        expect(() => platformWs.request({ type: 'a/b/c', timeoutMs: 100 })).toThrow(/expectedSucceeded/);
        expect(() => platformWs.request({ type: 'a/b/c', timeoutMs: 100, expectedSucceeded: 'a/b/d' })).toThrow(/expectedFailed/);
    });

    it('валидирует имена событий', () => {
        expect(() => platformWs.request({ type: 'BadName', timeoutMs: 100, expectedSucceeded: 'a/b/c', expectedFailed: 'a/b/d' })).toThrow();
    });

    it('до connect фрейм откладывается и reject ws_timeout если соединение не появилось', async () => {
        const promise = platformWs.request({
            type: 'svc/cmd/requested', payload: null, timeoutMs: 100,
            expectedSucceeded: 'svc/cmd/succeeded', expectedFailed: 'svc/cmd/failed',
        });
        const expectation = expect(promise).rejects.toMatchObject({ code: 'ws_timeout' });
        await vi.advanceTimersByTimeAsync(5_001);
        await expectation;
    });

    it('после AUTH_LOGGED_OUT pre-connect reject как ws_disconnected', async () => {
        const dispatched = [];
        const effect = createPlatformWsEffect();
        const ctx = buildCtx(() => ({}), dispatched);
        await effect(ev(CoreEvents.AUTH_USER_LOADED), ctx);
        await effect(ev(CoreEvents.AUTH_LOGGED_OUT), ctx);
        await expect(platformWs.request({
            type: 'svc/cmd/requested', payload: null, timeoutMs: 100,
            expectedSucceeded: 'svc/cmd/succeeded', expectedFailed: 'svc/cmd/failed',
        })).rejects.toMatchObject({ code: 'ws_disconnected' });
    });
});

describe('platformWs.request: pre-connect queue', () => {
    it('команда до AUTH_USER_LOADED уходит RPC сразу после connect', async () => {
        const dispatched = [];
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
        expect(sent.method).toBe('platform.event');
        expect(sent.data.type).toBe('svc/cmd/requested');
        expect(sent.data.payload).toEqual({ x: 1 });
        expect(sent.data.company_id).toBe('c1');
        expect(sent.data.meta.namespace).toBe('default');
        client.emitPublication({
            event_id: 'e_reply',
            type: 'svc/cmd/succeeded',
            company_id: 'c1',
            payload: { ok: true },
            meta: { ts: 0, source: 'system', causation_id: sent.data.event_id },
        });
        await expect(promise).resolves.toEqual({ ok: true });
    });

    it('несколько pre-connect команд уходят в порядке очереди', async () => {
        const dispatched = [];
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
        expect(client.rpcCalls[0].data.payload).toEqual({ i: 1 });
        expect(client.rpcCalls[1].data.payload).toEqual({ i: 2 });

        client.emitPublication({
            type: 'svc/cmd/succeeded',
            payload: { n: 1 },
            meta: { causation_id: client.rpcCalls[0].data.event_id },
        });
        client.emitPublication({
            type: 'svc/cmd/succeeded',
            payload: { n: 2 },
            meta: { causation_id: client.rpcCalls[1].data.event_id },
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
        const sent = client.rpcCalls[0].data;
        expect(sent.type).toBe('svc/cmd/requested');
        expect(sent.payload).toEqual({ x: 1 });
        client.emitPublication({
            type: 'svc/cmd/succeeded',
            payload: { ok: true },
            meta: { causation_id: sent.event_id },
        });
        await expect(promise).resolves.toEqual({ ok: true });
    });

    it('failed → reject с WsTransportError', async () => {
        await _connect();
        const promise = platformWs.request({
            type: 'svc/cmd/requested', payload: null, timeoutMs: 1000,
            expectedSucceeded: 'svc/cmd/succeeded', expectedFailed: 'svc/cmd/failed',
        });
        const client = MockCentrifuge.latest();
        const sent = client.rpcCalls[0].data;
        client.emitPublication({
            type: 'svc/cmd/failed',
            payload: { error_code: 'invalid', error_detail: 'bad' },
            meta: { causation_id: sent.event_id },
        });
        await expect(promise).rejects.toMatchObject({ name: 'WsTransportError', code: 'invalid', message: 'invalid' });
    });

    it('таймаут без terminal → reject ws_timeout, не *_failed', async () => {
        await _connect();
        const promise = platformWs.request({
            type: 'svc/cmd/requested', payload: null, timeoutMs: 100,
            expectedSucceeded: 'svc/cmd/succeeded', expectedFailed: 'svc/cmd/failed',
        });
        const expectation = expect(promise).rejects.toMatchObject({ code: 'ws_timeout' });
        await vi.advanceTimersByTimeAsync(150);
        await expectation;
        expect(globalThis.fetch).toHaveBeenCalled();
    });

    it('disconnect → reject всех pending как ws_disconnected', async () => {
        await _connect();
        const promise = platformWs.request({
            type: 'svc/cmd/requested', payload: null, timeoutMs: 5000,
            expectedSucceeded: 'svc/cmd/succeeded', expectedFailed: 'svc/cmd/failed',
        });
        const client = MockCentrifuge.latest();
        client.disconnect();
        await expect(promise).rejects.toMatchObject({ code: 'ws_disconnected' });
    });

    it('ошибка rpc → reject ws_disconnected, не ждать timeout', async () => {
        await _connect();
        const client = MockCentrifuge.latest();
        client.rpc = () => Promise.reject(new Error('rpc down'));
        await expect(platformWs.request({
            type: 'svc/cmd/requested', payload: null, timeoutMs: 5000,
            expectedSucceeded: 'svc/cmd/succeeded', expectedFailed: 'svc/cmd/failed',
        })).rejects.toMatchObject({ code: 'ws_disconnected', message: 'rpc down' });
    });
});

describe('ws.effect: push frames', () => {
    it('publication диспатчится в bus', async () => {
        const dispatched = [];
        await _connect(dispatched);
        const client = MockCentrifuge.latest();
        client.emitPublication({ type: 'sync/message/created', payload: { id: 'm1' }, meta: {} });
        const pushed = dispatched.find((d) => d.type === 'sync/message/created');
        expect(pushed.payload).toEqual({ id: 'm1' });
    });

    it('publication с невалидным типом игнорируется без падения', async () => {
        const dispatched = [];
        await _connect(dispatched);
        const client = MockCentrifuge.latest();
        const before = dispatched.length;
        client.emitPublication({ type: 'NotValid', payload: null });
        expect(dispatched.length).toBeGreaterThan(before);
        expect(dispatched.find((d) => d.type === 'NotValid')).toBeUndefined();
    });
});

describe('ws.effect: lifecycle', () => {
    it('AUTH_LOGGED_OUT закрывает клиент', async () => {
        const dispatched = [];
        const effect = createPlatformWsEffect();
        const ctx = buildCtx(() => ({}), dispatched);
        await effect(ev(CoreEvents.AUTH_USER_LOADED), ctx);
        expect(platformWs.isOpen()).toBe(true);
        await effect(ev(CoreEvents.AUTH_LOGGED_OUT), ctx);
        expect(platformWs.isOpen()).toBe(false);
    });
});
