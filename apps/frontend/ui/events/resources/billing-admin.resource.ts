/**
 * Ресурсы admin billing — компании, цены, settlement rules, usage report, системный доступ
 * к компаниям. Команды `frontend/platform_billing/*` и `frontend/companies/system_access_*`
 * (REST-зеркало `apps/frontend/api/platform_billing.py`, `companies.py`); только компания system.
 *
 * Пагинация overview/usage — `OffsetPage`: reducer берёт offset из `lastRequest.payload`,
 * `hasMore = offset + items.length < total`; дозагрузка overview — запрос с `offset > 0`.
 */

import { createAsyncOp, createFacets } from '@platform/lib/events/index.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
import type { PlatformEvent } from '@platform/lib/events/contract.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';

const BASE_BILLING = '/frontend/api/platform-billing';
const WS_TIMEOUT_MS = 15_000;

const _COMPANY_OVERVIEW_REQUIRED_KEYS = Object.freeze([
    'company_id',
    'name',
    'status',
    'tariff_plan',
    'balance',
    'monthly_budget',
    'current_month_spent',
]);

function _assertCompanyOverviewItemsShape(items: unknown[]) {
    for (let i = 0; i < items.length; i += 1) {
        const row = items[i];
        if (!isPlainRecord(row)) {
            throw new Error(`companies_billing_overview: items[${i}] must be an object`);
        }
        for (const k of _COMPANY_OVERVIEW_REQUIRED_KEYS) {
            if (!Object.prototype.hasOwnProperty.call(row, k)) {
                throw new Error(`companies_billing_overview: items[${i}] missing "${k}"`);
            }
        }
    }
}

function _toastError(ctx: Record<string, unknown>, key: string) {
    ctx.dispatch(
        CoreEvents.UI_TOAST_SHOW,
        { i18n_key: key },
        { source: 'local' },
    );
}

function _offsetPage(event: PlatformEvent) {
    if (!isPlainRecord(event.payload)) {
        throw new Error(`${event.type}: OffsetPage { items, total, limit, offset } required`);
    }
    const page = event.payload.result;
    if (!isPlainRecord(page)) {
        throw new Error(`${event.type}: OffsetPage { items, total, limit, offset } required`);
    }
    const items = page.items;
    const total = page.total;
    const offset = page.offset;
    const limit = page.limit;
    if (!Array.isArray(items) || typeof total !== 'number' || typeof offset !== 'number') {
        throw new Error(`${event.type}: OffsetPage { items, total, limit, offset } required`);
    }
    return {
        items,
        total,
        offset,
        limit: typeof limit === 'number' ? limit : undefined,
    };
}

function _companyId(payload: unknown): string {
    if (!isPlainRecord(payload)) {
        throw new Error('billing-admin: payload.company_id required');
    }
    const id = payload.company_id;
    if (typeof id !== 'string' || id.length === 0) {
        throw new Error('billing-admin: payload.company_id required');
    }
    return id;
}

function _terminalOf(failurePayload: any) {
    const status = failurePayload && failurePayload.status;
    const code = failurePayload && failurePayload.code;
    if (status === 403 || code === 'forbidden') return 'forbidden';
    if (status === 503 || code === 'unavailable') return 'unavailable';
    return null;
}

const PAGE_SIZE = 50;

export const companiesOverviewLoadOp = createAsyncOp({
    name: 'frontend/admin_billing_companies',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'frontend/platform_billing/companies_overview_requested',
    restMirror: { method: 'GET', path: '/frontend/api/platform-billing/companies-billing-overview' },
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
            const page = _offsetPage(event);
            _assertCompanyOverviewItemsShape(page.items);
            const previous = state.items;
            if (page.offset > 0 && !Array.isArray(previous)) {
                throw new Error('companies_billing_overview: items must be an array');
            }
            const items = page.offset > 0 && Array.isArray(previous)
                ? [...previous, ...page.items]
                : page.items;
            return {
                ...state,
                items,
                offset: page.offset + page.items.length,
                hasMore: page.offset + page.items.length < page.total,
                terminal: null,
            };
        }
        if (event.type === events.FAILED) {
            const terminal = _terminalOf(event.payload);
            if (terminal) return { ...state, terminal, items: [], hasMore: false };
            return state;
        }
        if (event.type === events.RESET) {
            return { ...state, items: [], offset: 0, hasMore: false, terminal: null };
        }
        return state;
    },
    onFailure: (ctx, err) => {
        if (_terminalOf(err)) return;
        _toastError(ctx, 'frontend:platform_billing_page.companies_load_failed');
    },
});

export const companyResolveOp = createAsyncOp({
    name: 'frontend/admin_billing_company_resolve',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'frontend/platform_billing/company_resolve_requested',
    restMirror: { method: 'GET', path: '/frontend/api/platform-billing/company-resolve' },
    onFailure: (ctx) => {
        _toastError(ctx, 'frontend:platform_billing_page.billing_company_resolve_failed');
    },
});

export const pricesGlobalLoadOp = createAsyncOp({
    name: 'frontend/admin_billing_prices_global_load',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'frontend/platform_billing/prices_requested',
    restMirror: { method: 'GET', path: '/frontend/api/platform-billing/prices' },
    onFailure: (ctx) => {
        _toastError(ctx, 'frontend:platform_billing_page.prices_load_failed');
    },
});

export const pricesGlobalUpdateOp = createAsyncOp({
    name: 'frontend/admin_billing_prices_global_update',
    successToastKey: 'frontend:platform_billing_page.saved_ok',
    errorToastKey: 'frontend:platform_billing_page.prices_save_failed',
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'frontend/platform_billing/prices_update_requested',
    restMirror: { method: 'PUT', path: '/frontend/api/platform-billing/prices' },
    onSuccess: (ctx) => {
        ctx.dispatch(pricesGlobalLoadOp.events.REQUESTED, null, { source: 'local' });
    },
});

export const companyPricesLoadOp = createAsyncOp({
    name: 'frontend/admin_billing_company_prices_load',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'frontend/platform_billing/company_prices_requested',
    restMirror: { method: 'GET', path: '/frontend/api/platform-billing/prices/company/:company_id' },
    onFailure: (ctx) => {
        _toastError(ctx, 'frontend:platform_billing_page.prices_load_failed');
    },
});

export const companyPricesUpdateOp = createAsyncOp({
    name: 'frontend/admin_billing_company_prices_update',
    successToastKey: 'frontend:platform_billing_page.saved_ok',
    errorToastKey: 'frontend:platform_billing_page.prices_save_failed',
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'frontend/platform_billing/company_prices_update_requested',
    restMirror: { method: 'PUT', path: '/frontend/api/platform-billing/prices/company/:company_id' },
    onSuccess: (ctx, _result, event) => {
        const id = _companyId(event.payload);
        ctx.dispatch(companyPricesLoadOp.events.REQUESTED, { company_id: id }, { source: 'local' });
    },
});

export const settlementRulesLoadOp = createAsyncOp({
    name: 'frontend/admin_billing_rules_load',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'frontend/platform_billing/settlement_rules_requested',
    restMirror: { method: 'GET', path: '/frontend/api/platform-billing/settlement-rules/:company_id' },
    onFailure: (ctx) => {
        _toastError(ctx, 'frontend:platform_billing_page.rules_load_failed');
    },
});

export const settlementRulesUpdateOp = createAsyncOp({
    name: 'frontend/admin_billing_rules_update',
    successToastKey: 'frontend:platform_billing_page.saved_ok',
    errorToastKey: 'frontend:platform_billing_page.rules_save_failed',
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'frontend/platform_billing/settlement_rules_update_requested',
    restMirror: { method: 'PUT', path: '/frontend/api/platform-billing/settlement-rules/:company_id' },
    onSuccess: (ctx, _result, event) => {
        const id = _companyId(event.payload);
        ctx.dispatch(settlementRulesLoadOp.events.REQUESTED, { company_id: id }, { source: 'local' });
    },
});

export const defaultSettlementRulesLoadOp = createAsyncOp({
    name: 'frontend/admin_billing_rules_default_load',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'frontend/platform_billing/default_settlement_rules_requested',
    restMirror: { method: 'GET', path: '/frontend/api/platform-billing/default-settlement-rules' },
    onFailure: (ctx) => {
        _toastError(ctx, 'frontend:platform_billing_page.rules_template_invalid');
    },
});

const USAGE_REPORT_LIMIT = 200;

export const usageReportLoadOp = createAsyncOp({
    name: 'frontend/admin_billing_usage_load',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 30_000,
    commandType: 'frontend/platform_billing/usage_report_requested',
    restMirror: { method: 'GET', path: '/frontend/api/platform-billing/usage-report' },
    extraInitial: {
        items: [],
        offset: 0,
        limit: USAGE_REPORT_LIMIT,
    },
    extraReducer: (state, event, events) => {
        if (event.type === events.SUCCEEDED) {
            const page = _offsetPage(event);
            return {
                ...state,
                items: page.items,
                offset: page.offset,
                limit: typeof page.limit === 'number' ? page.limit : USAGE_REPORT_LIMIT,
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

export const balanceGrantOp = createAsyncOp({
    name: 'frontend/admin_billing_balance_grant',
    successToastKey: 'frontend:platform_billing_page.balance_grant_toast_ok',
    errorToastKey: 'frontend:platform_billing_page.balance_grant_toast_error',
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'frontend/platform_billing/balance_grant_requested',
    restMirror: { method: 'POST', path: '/frontend/api/platform-billing/balance-grant' },
    onSuccess: (ctx) => {
        ctx.dispatch(companiesOverviewLoadOp.events.REQUESTED, { limit: PAGE_SIZE, offset: 0 }, { source: 'local' });
    },
});

export const systemAccessEnterOp = createAsyncOp({
    name: 'frontend/admin_system_access_enter',
    successToastKey: 'frontend:platform_billing_page.saved_ok',
    errorToastKey: 'frontend:platform_billing_page.system_access_user_context_invalid',
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'frontend/companies/system_access_grant_requested',
    restMirror: { method: 'POST', path: '/frontend/api/companies/:company_id/system-access' },
    onSuccess: (ctx) => {
        ctx.dispatch(companiesOverviewLoadOp.events.REQUESTED, { limit: PAGE_SIZE, offset: 0 }, { source: 'local' });
    },
});

export const systemAccessLeaveOp = createAsyncOp({
    name: 'frontend/admin_system_access_leave',
    successToastKey: 'frontend:platform_billing_page.system_access_leave_success',
    errorToastKey: 'frontend:platform_billing_page.system_access_user_context_invalid',
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'frontend/companies/system_access_revoke_requested',
    restMirror: { method: 'DELETE', path: '/frontend/api/companies/:company_id/system-access' },
    onSuccess: (ctx) => {
        ctx.dispatch(companiesOverviewLoadOp.events.REQUESTED, { limit: PAGE_SIZE, offset: 0 }, { source: 'local' });
    },
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'frontend/admin_billing_companies': typeof companiesOverviewLoadOp;
        'frontend/admin_billing_company_resolve': typeof companyResolveOp;
        'frontend/admin_billing_prices_global_load': typeof pricesGlobalLoadOp;
        'frontend/admin_billing_prices_global_update': typeof pricesGlobalUpdateOp;
        'frontend/admin_billing_company_prices_load': typeof companyPricesLoadOp;
        'frontend/admin_billing_company_prices_update': typeof companyPricesUpdateOp;
        'frontend/admin_billing_rules_load': typeof settlementRulesLoadOp;
        'frontend/admin_billing_rules_update': typeof settlementRulesUpdateOp;
        'frontend/admin_billing_rules_default_load': typeof defaultSettlementRulesLoadOp;
        'frontend/admin_billing_usage_load': typeof usageReportLoadOp;
        'frontend/admin_billing_facets': typeof billingAdminFacets;
        'frontend/admin_billing_balance_grant': typeof balanceGrantOp;
        'frontend/admin_system_access_enter': typeof systemAccessEnterOp;
        'frontend/admin_system_access_leave': typeof systemAccessLeaveOp;
    }
}
