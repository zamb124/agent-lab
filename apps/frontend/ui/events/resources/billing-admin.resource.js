/**
 * Admin billing resources — компании, цены, settlement rules, usage report,
 * системный доступ к компаниям. Только для активной компании system.
 *
 * API:
 *   GET  /api/platform-billing/companies-billing-overview?limit=&offset=
 *   GET  /api/platform-billing/company-resolve?q=
 *   GET  /api/platform-billing/facets/billing-companies?q=&limit=
 *   GET  /api/platform-billing/facets/usage-types?q=&limit=
 *   GET  /api/platform-billing/facets/resource-names?q=&limit=
 *   GET  /api/platform-billing/prices
 *   PUT  /api/platform-billing/prices
 *   GET  /api/platform-billing/prices/company/{company_id}
 *   PUT  /api/platform-billing/prices/company/{company_id}
 *   GET  /api/platform-billing/settlement-rules/{company_id}
 *   PUT  /api/platform-billing/settlement-rules/{company_id}
 *   GET  /api/platform-billing/default-settlement-rules
 *   GET  /api/platform-billing/usage-report?...
 *   POST   /api/companies/{company_id}/system-access
 *   DELETE /api/companies/{company_id}/system-access
 *
 * Для эндпоинтов с offset/limit используется createAsyncOp с extraInitial.offset
 * и собственный extraReducer для пагинации.
 */

import { createAsyncOp, createFacets } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';
import { CoreEvents } from '@platform/lib/events/contract.js';

const BASE_BILLING = '/frontend/api/platform-billing';
const BASE_COMPANIES = '/frontend/api/companies';

function _toastError(ctx, key) {
    ctx.dispatch(
        CoreEvents.UI_TOAST_SHOW,
        { type: 'error', i18n_key: key },
        { source: 'local' },
    );
}

function _toastSuccess(ctx, key) {
    ctx.dispatch(
        CoreEvents.UI_TOAST_SHOW,
        { type: 'success', i18n_key: key },
        { source: 'local' },
    );
}

const PAGE_SIZE = 50;

export const companiesOverviewLoadOp = createAsyncOp({
    name: 'frontend/admin_billing_companies',
    silent: true,
    request: async ({ payload }) => {
        const offset = (payload && payload.offset) || 0;
        const append = !!(payload && payload.append);
        const data = await httpRequest({
            method: 'GET',
            url: `${BASE_BILLING}/companies-billing-overview`,
            query: { limit: PAGE_SIZE, offset },
        });
        return { items: data.items || [], has_more: !!data.has_more, offset, append };
    },
    extraInitial: {
        items: [],
        offset: 0,
        hasMore: false,
        terminal: null,
    },
    actions: {
        reset: 'reset',
    },
    extraReducer: (state, event, events) => {
        if (event.type === events.SUCCEEDED) {
            const r = (event.payload && event.payload.result) || {};
            const next = r.append ? [...(state.items || []), ...r.items] : r.items;
            return {
                ...state,
                items: next,
                offset: (r.offset || 0) + (r.items ? r.items.length : 0),
                hasMore: !!r.has_more,
                terminal: null,
            };
        }
        if (event.type === events.FAILED) {
            const status = event.payload && event.payload.status;
            if (status === 403) return { ...state, terminal: 'forbidden', items: [], hasMore: false };
            if (status === 503) return { ...state, terminal: 'unavailable', items: [], hasMore: false };
            return state;
        }
        if (event.type === events.RESET) {
            return { ...state, items: [], offset: 0, hasMore: false, terminal: null };
        }
        return state;
    },
    onFailure: (ctx, err) => {
        if (err.status === 403 || err.status === 503) return;
        _toastError(ctx, 'frontend:platform_billing_page.companies_load_failed');
    },
});

export const companyResolveOp = createAsyncOp({
    name: 'frontend/admin_billing_company_resolve',
    silent: true,
    request: async ({ payload }) => {
        const q = payload && payload.q;
        if (!q) throw new Error('company_resolve: q required');
        return await httpRequest({
            method: 'GET',
            url: `${BASE_BILLING}/company-resolve`,
            query: { q },
        });
    },
    onFailure: (ctx) => {
        _toastError(ctx, 'frontend:platform_billing_page.billing_company_resolve_failed');
    },
});

export const pricesGlobalLoadOp = createAsyncOp({
    name: 'frontend/admin_billing_prices_global_load',
    silent: true,
    request: async () => await httpRequest({
        method: 'GET',
        url: `${BASE_BILLING}/prices`,
    }),
    onFailure: (ctx) => {
        _toastError(ctx, 'frontend:platform_billing_page.prices_load_failed');
    },
});

export const pricesGlobalUpdateOp = createAsyncOp({
    name: 'frontend/admin_billing_prices_global_update',
    successToastKey: 'frontend:platform_billing_page.saved_ok',
    errorToastKey: 'frontend:platform_billing_page.prices_save_failed',
    request: async ({ payload }) => await httpRequest({
        method: 'PUT',
        url: `${BASE_BILLING}/prices`,
        body: payload || {},
    }),
    onSuccess: (ctx) => {
        ctx.dispatch(pricesGlobalLoadOp.events.REQUESTED, null, { source: 'local' });
    },
});

export const companyPricesLoadOp = createAsyncOp({
    name: 'frontend/admin_billing_company_prices_load',
    silent: true,
    request: async ({ payload }) => {
        const id = payload && payload.company_id;
        if (!id) throw new Error('company_prices_load: company_id required');
        return await httpRequest({
            method: 'GET',
            url: `${BASE_BILLING}/prices/company/${encodeURIComponent(id)}`,
        });
    },
    onFailure: (ctx) => {
        _toastError(ctx, 'frontend:platform_billing_page.prices_load_failed');
    },
});

export const companyPricesUpdateOp = createAsyncOp({
    name: 'frontend/admin_billing_company_prices_update',
    successToastKey: 'frontend:platform_billing_page.saved_ok',
    errorToastKey: 'frontend:platform_billing_page.prices_save_failed',
    request: async ({ payload }) => {
        const id = payload && payload.company_id;
        if (!id) throw new Error('company_prices_update: company_id required');
        return await httpRequest({
            method: 'PUT',
            url: `${BASE_BILLING}/prices/company/${encodeURIComponent(id)}`,
            body: payload.body || {},
        });
    },
    onSuccess: (ctx, _result, event) => {
        const id = event.payload && event.payload.company_id;
        ctx.dispatch(companyPricesLoadOp.events.REQUESTED, { company_id: id }, { source: 'local' });
    },
});

export const settlementRulesLoadOp = createAsyncOp({
    name: 'frontend/admin_billing_rules_load',
    silent: true,
    request: async ({ payload }) => {
        const id = payload && payload.company_id;
        if (!id) throw new Error('settlement_rules_load: company_id required');
        return await httpRequest({
            method: 'GET',
            url: `${BASE_BILLING}/settlement-rules/${encodeURIComponent(id)}`,
        });
    },
    onFailure: (ctx) => {
        _toastError(ctx, 'frontend:platform_billing_page.rules_load_failed');
    },
});

export const settlementRulesUpdateOp = createAsyncOp({
    name: 'frontend/admin_billing_rules_update',
    successToastKey: 'frontend:platform_billing_page.saved_ok',
    errorToastKey: 'frontend:platform_billing_page.rules_save_failed',
    request: async ({ payload }) => {
        const id = payload && payload.company_id;
        if (!id) throw new Error('settlement_rules_update: company_id required');
        return await httpRequest({
            method: 'PUT',
            url: `${BASE_BILLING}/settlement-rules/${encodeURIComponent(id)}`,
            body: payload.body || {},
        });
    },
    onSuccess: (ctx, _result, event) => {
        const id = event.payload && event.payload.company_id;
        ctx.dispatch(settlementRulesLoadOp.events.REQUESTED, { company_id: id }, { source: 'local' });
    },
});

export const defaultSettlementRulesLoadOp = createAsyncOp({
    name: 'frontend/admin_billing_rules_default_load',
    silent: true,
    request: async () => await httpRequest({
        method: 'GET',
        url: `${BASE_BILLING}/default-settlement-rules`,
    }),
    onFailure: (ctx) => {
        _toastError(ctx, 'frontend:platform_billing_page.rules_template_invalid');
    },
});

const USAGE_REPORT_LIMIT = 200;

export const usageReportLoadOp = createAsyncOp({
    name: 'frontend/admin_billing_usage_load',
    silent: true,
    request: async ({ payload }) => {
        const filters = (payload && payload.filters) || {};
        const offset = (payload && payload.offset) || 0;
        const limit = (payload && payload.limit) || USAGE_REPORT_LIMIT;
        const query = { limit, offset };
        if (filters.company_id)    query.company_id = filters.company_id;
        if (filters.usage_type)    query.usage_type = filters.usage_type;
        if (filters.resource_name) query.resource_name = filters.resource_name;
        if (filters.from_time)     query.from = filters.from_time;
        if (filters.to_time)       query.to = filters.to_time;
        const data = await httpRequest({
            method: 'GET',
            url: `${BASE_BILLING}/usage-report`,
            query,
        });
        return { items: data.items || [], offset, limit, filters };
    },
    extraInitial: {
        items: [],
        offset: 0,
        limit: USAGE_REPORT_LIMIT,
        filters: {},
    },
    extraReducer: (state, event, events) => {
        if (event.type === events.SUCCEEDED) {
            const r = (event.payload && event.payload.result) || {};
            return {
                ...state,
                items: r.items || [],
                offset: r.offset || 0,
                limit: r.limit || USAGE_REPORT_LIMIT,
                filters: r.filters || {},
            };
        }
        return state;
    },
    onFailure: (ctx) => {
        _toastError(ctx, 'frontend:platform_billing_page.usage_load_failed');
    },
});

export const billingAdminFacets = createFacets({
    name: 'frontend/admin_billing_facets',
    baseUrl: `${BASE_BILLING}/facets`,
    facets: {
        companies:      'billing-companies',
        usage_types:    'usage-types',
        resource_names: 'resource-names',
    },
    debounceMs: 200,
    minQueryLength: 2,
    pageSize: 20,
});

export const systemAccessEnterOp = createAsyncOp({
    name: 'frontend/admin_system_access_enter',
    successToastKey: 'frontend:platform_billing_page.saved_ok',
    errorToastKey: 'frontend:platform_billing_page.system_access_user_context_invalid',
    request: async ({ payload }) => {
        const id = payload && payload.company_id;
        const role = payload && payload.role;
        if (!id) throw new Error('system_access_enter: company_id required');
        if (!role) throw new Error('system_access_enter: role required');
        return await httpRequest({
            method: 'POST',
            url: `${BASE_COMPANIES}/${encodeURIComponent(id)}/system-access`,
            body: { role },
        });
    },
    onSuccess: (ctx) => {
        ctx.dispatch(companiesOverviewLoadOp.events.REQUESTED, { offset: 0, append: false }, { source: 'local' });
    },
});

export const systemAccessLeaveOp = createAsyncOp({
    name: 'frontend/admin_system_access_leave',
    successToastKey: 'frontend:platform_billing_page.system_access_leave_success',
    errorToastKey: 'frontend:platform_billing_page.system_access_user_context_invalid',
    request: async ({ payload }) => {
        const id = payload && payload.company_id;
        if (!id) throw new Error('system_access_leave: company_id required');
        return await httpRequest({
            method: 'DELETE',
            url: `${BASE_COMPANIES}/${encodeURIComponent(id)}/system-access`,
        });
    },
    onSuccess: (ctx) => {
        ctx.dispatch(companiesOverviewLoadOp.events.REQUESTED, { offset: 0, append: false }, { source: 'local' });
    },
});
