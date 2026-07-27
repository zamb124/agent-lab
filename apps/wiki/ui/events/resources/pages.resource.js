/**
 * Страницы wiki: дерево пространства, содержимое, перемещение, корзина.
 *
 * Дерево приходит без содержимого страниц — контент грузится отдельной
 * операцией по мере открытия, иначе переключение пространства тянуло бы
 * весь текст базы знаний.
 *
 * Все запросы адресованы рабочему пространству: заголовок
 * `X-Platform-Namespace` обязателен, без него backend отвечает ошибкой.
 */

import { createAsyncOp, createResourceCollection } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';
import { platformNamespaceHeader } from '@platform/lib/utils/platform-namespace-header.js';

const BASE_URL = '/wiki/api/v1/pages';

export const WIKI_PAGE_EVENTS = [
    'wiki/page/created',
    'wiki/page/updated',
    'wiki/page/published',
    'wiki/page/moved',
    'wiki/page/deleted',
    'wiki/page/restored',
    'wiki/page/access_changed',
];

function mergeSummary(state, summary) {
    const id = summary.wiki_page_id;
    const index = state.items.findIndex((item) => item && item.wiki_page_id === id);
    const items = index === -1
        ? [...state.items, summary]
        : state.items.map((item, position) => (position === index ? summary : item));
    return { ...state, items, byId: { ...state.byId, [id]: summary } };
}

export const wikiPagesResource = createResourceCollection({
    name: 'wiki/pages',
    baseUrl: '/wiki/api/v1/pages',
    idField: 'wiki_page_id',
    operations: ['list'],
    transport: 'http',
    itemsPath: 'items',
    requestHeaders: ({ ctx }) => platformNamespaceHeader(ctx),
    extraReducers: {
        'wiki/page/created': (state, payload) => mergeSummary(state, payload.page),
        'wiki/page/updated': (state, payload) => mergeSummary(state, payload.page),
        'wiki/page/published': (state, payload) => mergeSummary(state, payload.page),
        'wiki/page/restored': (state, payload) => mergeSummary(state, payload.page),
        'wiki/page/moved': (state, payload) => mergeSummary(state, payload.page),
        'wiki/page/deleted': (state, payload) => {
            const removed = new Set(payload.affected_page_ids);
            const items = state.items.filter((item) => item && !removed.has(item.wiki_page_id));
            const byId = { ...state.byId };
            for (const id of removed) delete byId[id];
            return { ...state, items, byId };
        },
    },
});

export const wikiPageReadOp = createAsyncOp({
    name: 'wiki/page_read',
    silent: true,
    restMirror: { method: 'GET', path: '/wiki/api/v1/pages/:wiki_page_id' },
    request: ({ payload, ctx }) => httpRequest({
        method: 'GET',
        url: `${BASE_URL}/${payload.wiki_page_id}`,
        headers: platformNamespaceHeader(ctx),
    }),
});

export const wikiPageCreateOp = createAsyncOp({
    name: 'wiki/page_create',
    successToastKey: 'wiki:toast.page.created',
    errorToastKey: 'wiki:toast.page.create_failed',
    restMirror: { method: 'POST', path: '/wiki/api/v1/pages' },
    request: ({ payload, ctx }) => httpRequest({
        method: 'POST',
        url: BASE_URL,
        headers: platformNamespaceHeader(ctx),
        body: payload,
    }),
});

export const wikiPageSaveOp = createAsyncOp({
    name: 'wiki/page_save',
    silent: true,
    restMirror: { method: 'PUT', path: '/wiki/api/v1/pages/:wiki_page_id/content' },
    request: ({ payload, ctx }) => httpRequest({
        method: 'PUT',
        url: `${BASE_URL}/${payload.wiki_page_id}/content`,
        headers: platformNamespaceHeader(ctx),
        body: {
            content: payload.content,
            title: payload.title,
            create_revision: payload.create_revision,
        },
    }),
});

export const wikiPagePropertiesOp = createAsyncOp({
    name: 'wiki/page_properties',
    silent: true,
    restMirror: { method: 'PATCH', path: '/wiki/api/v1/pages/:wiki_page_id' },
    request: ({ payload, ctx }) => {
        const { wiki_page_id: pageId, ...body } = payload;
        return httpRequest({
            method: 'PATCH',
            url: `${BASE_URL}/${pageId}`,
            headers: platformNamespaceHeader(ctx),
            body,
        });
    },
});

export const wikiPageMoveOp = createAsyncOp({
    name: 'wiki/page_move',
    silent: true,
    restMirror: { method: 'POST', path: '/wiki/api/v1/pages/:wiki_page_id/move' },
    request: ({ payload, ctx }) => httpRequest({
        method: 'POST',
        url: `${BASE_URL}/${payload.wiki_page_id}/move`,
        headers: platformNamespaceHeader(ctx),
        body: { parent_page_id: payload.parent_page_id, position: payload.position },
    }),
});

export const wikiPageMoveNamespaceOp = createAsyncOp({
    name: 'wiki/page_move_namespace',
    successToastKey: 'wiki:toast.page.namespace_changed',
    errorToastKey: 'wiki:toast.page.namespace_change_failed',
    restMirror: { method: 'POST', path: '/wiki/api/v1/pages/:wiki_page_id/move-namespace' },
    request: ({ payload, ctx }) => httpRequest({
        method: 'POST',
        url: `${BASE_URL}/${payload.wiki_page_id}/move-namespace`,
        headers: platformNamespaceHeader(ctx),
        body: {
            target_namespace: payload.target_namespace,
            parent_page_id: payload.parent_page_id,
        },
    }),
});

export const wikiPageDeleteOp = createAsyncOp({
    name: 'wiki/page_delete',
    successToastKey: 'wiki:toast.page.deleted',
    errorToastKey: 'wiki:toast.page.delete_failed',
    restMirror: { method: 'DELETE', path: '/wiki/api/v1/pages/:wiki_page_id' },
    request: ({ payload, ctx }) => httpRequest({
        method: 'DELETE',
        url: `${BASE_URL}/${payload.wiki_page_id}`,
        headers: platformNamespaceHeader(ctx),
    }),
});

export const wikiPageRestoreOp = createAsyncOp({
    name: 'wiki/page_restore',
    successToastKey: 'wiki:toast.page.restored',
    errorToastKey: 'wiki:toast.page.restore_failed',
    restMirror: { method: 'POST', path: '/wiki/api/v1/pages/:wiki_page_id/restore' },
    request: ({ payload, ctx }) => httpRequest({
        method: 'POST',
        url: `${BASE_URL}/${payload.wiki_page_id}/restore`,
        headers: platformNamespaceHeader(ctx),
    }),
});

export const wikiDeletedPagesOp = createAsyncOp({
    name: 'wiki/pages_deleted',
    silent: true,
    restMirror: { method: 'GET', path: '/wiki/api/v1/pages/deleted' },
    request: ({ ctx }) => httpRequest({
        method: 'GET',
        url: `${BASE_URL}/deleted`,
        headers: platformNamespaceHeader(ctx),
    }),
});

export const wikiPageMarkdownOp = createAsyncOp({
    name: 'wiki/page_markdown',
    silent: true,
    restMirror: { method: 'GET', path: '/wiki/api/v1/pages/:wiki_page_id/markdown' },
    request: ({ payload, ctx }) => httpRequest({
        method: 'GET',
        url: `${BASE_URL}/${payload.wiki_page_id}/markdown`,
        headers: platformNamespaceHeader(ctx),
    }),
});
