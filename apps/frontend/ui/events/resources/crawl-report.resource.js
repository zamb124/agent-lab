/**
 * Crawl report — admin monitoring of platform crawl pipeline.
 *
 * API: /frontend/api/crawl-report/* (system company only).
 */

import {
    createResourceCollection,
    createAsyncOp,
} from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';
import { CoreEvents } from '@platform/lib/events/contract.js';

const BASE = '/frontend/api/crawl-report';

export const crawlProfilesLoadOp = createAsyncOp({
    name: 'frontend/crawl_profiles_load',
    silent: true,
    restMirror: { method: 'GET', path: `${BASE}/profiles` },
    request: async () => httpRequest({ method: 'GET', url: `${BASE}/profiles`, query: { limit: 200, offset: 0 } }),
    statusMap: { 403: 'forbidden', 503: 'unavailable' },
});

export const crawlSummaryLoadOp = createAsyncOp({
    name: 'frontend/crawl_summary_load',
    silent: true,
    restMirror: { method: 'GET', path: `${BASE}/profiles/:crawl_profile_id/summary` },
    request: async ({ payload }) => {
        const crawlProfileId = payload && payload.crawl_profile_id;
        if (!crawlProfileId) throw new Error('crawl_summary_load: crawl_profile_id required');
        return await httpRequest({
            method: 'GET',
            url: `${BASE}/profiles/${encodeURIComponent(crawlProfileId)}/summary`,
        });
    },
    statusMap: { 403: 'forbidden', 503: 'unavailable', 404: 'not_found' },
});

export const crawlDomainsResource = createResourceCollection({
    name: 'frontend/crawl_domains',
    baseUrl: `${BASE}/domains`,
    idField: 'crawl_domain_id',
    operations: ['list'],
    listPreserveItemsOnRefresh: true,
    listQuery: (payload) => {
        const crawlProfileId = payload && payload.crawl_profile_id;
        if (!crawlProfileId) {
            throw new Error('frontend/crawl_domains: crawl_profile_id required for list');
        }
        const q = { limit: 200, offset: 0, crawl_profile_id: crawlProfileId };
        if (payload && payload.status) q.status = payload.status;
        return q;
    },
});

export const crawlUrlsResource = createResourceCollection({
    name: 'frontend/crawl_urls',
    baseUrl: `${BASE}/urls`,
    idField: 'crawl_url_id',
    operations: ['list'],
    listPreserveItemsOnRefresh: true,
    listQuery: (payload) => {
        const crawlProfileId = payload && payload.crawl_profile_id;
        if (!crawlProfileId) {
            throw new Error('frontend/crawl_urls: crawl_profile_id required for list');
        }
        const q = { limit: 200, offset: 0, crawl_profile_id: crawlProfileId };
        if (payload && payload.crawl_status) q.crawl_status = payload.crawl_status;
        if (payload && payload.domain) q.domain = payload.domain;
        if (payload && payload.content_type) q.content_type = payload.content_type;
        if (payload && payload.primary_topic) q.primary_topic = payload.primary_topic;
        if (payload && payload.enriched_only === true) q.enriched_only = true;
        return q;
    },
});

export const crawlJobsResource = createResourceCollection({
    name: 'frontend/crawl_jobs',
    baseUrl: `${BASE}/jobs`,
    idField: 'crawl_job_id',
    operations: ['list'],
    listPreserveItemsOnRefresh: true,
    listQuery: (payload) => {
        const crawlProfileId = payload && payload.crawl_profile_id;
        if (!crawlProfileId) {
            throw new Error('frontend/crawl_jobs: crawl_profile_id required for list');
        }
        const q = { limit: 100, offset: 0, crawl_profile_id: crawlProfileId };
        if (payload && payload.status) q.status = payload.status;
        return q;
    },
});

export const crawlUrlDetailOp = createAsyncOp({
    name: 'frontend/crawl_url_detail',
    silent: true,
    restMirror: { method: 'GET', path: `${BASE}/urls/:crawl_url_id` },
    request: async ({ payload }) => {
        const crawlUrlId = payload && payload.crawl_url_id;
        const crawlProfileId = payload && payload.crawl_profile_id;
        if (!crawlUrlId) throw new Error('crawl_url_detail: crawl_url_id required');
        if (!crawlProfileId) throw new Error('crawl_url_detail: crawl_profile_id required');
        return await httpRequest({
            method: 'GET',
            url: `${BASE}/urls/${encodeURIComponent(crawlUrlId)}`,
            query: { crawl_profile_id: crawlProfileId },
        });
    },
    statusMap: { 403: 'forbidden', 503: 'unavailable', 404: 'not_found' },
});

function _reloadSummary(ctx, crawlProfileId) {
    ctx.dispatch(crawlSummaryLoadOp.events.REQUESTED, { crawl_profile_id: crawlProfileId }, { source: 'local' });
}

export const crawlQueueTickOp = createAsyncOp({
    name: 'frontend/crawl_queue_tick',
    silent: true,
    restMirror: { method: 'POST', path: `${BASE}/jobs` },
    request: async ({ payload }) => {
        const crawlProfileId = payload && payload.crawl_profile_id;
        if (!crawlProfileId) throw new Error('crawl_queue_tick: crawl_profile_id required');
        return await httpRequest({
            method: 'POST',
            url: `${BASE}/jobs`,
            body: {
                crawl_profile_id: crawlProfileId,
                trigger: payload.trigger || 'manual',
            },
        });
    },
    onSuccess(ctx, _result, event) {
        const requestPayload = event && event.payload;
        ctx.dispatch(
            CoreEvents.UI_TOAST_SHOW,
            { type: 'success', i18n_key: 'frontend:crawl_report_page.toast_queued' },
            { source: 'local' },
        );
        if (requestPayload && requestPayload.crawl_profile_id) {
            _reloadSummary(ctx, requestPayload.crawl_profile_id);
            ctx.dispatch(crawlJobsResource.events.LIST_REQUESTED, requestPayload, { source: 'local' });
        }
    },
});

export const crawlDomainRunOp = createAsyncOp({
    name: 'frontend/crawl_domain_run',
    silent: true,
    restMirror: { method: 'POST', path: `${BASE}/domains/:crawl_domain_id/run` },
    request: async ({ payload }) => {
        const crawlDomainId = payload && payload.crawl_domain_id;
        const crawlProfileId = payload && payload.crawl_profile_id;
        if (!crawlDomainId) throw new Error('crawl_domain_run: crawl_domain_id required');
        if (!crawlProfileId) throw new Error('crawl_domain_run: crawl_profile_id required');
        return await httpRequest({
            method: 'POST',
            url: `${BASE}/domains/${encodeURIComponent(crawlDomainId)}/run`,
            query: { crawl_profile_id: crawlProfileId },
            body: {},
        });
    },
    onSuccess(ctx, _result, event) {
        const requestPayload = event && event.payload;
        ctx.dispatch(
            CoreEvents.UI_TOAST_SHOW,
            { type: 'success', i18n_key: 'frontend:crawl_report_page.toast_domain_queued' },
            { source: 'local' },
        );
        if (!requestPayload || !requestPayload.crawl_profile_id) {
            return;
        }
        _reloadSummary(ctx, requestPayload.crawl_profile_id);
        ctx.dispatch(crawlJobsResource.events.LIST_REQUESTED, requestPayload, { source: 'local' });
        ctx.dispatch(crawlDomainsResource.events.LIST_REQUESTED, requestPayload, { source: 'local' });
    },
});

export const crawlProfilePatchOp = createAsyncOp({
    name: 'frontend/crawl_profile_patch',
    silent: true,
    restMirror: { method: 'PATCH', path: `${BASE}/profiles/:crawl_profile_id` },
    request: async ({ payload }) => {
        const crawlProfileId = payload && payload.crawl_profile_id;
        if (!crawlProfileId) throw new Error('crawl_profile_patch: crawl_profile_id required');
        const { crawl_profile_id, ...patch } = payload;
        return await httpRequest({
            method: 'PATCH',
            url: `${BASE}/profiles/${encodeURIComponent(crawlProfileId)}`,
            body: patch,
        });
    },
    onSuccess(ctx, _result, event) {
        const requestPayload = event && event.payload;
        ctx.dispatch(
            CoreEvents.UI_TOAST_SHOW,
            { type: 'success', i18n_key: 'frontend:crawl_report_page.toast_profile_saved' },
            { source: 'local' },
        );
        ctx.dispatch(crawlProfilesLoadOp.events.REQUESTED, {}, { source: 'local' });
        if (requestPayload && requestPayload.crawl_profile_id) {
            _reloadSummary(ctx, requestPayload.crawl_profile_id);
        }
    },
});

export const crawlDomainCreateOp = createAsyncOp({
    name: 'frontend/crawl_domain_create',
    silent: true,
    restMirror: { method: 'POST', path: `${BASE}/profiles/:crawl_profile_id/domains` },
    request: async ({ payload }) => {
        const crawlProfileId = payload && payload.crawl_profile_id;
        if (!crawlProfileId) throw new Error('crawl_domain_create: crawl_profile_id required');
        const body = { domain: payload.domain };
        if (payload.category) body.category = payload.category;
        if (typeof payload.refresh_interval_seconds === 'number') {
            body.refresh_interval_seconds = payload.refresh_interval_seconds;
        }
        if (Array.isArray(payload.seed_urls) && payload.seed_urls.length > 0) {
            body.seed_urls = payload.seed_urls;
        }
        return await httpRequest({
            method: 'POST',
            url: `${BASE}/profiles/${encodeURIComponent(crawlProfileId)}/domains`,
            body,
        });
    },
    onSuccess(ctx, _result, event) {
        const requestPayload = event && event.payload;
        ctx.dispatch(
            CoreEvents.UI_TOAST_SHOW,
            { type: 'success', i18n_key: 'frontend:crawl_report_page.toast_domain_added' },
            { source: 'local' },
        );
        if (requestPayload && requestPayload.crawl_profile_id) {
            const listPayload = { crawl_profile_id: requestPayload.crawl_profile_id };
            _reloadSummary(ctx, requestPayload.crawl_profile_id);
            ctx.dispatch(crawlDomainsResource.events.LIST_REQUESTED, listPayload, { source: 'local' });
        }
    },
});

export const crawlDomainPatchOp = createAsyncOp({
    name: 'frontend/crawl_domain_patch',
    silent: true,
    restMirror: { method: 'PATCH', path: `${BASE}/domains/:crawl_domain_id` },
    request: async ({ payload }) => {
        const crawlDomainId = payload && payload.crawl_domain_id;
        const crawlProfileId = payload && payload.crawl_profile_id;
        if (!crawlDomainId) throw new Error('crawl_domain_patch: crawl_domain_id required');
        if (!crawlProfileId) throw new Error('crawl_domain_patch: crawl_profile_id required');
        const { crawl_domain_id, crawl_profile_id, ...patch } = payload;
        return await httpRequest({
            method: 'PATCH',
            url: `${BASE}/domains/${encodeURIComponent(crawlDomainId)}`,
            query: { crawl_profile_id: crawlProfileId },
            body: patch,
        });
    },
    onSuccess(ctx, _result, event) {
        const requestPayload = event && event.payload;
        ctx.dispatch(
            CoreEvents.UI_TOAST_SHOW,
            { type: 'success', i18n_key: 'frontend:crawl_report_page.toast_domain_saved' },
            { source: 'local' },
        );
        if (requestPayload && requestPayload.crawl_profile_id) {
            const listPayload = { crawl_profile_id: requestPayload.crawl_profile_id };
            _reloadSummary(ctx, requestPayload.crawl_profile_id);
            ctx.dispatch(crawlDomainsResource.events.LIST_REQUESTED, listPayload, { source: 'local' });
        }
    },
});

export const crawlDomainDeleteOp = createAsyncOp({
    name: 'frontend/crawl_domain_delete',
    silent: true,
    restMirror: { method: 'DELETE', path: `${BASE}/domains/:crawl_domain_id` },
    request: async ({ payload }) => {
        const crawlDomainId = payload && payload.crawl_domain_id;
        const crawlProfileId = payload && payload.crawl_profile_id;
        if (!crawlDomainId) throw new Error('crawl_domain_delete: crawl_domain_id required');
        if (!crawlProfileId) throw new Error('crawl_domain_delete: crawl_profile_id required');
        return await httpRequest({
            method: 'DELETE',
            url: `${BASE}/domains/${encodeURIComponent(crawlDomainId)}`,
            query: { crawl_profile_id: crawlProfileId },
        });
    },
    onSuccess(ctx, _result, event) {
        const requestPayload = event && event.payload;
        ctx.dispatch(
            CoreEvents.UI_TOAST_SHOW,
            { type: 'success', i18n_key: 'frontend:crawl_report_page.toast_domain_deleted' },
            { source: 'local' },
        );
        if (requestPayload && requestPayload.crawl_profile_id) {
            const listPayload = { crawl_profile_id: requestPayload.crawl_profile_id };
            _reloadSummary(ctx, requestPayload.crawl_profile_id);
            ctx.dispatch(crawlDomainsResource.events.LIST_REQUESTED, listPayload, { source: 'local' });
        }
    },
});

export const crawlUrlAddOp = createAsyncOp({
    name: 'frontend/crawl_url_add',
    silent: true,
    restMirror: { method: 'POST', path: `${BASE}/domains/:crawl_domain_id/urls` },
    request: async ({ payload }) => {
        const crawlDomainId = payload && payload.crawl_domain_id;
        const crawlProfileId = payload && payload.crawl_profile_id;
        if (!crawlDomainId) throw new Error('crawl_url_add: crawl_domain_id required');
        if (!crawlProfileId) throw new Error('crawl_url_add: crawl_profile_id required');
        if (!Array.isArray(payload.urls) || payload.urls.length === 0) {
            throw new Error('crawl_url_add: urls required');
        }
        return await httpRequest({
            method: 'POST',
            url: `${BASE}/domains/${encodeURIComponent(crawlDomainId)}/urls`,
            query: { crawl_profile_id: crawlProfileId },
            body: { urls: payload.urls },
        });
    },
    onSuccess(ctx, _result, event) {
        const requestPayload = event && event.payload;
        ctx.dispatch(
            CoreEvents.UI_TOAST_SHOW,
            { type: 'success', i18n_key: 'frontend:crawl_report_page.toast_urls_added' },
            { source: 'local' },
        );
        if (requestPayload && requestPayload.crawl_profile_id) {
            const listPayload = { crawl_profile_id: requestPayload.crawl_profile_id };
            _reloadSummary(ctx, requestPayload.crawl_profile_id);
            ctx.dispatch(crawlUrlsResource.events.LIST_REQUESTED, listPayload, { source: 'local' });
        }
    },
});

export const crawlUrlRecrawlOp = createAsyncOp({
    name: 'frontend/crawl_url_recrawl',
    silent: true,
    restMirror: { method: 'POST', path: `${BASE}/urls/:crawl_url_id/recrawl` },
    request: async ({ payload }) => {
        const crawlUrlId = payload && payload.crawl_url_id;
        const crawlProfileId = payload && payload.crawl_profile_id;
        if (!crawlUrlId) throw new Error('crawl_url_recrawl: crawl_url_id required');
        if (!crawlProfileId) throw new Error('crawl_url_recrawl: crawl_profile_id required');
        return await httpRequest({
            method: 'POST',
            url: `${BASE}/urls/${encodeURIComponent(crawlUrlId)}/recrawl`,
            query: { crawl_profile_id: crawlProfileId },
            body: {},
        });
    },
    onSuccess(ctx, _result, event) {
        const requestPayload = event && event.payload;
        ctx.dispatch(
            CoreEvents.UI_TOAST_SHOW,
            { type: 'success', i18n_key: 'frontend:crawl_report_page.toast_url_recrawl' },
            { source: 'local' },
        );
        if (requestPayload && requestPayload.crawl_profile_id) {
            const listPayload = { crawl_profile_id: requestPayload.crawl_profile_id };
            _reloadSummary(ctx, requestPayload.crawl_profile_id);
            ctx.dispatch(crawlUrlsResource.events.LIST_REQUESTED, listPayload, { source: 'local' });
        }
    },
});
