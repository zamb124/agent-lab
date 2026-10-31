import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import {
    searchProvidersLoadOp,
    searchProviderPutOp,
    searchProviderOrderPutOp,
    searchProviderDeleteOp,
} from '@platform/lib/events/resources/search-providers.resource.js';
import { resetFactories } from '../../helpers/factory-fixtures.js';

beforeEach(() => {
    resetFactories();
});
afterEach(() => {
    resetFactories();
});

describe('search providers resource', () => {
    it('команды search/providers идут по WS с REST-зеркалом', () => {
        expect(searchProvidersLoadOp.commandType).toBe('search/providers/list_requested');
        expect(searchProvidersLoadOp.restMirror).toEqual({
            method: 'GET',
            path: '/search/api/v1/providers/company',
        });
        expect(searchProviderPutOp.restMirror).toEqual({
            method: 'PUT',
            path: '/search/api/v1/providers/company/:provider_id',
        });
        expect(searchProviderOrderPutOp.commandType).toBe('search/providers/order_update_requested');
        expect(searchProviderDeleteOp.restMirror).toEqual({
            method: 'DELETE',
            path: '/search/api/v1/providers/company/:provider_id',
        });
    });
});
