import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { createFilesEffect } from '@platform/lib/events/effects/files.effect.js';
import { FILES_EVENTS } from '@platform/lib/events/reducers/files.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
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

describe('filesEffect: OPEN_REQUESTED', () => {
    it('требует file_id', async () => {
        await expect(createFilesEffect({ baseUrl: '/svc' })(ev(FILES_EVENTS.OPEN_REQUESTED, {}), buildCtx(() => ({}), []))).rejects.toThrow(/file_id/);
    });

    it('успех → UI_MODAL_OPEN platform.file_viewer с editor-config из FileRecord endpoint', async () => {
        const config = { document_server_url: 'https://docs.example', token: 'jwt' };
        fetchMock.respondJson('GET', '/documents/api/v1/files/f-doc/editor-config', config);
        const dispatched = [];
        await createFilesEffect({ baseUrl: '/svc' })(
            ev(
                FILES_EVENTS.OPEN_REQUESTED,
                {
                    file: {
                        id: 'f-doc',
                        original_name: 'A.docx',
                        content_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    },
                    source: 'spec',
                },
                { correlation_id: 'cid-open' },
            ),
            buildCtx(() => ({}), dispatched),
        );

        const opened = dispatched.find((d) => d.type === CoreEvents.UI_MODAL_OPEN);
        expect(opened.payload.kind).toBe('platform.file_viewer');
        expect(opened.payload.props).toEqual({
            fileId: 'f-doc',
            file: {
                id: 'f-doc',
                original_name: 'A.docx',
                content_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                file_id: 'f-doc',
            },
            config,
        });
        expect(opened.meta.correlation_id).toBe('cid-open');
    });

    it('ошибка → OPEN_FAILED и error toast', async () => {
        fetchMock.respondStatus('GET', '/documents/api/v1/files/f-doc/editor-config', 404, { detail: 'not office' });
        const dispatched = [];
        await createFilesEffect({ baseUrl: '/svc' })(
            ev(FILES_EVENTS.OPEN_REQUESTED, { file_id: 'f-doc' }, { correlation_id: 'cid-open' }),
            buildCtx(() => ({}), dispatched),
        );

        expect(dispatched.find((d) => d.type === FILES_EVENTS.OPEN_FAILED)).toBeTruthy();
        const toast = dispatched.find((d) => d.type === CoreEvents.UI_TOAST_SHOW);
        expect(toast.payload.type).toBe('error');
        expect(toast.payload.i18n_key).toBe('platform:file_viewer.open_failed');
    });
});

describe('filesEffect: EDITOR_SYNC_REQUESTED', () => {
    it('успех → EDITOR_SYNC_COMPLETED с результатом sync endpoint', async () => {
        fetchMock.respondJson('POST', '/documents/api/v1/files/f-doc/sync', {
            file_id: 'f-doc',
            checksum: 'sha',
            file_size: 12,
        });
        const dispatched = [];
        await createFilesEffect({ baseUrl: '/svc' })(
            ev(
                FILES_EVENTS.EDITOR_SYNC_REQUESTED,
                { file_id: 'f-doc', close: true, settle_ms: 10, dirty: true },
                { correlation_id: 'cid-sync' },
            ),
            buildCtx(() => ({}), dispatched),
        );

        const completed = dispatched.find((d) => d.type === FILES_EVENTS.EDITOR_SYNC_COMPLETED);
        expect(completed.payload).toEqual({
            file_id: 'f-doc',
            result: { file_id: 'f-doc', checksum: 'sha', file_size: 12 },
        });
        expect(completed.meta.correlation_id).toBe('cid-sync');
        expect(JSON.parse(fetchMock.calls.find((c) => c.url === '/documents/api/v1/files/f-doc/sync').init.body)).toEqual({
            close: true,
            settle_ms: 10,
            dirty: true,
        });
    });

    it('ошибка → EDITOR_SYNC_FAILED', async () => {
        fetchMock.respondStatus('POST', '/documents/api/v1/files/f-doc/sync', 500);
        const dispatched = [];
        await createFilesEffect({ baseUrl: '/svc' })(
            ev(FILES_EVENTS.EDITOR_SYNC_REQUESTED, { file_id: 'f-doc' }),
            buildCtx(() => ({}), dispatched),
        );
        expect(dispatched.find((d) => d.type === FILES_EVENTS.EDITOR_SYNC_FAILED)).toBeTruthy();
    });
});
