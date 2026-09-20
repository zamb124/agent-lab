/**
 * Ресурсы владельца voice в core: per-company провайдеры речи и правила произношения.
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import {
    companyVoiceProvidersLoadOp,
    companyVoiceProvidersUpsertOp,
    companyVoiceProvidersRemoveOp,
} from '@platform/lib/events/resources/voice-company-providers.resource.js';
import {
    companyPronunciationRulesLoadOp,
    companyPronunciationRuleCreateOp,
    companyPronunciationRuleUpdateOp,
    companyPronunciationRuleDeleteOp,
    companyPronunciationRuleTestOp,
} from '@platform/lib/events/resources/voice-company-pronunciation-rules.resource.js';
import { installFetchMock } from '../../helpers/mock-fetch.js';
import { buildCtx } from '../../helpers/bus-fixtures.js';
import { resetFactories } from '../../helpers/factory-fixtures.js';

const COMPANY_ID = 'acme';
const PROVIDERS_URL = `/voice/api/v1/companies/${COMPANY_ID}/voice-providers`;
const RULES_URL = `/voice/api/v1/companies/${COMPANY_ID}/pronunciation-rules`;

let fetchMock;

beforeEach(() => {
    resetFactories();
    fetchMock = installFetchMock();
});
afterEach(() => {
    fetchMock.uninstall();
});

async function runOp(op, payload) {
    const dispatched = [];
    await op.effect(
        { type: op.events.REQUESTED, payload, id: 'r1', meta: {} },
        buildCtx(() => ({}), dispatched),
    );
    return dispatched;
}

function succeeded(op, dispatched) {
    const event = dispatched.find((d) => d.type === op.events.SUCCEEDED);
    expect(event, `${op.name} должен завершиться SUCCEEDED`).toBeTruthy();
    return event.payload.result;
}

async function rejects(op, payload, message) {
    await expect(runOp(op, payload)).rejects.toThrow(message);
}

describe('voice company providers resource', () => {
    it('restMirror указывает на API владельца voice', () => {
        expect(companyVoiceProvidersLoadOp.restMirror).toEqual({
            method: 'GET',
            path: '/voice/api/v1/companies/:company_id/voice-providers',
        });
        expect(companyVoiceProvidersUpsertOp.restMirror).toEqual({
            method: 'PUT',
            path: '/voice/api/v1/companies/:company_id/voice-providers/:kind',
        });
        expect(companyVoiceProvidersRemoveOp.restMirror).toEqual({
            method: 'DELETE',
            path: '/voice/api/v1/companies/:company_id/voice-providers/:kind',
        });
        expect(companyVoiceProvidersLoadOp.name).toBe('voice/company_voice_providers_load');
    });

    it('load нормализует items и раскладывает byKind', async () => {
        fetchMock.respondJson('GET', PROVIDERS_URL, {
            company_id: COMPANY_ID,
            items: [
                { kind: 'stt', provider: 'cloud_ru', model: 'general', secrets_meta: { api_key_set: true } },
                { kind: 'tts', provider: 'litserve' },
            ],
        });
        const dispatched = await runOp(companyVoiceProvidersLoadOp, { company_id: COMPANY_ID });
        const result = succeeded(companyVoiceProvidersLoadOp, dispatched);
        expect(result.items).toHaveLength(2);
        expect(result.items[0]).toMatchObject({
            kind: 'stt',
            provider: 'cloud_ru',
            model: 'general',
            secrets_meta: { api_key_set: true, client_secret_set: false, folder_id: null },
        });
        expect(result.items[1].secrets_meta).toBeNull();
        const state = companyVoiceProvidersLoadOp.reducer(
            companyVoiceProvidersLoadOp.initialState,
            { type: companyVoiceProvidersLoadOp.events.SUCCEEDED, payload: { result } },
        );
        expect(state.byKind.stt.provider).toBe('cloud_ru');
        expect(state.byKind.tts.provider).toBe('litserve');
    });

    it('load без company_id и с битым ответом бросает, а не отдаёт тихий пустой список', async () => {
        await rejects(companyVoiceProvidersLoadOp, {}, 'company_id required');
        fetchMock.respondJson('GET', PROVIDERS_URL, { company_id: COMPANY_ID });
        await rejects(companyVoiceProvidersLoadOp, { company_id: COMPANY_ID }, 'response.items required');
    });

    it('upsert шлёт нормализованное тело и возвращает item; remove отдаёт deleted', async () => {
        fetchMock.respondJson('PUT', `${PROVIDERS_URL}/tts`, {
            kind: 'tts',
            provider: 'yandex',
            voice: 'alena',
            sample_rate: 48000,
        });
        const upserted = succeeded(
            companyVoiceProvidersUpsertOp,
            await runOp(companyVoiceProvidersUpsertOp, {
                company_id: COMPANY_ID,
                kind: 'tts',
                provider: 'yandex',
                voice: 'alena',
                model: '',
                sample_rate: 48000,
                secrets: { api_key: 'k' },
            }),
        );
        expect(upserted).toMatchObject({ kind: 'tts', provider: 'yandex', voice: 'alena', model: null });
        const body = JSON.parse(fetchMock.calls[0].init.body);
        expect(body).toMatchObject({ provider: 'yandex', voice: 'alena', model: null, secrets: { api_key: 'k' } });

        await rejects(
            companyVoiceProvidersUpsertOp,
            { company_id: COMPANY_ID, kind: 'vad', provider: 'x' },
            'unknown kind vad',
        );

        fetchMock.respondJson('DELETE', `${PROVIDERS_URL}/stt`, { deleted: true });
        const removed = succeeded(
            companyVoiceProvidersRemoveOp,
            await runOp(companyVoiceProvidersRemoveOp, { company_id: COMPANY_ID, kind: 'stt' }),
        );
        expect(removed).toEqual({ kind: 'stt', deleted: true });
    });
});

describe('voice company pronunciation rules resource', () => {
    it('restMirror указывает на API владельца voice', () => {
        expect(companyPronunciationRulesLoadOp.restMirror.path).toBe(
            '/voice/api/v1/companies/:company_id/pronunciation-rules',
        );
        expect(companyPronunciationRuleUpdateOp.restMirror).toEqual({
            method: 'PUT',
            path: '/voice/api/v1/companies/:company_id/pronunciation-rules/:rule_id',
        });
        expect(companyPronunciationRuleTestOp.restMirror).toEqual({
            method: 'POST',
            path: '/voice/api/v1/companies/:company_id/pronunciation-rules/test',
        });
    });

    it('load нормализует правила; неизвестный kind — ошибка', async () => {
        fetchMock.respondJson('GET', RULES_URL, {
            items: [{ id: 'r1', kind: 'alias', pattern: 'Humanitec', replacement: 'хуманитэк' }],
        });
        const result = succeeded(
            companyPronunciationRulesLoadOp,
            await runOp(companyPronunciationRulesLoadOp, { company_id: COMPANY_ID }),
        );
        expect(result.items[0]).toMatchObject({
            id: 'r1',
            kind: 'alias',
            pattern: 'Humanitec',
            replacement: 'хуманитэк',
            enabled: true,
            word_boundary: true,
            case_sensitive: false,
        });
        const state = companyPronunciationRulesLoadOp.reducer(
            companyPronunciationRulesLoadOp.initialState,
            { type: companyPronunciationRulesLoadOp.events.SUCCEEDED, payload: { result } },
        );
        expect(state.items).toHaveLength(1);

        fetchMock.respondJson('GET', RULES_URL, { items: [{ id: 'r2', kind: 'unknown' }] });
        await rejects(companyPronunciationRulesLoadOp, { company_id: COMPANY_ID }, 'unknown kind unknown');
    });

    it('create/update/delete/test используют пути владельца и нормализуют ответ', async () => {
        fetchMock.respondJson('POST', RULES_URL, { id: 'r9', kind: 'regex', pattern: 'a', replacement: 'b' });
        const created = succeeded(
            companyPronunciationRuleCreateOp,
            await runOp(companyPronunciationRuleCreateOp, {
                company_id: COMPANY_ID,
                kind: 'regex',
                pattern: 'a',
                replacement: 'b',
                providers: [],
            }),
        );
        expect(created).toMatchObject({ id: 'r9', kind: 'regex', providers: null });
        expect(JSON.parse(fetchMock.calls[0].init.body)).toMatchObject({ kind: 'regex', providers: null, enabled: true });

        fetchMock.respondJson('PUT', `${RULES_URL}/r9`, { id: 'r9', kind: 'regex', pattern: 'a', replacement: 'c' });
        const updated = succeeded(
            companyPronunciationRuleUpdateOp,
            await runOp(companyPronunciationRuleUpdateOp, {
                company_id: COMPANY_ID,
                rule_id: 'r9',
                kind: 'regex',
                pattern: 'a',
                replacement: 'c',
            }),
        );
        expect(updated.replacement).toBe('c');
        await rejects(
            companyPronunciationRuleUpdateOp,
            { company_id: COMPANY_ID, kind: 'regex' },
            'rule_id required',
        );

        fetchMock.respondJson('DELETE', `${RULES_URL}/r9`, { deleted: true });
        expect(
            succeeded(
                companyPronunciationRuleDeleteOp,
                await runOp(companyPronunciationRuleDeleteOp, { company_id: COMPANY_ID, rule_id: 'r9' }),
            ),
        ).toEqual({ rule_id: 'r9', deleted: true });

        fetchMock.respondJson('POST', `${RULES_URL}/test`, { original: 'Humanitec', transformed: 'хуманитэк', changed: true });
        expect(
            succeeded(
                companyPronunciationRuleTestOp,
                await runOp(companyPronunciationRuleTestOp, { company_id: COMPANY_ID, text: 'Humanitec' }),
            ),
        ).toEqual({ original: 'Humanitec', transformed: 'хуманитэк', changed: true });
    });
});
