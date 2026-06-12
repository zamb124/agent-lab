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
    listQuery: (payload) => {
        const q = { limit: 200, offset: 0 };
        if (payload && payload.crawl_profile_id) q.crawl_profile_id = payload.crawl_profile_id;
        if (payload && payload.status) q.status = payload.status;
        return q;
    },
});

export const crawlUrlsResource = createResourceCollection({
    name: 'frontend/crawl_urls',
    baseUrl: `${BASE}/urls`,
    idField: 'crawl_url_id',
    operations: ['list'],
    listQuery: (payload) => {
        const q = { limit: 200, offset: 0 };
        if (payload && payload.crawl_profile_id) q.crawl_profile_id = payload.crawl_profile_id;
        if (payload && payload.crawl_status) q.crawl_status = payload.crawl_status;
        if (payload && payload.domain) q.domain = payload.domain;
        return q;
    },
});

export const crawlJobsResource = createResourceCollection({
    name: 'frontend/crawl_jobs',
    baseUrl: `${BASE}/jobs`,
    idField: 'crawl_job_id',
    operations: ['list'],
    listQuery: (payload) => {
        const q = { limit: 100, offset: 0 };
        if (payload && payload.crawl_profile_id) q.crawl_profile_id = payload.crawl_profile_id;
        if (payload && payload.status) q.status = payload.status;
        return q;
    },
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
    onSuccess(ctx, _payload, _result, requestPayload) {
        ctx.dispatch(
            CoreEvents.UI_TOAST_SHOW,
            { type: 'success', i18n_key: 'frontend:crawl_report_page.toast_queued' },
            { source: 'local' },
        );
        if (requestPayload && requestPayload.crawl_profile_id) {
            _reloadSummary(ctx, requestPayload.crawl_profile_id);
        }
        ctx.dispatch(crawlJobsResource.events.LIST_REQUESTED, requestPayload, { source: 'local' });
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
    onSuccess(ctx, _payload, _result, requestPayload) {
        ctx.dispatch(
            CoreEvents.UI_TOAST_SHOW,
            { type: 'success', i18n_key: 'frontend:crawl_report_page.toast_domain_queued' },
            { source: 'local' },
        );
        if (requestPayload && requestPayload.crawl_profile_id) {
            _reloadSummary(ctx, requestPayload.crawl_profile_id);
        }
        ctx.dispatch(crawlJobsResource.events.LIST_REQUESTED, requestPayload, { source: 'local' });
        ctx.dispatch(crawlDomainsResource.events.LIST_REQUESTED, requestPayload, { source: 'local' });
    },
});
