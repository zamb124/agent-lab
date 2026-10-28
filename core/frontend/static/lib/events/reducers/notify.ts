/**
 * Слайс notify (toast-уведомления).
 *
 * Поля state.notify:
 *   toasts: Array<{ id, type, message, duration, ts }>
 */

import { CoreEvents } from '../contract.js';
import type { PlatformEvent } from '../contract.js';
import { isPlainRecord, payloadFields } from '../payload.js';

export interface NotifyToast {
    id: string;
    type: string;
    message: string;
    i18n_key: string | null;
    i18n_vars: Record<string, unknown> | null;
    duration: number;
    ts: number;
}

export interface NotifyState {
    toasts: NotifyToast[];
}

export const initialNotifyState: NotifyState = Object.freeze({
    toasts: [],
});

let _toastSeq = 0;
function _nextToastId() {
    _toastSeq += 1;
    return `toast_${_toastSeq.toString(36)}`;
}

export function notifyReducer(state: NotifyState = initialNotifyState, event: PlatformEvent): NotifyState {
    switch (event.type) {
        case CoreEvents.UI_TOAST_SHOW: {
            const p = payloadFields(event);
            const hasMessage = typeof p.message === 'string' && p.message.length > 0;
            const hasI18nKey = typeof p.i18n_key === 'string' && p.i18n_key.length > 0;
            if (!hasMessage && !hasI18nKey) return state;
            const vars = p.i18n_vars;
            if (vars != null && !isPlainRecord(vars)) {
                throw new Error(`${event.type}: i18n_vars must be an object`);
            }
            const toast = {
                id: typeof p.id === 'string' && p.id ? p.id : _nextToastId(),
                type: typeof p.type === 'string' && p.type ? p.type : 'info',
                message: hasMessage ? (p.message as string) : '',
                i18n_key: hasI18nKey ? (p.i18n_key as string) : null,
                i18n_vars: vars == null ? null : vars,
                duration: typeof p.duration === 'number' ? p.duration : 3000,
                ts: event.meta.ts,
            };
            return { ...state, toasts: [...state.toasts, toast] };
        }
        case CoreEvents.UI_TOAST_DISMISS: {
            const p = payloadFields(event);
            const id = p.id;
            if (typeof id !== 'string' || !id) return state;
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
