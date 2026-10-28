/**
 * Per-company правила произношения TTS.
 *
 * Бэкенд:
 *   GET    /voice/api/v1/companies/{company_id}/pronunciation-rules       → { company_id, items[] }
 *   POST   /voice/api/v1/companies/{company_id}/pronunciation-rules       → item (201)
 *   PUT    /voice/api/v1/companies/{company_id}/pronunciation-rules/{id}  → item
 *   DELETE /voice/api/v1/companies/{company_id}/pronunciation-rules/{id}  → { deleted }
 *   POST   /voice/api/v1/companies/{company_id}/pronunciation-rules/test  → { original, transformed, changed }
 *
 * Slice (`frontend/companyPronunciationRules`):
 *   { items: [], loading, error, saving, removing }
 */

import { createAsyncOp } from '../index.js';
import { httpRequest } from '../http.js';
import { isPlainRecord } from '../payload.js';

type JsonObject = Record<string, unknown>;

type RuleKind = 'alias' | 'regex' | 'stress';

function isRuleKind(value: unknown): value is RuleKind {
    return value === 'alias' || value === 'regex' || value === 'stress';
}

function isStringList(value: unknown): value is string[] {
    return Array.isArray(value) && value.every((item) => typeof item === 'string');
}

function stringList(value: unknown): string[] | null {
    if (value === undefined || value === null) return null;
    if (!isStringList(value)) {
        throw new Error('pronunciation_rules: list item must be a string');
    }
    return value;
}

export interface PronunciationRule {
    pronunciation_rule_id: string;
    kind: RuleKind;
    pattern: string;
    replacement: string;
    language: string | null;
    case_sensitive: boolean;
    word_boundary: boolean;
    providers: string[] | null;
    voices: string[] | null;
    enabled: boolean;
    note: string | null;
}

function isPronunciationRule(value: unknown): value is PronunciationRule {
    if (!isPlainRecord(value) || typeof value.pronunciation_rule_id !== 'string' || value.pronunciation_rule_id.length === 0) {
        return false;
    }
    if (!isRuleKind(value.kind)) return false;
    if (typeof value.pattern !== 'string' || typeof value.replacement !== 'string') return false;
    if (value.language !== null && typeof value.language !== 'string') return false;
    if (typeof value.case_sensitive !== 'boolean' || typeof value.word_boundary !== 'boolean' || typeof value.enabled !== 'boolean') {
        return false;
    }
    if (value.providers !== null && !isStringList(value.providers)) return false;
    if (value.voices !== null && !isStringList(value.voices)) return false;
    if (value.note !== null && typeof value.note !== 'string') return false;
    return true;
}

function _normalizeRule(raw: unknown): PronunciationRule {
    if (!isPlainRecord(raw)) {
        throw new Error('pronunciation_rules: rule object required');
    }
    const pronunciationRuleId = raw.pronunciation_rule_id;
    if (typeof pronunciationRuleId !== 'string' || pronunciationRuleId.length === 0) {
        throw new Error('pronunciation_rules: pronunciation_rule_id required');
    }
    const kind = raw.kind;
    if (!isRuleKind(kind)) {
        throw new Error(`pronunciation_rules: unknown kind ${String(kind)}`);
    }
    return {
        pronunciation_rule_id: pronunciationRuleId,
        kind,
        pattern: typeof raw.pattern === 'string' ? raw.pattern : '',
        replacement: typeof raw.replacement === 'string' ? raw.replacement : '',
        language: typeof raw.language === 'string' ? raw.language : null,
        case_sensitive: raw.case_sensitive === true,
        word_boundary: raw.word_boundary !== false,
        providers: stringList(raw.providers),
        voices: stringList(raw.voices),
        enabled: raw.enabled !== false,
        note: typeof raw.note === 'string' ? raw.note : null,
    };
}

function _requireCompanyId(payload: unknown, op: string): { p: JsonObject; companyId: string } {
    if (!isPlainRecord(payload)) {
        throw new Error(`${op}: company_id required`);
    }
    const companyId = payload.company_id;
    if (typeof companyId !== 'string' || companyId.length === 0) {
        throw new Error(`${op}: company_id required`);
    }
    return { p: payload, companyId };
}

export const companyPronunciationRulesLoadOp = createAsyncOp({
    name: 'voice/company_pronunciation_rules_load',
    silent: true,
    restMirror: {
        method: 'GET',
        path: '/voice/api/v1/companies/:company_id/pronunciation-rules',
    },
    request: async ({ payload }) => {
        const { companyId } = _requireCompanyId(payload, 'company_pronunciation_rules_load');
        const response = await httpRequest({
            method: 'GET',
            url: `/voice/api/v1/companies/${encodeURIComponent(companyId)}/pronunciation-rules`,
        });
        if (!isPlainRecord(response) || !Array.isArray(response.items)) {
            throw new Error('company_pronunciation_rules_load: response.items required');
        }
        return {
            company_id: companyId,
            items: response.items.map(_normalizeRule),
        };
    },
    extraInitial: {
        items: [],
        saving: false,
        removing: null,
    },
    extraReducer: (state, event, events) => {
        if (event.type === events.SUCCEEDED) {
            if (!isPlainRecord(event.payload) || !isPlainRecord(event.payload.result) || !Array.isArray(event.payload.result.items)) {
                throw new Error('company_pronunciation_rules_load: SUCCEEDED result.items required');
            }
            const items: PronunciationRule[] = [];
            for (const raw of event.payload.result.items) {
                if (!isPronunciationRule(raw)) {
                    throw new Error('company_pronunciation_rules_load: SUCCEEDED item must be a pronunciation rule');
                }
                items.push(raw);
            }
            return { ...state, items };
        }
        return state;
    },
});

export const companyPronunciationRuleCreateOp = createAsyncOp({
    name: 'voice/company_pronunciation_rule_create',
    successToastKey: 'frontend:pronunciation_rules_page.toast_created',
    errorToastKey: 'frontend:pronunciation_rules_page.err_create_failed',
    restMirror: {
        method: 'POST',
        path: '/voice/api/v1/companies/:company_id/pronunciation-rules',
    },
    request: async ({ payload }) => {
        const { p, companyId } = _requireCompanyId(payload, 'company_pronunciation_rule_create');
        const response = await httpRequest({
            method: 'POST',
            url: `/voice/api/v1/companies/${encodeURIComponent(companyId)}/pronunciation-rules`,
            body: {
                kind: p.kind,
                pattern: p.pattern,
                replacement: p.replacement,
                language: typeof p.language === 'string' && p.language.length > 0 ? p.language : null,
                case_sensitive: p.case_sensitive === true,
                word_boundary: p.word_boundary !== false,
                providers: Array.isArray(p.providers) && p.providers.length > 0 ? p.providers : null,
                voices: Array.isArray(p.voices) && p.voices.length > 0 ? p.voices : null,
                enabled: p.enabled !== false,
                note: typeof p.note === 'string' && p.note.length > 0 ? p.note : null,
            },
        });
        return _normalizeRule(response);
    },
});

export const companyPronunciationRuleUpdateOp = createAsyncOp({
    name: 'voice/company_pronunciation_rule_update',
    successToastKey: 'frontend:pronunciation_rules_page.toast_updated',
    errorToastKey: 'frontend:pronunciation_rules_page.err_update_failed',
    restMirror: {
        method: 'PUT',
        path: '/voice/api/v1/companies/:company_id/pronunciation-rules/:rule_id',
    },
    request: async ({ payload }) => {
        const { p, companyId } = _requireCompanyId(payload, 'company_pronunciation_rule_update');
        const ruleId = p.rule_id;
        if (typeof ruleId !== 'string' || ruleId.length === 0) {
            throw new Error('company_pronunciation_rule_update: rule_id required');
        }
        const body: JsonObject = {};
        if (p.kind !== undefined) body.kind = p.kind;
        if (p.pattern !== undefined) body.pattern = p.pattern;
        if (p.replacement !== undefined) body.replacement = p.replacement;
        if (p.language !== undefined) body.language = typeof p.language === 'string' && p.language.length > 0 ? p.language : null;
        if (p.case_sensitive !== undefined) body.case_sensitive = p.case_sensitive === true;
        if (p.word_boundary !== undefined) body.word_boundary = p.word_boundary !== false;
        if (p.providers !== undefined) body.providers = Array.isArray(p.providers) && p.providers.length > 0 ? p.providers : null;
        if (p.voices !== undefined) body.voices = Array.isArray(p.voices) && p.voices.length > 0 ? p.voices : null;
        if (p.enabled !== undefined) body.enabled = p.enabled !== false;
        if (p.note !== undefined) body.note = typeof p.note === 'string' && p.note.length > 0 ? p.note : null;
        const response = await httpRequest({
            method: 'PUT',
            url: `/voice/api/v1/companies/${encodeURIComponent(companyId)}/pronunciation-rules/${encodeURIComponent(ruleId)}`,
            body,
        });
        return _normalizeRule(response);
    },
});

export const companyPronunciationRuleDeleteOp = createAsyncOp({
    name: 'voice/company_pronunciation_rule_delete',
    successToastKey: 'frontend:pronunciation_rules_page.toast_deleted',
    errorToastKey: 'frontend:pronunciation_rules_page.err_delete_failed',
    restMirror: {
        method: 'DELETE',
        path: '/voice/api/v1/companies/:company_id/pronunciation-rules/:rule_id',
    },
    request: async ({ payload }) => {
        const { p, companyId } = _requireCompanyId(payload, 'company_pronunciation_rule_delete');
        const ruleId = p.rule_id;
        if (typeof ruleId !== 'string' || ruleId.length === 0) {
            throw new Error('company_pronunciation_rule_delete: rule_id required');
        }
        const response = await httpRequest({
            method: 'DELETE',
            url: `/voice/api/v1/companies/${encodeURIComponent(companyId)}/pronunciation-rules/${encodeURIComponent(ruleId)}`,
        });
        if (!isPlainRecord(response)) {
            throw new Error('company_pronunciation_rule_delete: response must be an object');
        }
        return { rule_id: ruleId, deleted: response.deleted === true };
    },
});

export const companyPronunciationRuleTestOp = createAsyncOp({
    name: 'voice/company_pronunciation_rule_test',
    silent: true,
    restMirror: {
        method: 'POST',
        path: '/voice/api/v1/companies/:company_id/pronunciation-rules/test',
    },
    request: async ({ payload }) => {
        const { p, companyId } = _requireCompanyId(payload, 'company_pronunciation_rule_test');
        const response = await httpRequest({
            method: 'POST',
            url: `/voice/api/v1/companies/${encodeURIComponent(companyId)}/pronunciation-rules/test`,
            body: {
                text: p.text,
                provider: typeof p.provider === 'string' && p.provider.length > 0 ? p.provider : 'litserve',
                voice: typeof p.voice === 'string' && p.voice.length > 0 ? p.voice : null,
                language: typeof p.language === 'string' && p.language.length > 0 ? p.language : null,
            },
        });
        if (!isPlainRecord(response) || typeof response.original !== 'string' || typeof response.transformed !== 'string') {
            throw new Error('company_pronunciation_rule_test: original and transformed required');
        }
        return {
            original: response.original,
            transformed: response.transformed,
            changed: response.changed === true,
        };
    },
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'voice/company_pronunciation_rules_load': typeof companyPronunciationRulesLoadOp;
        'voice/company_pronunciation_rule_create': typeof companyPronunciationRuleCreateOp;
        'voice/company_pronunciation_rule_update': typeof companyPronunciationRuleUpdateOp;
        'voice/company_pronunciation_rule_delete': typeof companyPronunciationRuleDeleteOp;
        'voice/company_pronunciation_rule_test': typeof companyPronunciationRuleTestOp;
    }
}
