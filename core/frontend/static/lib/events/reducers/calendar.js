/**
 * Calendar slice.
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

export const initialCalendarState = Object.freeze({
    events: [],
    integrations: [],
    loading: false,
    syncing: false,
});

function requireItems(payload, eventType) {
    if (!payload || !Array.isArray(payload.items)) {
        throw new Error(`${eventType}: payload.items must be an array`);
    }
    return payload.items;
}

export function calendarReducer(state = initialCalendarState, event) {
    switch (event.type) {
        case CALENDAR_EVENTS.EVENTS_LOAD_REQUESTED:
            return { ...state, loading: true };
        case CALENDAR_EVENTS.EVENTS_LOADED:
            return { ...state, loading: false, events: requireItems(event.payload, event.type) };
        case CALENDAR_EVENTS.EVENTS_LOAD_FAILED:
            return { ...state, loading: false };
        case CALENDAR_EVENTS.EVENT_CREATED: {
            const ev = event.payload && event.payload.event;
            if (!ev) return state;
            return { ...state, events: [...state.events, ev] };
        }
        case CALENDAR_EVENTS.EVENT_UPDATED: {
            const ev = event.payload && event.payload.event;
            if (!ev) return state;
            return { ...state, events: state.events.map((e) => (e.id === ev.id ? ev : e)) };
        }
        case CALENDAR_EVENTS.EVENT_DELETED: {
            const id = event.payload && event.payload.event_id;
            if (!id) return state;
            return { ...state, events: state.events.filter((e) => e.id !== id) };
        }
        case CALENDAR_EVENTS.INTEGRATIONS_LOADED:
            return { ...state, integrations: requireItems(event.payload, event.type) };
        case CALENDAR_EVENTS.INTEGRATION_DISCONNECTED: {
            const provider = event.payload && event.payload.provider;
            return { ...state, integrations: state.integrations.filter((i) => i.provider !== provider) };
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
