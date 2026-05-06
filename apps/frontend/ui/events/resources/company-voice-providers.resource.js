/**
 * Per-company override провайдеров речи (`company_voice_providers`).
 *
 * Backend:
 *   GET    /frontend/api/companies/{company_id}/voice-providers        → { company_id, items[] }
 *   PUT    /frontend/api/companies/{company_id}/voice-providers/{kind} → item
 *   DELETE /frontend/api/companies/{company_id}/voice-providers/{kind} → { deleted }
 *   GET    /frontend/api/voice-providers/catalog                       → VoiceProvidersCatalogDTO
 *
 * Slice (`frontend/companyVoiceProviders`):
 *   { byKind: { stt|tts: item | null }, loading, error, savingKind, removingKind }
 *
 * Источник правды для UI настроек речи компании. Без фолбеков: дефолты
 * показываются как «не задано (используется deployment-default)».
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

export { companyVoiceProvidersCatalogLoadOp } from '@platform/lib/events/resources/voice-providers-catalog.resource.js';

const VOICE_KINDS = ['stt', 'tts'];

function _emptyByKind() {
    return { stt: null, tts: null };
}

function _normalizeSecretsMetaField(raw) {
    if (raw === null || raw === undefined) {
        return {
            api_key_set: false,
            client_secret_set: false,
            folder_id: null,
            client_id: null,
            scope: null,
        };
    }
    if (typeof raw !== 'object') {
        throw new Error('company_voice_providers: secrets_meta must be object or null');
    }
    return {
        api_key_set: raw.api_key_set === true,
        client_secret_set: raw.client_secret_set === true,
        folder_id: typeof raw.folder_id === 'string' ? raw.folder_id : null,
        client_id: typeof raw.client_id === 'string' ? raw.client_id : null,
        scope: typeof raw.scope === 'string' ? raw.scope : null,
    };
}

function _normalizeItem(raw) {
    if (!raw || typeof raw !== 'object') {
        throw new Error('company_voice_providers: payload item required');
    }
    if (!VOICE_KINDS.includes(raw.kind)) {
        throw new Error(`company_voice_providers: unknown kind ${raw.kind}`);
    }
    if (typeof raw.provider !== 'string' || raw.provider.length === 0) {
        throw new Error('company_voice_providers: provider required');
    }
    let secrets_meta = null;
    if (Object.prototype.hasOwnProperty.call(raw, 'secrets_meta')) {
        secrets_meta = _normalizeSecretsMetaField(raw.secrets_meta);
    }
    return {
        kind: raw.kind,
        provider: raw.provider,
        model: typeof raw.model === 'string' ? raw.model : null,
        voice: typeof raw.voice === 'string' ? raw.voice : null,
        language: typeof raw.language === 'string' ? raw.language : null,
        sample_rate: typeof raw.sample_rate === 'number' ? raw.sample_rate : null,
        threshold: typeof raw.threshold === 'number' ? raw.threshold : null,
        response_format:
            typeof raw.response_format === 'string' ? raw.response_format : null,
        secrets_meta,
    };
}

export const companyVoiceProvidersLoadOp = createAsyncOp({
    name: 'frontend/company_voice_providers_load',
    silent: true,
    restMirror: {
        method: 'GET',
        path: '/frontend/api/companies/:company_id/voice-providers',
    },
    request: async ({ payload }) => {
        if (!payload || typeof payload.company_id !== 'string' || payload.company_id.length === 0) {
            throw new Error('company_voice_providers_load: company_id required');
        }
        const response = await httpRequest({
            method: 'GET',
            url: `/frontend/api/companies/${encodeURIComponent(payload.company_id)}/voice-providers`,
        });
        if (!Array.isArray(response.items)) {
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
            const result = event.payload && event.payload.result;
            if (!result || !Array.isArray(result.items)) return state;
            const byKind = _emptyByKind();
            for (const item of result.items) {
                byKind[item.kind] = item;
            }
            return { ...state, byKind };
        }
        return state;
    },
});

export const companyVoiceProvidersUpsertOp = createAsyncOp({
    name: 'frontend/company_voice_providers_upsert',
    successToastKey: 'frontend:company_voice_providers_page.toast_saved',
    errorToastKey: 'frontend:company_voice_providers_page.err_save_failed',
    restMirror: {
        method: 'PUT',
        path: '/frontend/api/companies/:company_id/voice-providers/:kind',
    },
    request: async ({ payload }) => {
        if (!payload || typeof payload.company_id !== 'string' || payload.company_id.length === 0) {
            throw new Error('company_voice_providers_upsert: company_id required');
        }
        if (!VOICE_KINDS.includes(payload.kind)) {
            throw new Error(`company_voice_providers_upsert: unknown kind ${payload.kind}`);
        }
        if (typeof payload.provider !== 'string' || payload.provider.length === 0) {
            throw new Error('company_voice_providers_upsert: provider required');
        }
        const body = {
            provider: payload.provider,
            model: typeof payload.model === 'string' && payload.model.length > 0 ? payload.model : null,
            voice: typeof payload.voice === 'string' && payload.voice.length > 0 ? payload.voice : null,
            language: typeof payload.language === 'string' && payload.language.length > 0 ? payload.language : null,
            sample_rate: typeof payload.sample_rate === 'number' ? payload.sample_rate : null,
            threshold: typeof payload.threshold === 'number' ? payload.threshold : null,
            response_format: typeof payload.response_format === 'string' && payload.response_format.length > 0 ? payload.response_format : null,
        };
        const sec = payload.secrets;
        if (sec !== undefined) {
            body.secrets = sec;
        }
        const response = await httpRequest({
            method: 'PUT',
            url: `/frontend/api/companies/${encodeURIComponent(payload.company_id)}/voice-providers/${encodeURIComponent(payload.kind)}`,
            body,
        });
        return _normalizeItem(response);
    },
});

export const companyVoiceProvidersRemoveOp = createAsyncOp({
    name: 'frontend/company_voice_providers_remove',
    successToastKey: 'frontend:company_voice_providers_page.toast_removed',
    errorToastKey: 'frontend:company_voice_providers_page.err_remove_failed',
    restMirror: {
        method: 'DELETE',
        path: '/frontend/api/companies/:company_id/voice-providers/:kind',
    },
    request: async ({ payload }) => {
        if (!payload || typeof payload.company_id !== 'string' || payload.company_id.length === 0) {
            throw new Error('company_voice_providers_remove: company_id required');
        }
        if (!VOICE_KINDS.includes(payload.kind)) {
            throw new Error(`company_voice_providers_remove: unknown kind ${payload.kind}`);
        }
        const response = await httpRequest({
            method: 'DELETE',
            url: `/frontend/api/companies/${encodeURIComponent(payload.company_id)}/voice-providers/${encodeURIComponent(payload.kind)}`,
        });
        return { kind: payload.kind, deleted: !!response.deleted };
    },
});
