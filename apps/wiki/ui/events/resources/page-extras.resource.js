/**
 * Окружение страницы: доступ, история, комментарии, поиск, обратные ссылки.
 *
 * Команды с сессией идут через WS RPC. Публичный сайт — HTTP без сессии.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

const API_URL = '/wiki/api/v1';

export const WIKI_COMMENT_EVENTS = ['wiki/comment/created', 'wiki/comment/resolved'];

function unwrapWikiPageResult(state, event, events) {
    if (event.type !== events.SUCCEEDED) {
        return state;
    }
    if (!event.payload || !('result' in event.payload)) {
        throw new Error('wiki extras: SUCCEEDED payload.result required');
    }
    const result = event.payload.result;
    if (
        !result
        || typeof result !== 'object'
        || result.page === null
        || typeof result.page !== 'object'
    ) {
        throw new Error('wiki extras: ожидался WikiPageResponse с полем page');
    }
    return { ...state, lastResult: result.page };
}

export const wikiAccessReadOp = createAsyncOp({
    name: 'wiki/access_read',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'wiki/pages/access_requested',
    restMirror: { method: 'GET', path: '/wiki/api/v1/pages/:wiki_page_id/access' },
});

export const wikiCompanyVisibleOp = createAsyncOp({
    name: 'wiki/company_visible',
    successToastKey: 'wiki:toast.access.company_visible_updated',
    errorToastKey: 'wiki:toast.access.company_visible_failed',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'wiki/pages/company_visible_requested',
    restMirror: { method: 'PATCH', path: '/wiki/api/v1/pages/:wiki_page_id/access/company-visible' },
});

export const wikiMemberAddOp = createAsyncOp({
    name: 'wiki/member_add',
    successToastKey: 'wiki:toast.access.member_added',
    errorToastKey: 'wiki:toast.access.member_add_failed',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'wiki/pages/member_add_requested',
    restMirror: { method: 'POST', path: '/wiki/api/v1/pages/:wiki_page_id/access/members' },
});

export const wikiMemberRemoveOp = createAsyncOp({
    name: 'wiki/member_remove',
    successToastKey: 'wiki:toast.access.member_removed',
    errorToastKey: 'wiki:toast.access.member_remove_failed',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'wiki/pages/member_remove_requested',
    restMirror: {
        method: 'DELETE',
        path: '/wiki/api/v1/pages/:wiki_page_id/access/members/:member_user_id',
    },
});

export const wikiPublicLinkOp = createAsyncOp({
    name: 'wiki/public_link',
    successToastKey: 'wiki:toast.access.link_updated',
    errorToastKey: 'wiki:toast.access.link_failed',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'wiki/pages/public_link_requested',
    restMirror: { method: 'POST', path: '/wiki/api/v1/pages/:wiki_page_id/access/link' },
});

export const wikiRevisionsOp = createAsyncOp({
    name: 'wiki/revisions',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'wiki/pages/revisions_list_requested',
    restMirror: { method: 'GET', path: '/wiki/api/v1/pages/:wiki_page_id/revisions' },
});

export const wikiRevisionReadOp = createAsyncOp({
    name: 'wiki/revision_read',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'wiki/revisions/item_requested',
    restMirror: { method: 'GET', path: '/wiki/api/v1/revisions/:wiki_revision_id' },
});

export const wikiRevisionRestoreOp = createAsyncOp({
    name: 'wiki/revision_restore',
    successToastKey: 'wiki:toast.revision.restored',
    errorToastKey: 'wiki:toast.revision.restore_failed',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'wiki/revisions/restore_requested',
    restMirror: { method: 'POST', path: '/wiki/api/v1/revisions/:wiki_revision_id/restore' },
    extraReducer: unwrapWikiPageResult,
});

export const wikiCommentsOp = createAsyncOp({
    name: 'wiki/comments',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'wiki/pages/comments_list_requested',
    restMirror: { method: 'GET', path: '/wiki/api/v1/pages/:wiki_page_id/comments' },
});

export const wikiCommentCreateOp = createAsyncOp({
    name: 'wiki/comment_create',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'wiki/pages/comment_create_requested',
    restMirror: { method: 'POST', path: '/wiki/api/v1/pages/:wiki_page_id/comments' },
});

export const wikiCommentResolveOp = createAsyncOp({
    name: 'wiki/comment_resolve',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'wiki/comments/resolve_requested',
    restMirror: { method: 'POST', path: '/wiki/api/v1/comments/:wiki_comment_id/resolve' },
});

export const wikiSearchOp = createAsyncOp({
    name: 'wiki/search',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'wiki/search/run_requested',
    restMirror: { method: 'POST', path: '/wiki/api/v1/search' },
});

export const wikiBacklinksOp = createAsyncOp({
    name: 'wiki/backlinks',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'wiki/backlinks/list_requested',
    restMirror: { method: 'GET', path: '/wiki/api/v1/backlinks' },
});

export const wikiPublicPageOp = createAsyncOp({
    name: 'wiki/public_page',
    silent: true,
    restMirror: { method: 'GET', path: '/wiki/api/v1/public/pages/:link_token' },
    request: ({ payload }) => httpRequest({
        method: 'GET',
        url: `${API_URL}/public/pages/${payload.link_token}`,
    }),
});

export const wikiPublicTreeOp = createAsyncOp({
    name: 'wiki/public_tree',
    silent: true,
    restMirror: { method: 'GET', path: '/wiki/api/v1/public/pages/:link_token/tree' },
    request: ({ payload }) => httpRequest({
        method: 'GET',
        url: `${API_URL}/public/pages/${payload.link_token}/tree`,
    }),
});

export const wikiPublicSitePageOp = createAsyncOp({
    name: 'wiki/public_site_page',
    silent: true,
    restMirror: {
        method: 'GET',
        path: '/wiki/api/v1/public/pages/:link_token/pages/:wiki_page_id',
    },
    request: ({ payload }) => httpRequest({
        method: 'GET',
        url: `${API_URL}/public/pages/${payload.link_token}/pages/${payload.wiki_page_id}`,
    }),
});
