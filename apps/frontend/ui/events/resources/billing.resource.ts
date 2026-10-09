/**
 * Ресурсы billing — подписка, usage, история транзакций, смена тарифа, пополнение баланса
 * (команды `frontend/billing/*`, REST-зеркало `apps/frontend/api/billing.py`).
 *
 * Состав:
 *   - billingSubscriptionLoadOp / billingUsageLoadOp / billingHistoryLoadOp: снимки, silent.
 *   - billingPlanChangeOp: успех показывает toast и перезапрашивает подписку.
 *   - billingTopupOp: успех показывает toast и уводит на `payment_url` провайдера.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { CoreEvents } from '@platform/lib/events/contract.js';

const WS_TIMEOUT_MS = 8_000;

export const billingSubscriptionLoadOp = createAsyncOp({
    name: 'frontend/billing_subscription',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'frontend/billing/subscription_requested',
    restMirror: { method: 'GET', path: '/frontend/api/billing/subscription' },
});

export const billingUsageLoadOp = createAsyncOp({
    name: 'frontend/billing_usage',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'frontend/billing/usage_requested',
    restMirror: { method: 'GET', path: '/frontend/api/billing/usage' },
});

export const billingHistoryLoadOp = createAsyncOp({
    name: 'frontend/billing_history',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'frontend/billing/payment_history_requested',
    restMirror: { method: 'GET', path: '/frontend/api/billing/history' },
});

export const billingPlanChangeOp = createAsyncOp({
    name: 'frontend/billing_plan_change',
    successToastKey: 'frontend:billing_page.toast_plan_changed',
    errorToastKey: 'frontend:billing_page.err_plan_change_failed',
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'frontend/billing/plan_change_requested',
    restMirror: { method: 'PATCH', path: '/frontend/api/billing/plan' },
    onSuccess: (ctx) => {
        ctx.dispatch(billingSubscriptionLoadOp.events.REQUESTED, null, { source: 'local' });
    },
});

export const billingTopupOp = createAsyncOp({
    name: 'frontend/billing_topup',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'frontend/billing/topup_requested',
    restMirror: { method: 'POST', path: '/frontend/api/billing/topup' },
    onSuccess: (ctx, result) => {
        ctx.dispatch(
            CoreEvents.UI_TOAST_SHOW,
            { i18n_key: 'frontend:topup_modal.toast_redirect' },
            { source: 'local' },
        );
        if (!result || typeof (result as Record<string, any>).payment_url !== 'string' || (result as Record<string, any>).payment_url === '') {
            throw new Error('billingTopupOp: payment_url required in result');
        }
        window.location.assign((result as Record<string, any>).payment_url);
    },
});
