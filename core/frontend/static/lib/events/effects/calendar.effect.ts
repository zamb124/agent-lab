/**
 * Эффект calendar — события, интеграции, синхронизация.
 */

import { httpRequest } from '../http.js';
import type { PlatformEvent, EffectCtx } from '../contract.js';
import { isPlainRecord, recordField, payloadFields, stringField } from '../payload.js';
import { CALENDAR_EVENTS } from '../reducers/calendar.js';

function errorMessage(err: unknown): string {
    if (err instanceof Error && err.message.length > 0) return err.message;
    if (isPlainRecord(err) && typeof err.message === 'string' && err.message.length > 0) return err.message;
    throw new Error('calendar: failure has no message');
}

function unknownItems(value: unknown[]): unknown[] {
    const items: unknown[] = [];
    for (const item of value) items.push(item);
    return items;
}

export function createCalendarEffect({ baseUrl }: { baseUrl?: string }): (event: PlatformEvent, ctx: EffectCtx) => Promise<void> {
    const base = baseUrl === undefined ? '' : baseUrl;
    return async function calendarEffect(event: PlatformEvent, ctx: EffectCtx): Promise<void> {
        switch (event.type) {
            case CALENDAR_EVENTS.EVENTS_LOAD_REQUESTED: {
                const payload = payloadFields(event);
                const startAt = payload.start_at;
                const endAt = payload.end_at;
                const sources = Array.isArray(payload.include_sources) ? payload.include_sources : null;
                const limit = payload.limit;
                try {
                    const data = await httpRequest({
                        method: 'POST',
                        url: `${base}/api/calendar/events/list`,
                        body: { start_at: startAt, end_at: endAt, include_sources: sources, limit: typeof limit === 'number' ? limit : 1000 },
                    });
                    if (!isPlainRecord(data) || !Array.isArray(data.events)) {
                        throw new Error('calendar.events.list: events must be array');
                    }
                    ctx.dispatch(CALENDAR_EVENTS.EVENTS_LOADED, { items: unknownItems(data.events) }, { causation_id: event.id, source: 'http' });
                    if (Array.isArray(data.integrations)) {
                        ctx.dispatch(CALENDAR_EVENTS.INTEGRATIONS_LOADED, { items: unknownItems(data.integrations) }, { causation_id: event.id, source: 'http' });
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
                const payload = payloadFields(event);
                const id = stringField(payload.event_id);
                if (id === null) throw new Error('calendar.effect: event_id required');
                const rest: Record<string, unknown> = { ...payload };
                delete rest.event_id;
                try {
                    const ev = await httpRequest({ method: 'PUT', url: `${base}/api/calendar/events/${encodeURIComponent(id)}`, body: rest });
                    ctx.dispatch(CALENDAR_EVENTS.EVENT_UPDATED, { event: ev }, { causation_id: event.id, source: 'http' });
                } catch (err) {
                    ctx.dispatch(CALENDAR_EVENTS.EVENT_UPDATE_FAILED, { event_id: id, message: errorMessage(err) }, { causation_id: event.id, source: 'http' });
                }
                return;
            }
            case CALENDAR_EVENTS.EVENT_DELETE_REQUESTED: {
                const id = stringField(payloadFields(event).event_id);
                if (id === null) throw new Error('calendar.effect: event_id required');
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
                    if (!isPlainRecord(data) || !Array.isArray(data.items)) {
                        throw new Error('calendar.integrations: items must be array');
                    }
                    ctx.dispatch(CALENDAR_EVENTS.INTEGRATIONS_LOADED, { items: unknownItems(data.items) }, { causation_id: event.id, source: 'http' });
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
                const integrationId = stringField(payloadFields(event).integration_id);
                if (integrationId === null) throw new Error('calendar.effect: integration_id required');
                try {
                    await httpRequest({ method: 'DELETE', url: `${base}/api/calendar/integrations/${encodeURIComponent(integrationId)}` });
                    ctx.dispatch(CALENDAR_EVENTS.INTEGRATION_DISCONNECTED, { integration_id: integrationId }, { causation_id: event.id, source: 'http' });
                } catch (err) {
                    ctx.dispatch(CALENDAR_EVENTS.INTEGRATION_DISCONNECT_FAILED, { integration_id: integrationId, message: errorMessage(err) }, { causation_id: event.id, source: 'http' });
                }
                return;
            }
            case CALENDAR_EVENTS.SYNC_REQUESTED: {
                try {
                    await httpRequest({ method: 'POST', url: `${base}/api/calendar/sync`, body: recordField(event.payload, 'calendar.sync') });
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
