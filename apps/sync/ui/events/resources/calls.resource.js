/**
 * Sync Calls — звонки, ссылки, токены, запись.
 *
 * Все операции через WS (single canonical path), кроме UI-state в
 * `createSlice('sync/call_ui')`. Каждая фабрика задаёт явный `commandType`
 * — каноничный backend-handler в `apps/sync/realtime/command_router.py`.
 *
 * REST-зеркала живут в `apps/sync/api/calls.py` и вызывают те же `op_*`.
 */

import { createAsyncOp, createSlice } from '@platform/lib/events/index.js';

// ============================================================================
// Read-операции звонков
// ============================================================================

export const callTokenOp = createAsyncOp({
    name: 'sync/call_token',
    transport: 'ws',
    wsTimeoutMs: 5_000,
    silent: true,
    commandType: 'sync/calls/token_requested',
    restMirror: { method: 'GET', path: '/sync/api/v1/calls/:call_id/token' },
});

export const callStatusOp = createAsyncOp({
    name: 'sync/call_status',
    transport: 'ws',
    wsTimeoutMs: 5_000,
    silent: true,
    commandType: 'sync/calls/get_requested',
    restMirror: { method: 'GET', path: '/sync/api/v1/calls/:call_id' },
});

export const callTurnOp = createAsyncOp({
    name: 'sync/call_turn',
    transport: 'ws',
    wsTimeoutMs: 5_000,
    silent: true,
    commandType: 'sync/calls/turn_credentials_requested',
    restMirror: { method: 'GET', path: '/sync/api/v1/calls/turn-credentials' },
});

export const callRecordingsListOp = createAsyncOp({
    name: 'sync/call_recordings_list',
    transport: 'ws',
    wsTimeoutMs: 5_000,
    silent: true,
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
    commandType: 'sync/calls/invite_requested',
    restMirror: { method: 'POST', path: '/sync/api/v1/calls/:call_id/invite' },
});

export const callAcceptOp = createAsyncOp({
    name: 'sync/calls_accept',
    transport: 'ws',
    wsTimeoutMs: 5_000,
    silent: true,
    commandType: 'sync/calls/accept_requested',
    restMirror: { method: 'POST', path: '/sync/api/v1/calls/:call_id/accept' },
});

export const callDeclineOp = createAsyncOp({
    name: 'sync/calls_decline',
    transport: 'ws',
    wsTimeoutMs: 3_000,
    silent: true,
    commandType: 'sync/calls/decline_requested',
    restMirror: { method: 'POST', path: '/sync/api/v1/calls/:call_id/decline' },
});

export const callHangupOp = createAsyncOp({
    name: 'sync/calls_hangup',
    transport: 'ws',
    wsTimeoutMs: 5_000,
    silent: true,
    commandType: 'sync/calls/hangup_requested',
    restMirror: { method: 'POST', path: '/sync/api/v1/calls/:call_id/hangup' },
});

export const callRecordingStartOp = createAsyncOp({
    name: 'sync/calls_recording_start',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    silent: true,
    commandType: 'sync/calls/recording_start_requested',
    restMirror: { method: 'POST', path: '/sync/api/v1/calls/:call_id/recording/start' },
});

export const callRecordingStopOp = createAsyncOp({
    name: 'sync/calls_recording_stop',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    silent: true,
    commandType: 'sync/calls/recording_stop_requested',
    restMirror: { method: 'POST', path: '/sync/api/v1/calls/:call_id/recording/stop' },
});

export const callAdminTransferOp = createAsyncOp({
    name: 'sync/calls_admin_transfer',
    transport: 'ws',
    wsTimeoutMs: 5_000,
    silent: true,
    commandType: 'sync/calls/admin_transfer_requested',
    restMirror: { method: 'POST', path: '/sync/api/v1/calls/:call_id/admin/transfer' },
});

export const callSignalOp = createAsyncOp({
    name: 'sync/calls_signal',
    transport: 'ws',
    wsTimeoutMs: 2_000,
    silent: true,
    commandType: 'sync/calls/signal_requested',
    restMirror: { method: 'POST', path: '/sync/api/v1/calls/:call_id/signal' },
});

// ============================================================================
// Ad-hoc встреча: создать канал и сразу пригласить себя в звонок.
// На backend нет отдельного REST/WS-эндпоинта для adhoc — используем
// канонический `sync/channels/create_requested` через WS (тот же commandType,
// что и обычное создание канала из `channelsResource`). Имя фабрики уникальное
// для отдельного slice, чтобы не пересекаться с CRUD-resource'ом.
// ============================================================================

export const channelCreateAdhocCallOp = createAsyncOp({
    name: 'sync/channel_create_adhoc_call',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    silent: true,
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
    commandType: 'sync/calls/links_list_requested',
    restMirror: { method: 'GET', path: '/sync/api/v1/calls/links/scheduled' },
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
});

// ============================================================================
// UI-state звонков (slice activeCall, incomingCall, recordingStatus и пр.)
//
// Чистая `createSlice` фабрика без HTTP/WS — slice реагирует на push-события
// `sync/call/*` (server -> client через `platform:ui_events`) и локальные
// UI-actions overlay/incoming.
//
// Components используют `this.useSlice('sync/call_ui')` -> читают `.value`
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
    extraReducer: (state, event) => {
        switch (event.type) {
            case 'sync/call/incoming': {
                const p = event.payload;
                if (!p || typeof p.call_id !== 'string') return state;
                const callType = typeof p.call_type === 'string' ? p.call_type : 'video';
                const channelId = typeof p.channel_id === 'string' ? p.channel_id : null;
                let callerUserId = null;
                if (typeof p.created_by_user_id === 'string') callerUserId = p.created_by_user_id;
                else if (typeof p.initiator_user_id === 'string') callerUserId = p.initiator_user_id;
                const callerDisplayName = typeof p.caller_display_name === 'string' ? p.caller_display_name : null;
                const channelDisplayName = typeof p.channel_display_name === 'string' ? p.channel_display_name : null;
                const tracker = { ...state.activeCallChannels };
                if (channelId !== null && channelId !== '') {
                    tracker[channelId] = { call_id: p.call_id, call_type: callType };
                }
                return {
                    ...state,
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
                const p = event.payload;
                if (!p || typeof p.call_id !== 'string') return state;
                const tracker = { ...state.activeCallChannels };
                const ch = typeof p.channel_id === 'string' ? p.channel_id : '';
                if (ch !== '') {
                    tracker[ch] = {
                        call_id: p.call_id,
                        call_type: typeof p.call_type === 'string' ? p.call_type : 'video',
                    };
                }
                const isSameCallId =
                    state.activeCall !== null
                    && typeof state.activeCall.call_id === 'string'
                    && state.activeCall.call_id === p.call_id;
                const overlayMinimized = isSameCallId ? state.overlayMinimized : false;
                const activeCall =
                    isSameCallId && state.activeCall
                        ? { ...state.activeCall, ...p }
                        : { ...p };
                return {
                    ...state,
                    activeCall,
                    overlayMinimized,
                    bannerHangupGuardUntil: 0,
                    incomingCall: state.incomingCall && state.incomingCall.call_id === p.call_id
                        ? null
                        : state.incomingCall,
                    activeCallChannels: Object.freeze(tracker),
                };
            }
            case 'sync/call_ui/overlay_minimized': {
                const p = event.payload;
                let guard = 0;
                if (p !== null && typeof p === 'object' && typeof p.banner_hangup_guard_until === 'number') {
                    guard = p.banner_hangup_guard_until;
                }
                return { ...state, overlayMinimized: true, bannerHangupGuardUntil: guard };
            }
            case 'sync/call_ui/overlay_expanded':
                return { ...state, overlayMinimized: false, bannerHangupGuardUntil: 0 };
            case 'sync/call_ui/overlay_closed':
                return {
                    ...state,
                    activeCall: null,
                    overlayMinimized: false,
                    bannerHangupGuardUntil: 0,
                    overlayChatOpen: false,
                    recordingStatus: 'idle',
                    recordingError: null,
                };
            case 'sync/call_ui/overlay_chat_set': {
                const p = event.payload;
                if (!p || typeof p.open !== 'boolean') return state;
                return { ...state, overlayChatOpen: p.open };
            }
            case 'sync/call_ui/incoming_dismissed':
                return { ...state, incomingCall: null };
            case 'sync/call_ui/recording_status_set': {
                const p = event.payload;
                if (!p || typeof p.status !== 'string') return state;
                return {
                    ...state,
                    recordingStatus: p.status,
                    recordingError: typeof p.error === 'string' ? p.error : null,
                };
            }
            case 'sync/call/ended': {
                const p = event.payload;
                if (!p || typeof p.call_id !== 'string') return state;
                const tracker = { ...state.activeCallChannels };
                if (typeof p.channel_id === 'string') delete tracker[p.channel_id];
                return {
                    ...state,
                    activeCall: state.activeCall && state.activeCall.call_id === p.call_id ? null : state.activeCall,
                    incomingCall: state.incomingCall && state.incomingCall.call_id === p.call_id ? null : state.incomingCall,
                    overlayMinimized: state.activeCall && state.activeCall.call_id === p.call_id ? false : state.overlayMinimized,
                    bannerHangupGuardUntil:
                        state.activeCall && state.activeCall.call_id === p.call_id ? 0 : state.bannerHangupGuardUntil,
                    recordingStatus: state.activeCall && state.activeCall.call_id === p.call_id ? 'idle' : state.recordingStatus,
                    activeCallChannels: Object.freeze(tracker),
                };
            }
            case 'sync/call/recording_started':
                return { ...state, recordingStatus: 'recording', recordingError: null };
            case 'sync/call/recording_stopped':
                return { ...state, recordingStatus: 'idle', recordingError: null };
            case 'sync/call/recording_failed': {
                const p = event.payload;
                return {
                    ...state,
                    recordingStatus: 'failed',
                    recordingError: (p && typeof p.error === 'string') ? p.error : 'recording_failed',
                };
            }
            case 'sync/call/admin_changed': {
                const p = event.payload;
                if (!p || !state.activeCall || state.activeCall.call_id !== p.call_id) return state;
                const newAdmin = (typeof p.created_by_user_id === 'string' && p.created_by_user_id !== '')
                    ? p.created_by_user_id
                    : state.activeCall.created_by_user_id;
                return {
                    ...state,
                    activeCall: { ...state.activeCall, created_by_user_id: newAdmin },
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
    restMirror: { method: 'GET', path: '/sync/api/v1/calls/join/:link_token' },
    request: async ({ payload }) => {
        const { httpRequest } = await import('@platform/lib/events/http.js');
        if (!payload || typeof payload.link_token !== 'string' || payload.link_token === '') {
            throw new Error('callJoinInfoOp: payload.link_token (non-empty string) required');
        }
        const token = encodeURIComponent(payload.link_token);
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
    restMirror: { method: 'POST', path: '/sync/api/v1/calls/join/:link_token' },
    request: async ({ payload }) => {
        const { httpRequest } = await import('@platform/lib/events/http.js');
        if (!payload || typeof payload.link_token !== 'string' || payload.link_token === '') {
            throw new Error('callJoinAcceptOp: payload.link_token (non-empty string) required');
        }
        const token = encodeURIComponent(payload.link_token);
        const body = payload.body !== null && payload.body !== undefined && typeof payload.body === 'object'
            ? payload.body
            : null;
        if (body !== null) {
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
