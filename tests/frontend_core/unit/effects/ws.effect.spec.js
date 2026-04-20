/**
 * ws.effect: WebSocket request-reply machinery + connect/disconnect lifecycle.
 *
 * Особенность: модуль ws.effect — singleton с module-level state. Между тестами
 * вызываем _resetPlatformWsForTests().
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import {
    platformWs,
    createPlatformWsEffect,
    WsTransportError,
    _resetPlatformWsForTests,
} from '@platform/lib/events/effects/ws.effect.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
import { installMockWebSocket, MockWebSocket } from '../../helpers/mock-ws.js';
import { installDomShim } from '../../helpers/dom-shim.js';
import { buildCtx } from '../../helpers/bus-fixtures.js';

let dom;
let wsHandle;

beforeEach(() => {
    dom = installDomShim();
    wsHandle = installMockWebSocket({ openSync: true });
    vi.useFakeTimers();
    _resetPlatformWsForTests();
});
afterEach(() => {
    _resetPlatformWsForTests();
    vi.useRealTimers();
    wsHandle.uninstall();
    dom.uninstall();
});

const ev = (type, payload = null) => ({ id: `id_${type}`, type, payload, meta: { ts: 0, source: 'system' } });

async function _connect(dispatched = []) {
    const effect = createPlatformWsEffect({ baseUrl: '/svc' });
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
        const effect = createPlatformWsEffect({ baseUrl: '/svc' });
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
    it('фрейм отправленный до AUTH_USER_LOADED уходит сразу после onopen', async () => {
        const dispatched = [];
        const effect = createPlatformWsEffect({ baseUrl: '/svc' });
        const ctx = buildCtx(() => ({}), dispatched);

        const promise = platformWs.request({
            type: 'svc/cmd/requested', payload: { x: 1 }, timeoutMs: 1000,
            expectedSucceeded: 'svc/cmd/succeeded', expectedFailed: 'svc/cmd/failed',
        });
        await effect(ev(CoreEvents.AUTH_USER_LOADED), ctx);

        const ws = wsHandle.latest();
        expect(ws.sent).toHaveLength(1);
        const sent = JSON.parse(ws.sent[0]);
        expect(sent.type).toBe('svc/cmd/requested');
        expect(sent.payload).toEqual({ x: 1 });
        ws.serverFrame({ request_id: sent.request_id, type: 'svc/cmd/succeeded', payload: { ok: true } });
        await expect(promise).resolves.toEqual({ ok: true });
    });

    it('несколько pre-connect фреймов отправляются в порядке очереди', async () => {
        const dispatched = [];
        const effect = createPlatformWsEffect({ baseUrl: '/svc' });
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

        const ws = wsHandle.latest();
        expect(ws.sent).toHaveLength(2);
        const sent1 = JSON.parse(ws.sent[0]);
        const sent2 = JSON.parse(ws.sent[1]);
        expect(sent1.payload).toEqual({ i: 1 });
        expect(sent2.payload).toEqual({ i: 2 });

        ws.serverFrame({ request_id: sent1.request_id, type: 'svc/cmd/succeeded', payload: { n: 1 } });
        ws.serverFrame({ request_id: sent2.request_id, type: 'svc/cmd/succeeded', payload: { n: 2 } });
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
        const ws = wsHandle.latest();
        expect(ws.sent).toHaveLength(1);
        const sent = JSON.parse(ws.sent[0]);
        expect(sent.type).toBe('svc/cmd/requested');
        expect(sent.payload).toEqual({ x: 1 });
        ws.serverFrame({ request_id: sent.request_id, type: 'svc/cmd/succeeded', payload: { ok: true } });
        await expect(promise).resolves.toEqual({ ok: true });
    });

    it('failed → reject с WsTransportError', async () => {
        await _connect();
        const promise = platformWs.request({
            type: 'svc/cmd/requested', payload: null, timeoutMs: 1000,
            expectedSucceeded: 'svc/cmd/succeeded', expectedFailed: 'svc/cmd/failed',
        });
        const ws = wsHandle.latest();
        const sent = JSON.parse(ws.sent[0]);
        ws.serverFrame({ request_id: sent.request_id, type: 'svc/cmd/failed', payload: { error_code: 'invalid', error_detail: 'bad' } });
        await expect(promise).rejects.toMatchObject({ name: 'WsTransportError', code: 'invalid', message: 'bad' });
    });

    it('неожиданный reply-type → reject', async () => {
        await _connect();
        const promise = platformWs.request({
            type: 'svc/cmd/requested', payload: null, timeoutMs: 1000,
            expectedSucceeded: 'svc/cmd/succeeded', expectedFailed: 'svc/cmd/failed',
        });
        const ws = wsHandle.latest();
        const sent = JSON.parse(ws.sent[0]);
        ws.serverFrame({ request_id: sent.request_id, type: 'svc/cmd/something_else', payload: {} });
        await expect(promise).rejects.toMatchObject({ code: 'ws_unexpected_reply' });
    });

    it('таймаут → reject ws_timeout', async () => {
        await _connect();
        const promise = platformWs.request({
            type: 'svc/cmd/requested', payload: null, timeoutMs: 100,
            expectedSucceeded: 'svc/cmd/succeeded', expectedFailed: 'svc/cmd/failed',
        });
        const expectation = expect(promise).rejects.toMatchObject({ code: 'ws_timeout' });
        await vi.advanceTimersByTimeAsync(150);
        await expectation;
    });

    it('disconnect → reject всех pending как ws_disconnected', async () => {
        await _connect();
        const promise = platformWs.request({
            type: 'svc/cmd/requested', payload: null, timeoutMs: 5000,
            expectedSucceeded: 'svc/cmd/succeeded', expectedFailed: 'svc/cmd/failed',
        });
        const ws = wsHandle.latest();
        ws.serverClose(1006, 'lost');
        await expect(promise).rejects.toMatchObject({ code: 'ws_disconnected' });
    });
});

describe('ws.effect: push frames', () => {
    it('push (без request_id) диспатчится в bus', async () => {
        const dispatched = [];
        await _connect(dispatched);
        const ws = wsHandle.latest();
        ws.serverFrame({ type: 'sync/message/created', payload: { id: 'm1' } });
        const pushed = dispatched.find((d) => d.type === 'sync/message/created');
        expect(pushed.payload).toEqual({ id: 'm1' });
    });

    it('push с невалидным типом игнорируется без падения', async () => {
        const dispatched = [];
        await _connect(dispatched);
        const ws = wsHandle.latest();
        const before = dispatched.length;
        ws.serverFrame({ type: 'NotValid', payload: null });
        // не упало; в bus попадает только WS_FRAME_RECEIVED
        expect(dispatched.length).toBeGreaterThan(before);
        expect(dispatched.find((d) => d.type === 'NotValid')).toBeUndefined();
    });
});

describe('ws.effect: lifecycle', () => {
    it('AUTH_LOGGED_OUT закрывает сокет', async () => {
        const dispatched = [];
        const effect = createPlatformWsEffect({ baseUrl: '/svc' });
        const ctx = buildCtx(() => ({}), dispatched);
        await effect(ev(CoreEvents.AUTH_USER_LOADED), ctx);
        expect(wsHandle.latest().readyState).toBe(MockWebSocket.OPEN);
        await effect(ev(CoreEvents.AUTH_LOGGED_OUT), ctx);
        expect(platformWs.isOpen()).toBe(false);
    });
});
