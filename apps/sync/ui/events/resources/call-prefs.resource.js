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

const EMPTY_DEVICE_IDS = Object.freeze({
    audioinput: '',
    videoinput: '',
    audiooutput: '',
});

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
    extraReducer: (state, event) => {
        switch (event.type) {
            case 'sync/call_prefs/camera_set': {
                const p = event.payload;
                if (!p || typeof p.value !== 'boolean') return state;
                return { ...state, cameraEnabled: p.value };
            }
            case 'sync/call_prefs/noise_suppression_set': {
                const p = event.payload;
                if (!p || typeof p.value !== 'boolean') return state;
                return { ...state, noiseSuppression: p.value };
            }
            case 'sync/call_prefs/echo_cancellation_set': {
                const p = event.payload;
                if (!p || typeof p.value !== 'boolean') return state;
                return { ...state, echoCancellation: p.value };
            }
            case 'sync/call_prefs/auto_gain_set': {
                const p = event.payload;
                if (!p || typeof p.value !== 'boolean') return state;
                return { ...state, autoGainControl: p.value };
            }
            case 'sync/call_prefs/device_id_set': {
                const p = event.payload;
                if (!p || typeof p.kind !== 'string' || typeof p.id !== 'string') return state;
                if (p.kind !== 'audioinput' && p.kind !== 'videoinput' && p.kind !== 'audiooutput') return state;
                return {
                    ...state,
                    deviceIds: Object.freeze({ ...state.deviceIds, [p.kind]: p.id }),
                };
            }
            case 'sync/call_prefs/hydrated': {
                const p = event.payload;
                if (!p || typeof p !== 'object') return state;
                const cameraEnabled = typeof p.cameraEnabled === 'boolean' ? p.cameraEnabled : state.cameraEnabled;
                const noiseSuppression = typeof p.noiseSuppression === 'boolean' ? p.noiseSuppression : state.noiseSuppression;
                const echoCancellation = typeof p.echoCancellation === 'boolean' ? p.echoCancellation : state.echoCancellation;
                const autoGainControl = typeof p.autoGainControl === 'boolean' ? p.autoGainControl : state.autoGainControl;
                const deviceIds = (p.deviceIds && typeof p.deviceIds === 'object')
                    ? Object.freeze({
                        audioinput: typeof p.deviceIds.audioinput === 'string' ? p.deviceIds.audioinput : state.deviceIds.audioinput,
                        videoinput: typeof p.deviceIds.videoinput === 'string' ? p.deviceIds.videoinput : state.deviceIds.videoinput,
                        audiooutput: typeof p.deviceIds.audiooutput === 'string' ? p.deviceIds.audiooutput : state.deviceIds.audiooutput,
                    })
                    : state.deviceIds;
                return {
                    ...state,
                    cameraEnabled,
                    noiseSuppression,
                    echoCancellation,
                    autoGainControl,
                    deviceIds,
                    hydrated: true,
                };
            }
            default:
                return state;
        }
    },
});
