/**
 * Ресурсы настроек — настройки компании.
 *
 * API:
 *   GET   /frontend/api/settings/company         → profile (name/subdomain/budget/metadata)
 *   PATCH /frontend/api/settings/company         ← CompanySettingsUpdate (без AI providers)
 *   GET   /frontend/api/settings/ai-providers    → capabilities + custom + catalog
 *   PUT   /frontend/api/settings/ai-providers/llm-context
 *   DELETE /frontend/api/settings/ai-providers/llm-context
 *   PUT   /frontend/api/settings/ai-providers/:capability  ← AIProvidersCapabilityUpdate
 *   DELETE /frontend/api/settings/ai-providers/:capability
 *   POST  /frontend/api/settings/ai-providers/custom              ← CustomProviderCreate
 *   PATCH /frontend/api/settings/ai-providers/custom/:id          ← CustomProviderUpdate
 *   DELETE /frontend/api/settings/ai-providers/custom/:id
 *   GET   /frontend/api/settings/ai-providers/resolved
 *   GET   /frontend/api/settings/search-providers
 *   PUT   /frontend/api/settings/search-providers/order
 *   PUT   /frontend/api/settings/search-providers/:provider_id
 *   DELETE /frontend/api/settings/search-providers/:provider_id
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

const BASE = '/frontend/api/settings';

export const settingsLoadOp = createAsyncOp({
    name: 'frontend/settings_load',
    silent: true,
    restMirror: { method: 'GET', path: '/frontend/api/settings/company' },
    request: async () => await httpRequest({
        method: 'GET',
        url: `${BASE}/company`,
    }),
});

export const settingsUpdateOp = createAsyncOp({
    name: 'frontend/settings_update',
    successToastKey: 'frontend:settings_page.toast_saved',
    errorToastKey: 'frontend:settings_page.err_save_failed',
    restMirror: { method: 'PATCH', path: '/frontend/api/settings/company' },
    request: async ({ payload }) => await httpRequest({
        method: 'PATCH',
        url: `${BASE}/company`,
        body: payload && typeof payload === 'object' ? payload : {},
    }),
    onSuccess: (ctx) => {
        ctx.dispatch(settingsLoadOp.events.REQUESTED, null, { source: 'local' });
    },
});

// === AI providers ===

export const aiProvidersLoadOp = createAsyncOp({
    name: 'frontend/ai_providers_load',
    silent: true,
    restMirror: { method: 'GET', path: '/frontend/api/settings/ai-providers' },
    request: async () => await httpRequest({
        method: 'GET',
        url: `${BASE}/ai-providers`,
    }),
});

export const aiProviderCapabilityPutOp = createAsyncOp({
    name: 'frontend/ai_provider_capability_put',
    successToastKey: 'frontend:settings_page.ai_providers.toast_capability_saved',
    errorToastKey: 'frontend:settings_page.ai_providers.toast_capability_failed',
    restMirror: { method: 'PUT', path: '/frontend/api/settings/ai-providers/:capability' },
    request: async ({ payload }) => {
        if (!payload || typeof payload !== 'object') {
            throw new Error('ai_provider_capability_put: payload required');
        }
        const { capability, ...body } = payload;
        if (!capability || typeof capability !== 'string') {
            throw new Error('ai_provider_capability_put: capability required');
        }
        return await httpRequest({
            method: 'PUT',
            url: `${BASE}/ai-providers/${encodeURIComponent(capability)}`,
            body,
        });
    },
    onSuccess: (ctx) => {
        ctx.dispatch(aiProvidersLoadOp.events.REQUESTED, null, { source: 'local' });
    },
});

export const aiProviderCapabilityDeleteOp = createAsyncOp({
    name: 'frontend/ai_provider_capability_delete',
    successToastKey: 'frontend:settings_page.ai_providers.toast_capability_cleared',
    errorToastKey: 'frontend:settings_page.ai_providers.toast_capability_failed',
    restMirror: { method: 'DELETE', path: '/frontend/api/settings/ai-providers/:capability' },
    request: async ({ payload }) => {
        if (!payload || !payload.capability) {
            throw new Error('ai_provider_capability_delete: capability required');
        }
        return await httpRequest({
            method: 'DELETE',
            url: `${BASE}/ai-providers/${encodeURIComponent(payload.capability)}`,
        });
    },
    onSuccess: (ctx) => {
        ctx.dispatch(aiProvidersLoadOp.events.REQUESTED, null, { source: 'local' });
    },
});

export const aiProviderLlmContextPutOp = createAsyncOp({
    name: 'frontend/ai_provider_llm_context_put',
    successToastKey: 'frontend:settings_page.ai_providers.toast_context_saved',
    errorToastKey: 'frontend:settings_page.ai_providers.toast_context_failed',
    restMirror: { method: 'PUT', path: '/frontend/api/settings/ai-providers/llm-context' },
    request: async ({ payload }) => await httpRequest({
        method: 'PUT',
        url: `${BASE}/ai-providers/llm-context`,
        body: payload && typeof payload === 'object' ? payload : {},
    }),
    onSuccess: (ctx) => {
        ctx.dispatch(aiProvidersLoadOp.events.REQUESTED, null, { source: 'local' });
    },
});

export const aiProviderLlmContextDeleteOp = createAsyncOp({
    name: 'frontend/ai_provider_llm_context_delete',
    successToastKey: 'frontend:settings_page.ai_providers.toast_context_cleared',
    errorToastKey: 'frontend:settings_page.ai_providers.toast_context_failed',
    restMirror: { method: 'DELETE', path: '/frontend/api/settings/ai-providers/llm-context' },
    request: async () => await httpRequest({
        method: 'DELETE',
        url: `${BASE}/ai-providers/llm-context`,
    }),
    onSuccess: (ctx) => {
        ctx.dispatch(aiProvidersLoadOp.events.REQUESTED, null, { source: 'local' });
    },
});

export const aiCustomProviderCreateOp = createAsyncOp({
    name: 'frontend/ai_custom_provider_create',
    successToastKey: 'frontend:settings_page.ai_providers.toast_custom_created',
    errorToastKey: 'frontend:settings_page.ai_providers.toast_custom_failed',
    restMirror: { method: 'POST', path: '/frontend/api/settings/ai-providers/custom' },
    request: async ({ payload }) => await httpRequest({
        method: 'POST',
        url: `${BASE}/ai-providers/custom`,
        body: payload && typeof payload === 'object' ? payload : {},
    }),
    onSuccess: (ctx) => {
        ctx.dispatch(aiProvidersLoadOp.events.REQUESTED, null, { source: 'local' });
    },
});

export const aiCustomProviderUpdateOp = createAsyncOp({
    name: 'frontend/ai_custom_provider_update',
    successToastKey: 'frontend:settings_page.ai_providers.toast_custom_updated',
    errorToastKey: 'frontend:settings_page.ai_providers.toast_custom_failed',
    restMirror: { method: 'PATCH', path: '/frontend/api/settings/ai-providers/custom/:provider_id' },
    request: async ({ payload }) => {
        if (!payload || !payload.id) {
            throw new Error('ai_custom_provider_update: id required');
        }
        const { id, ...body } = payload;
        return await httpRequest({
            method: 'PATCH',
            url: `${BASE}/ai-providers/custom/${encodeURIComponent(id)}`,
            body,
        });
    },
    onSuccess: (ctx) => {
        ctx.dispatch(aiProvidersLoadOp.events.REQUESTED, null, { source: 'local' });
    },
});

export const aiCustomProviderDeleteOp = createAsyncOp({
    name: 'frontend/ai_custom_provider_delete',
    successToastKey: 'frontend:settings_page.ai_providers.toast_custom_deleted',
    errorToastKey: 'frontend:settings_page.ai_providers.toast_custom_failed',
    restMirror: { method: 'DELETE', path: '/frontend/api/settings/ai-providers/custom/:provider_id' },
    request: async ({ payload }) => {
        if (!payload || !payload.id) {
            throw new Error('ai_custom_provider_delete: id required');
        }
        return await httpRequest({
            method: 'DELETE',
            url: `${BASE}/ai-providers/custom/${encodeURIComponent(payload.id)}`,
        });
    },
    onSuccess: (ctx) => {
        ctx.dispatch(aiProvidersLoadOp.events.REQUESTED, null, { source: 'local' });
    },
});

// === Search providers ===

export const searchProvidersLoadOp = createAsyncOp({
    name: 'frontend/search_providers_load',
    silent: true,
    restMirror: { method: 'GET', path: '/frontend/api/settings/search-providers' },
    request: async () => await httpRequest({
        method: 'GET',
        url: `${BASE}/search-providers`,
    }),
});

export const searchProviderPutOp = createAsyncOp({
    name: 'frontend/search_provider_put',
    successToastKey: 'frontend:settings_page.search_providers.toast_saved',
    errorToastKey: 'frontend:settings_page.search_providers.toast_failed',
    restMirror: { method: 'PUT', path: '/frontend/api/settings/search-providers/:provider_id' },
    request: async ({ payload }) => {
        if (!payload || typeof payload !== 'object') {
            throw new Error('search_provider_put: payload required');
        }
        const { provider_id, ...body } = payload;
        if (!provider_id || typeof provider_id !== 'string') {
            throw new Error('search_provider_put: provider_id required');
        }
        return await httpRequest({
            method: 'PUT',
            url: `${BASE}/search-providers/${encodeURIComponent(provider_id)}`,
            body,
        });
    },
    onSuccess: (ctx) => {
        ctx.dispatch(searchProvidersLoadOp.events.REQUESTED, null, { source: 'local' });
    },
});

export const searchProviderOrderPutOp = createAsyncOp({
    name: 'frontend/search_provider_order_put',
    successToastKey: 'frontend:settings_page.search_providers.toast_order_saved',
    errorToastKey: 'frontend:settings_page.search_providers.toast_failed',
    restMirror: { method: 'PUT', path: '/frontend/api/settings/search-providers/order' },
    request: async ({ payload }) => await httpRequest({
        method: 'PUT',
        url: `${BASE}/search-providers/order`,
        body: payload && typeof payload === 'object' ? payload : {},
    }),
    onSuccess: (ctx) => {
        ctx.dispatch(searchProvidersLoadOp.events.REQUESTED, null, { source: 'local' });
    },
});

export const searchProviderDeleteOp = createAsyncOp({
    name: 'frontend/search_provider_delete',
    successToastKey: 'frontend:settings_page.search_providers.toast_reset',
    errorToastKey: 'frontend:settings_page.search_providers.toast_failed',
    restMirror: { method: 'DELETE', path: '/frontend/api/settings/search-providers/:provider_id' },
    request: async ({ payload }) => {
        if (!payload || !payload.provider_id) {
            throw new Error('search_provider_delete: provider_id required');
        }
        return await httpRequest({
            method: 'DELETE',
            url: `${BASE}/search-providers/${encodeURIComponent(payload.provider_id)}`,
        });
    },
    onSuccess: (ctx) => {
        ctx.dispatch(searchProvidersLoadOp.events.REQUESTED, null, { source: 'local' });
    },
});
