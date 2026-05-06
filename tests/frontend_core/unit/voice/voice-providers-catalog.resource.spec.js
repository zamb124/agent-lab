/**
 * voice-providers-catalog.resource.js: GET каталога + нормализация DTO.
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import {
    companyVoiceProvidersCatalogLoadOp,
    flowsVoiceProvidersCatalogLoadOp,
} from '@platform/lib/events/resources/voice-providers-catalog.resource.js';
import { installFetchMock } from '../../helpers/mock-fetch.js';
import { buildCtx } from '../../helpers/bus-fixtures.js';
import { resetFactories } from '../../helpers/factory-fixtures.js';

function minimalCatalogPayload(overrides = {}) {
    return {
        stt_tts_provider_ids: [],
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
        litserve_silero_tts_sample_rate_ids: [],
        cloud_ru_tts_voice_ids: [],
        yandex_tts_voice_ids: [],
        sber_tts_voice_ids: [],
        ...overrides,
    };
}

let fetchMock;

beforeEach(() => {
    resetFactories();
    fetchMock = installFetchMock();
});
afterEach(() => {
    fetchMock.uninstall();
});

describe('voice-providers-catalog resource', () => {
    it('restMirror и silent для обеих операций', () => {
        expect(companyVoiceProvidersCatalogLoadOp.restMirror).toEqual({
            method: 'GET',
            path: '/frontend/api/voice-providers/catalog',
        });
        expect(flowsVoiceProvidersCatalogLoadOp.restMirror).toEqual({
            method: 'GET',
            path: '/flows/api/v1/voice-providers/catalog',
        });
        expect(companyVoiceProvidersCatalogLoadOp.name).toBe('frontend/voice_providers_catalog_load');
        expect(flowsVoiceProvidersCatalogLoadOp.name).toBe('flows/voice_providers_catalog_load');
    });

    it('companyVoiceProvidersCatalogLoadOp: успех и нормализация', async () => {
        fetchMock.respondJson(
            'GET',
            '/frontend/api/voice-providers/catalog',
            minimalCatalogPayload({
                stt_tts_provider_ids: ['a', 'b'],
                credential_field_groups: { yandex_cloud: [['key']] },
                tts_litserve_voice_hints: [
                    { api_model_id: 'm1', voice_ids: ['z', 'a'], default_voice: 'z' },
                    { api_model_id: 'm2', default_voice: null },
                ],
                tts_sample_rate_ids: [8000, '24000'],
            }),
        );
        const dispatched = [];
        await companyVoiceProvidersCatalogLoadOp.effect(
            {
                type: companyVoiceProvidersCatalogLoadOp.events.REQUESTED,
                payload: null,
                id: 'r1',
                meta: {},
            },
            buildCtx(() => ({}), dispatched),
        );
        const ok = dispatched.find((d) => d.type === companyVoiceProvidersCatalogLoadOp.events.SUCCEEDED);
        expect(ok).toBeTruthy();
        const catalog = ok.payload.result;
        expect(catalog.stt_tts_provider_ids).toEqual(['a', 'b']);
        expect(Object.isFrozen(catalog.stt_tts_provider_ids)).toBe(true);
        expect(catalog.tts_litserve_voice_hints[0].voice_ids).toEqual(['a', 'z']);
        expect(Object.isFrozen(catalog.tts_litserve_voice_hints[0].voice_ids)).toBe(true);
        expect(catalog.tts_litserve_voice_hints[1].voice_ids).toEqual([]);
        expect(catalog.tts_sample_rate_ids).toEqual([8000, 24000]);
        expect(fetchMock.calls[0].url).toBe('/frontend/api/voice-providers/catalog');
    });

    it('flowsVoiceProvidersCatalogLoadOp: успех', async () => {
        fetchMock.respondJson(
            'GET',
            '/flows/api/v1/voice-providers/catalog',
            minimalCatalogPayload(),
        );
        const dispatched = [];
        await flowsVoiceProvidersCatalogLoadOp.effect(
            {
                type: flowsVoiceProvidersCatalogLoadOp.events.REQUESTED,
                payload: null,
                id: 'r2',
                meta: {},
            },
            buildCtx(() => ({}), dispatched),
        );
        const ok = dispatched.find((d) => d.type === flowsVoiceProvidersCatalogLoadOp.events.SUCCEEDED);
        expect(ok.payload.result.tts_litserve_voice_hints).toEqual([]);
        expect(fetchMock.calls[0].url).toBe('/flows/api/v1/voice-providers/catalog');
    });

    it('ошибка нормализации пробрасывается (silent, без FAILED как HttpError)', async () => {
        fetchMock.respondJson(
            'GET',
            '/frontend/api/voice-providers/catalog',
            minimalCatalogPayload({ tts_litserve_voice_hints: [{}] }),
        );
        await expect(
            companyVoiceProvidersCatalogLoadOp.effect(
                {
                    type: companyVoiceProvidersCatalogLoadOp.events.REQUESTED,
                    payload: null,
                    id: 'r3',
                    meta: {},
                },
                buildCtx(() => ({}), []),
            ),
        ).rejects.toThrow(/tts_litserve_voice_hints/);
    });
});
