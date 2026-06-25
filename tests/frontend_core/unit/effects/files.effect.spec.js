import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { createFilesEffect } from '@platform/lib/events/effects/files.effect.js';
import { FILES_EVENTS } from '@platform/lib/events/reducers/files.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
import { installFetchMock } from '../../helpers/mock-fetch.js';
import { buildCtx } from '../../helpers/bus-fixtures.js';

const FILES_UPLOAD_URL = '/frontend/api/v1/files/';
const FILES_META_URL = '/frontend/api/v1/files/f1';

let fetchMock;
beforeEach(() => {
    fetchMock = installFetchMock();
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
        await expect(createFilesEffect()(ev(FILES_EVENTS.UPLOAD_REQUESTED, {}), buildCtx(() => ({}), []))).rejects.toThrow(/file/);
    });

    it('требует payload.spec', async () => {
        await expect(
            createFilesEffect()(ev(FILES_EVENTS.UPLOAD_REQUESTED, { file: { name: 'a.png' } }), buildCtx(() => ({}), [])),
        ).rejects.toThrow(/spec/);
    });

    it('успех → UPLOAD_COMPLETED с file', async () => {
        fetchMock.respondJson('POST', FILES_UPLOAD_URL, { file_id: 'f1', original_name: 'a.png' });
        const dispatched = [];
        await createFilesEffect()(
            ev(
                FILES_EVENTS.UPLOAD_REQUESTED,
                { file: { name: 'a.png' }, spec: '{"source_kind":"platform_auxiliary","source_ref":{},"retention":{"kind":"platform_default"}}' },
                { correlation_id: 'cid1' },
            ),
            buildCtx(() => ({}), dispatched),
        );
        const completed = dispatched.find((d) => d.type === FILES_EVENTS.UPLOAD_COMPLETED);
        expect(completed.payload.file).toEqual({ file_id: 'f1', original_name: 'a.png' });
        expect(completed.meta.correlation_id).toBe('cid1');
    });

    it('ошибка → UPLOAD_FAILED', async () => {
        fetchMock.respondStatus('POST', FILES_UPLOAD_URL, 500);
        const dispatched = [];
        await createFilesEffect()(
            ev(
                FILES_EVENTS.UPLOAD_REQUESTED,
                { file: { name: 'a.png' }, spec: '{"source_kind":"platform_auxiliary","source_ref":{},"retention":{"kind":"platform_default"}}' },
            ),
            buildCtx(() => ({}), dispatched),
        );
        expect(dispatched.find((d) => d.type === FILES_EVENTS.UPLOAD_FAILED)).toBeTruthy();
    });
});

describe('filesEffect: LOAD_REQUESTED', () => {
    it('требует file_id', async () => {
        await expect(createFilesEffect()(ev(FILES_EVENTS.LOAD_REQUESTED, {}), buildCtx(() => ({}), []))).rejects.toThrow(/file_id/);
    });

    it('успех → LOADED', async () => {
        fetchMock.respondJson('GET', FILES_META_URL, { file_id: 'f1', original_name: 'a.png' });
        const dispatched = [];
        await createFilesEffect()(ev(FILES_EVENTS.LOAD_REQUESTED, { file_id: 'f1' }), buildCtx(() => ({}), dispatched));
        const loaded = dispatched.find((d) => d.type === FILES_EVENTS.LOADED);
        expect(loaded.payload.file).toEqual({ file_id: 'f1', original_name: 'a.png' });
    });

    it('404 → LOAD_FAILED', async () => {
        fetchMock.respondStatus('GET', FILES_META_URL, 404);
        const dispatched = [];
        await createFilesEffect()(ev(FILES_EVENTS.LOAD_REQUESTED, { file_id: 'f1' }), buildCtx(() => ({}), dispatched));
        expect(dispatched.find((d) => d.type === FILES_EVENTS.LOAD_FAILED)).toBeTruthy();
    });
});

describe('filesEffect: OPEN_REQUESTED', () => {
    it('требует file_id', async () => {
        await expect(createFilesEffect()(ev(FILES_EVENTS.OPEN_REQUESTED, {}), buildCtx(() => ({}), []))).rejects.toThrow(/file_id/);
    });

    it('успех → UI_MODAL_OPEN platform.file_viewer с editor-config из FileRecord endpoint', async () => {
        const config = { document_server_url: 'https://docs.example', token: 'jwt' };
        fetchMock.respondJson('GET', '/documents/api/v1/files/f-doc/editor-config', config);
        const dispatched = [];
        await createFilesEffect()(
            ev(
                FILES_EVENTS.OPEN_REQUESTED,
                {
                    file: {
                        file_id: 'f-doc',
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
        expect(opened.payload.props.fileId).toBe('f-doc');
        expect(opened.payload.props.config).toEqual(config);
        expect(opened.meta.correlation_id).toBe('cid-open');
    });

    it('ошибка → OPEN_FAILED и error toast', async () => {
        fetchMock.respondStatus('GET', '/documents/api/v1/files/f-doc/editor-config', 404, { detail: 'not office' });
        const dispatched = [];
        await createFilesEffect()(
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
        await createFilesEffect()(
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
        await createFilesEffect()(
            ev(FILES_EVENTS.EDITOR_SYNC_REQUESTED, { file_id: 'f-doc' }),
            buildCtx(() => ({}), dispatched),
        );
        expect(dispatched.find((d) => d.type === FILES_EVENTS.EDITOR_SYNC_FAILED)).toBeTruthy();
    });
});
