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

export { companyVoiceProvidersCatalogLoadOp } from '@platform/lib/events/resources/voice-providers-catalog.resource.js';

type VoiceKind = 'stt' | 'tts';
const VOICE_KINDS: readonly string[] = ['stt', 'tts'];

type JsonObject = Record<string, unknown>;

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
    if (typeof raw !== 'object') {
        throw new Error('company_voice_providers: secrets_meta must be object or null');
    }
    const r = raw as JsonObject;
    return {
        api_key_set: r.api_key_set === true,
        client_secret_set: r.client_secret_set === true,
        folder_id: typeof r.folder_id === 'string' ? r.folder_id : null,
        client_id: typeof r.client_id === 'string' ? r.client_id : null,
        scope: typeof r.scope === 'string' ? r.scope : null,
    };
}

function _normalizeItem(raw: unknown): VoiceProviderItem {
    if (!raw || typeof raw !== 'object') {
        throw new Error('company_voice_providers: payload item required');
    }
    const r = raw as JsonObject;
    if (typeof r.kind !== 'string' || !VOICE_KINDS.includes(r.kind)) {
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
        kind: r.kind as VoiceKind,
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
        const p = payload as { company_id?: unknown } | null;
        if (!p || typeof p.company_id !== 'string' || p.company_id.length === 0) {
            throw new Error('company_voice_providers_load: company_id required');
        }
        const response = await httpRequest({
            method: 'GET',
            url: `/voice/api/v1/companies/${encodeURIComponent(p.company_id)}/voice-providers`,
        }) as { items?: unknown } | null;
        if (!response || !Array.isArray(response.items)) {
            throw new Error('company_voice_providers_load: response.items required');
        }
        return {
            company_id: p.company_id,
            items: (response.items as unknown[]).map(_normalizeItem),
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
            const result = (event.payload as { result?: { items?: VoiceProviderItem[] } } | null)?.result;
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
    name: 'voice/company_voice_providers_upsert',
    successToastKey: 'frontend:company_voice_providers_page.toast_saved',
    errorToastKey: 'frontend:company_voice_providers_page.err_save_failed',
    restMirror: {
        method: 'PUT',
        path: '/voice/api/v1/companies/:company_id/voice-providers/:kind',
    },
    request: async ({ payload }) => {
        const p = payload as JsonObject | null;
        if (!p || typeof p.company_id !== 'string' || p.company_id.length === 0) {
            throw new Error('company_voice_providers_upsert: company_id required');
        }
        if (typeof p.kind !== 'string' || !VOICE_KINDS.includes(p.kind)) {
            throw new Error(`company_voice_providers_upsert: unknown kind ${String(p.kind)}`);
        }
        if (typeof p.provider !== 'string' || p.provider.length === 0) {
            throw new Error('company_voice_providers_upsert: provider required');
        }
        const body: JsonObject = {
            provider: p.provider,
            model: typeof p.model === 'string' && p.model.length > 0 ? p.model : null,
            voice: typeof p.voice === 'string' && p.voice.length > 0 ? p.voice : null,
            language: typeof p.language === 'string' && p.language.length > 0 ? p.language : null,
            sample_rate: typeof p.sample_rate === 'number' ? p.sample_rate : null,
            threshold: typeof p.threshold === 'number' ? p.threshold : null,
            response_format: typeof p.response_format === 'string' && p.response_format.length > 0 ? p.response_format : null,
        };
        const sec = p.secrets;
        if (sec !== undefined) {
            body.secrets = sec;
        }
        const response = await httpRequest({
            method: 'PUT',
            url: `/voice/api/v1/companies/${encodeURIComponent(p.company_id)}/voice-providers/${encodeURIComponent(p.kind)}`,
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
        const p = payload as JsonObject | null;
        if (!p || typeof p.company_id !== 'string' || p.company_id.length === 0) {
            throw new Error('company_voice_providers_remove: company_id required');
        }
        if (typeof p.kind !== 'string' || !VOICE_KINDS.includes(p.kind)) {
            throw new Error(`company_voice_providers_remove: unknown kind ${String(p.kind)}`);
        }
        const response = await httpRequest({
            method: 'DELETE',
            url: `/voice/api/v1/companies/${encodeURIComponent(p.company_id)}/voice-providers/${encodeURIComponent(p.kind)}`,
        }) as { deleted?: unknown } | null;
        return { kind: p.kind, deleted: Boolean(response && response.deleted) };
    },
});
