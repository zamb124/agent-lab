/**
 * Настройки Search-провайдеров компании (`Company.metadata.search_providers`).
 *
 * Владелец — сервис search (`search/providers/*`, каталог SEARCH_OPERATIONS);
 * REST-зеркало: /search/api/v1/providers/company. Payload команд уходит as-is.
 */

import { createAsyncOp } from '../index.js';
import type { CompanySearchProvidersResponse, SearchOkResult } from '../wire/search.gen.js';


export const searchProvidersLoadOp = createAsyncOp<CompanySearchProvidersResponse>({
    name: 'search/providers_load',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'search/providers/list_requested',
    restMirror: { method: 'GET', path: '/search/api/v1/providers/company' },
});

export const searchProviderPutOp = createAsyncOp<SearchOkResult>({
    name: 'search/provider_update',
    successToastKey: 'frontend:settings_page.search_providers.toast_saved',
    errorToastKey: 'frontend:settings_page.search_providers.toast_failed',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'search/providers/update_requested',
    restMirror: { method: 'PUT', path: '/search/api/v1/providers/company/:provider_id' },
    onSuccess: (ctx) => {
        ctx.dispatch(searchProvidersLoadOp.events.REQUESTED, null, { source: 'local' });
    },
});

export const searchProviderOrderPutOp = createAsyncOp<SearchOkResult>({
    name: 'search/provider_order_update',
    successToastKey: 'frontend:settings_page.search_providers.toast_order_saved',
    errorToastKey: 'frontend:settings_page.search_providers.toast_failed',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'search/providers/order_update_requested',
    restMirror: { method: 'PUT', path: '/search/api/v1/providers/company/order' },
    onSuccess: (ctx) => {
        ctx.dispatch(searchProvidersLoadOp.events.REQUESTED, null, { source: 'local' });
    },
});

export const searchProviderDeleteOp = createAsyncOp<SearchOkResult>({
    name: 'search/provider_reset',
    successToastKey: 'frontend:settings_page.search_providers.toast_reset',
    errorToastKey: 'frontend:settings_page.search_providers.toast_failed',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'search/providers/reset_requested',
    restMirror: { method: 'DELETE', path: '/search/api/v1/providers/company/:provider_id' },
    onSuccess: (ctx) => {
        ctx.dispatch(searchProvidersLoadOp.events.REQUESTED, null, { source: 'local' });
    },
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'search/providers_load': typeof searchProvidersLoadOp;
        'search/provider_update': typeof searchProviderPutOp;
        'search/provider_order_update': typeof searchProviderOrderPutOp;
        'search/provider_reset': typeof searchProviderDeleteOp;
    }
}
