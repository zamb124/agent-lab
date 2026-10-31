/**
 * Эффект persist настроек звонка Sync — bridge между slice `sync/call_prefs`
 * и платформенным storage-effect.
 *
 * - На AUTH_USER_LOADED / AUTH_LOGIN_SUCCEEDED единожды диспатчит
 *   `STORAGE_LOAD_REQUESTED` для ключа `linnex.sync.call_prefs`.
 *   Когда core storage-effect отдаст значение через `STORAGE_LOADED`,
 *   мы конвертируем его в action `sync/call_prefs/hydrated`.
 *
 * - На любые actions slice (`sync/call_prefs/*_set`) — собираем актуальный
 *   снимок из getState().syncCallPrefs и шлём `STORAGE_PERSIST_REQUESTED`.
 *   Сам action `hydrated` не триггерит persist (избегаем эхо).
 */

import { CoreEvents } from '@platform/lib/events/index.js';
import type { EffectCtx, PlatformEvent } from '@platform/lib/events/contract.js';
import { platformStorageKey } from '@platform/lib/utils/storage-keys.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';

const STORAGE_KEY = platformStorageKey('sync', 'call_prefs');

const PERSIST_EVENT_TYPES = new Set([
    'sync/call_prefs/camera_set',
    'sync/call_prefs/noise_suppression_set',
    'sync/call_prefs/echo_cancellation_set',
    'sync/call_prefs/auto_gain_set',
    'sync/call_prefs/device_id_set',
]);

function deviceId(devices: Record<string, unknown> | null, key: string): string {
    if (!devices) return '';
    const value = devices[key];
    return typeof value === 'string' ? value : '';
}

function _snapshot(state: unknown) {
    if (!isPlainRecord(state)) return null;
    const slice = state.syncCallPrefs;
    if (!isPlainRecord(slice)) return null;
    const deviceIds = isPlainRecord(slice.deviceIds) ? slice.deviceIds : null;
    return {
        cameraEnabled: slice.cameraEnabled === true,
        noiseSuppression: slice.noiseSuppression === true,
        echoCancellation: slice.echoCancellation === true,
        autoGainControl: slice.autoGainControl === true,
        deviceIds: {
            audioinput: deviceId(deviceIds, 'audioinput'),
            videoinput: deviceId(deviceIds, 'videoinput'),
            audiooutput: deviceId(deviceIds, 'audiooutput'),
        },
    };
}

export function createSyncCallPrefsEffect() {
    let bootstrapDispatched = false;

    function dispatchBootstrap(ctx: EffectCtx) {
        if (bootstrapDispatched) return;
        bootstrapDispatched = true;
        ctx.dispatch(CoreEvents.STORAGE_LOAD_REQUESTED, { key: STORAGE_KEY }, { source: 'system' });
    }

    return async function syncCallPrefsEffect(event: PlatformEvent, ctx: EffectCtx) {
        if (event.type === CoreEvents.AUTH_USER_LOADED || event.type === CoreEvents.AUTH_LOGIN_SUCCEEDED) {
            dispatchBootstrap(ctx);
            return;
        }

        if (event.type === CoreEvents.STORAGE_LOADED) {
            const p = event.payload;
            if (!isPlainRecord(p) || p.key !== STORAGE_KEY) return;
            if (!isPlainRecord(p.value)) return;
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
