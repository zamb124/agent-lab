/**
 * Embed resources — встраиваемые виджеты и загрузка их HTML/JS-кода.
 *
 * Coverage:
 *   - embedConfigsResource (createResourceCollection): CRUD списка виджетов.
 *   - embedCodeLoadOp (createAsyncOp): загрузка html_code/script_url/token_endpoint
 *     для конкретного embed_id. Результат хранится в slice как lastResult и
 *     дополнительно проецируется в `codeByEmbedId[embed_id]`, чтобы модалка
 *     embed-code умела показывать код любому открытому embed_id, а не только
 *     последнему.
 *
 * Backend (apps/frontend/api/embed_configs.py):
 *   GET    /frontend/api/embed/configs                  → { items: EmbedConfig[] }
 *   POST   /frontend/api/embed/configs                  → EmbedConfig
 *   PATCH  /frontend/api/embed/configs/{embed_id}       → EmbedConfig
 *   DELETE /frontend/api/embed/configs/{embed_id}       → 204
 *   GET    /frontend/api/embed/configs/{embed_id}/code  → { html_code, script_url, token_endpoint }
 */

import {
    createResourceCollection,
    createAsyncOp,
} from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

export const embedConfigsResource = createResourceCollection({
    name: 'frontend/embed_configs',
    baseUrl: '/frontend/api/embed/configs',
    idField: 'embed_id',
    operations: ['list', 'create', 'update', 'remove'],
    toastKeys: {
        create: 'frontend:embed_create_modal.toast_created',
        update: 'frontend:embed_create_modal.toast_updated',
        remove: 'frontend:embed_page.toast_deleted',
    },
});

export const embedCodeLoadOp = createAsyncOp({
    name: 'frontend/embed_code',
    silent: true,
    request: async ({ payload }) => {
        const id = payload && payload.embed_id;
        if (!id) throw new Error('embedCodeLoadOp: embed_id required');
        const r = await httpRequest({
            method: 'GET',
            url: `/frontend/api/embed/configs/${encodeURIComponent(id)}/code`,
        });
        return {
            embed_id: id,
            html_code: r.html_code || '',
            script_url: r.script_url || '',
            token_endpoint: r.token_endpoint || '',
        };
    },
    extraInitial: { codeByEmbedId: {}, codeLoadingById: {} },
    extraReducer: (state, event, events) => {
        if (event.type === events.REQUESTED) {
            const id = event.payload && event.payload.embed_id;
            if (!id) return state;
            return { ...state, codeLoadingById: { ...state.codeLoadingById, [id]: true } };
        }
        if (event.type === events.SUCCEEDED) {
            const r = event.payload && event.payload.result;
            if (!r || !r.embed_id) return state;
            const nextLoading = { ...state.codeLoadingById };
            delete nextLoading[r.embed_id];
            return {
                ...state,
                codeByEmbedId: { ...state.codeByEmbedId, [r.embed_id]: {
                    html_code: r.html_code,
                    script_url: r.script_url,
                    token_endpoint: r.token_endpoint,
                } },
                codeLoadingById: nextLoading,
            };
        }
        if (event.type === events.FAILED) {
            return { ...state, codeLoadingById: {} };
        }
        return state;
    },
});
