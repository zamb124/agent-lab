import { describe, it, expect, afterEach, vi } from 'vitest';
import {
    isTransportError,
    normalizeRestMirrorCollection,
    normalizeRestMirrorSingle,
    normalizeTransport,
    normalizeWsTimeout,
    transportRequest,
} from '@platform/lib/events/factories/_transport.js';
import { HttpError } from '@platform/lib/events/http.js';
import { platformWs, WsTransportError } from '@platform/lib/events/effects/ws.effect.js';

afterEach(() => {
    vi.restoreAllMocks();
});

describe('factory transport helpers', () => {
    it('normalizeTransport', () => {
        expect(normalizeTransport(undefined, 'op')).toBe('http');
        expect(normalizeTransport(null, 'op')).toBe('http');
        expect(normalizeTransport('ws', 'op')).toBe('ws');
        expect(() => Reflect.apply(normalizeTransport, null, ['grpc', 'op'])).toThrow(/transport/);
    });

    it('normalizeWsTimeout', () => {
        expect(normalizeWsTimeout(undefined, 'http', 'op')).toBeNull();
        expect(normalizeWsTimeout(1500, 'ws', 'op')).toBe(1500);
        expect(() => Reflect.apply(normalizeWsTimeout, null, [0, 'ws', 'op'])).toThrow(/wsTimeoutMs/);
        expect(() => Reflect.apply(normalizeWsTimeout, null, [-1, 'ws', 'op'])).toThrow(/wsTimeoutMs/);
    });

    it('normalizeRestMirrorSingle', () => {
        expect(normalizeRestMirrorSingle({ method: 'get', path: '/x' }, 'op')).toEqual({
            method: 'GET',
            path: '/x',
        });
        expect(() => Reflect.apply(normalizeRestMirrorSingle, null, [null, 'op'])).toThrow(/restMirror is required/);
        expect(() => Reflect.apply(normalizeRestMirrorSingle, null, [{ method: 'GET' }, 'op'])).toThrow(/path/);
    });

    it('normalizeRestMirrorCollection', () => {
        const mirror = normalizeRestMirrorCollection(
            {
                list: { method: 'GET', path: '/items' },
                create: { method: 'POST', path: '/items' },
            },
            ['list', 'create'],
            undefined,
            'op',
        );
        expect(mirror.list?.method).toBe('GET');
        expect(() => Reflect.apply(normalizeRestMirrorCollection, null, [{}, ['list'], null, 'op'])).toThrow(/restMirror.list/);
        expect(() => Reflect.apply(normalizeRestMirrorCollection, null, [null, ['list'], null, 'op'])).toThrow(/restMirror is required/);
    });

    it('isTransportError', () => {
        expect(isTransportError(new HttpError('x', 500, {}))).toBe(true);
        expect(isTransportError(new WsTransportError('timeout', 'ws_timeout'))).toBe(true);
        expect(isTransportError(new Error('x'))).toBe(false);
    });
});

describe('transportRequest', () => {
    it('требует opts и WS-поля', async () => {
        await expect(Reflect.apply(transportRequest, null, [null])).rejects.toThrow(/opts object required/);
        await expect(Reflect.apply(transportRequest, null, [{ transport: 'ws' }])).rejects.toThrow(/commandType/);
        await expect(transportRequest({
            transport: 'ws',
            commandType: 'svc/x/requested',
        })).rejects.toThrow(/expectedSucceeded/);
        await expect(transportRequest({
            transport: 'ws',
            commandType: 'svc/x/requested',
            expectedSucceeded: 'svc/x/succeeded',
        })).rejects.toThrow(/expectedFailed/);
    });

    it('HTTP без method/url — throw', async () => {
        await expect(Reflect.apply(transportRequest, null, [{ transport: 'http' }])).rejects.toThrow(/method and opts.url/);
    });

    it('WS делегирует в platformWs.request', async () => {
        const spy = vi.spyOn(platformWs, 'request').mockResolvedValue({ ok: true });
        const result = await transportRequest({
            transport: 'ws',
            commandType: 'svc/demo/requested',
            expectedSucceeded: 'svc/demo/succeeded',
            expectedFailed: 'svc/demo/failed',
            payload: { n: 1 },
            wsTimeoutMs: 8000,
            causationEventId: 'e1',
        });
        expect(result).toEqual({ ok: true });
        expect(spy).toHaveBeenCalledWith({
            type: 'svc/demo/requested',
            payload: { n: 1 },
            timeoutMs: 8000,
            causationEventId: 'e1',
            expectedSucceeded: 'svc/demo/succeeded',
            expectedFailed: 'svc/demo/failed',
        });
    });
});
