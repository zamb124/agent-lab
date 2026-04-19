import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { createFilesEffect } from '@platform/lib/events/effects/files.effect.js';
import { FILES_EVENTS } from '@platform/lib/events/reducers/files.js';
import { installFetchMock } from '../../helpers/mock-fetch.js';
import { buildCtx } from '../../helpers/bus-fixtures.js';

let fetchMock;
beforeEach(() => {
    fetchMock = installFetchMock();
    // Минимальный FormData shim для Node — http.js проверяет `instanceof FormData`.
    if (typeof globalThis.FormData === 'undefined') {
        globalThis.FormData = class FormData {
            constructor() { this._data = {}; }
            append(k, v) { this._data[k] = v; }
        };
    }
});
afterEach(() => fetchMock.uninstall());

const ev = (type, payload, meta = {}) => ({ id: `id_${type}`, type, payload, meta: { ts: 0, source: 'local', ...meta } });

describe('filesEffect: UPLOAD_REQUESTED', () => {
    it('требует payload.file', async () => {
        await expect(createFilesEffect({ baseUrl: '/svc' })(ev(FILES_EVENTS.UPLOAD_REQUESTED, {}), buildCtx(() => ({}), []))).rejects.toThrow(/file/);
    });

    it('успех → UPLOAD_COMPLETED с file', async () => {
        fetchMock.respondJson('POST', '/svc/api/v1/files/', { id: 'f1', name: 'a.png' });
        const dispatched = [];
        await createFilesEffect({ baseUrl: '/svc' })(
            ev(FILES_EVENTS.UPLOAD_REQUESTED, { file: { name: 'a.png' } }, { correlation_id: 'cid1' }),
            buildCtx(() => ({}), dispatched),
        );
        const completed = dispatched.find((d) => d.type === FILES_EVENTS.UPLOAD_COMPLETED);
        expect(completed.payload.file).toEqual({ id: 'f1', name: 'a.png' });
        expect(completed.meta.correlation_id).toBe('cid1');
    });

    it('ошибка → UPLOAD_FAILED', async () => {
        fetchMock.respondStatus('POST', '/svc/api/v1/files/', 500);
        const dispatched = [];
        await createFilesEffect({ baseUrl: '/svc' })(
            ev(FILES_EVENTS.UPLOAD_REQUESTED, { file: { name: 'a.png' } }),
            buildCtx(() => ({}), dispatched),
        );
        expect(dispatched.find((d) => d.type === FILES_EVENTS.UPLOAD_FAILED)).toBeTruthy();
    });
});

describe('filesEffect: LOAD_REQUESTED', () => {
    it('требует file_id', async () => {
        await expect(createFilesEffect({ baseUrl: '/svc' })(ev(FILES_EVENTS.LOAD_REQUESTED, {}), buildCtx(() => ({}), []))).rejects.toThrow(/file_id/);
    });

    it('успех → LOADED', async () => {
        fetchMock.respondJson('GET', '/svc/api/v1/files/f1', { id: 'f1', name: 'a.png' });
        const dispatched = [];
        await createFilesEffect({ baseUrl: '/svc' })(ev(FILES_EVENTS.LOAD_REQUESTED, { file_id: 'f1' }), buildCtx(() => ({}), dispatched));
        const loaded = dispatched.find((d) => d.type === FILES_EVENTS.LOADED);
        expect(loaded.payload.file).toEqual({ id: 'f1', name: 'a.png' });
    });

    it('404 → LOAD_FAILED', async () => {
        fetchMock.respondStatus('GET', '/svc/api/v1/files/f1', 404);
        const dispatched = [];
        await createFilesEffect({ baseUrl: '/svc' })(ev(FILES_EVENTS.LOAD_REQUESTED, { file_id: 'f1' }), buildCtx(() => ({}), dispatched));
        expect(dispatched.find((d) => d.type === FILES_EVENTS.LOAD_FAILED)).toBeTruthy();
    });
});
