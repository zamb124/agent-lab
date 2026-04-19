/**
 * Notifications slice — inbox-уведомления, приходящие с сервера через
 * WS-канал ui_events. Любое событие с типом, начинающимся с `notify/`,
 * добавляется в inbox.
 *
 * state.notifications:
 *   list:   Array<{ id, type, scope, kind, title, message, ts, action_url, data }>
 *   unread: number
 */

const NOTIFY_PREFIX = 'notify/';

export const NOTIFICATIONS_EVENTS = Object.freeze({
    READ:       'ui/notification/read',
    DISMISS:    'ui/notification/dismiss',
    DISMISS_ALL:'ui/notification/dismiss_all',
});

export const initialNotificationsState = Object.freeze({
    list: [],
    unread: 0,
});

let _seq = 0;
function _nextId() { _seq += 1; return `n_${_seq.toString(36)}`; }

export function notificationsReducer(state = initialNotificationsState, event) {
    if (typeof event.type === 'string' && event.type.startsWith(NOTIFY_PREFIX)) {
        const segments = event.type.split('/');
        const scope = segments[1] || 'unknown';
        const kindRaw = segments[2] || 'event';
        const kind = kindRaw.replace(/_received$/, '');
        const p = event.payload || {};
        const item = {
            id: _nextId(),
            type: event.type,
            scope,
            kind,
            title: p.title || '',
            message: p.message || '',
            ts: event.meta.ts,
            action_url: p.action_url || null,
            data: p.data || {},
            read: false,
        };
        return { ...state, list: [item, ...state.list], unread: state.unread + 1 };
    }
    switch (event.type) {
        case NOTIFICATIONS_EVENTS.READ: {
            const id = event.payload && event.payload.id;
            if (!id) return state;
            let unreadDelta = 0;
            const list = state.list.map((n) => {
                if (n.id !== id) return n;
                if (!n.read) unreadDelta -= 1;
                return { ...n, read: true };
            });
            return { ...state, list, unread: Math.max(0, state.unread + unreadDelta) };
        }
        case NOTIFICATIONS_EVENTS.DISMISS: {
            const id = event.payload && event.payload.id;
            if (!id) return state;
            const target = state.list.find((n) => n.id === id);
            if (!target) return state;
            const list = state.list.filter((n) => n.id !== id);
            const unread = Math.max(0, state.unread - (target.read ? 0 : 1));
            return { ...state, list, unread };
        }
        case NOTIFICATIONS_EVENTS.DISMISS_ALL:
            return { list: [], unread: 0 };
        default:
            return state;
    }
}

export const notificationsSlice = { reducer: notificationsReducer, initial: initialNotificationsState };
