import { describe, it, expect } from 'vitest';
import { notificationsReducer, initialNotificationsState, NOTIFICATIONS_EVENTS, notificationsSlice } from '@platform/lib/events/reducers/notifications.js';

const ev = (type, payload, ts = 1000) => ({ id: `id_${type}`, type, payload, meta: { ts, source: 'ws' } });

describe('notificationsReducer', () => {
    it('initial', () => {
        expect(initialNotificationsState).toEqual({ list: [], unread: 0 });
        expect(notificationsSlice.initial).toBe(initialNotificationsState);
    });

    it('любое notify/* добавляется в inbox', () => {
        const next = notificationsReducer(initialNotificationsState, ev('notify/sync/sync_new_message_received', {
            title: 'Hi',
            message: 'hello',
            title_i18n_key: 'sync:notifications.message_title',
            message_i18n_key: 'sync:notifications.message_body',
            action_url: '/sync',
            actions: [{ label: 'Open channel', url: '/sync?channel=c1' }],
            data: { x: 1 },
        }, 555));
        expect(next.list).toHaveLength(1);
        expect(next.list[0]).toMatchObject({
            scope: 'sync',
            kind: 'sync_new_message',
            title: 'Hi',
            message: 'hello',
            title_i18n_key: 'sync:notifications.message_title',
            message_i18n_key: 'sync:notifications.message_body',
            ts: 555,
            action_url: '/sync',
            actions: [{ label: 'Open channel', url: '/sync?channel=c1' }],
            read: false,
        });
        expect(next.unread).toBe(1);
    });

    it('notify без _received сохраняет kind', () => {
        const next = notificationsReducer(initialNotificationsState, ev('notify/crm/note_created', { title: 'N' }));
        expect(next.list[0].kind).toBe('note_created');
    });

    it('READ помечает read и уменьшает unread', () => {
        const seeded = notificationsReducer(initialNotificationsState, ev('notify/x/y_received', { title: 't' }));
        const id = seeded.list[0].id;
        const next = notificationsReducer(seeded, ev(NOTIFICATIONS_EVENTS.READ, { id }));
        expect(next.list[0].read).toBe(true);
        expect(next.unread).toBe(0);
    });

    it('READ повторный — без изменения unread', () => {
        let s = notificationsReducer(initialNotificationsState, ev('notify/x/y', { title: 't' }));
        const id = s.list[0].id;
        s = notificationsReducer(s, ev(NOTIFICATIONS_EVENTS.READ, { id }));
        const next = notificationsReducer(s, ev(NOTIFICATIONS_EVENTS.READ, { id }));
        expect(next.unread).toBe(0);
    });

    it('DISMISS убирает уведомление и корректирует unread', () => {
        let s = notificationsReducer(initialNotificationsState, ev('notify/x/y', { title: 't1' }));
        s = notificationsReducer(s, ev('notify/x/y', { title: 't2' }));
        expect(s.unread).toBe(2);
        const targetId = s.list[0].id;
        const next = notificationsReducer(s, ev(NOTIFICATIONS_EVENTS.DISMISS, { id: targetId }));
        expect(next.list).toHaveLength(1);
        expect(next.unread).toBe(1);
    });

    it('DISMISS_ALL обнуляет', () => {
        let s = notificationsReducer(initialNotificationsState, ev('notify/x/y', { title: 't1' }));
        s = notificationsReducer(s, ev('notify/x/y', { title: 't2' }));
        const next = notificationsReducer(s, ev(NOTIFICATIONS_EVENTS.DISMISS_ALL, null));
        expect(next).toEqual({ list: [], unread: 0 });
    });
});
