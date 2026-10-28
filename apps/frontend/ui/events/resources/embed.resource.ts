/**
 * Ресурсы embed — встраиваемые виджеты и код для встраивания
 * (команды `frontend/embed_configs/*`, REST-зеркало `apps/frontend/api/embed_configs.py`).
 *
 * Coverage:
 *   - embedConfigsResource (createResourceCollection): CRUD списка виджетов.
 *   - embedCodeLoadOp (createAsyncOp): `{ embed_id, public_origin }` → html_code/script_url/token_endpoint.
 *     Результат проецируется в `codeByEmbedId[embed_id]`, чтобы модалка embed-code показывала код
 *     любого открытого embed_id, а не только последнего.
 */

import {
    createResourceCollection,
    createAsyncOp,
} from '@platform/lib/events/index.js';

export const embedConfigsResource = createResourceCollection({
    name: 'frontend/embed_configs',
    baseUrl: '/frontend/api/embed/configs',
    idField: 'embed_id',
    operations: ['list', 'create', 'update', 'remove'],
    transport: 'ws',
    wsTimeoutMs: 8_000,
    listQuery: () => ({ limit: 200, offset: 0 }),
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
        if (raw.presentation != null && raw.presentation !== 'drawer' && raw.presentation !== 'page') {
            throw new Error('frontend/embed_configs: presentation must be drawer or page');
        }
        if (raw.guest_max_user_messages != null) {
            if (typeof raw.guest_max_user_messages !== 'number' || !Number.isFinite(raw.guest_max_user_messages)) {
                throw new Error('frontend/embed_configs: guest_max_user_messages invalid');
            }
        }
        if (typeof raw.voice_enabled !== 'boolean') {
            throw new Error('frontend/embed_configs: voice_enabled required');
        }
        if (typeof raw.voice_default_on !== 'boolean') {
            throw new Error('frontend/embed_configs: voice_default_on required');
        }
        if (typeof raw.session_share_enabled !== 'boolean') {
            throw new Error('frontend/embed_configs: session_share_enabled required');
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
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'frontend/embed_configs/code_requested',
    restMirror: { method: 'GET', path: '/frontend/api/embed/configs/:embed_id/code' },
    extraInitial: { codeByEmbedId: {}, codeLoadingById: {} },
    extraReducer: (state, event, events) => {
        if (event.type === events.REQUESTED) {
            const id = (event.payload as Record<string, any>) && (event.payload as Record<string, any>).embed_id;
            if (typeof id !== 'string' || id === '') {
                throw new Error('embedCodeLoadOp: payload.embed_id required');
            }
            return { ...state, codeLoadingById: { ...(state.codeLoadingById as Record<string, unknown>), [id]: true } };
        }
        if (event.type === events.SUCCEEDED) {
            const r = (event.payload as Record<string, any>) && (event.payload as Record<string, any>).result;
            if (!r || typeof r.embed_id !== 'string' || !Array.isArray(r.allowed_origins)) {
                throw new Error('embedCodeLoadOp: result.embed_id and allowed_origins required');
            }
            const nextLoading = { ...(state.codeLoadingById as Record<string, unknown>) };
            delete nextLoading[r.embed_id];
            return {
                ...state,
                codeByEmbedId: {
                    ...(state.codeByEmbedId as Record<string, unknown>),
                    [r.embed_id]: {
                        html_code: r.html_code,
                        script_url: r.script_url,
                        presentation: r.presentation,
                        page_url: r.page_url,
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

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'frontend/embed_configs': typeof embedConfigsResource;
        'frontend/embed_code': typeof embedCodeLoadOp;
    }
}
