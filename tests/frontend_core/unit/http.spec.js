/**
 * httpRequest / HttpError: контракт low-level HTTP-клиента.
 *
 * Используем mock-fetch — minimal Response-shim, без MSW (Node-режим).
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { httpRequest, HttpError } from '@platform/lib/events/http.js';
import { installFetchMock } from '../helpers/mock-fetch.js';

let fetchMock;

beforeEach(() => {
    fetchMock = installFetchMock();
});
afterEach(() => fetchMock.uninstall());

describe('httpRequest: success', () => {
    it('GET возвращает JSON', async () => {
        fetchMock.respondJson('GET', '/api/items', { items: [1, 2, 3] });
        const result = await httpRequest({ method: 'GET', url: '/api/items' });
        expect(result).toEqual({ items: [1, 2, 3] });
    });

    it('добавляет query-string', async () => {
        fetchMock.respondJson('GET', '/api/items?a=1&b=hello', { ok: true });
        const result = await httpRequest({ method: 'GET', url: '/api/items', query: { a: 1, b: 'hello', c: null, d: undefined } });
        expect(result).toEqual({ ok: true });
        expect(fetchMock.calls[0].url).toBe('/api/items?a=1&b=hello');
    });

    it('POST с body сериализует JSON', async () => {
        fetchMock.respondJson('POST', '/api/items', { ok: true });
        await httpRequest({ method: 'POST', url: '/api/items', body: { foo: 'bar' } });
        const init = fetchMock.calls[0].init;
        expect(init.body).toBe('{"foo":"bar"}');
        expect(init.headers['Content-Type']).toBe('application/json');
    });

    it('204 NO CONTENT → {}', async () => {
        fetchMock.respondStatus('DELETE', '/api/items/1', 204);
        const result = await httpRequest({ method: 'DELETE', url: '/api/items/1' });
        expect(result).toEqual({});
    });

    it('пустое тело → {}', async () => {
        fetchMock.respondText('GET', '/api/empty', '', 200, 'application/json');
        const result = await httpRequest({ method: 'GET', url: '/api/empty' });
        expect(result).toEqual({});
    });

    it('text/plain возвращает строку', async () => {
        fetchMock.respondText('GET', '/api/text', 'hello world', 200, 'text/plain');
        const result = await httpRequest({ method: 'GET', url: '/api/text' });
        expect(result).toBe('hello world');
    });

    it('text/markdown возвращает строку', async () => {
        fetchMock.respondText('GET', '/api/md', '# Title', 200, 'text/markdown');
        const result = await httpRequest({ method: 'GET', url: '/api/md' });
        expect(result).toBe('# Title');
    });

    it('текст начинающийся с { парсится как JSON', async () => {
        fetchMock.respondText('GET', '/api/raw', '{"a":1}', 200, 'application/octet-stream');
        const result = await httpRequest({ method: 'GET', url: '/api/raw' });
        expect(result).toEqual({ a: 1 });
    });
});

describe('httpRequest: errors', () => {
    it('требует url', async () => {
        await expect(httpRequest({})).rejects.toThrow(/url/);
    });

    it('4xx бросает HttpError со статусом и body', async () => {
        fetchMock.respondStatus('GET', '/api/x', 404, { detail: 'not found' });
        await expect(httpRequest({ method: 'GET', url: '/api/x' })).rejects.toMatchObject({
            name: 'HttpError',
            status: 404,
        });
    });

    it('форматирует error.detail = string', async () => {
        fetchMock.respondStatus('GET', '/api/x', 400, { detail: 'bad input' });
        try {
            await httpRequest({ method: 'GET', url: '/api/x' });
            expect.fail('should throw');
        } catch (err) {
            expect(err).toBeInstanceOf(HttpError);
            expect(err.message).toBe('bad input');
            expect(err.status).toBe(400);
            expect(err.body).toEqual({ detail: 'bad input' });
        }
    });

    it('форматирует error.detail = list (Pydantic)', async () => {
        fetchMock.respondStatus('GET', '/api/x', 422, {
            detail: [
                { loc: ['body', 'name'], msg: 'required' },
                { field: 'email', error: 'invalid' },
            ],
        });
        try {
            await httpRequest({ method: 'GET', url: '/api/x' });
            expect.fail('should throw');
        } catch (err) {
            expect(err.message).toBe('name: required; email: invalid');
        }
    });

    it('пустое тело ошибки → "HTTP <status>"', async () => {
        fetchMock.respondStatus('GET', '/api/x', 500);
        try {
            await httpRequest({ method: 'GET', url: '/api/x' });
            expect.fail('should throw');
        } catch (err) {
            expect(err.message).toBe('HTTP 500');
        }
    });
});
