/**
 * httpStream и расширенные ветки httpRequest: SSE-разбор, ошибки, метаданные ответа.
 * Используется настоящий `Response` Node, подменяется только `fetch`.
 */

import { afterEach, describe, expect, it, vi, type Mock } from 'vitest';
import { HttpError, httpRequest, httpStream } from '@platform/lib/events/http.js';

type FetchSpy = Mock<(url: string, init: RequestInit) => Promise<Response>>;

function stubFetch(response: Response): FetchSpy {
    const fetchSpy: FetchSpy = vi.fn(async () => response);
    vi.stubGlobal('fetch', fetchSpy);
    return fetchSpy;
}

function sseResponse(chunks: string[], init: ResponseInit = { status: 200 }): Response {
    const encoder = new TextEncoder();
    const stream = new ReadableStream<Uint8Array>({
        start(controller) {
            for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
            controller.close();
        },
    });
    return new Response(stream, init);
}

function firstCall(fetchSpy: FetchSpy): [string, RequestInit] {
    const call = fetchSpy.mock.calls[0];
    if (!call) throw new Error('fetch не вызывался');
    return call;
}

async function rejectedHttpError(call: Promise<unknown>): Promise<HttpError> {
    const outcome = await call.then(
        () => null,
        (reason: unknown) => reason,
    );
    if (!(outcome instanceof HttpError)) throw new Error('ожидался отказ с HttpError');
    return outcome;
}

afterEach(() => {
    vi.unstubAllGlobals();
});

describe('httpStream', () => {
    it('требует функцию onEvent', async () => {
        await expect(Reflect.apply(httpStream, undefined, [{ url: '/s' }, null])).rejects.toThrow(/onEvent function required/);
    });

    it('собирает data-строки из разрезанных чанков и останавливается на [DONE]', async () => {
        const fetchSpy = stubFetch(sseResponse(['data: {"a":1}\nda', 'ta: {"b":2}\n', 'data: [DONE]\n', 'data: {"c":3}\n']));
        const events: unknown[] = [];
        const result = await httpStream({ url: '/s', body: { q: 1 } }, (data) => events.push(data));
        expect(events).toEqual([{ a: 1 }, { b: 2 }]);
        expect(result).toBeUndefined();
        const [url, init] = firstCall(fetchSpy);
        expect(url).toBe('/s');
        expect(init.method).toBe('POST');
        expect(init.body).toBe('{"q":1}');
    });

    it('returnMeta + captureRaw возвращают конверт с сырым телом при [DONE]', async () => {
        stubFetch(sseResponse(['data: {"a":1}\n', 'data: [DONE]\n']));
        const result = await httpStream({ url: '/s', returnMeta: true, captureRaw: true }, () => undefined);
        expect(result).toMatchObject({ status: 200, body: {} });
        expect(result?.raw).toContain('data: {"a":1}');
    });

    it('returnMeta возвращает конверт и при закрытии потока без [DONE]', async () => {
        stubFetch(sseResponse(['data: {"a":1}\n']));
        const result = await httpStream({ url: '/s', returnMeta: true }, () => undefined);
        expect(result).toMatchObject({ status: 200, raw: '' });
    });

    it('без returnMeta на закрытии потока возвращает undefined', async () => {
        stubFetch(sseResponse(['data: {"a":1}\n']));
        await expect(httpStream({ url: '/s' }, () => undefined)).resolves.toBeUndefined();
    });

    it('не-ok ответ бросает HttpError с телом', async () => {
        stubFetch(new Response(JSON.stringify({ detail: 'нельзя' }), { status: 403, headers: { 'content-type': 'application/json' } }));
        const error = await rejectedHttpError(httpStream({ url: '/s' }, () => undefined));
        expect(error.status).toBe(403);
        expect(error.message).toBe('нельзя');
    });

    it('не-ok ответ без JSON даёт HTTP <status>', async () => {
        stubFetch(new Response('boom', { status: 502 }));
        const error = await rejectedHttpError(httpStream({ url: '/s' }, () => undefined));
        expect(error.message).toBe('HTTP 502');
        expect(error.body).toBeNull();
    });

    it('битый JSON в теле отказа пробрасывает SyntaxError, как и у успешного ответа', async () => {
        stubFetch(new Response('{"detail":', { status: 500 }));
        await expect(httpStream({ url: '/s' }, () => undefined)).rejects.toBeInstanceOf(SyntaxError);
    });

    it('ответ без body — ошибка', async () => {
        stubFetch(new Response(null, { status: 200 }));
        await expect(httpStream({ url: '/s' }, () => undefined)).rejects.toThrow(/response.body is null/);
    });
});

describe('httpRequest: платформенная ошибка и форматы', () => {
    it('поля конверта ошибки попадают в HttpError', async () => {
        stubFetch(
            new Response(
                JSON.stringify({
                    error_code: 'platform:errors.forbidden',
                    error_params: { name: 'x' },
                    request_id: 'r1',
                    trace_id: 't1',
                    service: 'crm',
                    observability: { logs_explore_url: 'https://logs/x' },
                }),
                { status: 403 },
            ),
        );
        const error = await rejectedHttpError(httpRequest({ url: '/x' }));
        expect(error.request_id).toBe('r1');
        expect(error.trace_id).toBe('t1');
        expect(error.service).toBe('crm');
        expect(error.observability).toEqual({ logs_explore_url: 'https://logs/x' });
        expect(error.error_code).toBe('platform:errors.forbidden');
        expect(error.error_params).toEqual({ name: 'x' });
    });

    it('detail-массив собирается в "поле: сообщение"', async () => {
        stubFetch(
            new Response(
                JSON.stringify({ detail: [{ loc: ['body', 'name'], msg: 'обязательно' }, { field: 'age', error: 'мало' }, { msg: 'без пути' }] }),
                { status: 422 },
            ),
        );
        const error = await rejectedHttpError(httpRequest({ url: '/x' }));
        expect(error.message).toBe('name: обязательно; age: мало; field: без пути');
    });

    it('message из тела используется, когда нет detail', async () => {
        stubFetch(new Response(JSON.stringify({ message: 'сломалось' }), { status: 500 }));
        const error = await rejectedHttpError(httpRequest({ url: '/x' }));
        expect(error.message).toBe('сломалось');
    });

    it('тело ошибки без известных полей даёт HTTP <status>', async () => {
        stubFetch(new Response(JSON.stringify({ other: 1 }), { status: 500 }));
        const error = await rejectedHttpError(httpRequest({ url: '/x' }));
        expect(error.message).toBe('HTTP 500');
        expect(error.request_id).toBeNull();
        expect(error.observability).toBeNull();
    });

    it('204 с returnMeta возвращает конверт', async () => {
        stubFetch(new Response(null, { status: 204 }));
        await expect(httpRequest({ url: '/x', returnMeta: true })).resolves.toMatchObject({ status: 204, raw: '', body: {} });
    });

    it('text/plain возвращается строкой, пустое тело — {}', async () => {
        stubFetch(new Response('привет', { status: 200, headers: { 'content-type': 'text/plain' } }));
        await expect(httpRequest({ url: '/x' })).resolves.toBe('привет');
        stubFetch(new Response(new Blob(['  ']), { status: 200 }));
        await expect(httpRequest({ url: '/x' })).resolves.toEqual({});
    });

    it('JSON без content-type разбирается по первому символу, прочее — строка', async () => {
        const bytes = (text: string): Blob => new Blob([text]);
        stubFetch(new Response(bytes('[1,2]'), { status: 200 }));
        await expect(httpRequest({ url: '/x' })).resolves.toEqual([1, 2]);
        stubFetch(new Response(bytes('<html>'), { status: 200 }));
        await expect(httpRequest({ url: '/x' })).resolves.toBe('<html>');
    });

    it('FormData уходит без Content-Type и без JSON-сериализации', async () => {
        const fetchSpy = stubFetch(new Response('{}', { status: 200 }));
        const form = new FormData();
        form.append('file', 'x');
        await httpRequest({ url: '/x', method: 'POST', body: form });
        const [, init] = firstCall(fetchSpy);
        expect(init.body).toBe(form);
        expect(init.headers).toEqual({});
    });

    it('returnMeta отдаёт заголовки и сырой текст', async () => {
        stubFetch(new Response('{"a":1}', { status: 200, headers: { 'content-type': 'application/json', 'x-test': '1' } }));
        const result = await httpRequest({ url: '/x', returnMeta: true });
        expect(result).toMatchObject({ headers: { 'x-test': '1' }, raw: '{"a":1}', body: { a: 1 } });
    });

    it('требует url', async () => {
        await expect(Reflect.apply(httpRequest, undefined, [{}])).rejects.toThrow(/url/);
    });
});
