/**
 * Middleware для @web/test-runner: то же соглашение URL, что у FastAPI-статики
 * (`/static/core/...` → `core/frontend/static/...`), плюс минимальные ответы для
 * bootstrap-эффектов (file-types, i18n, health, sw) и GET CRM offset-page.
 */

/** @param {import('koa').Context} context */
function _pathname(context) {
    if (context.URL && typeof context.URL.pathname === 'string') {
        return context.URL.pathname;
    }
    const href = context.request?.href || context.url;
    return new URL(href, 'http://localhost').pathname;
}

function _search(context) {
    if (context.URL && typeof context.URL.search === 'string') {
        return context.URL.search;
    }
    const href = context.request?.href || context.url;
    return new URL(href, 'http://localhost').search;
}

/** @param {import('koa').Context} context */
export async function browserTestDevMiddleware(context, next) {
    const pathname = _pathname(context);
    const method = context.method;

    if (method === 'GET' && pathname === '/health') {
        context.status = 200;
        context.body = 'ok';
        context.set('content-type', 'text/plain; charset=utf-8');
        return;
    }
    if (method === 'GET' && pathname === '/sw.js') {
        context.status = 200;
        context.body = '// test runner stub\n';
        context.set('content-type', 'application/javascript; charset=utf-8');
        return;
    }
    if (method === 'GET' && pathname === '/api/platform/file-types') {
        context.status = 200;
        context.body = JSON.stringify({ categories: [], registry: [] });
        context.set('content-type', 'application/json; charset=utf-8');
        return;
    }
    if (method === 'GET' && pathname.startsWith('/api/i18n/')) {
        context.status = 200;
        context.body = JSON.stringify({});
        context.set('content-type', 'application/json; charset=utf-8');
        return;
    }
    if (
        method === 'GET'
        && pathname.startsWith('/crm/api/')
        && pathname.includes('entity-types')
        && !pathname.endsWith('.js')
    ) {
        context.status = 200;
        context.body = JSON.stringify({
            items: [],
            total: 0,
            limit: 200,
            offset: 0,
        });
        context.set('content-type', 'application/json; charset=utf-8');
        return;
    }

    if (pathname.startsWith('/static/core/')) {
        const rest = pathname.slice('/static/core/'.length);
        context.url = `/core/frontend/static/${rest}${_search(context)}`;
    }
    return next();
}
