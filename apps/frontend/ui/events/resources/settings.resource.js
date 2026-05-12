/**
 * Settings resources — настройки компании.
 *
 * API:
 *   GET   /frontend/api/settings/company         → profile (name/subdomain/budget/metadata)
 *   PATCH /frontend/api/settings/company         ← CompanySettingsUpdate (без AI providers)
 *   GET   /frontend/api/settings/ai-providers    → capabilities + custom + catalog
 *   PUT   /frontend/api/settings/ai-providers/:capability  ← AIProvidersCapabilityUpdate
 *   DELETE /frontend/api/settings/ai-providers/:capability
 *   POST  /frontend/api/settings/ai-providers/custom              ← CustomProviderCreate
 *   PATCH /frontend/api/settings/ai-providers/custom/:id          ← CustomProviderUpdate
 *   DELETE /frontend/api/settings/ai-providers/custom/:id
 *   GET   /frontend/api/settings/ai-providers/resolved
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
