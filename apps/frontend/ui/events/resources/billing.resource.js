/**
 * Ресурсы billing — подписка, usage, история транзакций, смена тарифа,
 * пополнение баланса. Все операции через прокси `/frontend/api/billing/*`.
 *
 * Состав:
 *   - billingSubscriptionLoadOp: GET /subscription, silent.
 *   - billingUsageLoadOp:        GET /usage, silent.
 *   - billingHistoryLoadOp:      GET /history, silent (lastResult.items).
 *   - billingPlanChangeOp:       PATCH /plan, успех показывает toast и
 *     перезагружает subscription.
 *   - billingTopupOp:            POST /topup, успех показывает toast и
 *     редиректит на payment_url через router.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';
import { CoreEvents } from '@platform/lib/events/contract.js';

const BASE = '/frontend/api/billing';

export const billingSubscriptionLoadOp = createAsyncOp({
    name: 'frontend/billing_subscription',
    silent: true,
    restMirror: { method: 'GET', path: '/frontend/api/billing/subscription' },
    request: async () => await httpRequest({
        method: 'GET',
        url: `${BASE}/subscription`,
    }),
});

export const billingUsageLoadOp = createAsyncOp({
    name: 'frontend/billing_usage',
    silent: true,
    restMirror: { method: 'GET', path: '/frontend/api/billing/usage' },
    request: async () => await httpRequest({
        method: 'GET',
        url: `${BASE}/usage`,
    }),
});

export const billingHistoryLoadOp = createAsyncOp({
    name: 'frontend/billing_history',
    silent: true,
    restMirror: { method: 'GET', path: '/frontend/api/billing/history' },
    request: async () => {
        const data = await httpRequest({
            method: 'GET',
            url: `${BASE}/history`,
        });
        return { items: Array.isArray(data.payments) ? data.payments : [] };
    },
});

export const billingPlanChangeOp = createAsyncOp({
    name: 'frontend/billing_plan_change',
    successToastKey: 'frontend:billing_page.toast_plan_changed',
    errorToastKey: 'frontend:billing_page.err_plan_change_failed',
    restMirror: { method: 'PATCH', path: '/frontend/api/billing/plan' },
    request: async ({ payload }) => {
        const plan = payload && payload.plan;
        if (!plan) throw new Error('billingPlanChangeOp: plan required');
        await httpRequest({
            method: 'PATCH',
            url: `${BASE}/plan`,
            body: { plan },
        });
        return { plan };
    },
    onSuccess: (ctx) => {
        ctx.dispatch(billingSubscriptionLoadOp.events.REQUESTED, null, { source: 'local' });
    },
});

export const billingTopupOp = createAsyncOp({
    name: 'frontend/billing_topup',
    silent: true,
    restMirror: { method: 'POST', path: '/frontend/api/billing/topup' },
    request: async ({ payload }) => {
        const amount = payload && payload.amount;
        if (!amount) throw new Error('billingTopupOp: amount required');
        return await httpRequest({
            method: 'POST',
            url: `${BASE}/topup`,
            body: { amount },
        });
    },
    onSuccess: (ctx, result) => {
        ctx.dispatch(
            CoreEvents.UI_TOAST_SHOW,
            { type: 'info', i18n_key: 'frontend:topup_modal.toast_redirect' },
            { source: 'local' },
        );
        if (result && result.payment_url) {
            window.location.assign(result.payment_url);
        }
    },
});
