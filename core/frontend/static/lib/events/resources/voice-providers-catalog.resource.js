/**
 * Каталог провайдеров речи.
 * Console: GET /frontend/api/voice-providers/catalog.
 * Flows editor: GET /flows/api/v1/voice-providers/catalog (тот же DTO, без прокси на другой сервис).
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

function _normalizeVoiceHint(raw) {
    if (!raw || typeof raw !== 'object') {
        throw new Error('voice_catalog: tts voice hint invalid');
    }
    if (typeof raw.api_model_id !== 'string') {
        throw new Error('voice_catalog: tts_litserve_voice_hints.api_model_id required');
    }
    const voiceIdsIn = raw.voice_ids;
    let voiceIds = [];
    if (Array.isArray(voiceIdsIn)) {
        for (let j = 0; j < voiceIdsIn.length; j += 1) {
            const vid = voiceIdsIn[j];
            if (typeof vid !== 'string') {
                throw new Error(
                    `voice_catalog: tts_litserve_voice_hints.voice_ids[${j}] must be string`,
                );
            }
            voiceIds.push(vid);
        }
        voiceIds = [...voiceIds].sort();
    }
    return {
        api_model_id: raw.api_model_id,
        default_voice:
            typeof raw.default_voice === 'string' ? raw.default_voice : null,
        voice_ids: Object.freeze(voiceIds),
    };
}

function _normalizeStringList(raw, field) {
    if (!Array.isArray(raw)) {
        throw new Error(`voice_catalog: ${field} must be array`);
    }
    const out = [];
    for (let i = 0; i < raw.length; i += 1) {
        const v = raw[i];
        if (typeof v !== 'string') {
            throw new Error(`voice_catalog: ${field}[${i}] must be string`);
        }
        out.push(v);
    }
    return Object.freeze(out);
}

function _normalizeIntList(raw, field) {
    if (!Array.isArray(raw)) {
        throw new Error(`voice_catalog: ${field} must be array`);
    }
    const out = [];
    for (let i = 0; i < raw.length; i += 1) {
        const v = raw[i];
        const n = typeof v === 'number' ? v : parseInt(String(v), 10);
        if (!Number.isFinite(n)) {
            throw new Error(`voice_catalog: ${field}[${i}] must be int`);
        }
        out.push(n);
    }
    return Object.freeze(out);
}

function _normalizeCredentialGroups(raw) {
    if (!raw || typeof raw !== 'object') {
        throw new Error('voice_catalog: credential_field_groups required');
    }
    const keys = Object.keys(raw);
    const out = {};
    for (let i = 0; i < keys.length; i += 1) {
        const k = keys[i];
        const g = raw[k];
        if (!Array.isArray(g)) {
            throw new Error(`voice_catalog: credential_field_groups.${k} must be array`);
        }
        out[k] = g;
    }
    return Object.freeze(out);
}

function _normalizeCatalog(raw) {
    if (!raw || typeof raw !== 'object') {
        throw new Error('voice_catalog: payload required');
    }
    const hintsIn = raw.tts_litserve_voice_hints;
    if (!Array.isArray(hintsIn)) {
        throw new Error('voice_catalog: tts_litserve_voice_hints must be array');
    }
    const hints = [];
    for (let i = 0; i < hintsIn.length; i += 1) {
        hints.push(_normalizeVoiceHint(hintsIn[i]));
    }
    return Object.freeze({
        stt_tts_provider_ids: _normalizeStringList(raw.stt_tts_provider_ids, 'stt_tts_provider_ids'),
        response_format_ids: _normalizeStringList(raw.response_format_ids, 'response_format_ids'),
        credential_field_groups: _normalizeCredentialGroups(raw.credential_field_groups),
        stt_litserve_models: _normalizeStringList(raw.stt_litserve_models, 'stt_litserve_models'),
        tts_litserve_models: _normalizeStringList(raw.tts_litserve_models, 'tts_litserve_models'),
        tts_litserve_voice_hints: Object.freeze(hints),
        cloud_ru_stt_models: _normalizeStringList(raw.cloud_ru_stt_models, 'cloud_ru_stt_models'),
        cloud_ru_tts_models: _normalizeStringList(raw.cloud_ru_tts_models, 'cloud_ru_tts_models'),
        yandex_speech_models: _normalizeStringList(raw.yandex_speech_models, 'yandex_speech_models'),
        sber_speech_models: _normalizeStringList(raw.sber_speech_models, 'sber_speech_models'),
        speech_language_ids: _normalizeStringList(raw.speech_language_ids, 'speech_language_ids'),
        vad_provider_ids: _normalizeStringList(raw.vad_provider_ids, 'vad_provider_ids'),
        tts_sample_rate_ids: _normalizeIntList(raw.tts_sample_rate_ids, 'tts_sample_rate_ids'),
        vad_sample_rate_ids: _normalizeIntList(raw.vad_sample_rate_ids, 'vad_sample_rate_ids'),
        litserve_silero_tts_sample_rate_ids: _normalizeIntList(
            raw.litserve_silero_tts_sample_rate_ids,
            'litserve_silero_tts_sample_rate_ids',
        ),
        cloud_ru_tts_voice_ids: _normalizeStringList(raw.cloud_ru_tts_voice_ids, 'cloud_ru_tts_voice_ids'),
        yandex_tts_voice_ids: _normalizeStringList(raw.yandex_tts_voice_ids, 'yandex_tts_voice_ids'),
        sber_tts_voice_ids: _normalizeStringList(raw.sber_tts_voice_ids, 'sber_tts_voice_ids'),
    });
}

function _createVoiceProvidersCatalogLoadOp(name, url, restPath) {
    return createAsyncOp({
        name,
        silent: true,
        restMirror: {
            method: 'GET',
            path: restPath,
        },
        request: async () => {
            const response = await httpRequest({
                method: 'GET',
                url,
            });
            return _normalizeCatalog(response);
        },
    });
}

export const companyVoiceProvidersCatalogLoadOp = _createVoiceProvidersCatalogLoadOp(
    'frontend/voice_providers_catalog_load',
    '/frontend/api/voice-providers/catalog',
    '/frontend/api/voice-providers/catalog',
);

export const flowsVoiceProvidersCatalogLoadOp = _createVoiceProvidersCatalogLoadOp(
    'flows/voice_providers_catalog_load',
    '/flows/api/v1/voice-providers/catalog',
    '/flows/api/v1/voice-providers/catalog',
);
