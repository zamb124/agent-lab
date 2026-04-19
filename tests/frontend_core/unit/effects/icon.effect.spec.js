import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { createIconEffect } from '@platform/lib/events/effects/icon.effect.js';
import { ICON_EVENTS } from '@platform/lib/events/reducers/icon.js';
import { FILE_ICON_BASENAME_SET } from '@platform/lib/utils/file-icons.js';
import { installFetchMock } from '../../helpers/mock-fetch.js';
import { buildCtx } from '../../helpers/bus-fixtures.js';

let fetchMock;
beforeEach(() => { fetchMock = installFetchMock(); });
afterEach(() => fetchMock.uninstall());

const ev = (type, payload) => ({ id: `id_${type}`, type, payload, meta: { ts: 0, source: 'local' } });
const stateWith = (overrides = {}) => ({ icon: { uiCache: {}, fileCache: {}, loading: {}, errors: {}, ...overrides } });

describe('iconEffect: UI_LOAD_REQUESTED', () => {
    it('пустое имя → no-op', async () => {
        const dispatched = [];
        await createIconEffect()(ev(ICON_EVENTS.UI_LOAD_REQUESTED, {}), buildCtx(() => stateWith(), dispatched));
        expect(dispatched).toHaveLength(0);
    });

    it('уже в uiCache → no-op', async () => {
        const dispatched = [];
        await createIconEffect()(ev(ICON_EVENTS.UI_LOAD_REQUESTED, { name: 'plus' }), buildCtx(() => stateWith({ uiCache: { plus: '<svg/>' } }), dispatched));
        expect(dispatched).toHaveLength(0);
    });

    it('успех → UI_LOADED с svg', async () => {
        fetchMock.respondText('GET', '/static/core/assets/icons/some.svg', '<svg></svg>', 200, 'image/svg+xml');
        const dispatched = [];
        await createIconEffect()(ev(ICON_EVENTS.UI_LOAD_REQUESTED, { name: 'some' }), buildCtx(() => stateWith(), dispatched));
        const loaded = dispatched.find((d) => d.type === ICON_EVENTS.UI_LOADED);
        expect(loaded.payload.name).toBe('some');
        expect(loaded.payload.svg).toContain('<svg');
    });

    it('500 → UI_FAILED', async () => {
        fetchMock.respondStatus('GET', '/static/core/assets/icons/some.svg', 500);
        const dispatched = [];
        await createIconEffect()(ev(ICON_EVENTS.UI_LOAD_REQUESTED, { name: 'some' }), buildCtx(() => stateWith(), dispatched));
        const failed = dispatched.find((d) => d.type === ICON_EVENTS.UI_FAILED);
        expect(failed.payload.name).toBe('some');
    });
});

describe('iconEffect: FILE_LOAD_REQUESTED', () => {
    it('пустой basename → no-op', async () => {
        const dispatched = [];
        await createIconEffect()(ev(ICON_EVENTS.FILE_LOAD_REQUESTED, {}), buildCtx(() => stateWith(), dispatched));
        expect(dispatched).toHaveLength(0);
    });

    it('неизвестный basename → FILE_FAILED', async () => {
        const dispatched = [];
        await createIconEffect()(ev(ICON_EVENTS.FILE_LOAD_REQUESTED, { basename: 'mystery' }), buildCtx(() => stateWith(), dispatched));
        const failed = dispatched.find((d) => d.type === ICON_EVENTS.FILE_FAILED);
        expect(failed.payload.message).toContain('unknown basename');
    });

    it('известный basename → fetch + FILE_LOADED', async () => {
        const known = [...FILE_ICON_BASENAME_SET][0];
        fetchMock.respondText('GET', `/static/core/assets/icons/files_icons/${encodeURIComponent(known)}.svg`, '<svg/>', 200, 'image/svg+xml');
        const dispatched = [];
        await createIconEffect()(ev(ICON_EVENTS.FILE_LOAD_REQUESTED, { basename: known }), buildCtx(() => stateWith(), dispatched));
        const loaded = dispatched.find((d) => d.type === ICON_EVENTS.FILE_LOADED);
        expect(loaded.payload.basename).toBe(known);
    });
});
