/**
 * System-only platform LLM model scoring — команды `frontend/llm_model_scores/*`
 * (REST-зеркало `apps/frontend/api/platform_llm_model_scores.py`).
 * Список валидируется fail-closed в `extraReducer` (`normalizeLlmModelScoreList`) и кладётся в `lastResult`.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import type { PlatformEvent } from '@platform/lib/events/contract.js';
import type { AsyncOpSlice } from '@platform/lib/events/factories/async-op.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';

function anyRecord(value: unknown): Record<string, any> | null {
    if (!isPlainRecord(value)) return null;
    const row: Record<string, any> = {};
    for (const [key, field] of Object.entries(value)) row[key] = field;
    return row;
}

const WS_TIMEOUT_MS = 30_000;

const AVAILABILITY = new Set(['available', 'cooldown', 'disabled', 'not_configured']);
const ERROR_CLASS = new Set([
    'rate_limited',
    'payment_required',
    'auth_rejected',
    'timeout',
    'transient',
    'http_error',
    'transport',
    'content_filter',
    'unspecified',
]);

function _requireString(value: unknown, label: string) {
    if (typeof value !== 'string' || value === '') {
        throw new Error(`llm_model_scores: ${label} must be a non-empty string`);
    }
    return value;
}

function _optionalString(value: unknown, label: string) {
    if (value === null) {
        return null;
    }
    if (typeof value !== 'string') {
        throw new Error(`llm_model_scores: ${label} must be a string or null`);
    }
    return value;
}

function _optionalNumber(value: unknown, label: string) {
    if (value === null) {
        return null;
    }
    if (typeof value !== 'number' || !Number.isFinite(value)) {
        throw new Error(`llm_model_scores: ${label} must be a finite number or null`);
    }
    return value;
}

function _optionalErrorClass(value: unknown, label: string) {
    if (value === null) {
        return null;
    }
    if (typeof value !== 'string' || !ERROR_CLASS.has(value)) {
        throw new Error(`llm_model_scores: ${label} is not a known error_class`);
    }
    return value;
}

export function normalizeLlmModelScoreItem(raw: Record<string, any>) {
    if (!raw || typeof raw !== 'object') {
        throw new Error('llm_model_scores: item must be an object');
    }
    if (typeof raw.score !== 'number' || !Number.isFinite(raw.score)) {
        throw new Error('llm_model_scores: score must be a finite number');
    }
    if (typeof raw.enabled !== 'boolean') {
        throw new Error('llm_model_scores: enabled must be a boolean');
    }
    if (typeof raw.availability !== 'string' || !AVAILABILITY.has(raw.availability)) {
        throw new Error('llm_model_scores: availability is required');
    }
    if (typeof raw.editorial_prior !== 'number' || !Number.isFinite(raw.editorial_prior)) {
        throw new Error('llm_model_scores: editorial_prior must be a finite number');
    }
    if (!raw.score_breakdown || typeof raw.score_breakdown !== 'object' || Array.isArray(raw.score_breakdown)) {
        throw new Error('llm_model_scores: score_breakdown must be an object');
    }
    if (typeof raw.has_overlay_row !== 'boolean') {
        throw new Error('llm_model_scores: has_overlay_row must be a boolean');
    }
    return {
        provider: _requireString(raw.provider, 'provider'),
        model_id: _requireString(raw.model_id, 'model_id'),
        capability: _requireString(raw.capability, 'capability'),
        score: raw.score,
        enabled: raw.enabled,
        editorial_prior: raw.editorial_prior,
        note: _optionalString(raw.note, 'note'),
        has_overlay_row: raw.has_overlay_row,
        intelligence_index: _optionalNumber(raw.intelligence_index, 'intelligence_index'),
        coding_index: _optionalNumber(raw.coding_index, 'coding_index'),
        agentic_index: _optionalNumber(raw.agentic_index, 'agentic_index'),
        score_breakdown: raw.score_breakdown,
        updated_by_user_id: _optionalString(raw.updated_by_user_id, 'updated_by_user_id'),
        created_at: _optionalString(raw.created_at, 'created_at'),
        updated_at: _optionalString(raw.updated_at, 'updated_at'),
        availability: raw.availability,
        cooldown_seconds: _optionalNumber(raw.cooldown_seconds, 'cooldown_seconds'),
        error_class: _optionalErrorClass(raw.error_class, 'error_class'),
        error_text: _optionalString(raw.error_text, 'error_text'),
        http_status: _optionalNumber(raw.http_status, 'http_status'),
    };
}

export function normalizeLlmProviderRuntimeStatus(raw: Record<string, any>) {
    if (!raw || typeof raw !== 'object') {
        throw new Error('llm_model_scores: provider status must be an object');
    }
    if (typeof raw.configured !== 'boolean') {
        throw new Error('llm_model_scores: configured must be a boolean');
    }
    if (typeof raw.availability !== 'string' || !AVAILABILITY.has(raw.availability)) {
        throw new Error('llm_model_scores: provider availability is required');
    }
    if (typeof raw.model_count !== 'number' || !Number.isFinite(raw.model_count)) {
        throw new Error('llm_model_scores: model_count must be a finite number');
    }
    if (typeof raw.blocked_model_count !== 'number' || !Number.isFinite(raw.blocked_model_count)) {
        throw new Error('llm_model_scores: blocked_model_count must be a finite number');
    }
    return {
        provider: _requireString(raw.provider, 'provider'),
        configured: raw.configured,
        availability: raw.availability,
        model_count: raw.model_count,
        blocked_model_count: raw.blocked_model_count,
        cooldown_seconds: _optionalNumber(raw.cooldown_seconds, 'cooldown_seconds'),
        error_class: _optionalErrorClass(raw.error_class, 'error_class'),
        error_text: _optionalString(raw.error_text, 'error_text'),
        http_status: _optionalNumber(raw.http_status, 'http_status'),
        last_probe: _optionalProbeSnapshot(raw.last_probe, 'last_probe'),
    };
}

function _optionalProbeSnapshot(value: unknown, label: string) {
    if (value === null) {
        return null;
    }
    const probe = anyRecord(value);
    if (probe === null) {
        throw new Error(`llm_model_scores: ${label} must be an object or null`);
    }
    const ok = probe.ok;
    if (typeof ok !== 'boolean') {
        throw new Error(`llm_model_scores: ${label}.ok must be a boolean`);
    }
    return {
        provider: _requireString(probe.provider, `${label}.provider`),
        probed_at: _requireString(probe.probed_at, `${label}.probed_at`),
        ok,
        error_class: _optionalErrorClass(probe.error_class, `${label}.error_class`),
        error_text: _optionalString(probe.error_text, `${label}.error_text`),
        http_status: _optionalNumber(probe.http_status, `${label}.http_status`),
        smoke_model: _optionalString(probe.smoke_model, `${label}.smoke_model`),
    };
}

export function normalizeLlmModelScoreList(raw: Record<string, any>) {
    if (!raw || typeof raw !== 'object') {
        throw new Error('llm_model_scores: response must be an object');
    }
    if (!Array.isArray(raw.items)) {
        throw new Error('llm_model_scores: items must be an array');
    }
    if (!Array.isArray(raw.providers)) {
        throw new Error('llm_model_scores: providers must be an array');
    }
    return {
        items: raw.items.map(normalizeLlmModelScoreItem),
        providers: raw.providers.map(normalizeLlmProviderRuntimeStatus),
    };
}

function _normalizedListReducer(state: AsyncOpSlice, event: PlatformEvent, events: Readonly<Record<string, string>>): AsyncOpSlice {
    if (event.type === events.SUCCEEDED) {
        const payload = anyRecord(event.payload);
        const result = payload === null ? null : anyRecord(payload.result);
        if (result === null) {
            throw new Error('llm_model_scores: response must be an object');
        }
        return { ...state, lastResult: normalizeLlmModelScoreList(result) };
    }
    return state;
}

export const llmModelScoresLoadOp = createAsyncOp({
    name: 'frontend/llm_model_scores_load',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'frontend/llm_model_scores/list_requested',
    restMirror: { method: 'GET', path: '/frontend/api/platform/llm-model-scores' },
    extraReducer: _normalizedListReducer,
});

export const llmModelScoreUpsertOp = createAsyncOp({
    name: 'frontend/llm_model_score_upsert',
    successToastKey: 'frontend:settings_page.model_scoring.toast_saved',
    errorToastKey: 'frontend:settings_page.model_scoring.toast_failed',
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'frontend/llm_model_scores/upsert_requested',
    restMirror: { method: 'PUT', path: '/frontend/api/platform/llm-model-scores' },
    onSuccess: (ctx) => {
        ctx.dispatch(llmModelScoresLoadOp.events.REQUESTED, null, { source: 'local' });
    },
});

export const llmModelScoreDeleteOp = createAsyncOp({
    name: 'frontend/llm_model_score_delete',
    successToastKey: 'frontend:settings_page.model_scoring.toast_deleted',
    errorToastKey: 'frontend:settings_page.model_scoring.toast_failed',
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'frontend/llm_model_scores/delete_requested',
    restMirror: { method: 'DELETE', path: '/frontend/api/platform/llm-model-scores/:capability/:provider/:model_id' },
    onSuccess: (ctx) => {
        ctx.dispatch(llmModelScoresLoadOp.events.REQUESTED, null, { source: 'local' });
    },
});

export const llmModelScoresRefreshCacheOp = createAsyncOp({
    name: 'frontend/llm_model_scores_refresh_cache',
    successToastKey: 'frontend:settings_page.model_scoring.toast_cache_refreshed',
    errorToastKey: 'frontend:settings_page.model_scoring.toast_cache_failed',
    transport: 'ws',
    wsTimeoutMs: 60_000,
    commandType: 'frontend/llm_model_scores/refresh_cache_requested',
    restMirror: { method: 'POST', path: '/frontend/api/platform/llm-model-scores/refresh-cache' },
    onSuccess: (ctx) => {
        ctx.dispatch(llmModelScoresLoadOp.events.REQUESTED, null, { source: 'local' });
    },
});

export const llmModelScoresProbeProvidersOp = createAsyncOp({
    name: 'frontend/llm_model_scores_probe_providers',
    successToastKey: 'frontend:settings_page.model_scoring.toast_probe_done',
    errorToastKey: 'frontend:settings_page.model_scoring.toast_probe_failed',
    transport: 'ws',
    wsTimeoutMs: 60_000,
    commandType: 'frontend/llm_model_scores/probe_providers_requested',
    restMirror: { method: 'POST', path: '/frontend/api/platform/llm-model-scores/probe-providers' },
    extraReducer: _normalizedListReducer,
    onSuccess: (ctx) => {
        ctx.dispatch(llmModelScoresLoadOp.events.REQUESTED, null, { source: 'local' });
    },
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'frontend/llm_model_scores_load': typeof llmModelScoresLoadOp;
        'frontend/llm_model_score_upsert': typeof llmModelScoreUpsertOp;
        'frontend/llm_model_score_delete': typeof llmModelScoreDeleteOp;
        'frontend/llm_model_scores_refresh_cache': typeof llmModelScoresRefreshCacheOp;
        'frontend/llm_model_scores_probe_providers': typeof llmModelScoresProbeProvidersOp;
    }
}
