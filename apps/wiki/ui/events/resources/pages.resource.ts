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
import type { AsyncOpSlice } from '@platform/lib/events/factories/async-op.js';
import type { PlatformEvent } from '@platform/lib/events/contract.js';
import type { ResourceCollectionSlice, ResourceItem } from '@platform/lib/events/factories/resource-collection.js';
import { isPlatformEventType, isPlainRecord } from '@platform/lib/events/payload.js';
import type { WikiPage, WikiPageSummary } from '@platform/lib/events/wire/wiki.gen.js';

export const WIKI_PAGE_EVENTS = [
    'wiki/page/created',
    'wiki/page/updated',
    'wiki/page/published',
    'wiki/page/moved',
    'wiki/page/deleted',
    'wiki/page/restored',
    'wiki/page/access_changed',
];

function mergeSummary(state: ResourceCollectionSlice<WikiPageSummary>, summary: WikiPageSummary): ResourceCollectionSlice<WikiPageSummary> {
    const id = summary.wiki_page_id;
    const index = state.items.findIndex((item) => item && item.wiki_page_id === id);
    const items = index === -1
        ? [...state.items, summary]
        : state.items.map((item, position: number) => (position === index ? summary : item));
    return { ...state, items, byId: { ...state.byId, [id]: summary } };
}

function unwrapWikiPageResult(state: AsyncOpSlice<WikiPage>, event: PlatformEvent, events: Readonly<Record<string, string>>): AsyncOpSlice<WikiPage> {
    if (event.type !== events.SUCCEEDED) {
        return state;
    }
    if (!isPlainRecord(event.payload) || !('result' in event.payload)) {
        throw new Error('wiki pages: SUCCEEDED payload.result required');
    }
    const result = event.payload.result;
    if (!isPlainRecord(result)) {
        throw new Error('wiki pages: ожидался WikiPageResponse с полем page');
    }
    const page = result.page;
    if (!isPlainRecord(page)) {
        throw new Error('wiki pages: ожидался WikiPageResponse с полем page');
    }
    return { ...state, lastResult: page as WikiPage };
}

export const wikiPagesResource = createResourceCollection({
    name: 'wiki/pages',
    baseUrl: '/wiki/api/v1/pages',
    idField: 'wiki_page_id',
    operations: ['list'],
    transport: 'ws',
    wsTimeoutMs: 8_000,
    listQuery: () => ({}),
    extraReducer: (state, event) => {
        if (
            isPlatformEventType(event, 'wiki/page/created')
            || isPlatformEventType(event, 'wiki/page/updated')
            || isPlatformEventType(event, 'wiki/page/published')
            || isPlatformEventType(event, 'wiki/page/moved')
            || isPlatformEventType(event, 'wiki/page/restored')
        ) {
            return mergeSummary(state, event.payload.page);
        }
        if (isPlatformEventType(event, 'wiki/page/deleted')) {
            const removed = new Set(event.payload.affected_page_ids);
            const items = state.items.filter((item) => !removed.has(item.wiki_page_id));
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

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'wiki/pages': typeof wikiPagesResource;
        'wiki/page_read': typeof wikiPageReadOp;
        'wiki/page_create': typeof wikiPageCreateOp;
        'wiki/page_save': typeof wikiPageSaveOp;
        'wiki/page_properties': typeof wikiPagePropertiesOp;
        'wiki/page_move': typeof wikiPageMoveOp;
        'wiki/page_move_namespace': typeof wikiPageMoveNamespaceOp;
        'wiki/page_delete': typeof wikiPageDeleteOp;
        'wiki/page_restore': typeof wikiPageRestoreOp;
        'wiki/pages_deleted': typeof wikiDeletedPagesOp;
        'wiki/page_markdown': typeof wikiPageMarkdownOp;
        'wiki/page_markdown_import': typeof wikiPageMarkdownImportOp;
        'wiki/markdown_parse': typeof wikiMarkdownParseOp;
        'wiki/page_markdown_create': typeof wikiPageMarkdownCreateOp;
    }
}
