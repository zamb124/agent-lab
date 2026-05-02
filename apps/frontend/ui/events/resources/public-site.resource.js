/**
 * Публичный контент сайта: реквизиты, маркетинг, статьи блога.
 *
 * Backend:
 *   GET /frontend/api/public/site-bundle
 *   GET /frontend/api/public/blog
 *   GET /frontend/api/public/blog/post?slug=
 */
import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

export const publicSiteBundleOp = createAsyncOp({
    name: 'frontend/public_site_bundle',
    silent: true,
    restMirror: { method: 'GET', path: '/frontend/api/public/site-bundle' },
    request: async () =>
        httpRequest({
            method: 'GET',
            url: '/frontend/api/public/site-bundle',
            credentials: 'same-origin',
        }),
});

export const publicBlogListOp = createAsyncOp({
    name: 'frontend/public_blog_list',
    silent: true,
    restMirror: { method: 'GET', path: '/frontend/api/public/blog' },
    request: async () =>
        httpRequest({
            method: 'GET',
            url: '/frontend/api/public/blog',
            credentials: 'same-origin',
        }),
});

export const publicBlogPostOp = createAsyncOp({
    name: 'frontend/public_blog_post',
    silent: true,
    restMirror: { method: 'GET', path: '/frontend/api/public/blog/post' },
    request: async ({ payload }) => {
        if (!payload || typeof payload !== 'object') {
            throw new Error('frontend/public_blog_post: payload required');
        }
        const slug = payload.slug;
        if (typeof slug !== 'string' || slug === '') {
            throw new Error('frontend/public_blog_post: slug required');
        }
        const q = new URLSearchParams({ slug });
        return httpRequest({
            method: 'GET',
            url: `/frontend/api/public/blog/post?${q.toString()}`,
            credentials: 'same-origin',
        });
    },
});
