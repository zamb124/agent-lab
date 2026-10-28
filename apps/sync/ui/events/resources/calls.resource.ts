/**
 * Звонки Sync — звонки, ссылки, токены, запись.
 *
 * Все операции через WS (single canonical path), кроме UI-state в
 * `createSlice('sync/call_ui')`. Каждая фабрика задаёт явный `commandType`
 * — каноничный backend-handler в `apps/sync/realtime/command_router.py`.
 *
 * REST-зеркала живут в `apps/sync/api/calls.py` и вызывают те же `op_*`.
 */

import {
    createAsyncOp,
    createSlice,
    CoreEvents,
    HttpError,
    WsTransportError,
} from '@platform/lib/events/index.js';
import type { EffectCtx, PlatformEvent } from '@platform/lib/events/contract.js';
import type { AsyncOpSlice } from '@platform/lib/events/factories/async-op.js';
import type { SyncCallUiSlice } from '../sync.types.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';

function callRecord(payload: unknown): Record<string, unknown> | null {
    return isPlainRecord(payload) ? payload : null;
}

function mergeCall(base: Record<string, any> | null, patch: Record<string, unknown>): Record<string, any> {
    const next: Record<string, any> = base === null ? {} : { ...base };
    for (const [key, value] of Object.entries(patch)) {
        next[key] = value;
    }
    return next;
}

/**
 * У `silent: true` фабрика не шлёт errorToastKey; показываем текст ошибки
 * сервера/транспорта (error_detail WS, тело HTTP) в одном тосте.
 */
function _syncOpToastOnFailure(ctx: EffectCtx, err: unknown, event: PlatformEvent) {
    if (!(err instanceof HttpError) && !(err instanceof WsTransportError)) return;
    const msg = typeof err.message === 'string' ? err.message : '';
    if (msg === '') return;
    ctx.dispatch(
        CoreEvents.UI_TOAST_SHOW,
        { type: 'error', message: msg },
        { causation_id: event.id, source: 'local' },
    );
}

// ============================================================================
// Операции чтения звонков
// ============================================================================

export const callTokenOp = createAsyncOp({
    name: 'sync/call_token',
    transport: 'ws',
    wsTimeoutMs: 5_000,
    silent: true,
    onFailure: _syncOpToastOnFailure,
    commandType: 'sync/calls/token_requested',
    restMirror: { method: 'GET', path: '/sync/api/v1/calls/:call_id/token' },
});

export const callStatusOp = createAsyncOp({
    name: 'sync/call_status',
    transport: 'ws',
    wsTimeoutMs: 5_000,
    silent: true,
    onFailure: _syncOpToastOnFailure,
    commandType: 'sync/calls/get_requested',
    restMirror: { method: 'GET', path: '/sync/api/v1/calls/:call_id' },
});

export const callTurnOp = createAsyncOp({
    name: 'sync/call_turn',
    transport: 'ws',
    wsTimeoutMs: 5_000,
    silent: true,
    onFailure: _syncOpToastOnFailure,
    commandType: 'sync/calls/turn_credentials_requested',
    restMirror: { method: 'GET', path: '/sync/api/v1/calls/turn-credentials' },
});

export const callRecordingsListOp = createAsyncOp({
    name: 'sync/call_recordings_list',
    transport: 'ws',
    wsTimeoutMs: 5_000,
    silent: true,
    onFailure: _syncOpToastOnFailure,
    commandType: 'sync/calls/recordings_list_requested',
    restMirror: { method: 'GET', path: '/sync/api/v1/calls/:call_id/recordings' },
});

// ============================================================================
// WS-операции (request-reply через single WS)
// commandType — каноничный backend-handler в `apps/sync/realtime/command_router.py`.
// ============================================================================

export const callInviteOp = createAsyncOp({
    name: 'sync/calls_invite',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    silent: true,
    onFailure: _syncOpToastOnFailure,
    commandType: 'sync/calls/invite_requested',
    restMirror: { method: 'POST', path: '/sync/api/v1/calls/:call_id/invite' },
});

export const callAcceptOp = createAsyncOp({
    name: 'sync/calls_accept',
    transport: 'ws',
    wsTimeoutMs: 5_000,
    silent: true,
    onFailure: _syncOpToastOnFailure,
    commandType: 'sync/calls/accept_requested',
    restMirror: { method: 'POST', path: '/sync/api/v1/calls/:call_id/accept' },
});

export const callDeclineOp = createAsyncOp({
    name: 'sync/calls_decline',
    transport: 'ws',
    wsTimeoutMs: 3_000,
    silent: true,
    onFailure: _syncOpToastOnFailure,
    commandType: 'sync/calls/decline_requested',
    restMirror: { method: 'POST', path: '/sync/api/v1/calls/:call_id/decline' },
});

export const callHangupOp = createAsyncOp({
    name: 'sync/calls_hangup',
    transport: 'ws',
    wsTimeoutMs: 5_000,
    silent: true,
    onFailure: _syncOpToastOnFailure,
    commandType: 'sync/calls/hangup_requested',
    restMirror: { method: 'POST', path: '/sync/api/v1/calls/:call_id/hangup' },
});

export const callRecordingStartOp = createAsyncOp({
    name: 'sync/calls_recording_start',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    silent: true,
    onFailure: _syncOpToastOnFailure,
    commandType: 'sync/calls/recording_start_requested',
    restMirror: { method: 'POST', path: '/sync/api/v1/calls/:call_id/recording/start' },
});

export const callRecordingStopOp = createAsyncOp({
    name: 'sync/calls_recording_stop',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    silent: true,
    onFailure: _syncOpToastOnFailure,
    commandType: 'sync/calls/recording_stop_requested',
    restMirror: { method: 'POST', path: '/sync/api/v1/calls/:call_id/recording/stop' },
});

export const callAdminTransferOp = createAsyncOp({
    name: 'sync/calls_admin_transfer',
    transport: 'ws',
    wsTimeoutMs: 5_000,
    silent: true,
    onFailure: _syncOpToastOnFailure,
    commandType: 'sync/calls/admin_transfer_requested',
    restMirror: { method: 'POST', path: '/sync/api/v1/calls/:call_id/admin/transfer' },
});

export const callSignalOp = createAsyncOp({
    name: 'sync/calls_signal',
    transport: 'ws',
    wsTimeoutMs: 2_000,
    silent: true,
    onFailure: _syncOpToastOnFailure,
    commandType: 'sync/calls/signal_requested',
    restMirror: { method: 'POST', path: '/sync/api/v1/calls/:call_id/signal' },
});

// ============================================================================
// Ad-hoc-встреча: канал создаётся через `sync/channels/create_requested` (WS).
// Сразу после создания UI вызывает `sync/calls_invite` и открывает оверлей
// (`sync-sidebar._startAdhocCallSession`), как кнопка звонка в шапке чата.
// ============================================================================

export const channelCreateAdhocCallOp = createAsyncOp({
    name: 'sync/channel_create_adhoc_call',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    silent: true,
    onFailure: _syncOpToastOnFailure,
    commandType: 'sync/channels/create_requested',
    restMirror: { method: 'POST', path: '/sync/api/v1/channels/' },
});

// ============================================================================
// Календарные ссылки на звонки
// ============================================================================

export const callLinksScheduledOp = createAsyncOp({
    name: 'sync/call_links_scheduled',
    transport: 'ws',
    wsTimeoutMs: 5_000,
    silent: true,
    onFailure: _syncOpToastOnFailure,
    commandType: 'sync/calls/links_list_requested',
    restMirror: { method: 'GET', path: '/sync/api/v1/calls/links/scheduled' },
    extraEvents: {
        ITEM_REMOVED: 'item_removed',
    },
    extraReducer: (state: AsyncOpSlice, event, events) => {
        const page = state.lastResult;
        const items = Array.isArray(page)
            ? page
            : (isPlainRecord(page) && Array.isArray(page.items) ? page.items : null);
        if (items === null) {
            return state;
        }

        if (event.type === events.ITEM_REMOVED) {
            const removed = callRecord(event.payload);
            const linkToken = removed !== null && typeof removed.link_token === 'string'
                ? removed.link_token
                : null;
            if (linkToken === null) {
                return state;
            }
            const nextItems = items.filter((row) => row && row.link_token !== linkToken);
            if (nextItems.length === items.length) {
                return state;
            }
            if (Array.isArray(page)) {
                return { ...state, lastResult: nextItems };
            }
            if (!isPlainRecord(page)) {
                return state;
            }
            return {
                ...state,
                lastResult: { ...page, items: nextItems },
            };
        }

        if (
            event.type !== 'sync/call_link_create/succeeded'
            && event.type !== 'sync/call_link_update/succeeded'
        ) {
            return state;
        }
        const payload = callRecord(event.payload);
        const result = payload !== null ? payload.result : null;
        if (!isPlainRecord(result) || typeof result.link_token !== 'string') {
            return state;
        }
        const idx = items.findIndex((row) => row && row.link_token === result.link_token);
        const nextItems = idx === -1
            ? [result, ...items]
            : items.map((row, i) => (i === idx ? result : row));
        if (Array.isArray(page)) {
            return { ...state, lastResult: nextItems };
        }
        if (!isPlainRecord(page)) {
            return state;
        }
        return {
            ...state,
            lastResult: { ...page, items: nextItems },
        };
    },
});

export const callLinkCreateOp = createAsyncOp({
    name: 'sync/call_link_create',
    transport: 'ws',
    wsTimeoutMs: 5_000,
    successToastKey: 'sync:calls.toast_link_created',
    errorToastKey: 'sync:calls.err_link_create',
    commandType: 'sync/calls/links_create_requested',
    restMirror: { method: 'POST', path: '/sync/api/v1/calls/links' },
});

export const callLinkUpdateOp = createAsyncOp({
    name: 'sync/call_link_update',
    transport: 'ws',
    wsTimeoutMs: 5_000,
    successToastKey: 'sync:calls.toast_link_updated',
    errorToastKey: 'sync:calls.err_link_update',
    commandType: 'sync/calls/links_update_requested',
    restMirror: { method: 'PATCH', path: '/sync/api/v1/calls/links/:link_token' },
});

export const callLinkRemoveOp = createAsyncOp({
    name: 'sync/call_link_remove',
    transport: 'ws',
    wsTimeoutMs: 5_000,
    successToastKey: 'sync:calls.toast_link_removed',
    errorToastKey: 'sync:calls.err_link_remove',
    commandType: 'sync/calls/links_remove_requested',
    restMirror: { method: 'DELETE', path: '/sync/api/v1/calls/links/:link_token' },
    onSuccess: (ctx, _result, event) => {
        const removed = callRecord(event.payload);
        const linkToken = removed !== null && typeof removed.link_token === 'string'
            ? removed.link_token
            : null;
        if (linkToken === null) {
            throw new Error('callLinkRemoveOp.onSuccess: payload.link_token required');
        }
        ctx.dispatch(
            'sync/call_links_scheduled/item_removed',
            { link_token: linkToken },
            { causation_id: event.id, source: 'local' },
        );
    },
});

// ============================================================================
// UI-состояние звонков (slice activeCall, incomingCall, recordingStatus и пр.)
//
// Чистая `createSlice` фабрика без HTTP/WS — slice реагирует на push-события
// `sync/call/*` (server -> client через `platform:events`) и локальные
// UI-действия overlay/incoming.
//
// Компоненты используют `this.useSlice('sync/call_ui')` -> читают `.value`
// и вызывают actions: openOverlay, minimizeOverlay, expandOverlay,
// closeOverlay, dismissIncoming, setRecordingStatus.
// ============================================================================

export const callUiResource = createSlice({
    name: 'sync/call_ui',
    extraInitial: {
        activeCall: null,
        incomingCall: null,
        overlayMinimized: false,
        bannerHangupGuardUntil: 0,
        overlayChatOpen: false,
        recordingStatus: 'idle',
        recordingError: null,
        activeCallChannels: Object.freeze({}),
        /** @type {Record<string, ReadonlyArray<string>>} call_id → participant user_id[] */
        callParticipants: Object.freeze({}),
        /** Последний P2P/LiveKit signal (для peer path; SFU может игнорировать). */
        lastSignal: null,
    },
    extraEvents: {
        OVERLAY_OPENED: 'overlay_opened',
        OVERLAY_MINIMIZED: 'overlay_minimized',
        OVERLAY_EXPANDED: 'overlay_expanded',
        OVERLAY_CLOSED: 'overlay_closed',
        OVERLAY_CHAT_SET: 'overlay_chat_set',
        INCOMING_DISMISSED: 'incoming_dismissed',
        RECORDING_STATUS_SET: 'recording_status_set',
    },
    actions: {
        openOverlay: 'overlay_opened',
        minimizeOverlay: 'overlay_minimized',
        expandOverlay: 'overlay_expanded',
        closeOverlay: 'overlay_closed',
        setOverlayChatOpen: 'overlay_chat_set',
        dismissIncoming: 'incoming_dismissed',
        setRecordingStatus: 'recording_status_set',
    },
    extraReducer: (state: SyncCallUiSlice, event) => {
        const s = state;
        switch (event.type) {
            case 'sync/call/incoming': {
                const p = callRecord(event.payload);
                if (!p || typeof p.call_id !== 'string') return state;
                const callType = typeof p.call_type === 'string' ? p.call_type : 'video';
                const channelId = typeof p.channel_id === 'string' ? p.channel_id : null;
                let callerUserId = null;
                if (typeof p.created_by_user_id === 'string') callerUserId = p.created_by_user_id;
                else if (typeof p.initiator_user_id === 'string') callerUserId = p.initiator_user_id;
                const callerDisplayName = typeof p.caller_display_name === 'string' ? p.caller_display_name : null;
                const channelDisplayName = typeof p.channel_display_name === 'string' ? p.channel_display_name : null;
                const tracker = { ...s.activeCallChannels };
                if (channelId !== null && channelId !== '') {
                    tracker[channelId] = { call_id: p.call_id, call_type: callType };
                }
                return {
                    ...s,
                    incomingCall: {
                        call_id: p.call_id,
                        call_type: callType,
                        channel_id: channelId,
                        caller_user_id: callerUserId,
                        caller_display_name: callerDisplayName,
                        channel_display_name: channelDisplayName,
                    },
                    activeCallChannels: Object.freeze(tracker),
                };
            }
            case 'sync/call_ui/overlay_opened': {
                const p = callRecord(event.payload);
                if (!p || typeof p.call_id !== 'string') return state;
                const tracker = { ...s.activeCallChannels };
                const ch = typeof p.channel_id === 'string' ? p.channel_id : '';
                if (ch !== '') {
                    tracker[ch] = {
                        call_id: p.call_id,
                        call_type: typeof p.call_type === 'string' ? p.call_type : 'video',
                    };
                }
                const isSameCallId =
                    s.activeCall !== null
                    && typeof s.activeCall.call_id === 'string'
                    && s.activeCall.call_id === p.call_id;
                const overlayMinimized = isSameCallId ? s.overlayMinimized : false;
                const activeCall = isSameCallId && s.activeCall
                    ? mergeCall(s.activeCall, p)
                    : mergeCall(null, p);
                return {
                    ...s,
                    activeCall,
                    overlayMinimized,
                    bannerHangupGuardUntil: 0,
                    incomingCall: s.incomingCall && s.incomingCall.call_id === p.call_id
                        ? null
                        : s.incomingCall,
                    activeCallChannels: Object.freeze(tracker),
                };
            }
            case 'sync/call_ui/overlay_minimized': {
                const p = callRecord(event.payload);
                let guard = 0;
                if (p !== null && typeof p === 'object' && typeof p.banner_hangup_guard_until === 'number') {
                    guard = p.banner_hangup_guard_until;
                }
                return { ...s, overlayMinimized: true, bannerHangupGuardUntil: guard };
            }
            case 'sync/call_ui/overlay_expanded':
                return { ...s, overlayMinimized: false, bannerHangupGuardUntil: 0 };
            case 'sync/call_ui/overlay_closed':
                return {
                    ...s,
                    activeCall: null,
                    overlayMinimized: false,
                    bannerHangupGuardUntil: 0,
                    overlayChatOpen: false,
                    recordingStatus: 'idle',
                    recordingError: null,
                };
            case 'sync/call_ui/overlay_chat_set': {
                const p = callRecord(event.payload);
                if (!p || typeof p.open !== 'boolean') return state;
                return { ...s, overlayChatOpen: p.open };
            }
            case 'sync/call_ui/incoming_dismissed':
                return { ...s, incomingCall: null };
            case 'sync/call_ui/recording_status_set': {
                const p = callRecord(event.payload);
                if (!p || typeof p.status !== 'string') return state;
                return {
                    ...s,
                    recordingStatus: p.status,
                    recordingError: typeof p.error === 'string' ? p.error : null,
                };
            }
            case 'sync/call/accepted': {
                const p = callRecord(event.payload);
                if (!p || typeof p.call_id !== 'string') return state;
                const clearIncoming =
                    s.incomingCall && s.incomingCall.call_id === p.call_id
                        ? null
                        : s.incomingCall;
                return { ...s, incomingCall: clearIncoming };
            }
            case 'sync/call/declined': {
                const p = callRecord(event.payload);
                if (!p || typeof p.call_id !== 'string') return state;
                const clearIncoming =
                    s.incomingCall && s.incomingCall.call_id === p.call_id
                        ? null
                        : s.incomingCall;
                return { ...s, incomingCall: clearIncoming };
            }
            case 'sync/call/participant_joined': {
                const p = callRecord(event.payload);
                if (!p || typeof p.call_id !== 'string' || typeof p.user_id !== 'string') {
                    return state;
                }
                const prev: readonly string[] = Array.isArray(s.callParticipants[p.call_id])
                    ? (s.callParticipants[p.call_id] as readonly string[])
                    : [];
                if (prev.includes(p.user_id)) return state;
                return {
                    ...s,
                    callParticipants: Object.freeze({
                        ...s.callParticipants,
                        [p.call_id]: Object.freeze([...prev, p.user_id]),
                    }),
                };
            }
            case 'sync/call/participant_left': {
                const p = callRecord(event.payload);
                if (!p || typeof p.call_id !== 'string' || typeof p.user_id !== 'string') {
                    return state;
                }
                const prev: readonly string[] = Array.isArray(s.callParticipants[p.call_id])
                    ? (s.callParticipants[p.call_id] as readonly string[])
                    : [];
                if (!prev.includes(p.user_id)) return state;
                const nextList = prev.filter((uid) => uid !== p.user_id);
                const nextMap = { ...s.callParticipants };
                if (nextList.length === 0) {
                    delete nextMap[p.call_id];
                } else {
                    nextMap[p.call_id] = Object.freeze(nextList);
                }
                return { ...s, callParticipants: Object.freeze(nextMap) };
            }
            case 'sync/call/signaled': {
                const p = callRecord(event.payload);
                if (!p || typeof p.call_id !== 'string') return state;
                return {
                    ...s,
                    lastSignal: Object.freeze({
                        call_id: p.call_id,
                        signal_type: typeof p.signal_type === 'string' ? p.signal_type : null,
                        sender_user_id:
                            typeof p.sender_user_id === 'string' ? p.sender_user_id : null,
                        target_user_id:
                            typeof p.target_user_id === 'string' ? p.target_user_id : null,
                    }),
                };
            }
            case 'sync/call/ended': {
                const p = callRecord(event.payload);
                if (!p || typeof p.call_id !== 'string') return state;
                const tracker = { ...s.activeCallChannels };
                if (typeof p.channel_id === 'string') delete tracker[p.channel_id];
                const participants = { ...s.callParticipants };
                delete participants[p.call_id];
                return {
                    ...s,
                    activeCall: s.activeCall && s.activeCall.call_id === p.call_id ? null : s.activeCall,
                    incomingCall: s.incomingCall && s.incomingCall.call_id === p.call_id ? null : s.incomingCall,
                    overlayMinimized: s.activeCall && s.activeCall.call_id === p.call_id ? false : s.overlayMinimized,
                    bannerHangupGuardUntil:
                        s.activeCall && s.activeCall.call_id === p.call_id ? 0 : s.bannerHangupGuardUntil,
                    recordingStatus: s.activeCall && s.activeCall.call_id === p.call_id ? 'idle' : s.recordingStatus,
                    activeCallChannels: Object.freeze(tracker),
                    callParticipants: Object.freeze(participants),
                    lastSignal:
                        isPlainRecord(s.lastSignal) && s.lastSignal.call_id === p.call_id
                            ? null
                            : s.lastSignal,
                };
            }
            case 'sync/call/recording_started':
                return { ...s, recordingStatus: 'recording', recordingError: null };
            case 'sync/call/recording_stopped':
                return { ...s, recordingStatus: 'idle', recordingError: null };
            case 'sync/call/recording_failed': {
                const p = callRecord(event.payload);
                return {
                    ...s,
                    recordingStatus: 'failed',
                    recordingError: (p && typeof p.error === 'string') ? p.error : 'recording_failed',
                };
            }
            case 'sync/call/admin_changed': {
                const p = callRecord(event.payload);
                if (!p || !s.activeCall || s.activeCall.call_id !== p.call_id) return state;
                const newAdmin = (typeof p.created_by_user_id === 'string' && p.created_by_user_id !== '')
                    ? p.created_by_user_id
                    : s.activeCall.created_by_user_id;
                return {
                    ...s,
                    activeCall: { ...s.activeCall, created_by_user_id: newAdmin },
                };
            }
            default:
                return state;
        }
    },
});

// ============================================================================
// Гостевая страница входа в звонок (HTTP: сокет у гостя может быть не готов)
// ============================================================================

export const callJoinInfoOp = createAsyncOp({
    name: 'sync/call_join_info',
    transport: 'http',
    silent: true,
    onFailure: _syncOpToastOnFailure,
    restMirror: { method: 'GET', path: '/sync/api/v1/calls/join/:link_token' },
    request: async ({ payload }) => {
        const { httpRequest } = await import('@platform/lib/events/http.js');
        const pl = callRecord(payload);
        if (pl === null || typeof pl.link_token !== 'string' || pl.link_token === '') {
            throw new Error('callJoinInfoOp: payload.link_token (non-empty string) required');
        }
        const token = encodeURIComponent(pl.link_token);
        return httpRequest({
            method: 'GET',
            url: `/sync/api/v1/calls/join/${token}`,
        });
    },
});

export const callJoinAcceptOp = createAsyncOp({
    name: 'sync/call_join_accept',
    transport: 'http',
    silent: true,
    onFailure: _syncOpToastOnFailure,
    restMirror: { method: 'POST', path: '/sync/api/v1/calls/join/:link_token' },
    request: async ({ payload }) => {
        const { httpRequest } = await import('@platform/lib/events/http.js');
        const pl = callRecord(payload);
        if (pl === null || typeof pl.link_token !== 'string' || pl.link_token === '') {
            throw new Error('callJoinAcceptOp: payload.link_token (non-empty string) required');
        }
        const token = encodeURIComponent(pl.link_token);
        const body = pl.body;
        if (isPlainRecord(body) || Array.isArray(body)) {
            return httpRequest({
                method: 'POST',
                url: `/sync/api/v1/calls/join/${token}`,
                body,
            });
        }
        return httpRequest({
            method: 'POST',
            url: `/sync/api/v1/calls/join/${token}`,
        });
    },
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'sync/call_token': typeof callTokenOp;
        'sync/call_status': typeof callStatusOp;
        'sync/call_turn': typeof callTurnOp;
        'sync/call_recordings_list': typeof callRecordingsListOp;
        'sync/calls_invite': typeof callInviteOp;
        'sync/calls_accept': typeof callAcceptOp;
        'sync/calls_decline': typeof callDeclineOp;
        'sync/calls_hangup': typeof callHangupOp;
        'sync/calls_recording_start': typeof callRecordingStartOp;
        'sync/calls_recording_stop': typeof callRecordingStopOp;
        'sync/calls_admin_transfer': typeof callAdminTransferOp;
        'sync/calls_signal': typeof callSignalOp;
        'sync/channel_create_adhoc_call': typeof channelCreateAdhocCallOp;
        'sync/call_links_scheduled': typeof callLinksScheduledOp;
        'sync/call_link_create': typeof callLinkCreateOp;
        'sync/call_link_update': typeof callLinkUpdateOp;
        'sync/call_link_remove': typeof callLinkRemoveOp;
        'sync/call_ui': typeof callUiResource;
        'sync/call_join_info': typeof callJoinInfoOp;
        'sync/call_join_accept': typeof callJoinAcceptOp;
    }
}
