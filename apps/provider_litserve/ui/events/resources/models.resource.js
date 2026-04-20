/**
 * Ресурс провайдера LitServe: реестр моделей.
 *
 * CRUD по `/litserve/api/models` + отдельная операция retry для повторного
 * скачивания весов. Модель содержит поля model_id, kind, hf_model_id,
 * api_model_id, status, error, created_at, updated_at — всё нормализуется
 * через mapItem.
 */

import { createResourceCollection, createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

function _normalizeModel(raw) {
    if (!raw || typeof raw !== 'object') {
        throw new Error('provider_litserve/models: model item must be object');
    }
    if (typeof raw.model_id !== 'string' || raw.model_id.length === 0) {
        throw new Error('provider_litserve/models: model_id required');
    }
    return {
        model_id: raw.model_id,
        kind: typeof raw.kind === 'string' ? raw.kind : '',
        hf_model_id: typeof raw.hf_model_id === 'string' ? raw.hf_model_id : '',
        api_model_id: typeof raw.api_model_id === 'string' ? raw.api_model_id : '',
        status: typeof raw.status === 'string' ? raw.status : 'pending',
        error: typeof raw.error === 'string' ? raw.error : null,
        created_at: typeof raw.created_at === 'string' ? raw.created_at : '',
        updated_at: typeof raw.updated_at === 'string' ? raw.updated_at : '',
    };
}

export const litserveModelsResource = createResourceCollection({
    name: 'provider_litserve/models',
    baseUrl: '/litserve/api/models',
    idField: 'model_id',
    operations: ['list', 'create', 'remove'],
    toastKeys: {
        create: 'litserve:toast.model_created',
        create_error: 'litserve:toast.model_create_error',
        remove: 'litserve:toast.model_removed',
        remove_error: 'litserve:toast.model_remove_error',
    },
    mapItem: _normalizeModel,
});

export const litserveModelRetryOp = createAsyncOp({
    name: 'provider_litserve/model_retry',
    successToastKey: 'litserve:toast.model_retry_started',
    errorToastKey: 'litserve:toast.model_retry_error',
    restMirror: { method: 'POST', path: '/litserve/api/models/:model_id/retry' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.model_id !== 'string' || payload.model_id.length === 0) {
            throw new Error('provider_litserve/model_retry: payload.model_id required');
        }
        return httpRequest({
            method: 'POST',
            url: `/litserve/api/models/${encodeURIComponent(payload.model_id)}/retry`,
        });
    },
    onSuccess: (ctx, _result, event) => {
        ctx.dispatch(litserveModelsResource.events.LIST_REQUESTED, null, { causation_id: event.id });
    },
});
