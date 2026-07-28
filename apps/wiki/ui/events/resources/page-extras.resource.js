/**
 * Окружение страницы: доступ, история, комментарии, поиск, обратные ссылки.
 *
 * Как и страницы, всё адресовано текущему рабочему пространству через
 * заголовок `X-Platform-Namespace`.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';
import { platformNamespaceHeader } from '@platform/lib/utils/platform-namespace-header.js';

const PAGES_URL = '/wiki/api/v1/pages';
const API_URL = '/wiki/api/v1';

export const WIKI_COMMENT_EVENTS = ['wiki/comment/created', 'wiki/comment/resolved'];

export const wikiAccessReadOp = createAsyncOp({
    name: 'wiki/access_read',
    silent: true,
    restMirror: { method: 'GET', path: '/wiki/api/v1/pages/:wiki_page_id/access' },
    request: ({ payload, ctx }) => httpRequest({
        method: 'GET',
        url: `${PAGES_URL}/${payload.wiki_page_id}/access`,
        headers: platformNamespaceHeader(ctx),
    }),
});

export const wikiMemberAddOp = createAsyncOp({
    name: 'wiki/member_add',
    successToastKey: 'wiki:toast.access.member_added',
    errorToastKey: 'wiki:toast.access.member_add_failed',
    restMirror: { method: 'POST', path: '/wiki/api/v1/pages/:wiki_page_id/access/members' },
    request: ({ payload, ctx }) => httpRequest({
        method: 'POST',
        url: `${PAGES_URL}/${payload.wiki_page_id}/access/members`,
        headers: platformNamespaceHeader(ctx),
        body: { user_id: payload.user_id, permission: payload.permission },
    }),
});

export const wikiMemberRemoveOp = createAsyncOp({
    name: 'wiki/member_remove',
    successToastKey: 'wiki:toast.access.member_removed',
    errorToastKey: 'wiki:toast.access.member_remove_failed',
    restMirror: {
        method: 'DELETE',
        path: '/wiki/api/v1/pages/:wiki_page_id/access/members/:member_user_id',
    },
    request: ({ payload, ctx }) => httpRequest({
        method: 'DELETE',
        url: `${PAGES_URL}/${payload.wiki_page_id}/access/members/${payload.member_user_id}`,
        headers: platformNamespaceHeader(ctx),
    }),
});

export const wikiPublicLinkOp = createAsyncOp({
    name: 'wiki/public_link',
    successToastKey: 'wiki:toast.access.link_updated',
    errorToastKey: 'wiki:toast.access.link_failed',
    restMirror: { method: 'POST', path: '/wiki/api/v1/pages/:wiki_page_id/access/link' },
    request: ({ payload, ctx }) => httpRequest({
        method: 'POST',
        url: `${PAGES_URL}/${payload.wiki_page_id}/access/link`,
        headers: platformNamespaceHeader(ctx),
        body: { enabled: payload.enabled, permission: payload.permission },
    }),
});

export const wikiRevisionsOp = createAsyncOp({
    name: 'wiki/revisions',
    silent: true,
    restMirror: { method: 'GET', path: '/wiki/api/v1/pages/:wiki_page_id/revisions' },
    request: ({ payload, ctx }) => httpRequest({
        method: 'GET',
        url: `${API_URL}/pages/${payload.wiki_page_id}/revisions`,
        headers: platformNamespaceHeader(ctx),
    }),
});

export const wikiRevisionReadOp = createAsyncOp({
    name: 'wiki/revision_read',
    silent: true,
    restMirror: { method: 'GET', path: '/wiki/api/v1/revisions/:wiki_revision_id' },
    request: ({ payload, ctx }) => httpRequest({
        method: 'GET',
        url: `${API_URL}/revisions/${payload.wiki_revision_id}`,
        headers: platformNamespaceHeader(ctx),
    }),
});

export const wikiRevisionRestoreOp = createAsyncOp({
    name: 'wiki/revision_restore',
    successToastKey: 'wiki:toast.revision.restored',
    errorToastKey: 'wiki:toast.revision.restore_failed',
    restMirror: { method: 'POST', path: '/wiki/api/v1/revisions/:wiki_revision_id/restore' },
    request: ({ payload, ctx }) => httpRequest({
        method: 'POST',
        url: `${API_URL}/revisions/${payload.wiki_revision_id}/restore`,
        headers: platformNamespaceHeader(ctx),
    }),
});

export const wikiCommentsOp = createAsyncOp({
    name: 'wiki/comments',
    silent: true,
    restMirror: { method: 'GET', path: '/wiki/api/v1/pages/:wiki_page_id/comments' },
    request: ({ payload, ctx }) => httpRequest({
        method: 'GET',
        url: `${API_URL}/pages/${payload.wiki_page_id}/comments`,
        headers: platformNamespaceHeader(ctx),
    }),
});

export const wikiCommentCreateOp = createAsyncOp({
    name: 'wiki/comment_create',
    silent: true,
    restMirror: { method: 'POST', path: '/wiki/api/v1/pages/:wiki_page_id/comments' },
    // Пропущенные поля добираются дефолтами Pydantic — второй источник
    // умолчаний в UI разошёлся бы с бэкендом.
    request: ({ payload, ctx }) => httpRequest({
        method: 'POST',
        url: `${API_URL}/pages/${payload.wiki_page_id}/comments`,
        headers: platformNamespaceHeader(ctx),
        body: {
            body_markdown: payload.body_markdown,
            anchor_text: payload.anchor_text,
            parent_comment_id: payload.parent_comment_id,
        },
    }),
});

export const wikiCommentResolveOp = createAsyncOp({
    name: 'wiki/comment_resolve',
    silent: true,
    restMirror: { method: 'POST', path: '/wiki/api/v1/comments/:wiki_comment_id/resolve' },
    request: ({ payload, ctx }) => httpRequest({
        method: 'POST',
        url: `${API_URL}/comments/${payload.wiki_comment_id}/resolve`,
        headers: platformNamespaceHeader(ctx),
        body: { resolved: payload.resolved },
    }),
});

export const wikiSearchOp = createAsyncOp({
    name: 'wiki/search',
    silent: true,
    restMirror: { method: 'POST', path: '/wiki/api/v1/search' },
    request: ({ payload, ctx }) => httpRequest({
        method: 'POST',
        url: `${API_URL}/search`,
        headers: platformNamespaceHeader(ctx),
        body: {
            query: payload.query,
            mode: payload.mode,
            root_page_id: payload.root_page_id,
            published_only: payload.published_only,
            updated_after_days: payload.updated_after_days,
            editor_user_id: payload.editor_user_id,
            limit: payload.limit,
        },
    }),
});

export const wikiBacklinksOp = createAsyncOp({
    name: 'wiki/backlinks',
    silent: true,
    restMirror: { method: 'GET', path: '/wiki/api/v1/backlinks' },
    request: ({ payload, ctx }) => httpRequest({
        method: 'GET',
        url: `${API_URL}/backlinks`,
        query: {
            target_kind: 'wiki_page',
            target_id: payload.target_id,
        },
        headers: platformNamespaceHeader(ctx),
    }),
});

/** Корень публичного сайта читается без пространства и без сессии. */
export const wikiPublicPageOp = createAsyncOp({
    name: 'wiki/public_page',
    silent: true,
    restMirror: { method: 'GET', path: '/wiki/api/v1/public/pages/:link_token' },
    request: ({ payload }) => httpRequest({
        method: 'GET',
        url: `${API_URL}/public/pages/${payload.link_token}`,
    }),
});

/** Навигация публичного сайта: корень ссылки и его опубликованное поддерево. */
export const wikiPublicTreeOp = createAsyncOp({
    name: 'wiki/public_tree',
    silent: true,
    restMirror: { method: 'GET', path: '/wiki/api/v1/public/pages/:link_token/tree' },
    request: ({ payload }) => httpRequest({
        method: 'GET',
        url: `${API_URL}/public/pages/${payload.link_token}/tree`,
    }),
});

/** Подстраница публичного сайта по тому же токену. */
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
