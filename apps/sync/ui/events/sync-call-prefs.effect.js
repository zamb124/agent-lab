/**
 * Эффект persist настроек звонка Sync — bridge между slice `sync/call_prefs`
 * и платформенным storage-effect.
 *
 * - На AUTH_USER_LOADED / AUTH_LOGIN_SUCCEEDED единожды диспатчит
 *   `STORAGE_LOAD_REQUESTED` для ключа `humanitec.sync.call_prefs`.
 *   Когда core storage-effect отдаст значение через `STORAGE_LOADED`,
 *   мы конвертируем его в action `sync/call_prefs/hydrated`.
 *
 * - На любые actions slice (`sync/call_prefs/*_set`) — собираем актуальный
 *   снимок из getState().syncCallPrefs и шлём `STORAGE_PERSIST_REQUESTED`.
 *   Сам action `hydrated` не триггерит persist (избегаем эхо).
 */

import { CoreEvents } from '@platform/lib/events/index.js';

const STORAGE_KEY = 'humanitec.sync.call_prefs';

const PERSIST_EVENT_TYPES = new Set([
    'sync/call_prefs/camera_set',
    'sync/call_prefs/noise_suppression_set',
    'sync/call_prefs/echo_cancellation_set',
    'sync/call_prefs/auto_gain_set',
    'sync/call_prefs/device_id_set',
]);

function _snapshot(state) {
    const slice = state && state.syncCallPrefs;
    if (!slice || typeof slice !== 'object') return null;
    return {
        cameraEnabled: !!slice.cameraEnabled,
        noiseSuppression: !!slice.noiseSuppression,
        echoCancellation: !!slice.echoCancellation,
        autoGainControl: !!slice.autoGainControl,
        deviceIds: {
            audioinput: typeof slice.deviceIds?.audioinput === 'string' ? slice.deviceIds.audioinput : '',
            videoinput: typeof slice.deviceIds?.videoinput === 'string' ? slice.deviceIds.videoinput : '',
            audiooutput: typeof slice.deviceIds?.audiooutput === 'string' ? slice.deviceIds.audiooutput : '',
        },
    };
}

export function createSyncCallPrefsEffect() {
    let bootstrapDispatched = false;

    function dispatchBootstrap(ctx) {
        if (bootstrapDispatched) return;
        bootstrapDispatched = true;
        ctx.dispatch(CoreEvents.STORAGE_LOAD_REQUESTED, { key: STORAGE_KEY }, { source: 'system' });
    }

    return async function syncCallPrefsEffect(event, ctx) {
        if (event.type === CoreEvents.AUTH_USER_LOADED || event.type === CoreEvents.AUTH_LOGIN_SUCCEEDED) {
            dispatchBootstrap(ctx);
            return;
        }

        if (event.type === CoreEvents.STORAGE_LOADED) {
            const p = event.payload;
            if (!p || p.key !== STORAGE_KEY) return;
            if (p.value === null || p.value === undefined) return;
            if (typeof p.value !== 'object') return;
            ctx.dispatch('sync/call_prefs/hydrated', p.value, { source: 'storage' });
            return;
        }

        if (PERSIST_EVENT_TYPES.has(event.type)) {
            const snapshot = _snapshot(ctx.getState());
            if (snapshot === null) return;
            ctx.dispatch(
                CoreEvents.STORAGE_PERSIST_REQUESTED,
                { key: STORAGE_KEY, value: snapshot },
                { source: 'system' },
            );
        }
    };
}
