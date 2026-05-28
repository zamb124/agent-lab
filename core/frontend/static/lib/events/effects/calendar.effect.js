/**
 * Эффект calendar — события, интеграции, синхронизация.
 */

import { httpRequest } from '../http.js';
import { CALENDAR_EVENTS } from '../reducers/calendar.js';

function errorMessage(err) {
    return String(err && err.message ? err.message : err);
}

export function createCalendarEffect({ baseUrl }) {
    const base = baseUrl || '';
    return async function calendarEffect(event, ctx) {
        switch (event.type) {
            case CALENDAR_EVENTS.EVENTS_LOAD_REQUESTED: {
                const { start_at: startAt, end_at: endAt, include_sources: sources, limit } = event.payload || {};
                try {
                    const data = await httpRequest({
                        method: 'POST',
                        url: `${base}/api/calendar/events/list`,
                        body: { start_at: startAt, end_at: endAt, include_sources: sources || null, limit: typeof limit === 'number' ? limit : 1000 },
                    });
                    if (!data || !Array.isArray(data.events)) {
                        throw new Error('calendar.events.list: events must be array');
                    }
                    ctx.dispatch(CALENDAR_EVENTS.EVENTS_LOADED, { items: data.events }, { causation_id: event.id, source: 'http' });
                    if (Array.isArray(data.integrations)) {
                        ctx.dispatch(CALENDAR_EVENTS.INTEGRATIONS_LOADED, { items: data.integrations }, { causation_id: event.id, source: 'http' });
                    }
                } catch (err) {
                    ctx.dispatch(CALENDAR_EVENTS.EVENTS_LOAD_FAILED, { message: errorMessage(err) }, { causation_id: event.id, source: 'http' });
                }
                return;
            }
            case CALENDAR_EVENTS.EVENT_CREATE_REQUESTED: {
                try {
                    const ev = await httpRequest({ method: 'POST', url: `${base}/api/calendar/events`, body: event.payload });
                    ctx.dispatch(CALENDAR_EVENTS.EVENT_CREATED, { event: ev }, { causation_id: event.id, source: 'http' });
                } catch (err) {
                    ctx.dispatch(CALENDAR_EVENTS.EVENT_CREATE_FAILED, { message: errorMessage(err) }, { causation_id: event.id, source: 'http' });
                }
                return;
            }
            case CALENDAR_EVENTS.EVENT_UPDATE_REQUESTED: {
                const { event_id: id, ...rest } = event.payload || {};
                if (!id) throw new Error('calendar.effect: event_id required');
                try {
                    const ev = await httpRequest({ method: 'PUT', url: `${base}/api/calendar/events/${encodeURIComponent(id)}`, body: rest });
                    ctx.dispatch(CALENDAR_EVENTS.EVENT_UPDATED, { event: ev }, { causation_id: event.id, source: 'http' });
                } catch (err) {
                    ctx.dispatch(CALENDAR_EVENTS.EVENT_UPDATE_FAILED, { event_id: id, message: errorMessage(err) }, { causation_id: event.id, source: 'http' });
                }
                return;
            }
            case CALENDAR_EVENTS.EVENT_DELETE_REQUESTED: {
                const id = event.payload && event.payload.event_id;
                if (!id) throw new Error('calendar.effect: event_id required');
                try {
                    await httpRequest({ method: 'DELETE', url: `${base}/api/calendar/events/${encodeURIComponent(id)}` });
                    ctx.dispatch(CALENDAR_EVENTS.EVENT_DELETED, { event_id: id }, { causation_id: event.id, source: 'http' });
                } catch (err) {
                    ctx.dispatch(CALENDAR_EVENTS.EVENT_DELETE_FAILED, { event_id: id, message: errorMessage(err) }, { causation_id: event.id, source: 'http' });
                }
                return;
            }
            case CALENDAR_EVENTS.INTEGRATIONS_LOAD_REQUESTED: {
                try {
                    const data = await httpRequest({ method: 'GET', url: `${base}/api/calendar/integrations` });
                    if (!data || !Array.isArray(data.items)) {
                        throw new Error('calendar.integrations: items must be array');
                    }
                    ctx.dispatch(CALENDAR_EVENTS.INTEGRATIONS_LOADED, { items: data.items }, { causation_id: event.id, source: 'http' });
                } catch (err) {
                    ctx.dispatch(CALENDAR_EVENTS.INTEGRATIONS_LOAD_FAILED, { message: errorMessage(err) }, { causation_id: event.id, source: 'http' });
                }
                return;
            }
            case CALENDAR_EVENTS.INTEGRATION_CONNECT_REQUESTED: {
                try {
                    const integration = await httpRequest({ method: 'POST', url: `${base}/api/calendar/integrations/connect`, body: event.payload });
                    ctx.dispatch(CALENDAR_EVENTS.INTEGRATION_CONNECTED, { integration }, { causation_id: event.id, source: 'http' });
                } catch (err) {
                    ctx.dispatch(CALENDAR_EVENTS.INTEGRATION_CONNECT_FAILED, { message: errorMessage(err) }, { causation_id: event.id, source: 'http' });
                }
                return;
            }
            case CALENDAR_EVENTS.INTEGRATION_DISCONNECT_REQUESTED: {
                const provider = event.payload && event.payload.provider;
                if (!provider) throw new Error('calendar.effect: provider required');
                try {
                    await httpRequest({ method: 'DELETE', url: `${base}/api/calendar/integrations/${encodeURIComponent(provider)}` });
                    ctx.dispatch(CALENDAR_EVENTS.INTEGRATION_DISCONNECTED, { provider }, { causation_id: event.id, source: 'http' });
                } catch (err) {
                    ctx.dispatch(CALENDAR_EVENTS.INTEGRATION_DISCONNECT_FAILED, { provider, message: errorMessage(err) }, { causation_id: event.id, source: 'http' });
                }
                return;
            }
            case CALENDAR_EVENTS.SYNC_REQUESTED: {
                try {
                    await httpRequest({ method: 'POST', url: `${base}/api/calendar/sync`, body: event.payload || {} });
                    ctx.dispatch(CALENDAR_EVENTS.SYNC_COMPLETED, null, { causation_id: event.id, source: 'http' });
                } catch (err) {
                    ctx.dispatch(CALENDAR_EVENTS.SYNC_FAILED, { message: errorMessage(err) }, { causation_id: event.id, source: 'http' });
                }
                return;
            }
            default:
                return;
        }
    };
}
