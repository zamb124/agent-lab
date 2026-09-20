/**
 * Страницы wiki: дерево пространства, содержимое, перемещение, корзина.
 *
 * Mutating/read команды идут одним `op_*` через WS RPC и REST-зеркало.
 * Namespace едет в `PlatformEvent.meta.namespace`.
 *
 * Ответ страницы — `WikiPageResponse { page, can_edit, can_admin }`.
 * extraReducer оставляет в lastResult каноническую `WikiPage`.
 */

import { createAsyncOp, createResourceCollection } from '@platform/lib/events/index.js';

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

function unwrapWikiPageResult(state, event, events) {
    if (event.type !== events.SUCCEEDED) {
        return state;
    }
    if (!event.payload || !('result' in event.payload)) {
        throw new Error('wiki pages: SUCCEEDED payload.result required');
    }
    const result = event.payload.result;
    if (
        !result
        || typeof result !== 'object'
        || result.page === null
        || typeof result.page !== 'object'
    ) {
        throw new Error('wiki pages: ожидался WikiPageResponse с полем page');
    }
    return { ...state, lastResult: result.page };
}

export const wikiPagesResource = createResourceCollection({
    name: 'wiki/pages',
    baseUrl: '/wiki/api/v1/pages',
    idField: 'wiki_page_id',
    operations: ['list'],
    transport: 'ws',
    wsTimeoutMs: 8_000,
    itemsPath: 'items',
    listQuery: () => ({}),
    extraReducer: (state, event) => {
        if (
            WIKI_PAGE_EVENTS.includes(event.type)
            && event.type !== 'wiki/page/deleted'
            && event.type !== 'wiki/page/access_changed'
        ) {
            if (!event.payload || typeof event.payload.page !== 'object' || event.payload.page === null) {
                throw new Error(`${event.type}: payload.page required`);
            }
            return mergeSummary(state, event.payload.page);
        }
        if (event.type === 'wiki/page/deleted') {
            if (!event.payload || !Array.isArray(event.payload.affected_page_ids)) {
                throw new Error('wiki/page/deleted: payload.affected_page_ids required');
            }
            const removed = new Set(event.payload.affected_page_ids);
            const items = state.items.filter((item) => item && !removed.has(item.wiki_page_id));
            const byId = { ...state.byId };
            for (const id of removed) delete byId[id];
            return { ...state, items, byId };
        }
        return state;
    },
});

export const wikiPageReadOp = createAsyncOp({
    name: 'wiki/page_read',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'wiki/pages/item_requested',
    restMirror: { method: 'GET', path: '/wiki/api/v1/pages/:wiki_page_id' },
    extraReducer: unwrapWikiPageResult,
});

export const wikiPageCreateOp = createAsyncOp({
    name: 'wiki/page_create',
    successToastKey: 'wiki:toast.page.created',
    errorToastKey: 'wiki:toast.page.create_failed',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'wiki/pages/create_requested',
    restMirror: { method: 'POST', path: '/wiki/api/v1/pages' },
    extraReducer: unwrapWikiPageResult,
});

export const wikiPageSaveOp = createAsyncOp({
    name: 'wiki/page_save',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'wiki/pages/content_update_requested',
    restMirror: { method: 'PUT', path: '/wiki/api/v1/pages/:wiki_page_id/content' },
    extraReducer: unwrapWikiPageResult,
});

export const wikiPagePropertiesOp = createAsyncOp({
    name: 'wiki/page_properties',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'wiki/pages/properties_update_requested',
    restMirror: { method: 'PATCH', path: '/wiki/api/v1/pages/:wiki_page_id' },
    extraReducer: unwrapWikiPageResult,
});

export const wikiPageMoveOp = createAsyncOp({
    name: 'wiki/page_move',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'wiki/pages/move_requested',
    restMirror: { method: 'POST', path: '/wiki/api/v1/pages/:wiki_page_id/move' },
    extraReducer: unwrapWikiPageResult,
});

export const wikiPageMoveNamespaceOp = createAsyncOp({
    name: 'wiki/page_move_namespace',
    successToastKey: 'wiki:toast.page.namespace_changed',
    errorToastKey: 'wiki:toast.page.namespace_change_failed',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'wiki/pages/move_namespace_requested',
    restMirror: { method: 'POST', path: '/wiki/api/v1/pages/:wiki_page_id/move-namespace' },
    extraReducer: unwrapWikiPageResult,
});

export const wikiPageDeleteOp = createAsyncOp({
    name: 'wiki/page_delete',
    successToastKey: 'wiki:toast.page.deleted',
    errorToastKey: 'wiki:toast.page.delete_failed',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'wiki/pages/remove_requested',
    restMirror: { method: 'DELETE', path: '/wiki/api/v1/pages/:wiki_page_id' },
});

export const wikiPageRestoreOp = createAsyncOp({
    name: 'wiki/page_restore',
    successToastKey: 'wiki:toast.page.restored',
    errorToastKey: 'wiki:toast.page.restore_failed',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'wiki/pages/restore_requested',
    restMirror: { method: 'POST', path: '/wiki/api/v1/pages/:wiki_page_id/restore' },
    extraReducer: unwrapWikiPageResult,
});

export const wikiDeletedPagesOp = createAsyncOp({
    name: 'wiki/pages_deleted',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'wiki/pages/deleted_list_requested',
    restMirror: { method: 'GET', path: '/wiki/api/v1/pages/deleted' },
});

export const wikiPageMarkdownOp = createAsyncOp({
    name: 'wiki/page_markdown',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'wiki/pages/markdown_requested',
    restMirror: { method: 'GET', path: '/wiki/api/v1/pages/:wiki_page_id/markdown' },
});

export const wikiPageMarkdownImportOp = createAsyncOp({
    name: 'wiki/page_markdown_import',
    successToastKey: 'wiki:toast.markdown.imported',
    errorToastKey: 'wiki:toast.markdown.import_failed',
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'wiki/pages/markdown_import_requested',
    restMirror: { method: 'POST', path: '/wiki/api/v1/pages/:wiki_page_id/import/markdown' },
});

export const wikiMarkdownParseOp = createAsyncOp({
    name: 'wiki/markdown_parse',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'wiki/pages/markdown_parse_requested',
    restMirror: { method: 'POST', path: '/wiki/api/v1/pages/markdown/parse' },
});

export const wikiPageMarkdownCreateOp = createAsyncOp({
    name: 'wiki/page_markdown_create',
    successToastKey: 'wiki:toast.markdown.imported',
    errorToastKey: 'wiki:toast.markdown.import_failed',
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'wiki/pages/markdown_create_requested',
    restMirror: { method: 'POST', path: '/wiki/api/v1/pages/import/markdown' },
});
