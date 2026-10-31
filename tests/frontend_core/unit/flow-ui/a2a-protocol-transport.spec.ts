/**
 * Транспорт A2A и декодер Parts: JSON-RPC ошибки, SSE-кадры (разбиение по чанкам, CRLF, ``[DONE]``),
 * abort без утечки, unwrap кадров, RFC 6901 указатели в патче, картинка агента.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';
import { prop } from '../../helpers/prop.js';

import {
    consumeA2AStream,
    flowUIIsAbortError,
    isSettledTaskState,
    resolveA2aContextId,
    resolveA2aTaskId,
    sendA2ARequest,
    unwrapA2aStreamResult,
} from '@platform/lib/a2a/a2a-stream.js';
import {
    applyJsonPatch,
    decodePart,
    decodeParts,
    filesFromParts,
    firstDataFromParts,
    textFromParts,
} from '@platform/lib/a2a/parts.js';
import { INTERRUPTED_TASK_STATES, TERMINAL_TASK_STATES } from '@platform/lib/a2a/constants.js';
import {
    agentIdentityImageUrlFromDocument,
    flowUIMediaSrc,
    resolveAgentIdentityImageSrc,
} from '@platform/lib/flow-ui/runtime/agent-identity-image.js';
import { BRAND_LOGO_PATH } from '@platform/lib/flow-ui/shell/brand-logo.js';

function jsonResponse(body: unknown, { status = 200, contentType = 'application/json' } = {}) {
    return {
        ok: status >= 200 && status < 300,
        status,
        headers: { get: (name: string) => (name.toLowerCase() === 'content-type' ? contentType : null) },
        json: async () => body,
        text: async () => JSON.stringify(body),
    };
}

function sseResponse(chunks: string[], { contentType = 'text/event-stream', status = 200 } = {}) {
    const encoder = new TextEncoder();
    let index = 0;
    let cancelled = false;
    const reader = {
        read: async () => {
            if (index >= chunks.length) return { done: true, value: undefined };
            const value = chunks[index];
            index += 1;
            return { done: false, value: typeof value === 'string' ? encoder.encode(value) : value };
        },
        cancel: async () => { cancelled = true; },
    };
    return {
        response: {
            ok: status >= 200 && status < 300,
            status,
            headers: { get: (name: string) => (name.toLowerCase() === 'content-type' ? contentType : null) },
            text: async () => JSON.stringify({ detail: 'stream failed' }),
            body: { getReader: () => reader },
        },
        wasCancelled: () => cancelled,
    };
}

describe('sendA2ARequest', () => {
    afterEach(() => vi.unstubAllGlobals());

    it('posts JSON-RPC with protocol headers and returns the frame', async () => {
        const fetchMock = vi.fn(async (_input: unknown, _init?: unknown) => jsonResponse({ id: '1', result: { task: { id: 't1' } } }));
        vi.stubGlobal('fetch', fetchMock);
        const frame = await sendA2ARequest({ url: '/flows/api/v1/f', body: { method: 'ListTasks' }, headers: { Authorization: 'Bearer x' }, credentials: 'omit' });
        expect(prop(prop(frame.result, 'task'), 'id')).toBe('t1');
        const init = fetchMock.mock.calls[0]?.[1];
        if (typeof init !== 'object' || init === null) throw new Error('fetch init required');
        expect(prop(init, 'method')).toBe('POST');
        expect(prop(init, 'credentials')).toBe('omit');
        expect(prop(init, 'headers')).toMatchObject({ 'Content-Type': 'application/json', Accept: 'application/json', Authorization: 'Bearer x' });
        expect(prop(prop(init, 'headers'), 'A2A-Version')).toBeTypeOf('string');
        expect(JSON.parse(String(prop(init, 'body')))).toEqual({ method: 'ListTasks' });
    });

    it('turns HTTP errors into Error with status and detail, and JSON-RPC errors into coded errors', async () => {
        vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ detail: 'Forbidden here' }, { status: 403 })));
        await expect(sendA2ARequest({ url: '/u', body: {} })).rejects.toMatchObject({ message: 'Forbidden here', status: 403 });

        vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 502, text: async () => '<html>bad gateway</html>' })));
        await expect(sendA2ARequest({ url: '/u', body: {} })).rejects.toMatchObject({ message: 'HTTP 502', status: 502, payload: null });

        vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ error: { code: -32001, message: 'Task not found' } })));
        await expect(sendA2ARequest({ url: '/u', body: {} })).rejects.toMatchObject({ message: 'Task not found', code: -32001 });

        vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ error: { code: -32603 } })));
        await expect(sendA2ARequest({ url: '/u', body: {} })).rejects.toThrow('A2A request failed');
    });

    it('propagates AbortError when the body read is aborted', async () => {
        const controller = new AbortController();
        vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, status: 200, json: async () => { controller.abort(); throw new TypeError('network'); } })));
        await expect(sendA2ARequest({ url: '/u', body: {}, signal: controller.signal })).rejects.toSatisfy(flowUIIsAbortError);
        vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, status: 200, json: async () => { throw new TypeError('network'); } })));
        await expect(sendA2ARequest({ url: '/u', body: {} })).rejects.toThrow('network');
    });
});

describe('consumeA2AStream', () => {
    afterEach(() => vi.unstubAllGlobals());

    it('reassembles SSE records across chunk boundaries and ignores comments, [DONE] and empty data', async () => {
        const frames: unknown[] = [];
        const { response, wasCancelled } = sseResponse([
            'data: {"result":{"statusUpdate":{"taskId":"t1","status":{"state":"TASK_STATE_WORKING"}}}}\n\n: keep-alive\n\ndata: {"result":{"artifa',
            'ctUpdate":{"taskId":"t1","artifact":{"artifactId":"a","parts":[]}}}}\r\n\r\nevent: ping\ndata:\n\ndata: [DONE]\n\n',
            'data: {"result":{"task":{"id":"t1","status":{"state":"TASK_STATE_COMPLETED"}}}}',
        ]);
        vi.stubGlobal('fetch', vi.fn(async () => response));
        await consumeA2AStream({ url: '/u', body: {} }, (frame: unknown) => { frames.push(prop(frame, 'result')); });
        expect(frames.map((result) => unwrapA2aStreamResult(result)?.frameKind)).toEqual(['statusUpdate', 'artifactUpdate']);
        // Последняя запись без завершающей пустой строки остаётся в буфере: SSE требует разделитель
        expect(frames).toHaveLength(2);
        expect(wasCancelled?.()).toBe(true);
    });

    it('requires onFrame, an event-stream content type and a body', async () => {
        await expect(Reflect.apply(consumeA2AStream, null, [{ url: '/u', body: {} }, null])).rejects.toThrow(/onFrame is required/);
        vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ result: {} })));
        await expect(consumeA2AStream({ url: '/u', body: {} }, () => {})).rejects.toThrow(/expected A2A text\/event-stream/);
        vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, status: 200, headers: { get: () => 'text/event-stream; charset=utf-8' }, body: null })));
        await expect(consumeA2AStream({ url: '/u', body: {} }, () => {})).rejects.toThrow(/body is missing/);
        vi.stubGlobal('fetch', vi.fn(async () => sseResponse([], { status: 500 }).response));
        await expect(consumeA2AStream({ url: '/u', body: {} }, () => {})).rejects.toMatchObject({ message: 'stream failed', status: 500 });
    });

    it('sends the streaming Accept header and surfaces JSON errors from a frame line', async () => {
        const fetchMock = vi.fn(async (_input: unknown, _init?: unknown) => sseResponse(['data: {not json}\n\n']).response);
        vi.stubGlobal('fetch', fetchMock);
        await expect(consumeA2AStream({ url: '/u', body: {}, headers: { 'X-Test': '1' } }, () => {})).rejects.toBeInstanceOf(SyntaxError);
        expect(prop(fetchMock.mock.calls[0]?.[1], 'headers')).toMatchObject({ Accept: 'text/event-stream', 'X-Test': '1' });
    });

    it('converts a read failure after abort into AbortError and rethrows other read failures', async () => {
        const controller = new AbortController();
        const failingReader = {
            read: async () => { controller.abort(); throw new TypeError('BodyStreamBuffer was aborted'); },
            cancel: async () => { throw new Error('already aborted'); },
        };
        const response = { ok: true, status: 200, headers: { get: () => 'text/event-stream' }, body: { getReader: () => failingReader } };
        vi.stubGlobal('fetch', vi.fn(async () => response));
        await expect(consumeA2AStream({ url: '/u', body: {}, signal: controller.signal }, () => {})).rejects.toSatisfy(flowUIIsAbortError);

        const brokenReader = { read: async () => { throw new TypeError('connection reset'); }, cancel: async () => {} };
        vi.stubGlobal('fetch', vi.fn(async () => ({ ...response, body: { getReader: () => brokenReader } })));
        await expect(consumeA2AStream({ url: '/u', body: {} }, () => {})).rejects.toThrow('connection reset');
    });
});

describe('frame helpers', () => {
    it('unwraps every frame kind and a bare task snapshot', () => {
        expect(unwrapA2aStreamResult({ statusUpdate: { taskId: 't' } })).toEqual({ frameKind: 'statusUpdate', event: { taskId: 't' } });
        expect(unwrapA2aStreamResult({ message: { messageId: 'm' } })).toEqual({ frameKind: 'message', event: { messageId: 'm' } });
        expect(unwrapA2aStreamResult({ id: 't', status: { state: 'TASK_STATE_WORKING' } })).toEqual({ frameKind: 'task', event: { id: 't', status: { state: 'TASK_STATE_WORKING' } } });
        expect(unwrapA2aStreamResult({ id: 't' })).toBeNull();
        expect(unwrapA2aStreamResult({})).toBeNull();
        expect(unwrapA2aStreamResult(null)).toBeNull();
        expect(unwrapA2aStreamResult('x')).toBeNull();
    });

    it('resolves task and context ids with fallbacks to the current value', () => {
        expect(resolveA2aTaskId({ task: { id: 't1', contextId: 'c1' } })).toBe('t1');
        expect(resolveA2aTaskId({ artifactUpdate: { taskId: 't2' } }, 'old')).toBe('t2');
        expect(resolveA2aTaskId({ artifactUpdate: { taskId: '' } }, 'old')).toBe('old');
        expect(resolveA2aTaskId({}, 'old')).toBe('old');
        expect(resolveA2aContextId({ statusUpdate: { contextId: 'c2' } }, 'old')).toBe('c2');
        expect(resolveA2aContextId({ statusUpdate: {} }, 'old')).toBe('old');
        expect(resolveA2aContextId(null)).toBeNull();
    });

    it('treats interrupted states as settled', () => {
        for (const state of [...TERMINAL_TASK_STATES, ...INTERRUPTED_TASK_STATES]) expect(isSettledTaskState(state), state).toBe(true);
        expect(isSettledTaskState('TASK_STATE_WORKING')).toBe(false);
        expect(isSettledTaskState('TASK_STATE_SUBMITTED')).toBe(false);
        expect(isSettledTaskState('unknown')).toBe(false);
        expect(flowUIIsAbortError(new DOMException('x', 'AbortError'))).toBe(true);
        expect(flowUIIsAbortError(new Error('AbortError'))).toBe(false);
        expect(flowUIIsAbortError('AbortError')).toBe(false);
    });
});

describe('parts decoder', () => {
    it('decodes text, url, raw and untyped data parts and rejects malformed ones', () => {
        expect(decodePart({ text: 'hi' })).toEqual({ kind: 'text', text: 'hi' });
        expect(decodePart({ url: 'https://f/x', mediaType: 'image/png', filename: 'x.png' })).toEqual({ kind: 'file', file: { url: 'https://f/x', mediaType: 'image/png', filename: 'x.png' } });
        expect(decodePart({ url: 'https://f/x' })).toEqual({ kind: 'file', file: { url: 'https://f/x', mediaType: '', filename: '' } });
        expect(decodePart({ raw: 'AAA=', mediaType: 'audio/wav' })).toEqual({ kind: 'raw', raw: 'AAA=', mediaType: 'audio/wav' });
        expect(decodePart({ data: { tool: 'x' } })).toEqual({ kind: 'data', value: { tool: 'x' } });
        expect(decodePart({ data: [1, 2] })).toEqual({ kind: 'data', value: [1, 2] });
        expect(decodePart({ data: { a: 1 }, mediaType: 'application/json' })).toEqual({ kind: 'json', value: { a: 1 } });
        expect(decodePart({ data: [{ op: 'add', path: '/a', value: 1 }], mediaType: 'application/json-patch+json' })).toEqual({ kind: 'json_patch', operations: [{ op: 'add', path: '/a', value: 1 }] });
        expect(() => decodePart(null)).toThrow(/Part must be an object/);
        expect(() => decodePart([])).toThrow(/Part must be an object/);
        expect(() => decodePart({ mediaType: 'text/plain' })).toThrow(/neither text, url, raw nor data/);
        expect(() => decodePart({ data: [1], mediaType: 'application/json' })).toThrow(/state snapshot must be an object/);
        expect(() => decodePart({ data: {}, mediaType: 'application/json-patch+json' })).toThrow(/json patch must be an array/);
        expect(() => decodePart({ data: { fields: {} }, mediaType: 'application/vnd.platform.ui-action+json' })).toThrow(/ui action part requires action/);
    });

    it('collects text, files and the first data payload', () => {
        const parts = [{ text: 'a' }, { data: { x: 1 } }, { url: 'https://f/1', filename: 'one' }, { text: 'b' }, { data: { y: 2 } }, 'garbage', null];
        expect(textFromParts(parts)).toBe('ab');
        expect(filesFromParts(parts.filter((part) => part && typeof part === 'object'))).toEqual([{ url: 'https://f/1', mediaType: '', filename: 'one' }]);
        expect(firstDataFromParts(parts)).toEqual({ x: 1 });
        expect(firstDataFromParts([{ text: 'x' }])).toBeNull();
        expect(textFromParts(undefined)).toBe('');
        expect(decodeParts(undefined)).toEqual([]);
    });

    it('applies JSON pointers with escapes, creates missing parents on add, and never mutates the input', () => {
        const before = { a: { 'b/c': 1, 'd~e': 2 }, keep: [1, 2] };
        const after = applyJsonPatch(before, [
            { op: 'replace', path: '/a/b~1c', value: 10 },
            { op: 'remove', path: '/a/d~0e' },
            { op: 'add', path: '/x/y/z', value: [true] },
            { op: 'add', path: '', value: { root: 1 } },
            { op: 'add', path: '/again', value: null },
        ]);
        expect(after).toEqual({ root: 1, again: null });
        expect(before).toEqual({ a: { 'b/c': 1, 'd~e': 2 }, keep: [1, 2] });
        expect(applyJsonPatch({ a: 1 }, [])).toEqual({ a: 1 });
        expect(() => Reflect.apply(applyJsonPatch, null, [[], []])).toThrow(/target must be an object/);
        expect(() => applyJsonPatch({}, {})).toThrow(/operations must be an array/);
        expect(() => applyJsonPatch({}, [{ op: 'add', value: 1 }])).toThrow(/requires path/);
        expect(() => applyJsonPatch({}, [{ op: 'add', path: 'a', value: 1 }])).toThrow(/invalid JSON pointer/);
        expect(() => applyJsonPatch({}, [{ op: 'remove', path: '' }])).toThrow(/cannot remove document root/);
        expect(() => applyJsonPatch({}, [{ op: 'replace', path: '', value: 5 }])).toThrow(/root value must be an object/);
        expect(() => applyJsonPatch({ a: 1 }, [{ op: 'remove', path: '/a/b' }])).toThrow(/does not exist/);
        expect(() => applyJsonPatch({ a: { b: 1 } }, [{ op: 'remove', path: '/a/c' }])).toThrow(/\/a\/c does not exist/);
    });
});

describe('agent identity image', () => {
    const files = '/flows/api/v1/files/download/abc';

    it('accepts http(s), platform static and files download paths only', () => {
        expect(flowUIMediaSrc('', 'https://cdn/x.png')).toBe('https://cdn/x.png');
        expect(flowUIMediaSrc('https://ui', ' HTTP://cdn/x.png ')).toBe('HTTP://cdn/x.png');
        expect(flowUIMediaSrc('https://ui/', '/static/core/assets/a.svg')).toBe('https://ui/static/core/assets/a.svg');
        expect(flowUIMediaSrc('https://ui//', files)).toBe(`https://ui${files}`);
        expect(flowUIMediaSrc('', files)).toBe(files);
        expect(flowUIMediaSrc('   ', files)).toBe(files);
        expect(() => flowUIMediaSrc('', '')).toThrow(/raw URL required/);
        expect(() => flowUIMediaSrc('', 5)).toThrow(/raw URL required/);
        expect(() => flowUIMediaSrc('', 'javascript:alert(1)')).toThrow(/blocked scheme javascript/);
        expect(() => flowUIMediaSrc('', 'data:image/png;base64,AAA')).toThrow(/blocked scheme data/);
        expect(() => flowUIMediaSrc('', 'img.png')).toThrow(/expected absolute path or http\(s\) URL/);
        expect(() => flowUIMediaSrc('', '/uploads/img.png')).toThrow(/unsupported path/);
    });

    it('prefers explicit image, then the agent_identity block, then flow identity, then the brand logo', () => {
        const document = { start_page_id: 'main', pages: [{ page_id: 'main', blocks: [
            { block_id: 's', type: 'section', blocks: [{ block_id: 'id', type: 'agent_identity', title: '', image_url: 'https://doc/img.png' }] },
            { block_id: 'id2', type: 'agent_identity', title: '', image_url: '  ' },
        ] }] };
        expect(agentIdentityImageUrlFromDocument(document)).toBe('https://doc/img.png');
        expect(agentIdentityImageUrlFromDocument(null)).toBeNull();
        expect(() => agentIdentityImageUrlFromDocument({ pages: 'x' })).toThrow(/pages must be an array/);
        expect(() => agentIdentityImageUrlFromDocument({ pages: [{ blocks: [{ type: 'agent_identity', image_url: 7 }] }] })).toThrow(/image_url must be a string/);
        const conflict = { pages: [{ blocks: [
            { type: 'agent_identity', image_url: 'https://a/1.png' },
            { type: 'agent_identity', image_url: 'https://a/2.png' },
        ] }] };
        expect(() => agentIdentityImageUrlFromDocument(conflict)).toThrow(/image_url conflict/);

        expect(resolveAgentIdentityImageSrc({ imageUrl: files, document, platformUiOrigin: 'https://ui' })).toBe(`https://ui${files}`);
        expect(resolveAgentIdentityImageSrc({ document })).toBe('https://doc/img.png');
        expect(resolveAgentIdentityImageSrc({ flowIdentity: { image_url: 'https://flow/i.png' } })).toBe('https://flow/i.png');
        expect(resolveAgentIdentityImageSrc({ flowIdentity: { image_url: null }, platformUiOrigin: 'https://ui' })).toBe(`https://ui${BRAND_LOGO_PATH}`);
        expect(resolveAgentIdentityImageSrc()).toBe(BRAND_LOGO_PATH);
    });
});
