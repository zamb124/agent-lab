import { describe, it, expect } from 'vitest';
import { calendarReducer, initialCalendarState, CALENDAR_EVENTS, calendarSlice } from '@platform/lib/events/reducers/calendar.js';

const ev = (type, payload = null) => ({ id: `id_${type}`, type, payload, meta: { ts: 0, source: 'local' } });

describe('calendarReducer', () => {
    it('initial', () => {
        expect(initialCalendarState.events).toEqual([]);
        expect(initialCalendarState.integrations).toEqual([]);
        expect(calendarSlice.initial).toBe(initialCalendarState);
    });

    it('EVENTS_LOAD_REQUESTED → loading=true', () => {
        expect(calendarReducer(initialCalendarState, ev(CALENDAR_EVENTS.EVENTS_LOAD_REQUESTED)).loading).toBe(true);
    });

    it('EVENTS_LOADED заполняет events; без массива — throw', () => {
        const next = calendarReducer(initialCalendarState, ev(CALENDAR_EVENTS.EVENTS_LOADED, { items: [{ id: 'e1' }] }));
        expect(next.events).toEqual([{ id: 'e1' }]);
        expect(() => calendarReducer(initialCalendarState, ev(CALENDAR_EVENTS.EVENTS_LOADED, {}))).toThrow(/items/);
    });

    it('EVENT_CREATED добавляет', () => {
        const next = calendarReducer(initialCalendarState, ev(CALENDAR_EVENTS.EVENT_CREATED, { event: { id: 'e1' } }));
        expect(next.events).toEqual([{ id: 'e1' }]);
    });

    it('EVENT_UPDATED заменяет по id', () => {
        const seeded = calendarReducer(initialCalendarState, ev(CALENDAR_EVENTS.EVENT_CREATED, { event: { id: 'e1', title: 'a' } }));
        const next = calendarReducer(seeded, ev(CALENDAR_EVENTS.EVENT_UPDATED, { event: { id: 'e1', title: 'b' } }));
        expect(next.events[0].title).toBe('b');
    });

    it('EVENT_DELETED удаляет', () => {
        const seeded = calendarReducer(initialCalendarState, ev(CALENDAR_EVENTS.EVENT_CREATED, { event: { id: 'e1' } }));
        const next = calendarReducer(seeded, ev(CALENDAR_EVENTS.EVENT_DELETED, { event_id: 'e1' }));
        expect(next.events).toEqual([]);
    });

    it('INTEGRATIONS_LOADED + INTEGRATION_DISCONNECTED', () => {
        const a = calendarReducer(initialCalendarState, ev(CALENDAR_EVENTS.INTEGRATIONS_LOADED, { items: [{ provider: 'google' }, { provider: 'apple' }] }));
        expect(a.integrations).toHaveLength(2);
        const b = calendarReducer(a, ev(CALENDAR_EVENTS.INTEGRATION_DISCONNECTED, { provider: 'google' }));
        expect(b.integrations).toEqual([{ provider: 'apple' }]);
    });

    it('SYNC флаг', () => {
        const a = calendarReducer(initialCalendarState, ev(CALENDAR_EVENTS.SYNC_REQUESTED));
        expect(a.syncing).toBe(true);
        const b = calendarReducer(a, ev(CALENDAR_EVENTS.SYNC_COMPLETED));
        expect(b.syncing).toBe(false);
        const c = calendarReducer(a, ev(CALENDAR_EVENTS.SYNC_FAILED));
        expect(c.syncing).toBe(false);
    });
});
