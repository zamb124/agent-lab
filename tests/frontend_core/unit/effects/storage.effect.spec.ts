import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { createStorageEffect } from '@platform/lib/events/effects/storage.effect.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
import { installFakeStorage } from '../../helpers/fake-storage.js';
import { buildCtx } from '../../helpers/bus-fixtures.js';
import type { PlatformEvent } from '../../../../core/frontend/static/lib/events/contract.js';
import type { DispatchedRecord } from '../../helpers/bus-fixtures.js';
import { prop } from '../../helpers/prop.js';

let storage: ReturnType<typeof installFakeStorage>;
beforeEach(() => { storage = installFakeStorage(); });
afterEach(() => storage.uninstall());

const ev = (type: string, payload: unknown): PlatformEvent => ({ id: `id_${type}`, type, payload, meta: { ts: 0, source: 'local', causation_id: null, correlation_id: null, trace_id: null } });

describe('storageEffect', () => {
    it('LOAD_REQUESTED → LOADED с парсенным JSON', async () => {
        storage.localStorage.setItem('k', JSON.stringify({ a: 1 }));
        const dispatched: DispatchedRecord[] = [];
        await createStorageEffect()(ev(CoreEvents.STORAGE_LOAD_REQUESTED, { key: 'k' }), buildCtx(() => ({}), dispatched));
        const loaded = dispatched.find((d) => d.type === CoreEvents.STORAGE_LOADED);
        expect(prop(loaded?.payload, 'value')).toEqual({ a: 1 });
    });

    it('LOAD_REQUESTED обычная строка остаётся строкой', async () => {
        storage.localStorage.setItem('k', 'not json');
        const dispatched: DispatchedRecord[] = [];
        await createStorageEffect()(ev(CoreEvents.STORAGE_LOAD_REQUESTED, { key: 'k' }), buildCtx(() => ({}), dispatched));
        expect(prop(dispatched[0]?.payload, 'value')).toBe('not json');
    });

    it('LOAD_REQUESTED битый JSON-литерал бросает', async () => {
        storage.localStorage.setItem('k', '{"a":');
        await expect(
            createStorageEffect()(ev(CoreEvents.STORAGE_LOAD_REQUESTED, { key: 'k' }), buildCtx(() => ({}), [])),
        ).rejects.toBeInstanceOf(SyntaxError);
    });

    it('LOAD_REQUESTED отсутствующий ключ → null', async () => {
        const dispatched: DispatchedRecord[] = [];
        await createStorageEffect()(ev(CoreEvents.STORAGE_LOAD_REQUESTED, { key: 'missing' }), buildCtx(() => ({}), dispatched));
        expect(prop(dispatched[0]?.payload, 'value')).toBeNull();
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

    it('PERSIST_REQUESTED без key — throw', async () => {
        await expect(
            createStorageEffect()(ev(CoreEvents.STORAGE_PERSIST_REQUESTED, {}), buildCtx(() => ({}), [])),
        ).rejects.toThrow(/key/);
    });
});
