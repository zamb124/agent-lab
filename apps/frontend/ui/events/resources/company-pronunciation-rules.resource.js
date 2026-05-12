/**
 * Per-company правила произношения TTS.
 *
 * Backend:
 *   GET    /frontend/api/companies/{company_id}/pronunciation-rules       → { company_id, items[] }
 *   POST   /frontend/api/companies/{company_id}/pronunciation-rules       → item (201)
 *   PUT    /frontend/api/companies/{company_id}/pronunciation-rules/{id}  → item
 *   DELETE /frontend/api/companies/{company_id}/pronunciation-rules/{id}  → { deleted }
 *   POST   /frontend/api/companies/{company_id}/pronunciation-rules/test  → { original, transformed, changed }
 *
 * Slice (`frontend/companyPronunciationRules`):
 *   { items: [], loading, error, saving, removing }
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

const VALID_KINDS = ['alias', 'regex', 'stress'];

function _normalizeRule(raw) {
    if (!raw || typeof raw !== 'object') {
        throw new Error('pronunciation_rules: rule object required');
    }
    if (typeof raw.id !== 'string' || raw.id.length === 0) {
        throw new Error('pronunciation_rules: id required');
    }
    if (!VALID_KINDS.includes(raw.kind)) {
        throw new Error(`pronunciation_rules: unknown kind ${raw.kind}`);
    }
    return {
        id: raw.id,
        kind: raw.kind,
        pattern: typeof raw.pattern === 'string' ? raw.pattern : '',
        replacement: typeof raw.replacement === 'string' ? raw.replacement : '',
        language: typeof raw.language === 'string' ? raw.language : null,
        case_sensitive: raw.case_sensitive === true,
        word_boundary: raw.word_boundary !== false,
        providers: Array.isArray(raw.providers) ? raw.providers : null,
        voices: Array.isArray(raw.voices) ? raw.voices : null,
        enabled: raw.enabled !== false,
        note: typeof raw.note === 'string' ? raw.note : null,
    };
}

export const companyPronunciationRulesLoadOp = createAsyncOp({
    name: 'frontend/company_pronunciation_rules_load',
    silent: true,
    restMirror: {
        method: 'GET',
        path: '/frontend/api/companies/:company_id/pronunciation-rules',
    },
    request: async ({ payload }) => {
        if (!payload || typeof payload.company_id !== 'string' || payload.company_id.length === 0) {
            throw new Error('company_pronunciation_rules_load: company_id required');
        }
        const response = await httpRequest({
            method: 'GET',
            url: `/frontend/api/companies/${encodeURIComponent(payload.company_id)}/pronunciation-rules`,
        });
        if (!Array.isArray(response.items)) {
            throw new Error('company_pronunciation_rules_load: response.items required');
        }
        return {
            company_id: payload.company_id,
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
            const result = event.payload && event.payload.result;
            if (!result || !Array.isArray(result.items)) return state;
            return { ...state, items: result.items };
        }
        return state;
    },
});

export const companyPronunciationRuleCreateOp = createAsyncOp({
    name: 'frontend/company_pronunciation_rule_create',
    successToastKey: 'frontend:pronunciation_rules_page.toast_created',
    errorToastKey: 'frontend:pronunciation_rules_page.err_create_failed',
    restMirror: {
        method: 'POST',
        path: '/frontend/api/companies/:company_id/pronunciation-rules',
    },
    request: async ({ payload }) => {
        if (!payload || typeof payload.company_id !== 'string' || payload.company_id.length === 0) {
            throw new Error('company_pronunciation_rule_create: company_id required');
        }
        const response = await httpRequest({
            method: 'POST',
            url: `/frontend/api/companies/${encodeURIComponent(payload.company_id)}/pronunciation-rules`,
            body: {
                kind: payload.kind,
                pattern: payload.pattern,
                replacement: payload.replacement,
                language: typeof payload.language === 'string' && payload.language.length > 0 ? payload.language : null,
                case_sensitive: payload.case_sensitive === true,
                word_boundary: payload.word_boundary !== false,
                providers: Array.isArray(payload.providers) && payload.providers.length > 0 ? payload.providers : null,
                voices: Array.isArray(payload.voices) && payload.voices.length > 0 ? payload.voices : null,
                enabled: payload.enabled !== false,
                note: typeof payload.note === 'string' && payload.note.length > 0 ? payload.note : null,
            },
        });
        return _normalizeRule(response);
    },
});

export const companyPronunciationRuleUpdateOp = createAsyncOp({
    name: 'frontend/company_pronunciation_rule_update',
    successToastKey: 'frontend:pronunciation_rules_page.toast_updated',
    errorToastKey: 'frontend:pronunciation_rules_page.err_update_failed',
    restMirror: {
        method: 'PUT',
        path: '/frontend/api/companies/:company_id/pronunciation-rules/:rule_id',
    },
    request: async ({ payload }) => {
        if (!payload || typeof payload.company_id !== 'string' || payload.company_id.length === 0) {
            throw new Error('company_pronunciation_rule_update: company_id required');
        }
        if (typeof payload.rule_id !== 'string' || payload.rule_id.length === 0) {
            throw new Error('company_pronunciation_rule_update: rule_id required');
        }
        const body = {};
        if (payload.kind !== undefined) body.kind = payload.kind;
        if (payload.pattern !== undefined) body.pattern = payload.pattern;
        if (payload.replacement !== undefined) body.replacement = payload.replacement;
        if (payload.language !== undefined) body.language = typeof payload.language === 'string' && payload.language.length > 0 ? payload.language : null;
        if (payload.case_sensitive !== undefined) body.case_sensitive = payload.case_sensitive === true;
        if (payload.word_boundary !== undefined) body.word_boundary = payload.word_boundary !== false;
        if (payload.providers !== undefined) body.providers = Array.isArray(payload.providers) && payload.providers.length > 0 ? payload.providers : null;
        if (payload.voices !== undefined) body.voices = Array.isArray(payload.voices) && payload.voices.length > 0 ? payload.voices : null;
        if (payload.enabled !== undefined) body.enabled = payload.enabled !== false;
        if (payload.note !== undefined) body.note = typeof payload.note === 'string' && payload.note.length > 0 ? payload.note : null;
        const response = await httpRequest({
            method: 'PUT',
            url: `/frontend/api/companies/${encodeURIComponent(payload.company_id)}/pronunciation-rules/${encodeURIComponent(payload.rule_id)}`,
            body,
        });
        return _normalizeRule(response);
    },
});

export const companyPronunciationRuleDeleteOp = createAsyncOp({
    name: 'frontend/company_pronunciation_rule_delete',
    successToastKey: 'frontend:pronunciation_rules_page.toast_deleted',
    errorToastKey: 'frontend:pronunciation_rules_page.err_delete_failed',
    restMirror: {
        method: 'DELETE',
        path: '/frontend/api/companies/:company_id/pronunciation-rules/:rule_id',
    },
    request: async ({ payload }) => {
        if (!payload || typeof payload.company_id !== 'string' || payload.company_id.length === 0) {
            throw new Error('company_pronunciation_rule_delete: company_id required');
        }
        if (typeof payload.rule_id !== 'string' || payload.rule_id.length === 0) {
            throw new Error('company_pronunciation_rule_delete: rule_id required');
        }
        const response = await httpRequest({
            method: 'DELETE',
            url: `/frontend/api/companies/${encodeURIComponent(payload.company_id)}/pronunciation-rules/${encodeURIComponent(payload.rule_id)}`,
        });
        return { rule_id: payload.rule_id, deleted: !!response.deleted };
    },
});

export const companyPronunciationRuleTestOp = createAsyncOp({
    name: 'frontend/company_pronunciation_rule_test',
    silent: true,
    restMirror: {
        method: 'POST',
        path: '/frontend/api/companies/:company_id/pronunciation-rules/test',
    },
    request: async ({ payload }) => {
        if (!payload || typeof payload.company_id !== 'string' || payload.company_id.length === 0) {
            throw new Error('company_pronunciation_rule_test: company_id required');
        }
        const response = await httpRequest({
            method: 'POST',
            url: `/frontend/api/companies/${encodeURIComponent(payload.company_id)}/pronunciation-rules/test`,
            body: {
                text: payload.text,
                provider: typeof payload.provider === 'string' && payload.provider.length > 0 ? payload.provider : 'litserve',
                voice: typeof payload.voice === 'string' && payload.voice.length > 0 ? payload.voice : null,
                language: typeof payload.language === 'string' && payload.language.length > 0 ? payload.language : null,
            },
        });
        return {
            original: response.original,
            transformed: response.transformed,
            changed: response.changed === true,
        };
    },
});
