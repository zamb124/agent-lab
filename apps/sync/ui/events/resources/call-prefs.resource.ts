/**
 * Настройки звонка Sync — пользовательские настройки звонка (slice-only).
 *
 * Хранит:
 *   - cameraEnabled: bool — последнее состояние камеры (восстанавливается при подключении).
 *   - noiseSuppression / echoCancellation / autoGainControl: bool — audio capture options
 *     (передаются в LiveKit `AudioCaptureOptions`).
 *   - deviceIds: { audioinput, videoinput, audiooutput } — выбранные устройства, чтобы
 *     при следующем звонке сразу взять те же mic/cam/speaker (при наличии в системе).
 *   - hydrated: bool — флаг гидратации из localStorage через STORAGE_LOADED.
 *
 * Сохранение реализовано в bridge-effect [apps/sync/ui/events/sync-call-prefs.effect.js],
 * слушает actions slice'а и шлёт `STORAGE_PERSIST_REQUESTED`.
 */

import { createSlice } from '@platform/lib/events/index.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';
import type { SyncCallPrefsSlice } from '../sync.types.js';

const EMPTY_DEVICE_IDS = Object.freeze({
    audioinput: '',
    videoinput: '',
    audiooutput: '',
});

function eventRecord(payload: unknown): Record<string, unknown> | null {
    return isPlainRecord(payload) ? payload : null;
}

function booleanValue(payload: unknown): boolean | null {
    const record = eventRecord(payload);
    if (record === null) {
        return null;
    }
    const value = record.value;
    return typeof value === 'boolean' ? value : null;
}

function boolField(record: Record<string, unknown>, key: string, current: boolean): boolean {
    const value = record[key];
    return typeof value === 'boolean' ? value : current;
}

function stringField(record: Record<string, unknown>, key: string, current: string): string {
    const value = record[key];
    return typeof value === 'string' ? value : current;
}

export const callPrefsSlice = createSlice({
    name: 'sync/call_prefs',
    extraInitial: {
        cameraEnabled: true,
        noiseSuppression: true,
        echoCancellation: true,
        autoGainControl: true,
        deviceIds: EMPTY_DEVICE_IDS,
        hydrated: false,
    },
    extraEvents: {
        CAMERA_SET: 'camera_set',
        NOISE_SUPPRESSION_SET: 'noise_suppression_set',
        ECHO_CANCELLATION_SET: 'echo_cancellation_set',
        AUTO_GAIN_SET: 'auto_gain_set',
        DEVICE_ID_SET: 'device_id_set',
        HYDRATED: 'hydrated',
    },
    actions: {
        setCamera: 'camera_set',
        setNoiseSuppression: 'noise_suppression_set',
        setEchoCancellation: 'echo_cancellation_set',
        setAutoGain: 'auto_gain_set',
        setDeviceId: 'device_id_set',
        setHydrated: 'hydrated',
    },
    extraReducer: (state: SyncCallPrefsSlice, event) => {
        switch (event.type) {
            case 'sync/call_prefs/camera_set': {
                const value = booleanValue(event.payload);
                if (value === null) return state;
                return { ...state, cameraEnabled: value };
            }
            case 'sync/call_prefs/noise_suppression_set': {
                const value = booleanValue(event.payload);
                if (value === null) return state;
                return { ...state, noiseSuppression: value };
            }
            case 'sync/call_prefs/echo_cancellation_set': {
                const value = booleanValue(event.payload);
                if (value === null) return state;
                return { ...state, echoCancellation: value };
            }
            case 'sync/call_prefs/auto_gain_set': {
                const value = booleanValue(event.payload);
                if (value === null) return state;
                return { ...state, autoGainControl: value };
            }
            case 'sync/call_prefs/device_id_set': {
                const p = eventRecord(event.payload);
                if (p === null) return state;
                const kind = p.kind;
                const id = p.id;
                if (typeof id !== 'string') return state;
                if (kind !== 'audioinput' && kind !== 'videoinput' && kind !== 'audiooutput') return state;
                return {
                    ...state,
                    deviceIds: Object.freeze({ ...state.deviceIds, [kind]: id }),
                };
            }
            case 'sync/call_prefs/hydrated': {
                const p = eventRecord(event.payload);
                if (p === null) return state;
                const devices = p.deviceIds;
                const deviceIds = isPlainRecord(devices)
                    ? Object.freeze({
                        audioinput: stringField(devices, 'audioinput', state.deviceIds.audioinput),
                        videoinput: stringField(devices, 'videoinput', state.deviceIds.videoinput),
                        audiooutput: stringField(devices, 'audiooutput', state.deviceIds.audiooutput),
                    })
                    : state.deviceIds;
                return {
                    ...state,
                    cameraEnabled: boolField(p, 'cameraEnabled', state.cameraEnabled),
                    noiseSuppression: boolField(p, 'noiseSuppression', state.noiseSuppression),
                    echoCancellation: boolField(p, 'echoCancellation', state.echoCancellation),
                    autoGainControl: boolField(p, 'autoGainControl', state.autoGainControl),
                    deviceIds,
                    hydrated: true,
                };
            }
            default:
                return state;
        }
    },
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'sync/call_prefs': typeof callPrefsSlice;
    }
}
