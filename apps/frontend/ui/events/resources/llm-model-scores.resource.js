/**
 * System-only platform LLM model scoring.
 *
 * API:
 *   GET    /frontend/api/platform/llm-model-scores
 *   PUT    /frontend/api/platform/llm-model-scores
 *   DELETE /frontend/api/platform/llm-model-scores/:capability/:provider/:model_id
 *   POST   /frontend/api/platform/llm-model-scores/refresh-cache
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

const BASE = '/frontend/api/platform/llm-model-scores';

export const llmModelScoresLoadOp = createAsyncOp({
    name: 'frontend/llm_model_scores_load',
    silent: true,
    restMirror: { method: 'GET', path: '/frontend/api/platform/llm-model-scores' },
    request: async () => await httpRequest({
        method: 'GET',
        url: BASE,
    }),
});

export const llmModelScoreUpsertOp = createAsyncOp({
    name: 'frontend/llm_model_score_upsert',
    successToastKey: 'frontend:settings_page.model_scoring.toast_saved',
    errorToastKey: 'frontend:settings_page.model_scoring.toast_failed',
    restMirror: { method: 'PUT', path: '/frontend/api/platform/llm-model-scores' },
    request: async ({ payload }) => {
        if (!payload || typeof payload !== 'object') {
            throw new Error('llm_model_score_upsert: payload required');
        }
        return await httpRequest({
            method: 'PUT',
            url: BASE,
            body: payload,
        });
    },
    onSuccess: (ctx) => {
        ctx.dispatch(llmModelScoresLoadOp.events.REQUESTED, null, { source: 'local' });
    },
});

export const llmModelScoreDeleteOp = createAsyncOp({
    name: 'frontend/llm_model_score_delete',
    successToastKey: 'frontend:settings_page.model_scoring.toast_deleted',
    errorToastKey: 'frontend:settings_page.model_scoring.toast_failed',
    restMirror: { method: 'DELETE', path: '/frontend/api/platform/llm-model-scores/{capability}/{provider}/{model_id:path}' },
    request: async ({ payload }) => {
        if (!payload || typeof payload !== 'object') {
            throw new Error('llm_model_score_delete: payload required');
        }
        if (!payload.capability || !payload.provider || !payload.model_id) {
            throw new Error('llm_model_score_delete: capability/provider/model_id required');
        }
        return await httpRequest({
            method: 'DELETE',
            url: `${BASE}/${encodeURIComponent(payload.capability)}/${encodeURIComponent(payload.provider)}/${encodeURIComponent(payload.model_id)}`,
        });
    },
    onSuccess: (ctx) => {
        ctx.dispatch(llmModelScoresLoadOp.events.REQUESTED, null, { source: 'local' });
    },
});

export const llmModelScoresRefreshCacheOp = createAsyncOp({
    name: 'frontend/llm_model_scores_refresh_cache',
    successToastKey: 'frontend:settings_page.model_scoring.toast_cache_refreshed',
    errorToastKey: 'frontend:settings_page.model_scoring.toast_cache_failed',
    restMirror: { method: 'POST', path: '/frontend/api/platform/llm-model-scores/refresh-cache' },
    request: async () => await httpRequest({
        method: 'POST',
        url: `${BASE}/refresh-cache`,
        body: {},
    }),
    onSuccess: (ctx) => {
        ctx.dispatch(llmModelScoresLoadOp.events.REQUESTED, null, { source: 'local' });
    },
});
