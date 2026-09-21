/**
 * Crawl report — admin monitoring of platform crawl pipeline.
 *
 * Владелец команд — сервис search (`search/crawl_*`, каталог SEARCH_OPERATIONS).
 * REST-зеркало: /search/api/v1/crawl/* (компания system, FGA company#admin).
 * Payload команд уходит as-is: контракт задаёт Pydantic-модель владельца.
 */

import { createAsyncOp, createResourceCollection } from '../index.js';
import { CoreEvents } from '../contract.js';

const WS_TIMEOUT_MS = 8_000;

function _requireProfileId(payload, op) {
    const crawlProfileId = payload && payload.crawl_profile_id;
    if (typeof crawlProfileId !== 'string' || crawlProfileId.length === 0) {
        throw new Error(`${op}: crawl_profile_id required`);
    }
    return crawlProfileId;
}

function _toast(ctx, key) {
    ctx.dispatch(CoreEvents.UI_TOAST_SHOW, { type: 'success', i18n_key: key }, { source: 'local' });
}

export const crawlProfilesLoadOp = createAsyncOp({
    name: 'search/crawl_profiles_load',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'search/crawl_profiles/list_requested',
    restMirror: { method: 'GET', path: '/search/api/v1/crawl/profiles' },
});

export const crawlSummaryLoadOp = createAsyncOp({
    name: 'search/crawl_summary_load',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'search/crawl_profiles/summary_requested',
    restMirror: { method: 'GET', path: '/search/api/v1/crawl/profiles/:crawl_profile_id/summary' },
});

function _reloadSummary(ctx, crawlProfileId) {
    ctx.dispatch(crawlSummaryLoadOp.events.REQUESTED, { crawl_profile_id: crawlProfileId }, { source: 'local' });
}

export const crawlDomainsResource = createResourceCollection({
    name: 'search/crawl_domains',
    baseUrl: '/search/api/v1/crawl/domains',
    idField: 'crawl_domain_id',
    operations: ['list'],
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    listPreserveItemsOnRefresh: true,
    listQuery: (payload) => {
        const q = { limit: 200, offset: 0, crawl_profile_id: _requireProfileId(payload, 'search/crawl_domains') };
        if (payload && payload.status) q.status = payload.status;
        return q;
    },
    restMirror: { list: { method: 'GET', path: '/search/api/v1/crawl/domains' } },
});

export const crawlUrlsResource = createResourceCollection({
    name: 'search/crawl_urls',
    baseUrl: '/search/api/v1/crawl/urls',
    idField: 'crawl_url_id',
    operations: ['list'],
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    listPreserveItemsOnRefresh: true,
    listQuery: (payload) => {
        const q = { limit: 200, offset: 0, crawl_profile_id: _requireProfileId(payload, 'search/crawl_urls') };
        if (payload && payload.crawl_status) q.crawl_status = payload.crawl_status;
        if (payload && payload.domain) q.domain = payload.domain;
        if (payload && payload.content_type) q.content_type = payload.content_type;
        if (payload && payload.primary_topic) q.primary_topic = payload.primary_topic;
        if (payload && payload.enriched_only === true) q.enriched_only = true;
        return q;
    },
    restMirror: { list: { method: 'GET', path: '/search/api/v1/crawl/urls' } },
});

export const crawlJobsResource = createResourceCollection({
    name: 'search/crawl_jobs',
    baseUrl: '/search/api/v1/crawl/jobs',
    idField: 'crawl_job_id',
    operations: ['list'],
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    listPreserveItemsOnRefresh: true,
    listQuery: (payload) => {
        const q = { limit: 100, offset: 0, crawl_profile_id: _requireProfileId(payload, 'search/crawl_jobs') };
        if (payload && payload.status) q.status = payload.status;
        return q;
    },
    restMirror: { list: { method: 'GET', path: '/search/api/v1/crawl/jobs' } },
});

export const crawlUrlDetailOp = createAsyncOp({
    name: 'search/crawl_url_detail',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'search/crawl_urls/get_requested',
    restMirror: { method: 'GET', path: '/search/api/v1/crawl/urls/:crawl_url_id' },
});

export const crawlQueueTickOp = createAsyncOp({
    name: 'search/crawl_queue_tick',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'search/crawl_jobs/queue_requested',
    restMirror: { method: 'POST', path: '/search/api/v1/crawl/jobs' },
    onSuccess(ctx, _result, event) {
        const requestPayload = event && event.payload;
        _toast(ctx, 'frontend:crawl_report_page.toast_queued');
        if (requestPayload && requestPayload.crawl_profile_id) {
            _reloadSummary(ctx, requestPayload.crawl_profile_id);
            ctx.dispatch(crawlJobsResource.events.LIST_REQUESTED, requestPayload, { source: 'local' });
        }
    },
});

export const crawlDomainRunOp = createAsyncOp({
    name: 'search/crawl_domain_run',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'search/crawl_domains/run_requested',
    restMirror: { method: 'POST', path: '/search/api/v1/crawl/domains/:crawl_domain_id/run' },
    onSuccess(ctx, _result, event) {
        const requestPayload = event && event.payload;
        _toast(ctx, 'frontend:crawl_report_page.toast_domain_queued');
        if (!requestPayload || !requestPayload.crawl_profile_id) {
            return;
        }
        _reloadSummary(ctx, requestPayload.crawl_profile_id);
        ctx.dispatch(crawlJobsResource.events.LIST_REQUESTED, requestPayload, { source: 'local' });
        ctx.dispatch(crawlDomainsResource.events.LIST_REQUESTED, requestPayload, { source: 'local' });
    },
});

export const crawlProfilePatchOp = createAsyncOp({
    name: 'search/crawl_profile_patch',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'search/crawl_profiles/update_requested',
    restMirror: { method: 'PATCH', path: '/search/api/v1/crawl/profiles/:crawl_profile_id' },
    onSuccess(ctx, _result, event) {
        const requestPayload = event && event.payload;
        _toast(ctx, 'frontend:crawl_report_page.toast_profile_saved');
        ctx.dispatch(crawlProfilesLoadOp.events.REQUESTED, {}, { source: 'local' });
        if (requestPayload && requestPayload.crawl_profile_id) {
            _reloadSummary(ctx, requestPayload.crawl_profile_id);
        }
    },
});

export const crawlDomainCreateOp = createAsyncOp({
    name: 'search/crawl_domain_create',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'search/crawl_domains/create_requested',
    restMirror: { method: 'POST', path: '/search/api/v1/crawl/profiles/:crawl_profile_id/domains' },
    onSuccess(ctx, _result, event) {
        const requestPayload = event && event.payload;
        _toast(ctx, 'frontend:crawl_report_page.toast_domain_added');
        if (requestPayload && requestPayload.crawl_profile_id) {
            const listPayload = { crawl_profile_id: requestPayload.crawl_profile_id };
            _reloadSummary(ctx, requestPayload.crawl_profile_id);
            ctx.dispatch(crawlDomainsResource.events.LIST_REQUESTED, listPayload, { source: 'local' });
        }
    },
});

export const crawlDomainPatchOp = createAsyncOp({
    name: 'search/crawl_domain_patch',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'search/crawl_domains/update_requested',
    restMirror: { method: 'PATCH', path: '/search/api/v1/crawl/domains/:crawl_domain_id' },
    onSuccess(ctx, _result, event) {
        const requestPayload = event && event.payload;
        _toast(ctx, 'frontend:crawl_report_page.toast_domain_saved');
        if (requestPayload && requestPayload.crawl_profile_id) {
            const listPayload = { crawl_profile_id: requestPayload.crawl_profile_id };
            _reloadSummary(ctx, requestPayload.crawl_profile_id);
            ctx.dispatch(crawlDomainsResource.events.LIST_REQUESTED, listPayload, { source: 'local' });
        }
    },
});

export const crawlDomainDeleteOp = createAsyncOp({
    name: 'search/crawl_domain_delete',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'search/crawl_domains/remove_requested',
    restMirror: { method: 'DELETE', path: '/search/api/v1/crawl/domains/:crawl_domain_id' },
    onSuccess(ctx, _result, event) {
        const requestPayload = event && event.payload;
        _toast(ctx, 'frontend:crawl_report_page.toast_domain_deleted');
        if (requestPayload && requestPayload.crawl_profile_id) {
            const listPayload = { crawl_profile_id: requestPayload.crawl_profile_id };
            _reloadSummary(ctx, requestPayload.crawl_profile_id);
            ctx.dispatch(crawlDomainsResource.events.LIST_REQUESTED, listPayload, { source: 'local' });
        }
    },
});

export const crawlUrlAddOp = createAsyncOp({
    name: 'search/crawl_url_add',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'search/crawl_domains/urls_add_requested',
    restMirror: { method: 'POST', path: '/search/api/v1/crawl/domains/:crawl_domain_id/urls' },
    onSuccess(ctx, _result, event) {
        const requestPayload = event && event.payload;
        _toast(ctx, 'frontend:crawl_report_page.toast_urls_added');
        if (requestPayload && requestPayload.crawl_profile_id) {
            const listPayload = { crawl_profile_id: requestPayload.crawl_profile_id };
            _reloadSummary(ctx, requestPayload.crawl_profile_id);
            ctx.dispatch(crawlUrlsResource.events.LIST_REQUESTED, listPayload, { source: 'local' });
        }
    },
});

export const crawlUrlRecrawlOp = createAsyncOp({
    name: 'search/crawl_url_recrawl',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'search/crawl_urls/recrawl_requested',
    restMirror: { method: 'POST', path: '/search/api/v1/crawl/urls/:crawl_url_id/recrawl' },
    onSuccess(ctx, _result, event) {
        const requestPayload = event && event.payload;
        _toast(ctx, 'frontend:crawl_report_page.toast_url_recrawl');
        if (requestPayload && requestPayload.crawl_profile_id) {
            const listPayload = { crawl_profile_id: requestPayload.crawl_profile_id };
            _reloadSummary(ctx, requestPayload.crawl_profile_id);
            ctx.dispatch(crawlUrlsResource.events.LIST_REQUESTED, listPayload, { source: 'local' });
        }
    },
});
