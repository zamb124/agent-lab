/**
 * Per-company override провайдеров речи (`company_voice_providers`).
 *
 * Бэкенд:
 *   GET    /voice/api/v1/companies/{company_id}/voice-providers        → { company_id, items[] }
 *   PUT    /voice/api/v1/companies/{company_id}/voice-providers/{kind} → item
 *   DELETE /voice/api/v1/companies/{company_id}/voice-providers/{kind} → { deleted }
 *   GET    /voice/api/v1/voice-providers/catalog                       → VoiceProvidersCatalogDTO
 *
 * Slice (`frontend/companyVoiceProviders`):
 *   { byKind: { stt|tts: item | null }, loading, error, savingKind, removingKind }
 *
 * Источник правды для UI настроек речи компании. Без фолбеков: дефолты
 * показываются как «не задано (используется deployment-default)».
 */

import { createAsyncOp } from '../index.js';
import { httpRequest } from '../http.js';
import { isPlainRecord } from '../payload.js';

export { companyVoiceProvidersCatalogLoadOp } from '@platform/lib/events/resources/voice-providers-catalog.resource.js';

type VoiceKind = 'stt' | 'tts';

type JsonObject = Record<string, unknown>;

function isVoiceKind(value: unknown): value is VoiceKind {
    return value === 'stt' || value === 'tts';
}

export interface VoiceProviderSecretsMeta {
    api_key_set: boolean;
    client_secret_set: boolean;
    folder_id: string | null;
    client_id: string | null;
    scope: string | null;
}

export interface VoiceProviderItem {
    kind: VoiceKind;
    provider: string;
    model: string | null;
    voice: string | null;
    language: string | null;
    sample_rate: number | null;
    threshold: number | null;
    response_format: string | null;
    secrets_meta: VoiceProviderSecretsMeta | null;
}

function _emptyByKind(): Record<VoiceKind, VoiceProviderItem | null> {
    return { stt: null, tts: null };
}

function _normalizeSecretsMetaField(raw: unknown): VoiceProviderSecretsMeta {
    if (raw === null || raw === undefined) {
        return {
            api_key_set: false,
            client_secret_set: false,
            folder_id: null,
            client_id: null,
            scope: null,
        };
    }
    if (!isPlainRecord(raw)) {
        throw new Error('company_voice_providers: secrets_meta must be object or null');
    }
    const r = raw;
    return {
        api_key_set: r.api_key_set === true,
        client_secret_set: r.client_secret_set === true,
        folder_id: typeof r.folder_id === 'string' ? r.folder_id : null,
        client_id: typeof r.client_id === 'string' ? r.client_id : null,
        scope: typeof r.scope === 'string' ? r.scope : null,
    };
}

function isSecretsMeta(value: unknown): value is VoiceProviderSecretsMeta {
    if (!isPlainRecord(value)) return false;
    return typeof value.api_key_set === 'boolean'
        && typeof value.client_secret_set === 'boolean'
        && (value.folder_id === null || typeof value.folder_id === 'string')
        && (value.client_id === null || typeof value.client_id === 'string')
        && (value.scope === null || typeof value.scope === 'string');
}

function isVoiceProviderItem(value: unknown): value is VoiceProviderItem {
    if (!isPlainRecord(value) || !isVoiceKind(value.kind)) return false;
    if (typeof value.provider !== 'string' || value.provider.length === 0) return false;
    if (value.model !== null && typeof value.model !== 'string') return false;
    if (value.voice !== null && typeof value.voice !== 'string') return false;
    if (value.language !== null && typeof value.language !== 'string') return false;
    if (value.sample_rate !== null && typeof value.sample_rate !== 'number') return false;
    if (value.threshold !== null && typeof value.threshold !== 'number') return false;
    if (value.response_format !== null && typeof value.response_format !== 'string') return false;
    if (value.secrets_meta !== null && !isSecretsMeta(value.secrets_meta)) return false;
    return true;
}

function _normalizeItem(raw: unknown): VoiceProviderItem {
    if (!isPlainRecord(raw)) {
        throw new Error('company_voice_providers: payload item required');
    }
    const r = raw;
    if (!isVoiceKind(r.kind)) {
        throw new Error(`company_voice_providers: unknown kind ${String(r.kind)}`);
    }
    if (typeof r.provider !== 'string' || r.provider.length === 0) {
        throw new Error('company_voice_providers: provider required');
    }
    let secrets_meta: VoiceProviderSecretsMeta | null = null;
    if (Object.prototype.hasOwnProperty.call(r, 'secrets_meta')) {
        secrets_meta = _normalizeSecretsMetaField(r.secrets_meta);
    }
    return {
        kind: r.kind,
        provider: r.provider,
        model: typeof r.model === 'string' ? r.model : null,
        voice: typeof r.voice === 'string' ? r.voice : null,
        language: typeof r.language === 'string' ? r.language : null,
        sample_rate: typeof r.sample_rate === 'number' ? r.sample_rate : null,
        threshold: typeof r.threshold === 'number' ? r.threshold : null,
        response_format:
            typeof r.response_format === 'string' ? r.response_format : null,
        secrets_meta,
    };
}

export const companyVoiceProvidersLoadOp = createAsyncOp({
    name: 'voice/company_voice_providers_load',
    silent: true,
    restMirror: {
        method: 'GET',
        path: '/voice/api/v1/companies/:company_id/voice-providers',
    },
    request: async ({ payload }) => {
        if (!isPlainRecord(payload) || typeof payload.company_id !== 'string' || payload.company_id.length === 0) {
            throw new Error('company_voice_providers_load: company_id required');
        }
        const response = await httpRequest({
            method: 'GET',
            url: `/voice/api/v1/companies/${encodeURIComponent(payload.company_id)}/voice-providers`,
        });
        if (!isPlainRecord(response) || !Array.isArray(response.items)) {
            throw new Error('company_voice_providers_load: response.items required');
        }
        return {
            company_id: payload.company_id,
            items: response.items.map(_normalizeItem),
        };
    },
    extraInitial: {
        byKind: _emptyByKind(),
        savingKind: null,
        removingKind: null,
    },
    extraReducer: (state, event, events) => {
        if (event.type === events.REQUESTED) {
            return state;
        }
        if (event.type === events.SUCCEEDED) {
            if (!isPlainRecord(event.payload) || !isPlainRecord(event.payload.result) || !Array.isArray(event.payload.result.items)) {
                throw new Error('company_voice_providers_load: SUCCEEDED result.items required');
            }
            const byKind = _emptyByKind();
            for (const raw of event.payload.result.items) {
                if (!isVoiceProviderItem(raw)) {
                    throw new Error('company_voice_providers_load: SUCCEEDED item must include kind and provider');
                }
                byKind[raw.kind] = raw;
            }
            return { ...state, byKind };
        }
        return state;
    },
});

export const companyVoiceProvidersUpsertOp = createAsyncOp({
    name: 'voice/company_voice_providers_upsert',
    successToastKey: 'frontend:company_voice_providers_page.toast_saved',
    errorToastKey: 'frontend:company_voice_providers_page.err_save_failed',
    restMirror: {
        method: 'PUT',
        path: '/voice/api/v1/companies/:company_id/voice-providers/:kind',
    },
    request: async ({ payload }) => {
        if (!isPlainRecord(payload) || typeof payload.company_id !== 'string' || payload.company_id.length === 0) {
            throw new Error('company_voice_providers_upsert: company_id required');
        }
        const companyId = payload.company_id;
        const kind = payload.kind;
        if (!isVoiceKind(kind)) {
            throw new Error(`company_voice_providers_upsert: unknown kind ${String(kind)}`);
        }
        const provider = payload.provider;
        if (typeof provider !== 'string' || provider.length === 0) {
            throw new Error('company_voice_providers_upsert: provider required');
        }
        const model = payload.model;
        const voice = payload.voice;
        const language = payload.language;
        const sampleRate = payload.sample_rate;
        const threshold = payload.threshold;
        const responseFormat = payload.response_format;
        const body: JsonObject = {
            provider,
            model: typeof model === 'string' && model.length > 0 ? model : null,
            voice: typeof voice === 'string' && voice.length > 0 ? voice : null,
            language: typeof language === 'string' && language.length > 0 ? language : null,
            sample_rate: typeof sampleRate === 'number' ? sampleRate : null,
            threshold: typeof threshold === 'number' ? threshold : null,
            response_format: typeof responseFormat === 'string' && responseFormat.length > 0 ? responseFormat : null,
        };
        const sec = payload.secrets;
        if (sec !== undefined) {
            body.secrets = sec;
        }
        const response = await httpRequest({
            method: 'PUT',
            url: `/voice/api/v1/companies/${encodeURIComponent(companyId)}/voice-providers/${encodeURIComponent(kind)}`,
            body,
        });
        return _normalizeItem(response);
    },
});

export const companyVoiceProvidersRemoveOp = createAsyncOp({
    name: 'voice/company_voice_providers_remove',
    successToastKey: 'frontend:company_voice_providers_page.toast_removed',
    errorToastKey: 'frontend:company_voice_providers_page.err_remove_failed',
    restMirror: {
        method: 'DELETE',
        path: '/voice/api/v1/companies/:company_id/voice-providers/:kind',
    },
    request: async ({ payload }) => {
        if (!isPlainRecord(payload) || typeof payload.company_id !== 'string' || payload.company_id.length === 0) {
            throw new Error('company_voice_providers_remove: company_id required');
        }
        const companyId = payload.company_id;
        const kind = payload.kind;
        if (!isVoiceKind(kind)) {
            throw new Error(`company_voice_providers_remove: unknown kind ${String(kind)}`);
        }
        const response = await httpRequest({
            method: 'DELETE',
            url: `/voice/api/v1/companies/${encodeURIComponent(companyId)}/voice-providers/${encodeURIComponent(kind)}`,
        });
        if (!isPlainRecord(response)) {
            throw new Error('company_voice_providers_remove: response must be an object');
        }
        return { kind, deleted: response.deleted === true };
    },
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'voice/company_voice_providers_load': typeof companyVoiceProvidersLoadOp;
        'voice/company_voice_providers_upsert': typeof companyVoiceProvidersUpsertOp;
        'voice/company_voice_providers_remove': typeof companyVoiceProvidersRemoveOp;
    }
}
