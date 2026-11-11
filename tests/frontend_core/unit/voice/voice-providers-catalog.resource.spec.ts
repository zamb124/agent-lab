/**
 * voice-providers-catalog.resource.js: контракт фабрик каталога речи.
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import {
    companyVoiceProvidersCatalogLoadOp,
    flowsVoiceProvidersCatalogLoadOp,
} from '@platform/lib/events/resources/voice-providers-catalog.resource.js';
import { installFetchMock } from '../../helpers/mock-fetch.js';
import { buildCtx, testEvent } from '../../helpers/bus-fixtures.js';
import type { DispatchedRecord } from '../../helpers/bus-fixtures.js';
import { prop } from '../../helpers/prop.js';
import { resetFactories } from '../../helpers/factory-fixtures.js';

function minimalCatalogPayload() {
    return {
        stt_tts_provider_ids: ['litserve'],
        response_format_ids: [],
        credential_field_groups: {},
        stt_litserve_models: [],
        tts_litserve_models: [],
        tts_litserve_voice_hints: [],
        cloud_ru_stt_models: [],
        cloud_ru_tts_models: [],
        yandex_speech_models: [],
        sber_speech_models: [],
        speech_language_ids: [],
        vad_provider_ids: [],
        tts_sample_rate_ids: [],
        vad_sample_rate_ids: [],
        litserve_tts_sample_rate_ids: [],
        cloud_ru_tts_voice_ids: [],
        yandex_tts_voice_ids: [],
        sber_tts_voice_ids: [],
    };
}

let fetchMock: ReturnType<typeof installFetchMock>;

beforeEach(() => {
    resetFactories();
    fetchMock = installFetchMock();
});
afterEach(() => {
    fetchMock.uninstall();
});

describe('voice-providers-catalog resource', () => {
    it('restMirror, transport и commandType', () => {
        expect(companyVoiceProvidersCatalogLoadOp.restMirror).toEqual({
            method: 'GET',
            path: '/voice/api/v1/voice-providers/catalog',
        });
        expect(companyVoiceProvidersCatalogLoadOp.transport).toBe('http');
        expect(flowsVoiceProvidersCatalogLoadOp.restMirror).toEqual({
            method: 'GET',
            path: '/flows/api/v1/voice-providers/catalog',
        });
        expect(flowsVoiceProvidersCatalogLoadOp.transport).toBe('ws');
        expect(flowsVoiceProvidersCatalogLoadOp.commandType).toBe(
            'flows/voice_providers/catalog_requested',
        );
        expect(companyVoiceProvidersCatalogLoadOp.name).toBe('voice/voice_providers_catalog_load');
        expect(flowsVoiceProvidersCatalogLoadOp.name).toBe('flows/voice_providers_catalog_load');
    });

    it('companyVoiceProvidersCatalogLoadOp: HTTP отдаёт тело каталога как есть', async () => {
        const catalog = minimalCatalogPayload();
        fetchMock.respondJson(
            'GET',
            '/voice/api/v1/voice-providers/catalog',
            catalog,
        );
        const dispatched: DispatchedRecord[] = [];
        await companyVoiceProvidersCatalogLoadOp.effect(
            testEvent(companyVoiceProvidersCatalogLoadOp.events.REQUESTED, null),
            buildCtx(() => ({}), dispatched),
        );
        const ok = dispatched.find((d) => d.type === companyVoiceProvidersCatalogLoadOp.events.SUCCEEDED);
        expect(ok).toBeTruthy();
        expect(prop(ok?.payload, 'result')).toEqual(catalog);
        expect(fetchMock.calls[0]?.url).toBe('/voice/api/v1/voice-providers/catalog');
    });
});
