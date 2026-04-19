import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { createFileTypesEffect } from '@platform/lib/events/effects/file-types.effect.js';
import { FILE_TYPES_EVENTS } from '@platform/lib/events/reducers/file-types.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
import { installFetchMock } from '../../helpers/mock-fetch.js';
import { buildCtx } from '../../helpers/bus-fixtures.js';

let fetchMock;
beforeEach(() => { fetchMock = installFetchMock(); });
afterEach(() => fetchMock.uninstall());

const ev = (type, payload = null) => ({ id: `id_${type}`, type, payload, meta: { ts: 0, source: 'system' } });
const stateNotLoaded = { fileTypes: { loaded: false, categories: [], registry: [], error: null } };
const stateLoaded = { fileTypes: { loaded: true, categories: ['x'], registry: [], error: null } };

describe('fileTypesEffect', () => {
    it('не на bootstrap → no-op', async () => {
        const dispatched = [];
        await createFileTypesEffect()(ev('foo/bar/baz'), buildCtx(() => stateNotLoaded, dispatched));
        expect(dispatched).toHaveLength(0);
    });

    it('уже loaded → no-op', async () => {
        const dispatched = [];
        await createFileTypesEffect()(ev(CoreEvents.APP_BOOTSTRAP_STARTED), buildCtx(() => stateLoaded, dispatched));
        expect(dispatched).toHaveLength(0);
    });

    it('успех → LOADED', async () => {
        fetchMock.respondJson('GET', '/api/platform/file-types', { categories: ['image'], registry: [{ extension: '.png', mime_types: ['image/png'], category: 'image' }] });
        const dispatched = [];
        await createFileTypesEffect()(ev(CoreEvents.APP_BOOTSTRAP_STARTED), buildCtx(() => stateNotLoaded, dispatched));
        const loaded = dispatched.find((d) => d.type === FILE_TYPES_EVENTS.LOADED);
        expect(loaded.payload.categories).toEqual(['image']);
    });

    it('ошибка → LOAD_FAILED', async () => {
        fetchMock.respondStatus('GET', '/api/platform/file-types', 500);
        const dispatched = [];
        await createFileTypesEffect()(ev(CoreEvents.APP_BOOTSTRAP_STARTED), buildCtx(() => stateNotLoaded, dispatched));
        expect(dispatched.find((d) => d.type === FILE_TYPES_EVENTS.LOAD_FAILED)).toBeTruthy();
    });
});
