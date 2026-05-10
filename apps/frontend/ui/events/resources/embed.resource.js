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
 *   GET    /frontend/api/embed/configs/{embed_id}/code  → { html_code, script_url, token_endpoint,
 *     backend_proxy_code, browser_to_host_backend_code, allowed_origins }
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
    mapItem: (raw) => {
        if (!raw || typeof raw !== 'object') {
            throw new Error('frontend/embed_configs: invalid item');
        }
        if (typeof raw.embed_id !== 'string' || raw.embed_id === '') {
            throw new Error('frontend/embed_configs: embed_id required');
        }
        if (typeof raw.landing_visible !== 'boolean') {
            throw new Error('frontend/embed_configs: landing_visible required');
        }
        if (raw.landing_card_image_url != null && typeof raw.landing_card_image_url !== 'string') {
            throw new Error('frontend/embed_configs: landing_card_image_url invalid');
        }
        if (typeof raw.landing_sort_order !== 'number') {
            throw new Error('frontend/embed_configs: landing_sort_order required');
        }
        if (raw.guest_max_user_messages != null) {
            if (typeof raw.guest_max_user_messages !== 'number' || !Number.isFinite(raw.guest_max_user_messages)) {
                throw new Error('frontend/embed_configs: guest_max_user_messages invalid');
            }
        }
        return {
            ...raw,
            landing_card_image_url:
                typeof raw.landing_card_image_url === 'string' ? raw.landing_card_image_url : null,
        };
    },
});

export const embedCodeLoadOp = createAsyncOp({
    name: 'frontend/embed_code',
    silent: true,
    restMirror: { method: 'GET', path: '/frontend/api/embed/configs/:embed_id/code' },
    request: async ({ payload }) => {
        const id = payload && payload.embed_id;
        if (!id) throw new Error('embedCodeLoadOp: embed_id required');
        const r = await httpRequest({
            method: 'GET',
            url: `/frontend/api/embed/configs/${encodeURIComponent(id)}/code`,
        });
        if (!Array.isArray(r.allowed_origins)) {
            throw new Error('embedCodeLoadOp: allowed_origins must be array');
        }
        for (let i = 0; i < r.allowed_origins.length; i += 1) {
            if (typeof r.allowed_origins[i] !== 'string') {
                throw new Error('embedCodeLoadOp: allowed_origins entries must be strings');
            }
        }
        const backend_proxy_code =
            typeof r.backend_proxy_code === 'string' ? r.backend_proxy_code : '';
        const browser_to_host_backend_code =
            typeof r.browser_to_host_backend_code === 'string'
                ? r.browser_to_host_backend_code
                : '';
        return {
            embed_id: id,
            html_code: typeof r.html_code === 'string' ? r.html_code : '',
            script_url: typeof r.script_url === 'string' ? r.script_url : '',
            token_endpoint: typeof r.token_endpoint === 'string' ? r.token_endpoint : '',
            backend_proxy_code,
            browser_to_host_backend_code,
            allowed_origins: r.allowed_origins,
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
                codeByEmbedId: {
                    ...state.codeByEmbedId,
                    [r.embed_id]: {
                        html_code: r.html_code,
                        script_url: r.script_url,
                        token_endpoint: r.token_endpoint,
                        backend_proxy_code: r.backend_proxy_code,
                        browser_to_host_backend_code: r.browser_to_host_backend_code,
                        allowed_origins: r.allowed_origins,
                    },
                },
                codeLoadingById: nextLoading,
            };
        }
        if (event.type === events.FAILED) {
            return { ...state, codeLoadingById: {} };
        }
        return state;
    },
});
