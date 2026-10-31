/**
 * Crawl report — admin monitoring of platform crawl pipeline.
 *
 * Владелец команд — сервис search (`search/crawl_*`, каталог SEARCH_OPERATIONS).
 * REST-зеркало: /search/api/v1/crawl/* (компания system, FGA company#admin).
 * Payload команд уходит as-is: контракт задаёт Pydantic-модель владельца.
 */

import { createAsyncOp, createResourceCollection } from '../index.js';
import { CoreEvents } from '../contract.js';
import type { EffectCtx } from '../contract.js';
import { isPlainRecord } from '../payload.js';
import type {
    CrawlDomain,
    CrawlDomainRunResponse,
    CrawlJob,
    CrawlJobQueuedResponse,
    CrawlProfileSummary,
    CrawlProfileWithIndex,
    CrawlUrl,
    CrawlUrlDetail,
    CrawlUrlListItem,
    OffsetPage_CrawlProfileWithIndex_,
    UpsertStats,
} from '../wire/search.gen.js';

type QueryObject = Record<string, unknown>;

const WS_TIMEOUT_MS = 8_000;

function requestProfile(payload: unknown): { id: string; payload: Record<string, unknown> } | null {
    if (!isPlainRecord(payload)) return null;
    const crawlProfileId = payload.crawl_profile_id;
    if (typeof crawlProfileId !== 'string' || crawlProfileId.length === 0) return null;
    return { id: crawlProfileId, payload };
}

function _requireProfileId(payload: unknown, op: string): string {
    const request = requestProfile(payload);
    if (request === null) {
        throw new Error(`${op}: crawl_profile_id required`);
    }
    return request.id;
}

function _toast(ctx: EffectCtx, key: string): void {
    ctx.dispatch(CoreEvents.UI_TOAST_SHOW, { type: 'success', i18n_key: key }, { source: 'local' });
}

export const crawlProfilesLoadOp = createAsyncOp<OffsetPage_CrawlProfileWithIndex_>({
    name: 'search/crawl_profiles_load',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'search/crawl_profiles/list_requested',
    restMirror: { method: 'GET', path: '/search/api/v1/crawl/profiles' },
});

export const crawlSummaryLoadOp = createAsyncOp<CrawlProfileSummary>({
    name: 'search/crawl_summary_load',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'search/crawl_profiles/summary_requested',
    restMirror: { method: 'GET', path: '/search/api/v1/crawl/profiles/:crawl_profile_id/summary' },
});

function _reloadSummary(ctx: EffectCtx, crawlProfileId: string): void {
    ctx.dispatch(crawlSummaryLoadOp.events.REQUESTED, { crawl_profile_id: crawlProfileId }, { source: 'local' });
}

export const crawlDomainsResource = createResourceCollection<CrawlDomain>({
    name: 'search/crawl_domains',
    baseUrl: '/search/api/v1/crawl/domains',
    idField: 'crawl_domain_id',
    operations: ['list'],
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    listPreserveItemsOnRefresh: true,
    listQuery: (payload) => {
        const q: QueryObject = { limit: 200, offset: 0, crawl_profile_id: _requireProfileId(payload, 'search/crawl_domains') };
        if (payload && payload.status) q.status = payload.status;
        return q;
    },
    restMirror: { list: { method: 'GET', path: '/search/api/v1/crawl/domains' } },
});

export const crawlUrlsResource = createResourceCollection<CrawlUrlListItem>({
    name: 'search/crawl_urls',
    baseUrl: '/search/api/v1/crawl/urls',
    idField: 'crawl_url_id',
    operations: ['list'],
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    listPreserveItemsOnRefresh: true,
    listQuery: (payload) => {
        const q: QueryObject = { limit: 200, offset: 0, crawl_profile_id: _requireProfileId(payload, 'search/crawl_urls') };
        if (payload && payload.crawl_status) q.crawl_status = payload.crawl_status;
        if (payload && payload.domain) q.domain = payload.domain;
        if (payload && payload.content_type) q.content_type = payload.content_type;
        if (payload && payload.primary_topic) q.primary_topic = payload.primary_topic;
        if (payload && payload.enriched_only === true) q.enriched_only = true;
        return q;
    },
    restMirror: { list: { method: 'GET', path: '/search/api/v1/crawl/urls' } },
});

export const crawlJobsResource = createResourceCollection<CrawlJob>({
    name: 'search/crawl_jobs',
    baseUrl: '/search/api/v1/crawl/jobs',
    idField: 'crawl_job_id',
    operations: ['list'],
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    listPreserveItemsOnRefresh: true,
    listQuery: (payload) => {
        const q: QueryObject = { limit: 100, offset: 0, crawl_profile_id: _requireProfileId(payload, 'search/crawl_jobs') };
        if (payload && payload.status) q.status = payload.status;
        return q;
    },
    restMirror: { list: { method: 'GET', path: '/search/api/v1/crawl/jobs' } },
});

export const crawlUrlDetailOp = createAsyncOp<CrawlUrlDetail>({
    name: 'search/crawl_url_detail',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'search/crawl_urls/get_requested',
    restMirror: { method: 'GET', path: '/search/api/v1/crawl/urls/:crawl_url_id' },
});

export const crawlQueueTickOp = createAsyncOp<CrawlJobQueuedResponse>({
    name: 'search/crawl_queue_tick',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'search/crawl_jobs/queue_requested',
    restMirror: { method: 'POST', path: '/search/api/v1/crawl/jobs' },
    onSuccess(ctx, _result, event) {
        _toast(ctx, 'frontend:crawl_report_page.toast_queued');
        const request = requestProfile(event.payload);
        if (request !== null) {
            _reloadSummary(ctx, request.id);
            ctx.dispatch(crawlJobsResource.events.LIST_REQUESTED, request.payload, { source: 'local' });
        }
    },
});

export const crawlDomainRunOp = createAsyncOp<CrawlDomainRunResponse>({
    name: 'search/crawl_domain_run',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'search/crawl_domains/run_requested',
    restMirror: { method: 'POST', path: '/search/api/v1/crawl/domains/:crawl_domain_id/run' },
    onSuccess(ctx, _result, event) {
        _toast(ctx, 'frontend:crawl_report_page.toast_domain_queued');
        const request = requestProfile(event.payload);
        if (request === null) {
            return;
        }
        _reloadSummary(ctx, request.id);
        ctx.dispatch(crawlJobsResource.events.LIST_REQUESTED, request.payload, { source: 'local' });
        ctx.dispatch(crawlDomainsResource.events.LIST_REQUESTED, request.payload, { source: 'local' });
    },
});

export const crawlProfilePatchOp = createAsyncOp<CrawlProfileWithIndex>({
    name: 'search/crawl_profile_patch',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'search/crawl_profiles/update_requested',
    restMirror: { method: 'PATCH', path: '/search/api/v1/crawl/profiles/:crawl_profile_id' },
    onSuccess(ctx, _result, event) {
        _toast(ctx, 'frontend:crawl_report_page.toast_profile_saved');
        ctx.dispatch(crawlProfilesLoadOp.events.REQUESTED, {}, { source: 'local' });
        const request = requestProfile(event.payload);
        if (request !== null) {
            _reloadSummary(ctx, request.id);
        }
    },
});

export const crawlDomainCreateOp = createAsyncOp<CrawlDomain>({
    name: 'search/crawl_domain_create',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'search/crawl_domains/create_requested',
    restMirror: { method: 'POST', path: '/search/api/v1/crawl/profiles/:crawl_profile_id/domains' },
    onSuccess(ctx, _result, event) {
        _toast(ctx, 'frontend:crawl_report_page.toast_domain_added');
        const request = requestProfile(event.payload);
        if (request !== null) {
            const listPayload = { crawl_profile_id: request.id };
            _reloadSummary(ctx, request.id);
            ctx.dispatch(crawlDomainsResource.events.LIST_REQUESTED, listPayload, { source: 'local' });
        }
    },
});

export const crawlDomainPatchOp = createAsyncOp<CrawlDomain>({
    name: 'search/crawl_domain_patch',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'search/crawl_domains/update_requested',
    restMirror: { method: 'PATCH', path: '/search/api/v1/crawl/domains/:crawl_domain_id' },
    onSuccess(ctx, _result, event) {
        _toast(ctx, 'frontend:crawl_report_page.toast_domain_saved');
        const request = requestProfile(event.payload);
        if (request !== null) {
            const listPayload = { crawl_profile_id: request.id };
            _reloadSummary(ctx, request.id);
            ctx.dispatch(crawlDomainsResource.events.LIST_REQUESTED, listPayload, { source: 'local' });
        }
    },
});

export const crawlDomainDeleteOp = createAsyncOp<null>({
    name: 'search/crawl_domain_delete',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'search/crawl_domains/remove_requested',
    restMirror: { method: 'DELETE', path: '/search/api/v1/crawl/domains/:crawl_domain_id' },
    onSuccess(ctx, _result, event) {
        _toast(ctx, 'frontend:crawl_report_page.toast_domain_deleted');
        const request = requestProfile(event.payload);
        if (request !== null) {
            const listPayload = { crawl_profile_id: request.id };
            _reloadSummary(ctx, request.id);
            ctx.dispatch(crawlDomainsResource.events.LIST_REQUESTED, listPayload, { source: 'local' });
        }
    },
});

export const crawlUrlAddOp = createAsyncOp<UpsertStats>({
    name: 'search/crawl_url_add',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'search/crawl_domains/urls_add_requested',
    restMirror: { method: 'POST', path: '/search/api/v1/crawl/domains/:crawl_domain_id/urls' },
    onSuccess(ctx, _result, event) {
        _toast(ctx, 'frontend:crawl_report_page.toast_urls_added');
        const request = requestProfile(event.payload);
        if (request !== null) {
            const listPayload = { crawl_profile_id: request.id };
            _reloadSummary(ctx, request.id);
            ctx.dispatch(crawlUrlsResource.events.LIST_REQUESTED, listPayload, { source: 'local' });
        }
    },
});

export const crawlUrlRecrawlOp = createAsyncOp<CrawlUrl>({
    name: 'search/crawl_url_recrawl',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'search/crawl_urls/recrawl_requested',
    restMirror: { method: 'POST', path: '/search/api/v1/crawl/urls/:crawl_url_id/recrawl' },
    onSuccess(ctx, _result, event) {
        _toast(ctx, 'frontend:crawl_report_page.toast_url_recrawl');
        const request = requestProfile(event.payload);
        if (request !== null) {
            const listPayload = { crawl_profile_id: request.id };
            _reloadSummary(ctx, request.id);
            ctx.dispatch(crawlUrlsResource.events.LIST_REQUESTED, listPayload, { source: 'local' });
        }
    },
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'search/crawl_profiles_load': typeof crawlProfilesLoadOp;
        'search/crawl_summary_load': typeof crawlSummaryLoadOp;
        'search/crawl_domains': typeof crawlDomainsResource;
        'search/crawl_urls': typeof crawlUrlsResource;
        'search/crawl_jobs': typeof crawlJobsResource;
        'search/crawl_url_detail': typeof crawlUrlDetailOp;
        'search/crawl_queue_tick': typeof crawlQueueTickOp;
        'search/crawl_domain_run': typeof crawlDomainRunOp;
        'search/crawl_profile_patch': typeof crawlProfilePatchOp;
        'search/crawl_domain_create': typeof crawlDomainCreateOp;
        'search/crawl_domain_patch': typeof crawlDomainPatchOp;
        'search/crawl_domain_delete': typeof crawlDomainDeleteOp;
        'search/crawl_url_add': typeof crawlUrlAddOp;
        'search/crawl_url_recrawl': typeof crawlUrlRecrawlOp;
    }
}
