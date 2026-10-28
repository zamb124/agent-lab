/**
 * Ресурсы настроек — профиль компании и AI-провайдеры (команды `frontend/company_settings/*`,
 * `frontend/ai_providers/*`; REST-зеркало `apps/frontend/api/settings.py`, `ai_providers.py`).
 *
 * Снимок AI-провайдеров несёт `public_host` — бренд подписей каталога резолвится по host браузера.
 * Мутации перезапрашивают снимок: overlay хранится в `Company.metadata`, push-события у него нет.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';

const WS_TIMEOUT_MS = 8_000;

export const settingsLoadOp = createAsyncOp({
    name: 'frontend/settings_load',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'frontend/company_settings/get_requested',
    restMirror: { method: 'GET', path: '/frontend/api/settings/company' },
});

export const settingsUpdateOp = createAsyncOp({
    name: 'frontend/settings_update',
    successToastKey: 'frontend:settings_page.toast_saved',
    errorToastKey: 'frontend:settings_page.err_save_failed',
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'frontend/company_settings/update_requested',
    restMirror: { method: 'PATCH', path: '/frontend/api/settings/company' },
    onSuccess: (ctx) => {
        ctx.dispatch(settingsLoadOp.events.REQUESTED, null, { source: 'local' });
    },
});

// === AI providers ===

function _reloadAiProviders(ctx: Record<string, any>) {
    ctx.dispatch(
        aiProvidersLoadOp.events.REQUESTED,
        { public_host: window.location.host },
        { source: 'local' },
    );
}

export const aiProvidersLoadOp = createAsyncOp({
    name: 'frontend/ai_providers_load',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'frontend/ai_providers/snapshot_requested',
    restMirror: { method: 'GET', path: '/frontend/api/settings/ai-providers' },
});

export const aiProviderCapabilityPutOp = createAsyncOp({
    name: 'frontend/ai_provider_capability_put',
    successToastKey: 'frontend:settings_page.ai_providers.toast_capability_saved',
    errorToastKey: 'frontend:settings_page.ai_providers.toast_capability_failed',
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'frontend/ai_providers/capability_update_requested',
    restMirror: { method: 'PUT', path: '/frontend/api/settings/ai-providers/:capability' },
    onSuccess: _reloadAiProviders,
});

export const aiProviderCapabilityDeleteOp = createAsyncOp({
    name: 'frontend/ai_provider_capability_delete',
    successToastKey: 'frontend:settings_page.ai_providers.toast_capability_cleared',
    errorToastKey: 'frontend:settings_page.ai_providers.toast_capability_failed',
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'frontend/ai_providers/capability_remove_requested',
    restMirror: { method: 'DELETE', path: '/frontend/api/settings/ai-providers/:capability' },
    onSuccess: _reloadAiProviders,
});

export const aiProviderLlmContextPutOp = createAsyncOp({
    name: 'frontend/ai_provider_llm_context_put',
    successToastKey: 'frontend:settings_page.ai_providers.toast_context_saved',
    errorToastKey: 'frontend:settings_page.ai_providers.toast_context_failed',
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'frontend/ai_providers/llm_context_update_requested',
    restMirror: { method: 'PUT', path: '/frontend/api/settings/ai-providers/llm-context' },
    onSuccess: _reloadAiProviders,
});

export const aiProviderLlmContextDeleteOp = createAsyncOp({
    name: 'frontend/ai_provider_llm_context_delete',
    successToastKey: 'frontend:settings_page.ai_providers.toast_context_cleared',
    errorToastKey: 'frontend:settings_page.ai_providers.toast_context_failed',
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'frontend/ai_providers/llm_context_remove_requested',
    restMirror: { method: 'DELETE', path: '/frontend/api/settings/ai-providers/llm-context' },
    onSuccess: _reloadAiProviders,
});

export const aiCustomProviderCreateOp = createAsyncOp({
    name: 'frontend/ai_custom_provider_create',
    successToastKey: 'frontend:settings_page.ai_providers.toast_custom_created',
    errorToastKey: 'frontend:settings_page.ai_providers.toast_custom_failed',
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'frontend/ai_providers/custom_create_requested',
    restMirror: { method: 'POST', path: '/frontend/api/settings/ai-providers/custom' },
    onSuccess: _reloadAiProviders,
});

export const aiCustomProviderUpdateOp = createAsyncOp({
    name: 'frontend/ai_custom_provider_update',
    successToastKey: 'frontend:settings_page.ai_providers.toast_custom_updated',
    errorToastKey: 'frontend:settings_page.ai_providers.toast_custom_failed',
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'frontend/ai_providers/custom_update_requested',
    restMirror: { method: 'PATCH', path: '/frontend/api/settings/ai-providers/custom/:provider_id' },
    onSuccess: _reloadAiProviders,
});

export const aiCustomProviderDeleteOp = createAsyncOp({
    name: 'frontend/ai_custom_provider_delete',
    successToastKey: 'frontend:settings_page.ai_providers.toast_custom_deleted',
    errorToastKey: 'frontend:settings_page.ai_providers.toast_custom_failed',
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'frontend/ai_providers/custom_remove_requested',
    restMirror: { method: 'DELETE', path: '/frontend/api/settings/ai-providers/custom/:provider_id' },
    onSuccess: _reloadAiProviders,
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'frontend/settings_load': typeof settingsLoadOp;
        'frontend/settings_update': typeof settingsUpdateOp;
        'frontend/ai_providers_load': typeof aiProvidersLoadOp;
        'frontend/ai_provider_capability_put': typeof aiProviderCapabilityPutOp;
        'frontend/ai_provider_capability_delete': typeof aiProviderCapabilityDeleteOp;
        'frontend/ai_provider_llm_context_put': typeof aiProviderLlmContextPutOp;
        'frontend/ai_provider_llm_context_delete': typeof aiProviderLlmContextDeleteOp;
        'frontend/ai_custom_provider_create': typeof aiCustomProviderCreateOp;
        'frontend/ai_custom_provider_update': typeof aiCustomProviderUpdateOp;
        'frontend/ai_custom_provider_delete': typeof aiCustomProviderDeleteOp;
    }
}
