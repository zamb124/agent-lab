import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import {
    crawlProfilesLoadOp,
    crawlSummaryLoadOp,
    crawlDomainsResource,
    crawlUrlsResource,
    crawlJobsResource,
    crawlUrlDetailOp,
    crawlQueueTickOp,
    crawlDomainRunOp,
    crawlProfilePatchOp,
    crawlDomainCreateOp,
    crawlDomainPatchOp,
    crawlDomainDeleteOp,
    crawlUrlAddOp,
    crawlUrlRecrawlOp,
} from '@platform/lib/events/resources/search-crawl-report.resource.js';
import { resetFactories } from '../../helpers/factory-fixtures.js';

beforeEach(() => {
    resetFactories();
});
afterEach(() => {
    resetFactories();
});

describe('search crawl report resource', () => {
    it('команды crawl идут по WS с REST-зеркалом владельца search', () => {
        expect(crawlProfilesLoadOp.restMirror).toEqual({
            method: 'GET',
            path: '/search/api/v1/crawl/profiles',
        });
        expect(crawlSummaryLoadOp.commandType).toBe('search/crawl_profiles/summary_requested');
        expect(crawlDomainsResource.restMirror.list).toEqual({
            method: 'GET',
            path: '/search/api/v1/crawl/domains',
        });
        expect(crawlUrlsResource.name).toBe('search/crawl_urls');
        expect(crawlJobsResource.name).toBe('search/crawl_jobs');
        expect(crawlUrlDetailOp.commandType).toBe('search/crawl_urls/get_requested');
        expect(crawlQueueTickOp.restMirror?.method).toBe('POST');
        expect(crawlDomainRunOp.commandType).toBe('search/crawl_domains/run_requested');
        expect(crawlProfilePatchOp.commandType).toBe('search/crawl_profiles/update_requested');
        expect(crawlDomainCreateOp.commandType).toBe('search/crawl_domains/create_requested');
        expect(crawlDomainPatchOp.commandType).toBe('search/crawl_domains/update_requested');
        expect(crawlDomainDeleteOp.restMirror?.method).toBe('DELETE');
        expect(crawlUrlAddOp.commandType).toBe('search/crawl_domains/urls_add_requested');
        expect(crawlUrlRecrawlOp.commandType).toBe('search/crawl_urls/recrawl_requested');
    });
});
