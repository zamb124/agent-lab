/**
 * Billing page — подписка, usage и история транзакций.
 *
 * Источники (apps/frontend/api/billing.py):
 *   - subscription: BillingSubscription (plan, balance, monthly_budget, current_month_spent, billing_period_start)
 *   - usage:        BillingUsage (total_cost, total_calls, by_resource, by_user)
 *   - history:      list of TransactionResponse (created_at, amount, status, payment_provider)
 *
 * Действия:
 *   - кнопка «Top up» открывает FrontendTopupModal
 *   - кнопки «Change plan» (free/basic/premium/enterprise) — billingPlanChangeOp
 */
import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/glass-card.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-user-chip.js';
import { FrontendTopupModal } from '../../modals/topup-modal.js';

const PLAN_KEYS = Object.freeze(['free', 'basic', 'premium', 'enterprise']);

function _planTranslationKey(plan) {
    return `tariff_plans.${(plan || 'free').toLowerCase()}.name`;
}

function _formatCurrency(value) {
    if (value === undefined || value === null) return '—';
    const n = Number(value);
    if (Number.isNaN(n)) return String(value);
    return n.toLocaleString('ru-RU', { maximumFractionDigits: 2 });
}

function _percent(spent, budget) {
    if (!budget || budget <= 0) return null;
    return Math.min(100, Math.round((Number(spent) / Number(budget)) * 100));
}

export class FrontendBillingPage extends PlatformPage {
    static i18nNamespace = 'billing';

    static styles = [
        PlatformPage.styles,
        css`
            :host { display: block; }
            .grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
                gap: var(--space-4);
                margin: var(--space-4) 0;
            }
            .stat { display: flex; flex-direction: column; gap: var(--space-2); padding: var(--space-4); }
            .stat-label { font-size: var(--text-xs); color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.05em; }
            .stat-value { font-size: var(--text-2xl); color: var(--text-primary); font-weight: var(--font-semibold); }
            .stat-meta { font-size: var(--text-xs); color: var(--text-tertiary); }

            .progress {
                width: 100%; height: 6px;
                background: var(--glass-solid-medium);
                border-radius: var(--radius-full);
                overflow: hidden;
            }
            .progress > div {
                height: 100%;
                background: var(--accent);
                transition: width 0.3s ease;
            }
            .progress.over > div { background: var(--error); }

            .btn {
                padding: var(--space-2) var(--space-4);
                background: var(--accent); color: white; border: none;
                border-radius: var(--radius-md); cursor: pointer;
                font-size: var(--text-sm); font-weight: var(--font-medium);
            }
            .btn:hover { filter: brightness(1.1); }
            .btn:disabled { opacity: 0.5; cursor: not-allowed; }
            .btn-ghost { background: transparent; color: var(--text-secondary); border: 1px solid var(--glass-border-subtle); }
            .btn-ghost[data-active="true"] {
                color: white; background: var(--accent); border-color: var(--accent);
            }

            .plan-row { display: flex; gap: var(--space-2); flex-wrap: wrap; }

            section { margin-top: var(--space-6); }
            section h3 {
                color: var(--text-primary);
                font-size: var(--text-lg);
                margin: 0 0 var(--space-3) 0;
            }

            table { width: 100%; border-collapse: collapse; }
            th, td {
                padding: var(--space-3);
                border-bottom: 1px solid var(--glass-border-subtle);
                text-align: left;
                font-size: var(--text-sm);
            }
            th {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                text-transform: uppercase; letter-spacing: 0.05em;
            }
            td { color: var(--text-primary); }
            td.num { text-align: right; font-variant-numeric: tabular-nums; }

            .status-tag {
                padding: 2px 8px;
                border-radius: var(--radius-full);
                font-size: var(--text-xs);
            }
            .status-tag.success, .status-tag.completed { background: var(--success); color: white; }
            .status-tag.pending { background: var(--accent); color: white; }
            .status-tag.failed, .status-tag.error { background: var(--error); color: white; }
            .status-tag.cancelled { background: var(--text-tertiary); color: white; }
            .status-tag.refunded { background: var(--warning); color: white; }

            .empty {
                padding: var(--space-6);
                text-align: center; color: var(--text-tertiary);
                background: var(--glass-solid-subtle);
                border: 1px dashed var(--glass-border-subtle);
                border-radius: var(--radius-lg);
            }
        `,
    ];

    constructor() {
        super();
        this._subscription = this.useOp('frontend/billing_subscription');
        this._usage = this.useOp('frontend/billing_usage');
        this._history = this.useOp('frontend/billing_history');
        this._planChange = this.useOp('frontend/billing_plan_change');
        this._loaded = false;
    }

    updated() {
        if (!this._loaded) {
            this._loaded = true;
            this._subscription.run();
            this._usage.run();
            this._history.run();
        }
    }

    _topup() {
        this.openModal(FrontendTopupModal);
    }

    _changePlan(plan) {
        this._planChange.run({ plan });
    }

    _renderSubscription(subscription) {
        const plan = subscription && subscription.plan;
        const balance = subscription && subscription.balance;
        const budget = subscription && subscription.monthly_budget;
        const spent = subscription && subscription.current_month_spent;
        const periodStart = subscription && subscription.billing_period_start;
        const pct = _percent(spent, budget);
        const planName = plan ? this.t(_planTranslationKey(plan)) : '—';
        return html`
            <div class="grid">
                <glass-card><div class="stat">
                    <div class="stat-label">${this.t('current_plan.title')}</div>
                    <div class="stat-value">${planName}</div>
                </div></glass-card>

                <glass-card><div class="stat">
                    <div class="stat-label">${this.t('current_plan.balance')}</div>
                    <div class="stat-value">${_formatCurrency(balance)} ${this.t('frontend_console.currency_rub')}</div>
                </div></glass-card>

                <glass-card><div class="stat">
                    <div class="stat-label">${this.t('budget_usage.spent_this_month')}</div>
                    <div class="stat-value">${_formatCurrency(spent)} ${this.t('frontend_console.currency_rub')}</div>
                    ${budget && budget > 0
                        ? html`
                            <div class="progress ${pct >= 100 ? 'over' : ''}">
                                <div style="width: ${pct}%"></div>
                            </div>
                            <div class="stat-meta">
                                ${pct}% ${this.t('budget_usage.used')} · ${this.t('current_plan.monthly_limit')}: ${_formatCurrency(budget)}
                            </div>
                        `
                        : html`<div class="stat-meta">${this.t('current_plan.no_limit')}</div>`
                    }
                </div></glass-card>

                <glass-card><div class="stat">
                    <div class="stat-label">${this.t('budget_usage.billing_period')}</div>
                    <div class="stat-value">${periodStart ? new Date(periodStart).toLocaleDateString() : '—'}</div>
                </div></glass-card>
            </div>

            <div class="plan-row">
                ${PLAN_KEYS.map((p) => html`
                    <button class="btn btn-ghost"
                        data-active=${(plan || '').toLowerCase() === p ? 'true' : 'false'}
                        ?disabled=${(plan || '').toLowerCase() === p || this._planChange.busy}
                        @click=${() => this._changePlan(p)}
                    >${this.t(`tariff_plans.${p}.name`)}</button>
                `)}
            </div>
        `;
    }

    _renderUsage(usage) {
        if (!usage) return '';
        const byResource = usage.by_resource || {};
        const byUser = usage.by_user || {};
        const resourceRows = Object.entries(byResource);
        const userRows = Object.entries(byUser);
        return html`
            <section>
                <h3>${this.t('usage_stats.title')}</h3>
                <div class="grid">
                    <glass-card><div class="stat">
                        <div class="stat-label">${this.t('usage_stats.total_cost')}</div>
                        <div class="stat-value">${_formatCurrency(usage.total_cost)} ${this.t('frontend_console.currency_rub')}</div>
                    </div></glass-card>
                    <glass-card><div class="stat">
                        <div class="stat-label">${this.t('usage_stats.total_calls')}</div>
                        <div class="stat-value">${usage.total_calls || 0}</div>
                    </div></glass-card>
                </div>
            </section>

            <section>
                <h3>${this.t('resources.title')}</h3>
                ${resourceRows.length === 0
                    ? html`<div class="empty">${this.t('resources.no_data')}</div>`
                    : html`
                        <table>
                            <thead><tr>
                                <th>${this.t('resources.resource')}</th>
                                <th class="num">${this.t('resources.calls')}</th>
                                <th class="num">${this.t('resources.cost')}</th>
                            </tr></thead>
                            <tbody>
                                ${resourceRows.map(([resource, info]) => html`
                                    <tr>
                                        <td>${resource}</td>
                                        <td class="num">${info.calls || 0}</td>
                                        <td class="num">${_formatCurrency(info.cost)}</td>
                                    </tr>
                                `)}
                            </tbody>
                        </table>
                    `
                }
            </section>

            <section>
                <h3>${this.t('users.title')}</h3>
                ${userRows.length === 0
                    ? html`<div class="empty">${this.t('users.no_data')}</div>`
                    : html`
                        <table>
                            <thead><tr>
                                <th>${this.t('users.user')}</th>
                                <th class="num">${this.t('users.calls')}</th>
                                <th class="num">${this.t('users.cost')}</th>
                            </tr></thead>
                            <tbody>
                                ${userRows.map(([user, info]) => html`
                                    <tr>
                                        <td><platform-user-chip user-id=${user}></platform-user-chip></td>
                                        <td class="num">${info.calls || 0}</td>
                                        <td class="num">${_formatCurrency(info.cost)}</td>
                                    </tr>
                                `)}
                            </tbody>
                        </table>
                    `
                }
            </section>
        `;
    }

    _renderHistory(history) {
        if (history.length === 0) {
            return html`
                <section>
                    <h3>${this.t('payment_history.title')}</h3>
                    <div class="empty">
                        <div>${this.t('payment_history.empty_title')}</div>
                        <div>${this.t('payment_history.empty_description')}</div>
                    </div>
                </section>
            `;
        }
        return html`
            <section>
                <h3>${this.t('payment_history.title')}</h3>
                <table>
                    <thead><tr>
                        <th>${this.t('history_table.date')}</th>
                        <th class="num">${this.t('history_table.amount')}</th>
                        <th>${this.t('history_table.provider')}</th>
                        <th>${this.t('history_table.status')}</th>
                    </tr></thead>
                    <tbody>
                        ${history.map((p) => {
                            const status = (p.status || '').toLowerCase();
                            const statusLabel = this.t(`status.${status}`);
                            return html`
                                <tr>
                                    <td>${p.created_at ? new Date(p.created_at).toLocaleString() : '—'}</td>
                                    <td class="num">${_formatCurrency(p.amount)}</td>
                                    <td>${p.payment_provider || '—'}</td>
                                    <td><span class="status-tag ${status}">${statusLabel}</span></td>
                                </tr>
                            `;
                        })}
                    </tbody>
                </table>
            </section>
        `;
    }

    render() {
        const subscription = this._subscription.lastResult;
        const usage = this._usage.lastResult;
        const historyResult = this._history.lastResult;
        const history = (historyResult && historyResult.items) || [];
        const loading = this._subscription.busy && !subscription;
        return html`
            <page-header
                title=${this.t('frontend_console.page_title')}
                subtitle=${this.t('frontend_console.balance_available')}
            >
                <button slot="actions" class="btn" @click=${this._topup}>
                    ${this.t('frontend_console.top_up')}
                </button>
            </page-header>

            ${loading
                ? html`<div class="empty"><glass-spinner></glass-spinner></div>`
                : html`
                    ${this._renderSubscription(subscription)}
                    ${this._renderUsage(usage)}
                    ${this._renderHistory(history)}
                `
            }
        `;
    }
}

customElements.define('frontend-billing-page', FrontendBillingPage);
