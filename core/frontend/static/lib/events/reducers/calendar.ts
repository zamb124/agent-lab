/**
 * Слайс calendar.
 *
 * state.calendar:
 *   events:       Array
 *   integrations: Array
 *   loading:      boolean
 *   syncing:      boolean
 */

export const CALENDAR_EVENTS = Object.freeze({
    EVENTS_LOAD_REQUESTED: 'calendar/events/load_requested',
    EVENTS_LOADED:         'calendar/events/loaded',
    EVENTS_LOAD_FAILED:    'calendar/events/load_failed',
    EVENT_CREATE_REQUESTED:'calendar/event/create_requested',
    EVENT_CREATED:         'calendar/event/created',
    EVENT_CREATE_FAILED:   'calendar/event/create_failed',
    EVENT_UPDATE_REQUESTED:'calendar/event/update_requested',
    EVENT_UPDATED:         'calendar/event/updated',
    EVENT_UPDATE_FAILED:   'calendar/event/update_failed',
    EVENT_DELETE_REQUESTED:'calendar/event/delete_requested',
    EVENT_DELETED:         'calendar/event/deleted',
    EVENT_DELETE_FAILED:   'calendar/event/delete_failed',
    INTEGRATIONS_LOAD_REQUESTED:'calendar/integrations/load_requested',
    INTEGRATIONS_LOADED:   'calendar/integrations/loaded',
    INTEGRATIONS_LOAD_FAILED:'calendar/integrations/load_failed',
    INTEGRATION_CONNECT_REQUESTED:'calendar/integration/connect_requested',
    INTEGRATION_CONNECTED: 'calendar/integration/connected',
    INTEGRATION_CONNECT_FAILED:'calendar/integration/connect_failed',
    INTEGRATION_DISCONNECT_REQUESTED:'calendar/integration/disconnect_requested',
    INTEGRATION_DISCONNECTED:'calendar/integration/disconnected',
    INTEGRATION_DISCONNECT_FAILED:'calendar/integration/disconnect_failed',
    SYNC_REQUESTED:        'calendar/sync/run_requested',
    SYNC_COMPLETED:        'calendar/sync/completed',
    SYNC_FAILED:           'calendar/sync/failed',
});

import type { PlatformEvent } from '../contract.js';

export interface CalendarEventRecord extends Record<string, unknown> {
    event_id?: string;
}

export interface CalendarIntegrationRecord extends Record<string, unknown> {
    integration_id?: string;
}

export interface CalendarState {
    events: CalendarEventRecord[];
    integrations: CalendarIntegrationRecord[];
    loading: boolean;
    syncing: boolean;
}

export const initialCalendarState: CalendarState = Object.freeze({
    events: [],
    integrations: [],
    loading: false,
    syncing: false,
});

function requireItems<T>(payload: unknown, eventType: string): T[] {
    const items = (payload as { items?: unknown } | null)?.items;
    if (!Array.isArray(items)) {
        throw new Error(`${eventType}: payload.items must be an array`);
    }
    return items as T[];
}

function requireCalendarEventId(event: unknown, eventType: string): string {
    if (!event || typeof event !== 'object') {
        throw new Error(`${eventType}: payload.event must be an object`);
    }
    const eventId = (event as { event_id?: unknown }).event_id;
    if (typeof eventId !== 'string' || eventId.length === 0) {
        throw new Error(`${eventType}: payload.event.event_id must be a non-empty string`);
    }
    return eventId;
}

export function calendarReducer(state: CalendarState = initialCalendarState, event: PlatformEvent): CalendarState {
    switch (event.type) {
        case CALENDAR_EVENTS.EVENTS_LOAD_REQUESTED:
            return { ...state, loading: true };
        case CALENDAR_EVENTS.EVENTS_LOADED:
            return { ...state, loading: false, events: requireItems<CalendarEventRecord>(event.payload, event.type) };
        case CALENDAR_EVENTS.EVENTS_LOAD_FAILED:
            return { ...state, loading: false };
        case CALENDAR_EVENTS.EVENT_CREATED: {
            const ev = ((event.payload || {}) as { event?: CalendarEventRecord }).event;
            if (!ev) return state;
            const eventId = requireCalendarEventId(ev, event.type);
            const exists = state.events.some((item) => item.event_id === eventId);
            if (exists) {
                return {
                    ...state,
                    events: state.events.map((item) => (item.event_id === eventId ? ev : item)),
                };
            }
            return { ...state, events: [...state.events, ev] };
        }
        case CALENDAR_EVENTS.EVENT_UPDATED: {
            const ev = ((event.payload || {}) as { event?: CalendarEventRecord }).event;
            if (!ev) return state;
            const eventId = requireCalendarEventId(ev, event.type);
            const exists = state.events.some((item) => item.event_id === eventId);
            if (!exists) {
                return { ...state, events: [...state.events, ev] };
            }
            return {
                ...state,
                events: state.events.map((item) => (item.event_id === eventId ? ev : item)),
            };
        }
        case CALENDAR_EVENTS.EVENT_DELETED: {
            const eventId = ((event.payload || {}) as { event_id?: unknown }).event_id;
            if (typeof eventId !== 'string' || !eventId) return state;
            return { ...state, events: state.events.filter((item) => item.event_id !== eventId) };
        }
        case CALENDAR_EVENTS.INTEGRATIONS_LOADED:
            return { ...state, integrations: requireItems<CalendarIntegrationRecord>(event.payload, event.type) };
        case CALENDAR_EVENTS.INTEGRATION_DISCONNECTED: {
            const integrationId = ((event.payload || {}) as { integration_id?: unknown }).integration_id;
            if (typeof integrationId !== 'string' || !integrationId) return state;
            return {
                ...state,
                integrations: state.integrations.filter((i) => i.integration_id !== integrationId),
            };
        }
        case CALENDAR_EVENTS.SYNC_REQUESTED:
            return { ...state, syncing: true };
        case CALENDAR_EVENTS.SYNC_COMPLETED:
            return { ...state, syncing: false };
        case CALENDAR_EVENTS.SYNC_FAILED:
            return { ...state, syncing: false };
        default:
            return state;
    }
}

export const calendarSlice = { reducer: calendarReducer, initial: initialCalendarState };
