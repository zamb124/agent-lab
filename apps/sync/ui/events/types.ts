/**
 * Sync domain push event-type constants (slash-канон).
 *
 * Pages/modals импортируют отсюда; литералы вне
 * `events/resources` / `events/types` запрещены CI.
 */

export const SYNC_CALL_INCOMING = 'sync/call/incoming';
export const SYNC_CALL_ACCEPTED = 'sync/call/accepted';
export const SYNC_CALL_DECLINED = 'sync/call/declined';
export const SYNC_CALL_ENDED = 'sync/call/ended';
export const SYNC_CALL_SIGNALED = 'sync/call/signaled';
export const SYNC_CALL_PARTICIPANT_JOINED = 'sync/call/participant_joined';
export const SYNC_CALL_PARTICIPANT_LEFT = 'sync/call/participant_left';
export const SYNC_CALL_RECORDING_STARTED = 'sync/call/recording_started';
export const SYNC_CALL_RECORDING_STOPPED = 'sync/call/recording_stopped';
export const SYNC_CALL_RECORDING_FAILED = 'sync/call/recording_failed';
export const SYNC_GIT_RESOURCE_UPSERTED = 'sync/git_resource/upserted';
export const SYNC_MESSAGE_CREATED = 'sync/message/created';
export const SYNC_CHANNELS_CREATED = 'sync/channels/created';
