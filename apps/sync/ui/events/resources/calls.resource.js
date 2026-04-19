/**
 * Sync Calls — звонки, ссылки, токены, запись.
 *
 * Транспорт смешанный по природе:
 *   - HTTP: token, status, turn, recordings list, scheduled links —
 *     нужны до подключения к LiveKit или из гостевой страницы.
 *   - WS: invite/accept/decline/hangup/recording.start/stop/admin.transfer/
 *     signal — низкая latency, ack-required. Каждая фабрика задаёт явный
 *     `commandType` под канон `sync/calls/<verb>_requested` (имя фабрики
 *     — `sync/calls_<verb>` для уникальности slice).
 *
 * UI-state звонков (`activeCall`, `incomingCall`, `recordingStatus`,
 * `overlayMinimized`, `activeCallChannels`) — в `createSlice('sync/call_ui')`,
 * без HTTP/WS, реакция на push-события `sync/call/*` через `extraReducer`.
 *
 * REST-зеркала живут в `apps/sync/api/calls.py`.
 */

import { createAsyncOp, createResourceCollection, createSlice } from '@platform/lib/events/index.js';

// ============================================================================
// HTTP-операции (read-only / preflight для LiveKit)
// ============================================================================

export const callTokenOp = createAsyncOp({
    name: 'sync/call_token',
    transport: 'http',
    silent: true,
    restMirror: { method: 'GET', path: '/sync/api/v1/calls/:call_id/token' },
    request: async ({ payload }) => {
        const { httpRequest } = await import('@platform/lib/events/http.js');
        return httpRequest({
            method: 'GET',
            url: `/sync/api/v1/calls/${encodeURIComponent(payload.call_id)}/token`,
        });
    },
});

export const callStatusOp = createAsyncOp({
    name: 'sync/call_status',
    transport: 'http',
    silent: true,
    restMirror: { method: 'GET', path: '/sync/api/v1/calls/:call_id' },
    request: async ({ payload }) => {
        const { httpRequest } = await import('@platform/lib/events/http.js');
        return httpRequest({
            method: 'GET',
            url: `/sync/api/v1/calls/${encodeURIComponent(payload.call_id)}`,
        });
    },
});

export const callTurnOp = createAsyncOp({
    name: 'sync/call_turn',
    transport: 'http',
    silent: true,
    restMirror: { method: 'GET', path: '/sync/api/v1/calls/turn-credentials' },
    request: async () => {
        const { httpRequest } = await import('@platform/lib/events/http.js');
        return httpRequest({ method: 'GET', url: '/sync/api/v1/calls/turn-credentials' });
    },
});

export const callRecordingsListOp = createAsyncOp({
    name: 'sync/call_recordings_list',
    transport: 'http',
    silent: true,
    restMirror: { method: 'GET', path: '/sync/api/v1/calls/:call_id/recordings' },
    request: async ({ payload }) => {
        const { httpRequest } = await import('@platform/lib/events/http.js');
        return httpRequest({
            method: 'GET',
            url: `/sync/api/v1/calls/${encodeURIComponent(payload.call_id)}/recordings`,
        });
    },
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
// Гостевые scheduled links (HTTP)
// ============================================================================

export const callLinksScheduledResource = createResourceCollection({
    name: 'sync/call_links_scheduled',
    baseUrl: '/sync/api/v1/calls/links',
    idField: 'link_token',
    operations: ['list'],
    transport: 'http',
    listQuery: ({ from_time, to_time }) => ({ from_time, to_time }),
    buildItemUrl: (id) => `/sync/api/v1/calls/links/${encodeURIComponent(id)}`,
    restMirror: {
        list: { method: 'GET', path: '/sync/api/v1/calls/links/scheduled' },
    },
});

export const callLinkCreateOp = createAsyncOp({
    name: 'sync/call_link_create',
    transport: 'http',
    successToastKey: 'sync:calls.toast_link_created',
    errorToastKey: 'sync:calls.err_link_create',
    restMirror: { method: 'POST', path: '/sync/api/v1/calls/links' },
    request: async ({ payload }) => {
        const { httpRequest } = await import('@platform/lib/events/http.js');
        return httpRequest({ method: 'POST', url: '/sync/api/v1/calls/links', body: payload });
    },
});

export const callLinkUpdateOp = createAsyncOp({
    name: 'sync/call_link_update',
    transport: 'http',
    successToastKey: 'sync:calls.toast_link_updated',
    errorToastKey: 'sync:calls.err_link_update',
    restMirror: { method: 'PATCH', path: '/sync/api/v1/calls/links/:link_token' },
    request: async ({ payload }) => {
        const { httpRequest } = await import('@platform/lib/events/http.js');
        const { link_token, ...body } = payload;
        return httpRequest({
            method: 'PATCH',
            url: `/sync/api/v1/calls/links/${encodeURIComponent(link_token)}`,
            body,
        });
    },
});

export const callLinkRemoveOp = createAsyncOp({
    name: 'sync/call_link_remove',
    transport: 'http',
    successToastKey: 'sync:calls.toast_link_removed',
    errorToastKey: 'sync:calls.err_link_remove',
    restMirror: { method: 'DELETE', path: '/sync/api/v1/calls/links/:link_token' },
    request: async ({ payload }) => {
        const { httpRequest } = await import('@platform/lib/events/http.js');
        return httpRequest({
            method: 'DELETE',
            url: `/sync/api/v1/calls/links/${encodeURIComponent(payload.link_token)}`,
        });
    },
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
        recordingStatus: 'idle',
        recordingError: null,
        activeCallChannels: Object.freeze({}),
    },
    extraEvents: {
        OVERLAY_OPENED: 'overlay_opened',
        OVERLAY_MINIMIZED: 'overlay_minimized',
        OVERLAY_EXPANDED: 'overlay_expanded',
        OVERLAY_CLOSED: 'overlay_closed',
        INCOMING_DISMISSED: 'incoming_dismissed',
        RECORDING_STATUS_SET: 'recording_status_set',
    },
    actions: {
        openOverlay: 'overlay_opened',
        minimizeOverlay: 'overlay_minimized',
        expandOverlay: 'overlay_expanded',
        closeOverlay: 'overlay_closed',
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
                return {
                    ...state,
                    activeCall: { ...p },
                    overlayMinimized: false,
                    incomingCall: state.incomingCall && state.incomingCall.call_id === p.call_id
                        ? null
                        : state.incomingCall,
                };
            }
            case 'sync/call_ui/overlay_minimized':
                return state.activeCall ? { ...state, overlayMinimized: true } : state;
            case 'sync/call_ui/overlay_expanded':
                return state.activeCall ? { ...state, overlayMinimized: false } : state;
            case 'sync/call_ui/overlay_closed':
                return {
                    ...state,
                    activeCall: null,
                    overlayMinimized: false,
                    recordingStatus: 'idle',
                    recordingError: null,
                };
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
// Гостевая страница входа в звонок
// ============================================================================

export const callJoinInfoOp = createAsyncOp({
    name: 'sync/call_join_info',
    transport: 'http',
    silent: true,
    restMirror: { method: 'GET', path: '/sync/api/v1/calls/join/:link_token' },
    request: async ({ payload }) => {
        const { httpRequest } = await import('@platform/lib/events/http.js');
        return httpRequest({
            method: 'GET',
            url: `/sync/api/v1/calls/join/${encodeURIComponent(payload.link_token)}`,
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
        const { link_token, ...body } = payload;
        return httpRequest({
            method: 'POST',
            url: `/sync/api/v1/calls/join/${encodeURIComponent(link_token)}`,
            body,
        });
    },
});
