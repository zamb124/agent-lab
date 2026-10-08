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

type JsonObject = Record<string, unknown>;

type RuleKind = 'alias' | 'regex' | 'stress';
const VALID_KINDS: readonly string[] = ['alias', 'regex', 'stress'];

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

function _normalizeRule(raw: unknown): PronunciationRule {
    if (!raw || typeof raw !== 'object') {
        throw new Error('pronunciation_rules: rule object required');
    }
    const r = raw as JsonObject;
    if (typeof r.pronunciation_rule_id !== 'string' || r.pronunciation_rule_id.length === 0) {
        throw new Error('pronunciation_rules: pronunciation_rule_id required');
    }
    if (typeof r.kind !== 'string' || !VALID_KINDS.includes(r.kind)) {
        throw new Error(`pronunciation_rules: unknown kind ${String(r.kind)}`);
    }
    return {
        pronunciation_rule_id: r.pronunciation_rule_id,
        kind: r.kind as RuleKind,
        pattern: typeof r.pattern === 'string' ? r.pattern : '',
        replacement: typeof r.replacement === 'string' ? r.replacement : '',
        language: typeof r.language === 'string' ? r.language : null,
        case_sensitive: r.case_sensitive === true,
        word_boundary: r.word_boundary !== false,
        providers: Array.isArray(r.providers) ? r.providers as string[] : null,
        voices: Array.isArray(r.voices) ? r.voices as string[] : null,
        enabled: r.enabled !== false,
        note: typeof r.note === 'string' ? r.note : null,
    };
}

function _requireCompanyId(payload: unknown, op: string): { p: JsonObject; companyId: string } {
    const p = payload as JsonObject | null;
    if (!p || typeof p.company_id !== 'string' || p.company_id.length === 0) {
        throw new Error(`${op}: company_id required`);
    }
    return { p, companyId: p.company_id };
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
        }) as { items?: unknown } | null;
        if (!response || !Array.isArray(response.items)) {
            throw new Error('company_pronunciation_rules_load: response.items required');
        }
        return {
            company_id: companyId,
            items: (response.items as unknown[]).map(_normalizeRule),
        };
    },
    extraInitial: {
        items: [],
        saving: false,
        removing: null,
    },
    extraReducer: (state, event, events) => {
        if (event.type === events.SUCCEEDED) {
            const result = (event.payload as { result?: { items?: unknown } } | null)?.result;
            if (!result || !Array.isArray(result.items)) return state;
            return { ...state, items: result.items };
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
        if (typeof p.rule_id !== 'string' || p.rule_id.length === 0) {
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
            url: `/voice/api/v1/companies/${encodeURIComponent(companyId)}/pronunciation-rules/${encodeURIComponent(p.rule_id)}`,
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
        if (typeof p.rule_id !== 'string' || p.rule_id.length === 0) {
            throw new Error('company_pronunciation_rule_delete: rule_id required');
        }
        const response = await httpRequest({
            method: 'DELETE',
            url: `/voice/api/v1/companies/${encodeURIComponent(companyId)}/pronunciation-rules/${encodeURIComponent(p.rule_id)}`,
        }) as { deleted?: unknown } | null;
        return { rule_id: p.rule_id, deleted: Boolean(response && response.deleted) };
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
        }) as { original?: unknown; transformed?: unknown; changed?: unknown } | null;
        return {
            original: response && response.original,
            transformed: response && response.transformed,
            changed: response?.changed === true,
        };
    },
});
