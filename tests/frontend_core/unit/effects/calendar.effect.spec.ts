import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { createCalendarEffect } from '@platform/lib/events/effects/calendar.effect.js';
import { CALENDAR_EVENTS } from '@platform/lib/events/reducers/calendar.js';
import { installFetchMock } from '../../helpers/mock-fetch.js';
import { buildCtx } from '../../helpers/bus-fixtures.js';
import type { PlatformEvent } from '../../../../core/frontend/static/lib/events/contract.js';
import type { DispatchedRecord } from '../../helpers/bus-fixtures.js';
import { prop } from '../../helpers/prop.js';

let fetchMock: ReturnType<typeof installFetchMock>;
beforeEach(() => { fetchMock = installFetchMock(); });
afterEach(() => fetchMock.uninstall());

const ev = (type: string, payload: unknown): PlatformEvent => ({ id: `id_${type}`, type, payload, meta: { ts: 0, source: 'local', causation_id: null, correlation_id: null, trace_id: null } });

describe('calendarEffect', () => {
    it('EVENTS_LOAD_REQUESTED → EVENTS_LOADED + INTEGRATIONS_LOADED', async () => {
        fetchMock.respondJson('POST', '/svc/api/calendar/events/list', { events: [{ id: 'e1' }], integrations: [{ provider: 'google' }] });
        const dispatched: DispatchedRecord[] = [];
        await createCalendarEffect({ baseUrl: '/svc' })(ev(CALENDAR_EVENTS.EVENTS_LOAD_REQUESTED, {}), buildCtx(() => ({}), dispatched));
        expect(prop(dispatched.find((d) => d.type === CALENDAR_EVENTS.EVENTS_LOADED)?.payload, 'items')).toEqual([{ id: 'e1' }]);
        expect(dispatched.find((d) => d.type === CALENDAR_EVENTS.INTEGRATIONS_LOADED)).toBeTruthy();
    });

    it('EVENTS_LOAD_REQUESTED ошибка shape → EVENTS_LOAD_FAILED', async () => {
        fetchMock.respondJson('POST', '/svc/api/calendar/events/list', { wrong: true });
        const dispatched: DispatchedRecord[] = [];
        await createCalendarEffect({ baseUrl: '/svc' })(ev(CALENDAR_EVENTS.EVENTS_LOAD_REQUESTED, {}), buildCtx(() => ({}), dispatched));
        expect(dispatched.find((d) => d.type === CALENDAR_EVENTS.EVENTS_LOAD_FAILED)).toBeTruthy();
    });

    it('EVENT_CREATE_REQUESTED → EVENT_CREATED', async () => {
        fetchMock.respondJson('POST', '/svc/api/calendar/events', { event_id: 'e1', title: 'M' });
        const dispatched: DispatchedRecord[] = [];
        await createCalendarEffect({ baseUrl: '/svc' })(ev(CALENDAR_EVENTS.EVENT_CREATE_REQUESTED, { title: 'M' }), buildCtx(() => ({}), dispatched));
        const created = dispatched.find((d) => d.type === CALENDAR_EVENTS.EVENT_CREATED);
        expect(prop(created?.payload, 'event')).toEqual({ event_id: 'e1', title: 'M' });
    });

    it('EVENT_UPDATE_REQUESTED требует event_id', async () => {
        await expect(createCalendarEffect({ baseUrl: '/svc' })(ev(CALENDAR_EVENTS.EVENT_UPDATE_REQUESTED, {}), buildCtx(() => ({}), []))).rejects.toThrow(/event_id/);
    });

    it('EVENT_DELETE_REQUESTED требует event_id', async () => {
        await expect(createCalendarEffect({ baseUrl: '/svc' })(ev(CALENDAR_EVENTS.EVENT_DELETE_REQUESTED, {}), buildCtx(() => ({}), []))).rejects.toThrow(/event_id/);
    });

    it('EVENT_DELETE_REQUESTED 204 → EVENT_DELETED', async () => {
        fetchMock.respondStatus('DELETE', '/svc/api/calendar/events/e1', 204);
        const dispatched: DispatchedRecord[] = [];
        await createCalendarEffect({ baseUrl: '/svc' })(ev(CALENDAR_EVENTS.EVENT_DELETE_REQUESTED, { event_id: 'e1' }), buildCtx(() => ({}), dispatched));
        expect(prop(dispatched.find((d) => d.type === CALENDAR_EVENTS.EVENT_DELETED)?.payload, 'event_id')).toBe('e1');
    });

    it('INTEGRATION_CONNECT_REQUESTED (caldav) → INTEGRATION_CONNECTED, forwards caldav_base_url', async () => {
        fetchMock.respondJson('POST', '/svc/api/calendar/integrations/connect', { provider: 'caldav' });
        const dispatched: DispatchedRecord[] = [];
        const payload = { provider: 'caldav', username: 'u@example.com', access_token: 'p', caldav_base_url: 'https://dav.example.com' };
        await createCalendarEffect({ baseUrl: '/svc' })(ev(CALENDAR_EVENTS.INTEGRATION_CONNECT_REQUESTED, payload), buildCtx(() => ({}), dispatched));
        expect(dispatched.find((d) => d.type === CALENDAR_EVENTS.INTEGRATION_CONNECTED)).toBeTruthy();
        const connectCall = fetchMock.calls.find((c) => c.method === 'POST' && c.url === '/svc/api/calendar/integrations/connect');
        const sentBody = JSON.parse(String(connectCall?.init?.body ?? 'null'));
        expect(prop(sentBody, 'caldav_base_url')).toBe('https://dav.example.com');
        expect(prop(sentBody, 'provider')).toBe('caldav');
    });

    it('INTEGRATIONS_LOAD_REQUESTED → INTEGRATIONS_LOADED', async () => {
        fetchMock.respondJson('GET', '/svc/api/calendar/integrations', { items: [{ provider: 'apple' }] });
        const dispatched: DispatchedRecord[] = [];
        await createCalendarEffect({ baseUrl: '/svc' })(ev(CALENDAR_EVENTS.INTEGRATIONS_LOAD_REQUESTED, null), buildCtx(() => ({}), dispatched));
        expect(prop(dispatched.find((d) => d.type === CALENDAR_EVENTS.INTEGRATIONS_LOADED)?.payload, 'items')).toEqual([{ provider: 'apple' }]);
    });

    it('INTEGRATION_DISCONNECT_REQUESTED требует integration_id', async () => {
        await expect(createCalendarEffect({ baseUrl: '/svc' })(ev(CALENDAR_EVENTS.INTEGRATION_DISCONNECT_REQUESTED, {}), buildCtx(() => ({}), []))).rejects.toThrow(/integration_id/);
    });

    it('INTEGRATION_DISCONNECT_REQUESTED удаляет интеграцию по integration_id', async () => {
        fetchMock.respondJson('DELETE', '/svc/api/calendar/integrations/int-1', { success: true });
        const dispatched: DispatchedRecord[] = [];
        await createCalendarEffect({ baseUrl: '/svc' })(
            ev(CALENDAR_EVENTS.INTEGRATION_DISCONNECT_REQUESTED, { integration_id: 'int-1' }),
            buildCtx(() => ({}), dispatched),
        );
        const done = dispatched.find((d) => d.type === CALENDAR_EVENTS.INTEGRATION_DISCONNECTED);
        expect(prop(done?.payload, 'integration_id')).toBe('int-1');
    });

    it('SYNC_REQUESTED → SYNC_COMPLETED', async () => {
        fetchMock.respondJson('POST', '/svc/api/calendar/sync', {});
        const dispatched: DispatchedRecord[] = [];
        await createCalendarEffect({ baseUrl: '/svc' })(ev(CALENDAR_EVENTS.SYNC_REQUESTED, {}), buildCtx(() => ({}), dispatched));
        expect(dispatched.find((d) => d.type === CALENDAR_EVENTS.SYNC_COMPLETED)).toBeTruthy();
    });

    it('SYNC_REQUESTED при ошибке → SYNC_FAILED', async () => {
        fetchMock.respondStatus('POST', '/svc/api/calendar/sync', 500);
        const dispatched: DispatchedRecord[] = [];
        await createCalendarEffect({ baseUrl: '/svc' })(ev(CALENDAR_EVENTS.SYNC_REQUESTED, {}), buildCtx(() => ({}), dispatched));
        expect(dispatched.find((d) => d.type === CALENDAR_EVENTS.SYNC_FAILED)).toBeTruthy();
    });
});
