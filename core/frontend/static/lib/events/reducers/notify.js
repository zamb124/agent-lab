/**
 * Слайс notify (toast-уведомления).
 *
 * Поля state.notify:
 *   toasts: Array<{ id, type, message, duration, ts }>
 */

import { CoreEvents } from '../contract.js';

export const initialNotifyState = Object.freeze({
    toasts: [],
});

let _toastSeq = 0;
function _nextToastId() {
    _toastSeq += 1;
    return `toast_${_toastSeq.toString(36)}`;
}

export function notifyReducer(state = initialNotifyState, event) {
    switch (event.type) {
        case CoreEvents.UI_TOAST_SHOW: {
            const p = event.payload || {};
            const hasMessage = typeof p.message === 'string' && p.message.length > 0;
            const hasI18nKey = typeof p.i18n_key === 'string' && p.i18n_key.length > 0;
            if (!hasMessage && !hasI18nKey) return state;
            const toast = {
                id: p.id || _nextToastId(),
                type: p.type || 'info',
                message: hasMessage ? p.message : '',
                i18n_key: hasI18nKey ? p.i18n_key : null,
                i18n_vars: p.i18n_vars || null,
                duration: typeof p.duration === 'number' ? p.duration : 3000,
                ts: event.meta.ts,
            };
            return { ...state, toasts: [...state.toasts, toast] };
        }
        case CoreEvents.UI_TOAST_DISMISS: {
            const id = event.payload && event.payload.id;
            if (!id) return state;
            const next = state.toasts.filter((t) => t.id !== id);
            if (next.length === state.toasts.length) return state;
            return { ...state, toasts: next };
        }
        case CoreEvents.UI_TOAST_CLEAR:
            return state.toasts.length === 0 ? state : { ...state, toasts: [] };
        default:
            return state;
    }
}
