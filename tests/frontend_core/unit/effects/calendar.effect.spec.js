import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { createCalendarEffect } from '@platform/lib/events/effects/calendar.effect.js';
import { CALENDAR_EVENTS } from '@platform/lib/events/reducers/calendar.js';
import { installFetchMock } from '../../helpers/mock-fetch.js';
import { buildCtx } from '../../helpers/bus-fixtures.js';

let fetchMock;
beforeEach(() => { fetchMock = installFetchMock(); });
afterEach(() => fetchMock.uninstall());

const ev = (type, payload) => ({ id: `id_${type}`, type, payload, meta: { ts: 0, source: 'local' } });

describe('calendarEffect', () => {
    it('EVENTS_LOAD_REQUESTED → EVENTS_LOADED + INTEGRATIONS_LOADED', async () => {
        fetchMock.respondJson('POST', '/svc/api/calendar/events/list', { events: [{ id: 'e1' }], integrations: [{ provider: 'google' }] });
        const dispatched = [];
        await createCalendarEffect({ baseUrl: '/svc' })(ev(CALENDAR_EVENTS.EVENTS_LOAD_REQUESTED, {}), buildCtx(() => ({}), dispatched));
        expect(dispatched.find((d) => d.type === CALENDAR_EVENTS.EVENTS_LOADED).payload.items).toEqual([{ id: 'e1' }]);
        expect(dispatched.find((d) => d.type === CALENDAR_EVENTS.INTEGRATIONS_LOADED)).toBeTruthy();
    });

    it('EVENTS_LOAD_REQUESTED ошибка shape → EVENTS_LOAD_FAILED', async () => {
        fetchMock.respondJson('POST', '/svc/api/calendar/events/list', { wrong: true });
        const dispatched = [];
        await createCalendarEffect({ baseUrl: '/svc' })(ev(CALENDAR_EVENTS.EVENTS_LOAD_REQUESTED, {}), buildCtx(() => ({}), dispatched));
        expect(dispatched.find((d) => d.type === CALENDAR_EVENTS.EVENTS_LOAD_FAILED)).toBeTruthy();
    });

    it('EVENT_CREATE_REQUESTED → EVENT_CREATED', async () => {
        fetchMock.respondJson('POST', '/svc/api/calendar/events', { id: 'e1', title: 'M' });
        const dispatched = [];
        await createCalendarEffect({ baseUrl: '/svc' })(ev(CALENDAR_EVENTS.EVENT_CREATE_REQUESTED, { title: 'M' }), buildCtx(() => ({}), dispatched));
        const created = dispatched.find((d) => d.type === CALENDAR_EVENTS.EVENT_CREATED);
        expect(created.payload.event).toEqual({ id: 'e1', title: 'M' });
    });

    it('EVENT_UPDATE_REQUESTED требует event_id', async () => {
        await expect(createCalendarEffect({ baseUrl: '/svc' })(ev(CALENDAR_EVENTS.EVENT_UPDATE_REQUESTED, {}), buildCtx(() => ({}), []))).rejects.toThrow(/event_id/);
    });

    it('EVENT_DELETE_REQUESTED требует event_id', async () => {
        await expect(createCalendarEffect({ baseUrl: '/svc' })(ev(CALENDAR_EVENTS.EVENT_DELETE_REQUESTED, {}), buildCtx(() => ({}), []))).rejects.toThrow(/event_id/);
    });

    it('EVENT_DELETE_REQUESTED 204 → EVENT_DELETED', async () => {
        fetchMock.respondStatus('DELETE', '/svc/api/calendar/events/e1', 204);
        const dispatched = [];
        await createCalendarEffect({ baseUrl: '/svc' })(ev(CALENDAR_EVENTS.EVENT_DELETE_REQUESTED, { event_id: 'e1' }), buildCtx(() => ({}), dispatched));
        expect(dispatched.find((d) => d.type === CALENDAR_EVENTS.EVENT_DELETED).payload.event_id).toBe('e1');
    });

    it('INTEGRATIONS_LOAD_REQUESTED → INTEGRATIONS_LOADED', async () => {
        fetchMock.respondJson('GET', '/svc/api/calendar/integrations', { items: [{ provider: 'apple' }] });
        const dispatched = [];
        await createCalendarEffect({ baseUrl: '/svc' })(ev(CALENDAR_EVENTS.INTEGRATIONS_LOAD_REQUESTED, null), buildCtx(() => ({}), dispatched));
        expect(dispatched.find((d) => d.type === CALENDAR_EVENTS.INTEGRATIONS_LOADED).payload.items).toEqual([{ provider: 'apple' }]);
    });

    it('INTEGRATION_DISCONNECT_REQUESTED требует provider', async () => {
        await expect(createCalendarEffect({ baseUrl: '/svc' })(ev(CALENDAR_EVENTS.INTEGRATION_DISCONNECT_REQUESTED, {}), buildCtx(() => ({}), []))).rejects.toThrow(/provider/);
    });

    it('SYNC_REQUESTED → SYNC_COMPLETED', async () => {
        fetchMock.respondJson('POST', '/svc/api/calendar/sync', {});
        const dispatched = [];
        await createCalendarEffect({ baseUrl: '/svc' })(ev(CALENDAR_EVENTS.SYNC_REQUESTED, {}), buildCtx(() => ({}), dispatched));
        expect(dispatched.find((d) => d.type === CALENDAR_EVENTS.SYNC_COMPLETED)).toBeTruthy();
    });

    it('SYNC_REQUESTED при ошибке → SYNC_FAILED', async () => {
        fetchMock.respondStatus('POST', '/svc/api/calendar/sync', 500);
        const dispatched = [];
        await createCalendarEffect({ baseUrl: '/svc' })(ev(CALENDAR_EVENTS.SYNC_REQUESTED, {}), buildCtx(() => ({}), dispatched));
        expect(dispatched.find((d) => d.type === CALENDAR_EVENTS.SYNC_FAILED)).toBeTruthy();
    });
});
