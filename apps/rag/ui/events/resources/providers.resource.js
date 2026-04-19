/**
 * Providers — RAG-провайдеры (pgvector, agentset).
 *
 * Backend (`/rag/api/v1/providers`):
 *   GET  /                → ProviderListResponse { items: ProviderInfo[], current_provider: string }
 *   POST /switch          → { success, provider, message }   (sessionный switch)
 *
 * `providersResource` — createAsyncOp, потому что бэк отдаёт список + текущий
 * провайдер одним пейлоадом, а createResourceCollection.LIST_LOADED не
 * передаёт ничего кроме `items`. Через extraReducer выкладываем оба поля
 * (`items`, `current`) в slice. Компоненты читают `state.items`/`state.current`.
 *
 * `providerSwitchOp` после успеха перезагружает оба ресурса (providers и
 * namespaces) — список namespaces зависит от текущего провайдера.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';
import { namespacesResource } from './namespaces.resource.js';

export const providersResource = createAsyncOp({
    name: 'rag/providers',
    silent: true,
    restMirror: { method: 'GET', path: '/rag/api/v1/providers' },
    request: () => httpRequest({ method: 'GET', url: '/rag/api/v1/providers' }),
    extraInitial: { items: [], current: null },
    extraReducer: (state, event, events) => {
        if (event.type !== events.SUCCEEDED) return state;
        const result = event.payload.result;
        if (!result || !Array.isArray(result.items)) {
            throw new Error('rag/providers: result.items must be array');
        }
        if (typeof result.current_provider !== 'string') {
            throw new Error('rag/providers: result.current_provider must be string');
        }
        return { ...state, items: result.items, current: result.current_provider };
    },
});

export const providerSwitchOp = createAsyncOp({
    name: 'rag/provider_switch',
    successToastKey: 'rag:toast.provider_switched',
    errorToastKey: 'rag:toast.provider_switch_failed',
    restMirror: { method: 'POST', path: '/rag/api/v1/providers/switch' },
    request: ({ payload }) => {
        if (!payload || typeof payload.providerName !== 'string' || payload.providerName.length === 0) {
            throw new Error('rag/provider_switch: payload.providerName required');
        }
        return httpRequest({
            method: 'POST',
            url: '/rag/api/v1/providers/switch',
            body: { provider_name: payload.providerName },
        });
    },
    onSuccess: (ctx) => {
        ctx.dispatch(providersResource.events.REQUESTED, null, { source: 'local' });
        ctx.dispatch(namespacesResource.events.LIST_REQUESTED, null, { source: 'local' });
    },
});
