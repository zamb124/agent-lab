import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { createStorageEffect } from '@platform/lib/events/effects/storage.effect.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
import { installFakeStorage } from '../../helpers/fake-storage.js';
import { buildCtx } from '../../helpers/bus-fixtures.js';

let storage;
beforeEach(() => { storage = installFakeStorage(); });
afterEach(() => storage.uninstall());

const ev = (type, payload) => ({ id: `id_${type}`, type, payload, meta: { ts: 0, source: 'local' } });

describe('storageEffect', () => {
    it('LOAD_REQUESTED → LOADED с парсенным JSON', async () => {
        storage.localStorage.setItem('k', JSON.stringify({ a: 1 }));
        const dispatched = [];
        await createStorageEffect()(ev(CoreEvents.STORAGE_LOAD_REQUESTED, { key: 'k' }), buildCtx(() => ({}), dispatched));
        const loaded = dispatched.find((d) => d.type === CoreEvents.STORAGE_LOADED);
        expect(loaded.payload).toEqual({ key: 'k', value: { a: 1 } });
    });

    it('LOAD_REQUESTED невалидный JSON → возвращает строку', async () => {
        storage.localStorage.setItem('k', 'not json');
        const dispatched = [];
        await createStorageEffect()(ev(CoreEvents.STORAGE_LOAD_REQUESTED, { key: 'k' }), buildCtx(() => ({}), dispatched));
        expect(dispatched[0].payload.value).toBe('not json');
    });

    it('LOAD_REQUESTED отсутствующий ключ → null', async () => {
        const dispatched = [];
        await createStorageEffect()(ev(CoreEvents.STORAGE_LOAD_REQUESTED, { key: 'missing' }), buildCtx(() => ({}), dispatched));
        expect(dispatched[0].payload.value).toBeNull();
    });

    it('LOAD_REQUESTED без key — throw', async () => {
        await expect(createStorageEffect()(ev(CoreEvents.STORAGE_LOAD_REQUESTED, {}), buildCtx(() => ({}), []))).rejects.toThrow(/key/);
    });

    it('PERSIST_REQUESTED сериализует объект', async () => {
        await createStorageEffect()(ev(CoreEvents.STORAGE_PERSIST_REQUESTED, { key: 'k', value: { a: 1 } }), buildCtx(() => ({}), []));
        expect(storage.localStorage.getItem('k')).toBe('{"a":1}');
    });

    it('PERSIST_REQUESTED string не сериализует JSON', async () => {
        await createStorageEffect()(ev(CoreEvents.STORAGE_PERSIST_REQUESTED, { key: 'k', value: 'plain' }), buildCtx(() => ({}), []));
        expect(storage.localStorage.getItem('k')).toBe('plain');
    });

    it('PERSIST_REQUESTED null/undefined → removeItem', async () => {
        storage.localStorage.setItem('k', 'value');
        await createStorageEffect()(ev(CoreEvents.STORAGE_PERSIST_REQUESTED, { key: 'k', value: null }), buildCtx(() => ({}), []));
        expect(storage.localStorage.getItem('k')).toBeNull();
    });
});
