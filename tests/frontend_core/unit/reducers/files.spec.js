import { describe, it, expect } from 'vitest';
import { filesReducer, initialFilesState, FILES_EVENTS, buildFileDownloadUrl } from '@platform/lib/events/reducers/files.js';

const ev = (type, payload, meta = {}) => ({
    id: `id_${type}`,
    type,
    payload,
    meta: { ts: 0, source: 'local', correlation_id: null, ...meta },
});

describe('filesReducer', () => {
    it('UPLOAD_REQUESTED фиксирует pending', () => {
        const next = filesReducer(initialFilesState, ev(FILES_EVENTS.UPLOAD_REQUESTED, { name: 'a.png' }, { correlation_id: 'cid1' }));
        expect(next.uploads.cid1).toEqual({ name: 'a.png', status: 'pending' });
    });

    it('UPLOAD_REQUESTED fallback на event.id если нет correlation_id', () => {
        const next = filesReducer(initialFilesState, ev(FILES_EVENTS.UPLOAD_REQUESTED, { name: 'b.png' }));
        const keys = Object.keys(next.uploads);
        expect(keys).toHaveLength(1);
        expect(next.uploads[keys[0]].name).toBe('b.png');
    });

    it('UPLOAD_COMPLETED помечает completed + кладёт file в byId', () => {
        const seeded = filesReducer(initialFilesState, ev(FILES_EVENTS.UPLOAD_REQUESTED, { name: 'a.png' }, { correlation_id: 'cid1' }));
        const next = filesReducer(seeded, ev(FILES_EVENTS.UPLOAD_COMPLETED, { file: { id: 'f1', name: 'a.png' } }, { correlation_id: 'cid1' }));
        expect(next.uploads.cid1.status).toBe('completed');
        expect(next.uploads.cid1.fileId).toBe('f1');
        expect(next.byId.f1).toEqual({ id: 'f1', name: 'a.png' });
    });

    it('UPLOAD_FAILED помечает failed', () => {
        const seeded = filesReducer(initialFilesState, ev(FILES_EVENTS.UPLOAD_REQUESTED, { name: 'a.png' }, { correlation_id: 'cid1' }));
        const next = filesReducer(seeded, ev(FILES_EVENTS.UPLOAD_FAILED, { message: 'oh' }, { correlation_id: 'cid1' }));
        expect(next.uploads.cid1.status).toBe('failed');
        expect(next.uploads.cid1.error).toBe('oh');
    });

    it('LOADED кладёт файл в byId', () => {
        const next = filesReducer(initialFilesState, ev(FILES_EVENTS.LOADED, { file: { id: 'f9', name: 'x.txt' } }));
        expect(next.byId.f9).toEqual({ id: 'f9', name: 'x.txt' });
    });
});

describe('buildFileDownloadUrl', () => {
    it('собирает URL с encode', () => {
        expect(buildFileDownloadUrl('file id with space')).toBe('/frontend/api/v1/files/download/file%20id%20with%20space');
    });

    it('пустой fileId — throw', () => {
        expect(() => buildFileDownloadUrl('')).toThrow(/fileId/);
    });
});
